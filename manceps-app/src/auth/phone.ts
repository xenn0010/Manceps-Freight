// US phone numbers: normalize to E.164 the same way the backend does (manceps_core/phones.py).

const US_COUNTRY_CODE = "1";
const US_NATIONAL_DIGITS = 10;
const AREA_LEN = 3;
const PREFIX_END = 6;

/**
 * Normalize a US phone number to E.164.
 *
 * Args:
 *   raw: Number in any common US format, e.g. "(214) 555-0199" or "+1 214 555 0199".
 *
 * Returns:
 *   "+1XXXXXXXXXX", or null when it is not a 10-digit US number.
 */
export function normalizeUsPhone(raw: string): string | null {
  let digits = raw.replace(/[^0-9]/g, "");
  if (digits.length === US_NATIONAL_DIGITS + 1 && digits.startsWith(US_COUNTRY_CODE)) digits = digits.slice(1);
  return digits.length === US_NATIONAL_DIGITS ? "+" + US_COUNTRY_CODE + digits : null;
}

/**
 * Format a phone for display as "(214) 555-0199".
 *
 * Args:
 *   phone: E.164 or any US format; other values are returned unchanged.
 *
 * Returns:
 *   The formatted number, or the input when it is not a US number.
 */
export function formatUsPhone(phone: string): string {
  const e = normalizeUsPhone(phone);
  if (!e) return phone;
  const d = e.slice(2);
  return "(" + d.slice(0, AREA_LEN) + ") " + d.slice(AREA_LEN, PREFIX_END) + "-" + d.slice(PREFIX_END);
}

/**
 * Progressive formatting while the user types, capped at a 10-digit number (with an optional leading 1).
 *
 * Args:
 *   raw: Current input text.
 *
 * Returns:
 *   Text like "(214) 555-01".
 */
export function typingUsPhone(raw: string): string {
  let d = raw.replace(/[^0-9]/g, "");
  if (d.length > US_NATIONAL_DIGITS && d.startsWith(US_COUNTRY_CODE)) d = d.slice(1);
  d = d.slice(0, US_NATIONAL_DIGITS);
  if (d.length <= AREA_LEN) return d.length ? "(" + d : "";
  if (d.length <= PREFIX_END) return "(" + d.slice(0, AREA_LEN) + ") " + d.slice(AREA_LEN);
  return "(" + d.slice(0, AREA_LEN) + ") " + d.slice(AREA_LEN, PREFIX_END) + "-" + d.slice(PREFIX_END);
}
