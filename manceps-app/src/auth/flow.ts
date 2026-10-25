// Sign-in state machine: phone -> code -> (new user) firm name -> provisioning wait -> signed in.
import { ApiError, friendlyMessage } from "../api/errors";
import type { AuthApi } from "../api/endpoints";
import type { ProvisioningStatus, TokenResponse } from "../api/types";
import { normalizeUsPhone } from "./phone";

/** How often the wait screen asks whether the firm is ready. */
export const POLL_MS = 3000;
/** After this many polls the wait screen says it is taking longer than usual. */
export const POLL_SLOW_AFTER = 20;
const CODE_RE = /^[0-9]{4,10}$/;
const FIRM_NAME_MAX = 200;

export type SignInStep =
  | { k: "phone" }
  | { k: "code"; phone: string }
  | { k: "firm"; phone: string; ticket: string }
  | { k: "provisioning"; status: ProvisioningStatus; message: string | null; slow: boolean }
  | { k: "done" };

export interface SignInState {
  step: SignInStep;
  busy: boolean;
  error: string | null;
}

export interface FlowDeps {
  api: Pick<AuthApi, "otpStart" | "otpVerify" | "provisioning" | "switchFirm">;
  /** Install tokens in the API client (needed before the provisioning poll, which is authenticated). */
  onTokens: (t: TokenResponse) => void;
  sleep?: (ms: number) => Promise<void>;
}

type Listener = (s: SignInState) => void;

/** Drives the sign-in screens; UI renders `state` and calls the submit methods. */
export class SignInFlow {
  state: SignInState = { step: { k: "phone" }, busy: false, error: null };
  private listeners = new Set<Listener>();
  /** Bumped by stop() and every resume, so only the newest poll loop keeps running. */
  private gen = 0;
  private readonly sleep: (ms: number) => Promise<void>;

  /**
   * Create a flow.
   *
   * Args:
   *   deps: Auth routes, a token sink and an optional sleep for the poll loop.
   */
  constructor(private readonly deps: FlowDeps) {
    this.sleep = deps.sleep ?? ((ms) => new Promise((r) => setTimeout(r, ms)));
  }

  /**
   * Subscribe to state changes.
   *
   * Returns:
   *   Unsubscribe function.
   */
  subscribe(l: Listener): () => void {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  }

  private set(patch: Partial<SignInState>): void {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((l) => l(this.state));
  }

  private fail(e: unknown, step: SignInStep = this.state.step): void {
    this.set({ step, busy: false, error: friendlyMessage(e) });
  }

  /**
   * Send a code to a US phone number.
   *
   * Args:
   *   raw: The phone as typed.
   */
  async submitPhone(raw: string): Promise<void> {
    const phone = normalizeUsPhone(raw);
    if (!phone) { this.set({ error: "Enter a 10-digit US phone number." }); return; }
    this.set({ busy: true, error: null });
    try {
      await this.deps.api.otpStart(phone);
      this.set({ step: { k: "code", phone }, busy: false });
    } catch (e) {
      this.fail(e);
    }
  }

  /** Send the code again to the same phone. */
  async resend(): Promise<void> {
    const st = this.state.step;
    if (st.k !== "code") return;
    this.set({ busy: true, error: null });
    try {
      await this.deps.api.otpStart(st.phone);
      this.set({ busy: false });
    } catch (e) {
      this.fail(e);
    }
  }

  /**
   * Check the code; existing users sign in, new phones move on to the firm name.
   *
   * Args:
   *   code: The digits from the text message.
   */
  async submitCode(code: string): Promise<void> {
    const st = this.state.step;
    if (st.k !== "code") return;
    const c = code.trim();
    if (!CODE_RE.test(c)) { this.set({ error: "Enter the code from the text message." }); return; }
    this.set({ busy: true, error: null });
    try {
      await this.signedIn(await this.deps.api.otpVerify({ phone: st.phone, code: c }));
    } catch (e) {
      const ticket = e instanceof ApiError && e.code === "signup_details_required" ? e.details.signup_ticket : null;
      if (typeof ticket === "string") this.set({ step: { k: "firm", phone: st.phone, ticket }, busy: false, error: null });
      else this.fail(e);
    }
  }

  /**
   * Create the firm for a new phone with the signup ticket the code earned.
   *
   * Args:
   *   firmName: Company name.
   *   acceptTerms: Whether the terms box is checked.
   */
  async submitFirm(firmName: string, acceptTerms: boolean): Promise<void> {
    const st = this.state.step;
    if (st.k !== "firm") return;
    const name = firmName.trim();
    if (!name || name.length > FIRM_NAME_MAX) { this.set({ error: "Enter your company name (up to 200 characters)." }); return; }
    if (!acceptTerms) { this.set({ error: "Accept the terms to continue." }); return; }
    this.set({ busy: true, error: null });
    try {
      await this.signedIn(await this.deps.api.otpVerify({ phone: st.phone, signup_ticket: st.ticket, firm_name: name, accept_terms: true }));
    } catch (e) {
      const expired = e instanceof ApiError && e.code === "invalid_ticket";
      this.fail(e, expired ? { k: "phone" } : st);
    }
  }

  /** Go back one step (code -> phone, firm -> phone, since the ticket is single use). */
  back(): void {
    if (this.state.step.k === "code" || this.state.step.k === "firm") this.set({ step: { k: "phone" }, error: null, busy: false });
  }

  /** Stop the provisioning poll (the screen unmounted). */
  stop(): void {
    this.gen++;
  }

  /**
   * Resume at the wait screen, e.g. after a page reload while the firm is still being set up.
   */
  resumeProvisioning(): Promise<void> {
    this.set({ step: { k: "provisioning", status: "pending", message: null, slow: false }, busy: false, error: null });
    return this.poll(++this.gen);
  }

  private async signedIn(t: TokenResponse): Promise<void> {
    if (t.state === "no_firm") { this.set({ step: { k: "phone" }, busy: false, error: friendlyMessage(new ApiError(403, "no_firm", "no firm")) }); return; }
    this.deps.onTokens(t);
    if (t.state === "active") { this.set({ step: { k: "done" }, busy: false }); return; }
    await this.resumeProvisioning();
  }

  private async poll(gen: number): Promise<void> {
    for (let n = 1; gen === this.gen; n++) {
      try {
        const p = await this.deps.api.provisioning();
        if (gen !== this.gen) return;
        if (p.status === "ready") { await this.finish(); return; }
        const failed = p.status === "failed";
        this.set({ step: { k: "provisioning", status: p.status, message: p.message, slow: n >= POLL_SLOW_AFTER }, error: null });
        if (failed) return;
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) { this.fail(e, { k: "phone" }); return; }
        this.set({ error: friendlyMessage(e) });
      }
      await this.sleep(POLL_MS);
    }
  }

  private async finish(): Promise<void> {
    const t = await this.deps.api.switchFirm();
    this.deps.onTokens(t);
    this.set({ step: { k: "done" }, busy: false, error: null });
  }
}
