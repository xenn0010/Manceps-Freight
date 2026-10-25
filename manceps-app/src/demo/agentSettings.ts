// Demo: the firm's agent persona and name, kept in this browser until the backend has agent settings.
import { DEFAULT_SELECTION, parseSelection, type AgentSelection } from "../agents";

const STORAGE_KEY = "manceps.agent";

/**
 * Read the saved agent selection.
 *
 * Returns:
 *   The saved selection, or the default when storage is empty, blocked or holds junk.
 */
export function loadAgentSelection(): AgentSelection {
  try {
    if (typeof localStorage === "undefined") return { ...DEFAULT_SELECTION };
    const raw = localStorage.getItem(STORAGE_KEY);
    return (raw ? parseSelection(JSON.parse(raw)) : null) ?? { ...DEFAULT_SELECTION };
  } catch {
    return { ...DEFAULT_SELECTION };
  }
}

/**
 * Save the agent selection in this browser.
 *
 * Args:
 *   sel: Selection to keep.
 *
 * Returns:
 *   False when storage is unavailable, so the caller can tell the user it won't survive a reload.
 */
export function saveAgentSelection(sel: AgentSelection): boolean {
  try {
    if (typeof localStorage === "undefined") return false;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sel));
    return true;
  } catch {
    return false;
  }
}
