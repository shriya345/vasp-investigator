"""Provider-independent evidence contracts. Amounts are decimal strings on the wire."""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Chain(str, Enum):
    ethereum = "ethereum"
    bnb = "bnb"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Transaction(StrictModel):
    tx_hash: str = Field(pattern=r"^0x[a-fA-F0-9]{64}$")
    event_index: int = Field(default=0, ge=0)
    chain: Chain
    block_number: int = Field(ge=0)
    transaction_index: int = Field(default=0, ge=0)
    timestamp: datetime
    from_address: str = Field(pattern=r"^0x[a-fA-F0-9]{40}$")
    to_address: str = Field(pattern=r"^0x[a-fA-F0-9]{40}$")
    asset: str = Field(min_length=1, max_length=20)
    amount: Decimal = Field(gt=0, max_digits=60, decimal_places=30)
    usd_value: Optional[Decimal] = Field(
        default=None, ge=0, max_digits=60, decimal_places=30
    )
    contract_address: Optional[str] = Field(
        default=None, pattern=r"^0x[a-fA-F0-9]{40}$"
    )
    transaction_type: str = Field(
        default="native", pattern=r"^(native|token|internal)$"
    )
    source: str = Field(min_length=1, max_length=200)
    source_confidence: float = Field(ge=0, le=1)

    @field_validator("from_address", "to_address", "tx_hash", "contract_address")
    @classmethod
    def lowercase(cls, value):
        return value.lower() if value else value

    @field_validator("timestamp")
    @classmethod
    def utc_timestamp(cls, value):
        if value.tzinfo is None:
            raise ValueError("timestamp must include a timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def asset_identity(self):
        if self.transaction_type == "token" and not self.contract_address:
            raise ValueError("token transfers require contract_address")
        if self.transaction_type != "token" and self.contract_address:
            raise ValueError("contract_address identifies token assets only")
        return self

    @property
    def asset_key(self):
        return self.contract_address or "native"

    @property
    def evidence_id(self):
        return f"{self.chain.value}:{self.tx_hash}:{self.event_index}"


class Label(StrictModel):
    address: str = Field(pattern=r"^0x[a-fA-F0-9]{40}$")
    chain: Chain
    entity: str = Field(min_length=1, max_length=100)
    entity_type: str = Field(
        pattern=r"^(vasp|exchange|mixer|bridge|dex|contract|scam|sanctioned)$"
    )
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    strength: str = Field(pattern=r"^(strong|probable|weak)$")
    source: str = Field(min_length=1, max_length=300)
    source_url: Optional[str] = Field(
        default=None, max_length=500, pattern=r"^https://"
    )
    source_reliability: Optional[float] = Field(default=None, ge=0, le=1)
    observed_at: Optional[datetime] = None
    # Entity-level regulatory status is separate from address ownership evidence.
    fiu_registered: Optional[bool] = None
    synthetic: bool = False

    @field_validator("fiu_registered")
    @classmethod
    def no_unverified_fiu_status(cls, value):
        if value is not None:
            raise ValueError(
                "FIU-IND status requires a verified registry source; current datasets do not provide one"
            )
        return value

    @field_validator("address")
    @classmethod
    def lowercase(cls, value):
        return value.lower()

    @field_validator("observed_at")
    @classmethod
    def dated_source(cls, value):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("observed_at must include timezone")
        return value.astimezone(timezone.utc)


class InvestigationRequest(StrictModel):
    target: str = Field(pattern=r"^0x[a-fA-F0-9]{40}$")
    chain: Chain = Chain.ethereum
    mode: str = Field(default="demo", pattern=r"^(demo|import|live)$")
    max_hops: int = Field(default=4, ge=1, le=6)
    transactions: list[Transaction] = Field(default_factory=list, max_length=5000)
    labels: list[Label] = Field(default_factory=list, max_length=1000)
    title: str = Field(default="Wallet investigation", min_length=1, max_length=100)

    @field_validator("target")
    @classmethod
    def lowercase(cls, value):
        return value.lower()

    @model_validator(mode="after")
    def coherent_evidence(self):
        if self.mode == "demo" and (self.transactions or self.labels):
            raise ValueError("demo does not accept imported evidence")
        if any(t.chain != self.chain for t in self.transactions) or any(
            label.chain != self.chain for label in self.labels
        ):
            raise ValueError("all evidence must match the selected chain")
        ids = [t.evidence_id for t in self.transactions]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate transaction event identity")
        addresses = [label.address for label in self.labels]
        if len(addresses) != len(set(addresses)):
            raise ValueError("conflicting or duplicate address labels")
        if self.mode != "demo" and any(label.synthetic for label in self.labels):
            raise ValueError("synthetic labels are only permitted in demo mode")
        return self
