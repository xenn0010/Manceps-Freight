import { useState } from "react";
import { Mic, ArrowUp, Sparkles, X } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useStore } from "../../store/useStore";
import { aiService, voiceService } from "../../services";
import { EXAMPLE_COMMANDS } from "../../data/scripts";
import { cn } from "../../lib/utils";

function Waveform() {
  return (
    <div className="flex h-6 items-center gap-[3px]" aria-hidden="true" data-testid="voice-waveform">
      {Array.from({ length: 22 }).map((_, i) => (
        <span key={i} className="wave-bar h-full w-[3px] rounded-full bg-[#AF6EFF]" style={{ animationDelay: `${(i * 73) % 600}ms`, opacity: 0.5 + ((i * 37) % 50) / 100 }} />
      ))}
    </div>
  );
}

export function CommandBar() {
  const [text, setText] = useState("");
  const voice = useStore((s) => s.transient.voice);
  const thinking = useStore((s) => aiService.isThinking(s.chat));
  const live = voice.status !== "idle";
  const submit = (q) => {
    if (!q.trim() || thinking) return;
    aiService.ask(q);
    setText("");
  };
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit(text);
      }}
      className="glass flex h-[60px] shrink-0 items-center gap-2 !rounded-[20px] pl-3 pr-2"
      data-testid="command-bar"
    >
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-[#181A1A] text-white"><Sparkles className="h-4 w-4" /></span>
      <div className="relative min-w-[180px] flex-1">
        <AnimatePresence mode="wait" initial={false}>
          {live ? (
            <motion.div key="voice" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} className="flex items-center gap-3" data-testid="voice-status">
              {voice.status === "listening" || voice.status === "connecting" || voice.status === "speaking" ? (
                <>
                  <Waveform />
                  <span className="shrink-0 text-[13.5px] font-medium text-[#7A35DB]" data-testid="voice-state">
                    {voice.status === "connecting" ? "Connecting…" : voice.status === "speaking" ? "FreightOS speaking" : "Listening…"}
                  </span>
                  {voice.mode === "live" && voice.transcript && <span className="truncate text-[13px] text-[#4B4F55]" data-testid="voice-caption">“{voice.transcript}”</span>}
                  <span className="ml-auto shrink-0 rounded-md bg-[#181A1A]/[0.06] px-1.5 py-0.5 text-[10.5px] font-semibold text-[#4B4F55]" data-testid="voice-mode-badge">{voice.mode === "live" ? "Live voice" : "Demo voice"}</span>
                </>
              ) : (
                <span className="truncate text-[14px] font-medium" data-testid="voice-transcript">“{voice.transcript}”</span>
              )}
            </motion.div>
          ) : (
            <motion.input
              key="input"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Ask FreightOS…"
              aria-label="Ask FreightOS"
              data-testid="command-input"
              className="h-10 w-full bg-transparent text-[14.5px] placeholder:text-[#6B6F76] focus:outline-none focus-visible:outline-none"
            />
          )}
        </AnimatePresence>
      </div>
      <div className="no-scrollbar flex shrink items-center gap-1.5 overflow-x-auto" data-testid="command-chips">
        {EXAMPLE_COMMANDS.map((c) => (
          <button
            key={c}
            type="button"
            disabled={thinking || live}
            data-testid={`chip-${c.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/-$/, "")}`}
            onClick={() => submit(c)}
            className="shrink-0 rounded-xl bg-white/80 px-2.5 py-1.5 text-[12px] font-medium text-[#3f4247] transition-colors hover:bg-white disabled:opacity-50"
          >
            {c}
          </button>
        ))}
      </div>
      <button
        type="button"
        onClick={() => voiceService.toggle()}
        aria-label={live ? "Stop listening" : "Speak a command"}
        aria-pressed={live}
        data-testid="command-mic-button"
        className={cn("grid h-10 w-10 shrink-0 place-items-center rounded-[13px] transition-colors", live ? "bg-[#AF6EFF] text-white" : "bg-white/85 hover:bg-white")}
      >
        {live ? <X className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
      </button>
      <button type="submit" aria-label="Send" data-testid="command-submit" disabled={!text.trim() || thinking || live} className="grid h-10 w-10 shrink-0 place-items-center rounded-[13px] bg-[#AF6EFF] text-white transition-opacity disabled:opacity-40">
        <ArrowUp className="h-4 w-4" />
      </button>
    </form>
  );
}
