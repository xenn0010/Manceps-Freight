import { cn } from "../../lib/utils";
import { DAY_OPTIONS } from "../../lib/windows";

const base = "h-9 w-full rounded-[10px] border border-[#181A1A]/10 bg-white px-2.5 text-[13px] outline-none transition-[border-color,box-shadow] focus:border-[#AF6EFF] focus:ring-2 focus:ring-[#AF6EFF]/20";

function WindowInput({ value, onChange, testid, bad }) {
  if (value.text !== undefined) return <input data-testid={testid} className={cn(base, bad)} value={value.text} onChange={(e) => onChange({ text: e.target.value })} />;
  const set = (k) => (e) => onChange({ ...value, [k]: e.target.value });
  return (
    <div className="flex gap-1.5">
      <select data-testid={`${testid}-day`} className={cn(base, "w-[84px]", bad)} value={value.day} onChange={set("day")}>
        <option value="">Day</option>
        {DAY_OPTIONS.map((d) => <option key={d} value={d}>{d}</option>)}
      </select>
      <input type="time" data-testid={`${testid}-start`} aria-label="Start" className={cn(base, bad)} value={value.start} onChange={set("start")} />
      <span className="self-center text-[#9A9DA4]">–</span>
      <input type="time" data-testid={`${testid}-end`} aria-label="End" className={cn(base, bad)} value={value.end} onChange={set("end")} />
    </div>
  );
}

function Control({ field, value, onChange, testid, data, rec, bad }) {
  if (field.kind === "window") return <WindowInput value={value} onChange={onChange} testid={testid} bad={bad} />;
  if (field.kind === "check")
    return (
      <label className="flex h-9 items-center gap-2 text-[13px]">
        <input type="checkbox" data-testid={testid} checked={!!value} onChange={(e) => onChange(e.target.checked)} className="h-4 w-4 accent-[#AF6EFF]" /> Yes
      </label>
    );
  if (field.kind === "select") {
    const opts = field.options(data, rec);
    return (
      <select data-testid={testid} className={cn(base, bad)} value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
        {!opts.some(([v]) => v === "") && <option value="">{field.placeholder || "Select…"}</option>}
        {opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    );
  }
  if (field.kind === "textarea") return <textarea data-testid={testid} rows={2} className={cn(base, "h-auto py-2", bad)} value={value} onChange={(e) => onChange(e.target.value)} />;
  return <input data-testid={testid} type={field.kind === "number" ? "number" : "text"} step="any" placeholder={field.placeholder} className={cn(base, bad)} value={value} onChange={(e) => onChange(e.target.value)} />;
}

export function FieldInput({ field, value, onChange, error, testid, data, rec, wide }) {
  const needs = error === "Required";
  const bad = error ? (needs ? "border-[#FFC46D] ring-2 ring-[#FFC46D]/30" : "border-[#E5484D] ring-2 ring-[#E5484D]/15") : "";
  return (
    <div className={cn("min-w-0", (wide || field.kind === "window" || field.kind === "textarea") && "col-span-2")}>
      <div className="mb-1 flex items-center gap-1.5 text-[11.5px] font-medium text-[#6B6F76]">
        {field.label}
        {field.required && <span className="text-[#AF6EFF]">*</span>}
        {needs && <span className="ml-auto rounded-md bg-[#FFC46D]/40 px-1.5 text-[10.5px] font-semibold text-[#8A5200]" data-testid={`${testid}-needs-info`}>Needs info</span>}
      </div>
      <Control field={field} value={value} onChange={onChange} testid={testid} data={data} rec={rec} bad={bad} />
      {error && !needs && <p className="mt-1 text-[11.5px] font-medium text-[#C2262B]" data-testid={`${testid}-error`}>{error}</p>}
      {field.hint && !error && <p className="mt-1 text-[11px] text-[#9A9DA4]">{field.hint}</p>}
    </div>
  );
}
