import { N_BOX, TASKS, type CardKey, type Question } from "../pages/start/content";

export type Stage = "signup" | "q" | "building" | "home";

export interface Answers {
  who: string | null;
  haul: string[];
  lanes: string[];
}

export interface OnboardState {
  stage: Stage;
  email: string;
  pw: string;
  qi: number;
  ans: Answers;
  agent: string | null;
  hover: string | null;
  biz: string;
  base: string;
  bi: number;
  done: Record<string, boolean>;
  open: string | null;
  imp: Record<string, { name: string; p: number }>;
}

export const MIN_PASSWORD = 8;
const BOX_COLORS = ["#2272AD", "#3A86C2", "#1B5E94"];
const BOX_STAGGER_MS = 40;

/** Starting state: on the sign-up form, account task done, import task open. */
export function initialOnboard(): OnboardState {
  return { stage: "signup", email: "", pw: "", qi: 0, ans: { who: null, haul: [], lanes: [] }, agent: null, hover: null, biz: "", base: "", bi: 0, done: { acct: true }, open: "import", imp: {} };
}

/**
 * Whether the sign-up form can be submitted.
 *
 * Args:
 *   email: Email text.
 *   pw: Password text.
 *
 * Returns:
 *   True for an email-shaped address and a long enough password.
 */
export function signupValid(email: string, pw: string): boolean {
  return /.+@.+\..+/.test(email) && pw.length >= MIN_PASSWORD;
}

/**
 * Whether the current question has an answer.
 *
 * Args:
 *   q: The question.
 *   s: Current state.
 *
 * Returns:
 *   True when Next may advance.
 */
export function isAnswered(q: Question, s: Pick<OnboardState, "ans" | "agent" | "biz">): boolean {
  if (q.type === "cards") return q.multi ? (s.ans[q.key] as string[]).length > 0 : Boolean(s.ans[q.key]);
  if (q.type === "agents") return Boolean(s.agent);
  return Boolean(s.biz.trim());
}

/**
 * Toggle a card answer: replace for single choice, add or remove for multi choice.
 *
 * Args:
 *   ans: Current answers.
 *   key: Question key.
 *   multi: Whether several cards may be picked.
 *   label: Card picked.
 *
 * Returns:
 *   New answers.
 */
export function pickCard(ans: Answers, key: CardKey, multi: boolean, label: string): Answers {
  if (!multi) return { ...ans, [key]: label };
  const cur = ans[key] as string[];
  return { ...ans, [key]: cur.includes(label) ? cur.filter((x) => x !== label) : [...cur, label] };
}

/** Whether a card is currently picked. */
export function isPicked(ans: Answers, key: CardKey, label: string): boolean {
  const v = ans[key];
  return Array.isArray(v) ? v.includes(label) : v === label;
}

export interface Box {
  bg: string;
  op: number;
  anim: string;
}

/**
 * Cargo boxes for the truck progress graphic; newly filled boxes drop in one after another.
 *
 * Args:
 *   pct: Fraction filled, 0 to 1.
 *   prev: Boxes filled on the previous render.
 *
 * Returns:
 *   The boxes and the new filled count.
 */
export function truckBoxes(pct: number, prev: number | null): { boxes: Box[]; filled: number } {
  const filled = Math.round(pct * N_BOX), from = prev ?? filled;
  const boxes = Array.from({ length: N_BOX }, (_, i) => ({
    bg: BOX_COLORS[i % BOX_COLORS.length] as string,
    op: i < filled ? 1 : 0,
    anim: i < filled && i >= from ? `boxIn .3s cubic-bezier(0,0,.2,1) ${(i - from) * BOX_STAGGER_MS}ms both` : "none",
  }));
  return { boxes, filled };
}

/**
 * Mark a task done and open the next unfinished one.
 *
 * Args:
 *   done: Done flags by task id.
 *   id: Task completed.
 *
 * Returns:
 *   New done flags and the task to open (null when all are done).
 */
export function completeTask(done: Record<string, boolean>, id: string): { done: Record<string, boolean>; open: string | null } {
  const d = { ...done, [id]: true };
  const nx = TASKS.find((t) => !d[t.id]);
  return { done: d, open: nx ? nx.id : null };
}

/**
 * One-line summary of the operation answers.
 *
 * Args:
 *   ans: Answers.
 *
 * Returns:
 *   Answers joined with dots, or a prompt when there are none.
 */
export function setupSummary(ans: Answers): string {
  return [ans.who, ans.haul.join(", "), ans.lanes.join(", ")].filter(Boolean).join(" · ") || "Tell us more in Settings";
}

/** Next upload progress step: 15–35% per tick, capped at 100. */
export function nextUploadProgress(p: number, rand: number): number {
  return Math.min(100, p + 15 + rand * 20);
}
