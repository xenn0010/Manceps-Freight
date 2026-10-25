import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/errors";
import type { Provisioning, TokenResponse } from "../api/types";
import { POLL_SLOW_AFTER, SignInFlow, type FlowDeps } from "./flow";

const PHONE = "+12145550199";
const TICKET = "mcs_" + "a".repeat(43);

const tokens = (state: TokenResponse["state"], access = "t-" + state): TokenResponse => ({
  access_token: access, expires_in: 900, refresh_token: null, session_id: "s", user_id: "u", tenant_id: state === "active" ? "acme" : null, role: "owner", state,
});

type Api = FlowDeps["api"];

function setup(api: Partial<Api>): { flow: SignInFlow; onTokens: ReturnType<typeof vi.fn>; api: Api } {
  const full: Api = {
    otpStart: vi.fn(async () => ({ sent: true })),
    otpVerify: vi.fn(async () => tokens("active")),
    provisioning: vi.fn(async (): Promise<Provisioning> => ({ status: "ready", tenant_id: "acme", message: null })),
    switchFirm: vi.fn(async () => tokens("active", "firm-scoped")),
    ...api,
  };
  const onTokens = vi.fn();
  return { flow: new SignInFlow({ api: full, onTokens, sleep: async () => undefined }), onTokens, api: full };
}

describe("SignInFlow", () => {
  it("validates the phone before calling the API", async () => {
    const { flow, api } = setup({});
    await flow.submitPhone("555-0199");
    expect(flow.state).toMatchObject({ step: { k: "phone" }, error: "Enter a 10-digit US phone number." });
    expect(api.otpStart).not.toHaveBeenCalled();
  });

  it("signs an existing user straight in: phone -> code -> done", async () => {
    const { flow, api, onTokens } = setup({});
    await flow.submitPhone("(214) 555-0199");
    expect(api.otpStart).toHaveBeenCalledWith(PHONE);
    expect(flow.state.step).toEqual({ k: "code", phone: PHONE });
    await flow.submitCode(" 123456 ");
    expect(api.otpVerify).toHaveBeenCalledWith({ phone: PHONE, code: "123456" });
    expect(onTokens).toHaveBeenCalledWith(expect.objectContaining({ state: "active" }));
    expect(flow.state).toMatchObject({ step: { k: "done" }, busy: false, error: null });
  });

  it("takes a new phone through firm name and provisioning to a firm-scoped token", async () => {
    let polls = 0;
    const { flow, api, onTokens } = setup({
      otpVerify: vi.fn(async (b) => {
        if (b.code) throw new ApiError(422, "signup_details_required", "need details", { signup_ticket: TICKET, expires_in: 900 });
        return tokens("provisioning");
      }),
      provisioning: vi.fn(async (): Promise<Provisioning> => ({ status: ++polls < 3 ? "provisioning" : "ready", tenant_id: polls < 3 ? null : "acme", message: null })),
    });
    await flow.submitPhone("2145550199");
    await flow.submitCode("123456");
    expect(flow.state.step).toEqual({ k: "firm", phone: PHONE, ticket: TICKET });
    await flow.submitFirm("  ", true);
    expect(flow.state.error).toMatch(/company name/);
    await flow.submitFirm("Acme Dispatch", false);
    expect(flow.state.error).toMatch(/terms/);
    await flow.submitFirm("Acme Dispatch", true);
    expect(api.otpVerify).toHaveBeenLastCalledWith({ phone: PHONE, signup_ticket: TICKET, firm_name: "Acme Dispatch", accept_terms: true });
    expect(api.provisioning).toHaveBeenCalledTimes(3);
    expect(api.switchFirm).toHaveBeenCalledTimes(1);
    expect(onTokens.mock.calls.map(([t]) => (t as TokenResponse).access_token)).toEqual(["t-provisioning", "firm-scoped"]);
    expect(flow.state.step).toEqual({ k: "done" });
  });

  it("shows clear messages for a wrong code and a rate limit, staying on the code step", async () => {
    const verify = vi.fn().mockRejectedValueOnce(new ApiError(400, "invalid_code", "bad")).mockRejectedValueOnce(new ApiError(429, "rate_limited", "slow", {}, 45));
    const { flow } = setup({ otpVerify: verify });
    await flow.submitPhone(PHONE);
    await flow.submitCode("000000");
    expect(flow.state).toMatchObject({ step: { k: "code" }, error: "That code didn't work. Check it and try again.", busy: false });
    await flow.submitCode("000000");
    expect(flow.state.error).toBe("Too many tries. Try again in 45 seconds.");
  });

  it("explains a server without sign-in configured", async () => {
    const { flow } = setup({ otpStart: vi.fn().mockRejectedValue(new ApiError(503, "twilio_not_configured", "off")) });
    await flow.submitPhone(PHONE);
    expect(flow.state).toMatchObject({ step: { k: "phone" }, error: "Phone sign-in isn't set up on this server yet." });
  });

  it("sends an expired signup ticket back to the phone step", async () => {
    const verify = vi.fn().mockRejectedValueOnce(new ApiError(422, "signup_details_required", "x", { signup_ticket: TICKET })).mockRejectedValueOnce(new ApiError(400, "invalid_ticket", "x"));
    const { flow } = setup({ otpVerify: verify });
    await flow.submitPhone(PHONE);
    await flow.submitCode("123456");
    await flow.submitFirm("Acme", true);
    expect(flow.state.step).toEqual({ k: "phone" });
    expect(flow.state.error).toMatch(/expired/);
  });

  it("stops on a failed provisioning and flags a slow one", async () => {
    let polls = 0;
    const slow = setup({ provisioning: vi.fn(async (): Promise<Provisioning> => ({ status: ++polls > POLL_SLOW_AFTER ? "failed" : "pending", tenant_id: null, message: polls > POLL_SLOW_AFTER ? "tenant setup failed" : null })) });
    const seen: boolean[] = [];
    slow.flow.subscribe((s) => { if (s.step.k === "provisioning") seen.push(s.step.slow); });
    await slow.flow.resumeProvisioning();
    expect(slow.flow.state.step).toMatchObject({ k: "provisioning", status: "failed", message: "tenant setup failed" });
    expect(seen.includes(true)).toBe(true);
    expect(slow.api.switchFirm).not.toHaveBeenCalled();
  });

  it("refuses accounts without a firm and installs no tokens", async () => {
    const { flow, onTokens } = setup({ otpVerify: vi.fn(async () => tokens("no_firm")) });
    await flow.submitPhone(PHONE);
    await flow.submitCode("123456");
    expect(flow.state).toMatchObject({ step: { k: "phone" }, error: "This account has no active firm." });
    expect(onTokens).not.toHaveBeenCalled();
  });

  it("stops polling once stopped", async () => {
    const { flow, api } = setup({ provisioning: vi.fn(async (): Promise<Provisioning> => { flow.stop(); return { status: "pending", tenant_id: null, message: null }; }) });
    await flow.resumeProvisioning();
    expect(api.provisioning).toHaveBeenCalledTimes(1);
  });
});
