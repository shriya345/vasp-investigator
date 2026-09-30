import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { test, expect } from "@playwright/test";

test("demo investigation, evidence, report and persisted case", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page
    .getByRole("button", { name: "Explore demo investigation" })
    .click();
  await expect(page.getByText("Why Binance (demo)?")).toBeVisible();
  await expect(page.getByText("$18,000", { exact: true })).toBeVisible();
  await expect(page.locator(".react-flow__node").first()).toBeVisible();
  await page.screenshot({
    path: "test-results/dashboard-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: /02 Coinbase/ }).click();
  await expect(page.getByText("Why Coinbase (demo)?")).toBeVisible();
  await page.getByLabel("Graph hop depth").selectOption("2");
  await expect(page.locator(".react-flow__node")).toHaveCount(10);
  await page.getByRole("button", { name: "Transactions", exact: true }).click();
  await page.locator("tbody tr").first().click();
  await expect(
    page.getByRole("dialog", { name: "Evidence details" }),
  ).toBeVisible();
  await expect(
    page.getByText("transaction detail", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close evidence" }).click();
  await page.getByRole("button", { name: "Report", exact: true }).click();
  await expect(page.locator(".report pre")).toContainText(
    "Evidence digest (SHA-256)",
  );
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export report" }).click();
  expect((await download).suggestedFilename()).toMatch(/CASE-.*\.md/);
  await page.reload();
  await page.getByRole("button", { name: "Case library", exact: true }).click();
  await page.locator(".case-list-item").first().click();
  await expect(page.getByText("Why Binance (demo)?")).toBeVisible();
  expect(errors).toEqual([]);
});

test("imported empty case produces no fabricated candidate", async ({
  page,
}) => {
  await page.goto("/");
  await page.locator("input[type=file]").setInputFiles({
    name: "empty.json",
    mimeType: "application/json",
    buffer: Buffer.from(
      JSON.stringify({
        target: "0x0000000000000000000000000000000000000001",
        chain: "ethereum",
        mode: "import",
        transactions: [],
        labels: [],
      }),
    ),
  });
  await expect(
    page
      .locator(".attribution-summary")
      .getByText("No VASP attribution supported by available evidence."),
  ).toBeVisible();
  await expect(page.getByText("IMPORT", { exact: true })).toBeVisible();
});

test("mobile dashboard remains navigable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Explore demo investigation" })
    .click();
  await expect(page.getByText("Why Binance (demo)?")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/dashboard-mobile.png",
    fullPage: true,
  });
});

test("nearest VASP, simulated routing gate and audit", async ({ page }) => {
  await page.goto("/");
  const fixture = readFileSync(
    resolve(process.cwd(), "../backend/data/test_cases/01_strong_vasp.json"),
  );
  await page.locator("input[type=file]").setInputFiles({
    name: "strong.json",
    mimeType: "application/json",
    buffer: fixture,
  });
  await expect(
    page
      .locator(".attribution-summary")
      .getByText("NEAREST VASP", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("HIGHEST-CONFIDENCE VASP")).toBeVisible();
  await page.getByRole("button", { name: "VASP attribution" }).click();
  await expect(
    page.getByText("SIMULATED — No connection to the live SAHYOG Portal"),
  ).toBeVisible();
  await page.getByLabel("Case/FIR reference").fill("FIR-BROWSER-1");
  await page.getByLabel("Investigating agency").fill("Test agency");
  await page.getByRole("button", { name: "Prepare simulated request" }).click();
  await expect(page.locator(".error[role=alert]")).toContainText(
    "authorized investigation",
  );
  await page
    .getByLabel("I confirm this forms part of an authorized investigation.")
    .check();
  await page
    .getByLabel(
      "I have reviewed the attribution evidence and confirm simulated preparation.",
    )
    .check();
  await page.getByRole("button", { name: "Prepare simulated request" }).click();
  await expect(page.locator(".simulation-result")).toContainText("SIM-SAHYOG-");
  await expect(page.locator(".simulation-result")).toContainText("prepared");
  await page.getByRole("button", { name: "Mark sent (simulated)" }).click();
  await expect(page.locator(".simulation-result")).toContainText("sent");
  await expect(page.locator(".integrity-panel")).toContainText(
    "Audit chain: Valid",
  );
  await expect(page.locator(".audit-list")).toContainText("routing state sent");
});
