import { describe, expect, it } from "vitest";
import { QS } from "../pages/start/content";
import { completeTask, initialOnboard, isAnswered, isPicked, nextUploadProgress, pickCard, setupSummary, signupValid, truckBoxes } from "./onboarding";

describe("sign-up", () => {
  it("needs an email and an 8+ character password", () => {
    expect(signupValid("jo@fleet.com", "12345678")).toBe(true);
    expect(signupValid("jo@fleet", "12345678")).toBe(false);
    expect(signupValid("jo@fleet.com", "1234567")).toBe(false);
  });
});

describe("questions", () => {
  it("replaces single-choice answers and toggles multi-choice ones", () => {
    let a = initialOnboard().ans;
    a = pickCard(a, "who", false, "Small fleet");
    a = pickCard(a, "who", false, "Owner-operator");
    expect(a.who).toBe("Owner-operator");
    a = pickCard(a, "haul", true, "Reefer");
    a = pickCard(a, "haul", true, "Flatbed");
    a = pickCard(a, "haul", true, "Reefer");
    expect(a.haul).toEqual(["Flatbed"]);
    expect(isPicked(a, "haul", "Flatbed")).toBe(true);
  });

  it("only lets Next advance once the question is answered", () => {
    const s = initialOnboard();
    const [who, haul, , agent, name] = QS;
    if (!who || !haul || !agent || !name) throw new Error("questions missing");
    expect(isAnswered(who, s)).toBe(false);
    expect(isAnswered(who, { ...s, ans: { ...s.ans, who: "Small fleet" } })).toBe(true);
    expect(isAnswered(haul, { ...s, ans: { ...s.ans, haul: ["Reefer"] } })).toBe(true);
    expect(isAnswered(agent, { ...s, agent: "mei" })).toBe(true);
    expect(isAnswered(name, { ...s, biz: "   " })).toBe(false);
  });
});

describe("setup guide", () => {
  it("opens the next unfinished task and closes when everything is done", () => {
    expect(completeTask({ acct: true }, "import")).toEqual({ done: { acct: true, import: true }, open: "truck" });
    const all = { acct: true, import: true, truck: true, rates: true, phone: true };
    expect(completeTask(all, "eld").open).toBeNull();
  });

  it("summarizes answers", () => {
    expect(setupSummary({ who: "Small fleet", haul: ["Dry van", "Reefer"], lanes: [] })).toBe("Small fleet · Dry van, Reefer");
    expect(setupSummary({ who: null, haul: [], lanes: [] })).toBe("Tell us more in Settings");
  });

  it("animates only newly filled truck boxes", () => {
    const first = truckBoxes(0.5, null);
    expect(first.filled).toBe(18);
    expect(first.boxes.filter((b) => b.anim !== "none")).toHaveLength(0);
    const next = truckBoxes(1, first.filled);
    expect(next.boxes.filter((b) => b.anim !== "none")).toHaveLength(18);
    expect(next.boxes[18]?.anim).toContain("0ms");
  });

  it("caps upload progress at 100", () => {
    expect(nextUploadProgress(90, 1)).toBe(100);
    expect(nextUploadProgress(0, 0)).toBe(15);
  });
});
