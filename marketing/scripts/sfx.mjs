// Synthesizes the launch film's sound effects (no samples, no third-party audio) to a 48 kHz stereo WAV.
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { ROOT_DIR } from "./paths.mjs";

const RATE = 48000;
const cues = JSON.parse(readFileSync(join(ROOT_DIR, "src", "launch", "cues.json"), "utf8"));
const n = Math.ceil(cues.duration * RATE);
const L = new Float32Array(n);
const R = new Float32Array(n);
const TAU = Math.PI * 2;

/** Add a mono voice at start time t (s) for len seconds; fn(sampleTime) returns the sample. */
function voice(t, len, fn, pan = 0) {
  const s0 = Math.floor(t * RATE), s1 = Math.min(n, s0 + Math.floor(len * RATE));
  const gl = Math.cos((pan + 1) * Math.PI / 4), gr = Math.sin((pan + 1) * Math.PI / 4);
  for (let i = Math.max(0, s0); i < s1; i++) {
    const v = fn((i - s0) / RATE);
    L[i] += v * gl;
    R[i] += v * gr;
  }
}

const env = (x, a, d) => (x < a ? x / a : Math.exp(-(x - a) / d));

function ring(t) {
  for (const off of [0, 0.42]) {
    voice(t + off, 0.36, (x) => {
      const am = 0.5 + 0.5 * Math.sin(TAU * 18 * x);
      const e = Math.min(1, x / 0.02) * Math.min(1, (0.36 - x) / 0.05);
      return 0.07 * e * am * (Math.sin(TAU * 440 * x) + Math.sin(TAU * 480 * x));
    });
  }
}

function thump(t) {
  voice(t, 1.2, (x) => 0.32 * env(x, 0.008, 0.28) * Math.sin(TAU * (52 + 30 * Math.exp(-x * 18)) * x));
}

function chime(t) {
  [[659.25, 0.11], [987.77, 0.07], [1318.5, 0.04]].forEach(([f, g], k) =>
    voice(t, 2.6, (x) => g * env(x, 0.004, 0.9 - k * 0.2) * Math.sin(TAU * f * x), k === 1 ? -0.2 : 0.2));
}

function blip(t) {
  voice(t, 0.6, (x) => 0.05 * env(x, 0.003, 0.12) * (Math.sin(TAU * 1318.5 * x) + 0.6 * Math.sin(TAU * 1975.5 * x)));
}

function whoosh(t) {
  let lp = 0, seed = Math.floor(t * 1000) + 7;
  const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff * 2 - 1; };
  voice(t - 0.45, 0.9, (x) => {
    const a = 0.02 + 0.25 * Math.min(1, x / 0.45);
    lp += a * (rnd() - lp);
    const e = x < 0.45 ? Math.pow(x / 0.45, 2) : Math.exp(-(x - 0.45) / 0.12);
    return 0.09 * e * lp;
  });
}

function drone(t0, t1) {
  const len = t1 - t0;
  voice(t0, len, (x) => {
    const e = Math.min(1, x / 1.5) * Math.min(1, (len - x) / 1.2);
    const trem = 0.8 + 0.2 * Math.sin(TAU * 0.25 * x);
    return 0.06 * e * trem * (Math.sin(TAU * 55 * x) + 0.7 * Math.sin(TAU * 82.41 * x) + 0.25 * Math.sin(TAU * 110 * x));
  });
}

drone(...cues.sfx.drone);
cues.sfx.ring.forEach(ring);
cues.sfx.thump.forEach(thump);
cues.sfx.whoosh.forEach(whoosh);
cues.sfx.chime.forEach(chime);
cues.sfx.blip.forEach(blip);

const out = Buffer.alloc(44 + n * 4);
out.write("RIFF", 0); out.writeUInt32LE(36 + n * 4, 4); out.write("WAVE", 8);
out.write("fmt ", 12); out.writeUInt32LE(16, 16); out.writeUInt16LE(1, 20); out.writeUInt16LE(2, 22);
out.writeUInt32LE(RATE, 24); out.writeUInt32LE(RATE * 4, 28); out.writeUInt16LE(4, 32); out.writeUInt16LE(16, 34);
out.write("data", 36); out.writeUInt32LE(n * 4, 40);
for (let i = 0; i < n; i++) {
  out.writeInt16LE(Math.round(Math.max(-1, Math.min(1, L[i])) * 32767), 44 + i * 4);
  out.writeInt16LE(Math.round(Math.max(-1, Math.min(1, R[i])) * 32767), 46 + i * 4);
}
const dest = join(ROOT_DIR, "out", "sfx.wav");
writeFileSync(dest, out);
console.log("wrote", dest);
