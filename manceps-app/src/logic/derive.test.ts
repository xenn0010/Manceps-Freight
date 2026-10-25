import { describe, expect, it } from "vitest";
import { PRESETS, allNeeds, presetName, truckHeadline, truckLoad, weekBars } from "../demo";
import { along, minutesTo } from "../map/geo";
import { fmtClock, fmtMinutes, needSummary } from "./derive";
import { formulaBar, sheetHeading } from "./sheetView";
import { initialState } from "../store";

describe("needs", () => {
  it("lists both decisions until they are handled", () => {
    expect(allNeeds({ booked: false, r102: false }).map((n) => n.id)).toEqual(["b101", "r102"]);
    expect(allNeeds({ booked: true, r102: true })).toEqual([]);
    expect(needSummary(2).text).toBe("2 things for you");
    expect(needSummary(1).text).toBe("1 thing for you");
    expect(needSummary(0)).toEqual({ dot: "#1F9A5A", mark: "✓", text: "All clear" });
  });
});

describe("presetName", () => {
  it("names exact presets and falls back to Custom", () => {
    expect(presetName({ ...PRESETS.balanced[2] })).toBe("Balanced");
    expect(presetName({ ...PRESETS.auto[2] })).toBe("Autopilot");
    expect(presetName({ ...PRESETS.auto[2], reroute: "ask" })).toBe("Custom");
  });
});

describe("trucks", () => {
  it("updates 102 once Ben is briefed and 101 once booked", () => {
    expect(truckHeadline("T-102", { booked: false, r102: true })).toMatchObject({ pill: "On time", next: "New window 15:30–16:30 · on time" });
    expect(truckHeadline("T-102", { booked: false, r102: false }).pill).toBe("Running late");
    expect(truckLoad("T-101", false)).toBeNull();
    expect(truckLoad("T-101", true)?.lane).toBe("Commerce → San Francisco");
  });

  it("adds the booked backhaul to Tuesday's bar", () => {
    expect(weekBars(false)[1]).toEqual({ d: "T", h: "10px", c: "#010D1D" });
    expect(weekBars(true)[1]).toEqual({ d: "T", h: "44px", c: "#2272AD" });
    expect(weekBars(false)[4]?.h).toBe("4px");
  });
});

describe("formatting", () => {
  it("formats minutes and clocks", () => {
    expect(fmtMinutes(45)).toBe("45 min");
    expect(fmtMinutes(125)).toBe("2 h 5 m");
    expect(fmtClock(65)).toBe("1:05");
  });

  it("shows the $/mi formula for the rpm cell", () => {
    const s = initialState();
    expect(formulaBar(s)).toEqual({ ref: "H5", val: "$2,240" });
    expect(formulaBar({ ...s, cell: { r: 0, k: "rpm" } })).toEqual({ ref: "I2", val: "=H2/G2" });
    expect(sheetHeading(true, s.loads)).toEqual({ title: "Loads · week of Oct 26", sub: "10 rows · 0 booked · 2 open" });
  });
});

describe("route geometry", () => {
  it("interpolates along a polyline and clamps the fraction", () => {
    const line: [number, number][] = [[0, 0], [10, 0], [10, 10]];
    expect(along(line, 0.25)).toEqual([5, 0]);
    expect(along(line, 0.75)).toEqual([10, 5]);
    expect(along(line, 2)).toEqual([10, 10]);
    expect(minutesTo("T-102", 1, 0.5)).toBe(95);
    expect(minutesTo("T-101", 0.5, 0.5)).toBe(1);
  });
});
