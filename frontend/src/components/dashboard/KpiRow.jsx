import { Info, AlertTriangle, ArrowUpRight, Sparkles, CheckCircle2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { useStore } from "../../store/useStore";
import { planLedger, summarize, previewMetrics } from "../../lib/metrics";
import { isAwaitingConfirmation, openAttention } from "../../lib/selectors";
import { money, pct, num } from "../../lib/format";
import { openLink } from "../../lib/links";
import { AnimatedNumber, Pill } from "../common/ui";
import { AreaLine, BarSpark } from "../common/charts";
import { cn } from "../../lib/utils";

function CurrentPlanInfo() {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" data-testid="current-plan-info-button" onClick={(e) => e.stopPropagation()} className="inline-flex items-center gap-1 rounded-lg bg-white/70 px-2 py-[3px] text-[11.5px] font-medium text-[#4B4F55] hover:bg-white">
          Current plan <Info className="h-3 w-3" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[320px] rounded-[18px] border-white/90 bg-white/95 p-4 text-[13px] leading-5 backdrop-blur-xl" data-testid="current-plan-info">
        <div className="mb-1.5 font-semibold">What “Current plan” covers</div>
        <ul className="list-disc space-y-1 pl-4 text-[#3f4247]">
          <li>Active trips</li>
          <li>Confirmed trips picking up in the next 48 h</li>
          <li>Required connecting repositioning (empty miles)</li>
        </ul>
        <p className="mt-2 text-[12.5px] text-[#6B6F76]">Booked revenue is not cash collected. Costs use $1.80/mi all-in, before overhead.</p>
      </PopoverContent>
    </Popover>
  );
}

function PreviewTag({ show, value, testid }) {
  return (
    <AnimatePresence>
      {show && (
        <motion.span initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="inline-flex items-center gap-1 rounded-lg bg-[#AF6EFF]/18 px-1.5 py-[2px] text-[11px] font-medium text-[#7A35DB] tnum" data-testid={testid}>
          Preview <ArrowUpRight className="h-3 w-3" /> {value}
        </motion.span>
      )}
    </AnimatePresence>
  );
}

function KpiCard({ id, label, wash, active, onClick, children, extra }) {
  return (
    <div
      role="button"
      tabIndex={0}
      data-testid={`metric-card-${id}`}
      onClick={onClick}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onClick())}
      className={cn("glass relative flex cursor-pointer flex-col justify-between overflow-hidden px-5 py-3.5 text-left transition-shadow hover:shadow-[0_18px_40px_-18px_rgba(24,26,26,0.28)]", wash, active && "ring-2 ring-[#AF6EFF]/60")}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[14px] font-medium">{label}</span>
        {extra}
      </div>
      {children}
    </div>
  );
}

function AttentionCard() {
  const data = useStore((s) => s.data);
  const items = openAttention(data);
  return (
    <div className="glass flex min-h-0 flex-col gap-1 overflow-hidden p-2" data-testid="attention-strip">
      <div className="flex items-center justify-between px-2">
        <span className="text-[12.5px] font-medium">Needs you</span>
        <span className="rounded-md bg-white/80 px-1.5 text-[11px] font-semibold tnum" data-testid="attention-count">{items.length}</span>
      </div>
      <AnimatePresence initial={false}>
        {items.map((a) => {
          const risk = a.kind === "risk";
          const unit = data.trucks[a.truckId].unit;
          return (
            <motion.button
              layout
              key={a.id}
              type="button"
              data-testid={`attention-item-${unit}`}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, x: 24, transition: { duration: 0.25 } }}
              onClick={() => openLink(a.link)}
              className={cn("flex min-h-0 flex-1 items-center gap-2.5 rounded-[14px] px-3 py-1 text-left transition-colors", risk ? "bg-[#FFC46D]/40 hover:bg-[#FFC46D]/55" : "bg-white/80 hover:bg-white")}
            >
              <span className={cn("grid h-7 w-7 shrink-0 place-items-center rounded-[10px]", risk ? "bg-[#FFC46D] text-[#7A4300]" : "bg-[#AF6EFF] text-white")}>
                {risk ? <AlertTriangle className="h-3.5 w-3.5" /> : <Sparkles className="h-3.5 w-3.5" />}
              </span>
              <span className="min-w-0 leading-tight">
                <span className="block truncate text-[13px] font-semibold">{a.title} · Truck {unit}</span>
                <span className={cn("block truncate text-[11.5px] tnum", risk ? "text-[#C2282D]" : "text-[#6B6F76]")}>{a.summary}</span>
              </span>
            </motion.button>
          );
        })}
      </AnimatePresence>
      {items.length === 0 && (
        <div className="flex flex-1 items-center gap-2 rounded-[14px] bg-[#A1E688]/35 px-3 text-[13px] font-medium" data-testid="attention-all-clear">
          <CheckCircle2 className="h-4 w-4 text-[#2C6A18]" /> All clear
        </div>
      )}
    </div>
  );
}

export function KpiRow() {
  const data = useStore((s) => s.data);
  const panel = useStore((s) => s.ui.panel);
  const togglePanel = useStore((s) => s.togglePanel);
  const items = planLedger(data);
  const m = summarize(items, data.carrier.costPerMile);
  const p = data.proposals["P-1"];
  const preview = isAwaitingConfirmation(p) ? previewMetrics(data, p.offerId) : null;
  const emptyVals = items.map((i) => i.emptyMiles);
  const cumulative = items.reduce((acc, i) => [...acc, (acc[acc.length - 1] || 0) + i.revenue], [0]);
  const isActive = (k) => panel?.type === "metric" && panel.id === k;
  const highEmpty = m.emptyPct > 15;

  return (
    <section className="grid h-[124px] shrink-0 grid-cols-[1fr_1fr_1fr_minmax(300px,0.95fr)] grid-rows-[minmax(0,1fr)] gap-3" data-testid="kpi-row">
      <KpiCard id="revenue" label="Booked revenue" wash="wash-purple" active={isActive("revenue")} onClick={() => togglePanel("metric", "revenue")} extra={<CurrentPlanInfo />}>
        <div className="flex items-end justify-between gap-2">
          <div>
            <AnimatedNumber value={m.revenue} format={money} testid="metric-revenue-value" className="block text-[30px] font-semibold leading-9 tracking-tight" />
            <div className="flex h-5 items-center gap-1.5 text-[12px] text-[#6B6F76]">
              {preview ? <PreviewTag show value={money(preview.revenue)} testid="metric-revenue-preview" /> : <span className="tnum">{items.filter((i) => i.kind === "trip").length} trips in plan</span>}
            </div>
          </div>
          <div className="-mb-1 -mr-1"><AreaLine values={cumulative} width={124} height={48} /></div>
        </div>
      </KpiCard>
      <KpiCard id="costs" label="After trip costs (est.)" wash="wash-green" active={isActive("costs")} onClick={() => togglePanel("metric", "costs")} extra={<PreviewTag show={!!preview} value={preview && money(preview.afterCosts)} testid="metric-costs-preview" />}>
        <div>
          <AnimatedNumber value={m.afterCosts} format={money} testid="metric-costs-value" className="block text-[30px] font-semibold leading-9 tracking-tight" />
          <div className="flex h-5 items-center gap-1.5 whitespace-nowrap text-[12px] text-[#4B4F55]">
            <span className="tnum" data-testid="metric-costs-sub">{money(m.cost)} direct costs · Before overhead</span>
          </div>
        </div>
      </KpiCard>
      <KpiCard id="empty" label="Empty driving" wash={highEmpty ? "wash-amber" : "wash-green"} active={isActive("empty")} onClick={() => togglePanel("metric", "empty")} extra={<PreviewTag show={!!preview} value={preview && pct(preview.emptyPct)} testid="metric-empty-preview" />}>
        <div className="flex items-end justify-between gap-2">
          <div>
            <AnimatedNumber value={m.emptyPct} format={pct} testid="metric-empty-value" className="block text-[30px] font-semibold leading-9 tracking-tight" />
            <div className="flex h-5 items-center gap-1.5 whitespace-nowrap text-[12px] text-[#4B4F55]">
              <span className="tnum" data-testid="metric-empty-sub">{num(m.emptyMiles)} of {num(m.totalMiles)} planned miles</span>
            </div>
          </div>
          <BarSpark values={emptyVals} highlight={emptyVals.indexOf(Math.max(...emptyVals))} color={highEmpty ? "#FFC46D" : "#A1E688"} testid="metric-empty-spark" />
        </div>
      </KpiCard>
      <AttentionCard />
    </section>
  );
}
