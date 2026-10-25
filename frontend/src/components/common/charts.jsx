import { motion } from "framer-motion";

export function BarSpark({ values, highlight, color = "#FFC46D", testid }) {
  const max = Math.max(...values, 1);
  return (
    <div className="flex h-9 items-end gap-[3px]" data-testid={testid} aria-hidden="true">
      {values.map((v, i) => (
        <motion.span
          key={i}
          initial={false}
          animate={{ height: `${Math.max(8, (v / max) * 100)}%` }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          className="w-[6px] rounded-full"
          style={{ background: i === highlight ? color : "rgba(24,26,26,0.12)" }}
        />
      ))}
    </div>
  );
}

export function AreaLine({ values, width = 150, height = 52 }) {
  const max = Math.max(...values, 1);
  const pts = values.map((v, i) => [(i / Math.max(values.length - 1, 1)) * (width - 8) + 4, height - 6 - (v / max) * (height - 14)]);
  const d = pts.reduce((acc, [x, y], i) => {
    if (!i) return `M${x},${y}`;
    const [px, py] = pts[i - 1];
    const cx = (px + x) / 2;
    return `${acc} C${cx},${py} ${cx},${y} ${x},${y}`;
  }, "");
  const area = `${d} L${pts[pts.length - 1][0]},${height} L${pts[0][0]},${height} Z`;
  const marks = pts.slice(-2);
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true" className="overflow-visible">
      <defs>
        <linearGradient id="fos-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#AF6EFF" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#AF6EFF" stopOpacity="0" />
        </linearGradient>
      </defs>
      <motion.path initial={false} animate={{ d: area }} transition={{ duration: 0.7 }} fill="url(#fos-area)" />
      <motion.path initial={false} animate={{ d }} transition={{ duration: 0.7 }} fill="none" stroke="#AF6EFF" strokeWidth="2.2" strokeLinecap="round" />
      {marks.map(([x, y], i) => (
        <g key={i}>
          <line x1={x} x2={x} y1={y} y2={height} stroke="#AF6EFF" strokeDasharray="3 3" strokeWidth="1.2" />
          <circle cx={x} cy={y} r="3.6" fill="#fff" stroke="#AF6EFF" strokeWidth="2" />
        </g>
      ))}
    </svg>
  );
}

export function TripProgress({ pct, left, mid, right, testid }) {
  return (
    <div data-testid={testid}>
      <div className="flex justify-between text-[12.5px] text-[#181A1A] tnum">
        <span>{left}</span>
        <span>{mid}</span>
        <span>{right}</span>
      </div>
      <div className="relative mt-2 h-[6px] rounded-full bg-[#181A1A]/[0.08]">
        <motion.div initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }} className="absolute inset-y-0 left-0 rounded-full bg-[#AF6EFF]" />
        <motion.svg initial={{ left: 0 }} animate={{ left: `calc(${pct}% - 6px)` }} transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }} className="absolute -top-[5px]" width="14" height="16" viewBox="0 0 14 16">
          <path d="M1 1 L13 8 L1 15 Z" fill="#181A1A" />
        </motion.svg>
      </div>
    </div>
  );
}

export function StopLine({ stops }) {
  return (
    <ol className="relative space-y-2.5 pl-5">
      <span className="absolute left-[4.5px] top-[9px] bottom-[9px] w-px bg-[#181A1A]/25" />
      {stops.map((s, i) => (
        <li key={i} className="relative text-[13px] leading-5">
          <span className={`absolute -left-5 top-[5px] h-[10px] w-[10px] rounded-full ${i === stops.length - 1 ? "bg-[#6B6F76]" : "border-[1.5px] border-[#6B6F76] bg-white"}`} />
          <span className="font-medium">{s.place}</span>
          {s.window && <span className="ml-1.5 text-[#6B6F76] tnum">{s.window}</span>}
        </li>
      ))}
    </ol>
  );
}
