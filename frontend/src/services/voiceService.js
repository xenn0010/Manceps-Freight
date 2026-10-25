import { useStore } from "../store/useStore";
import { VOICE_PRESET } from "../data/scripts";
import { aiService } from "./aiService";
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
    const { status } = useStore.getState().transient.voice;
    if (status !== "idle") return this.cancel();
    clear();
    setVoice({ status: "listening", transcript: "" });
    timers.push(setTimeout(() => setVoice({ status: "transcribing", transcript: "" }), 2600));
    VOICE_PRESET.split(" ").forEach((_, i, words) =>
      timers.push(setTimeout(() => setVoice({ status: "transcribing", transcript: words.slice(0, i + 1).join(" ") }), 2700 + i * 140))
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
