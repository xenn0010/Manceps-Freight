import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Mic, Sparkles, AlertTriangle, CheckCircle2, ArrowRight } from "lucide-react";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "../ui/dialog";
import { useStore } from "../../store/useStore";
import { INTAKE_FIELDS, validate } from "../../lib/fleetFields";
import { EXAMPLES, INTAKE_STEPS } from "../../lib/intakeParser";
import { fleetService, intakeService } from "../../services";
import { FieldInput } from "./FieldInput";
import { cn } from "../../lib/utils";

function Stepper({ kind, onPick }) {
  return (
    <div className="flex items-center gap-1.5" data-testid="intake-stepper">
      {INTAKE_STEPS.map(([id, label], i) => (
        <div key={id} className="flex items-center gap-1.5">
          {i > 0 && <ArrowRight className="h-3 w-3 text-[#9A9DA4]" />}
          <button type="button" data-testid={`intake-step-${id}`} aria-current={kind === id ? "step" : undefined} onClick={() => onPick(id)} className={cn("rounded-[10px] px-2.5 py-1 text-[12px] font-medium", kind === id ? "bg-[#181A1A] text-white" : "bg-white/80 text-[#4B4F55] hover:bg-white")}>{label}</button>
        </div>
      ))}
    </div>
  );
}

function Waveform() {
  return (
    <div className="flex h-9 items-center gap-[3px] px-2" data-testid="intake-waveform" aria-label="Listening">
      {Array.from({ length: 18 }).map((_, i) => <span key={i} className="wave-bar w-[3px] rounded-full bg-[#AF6EFF]" style={{ height: 28, animationDelay: `${(i % 6) * 0.11}s` }} />)}
    </div>
  );
}

function useVoice(onDone) {
  const [status, setStatus] = useState("idle");
  const timers = useRef([]);
  const clear = () => {
    timers.current.forEach((t) => clearTimeout(t) || clearInterval(t));
    timers.current = [];
  };
  useEffect(() => clear, []);
  const start = (preset, onText) => {
    clear();
    setStatus("listening");
    onText("");
    timers.current.push(setTimeout(() => {
      setStatus("transcribing");
      let i = 0;
      const iv = setInterval(() => {
        i = Math.min(preset.length, i + 3);
        onText(preset.slice(0, i));
        if (i >= preset.length) {
          clearInterval(iv);
          setStatus("idle");
          onDone(preset);
        }
      }, 22);
      timers.current.push(iv);
    }, 1500));
  };
  return { status, start, stop: () => { clear(); setStatus("idle"); } };
}

const SAVED_LABEL = { carrier: (f) => f.name, truck: (f) => `Truck ${f.unit}`, driver: (f) => f.name, trip: (f) => f.id };

export function IntakeDialog() {
  const intake = useStore((s) => s.transient.intake);
  const data = useStore((s) => s.data);
  const [kind, setKind] = useState("truck");
  const [text, setText] = useState("");
  const [form, setForm] = useState(null);
  const [saved, setSaved] = useState(null);
  const extract = (t) => {
    if (!t.trim()) return;
    setForm(intakeService.parse(kind, t));
    setSaved(null);
  };
  const voice = useVoice(extract);
  const pick = (k) => {
    voice.stop();
    setKind(k);
    setText("");
    setForm(null);
    setSaved(null);
  };
  useEffect(() => {
    if (intake.open) pick(intake.kind);
  }, [intake.open, intake.kind]); // eslint-disable-line react-hooks/exhaustive-deps

  const fields = INTAKE_FIELDS[kind];
  const errors = useMemo(() => (form ? validate(fields, form, { data }) : {}), [form, fields, data]);
  const needs = fields.filter((f) => errors[f.key] === "Required");
  const dupTruck = kind === "truck" && form?.unit && Object.values(data.trucks).find((t) => t.unit === form.unit);
  const ok = form && Object.keys(errors).length === 0;
  const confirm = () => {
    fleetService.create(kind, form);
    setSaved(SAVED_LABEL[kind](form));
    setForm(null);
    setText("");
    toast.success("Saved", { description: `${SAVED_LABEL[kind](form)} added` });
  };
  const nextKind = INTAKE_STEPS[(INTAKE_STEPS.findIndex(([k]) => k === kind) + 1) % INTAKE_STEPS.length][0];

  return (
    <Dialog open={intake.open} onOpenChange={(o) => !o && (voice.stop(), fleetService.closeIntake())}>
      <DialogContent className="max-h-[92vh] w-[720px] max-w-[720px] grid-cols-1 overflow-y-auto overflow-x-hidden rounded-[24px] border-0 bg-[#F4F5F7] p-6 scroll-thin [&>*]:min-w-0" data-testid="intake-dialog">
        <div className="flex items-start justify-between gap-4 pr-6">
          <div>
            <div className="eyebrow">Guided intake · parsed on device</div>
            <DialogTitle className="mt-1 text-[20px] font-semibold tracking-tight">Add to your fleet</DialogTitle>
            <DialogDescription className="text-[12.5px] text-[#6B6F76]">Describe it in one sentence. Review the card, then save. Steps are optional.</DialogDescription>
          </div>
        </div>
        <div className="mt-3 flex items-center justify-between">
          <Stepper kind={kind} onPick={pick} />
          <button type="button" data-testid="intake-skip-button" onClick={() => pick(nextKind)} className="text-[12px] font-medium text-[#6B6F76] hover:text-[#181A1A]">Skip step →</button>
        </div>

        <div className="mt-3 rounded-[18px] bg-white/85 p-3 ring-1 ring-[#181A1A]/[0.05]">
          {voice.status === "listening" ? (
            <div className="flex items-center gap-3"><Waveform /><span className="text-[12.5px] text-[#6B6F76]">Listening… (simulated)</span></div>
          ) : (
            <textarea
              data-testid="intake-input"
              rows={2}
              value={text}
              placeholder={EXAMPLES[kind][0]}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), extract(text))}
              className="w-full resize-none bg-transparent text-[14px] outline-none placeholder:text-[#9A9DA4]"
            />
          )}
          <div className="mt-2 flex items-center gap-2">
            <button type="button" data-testid="intake-mic-button" aria-label="Dictate (simulated)" onClick={() => voice.start(EXAMPLES[kind][0], setText)} className={cn("grid h-9 w-9 place-items-center rounded-[12px]", voice.status !== "idle" ? "bg-[#AF6EFF] text-white" : "bg-[#181A1A]/[0.06] hover:bg-[#181A1A]/10")}>
              <Mic className="h-4 w-4" />
            </button>
            {voice.status === "transcribing" && <span className="text-[12px] text-[#7A35DB]" data-testid="intake-transcribing">Transcribing…</span>}
            <button type="button" data-testid="intake-extract-button" disabled={!text.trim() || voice.status !== "idle"} onClick={() => extract(text)} className="ml-auto flex items-center gap-1.5 rounded-[12px] bg-[#181A1A] px-3.5 py-2 text-[12.5px] font-semibold text-white disabled:opacity-35">
              <Sparkles className="h-3.5 w-3.5" /> Extract details
            </button>
          </div>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {EXAMPLES[kind].map((ex, i) => (
            <button key={ex} type="button" data-testid={`intake-example-${i}`} onClick={() => (setText(ex), extract(ex))} className="max-w-full truncate rounded-[10px] bg-white/70 px-2.5 py-1 text-left text-[11.5px] text-[#4B4F55] hover:bg-white">“{ex}”</button>
          ))}
        </div>

        {saved && (
          <div className="mt-4 flex items-center gap-2 rounded-[16px] bg-[#A1E688]/35 px-4 py-3 text-[13px]" data-testid="intake-saved">
            <CheckCircle2 className="h-4 w-4 text-[#2C6A18]" /> <b>{saved}</b> saved. It now shows on the dashboard.
            <button type="button" data-testid="intake-next-step" onClick={() => pick(nextKind)} className="ml-auto rounded-[10px] bg-white/80 px-2.5 py-1 text-[12px] font-medium">Next: {INTAKE_STEPS.find(([k]) => k === nextKind)[1]}</button>
            <button type="button" data-testid="intake-done" onClick={() => fleetService.closeIntake()} className="rounded-[10px] bg-[#181A1A] px-2.5 py-1 text-[12px] font-medium text-white">Done</button>
          </div>
        )}

        {form && (
          <div className="mt-4 rounded-[20px] bg-white p-4 shadow-[0_12px_32px_-20px_rgba(24,26,26,0.35)]" data-testid="intake-confirmation-card">
            <div className="flex items-center gap-2">
              <span className="text-[14px] font-semibold">Confirm details</span>
              {needs.length > 0 ? (
                <span className="rounded-md bg-[#FFC46D]/40 px-2 py-0.5 text-[11px] font-semibold text-[#8A5200]" data-testid="intake-needs-info">Needs info: {needs.map((f) => f.label).join(", ")}</span>
              ) : (
                <span className="rounded-md bg-[#A1E688]/45 px-2 py-0.5 text-[11px] font-semibold text-[#2C6A18]">All required details found</span>
              )}
            </div>
            {dupTruck && (
              <div className="mt-3 flex items-center gap-2 rounded-[14px] bg-[#FFC46D]/30 px-3.5 py-2.5 text-[12.5px]" data-testid="intake-duplicate-warning">
                <AlertTriangle className="h-4 w-4 text-[#8A5200]" /> <b>Truck {form.unit} already exists</b>. Nothing will be duplicated.
                <button type="button" data-testid="intake-edit-existing" onClick={() => (fleetService.closeIntake(), fleetService.openDrawer("truck", dupTruck.id))} className="ml-auto rounded-[10px] bg-white px-2.5 py-1 text-[12px] font-semibold">Edit Truck {form.unit} instead</button>
              </div>
            )}
            <div className="mt-3 grid grid-cols-2 gap-3">
              {fields.map((f) => (
                <FieldInput key={f.key} field={f} value={form[f.key]} error={dupTruck && f.key === "unit" ? null : errors[f.key]} data={data} testid={`intake-field-${f.key}`} onChange={(v) => setForm((s) => ({ ...s, [f.key]: v }))} />
              ))}
            </div>
            <div className="mt-4 flex items-center gap-2">
              <span className="text-[11.5px] text-[#6B6F76]">Creates linked records with stable IDs.</span>
              <button type="button" data-testid="intake-confirm-button" disabled={!ok} onClick={confirm} className="ml-auto rounded-[14px] bg-[#AF6EFF] px-5 py-2.5 text-[13px] font-semibold text-white hover:bg-[#9F5BF5] disabled:cursor-not-allowed disabled:opacity-35">Confirm &amp; save</button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
