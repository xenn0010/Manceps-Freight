import { describe, expect, it } from "vitest";
import { DCOLS, type Row } from "../data";
import { DEMO_DRIVERS, LCOLS, PRESETS, classifyCommand, planSheetOp, type SheetInput } from "../demo";
import { initialState } from "../store";
import { applyStep, fmtCell, rpmOf, toCsv } from "./sheet";

const input = (patch: Partial<SheetInput> = {}): SheetInput => {
  const s = initialState();
  return { loads: s.loads, drivers: DEMO_DRIVERS, rowsSel: [], perm: s.perm, agentName: "Arjun", ...patch };
};

const applyAll = (plan: ReturnType<typeof planSheetOp>, rows: Row[]): Row[] => {
  if ("error" in plan) throw new Error(plan.error);
  return plan.steps.reduce(applyStep, rows);
};

describe("rpmOf and fmtCell", () => {
  it("computes rate per mile and blanks missing values", () => {
    const [first, , , , open] = initialState().loads;
    expect(rpmOf(first as Row)).toBeCloseTo(5.2);
    expect(rpmOf(open as Row)).toBeNull();
    expect(fmtCell(first as Row, "rate")).toBe("$650");
    expect(fmtCell(first as Row, "rpm")).toBe("$5.20");
    expect(fmtCell(open as Row, "rate")).toBe("");
    expect(fmtCell(open as Row, "miles")).toBe("");
  });
});

describe("planSheetOp", () => {
  it("fills both open rows with backhauls and marks them Proposed", () => {
    const rows = applyAll(planSheetOp("backhaul", input()), input().loads);
    expect(rows[4]).toMatchObject({ id: "L-41207", status: "Proposed", rate: 780 });
    expect(rows[5]).toMatchObject({ id: "L-41388", status: "Proposed", rate: 520 });
  });

  it("negotiates every offer up 7% rounded to $10", () => {
    const rows = applyAll(planSheetOp("negotiate", input()), input().loads);
    expect(rows[7]?.rate).toBe(1750);
    expect(rows[7]?.notes).toBe("Countered +$110 · accepted");
    expect(rows[0]?.rate).toBe(650);
  });

  it("only negotiates selected rows when some are selected", () => {
    const rows = applyAll(planSheetOp("negotiate", input({ rowsSel: [6] })), input().loads);
    expect(rows[6]?.rate).toBe(410);
    expect(rows[7]?.rate).toBe(1640);
  });

  it("refuses to negotiate when the permission is off; booking always waits for the owner's own tap", () => {
    const perm = { ...PRESETS.balanced[2], negotiate: "off" as const };
    expect(planSheetOp("negotiate", input({ perm }))).toEqual({ error: "Negotiating is off for Arjun · change it in Permissions" });
    expect(Object.values(PRESETS).every(([, , p]) => p.book === "ask" && p.sign === "ask")).toBe(true);
    expect("error" in planSheetOp("book", input({ perm }))).toBe(false);
  });

  it("books offers at or above $3.60/mi and reports the 101 backhaul", () => {
    const plan = planSheetOp("book", input());
    if ("error" in plan) throw new Error(plan.error);
    expect(plan.booksBackhaul101).toBe(true);
    const rows = plan.steps.reduce(applyStep, input().loads);
    expect(rows[3]?.status).toBe("Booked");
    expect(rows[7]?.status).toBe("Booked");
    expect(rows[8]?.status).toBe("Offer");
    expect(plan.label).toBe("Booked " + rows.filter((r) => r.status === "Booked").length + " loads");
  });

  it("flags offers under the floor", () => {
    const rows = applyAll(planSheetOp("flag", input()), input().loads);
    expect(rows[8]).toMatchObject({ flag: true, notes: "Under your $3.60/mi floor · I'd pass" });
    expect(rows[7]?.flag).toBe(false);
  });

  it("has nothing to send before anything is booked", () => {
    const plan = planSheetOp("ratecons", input());
    expect("error" in plan ? [] : plan.steps).toEqual([]);
  });

  it("texts every driver and switches to the drivers tab", () => {
    const plan = planSheetOp("text", input());
    if ("error" in plan) throw new Error(plan.error);
    expect(plan.switchToDrivers).toBe(true);
    const rows = plan.steps.reduce(applyStep, DEMO_DRIVERS);
    expect(rows[3]?.notes).toBe("Texted tomorrow's plan · will read at 07:00");
    expect(rows[0]?.checkin).toBe("Just now · WhatsApp");
  });
});

describe("classifyCommand", () => {
  it.each([
    ["find me backhauls", "backhaul"],
    ["negotiate harder", "negotiate"],
    ["flag the cheap ones", "flag"],
    ["send rate cons", "ratecons"],
    ["whatsapp the team", "text"],
    ["book them", "book"],
    ["hello", null],
  ])("%s -> %s", (q, want) => {
    expect(classifyCommand(q)).toBe(want);
  });
});

describe("toCsv", () => {
  it("quotes every cell and escapes quotes", () => {
    const csv = toCsv(DCOLS.slice(0, 2), [{ driver: 'Ava "A" Reed', truck: "101" }]);
    expect(csv).toBe('Driver,Truck\n"Ava ""A"" Reed","101"');
    expect(toCsv(LCOLS, initialState().loads).split("\n")).toHaveLength(11);
  });
});
