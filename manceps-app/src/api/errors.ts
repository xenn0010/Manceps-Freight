// Typed API errors parsed from the backend's {"error": {code, message, details}} envelope.

/** Status used for failures that never reached the server. */
export const NETWORK_STATUS = 0;
const SECONDS_PER_MINUTE = 60;

/** An error from the Manceps API, or a network failure reaching it. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  /** Seconds from the Retry-After header, when the server sent one. */
  readonly retryAfter: number | null;
  /** X-Request-ID of the failed response, for bug reports. */
  readonly requestId: string | null;

  /**
   * Build an API error.
   *
   * Args:
   *   status: HTTP status, or NETWORK_STATUS when the request never got an answer.
   *   code: Stable machine-readable code; branch on this, never on message.
   *   message: Server message, safe to show.
   *   details: Structured extra information.
   *   retryAfter: Seconds to wait before retrying, if known.
   *   requestId: X-Request-ID of the response, if any.
   */
  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}, retryAfter: number | null = null, requestId: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.retryAfter = retryAfter;
    this.requestId = requestId;
  }
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/**
 * Turn a failed response's status, headers and parsed body into an ApiError.
 *
 * Args:
 *   status: HTTP status.
 *   headers: Response headers.
 *   body: Parsed JSON body, or null when the body was not JSON.
 *
 * Returns:
 *   The error; a generic http_<status> code when the body is not an error envelope.
 */
export function errorFromResponse(status: number, headers: Headers, body: unknown): ApiError {
  const ra = Number(headers.get("Retry-After"));
  const retryAfter = Number.isFinite(ra) && ra > 0 ? ra : null;
  const requestId = headers.get("X-Request-ID");
  const err = isRecord(body) && isRecord(body.error) ? body.error : null;
  if (err && typeof err.code === "string" && typeof err.message === "string") {
    return new ApiError(status, err.code, err.message, isRecord(err.details) ? err.details : {}, retryAfter, requestId);
  }
  return new ApiError(status, "http_" + status, "The server answered " + status + ".", {}, retryAfter, requestId);
}

function waitText(seconds: number | null): string {
  if (!seconds) return "Try again in a little while.";
  if (seconds < SECONDS_PER_MINUTE) return "Try again in " + seconds + " seconds.";
  const m = Math.ceil(seconds / SECONDS_PER_MINUTE);
  return "Try again in " + m + (m === 1 ? " minute." : " minutes.");
}

const MESSAGES: Record<string, string> = {
  network_error: "Can't reach Manceps. Check your connection and try again.",
  invalid_code: "That code didn't work. Check it and try again.",
  invalid_ticket: "Your sign-up step expired. Start again with your phone number.",
  already_signed_up: "This phone already has a firm. Sign in with the code instead.",
  verify_unavailable: "We couldn't reach the text-message service. Try again in a moment.",
  twilio_not_configured: "Phone sign-in isn't set up on this server yet.",
  auth_not_configured: "Sign-in isn't set up on this server yet.",
  firm_provisioning: "Your firm is still being set up.",
  no_firm: "This account has no active firm.",
  firm_suspended: "This firm is suspended. Contact Manceps support.",
  refresh_reuse: "You were signed out for safety. Sign in again.",
  invalid_refresh: "Your session ended. Sign in again.",
  unauthorized: "Your session ended. Sign in again.",
  forbidden: "Your role can't do that.",
  not_found: "That record no longer exists.",
  idempotency_in_progress: "That's still being saved. Give it a second.",
  file_too_large: "That file is too big to import.",
  unsupported_file_type: "Use a .csv or .xlsx file.",
};

function validationText(details: Record<string, unknown>): string | null {
  const errs = Array.isArray(details.errors) ? details.errors : [];
  const first: unknown = errs[0];
  if (!isRecord(first) || typeof first.msg !== "string") return null;
  const loc = Array.isArray(first.loc) ? first.loc.filter((x) => x !== "body").join(".") : "";
  return (loc ? loc + ": " : "") + first.msg;
}

/**
 * A short message for the user, chosen by error code.
 *
 * Args:
 *   e: Any thrown value.
 *
 * Returns:
 *   Text that is safe to show in the UI.
 */
export function friendlyMessage(e: unknown): string {
  if (!(e instanceof ApiError)) return "Something went wrong. Try again.";
  if (e.code === "rate_limited") return "Too many tries. " + waitText(e.retryAfter);
  if (e.code === "validation_error") return validationText(e.details) ?? e.message;
  if (e.code.endsWith("_not_configured") && !MESSAGES[e.code]) return "That feature is switched off on this server.";
  if (e.status >= 500 && !MESSAGES[e.code]) return "Manceps had a problem. Try again in a moment.";
  return MESSAGES[e.code] ?? e.message;
}
