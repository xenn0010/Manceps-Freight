import { useStore } from "../store/useStore";
import { VOICE_PRESET } from "../data/scripts";
import { aiService } from "./aiService";
import { vapiVoice } from "./vapiVoice";
import { toast } from "sonner";

// Simulated microphone: listening waveform -> transcribed preset -> scripted answer.
let timers = [];
const clear = () => {
  timers.forEach(clearTimeout);
  timers = [];
};
const setVoice = (v) => useStore.getState().setVoice(v);

export const voiceService = {
  toggle() {
    const { status, mode } = useStore.getState().transient.voice;
    if (status !== "idle") return mode === "live" ? vapiVoice.stop() : this.cancel();
    if (vapiVoice.available() && !window.location.search.includes("voice=demo"))
      return vapiVoice.start((reason) => {
        console.warn(`[voice] ${reason}`);
        vapiVoice.stop();
        toast("Voice unavailable, using demo voice", { description: reason });
        this.demo();
      });
    this.demo();
  },
  demo() {
    clear();
    setVoice({ status: "listening", transcript: "", mode: "demo", notice: "Demo voice" });
    timers.push(setTimeout(() => setVoice({ status: "transcribing", transcript: "", mode: "demo" }), 2600));
    VOICE_PRESET.split(" ").forEach((_, i, words) =>
      timers.push(setTimeout(() => setVoice({ status: "transcribing", transcript: words.slice(0, i + 1).join(" "), mode: "demo" }), 2700 + i * 140))
    );
    timers.push(
      setTimeout(() => {
        setVoice({ status: "idle", transcript: "" });
        aiService.ask(VOICE_PRESET);
      }, 2700 + VOICE_PRESET.split(" ").length * 140 + 500)
    );
  },
  cancel(silent = false) {
    const wasActive = useStore.getState().transient.voice.status !== "idle";
    clear();
    setVoice({ status: "idle", transcript: "" });
    if (wasActive && !silent) toast("Listening cancelled", { description: "No command sent" });
  },
};
