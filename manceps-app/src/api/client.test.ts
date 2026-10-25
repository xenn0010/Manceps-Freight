import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "./client";
import { ApiError, friendlyMessage } from "./errors";
import type { TokenResponse } from "./types";

interface Call {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
  credentials: RequestCredentials | undefined;
}

const tokens = (access: string): TokenResponse => ({
  access_token: access, expires_in: 900, refresh_token: null, session_id: "s1", user_id: "u1", tenant_id: "acme", role: "owner", state: "active",
});

const json = (status: number, body: unknown, headers: Record<string, string> = {}): Response =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

const envelope = (status: number, code: string, message = code, details: Record<string, unknown> = {}, headers: Record<string, string> = {}): Response =>
  json(status, { error: { code, message, details } }, headers);

/** A fetch that records calls and answers with the handler's response. */
function fakeFetch(handler: (c: Call) => Response | Promise<Response>): { fetch: typeof fetch; calls: Call[] } {
  const calls: Call[] = [];
  const f = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const c: Call = {
      url: String(input), method: init?.method ?? "GET", headers: (init?.headers ?? {}) as Record<string, string>,
      body: typeof init?.body === "string" ? JSON.parse(init.body) : init?.body, credentials: init?.credentials,
    };
    calls.push(c);
    return handler(c);
  };
  return { fetch: f as typeof fetch, calls };
}

let n = 0;
const client = (f: typeof fetch): ApiClient => new ApiClient({ baseUrl: "http://api.test/", fetch: f, uuid: () => "key-" + ++n, lock: (fn) => fn() });

/** Answers 401 unless the bearer token is "fresh"; refresh returns "fresh" after a short delay. */
function expiringServer(refreshDelayMs = 5): ReturnType<typeof fakeFetch> {
  return fakeFetch(async (c) => {
    if (c.url.endsWith("/v1/auth/refresh")) {
      await new Promise((r) => setTimeout(r, refreshDelayMs));
      return json(200, tokens("fresh"));
    }
    return c.headers.Authorization === "Bearer fresh" ? json(200, { ok: c.url }) : envelope(401, "unauthorized", "token expired");
  });
}

describe("ApiClient refresh", () => {
  it("shares one refresh across concurrent 401s and retries each request once", async () => {
    const srv = expiringServer();
    const c = client(srv.fetch);
    c.setTokens(tokens("stale"));
    const out = await Promise.all([c.request("GET", "/v1/me"), c.request("GET", "/v1/firm"), c.request("GET", "/v1/trucks")]);
    expect(out).toEqual([{ ok: "http://api.test/v1/me" }, { ok: "http://api.test/v1/firm" }, { ok: "http://api.test/v1/trucks" }]);
    expect(srv.calls.filter((x) => x.url.endsWith("/v1/auth/refresh"))).toHaveLength(1);
    expect(srv.calls.filter((x) => x.url.endsWith("/v1/me"))).toHaveLength(2);
    expect(c.accessToken).toBe("fresh");
  });

  it("sends the refresh with credentials and without a bearer token", async () => {
    const srv = expiringServer();
    const c = client(srv.fetch);
    c.setTokens(tokens("stale"));
    await c.request("GET", "/v1/me");
    const r = srv.calls.find((x) => x.url.endsWith("/v1/auth/refresh"));
    expect(r?.credentials).toBe("include");
    expect(r?.headers.Authorization).toBeUndefined();
    expect(srv.calls.every((x) => x.credentials === "include")).toBe(true);
  });

  it("retries exactly once: a second 401 after refreshing is thrown, not refreshed again", async () => {
    const srv = fakeFetch((c) => (c.url.endsWith("/v1/auth/refresh") ? json(200, tokens("fresh")) : envelope(401, "unauthorized")));
    const c = client(srv.fetch);
    c.setTokens(tokens("stale"));
    await expect(c.request("GET", "/v1/me")).rejects.toMatchObject({ status: 401, code: "unauthorized" });
    expect(srv.calls.map((x) => x.url.replace("http://api.test", ""))).toEqual(["/v1/me", "/v1/auth/refresh", "/v1/me"]);
  });

  it("ends the session when the refresh token was reused, and tells listeners why", async () => {
    const srv = fakeFetch((c) => (c.url.endsWith("/v1/auth/refresh") ? envelope(401, "refresh_reuse", "reused") : envelope(401, "unauthorized")));
    const c = client(srv.fetch);
    const seen = vi.fn();
    c.setTokens(tokens("stale"));
    c.onTokens(seen);
    await expect(c.request("GET", "/v1/me")).rejects.toMatchObject({ code: "refresh_reuse" });
    expect(c.accessToken).toBeNull();
    expect(seen).toHaveBeenLastCalledWith(null, expect.objectContaining({ code: "refresh_reuse" }));
    expect(srv.calls.filter((x) => x.url.endsWith("/v1/me"))).toHaveLength(1);
  });

  it("does not refresh for unauthenticated routes", async () => {
    const srv = fakeFetch(() => envelope(401, "unauthorized"));
    const c = client(srv.fetch);
    await expect(c.request("POST", "/v1/auth/otp/verify", { auth: false, body: { phone: "+12145550199", code: "123456" } })).rejects.toBeInstanceOf(ApiError);
    expect(srv.calls).toHaveLength(1);
  });

  it("skips its own refresh when another request already rotated the token", async () => {
    let first = true;
    const srv = fakeFetch((c) => {
      if (c.url.endsWith("/v1/auth/refresh")) return json(200, tokens("fresh"));
      if (first) { first = false; return envelope(401, "unauthorized"); }
      return json(200, { ok: true });
    });
    const c = client(srv.fetch);
    c.setTokens(tokens("stale"));
    const p = c.request("GET", "/v1/me");
    c.setTokens(tokens("rotated-elsewhere"));
    await expect(p).resolves.toEqual({ ok: true });
    expect(srv.calls.filter((x) => x.url.endsWith("/v1/auth/refresh"))).toHaveLength(0);
  });
});

describe("ApiClient errors", () => {
  it("parses the error envelope into ApiError with code, message, details, status and Retry-After", async () => {
    const srv = fakeFetch(() => envelope(429, "rate_limited", "slow down", { scope: "phone" }, { "Retry-After": "120", "X-Request-ID": "req-9" }));
    const c = client(srv.fetch);
    const err = await c.request("POST", "/v1/auth/otp/start", { auth: false, body: { phone: "+12145550199" } }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 429, code: "rate_limited", message: "slow down", details: { scope: "phone" }, retryAfter: 120, requestId: "req-9" });
    expect(friendlyMessage(err)).toBe("Too many tries. Try again in 2 minutes.");
  });

  it("falls back to http_<status> for bodies that are not an envelope", async () => {
    const c = client(fakeFetch(() => new Response("<html>bad gateway</html>", { status: 502 })).fetch);
    await expect(c.request("GET", "/v1/me")).rejects.toMatchObject({ status: 502, code: "http_502" });
  });

  it("turns a failed fetch into a network_error", async () => {
    const c = client((async () => { throw new TypeError("Failed to fetch"); }) as typeof fetch);
    const err = await c.request("GET", "/v1/me").catch((e: unknown) => e);
    expect(err).toMatchObject({ status: 0, code: "network_error" });
    expect(friendlyMessage(err)).toMatch(/Can't reach Manceps/);
  });

  it("shows the first field problem for validation errors", () => {
    const e = new ApiError(422, "validation_error", "request validation failed", { errors: [{ loc: ["body", "phone"], msg: "enter a 10-digit US phone number", type: "value_error" }] });
    expect(friendlyMessage(e)).toBe("phone: enter a 10-digit US phone number");
  });
});

describe("ApiClient idempotency and pagination", () => {
  it("adds one Idempotency-Key per action and reuses it on the post-refresh retry", async () => {
    const srv = expiringServer(0);
    const c = client(srv.fetch);
    c.setTokens(tokens("stale"));
    await c.request("POST", "/v1/trucks", { body: { carrier_id: "c1", unit: "101" }, idempotencyKey: "action-1" });
    const posts = srv.calls.filter((x) => x.url.endsWith("/v1/trucks"));
    expect(posts).toHaveLength(2);
    expect(posts.map((x) => x.headers["Idempotency-Key"])).toEqual(["action-1", "action-1"]);
    expect(posts[0]?.headers["Content-Type"]).toBe("application/json");
    expect(posts[0]?.body).toEqual({ carrier_id: "c1", unit: "101" });
  });

  it("generates a UUID key when asked and sends none otherwise", async () => {
    const srv = fakeFetch(() => json(201, {}));
    const c = client(srv.fetch);
    c.setTokens(tokens("fresh"));
    await c.request("POST", "/v1/drivers", { body: {}, idempotencyKey: true });
    await c.request("PATCH", "/v1/drivers/d1", { body: { name: "Ava" } });
    expect(srv.calls[0]?.headers["Idempotency-Key"]).toMatch(/^key-\d+$/);
    expect(srv.calls[1]?.headers["Idempotency-Key"]).toBeUndefined();
  });

  it("follows next_cursor until it is null", async () => {
    const pages: Record<string, unknown> = { "": { items: [1, 2], next_cursor: "c2" }, c2: { items: [3], next_cursor: "c3" }, c3: { items: [], next_cursor: null } };
    const srv = fakeFetch((c) => json(200, pages[new URL(c.url).searchParams.get("cursor") ?? ""]));
    const c = client(srv.fetch);
    c.setTokens(tokens("fresh"));
    expect(await c.listAll<number>("/v1/trucks", { carrier_id: "c1" })).toEqual([1, 2, 3]);
    expect(srv.calls.map((x) => new URL(x.url).search)).toEqual(["?limit=200&carrier_id=c1", "?limit=200&carrier_id=c1&cursor=c2", "?limit=200&carrier_id=c1&cursor=c3"]);
  });
});
