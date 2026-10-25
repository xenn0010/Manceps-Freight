import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { PhoneOutgoing, X } from "lucide-react";
import { useStore } from "../../store/useStore";
import { liveCallService, contactsService, callScripts } from "../../services";

const E164 = /^\+[1-9]\d{7,14}$/;

export function CallConfirmCard() {
  const req = useStore((s) => s.transient.callConfirm);
  const data = useStore((s) => s.data);
  const [cfg, setCfg] = useState(null);
  const [num, setNum] = useState("");
  useEffect(() => {
    if (req && !cfg) liveCallService.config().then(setCfg);
  }, [req, cfg]);
  const c = req ? contactsService.get(data, req.contactId) : null;
  const live = data.calling.mode === "live";
  const needsNumber = live && c && !c.phone && c.role !== "driver";
  const notConfigured = live && (!cfg || !cfg.configured);
  const task = c ? callScripts.build(req.taskType, data, c, req.purpose) : null;
  return (
    <AnimatePresence>
      {c && (
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 16 }} className="fixed bottom-24 left-1/2 z-[60] w-[440px] -translate-x-1/2" data-testid="call-confirm-card">
          <div className="rounded-[22px] bg-white p-4 shadow-[0_24px_60px_-24px_rgba(24,26,26,0.45)] ring-1 ring-[#181A1A]/[0.06]">
            <div className="flex items-center gap-2">
              <span className="grid h-9 w-9 place-items-center rounded-xl bg-[#AF6EFF]/15 text-[#7A35DB]"><PhoneOutgoing className="h-4 w-4" /></span>
              <div className="min-w-0 flex-1">
                <div className="text-[14px] font-semibold">Call {c.name}{c.role === "broker" ? ` · ${c.company}` : ""}?</div>
                <div className="text-[11.5px] text-[#6B6F76]" data-testid="call-confirm-number">
                  {c.phone || (c.role === "driver" ? `Demo default ${cfg?.demoDriverPhone || "number"}` : "No number yet")}
                </div>
              </div>
              <span className={`rounded-md px-1.5 py-0.5 text-[10.5px] font-bold ${live ? "bg-[#E5484D] text-white" : "bg-[#181A1A]/[0.06] text-[#4B4F55]"}`} data-testid="call-confirm-mode">{live ? "LIVE CALL" : "Simulated"}</span>
              <button type="button" aria-label="Cancel" data-testid="call-confirm-close" onClick={() => liveCallService.cancelRequest()} className="grid h-7 w-7 place-items-center rounded-lg hover:bg-[#181A1A]/[0.06]"><X className="h-4 w-4" /></button>
            </div>
            <p className="mt-3 rounded-[12px] bg-[#F4F5F7] px-3 py-2 text-[12.5px]" data-testid="call-confirm-purpose">{task.objective}</p>
            {needsNumber && (
              <div className="mt-2 flex gap-2" data-testid="call-confirm-number-prompt">
                <input value={num} onChange={(e) => setNum(e.target.value.trim())} placeholder="+1 555 010 0000 (E.164)" data-testid="call-confirm-number-input" className="h-9 flex-1 rounded-[10px] border border-[#FFC46D] px-2.5 text-[13px] outline-none" />
                <button type="button" disabled={!E164.test(num)} onClick={() => liveCallService.setNumber(c.id, num)} data-testid="call-confirm-number-save" className="rounded-[10px] bg-[#181A1A] px-3 text-[12px] font-semibold text-white disabled:opacity-35">Save number</button>
              </div>
            )}
            {notConfigured && <p className="mt-2 text-[12px] text-[#C2262B]" data-testid="call-confirm-not-configured">Live calling isn't configured on the server. Switch to Simulated in AI settings.</p>}
            <div className="mt-3 flex gap-2">
              <button type="button" data-testid="call-confirm-cancel" onClick={() => liveCallService.cancelRequest()} className="flex-1 rounded-[14px] bg-[#181A1A]/[0.05] py-2.5 text-[13px] font-medium">Not now</button>
              <button type="button" data-testid="call-confirm-dial" disabled={needsNumber || notConfigured} onClick={() => (liveCallService.cancelRequest(), liveCallService.start(req))} className="flex-[2] rounded-[14px] bg-[#AF6EFF] py-2.5 text-[13px] font-semibold text-white hover:bg-[#9F5BF5] disabled:opacity-35">
                {live ? "Place live call" : "Run simulated call"}
              </button>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
