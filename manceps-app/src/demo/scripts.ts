// Demo: scripted agent call lines, filled in with the agent's and the driver's names.
import { SCRIPTS, type ScriptLine } from "./data";

/** A rendered call line: speaker label and text. */
export type CallLine = [string, string];

/**
 * Fill {agent} and {driver} in a template.
 *
 * Args:
 *   text: Template text.
 *   agent: Agent display name.
 *   driver: Driver first name.
 *
 * Returns:
 *   The text with both names in place.
 */
export function fillNames(text: string, agent: string, driver: string): string {
  return text.replace(/\{agent\}/g, agent).replace(/\{driver\}/g, driver);
}

/**
 * The scripted call used for the n-th truck in the fleet list.
 *
 * Args:
 *   index: Truck position in the fleet list; negative or unknown positions use the first script.
 *   agent: Agent display name.
 *   driver: Driver first name.
 *
 * Returns:
 *   Speaker label and text per line.
 */
export function callScript(index: number, agent: string, driver: string): CallLine[] {
  const lines: ScriptLine[] = SCRIPTS[Math.max(0, index) % SCRIPTS.length] ?? [];
  return lines.map(([who, text]) => [who === "agent" ? agent : driver, fillNames(text, agent, driver)]);
}
