import { useEffect, useState } from "react";
import { Phone } from "lucide-react";
import { useStore } from "../../store/useStore";
import { liveCallService, contactsService } from "../../services";
import { cn } from "../../lib/utils";

const E164 = /^\+[1-9]\d{7,14}$/;

function NumberRow({ c, live, demo }) {
  const [v, setV] = useState(c.phone);
  useEffect(() => setV(c.phone), [c.phone]);
  const bad = v && !E164.test(v);
  const missing = live && !v && c.role === "broker";
  return (
    <li className="py-2.5" data-testid={`calling-contact-${c.id}`}>
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <div className="truncate text-[12.5px] font-medium">{c.name}</div>
          <div className="truncate text-[11px] text-[#6B6F76]">{c.role === "broker" ? c.company : "Driver"}</div>
        </div>
        <input data-testid={`calling-number-${c.id}`} value={v} placeholder={c.role === "driver" ? `Default ${demo || "demo number"}` : "Add phone (E.164)"} onChange={(e) => setV(e.target.value.trim())} onBlur={() => !bad && liveCallService.setNumber(c.id, v)}
          className={cn("h-8 w-[150px] rounded-[10px] border bg-white px-2 text-[12px] outline-none tnum", bad ? "border-[#E5484D]" : missing ? "border-[#FFC46D]" : "border-[#181A1A]/10")} />
        <button type="button" aria-label={`Call ${c.name}`} data-testid={`calling-call-${c.id}`} onClick={() => liveCallService.request(c.id, "manual", null, `Check in with ${c.name}`)} className="grid h-8 w-8 place-items-center rounded-[10px] bg-[#181A1A]/[0.06] hover:bg-[#181A1A]/10"><Phone className="h-3.5 w-3.5" /></button>
      </div>
      {bad && <p className="mt-1 text-[11px] text-[#C2262B]">Use E.164, e.g. +16095550100</p>}
      {missing && <p className="mt-1 text-[11px] font-medium text-[#8A5200]" data-testid={`calling-missing-${c.id}`}>Add a number to call this broker live</p>}
    </li>
  );
}

export function CallingSettings() {
  const data = useStore((s) => s.data);
  const [cfg, setCfg] = useState(null);
  useEffect(() => {
    liveCallService.config().then(setCfg);
  }, []);
  const live = data.calling.mode === "live";
  return (
    <>
      <div className="eyebrow mt-5">Calling</div>
      <div className="mt-2 rounded-[18px] bg-white/85 px-4 py-3 ring-1 ring-[#181A1A]/[0.05]" data-testid="calling-settings">
        <div className="flex items-center gap-2">
          <div className="flex-1">
            <div className="text-[13px] font-medium">Phone calls</div>
            <div className="text-[11.5px] text-[#6B6F76]">{live ? (cfg?.configured === false ? "Server isn't configured for live calls" : "Real calls via Vapi. Each call needs your confirm.") : "Scripted calls, nothing dials"}</div>
          </div>
          <div className="flex rounded-[12px] bg-[#181A1A]/[0.05] p-0.5" role="radiogroup" aria-label="Calling mode">
            {[["simulated", "Simulated"], ["live", "Live"]].map(([m, l]) => (
              <button key={m} type="button" role="radio" aria-checked={data.calling.mode === m} data-testid={`calling-mode-${m}`} onClick={() => liveCallService.setMode(m)}
                className={cn("rounded-[10px] px-3 py-1 text-[12px] font-semibold", data.calling.mode === m ? (m === "live" ? "bg-[#E5484D] text-white" : "bg-white shadow-sm") : "text-[#6B6F76]")}>{l}</button>
            ))}
          </div>
        </div>
        <ul className="mt-1 divide-y divide-[#181A1A]/[0.06]">
          {contactsService.list(data).map((c) => <NumberRow key={c.id} c={c} live={live} demo={cfg?.demoDriverPhone} />)}
        </ul>
      </div>
    </>
  );
}
