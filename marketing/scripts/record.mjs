// Records key interactions of the prebuilt dispatch app with a CDP screencast,
// then encodes each to a constant-frame-rate H.264 clip in marketing/recordings/.
import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { ROOT, glideClick, launch, openApp, settle } from "./lib.mjs";

const OUT = join(ROOT, "recordings");
const RAW = join(ROOT, ".raw");
const FFMPEG = process.env.FFMPEG ?? "/usr/local/bin/ffmpeg";
const FPS = 30;
const JPEG_QUALITY = 92;
const W = 1920;
const H = 1080;

/**
 * Run `fn` while capturing screencast frames, then encode them.
 *
 * Args:
 *   page: Playwright page.
 *   name: Clip name (file stem).
 *   fn: Async interaction script.
 */
async function capture(page, name, fn) {
  const dir = join(RAW, name);
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  const cdp = await page.context().newCDPSession(page);
  const frames = [];
  cdp.on("Page.screencastFrame", async ({ data, metadata, sessionId }) => {
    const file = join(dir, String(frames.length).padStart(6, "0") + ".jpg");
    writeFileSync(file, Buffer.from(data, "base64"));
    frames.push({ file, t: metadata.timestamp });
    await cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
  });
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: JPEG_QUALITY, maxWidth: W, maxHeight: H, everyNthFrame: 1 });
  const t0 = Date.now() / 1000;
  await fn();
  const t1 = Date.now() / 1000;
  await cdp.send("Page.stopScreencast");
  await cdp.detach();
  if (frames.length < 2) throw new Error(`capture ${name}: only ${frames.length} frames`);
  encode(name, dir, frames, Math.max(t1, frames[frames.length - 1].t + 1 / FPS), t0);
}

function encode(name, dir, frames, end, t0) {
  const lines = ["ffconcat version 1.0"];
  const first = frames[0];
  frames.forEach((f, i) => {
    const next = i + 1 < frames.length ? frames[i + 1].t : end;
    const start = i === 0 ? Math.min(first.t, t0) : f.t;
    lines.push(`file '${f.file}'`, `duration ${Math.max(0.001, next - start).toFixed(4)}`);
  });
  lines.push(`file '${frames[frames.length - 1].file}'`);
  const list = join(dir, "list.ffconcat");
  writeFileSync(list, lines.join("\n"));
  const out = join(OUT, name + ".mp4");
  execFileSync(FFMPEG, ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list, "-vf", `fps=${FPS},scale=${W}:${H}:flags=lanczos,format=yuv420p`, "-c:v", "libx264", "-crf", "14", "-preset", "slow", "-movflags", "+faststart", out]);
  rmSync(dir, { recursive: true, force: true });
  console.log("encoded", out, frames.length, "frames");
}

const btn = (page, name, exact = true) => page.getByRole("button", { name, exact });

async function truckSelect(browser) {
  const { context, page } = await openApp(browser, { width: W, height: H, scale: 1, cursor: true });
  await page.mouse.move(W * 0.55, H * 0.75);
  await capture(page, "rec-truck-select", async () => {
    await page.waitForTimeout(1200);
    await glideClick(page, btn(page, "Truck 103"), 40);
    await page.waitForTimeout(3600);
    await glideClick(page, btn(page, "Driver"), 30);
    await page.waitForTimeout(1600);
    await glideClick(page, btn(page, "Route"), 20);
    await page.waitForTimeout(1800);
  });
  await context.close();
}

async function sheetAgent(browser) {
  const { context, page } = await openApp(browser, { width: W, height: H, scale: 1, cursor: true });
  await btn(page, "Sheet").click();
  await page.waitForTimeout(1200);
  await page.mouse.move(W * 0.5, H * 0.5);
  await capture(page, "rec-sheet-agent", async () => {
    await page.waitForTimeout(900);
    await glideClick(page, btn(page, /Find backhauls/, false), 35);
    await page.waitForTimeout(4600);
    await glideClick(page, btn(page, /Negotiate offers/, false), 25);
    await page.waitForTimeout(4200);
  });
  await context.close();
}

async function approve(browser) {
  const { context, page } = await openApp(browser, { width: W, height: H, scale: 1, cursor: true });
  await page.mouse.move(W * 0.45, H * 0.6);
  await capture(page, "rec-approve-backhaul", async () => {
    await page.waitForTimeout(1500);
    await glideClick(page, btn(page, "Book it"), 45);
    await page.waitForTimeout(4200);
  });
  await context.close();
}

/** One continuous take of the whole flow, used by the landing-page demo. */
async function demoFlow(browser) {
  const { context, page } = await openApp(browser, { width: W, height: H, scale: 1, cursor: true });
  await page.mouse.move(W * 0.6, H * 0.7);
  await capture(page, "rec-demo-flow", async () => {
    await page.waitForTimeout(1500);
    await glideClick(page, btn(page, "Truck 101"), 40);
    await page.waitForTimeout(4200);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(1600);
    await glideClick(page, btn(page, "Sheet"), 35);
    await page.waitForTimeout(1500);
    await glideClick(page, btn(page, /Find backhauls/, false), 35);
    await page.waitForTimeout(4300);
    await glideClick(page, btn(page, /Negotiate offers/, false), 25);
    await page.waitForTimeout(4300);
    await glideClick(page, btn(page, "Map"), 35);
    await settle(page, 1500);
    await glideClick(page, btn(page, "Book it"), 40);
    await page.waitForTimeout(4500);
  });
  await context.close();
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  const only = process.argv[2];
  const jobs = { truck: truckSelect, sheet: sheetAgent, approve, demo: demoFlow };
  const browser = await launch();
  try {
    for (const [k, fn] of Object.entries(jobs)) if (!only || only === k) await fn(browser);
  } finally {
    await browser.close();
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
