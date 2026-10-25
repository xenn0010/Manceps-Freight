// Fetch wrapper for the Manceps API: bearer token in memory, single-flight cookie refresh, one retry on 401.
import { ApiError, NETWORK_STATUS, errorFromResponse } from "./errors";
import type { Page, TokenResponse } from "./types";

const REFRESH_PATH = "/v1/auth/refresh";
const HTTP_UNAUTHORIZED = 401;
const HTTP_NO_CONTENT = 204;
/** Refresh codes that mean the session is over and the user must sign in again. */
const SESSION_DEAD_CODES = new Set(["refresh_reuse", "invalid_refresh", "unauthorized", "account_disabled"]);
/** Largest page the list routes accept. */
export const MAX_PAGE = 200;
/** Safety stop for listAll so a server bug can't loop forever. */
const MAX_PAGES = 500;

export type Query = Record<string, string | number | boolean | null | undefined>;
export type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface RequestOptions {
  /** JSON body; ignored when form is set. */
  body?: unknown;
  /** Multipart body. */
  form?: FormData;
  query?: Query;
  /** Send the bearer token and refresh on 401 (default true). */
  auth?: boolean;
  /** Idempotency-Key: true makes a fresh UUID, a string is used as is (reuse it for retries of one user action). */
  idempotencyKey?: boolean | string;
  /** Return the raw Response instead of parsed JSON. */
  raw?: boolean;
}

export interface ClientOptions {
  baseUrl: string;
  fetch?: typeof fetch;
  /** UUID source for Idempotency-Key. */
  uuid?: () => string;
  /** Cross-tab mutual exclusion for refresh; defaults to the Web Locks API when present. */
  lock?: <T>(fn: () => Promise<T>) => Promise<T>;
}

type Listener = (tokens: TokenResponse | null, cause: ApiError | null) => void;

function defaultLock<T>(fn: () => Promise<T>): Promise<T> {
  const locks = typeof navigator !== "undefined" ? (navigator as Navigator & { locks?: LockManager }).locks : undefined;
  return locks ? locks.request("manceps-refresh", fn) : fn();
}

function buildUrl(base: string, path: string, query?: Query): string {
  const url = base.replace(/\/+$/, "") + path;
  if (!query) return url;
  const qs = new URLSearchParams();
  Object.entries(query).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") qs.set(k, String(v)); });
  const s = qs.toString();
  return s ? url + "?" + s : url;
}

async function parseBody(res: Response): Promise<unknown> {
  if (res.status === HTTP_NO_CONTENT) return undefined;
  const text = await res.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

/** Typed client; one instance per app holds the access token in memory only. */
export class ApiClient {
  private token: string | null = null;
  private inflight: Promise<TokenResponse> | null = null;
  private listeners = new Set<Listener>();
  private readonly fetchFn: typeof fetch;
  private readonly uuid: () => string;
  private readonly lock: <T>(fn: () => Promise<T>) => Promise<T>;

  /**
   * Create a client.
   *
   * Args:
   *   opts: Base URL plus optional fetch, UUID and lock implementations (tests inject these).
   */
  constructor(private readonly opts: ClientOptions) {
    this.fetchFn = opts.fetch ?? ((input, init) => fetch(input, init));
    this.uuid = opts.uuid ?? (() => crypto.randomUUID());
    this.lock = opts.lock ?? defaultLock;
  }

  /** The current access token, or null when signed out. */
  get accessToken(): string | null {
    return this.token;
  }

  /**
   * Install tokens from sign-in, refresh or switch-firm, or clear them.
   *
   * Args:
   *   tokens: The token response, or null to forget the access token.
   *   cause: Why the session ended, when tokens is null because of an error.
   */
  setTokens(tokens: TokenResponse | null, cause: ApiError | null = null): void {
    this.token = tokens?.access_token ?? null;
    this.listeners.forEach((l) => l(tokens, cause));
  }

  /**
   * Listen for token changes (sign-in, refresh, sign-out, session death).
   *
   * Args:
   *   l: Called with the new tokens, or null plus the cause.
   *
   * Returns:
   *   Unsubscribe function.
   */
  onTokens(l: Listener): () => void {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  }

  /**
   * Rotate the refresh cookie for new tokens. Concurrent callers share one request, because reusing a spent
   * refresh token revokes the whole session family.
   *
   * Returns:
   *   The new tokens.
   *
   * Raises:
   *   ApiError: When the refresh fails; session-ending codes also clear the token.
   */
  refresh(): Promise<TokenResponse> {
    if (!this.inflight) {
      this.inflight = this.lock(() => this.doRefresh()).finally(() => { this.inflight = null; });
    }
    return this.inflight;
  }

  private async doRefresh(): Promise<TokenResponse> {
    try {
      const t = await this.send<TokenResponse>("POST", REFRESH_PATH, { auth: false }, null);
      this.setTokens(t);
      return t;
    } catch (e) {
      if (e instanceof ApiError && (e.status === HTTP_UNAUTHORIZED || SESSION_DEAD_CODES.has(e.code))) this.setTokens(null, e);
      throw e;
    }
  }

  /**
   * Call the API. On a 401 for an authenticated route it refreshes once (shared) and retries exactly once.
   *
   * Args:
   *   method: HTTP method.
   *   path: Path starting with /v1 or /healthz.
   *   opts: Body, query, auth and idempotency options.
   *
   * Returns:
   *   The parsed JSON body (undefined for 204), or the Response when opts.raw.
   *
   * Raises:
   *   ApiError: For any non-2xx answer or network failure.
   */
  async request<T>(method: Method, path: string, opts: RequestOptions = {}): Promise<T> {
    const key = opts.idempotencyKey === true ? this.uuid() : opts.idempotencyKey || null;
    const auth = opts.auth ?? true;
    const sentWith = this.token;
    try {
      return await this.send<T>(method, path, opts, key);
    } catch (e) {
      if (!auth || !(e instanceof ApiError) || e.status !== HTTP_UNAUTHORIZED) throw e;
      if (this.token === sentWith) await this.refresh();
      return this.send<T>(method, path, opts, key);
    }
  }

  private async send<T>(method: Method, path: string, opts: RequestOptions, key: string | null): Promise<T> {
    const headers: Record<string, string> = { Accept: "application/json" };
    if ((opts.auth ?? true) && this.token) headers.Authorization = "Bearer " + this.token;
    if (key) headers["Idempotency-Key"] = key;
    let body: BodyInit | undefined;
    if (opts.form) body = opts.form;
    else if (opts.body !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.body); }
    let res: Response;
    try {
      res = await this.fetchFn(buildUrl(this.opts.baseUrl, path, opts.query), { method, headers, body, credentials: "include" });
    } catch (e) {
      throw new ApiError(NETWORK_STATUS, "network_error", e instanceof Error ? e.message : "network error");
    }
    if (res.ok && opts.raw) return res as unknown as T;
    const parsed = await parseBody(res);
    if (!res.ok) throw errorFromResponse(res.status, res.headers, parsed);
    return parsed as T;
  }

  /**
   * Fetch every item of a cursor-paginated list.
   *
   * Args:
   *   path: List route.
   *   query: Filters; limit and cursor are managed here.
   *
   * Returns:
   *   All items in server order.
   */
  async listAll<T>(path: string, query: Query = {}): Promise<T[]> {
    const out: T[] = [];
    for await (const item of this.paginate<T>(path, query)) out.push(item);
    return out;
  }

  /**
   * Iterate a cursor-paginated list page by page.
   *
   * Args:
   *   path: List route.
   *   query: Filters; limit defaults to MAX_PAGE.
   *
   * Yields:
   *   Each item in server order.
   */
  async *paginate<T>(path: string, query: Query = {}): AsyncGenerator<T> {
    let cursor: string | null = null;
    for (let i = 0; i < MAX_PAGES; i++) {
      const page: Page<T> = await this.request<Page<T>>("GET", path, { query: { limit: MAX_PAGE, ...query, cursor } });
      yield* page.items;
      cursor = page.next_cursor;
      if (!cursor) return;
    }
    throw new ApiError(NETWORK_STATUS, "too_many_pages", "the list did not end after " + MAX_PAGES + " pages");
  }
}
