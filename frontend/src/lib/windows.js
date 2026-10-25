export const DAY_OFFSET = { Sun: -1, Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5 };
export const DAY_OPTIONS = ["Mon", "Tue", "Wed", "Thu", "Fri"];
const DAY_RE = "(Sun|Mon|Tue|Wed|Thu|Fri|Sat)";
const pad = (t) => t.replace(/^(\d):/, "0$1:");
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1, 3).toLowerCase();

export const toMin = (day, hhmm) => {
  const [h, m] = hhmm.split(":").map(Number);
  return DAY_OFFSET[day] * 1440 + h * 60 + m;
};

export function parseWindow(str) {
  const m = new RegExp(`^${DAY_RE}\\s+(\\d{1,2}:\\d{2})\\s*[–-]\\s*(\\d{1,2}:\\d{2})$`, "i").exec((str || "").trim());
  if (!m) return null;
  const day = cap(m[1]);
  const start = pad(m[2]);
  const end = pad(m[3]);
  return { day, start, end, startMin: toMin(day, start), endMin: toMin(day, end) };
}

export function parsePoint(str) {
  const m = new RegExp(`^${DAY_RE}\\s+(\\d{1,2}:\\d{2})`, "i").exec((str || "").trim());
  return m ? toMin(cap(m[1]), pad(m[2])) : null;
}

export const formatWindow = (w) => `${w.day} ${w.start}–${w.end}`;
export const windowForm = (str) => {
  const w = parseWindow(str);
  return w ? { day: w.day, start: w.start, end: w.end } : { text: str || "" };
};

export function windowError(w, required) {
  if (w.text !== undefined) return required && !w.text.trim() ? "Required" : null;
  if (!w.day && !w.start && !w.end) return required ? "Required" : null;
  if (!w.day || !w.start || !w.end) return "Required";
  return toMin(w.day, w.end) <= toMin(w.day, w.start) ? "Window ends before it starts" : null;
}

export function normalizePoint(str) {
  const m = new RegExp(`${DAY_RE}\\s+(\\d{1,2}:\\d{2})`, "i").exec(str || "");
  return m ? `${cap(m[1])} ${pad(m[2])}` : "";
}
