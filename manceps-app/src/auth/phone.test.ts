import { describe, expect, it } from "vitest";
import { formatUsPhone, normalizeUsPhone, typingUsPhone } from "./phone";

describe("normalizeUsPhone", () => {
  it.each([
    ["(214) 555-0199", "+12145550199"],
    ["214.555.0199", "+12145550199"],
    ["+1 214 555 0199", "+12145550199"],
    ["1-214-555-0199", "+12145550199"],
    ["2145550199", "+12145550199"],
  ])("%s -> %s", (raw, want) => {
    expect(normalizeUsPhone(raw)).toBe(want);
  });

  it.each(["", "555-0199", "+44 20 7946 0958", "22145550199", "214555019912", "١٢٣٤٥٦٧٨٩٠"])("rejects %s", (raw) => {
    expect(normalizeUsPhone(raw)).toBeNull();
  });
});

describe("display and typing", () => {
  it("formats E.164 for display and leaves other text alone", () => {
    expect(formatUsPhone("+12145550199")).toBe("(214) 555-0199");
    expect(formatUsPhone("not a phone")).toBe("not a phone");
  });

  it("formats progressively while typing and drops a leading country code", () => {
    expect(typingUsPhone("")).toBe("");
    expect(typingUsPhone("21")).toBe("(21");
    expect(typingUsPhone("21455")).toBe("(214) 55");
    expect(typingUsPhone("2145550199")).toBe("(214) 555-0199");
    expect(typingUsPhone("12145550199")).toBe("(214) 555-0199");
    expect(typingUsPhone("(214) 555-01999")).toBe("(214) 555-0199");
  });
});
