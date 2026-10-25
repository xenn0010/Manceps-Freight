// Session lifecycle: boot from the refresh cookie, finish sign-in, react to session death, sign out.
import { auth, client } from "../api";
import { ApiError, NETWORK_STATUS, friendlyMessage } from "../api/errors";
import type { TokenResponse } from "../api/types";
import { getState, initialState, resetState, setState } from "../store";
import { clearLiveCache, loadAll } from "./fleet";

let wired = false;

function toSignedOut(note: string | null): void {
  clearLiveCache();
  resetState({ ...initialState(), session: "signedOut", sessionNote: note, agent: getState().agent });
}

/** Watch the client: when a refresh fails for good, drop to the sign-in screen with the reason. */
function wire(): void {
  if (wired) return;
  wired = true;
  client.onTokens((tokens, cause) => {
    const live = getState().session === "ready" || getState().session === "provisioning";
    if (!tokens && cause && live) toSignedOut(friendlyMessage(cause));
  });
}

/**
 * Enter the app with tokens from sign-in, refresh or switch-firm.
 *
 * Args:
 *   t: Tokens; their state decides between the app and the provisioning wait screen.
 */
export function enterWith(t: TokenResponse): void {
  if (t.state === "active") {
    setState({ session: "ready", sessionNote: null });
    void loadAll();
  } else if (t.state === "provisioning") setState({ session: "provisioning", sessionNote: null });
  else toSignedOut(friendlyMessage(new ApiError(403, "no_firm", "no firm")));
}

/**
 * On page load, try the refresh cookie; without a live session show the sign-in screen.
 */
export async function bootSession(): Promise<void> {
  wire();
  try {
    enterWith(await client.refresh());
  } catch (e) {
    const unreachable = e instanceof ApiError && (e.status === NETWORK_STATUS || e.status >= 500);
    toSignedOut(unreachable ? friendlyMessage(e) : null);
  }
}

/** End this session on the server and locally. */
export async function signOut(): Promise<void> {
  let note: string | null = null;
  try {
    await auth.logout();
  } catch (e) {
    note = "Signed out here, but the server didn't confirm (" + friendlyMessage(e) + ") Sign out again on a shared computer.";
  }
  client.setTokens(null);
  toSignedOut(note);
}
