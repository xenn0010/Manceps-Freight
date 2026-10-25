import { Fragment, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Info } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "../ui/sheet";
import { useStore } from "../../store/useStore";
import { FIELDS, toForm, toPatch, validate } from "../../lib/fleetFields";
import { recordOf } from "../../services/engine3";
import { fleetService } from "../../services";
import { FieldInput } from "./FieldInput";

const TITLE = { carrier: (r) => r.name, truck: (r) => `Truck ${r.unit}`, driver: (r) => r.name, trip: (r) => `${r.id} · ${r.origin} → ${r.destination}` };
const EYEBROW = { carrier: "Carrier", truck: "Truck", driver: "Driver", trip: "Commitment" };

export function RecordDrawer() {
  const drawer = useStore((s) => s.transient.drawer);
  const data = useStore((s) => s.data);
  const rec = drawer ? recordOf(data, drawer.type, drawer.id) : null;
  const [form, setForm] = useState(null);
  useEffect(() => {
    setForm(rec ? toForm(drawer.type, rec) : null);
  }, [drawer?.type, drawer?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const fields = useMemo(() => (drawer ? FIELDS[drawer.type] : []), [drawer]);
  const errors = useMemo(() => (form && drawer ? validate(fields, form, { data, id: drawer.id }) : {}), [form, fields, data, drawer]);
  const open = !!(drawer && rec && form);
  const dirty = open && JSON.stringify(form) !== JSON.stringify(toForm(drawer.type, rec));
  const invalid = Object.keys(errors).length > 0;
  const save = () => {
    fleetService.save(drawer.type, drawer.id, toPatch(drawer.type, form, rec));
    toast.success("Saved", { description: `${TITLE[drawer.type]({ ...rec, ...toPatch(drawer.type, form, rec) })} updated` });
  };
  const driver = open && drawer.type === "truck" ? data.drivers[rec.driverId] : null;
  return (
    <Sheet open={open} onOpenChange={(o) => !o && fleetService.closeDrawer()}>
      <SheetContent side="right" className="flex w-[460px] flex-col gap-0 border-l-0 bg-[#F4F5F7] p-0 sm:max-w-[460px]" data-testid="record-drawer">
        {open && (
          <>
            <SheetHeader className="px-6 pb-3 pt-6 text-left">
              <div className="eyebrow">{EYEBROW[drawer.type]} · {rec.id}</div>
              <SheetTitle className="text-[20px] font-semibold tracking-tight" data-testid="record-drawer-title">{TITLE[drawer.type](rec)}</SheetTitle>
              <SheetDescription className="text-[12px] text-[#6B6F76]">Edits save to the shared store and update the map, schedule and metrics.</SheetDescription>
            </SheetHeader>
            <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-6 scroll-thin">
              <div className="grid grid-cols-2 gap-x-3 gap-y-3 rounded-[18px] bg-white/80 p-4 ring-1 ring-[#181A1A]/[0.05]">
                {fields.map((f) => (
                  <Fragment key={f.key}>
                    {f.section && <div className="eyebrow col-span-2 mt-2 first:mt-0">{f.section}</div>}
                    <FieldInput field={f} value={form[f.key]} error={errors[f.key]} data={data} rec={rec} testid={`drawer-field-${f.key}`} onChange={(v) => setForm((s) => ({ ...s, [f.key]: v }))} />
                  </Fragment>
                ))}
              </div>
              {driver && (
                <button type="button" data-testid="drawer-open-driver" onClick={() => fleetService.openDrawer("driver", driver.id)} className="mt-3 w-full rounded-[14px] bg-white/70 px-3.5 py-2.5 text-left text-[12.5px] hover:bg-white">
                  Driver availability is set separately on <b>{driver.name}</b>: <span className="tnum">{driver.availableAt}</span> · Edit driver →
                </button>
              )}
              {drawer.type === "driver" && (
                <p className="mt-3 flex items-start gap-2 rounded-[14px] bg-[#AF6EFF]/10 px-3.5 py-2.5 text-[12px] text-[#5B21B6]" data-testid="driver-hours-note">
                  <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" /> Rest/hours info is scenario data, not a compliance assessment.
                </p>
              )}
            </div>
            <div className="flex gap-2 border-t border-[#181A1A]/[0.06] bg-white/70 px-6 py-4">
              <button type="button" data-testid="drawer-cancel-button" onClick={() => fleetService.closeDrawer()} className="flex-1 rounded-[14px] bg-[#181A1A]/[0.05] py-2.5 text-[13px] font-medium hover:bg-[#181A1A]/[0.09]">Close</button>
              <button type="button" data-testid="drawer-save-button" disabled={invalid || !dirty} onClick={save} className="flex-[2] rounded-[14px] bg-[#181A1A] py-2.5 text-[13px] font-semibold text-white transition-opacity hover:bg-[#2a2d2d] disabled:cursor-not-allowed disabled:opacity-35">
                {invalid ? "Fix errors to save" : "Save"}
              </button>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
