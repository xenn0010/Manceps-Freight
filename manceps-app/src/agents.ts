// AI dispatcher personas: the firm picks one of four and may rename it. Ids, names and photos match
// src/pages/start/content.ts so onboarding and the app agree.

export type PersonaId = "arjun" | "mei" | "amara" | "ethan";

export interface Persona {
  id: PersonaId;
  fullName: string;
  role: string;
  avatar: string;
  description: string;
}

/** The firm's choice: which persona, and the name it goes by. */
export interface AgentSelection {
  personaId: PersonaId;
  name: string;
}

/** What the UI needs to show the agent. */
export interface AgentView {
  persona: Persona;
  name: string;
  initials: string;
  avatar: string;
}

/** Name every persona goes by until the firm renames it. */
export const DEFAULT_AGENT_NAME = "Manceps";
/** Longest name the rename field accepts. */
export const AGENT_NAME_MAX = 24;

export const PERSONAS: Persona[] = [
  { id: "arjun", fullName: "Arjun Mehta", role: "The Closer", avatar: "/assets/agent-d.jpg", description: "Quick with numbers. Pushes every rate a little further." },
  { id: "mei", fullName: "Mei Lin", role: "The Planner", avatar: "/assets/agent-c.jpg", description: "Thinks three loads ahead. Keeps empty miles low." },
  { id: "amara", fullName: "Amara Okafor", role: "The Steady Hand", avatar: "/assets/agent-b.jpg", description: "Calm on bad days. Drivers trust her." },
  { id: "ethan", fullName: "Ethan Cole", role: "The Hustler", avatar: "/assets/agent-a.jpg", description: "Always on the boards. First to call on a good load." },
];

export const DEFAULT_SELECTION: AgentSelection = { personaId: "arjun", name: DEFAULT_AGENT_NAME };

/**
 * Look up a persona, falling back to the default one.
 *
 * Args:
 *   id: Persona id.
 *
 * Returns:
 *   The persona.
 */
export function personaById(id: string): Persona {
  return PERSONAS.find((p) => p.id === id) ?? (PERSONAS[0] as Persona);
}

/**
 * Clean a typed agent name: collapse spaces, cap the length, fall back to "Manceps" when blank.
 *
 * Args:
 *   raw: Typed name.
 *
 * Returns:
 *   The name to store.
 */
export function cleanAgentName(raw: string): string {
  return raw.replace(/\s+/g, " ").trim().slice(0, AGENT_NAME_MAX).trim() || DEFAULT_AGENT_NAME;
}

/**
 * Initials drawn when the persona photo fails to load.
 *
 * Args:
 *   name: Display name.
 *
 * Returns:
 *   One or two uppercase letters.
 */
export function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? (parts[0]?.[0] ?? "") + (parts[parts.length - 1]?.[0] ?? "") : name.trim().slice(0, 2);
  return letters.toUpperCase() || "AI";
}

/**
 * Resolve a selection into everything the UI shows. Every surface uses this, so the name and photo stay in sync.
 *
 * Args:
 *   sel: The firm's selection.
 *
 * Returns:
 *   Persona, display name, initials and avatar path.
 */
export function agentOf(sel: AgentSelection): AgentView {
  const persona = personaById(sel.personaId);
  const name = cleanAgentName(sel.name);
  return { persona, name, initials: initialsOf(name), avatar: persona.avatar };
}

/**
 * Validate an unknown value (e.g. from storage) as a selection.
 *
 * Args:
 *   v: Parsed value.
 *
 * Returns:
 *   A valid selection, or null.
 */
export function parseSelection(v: unknown): AgentSelection | null {
  if (typeof v !== "object" || v === null) return null;
  const o = v as Record<string, unknown>;
  if (typeof o.personaId !== "string" || typeof o.name !== "string") return null;
  const persona = PERSONAS.find((p) => p.id === o.personaId);
  return persona ? { personaId: persona.id, name: cleanAgentName(o.name) } : null;
}
