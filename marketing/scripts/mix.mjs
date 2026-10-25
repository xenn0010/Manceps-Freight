// Mixes the edited music bed and synthesized SFX under the silent Remotion render,
// masters to -14 LUFS integrated (two-pass loudnorm) and writes the final launch MP4(s).
// Usage: node scripts/mix.mjs <silent-video.mp4> <out.mp4> [--4k]
import { execFileSync, spawnSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { ROOT_DIR } from "./paths.mjs";

const FFMPEG = process.env.FFMPEG ?? "/usr/local/bin/ffmpeg";
const MUSIC = join(ROOT_DIR, "audio", "dreamer-kevin-macleod.mp3");
const SFX = join(ROOT_DIR, "out", "sfx.wav");
const cues = JSON.parse(readFileSync(join(ROOT_DIR, "src", "launch", "cues.json"), "utf8"));
const TARGET = { I: -14, TP: -1.5, LRA: 11 };
const QUIET = 0.36;
const DUCK = 0.3;
const NIGHT = 0.62;
const CLOSED_HZ = 420;
const DUCK_HZ = 750;
const NIGHT_HZ = 3200;
const OPEN_HZ = 20000;
const STEP_S = 0.1;

/** Piecewise music gain at film time t (seconds), as an ffmpeg expression. */
function gainExpr() {
  const [o0, o1] = cues.musicOpen, [d0, d1] = cues.duck, [n0, n1] = cues.night;
  const ramp = (a, b, from, to) => `if(between(t,${a},${b}),${from}+(${to}-${from})*(t-${a})/(${b - a})`;
  return [
    `if(lt(t,${o0}),${QUIET}`,
    ramp(o0, o1, QUIET, 1),
    ramp(d0 - 0.3, d0, 1, DUCK),
    `if(between(t,${d0},${d1}),${DUCK}`,
    ramp(d1, d1 + 0.6, DUCK, 1),
    ramp(n0 - 0.3, n0, 1, NIGHT),
    `if(between(t,${n0},${n1}),${NIGHT}`,
    ramp(n1, n1 + 0.6, NIGHT, 1),
    "1",
  ].join(",") + ")".repeat(8);
}

/** asendcmd script sweeping the low-pass cutoff over the film. */
function cutoffCommands() {
  const lines = [];
  const at = (t, hz) => lines.push(`${t.toFixed(2)} lowpass f ${Math.round(hz)};`);
  const sweep = (t0, t1, a, b) => {
    for (let t = t0; t <= t1 + 1e-6; t += STEP_S) at(t, a * Math.pow(b / a, (t - t0) / (t1 - t0)));
  };
  at(0, CLOSED_HZ);
  sweep(cues.musicOpen[0], cues.musicOpen[1], CLOSED_HZ, OPEN_HZ);
  sweep(cues.duck[0] - 0.3, cues.duck[0], OPEN_HZ, DUCK_HZ);
  sweep(cues.duck[1], cues.duck[1] + 0.6, DUCK_HZ, OPEN_HZ);
  sweep(cues.night[0] - 0.3, cues.night[0], OPEN_HZ, NIGHT_HZ);
  sweep(cues.night[1], cues.night[1] + 0.6, NIGHT_HZ, OPEN_HZ);
  const file = join(ROOT_DIR, "out", "cutoff.cmd");
  writeFileSync(file, lines.join("\n"));
  return file;
}

function graph(cmdFile, norm) {
  const len = cues.duration - cues.musicIn;
  const [f0, f1] = cues.fadeOut;
  const delayMs = Math.round(cues.musicIn * 1000);
  return [
    `[1:a]atrim=0:${len},asetpts=PTS-STARTPTS,aresample=48000,adelay=${delayMs}|${delayMs},apad=whole_dur=${cues.duration},asendcmd=f='${cmdFile}',lowpass=f=${CLOSED_HZ}:p=2,volume='${gainExpr()}':eval=frame,afade=t=out:st=${f0}:d=${f1 - f0}[m]`,
    `[2:a]aresample=48000[s]`,
    `[m][s]amix=inputs=2:normalize=0:duration=first,atrim=0:${cues.duration},${norm}[a]`,
  ].join(";");
}

function main() {
  const [video, out, flag] = process.argv.slice(2);
  if (!video || !out) throw new Error("usage: node scripts/mix.mjs <silent-video.mp4> <out.mp4> [--4k]");
  const cmd = cutoffCommands();
  const inputs = ["-i", video, "-i", MUSIC, "-i", SFX];
  const probe = `loudnorm=I=${TARGET.I}:TP=${TARGET.TP}:LRA=${TARGET.LRA}:print_format=json`;
  const run1 = spawnSync(FFMPEG, ["-hide_banner", ...inputs, "-filter_complex", graph(cmd, probe), "-map", "[a]", "-f", "null", "-"], { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
  if (run1.status !== 0) throw new Error("loudnorm pass 1 failed:\n" + run1.stderr.slice(-2000));
  const m = /\{[^{}]*"input_i"[^{}]*\}/.exec(run1.stderr);
  if (!m) throw new Error("loudnorm pass 1 produced no stats");
  const st = JSON.parse(m[0]);
  const norm = `loudnorm=I=${TARGET.I}:TP=${TARGET.TP}:LRA=${TARGET.LRA}:measured_I=${st.input_i}:measured_TP=${st.input_tp}:measured_LRA=${st.input_lra}:measured_thresh=${st.input_thresh}:offset=${st.target_offset}:linear=true,aresample=48000`;
  const vf = flag === "--4k" ? ["-vf", "scale=3840:2160:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-profile:v", "high", "-level", "5.1"] : ["-c:v", "copy"];
  execFileSync(FFMPEG, ["-y", "-hide_banner", "-loglevel", "error", ...inputs, "-filter_complex", graph(cmd, norm), "-map", "0:v", "-map", "[a]", ...vf, "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-shortest", out], { stdio: "inherit" });
  console.log("mixed", out, "input loudness", st.input_i, "LUFS");
}

main();
