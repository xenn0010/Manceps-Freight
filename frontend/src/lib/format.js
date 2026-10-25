const DAYS = ["Mon 26 Oct", "Tue 27 Oct", "Wed 28 Oct", "Thu 29 Oct"];
const pad = (n) => String(n).padStart(2, "0");

export const money = (n) => `${n < 0 ? "-" : ""}$${Math.abs(Math.round(n)).toLocaleString("en-US")}`;
export const signedMoney = (n) => (n > 0 ? `+${money(n)}` : money(n));
export const num = (n) => Math.round(n).toLocaleString("en-US");
export const pct = (x) => `${x.toFixed(1)}%`;
export const hhmm = (min) => `${pad(Math.floor((min % 1440) / 60))}:${pad(min % 60)}`;
export const clockLabel = (min) => `${DAYS[Math.floor(min / 1440)]} 2026 · ${hhmm(min)} PT`;
export const stamp = (min) => (min < 1440 ? hhmm(min) : `${DAYS[Math.floor(min / 1440)].slice(0, 3)} ${hhmm(min)}`);
