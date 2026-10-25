// Captures still screenshots of the prebuilt dispatch app into marketing/screens/.
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { ROOT, launch, openApp, settle } from "./lib.mjs";

const OUT = join(ROOT, "screens");
const BEN_CALL_WAIT_MS = 12500;
const SHEET_STEP_WAIT_MS = 1400;
const ANSWER_WAIT_MS = 1500;
const FLY_WAIT_MS = 2600;

/** Save a full-viewport PNG. */
async function shot(page, name) {
  await page.screenshot({ path: join(OUT, name + ".png") });
  console.log("saved", name);
}

async function mapStates(browser, w, h, tag) {
  const { context, page } = await openApp(browser, { width: w, height: h });
  await page.waitForTimeout(800);
  await shot(page, `map-overview-${tag}`);
  const card = page.locator("text=Needs your yes").locator("xpath=ancestor::div[2]");
  if (tag === "1920") await card.screenshot({ path: join(OUT, "needs-your-yes-card.png") });
  await page.waitForTimeout(BEN_CALL_WAIT_MS);
  await shot(page, `map-agent-call-bubble-${tag}`);
  await page.getByRole("button", { name: "Truck 102" }).click();
  await settle(page, FLY_WAIT_MS);
  await shot(page, `truck-102-live-call-${tag}`);
  await page.getByRole("button", { name: "Truck 103" }).click();
  await settle(page, FLY_WAIT_MS);
  const panelTabs = [["Load", "load"], ["Driver", "driver"], ["Route", "route"], ["Truck", "truck"]];
  for (const [label, key] of panelTabs) {
    await page.getByRole("button", { name: label, exact: true }).click();
    await page.waitForTimeout(500);
    await shot(page, `truck-103-${key}-tab-${tag}`);
  }
  await context.close();
}

async function sheetStates(browser, w, h, tag) {
  const { context, page } = await openApp(browser, { width: w, height: h });
  await page.getByRole("button", { name: "Sheet", exact: true }).click();
  await page.waitForTimeout(900);
  await shot(page, `sheet-loads-${tag}`);
  await page.getByRole("button", { name: /Find backhauls/ }).click();
  await page.waitForTimeout(SHEET_STEP_WAIT_MS);
  await shot(page, `sheet-agent-editing-${tag}`);
  await page.waitForTimeout(3500);
  await page.getByRole("button", { name: /Negotiate offers/ }).click();
  await page.waitForTimeout(900);
  await shot(page, `sheet-agent-negotiating-${tag}`);
  await page.waitForTimeout(4000);
  await shot(page, `sheet-after-agent-${tag}`);
  await context.close();
}

async function panels(browser) {
  const { context, page } = await openApp(browser, { width: 1920, height: 1080 });
  await page.keyboard.press("/");
  await page.waitForTimeout(600);
  await page.getByRole("button", { name: "What did you do today?" }).click();
  await page.waitForTimeout(ANSWER_WAIT_MS);
  await shot(page, "chat-panel-1920");
  await page.getByRole("button", { name: "Balanced" }).first().click();
  await page.waitForTimeout(700);
  await shot(page, "permissions-panel-1920");
  await page.keyboard.press("Escape");
  await page.reload();
  await settle(page);
  await page.getByRole("button", { name: "Account" }).click();
  await page.waitForTimeout(900);
  await shot(page, "account-dashboard-1920");
  await page.getByRole("button", { name: "Account" }).click();
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: "Book it" }).click();
  await page.waitForTimeout(1200);
  await shot(page, "map-booked-toast-1920");
  await context.close();
}

async function mobile(browser) {
  const { context, page } = await openApp(browser, { width: 430, height: 932, scale: 3, mobile: true });
  await page.waitForTimeout(800);
  await shot(page, "mobile-map-430");
  await page.getByRole("button", { name: "Truck 101" }).click();
  await settle(page, FLY_WAIT_MS);
  await shot(page, "mobile-truck-101-430");
  await context.close();
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  const only = process.argv[2];
  const browser = await launch();
  try {
    if (!only || only === "map") { await mapStates(browser, 1920, 1080, "1920"); await mapStates(browser, 1440, 900, "1440"); }
    if (!only || only === "sheet") { await sheetStates(browser, 1920, 1080, "1920"); await sheetStates(browser, 1440, 900, "1440"); }
    if (!only || only === "panels") await panels(browser);
    if (!only || only === "mobile") await mobile(browser);
  } finally {
    await browser.close();
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
