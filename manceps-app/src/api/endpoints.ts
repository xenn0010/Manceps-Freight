// One typed function per backend route the app uses.
import type { ApiClient } from "./client";
import type {
  Carrier, CarrierCreate, Driver, DriverCreate, DriverPatch, DuplicateStrategy, Firm, ImportEntity, ImportOut, Me,
  OtpVerifyRequest, PreviewOut, Provisioning, SentResponse, TokenResponse, Truck, TruckCreate,
} from "./types";

/** Auth routes: phone OTP, provisioning, firm switch and sign-out. */
export function authApi(c: ApiClient) {
  return {
    otpStart: (phone: string): Promise<SentResponse> => c.request("POST", "/v1/auth/otp/start", { auth: false, body: { phone } }),
    otpVerify: (body: OtpVerifyRequest): Promise<TokenResponse> => c.request("POST", "/v1/auth/otp/verify", { auth: false, body }),
    provisioning: (): Promise<Provisioning> => c.request("GET", "/v1/firm/provisioning"),
    switchFirm: (tenantId: string | null = null): Promise<TokenResponse> => c.request("POST", "/v1/auth/switch-firm", { body: tenantId ? { tenant_id: tenantId } : {} }),
    logout: (): Promise<void> => c.request("POST", "/v1/auth/logout"),
  };
}

export type AuthApi = ReturnType<typeof authApi>;

/** Firm-scoped data routes. Create calls take the Idempotency-Key of the user action. */
export function dataApi(c: ApiClient) {
  return {
    me: (): Promise<Me> => c.request("GET", "/v1/me"),
    firm: (): Promise<Firm> => c.request("GET", "/v1/firm"),
    trucks: (): Promise<Truck[]> => c.listAll<Truck>("/v1/trucks"),
    drivers: (): Promise<Driver[]> => c.listAll<Driver>("/v1/drivers"),
    carriers: (): Promise<Carrier[]> => c.listAll<Carrier>("/v1/carriers"),
    createTruck: (body: TruckCreate, key: string): Promise<Truck> => c.request("POST", "/v1/trucks", { body, idempotencyKey: key }),
    createDriver: (body: DriverCreate, key: string): Promise<Driver> => c.request("POST", "/v1/drivers", { body, idempotencyKey: key }),
    createCarrier: (body: CarrierCreate, key: string): Promise<Carrier> => c.request("POST", "/v1/carriers", { body, idempotencyKey: key }),
    patchDriver: (id: string, body: DriverPatch): Promise<Driver> => c.request("PATCH", "/v1/drivers/" + encodeURIComponent(id), { body }),
  };
}

export type DataApi = ReturnType<typeof dataApi>;

/** Import routes: upload, mapping, preview, commit, status and undo. */
export function importsApi(c: ApiClient) {
  const base = (id: string): string => "/v1/imports/" + encodeURIComponent(id);
  return {
    upload: (entity: ImportEntity, file: Blob, filename: string, key: string): Promise<ImportOut> => {
      const form = new FormData();
      form.set("entity", entity);
      form.set("file", file, filename);
      return c.request("POST", "/v1/imports", { form, idempotencyKey: key });
    },
    get: (id: string): Promise<ImportOut> => c.request("GET", base(id)),
    setMapping: (id: string, mapping: Record<string, string | null>): Promise<ImportOut> => c.request("PUT", base(id) + "/mapping", { body: { mapping } }),
    preview: (id: string, strategy: DuplicateStrategy): Promise<PreviewOut> => c.request("GET", base(id) + "/preview", { query: { duplicate_strategy: strategy } }),
    commit: (id: string, strategy: DuplicateStrategy): Promise<ImportOut> => c.request("POST", base(id) + "/commit", { body: { duplicate_strategy: strategy } }),
    undo: (id: string): Promise<ImportOut> => c.request("POST", base(id) + "/undo"),
    template: (entity: ImportEntity): Promise<Response> => c.request("GET", "/v1/imports/templates/" + entity, { raw: true }),
  };
}

export type ImportsApi = ReturnType<typeof importsApi>;
