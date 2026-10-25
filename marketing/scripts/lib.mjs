// Shared Playwright helpers for capturing the prebuilt Manceps dispatch app.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { installMockApi } from "./mockapi.mjs";

export const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
export const APP_URL = process.env.MANCEPS_APP_URL ?? "http://127.0.0.1:4791/app";
const COPY_FIX = readFileSync(join(ROOT, "scripts", "copyfix.js"), "utf8");
const TILE_SETTLE_MS = 2500;
const NETWORK_IDLE_TIMEOUT_MS = 20000;

/** A soft visible pointer, since headless Chromium draws none. Follows real mouse events. */
const CURSOR = `(() => {
  const add = () => {
    const c = document.createElement("div");
    c.id = "mk-cursor";
    c.style.cssText = "position:fixed;left:0;top:0;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;background:rgba(1,13,29,.28);border:2px solid rgba(255,255,255,.95);box-shadow:0 4px 14px rgba(1,13,29,.35);z-index:2147483647;pointer-events:none;transform:translate(-100px,-100px);transition:width .12s,height .12s,margin .12s;";
    document.body.appendChild(c);
    addEventListener("mousemove", (e) => { c.style.transform = "translate(" + e.clientX + "px," + e.clientY + "px)"; }, true);
    addEventListener("mousedown", () => { c.style.width = c.style.height = "16px"; c.style.margin = "-8px 0 0 -8px"; }, true);
    addEventListener("mouseup", () => { c.style.width = c.style.height = "22px"; c.style.margin = "-11px 0 0 -11px"; }, true);
  };
  if (document.body) add(); else document.addEventListener("DOMContentLoaded", add);
})();`;

/**
 * Launch Chrome (or bundled Chromium when MANCEPS_BROWSER_CHANNEL=bundled) with flags so maplibre and three.js render.
 *
 * Returns:
 *   The launched browser.
 */
export async function launch() {
  const channel = process.env.MANCEPS_BROWSER_CHANNEL ?? "chrome";
  return chromium.launch({ channel: channel === "bundled" ? undefined : channel, args: (process.env.MANCEPS_SWIFTSHADER ? ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] : []).concat(["--ignore-gpu-blocklist", "--hide-scrollbars"]) });
}

/**
 * Open the app in a fresh context and wait for map tiles to settle.
 *
 * Args:
 *   browser: Launched browser.
 *   opts: { width, height, scale, cursor, mobile }.
 *
 * Returns:
 *   { context, page }.
 */
export async function openApp(browser, { width, height, scale = 2, cursor = false, mobile = false }) {
  const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: scale, isMobile: mobile, hasTouch: mobile, colorScheme: "light", locale: "en-US", timezoneId: "America/Los_Angeles" });
  await installMockApi(context, new URL(APP_URL).origin);
  await context.addInitScript(COPY_FIX);
  if (cursor) await context.addInitScript(CURSOR);
  const page = await context.newPage();
  page.on("pageerror", (e) => console.error("[pageerror]", e.message));
  await page.goto(APP_URL, { waitUntil: "load" });
  await settle(page);
  return { context, page };
}

/**
 * Wait for network idle plus a short settle for map tiles and fly animations.
 *
 * Args:
 *   page: The page.
 *   extraMs: Additional settle time.
 */
export async function settle(page, extraMs = TILE_SETTLE_MS) {
  await page.waitForLoadState("networkidle", { timeout: NETWORK_IDLE_TIMEOUT_MS }).catch(() => console.warn("networkidle timed out; continuing"));
  await page.waitForTimeout(extraMs);
}

/**
 * Move the visible pointer smoothly to an element's center and click it.
 *
 * Args:
 *   page: The page.
 *   locator: Playwright locator.
 *   steps: Mouse move interpolation steps.
 */
export async function glideClick(page, locator, steps = 30) {
  const box = await locator.boundingBox();
  if (!box) throw new Error("glideClick: element not visible");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps });
  await page.waitForTimeout(250);
  await page.mouse.down();
  await page.waitForTimeout(90);
  await page.mouse.up();
}
