import { describe, expect, it } from "vitest";
import { DEFAULT_SELECTION, PERSONAS, agentOf, cleanAgentName, parseSelection } from "./agents";
import { DISPATCHES, PRESETS, SCRIPTS, callScript, setPerm } from "./demo";
import { getState, resetState } from "./store";

describe("agent personas", () => {
  it("offers the four design personas with their photos, Arjun selected and named Manceps by default", () => {
    expect(PERSONAS.map((p) => [p.id, p.fullName, p.avatar])).toEqual([
      ["arjun", "Arjun Mehta", "/assets/agent-d.jpg"], ["mei", "Mei Lin", "/assets/agent-c.jpg"],
      ["amara", "Amara Okafor", "/assets/agent-b.jpg"], ["ethan", "Ethan Cole", "/assets/agent-a.jpg"],
    ]);
    expect(agentOf(DEFAULT_SELECTION)).toMatchObject({ name: "Manceps", initials: "MA", avatar: "/assets/agent-d.jpg" });
  });

  it("cleans renames and rejects junk from storage", () => {
    expect(cleanAgentName("  Big   Rig  ")).toBe("Big Rig");
    expect(cleanAgentName("   ")).toBe("Manceps");
    expect(cleanAgentName("x".repeat(40))).toHaveLength(24);
    expect(parseSelection({ personaId: "mei", name: " Mei " })).toEqual({ personaId: "mei", name: "Mei" });
    expect(parseSelection({ personaId: "bob", name: "Bob" })).toBeNull();
    expect(parseSelection("nope")).toBeNull();
  });
});

describe("AI disclosure", () => {
  it("opens every scripted call by saying the agent is an AI, under any name", () => {
    SCRIPTS.forEach((_, i) => {
      const first = callScript(i, "Rosie", "Ava")[0];
      expect(first?.[0]).toBe("Rosie");
      expect(first?.[1]).toMatch(/it's Rosie, the AI dispatcher/);
    });
    expect(DISPATCHES.some(([t]) => t.includes("Arjun"))).toBe(false);
  });
});

describe("booking and signing always need the owner", () => {
  it("keeps book and sign at ask in every preset", () => {
    Object.values(PRESETS).forEach(([, , p]) => expect([p.book, p.sign]).toEqual(["ask", "ask"]));
  });

  it("never books by itself when permissions change", () => {
    resetState();
    setPerm({ ...PRESETS.auto[2] });
    expect(getState().booked).toBe(false);
    expect(getState().perm).toMatchObject({ book: "ask", sign: "ask", negotiate: "auto" });
  });
});
