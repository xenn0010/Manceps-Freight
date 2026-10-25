// Response and request shapes for the routes the app calls, written from backend/openapi.json.

export type Role = "owner" | "dispatcher" | "viewer" | "carrier" | "driver" | "system";
export type LoginState = "active" | "provisioning" | "no_firm";

/** Every non-2xx body: {"error": {...}}. */
export interface ErrorBody {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface ErrorEnvelope {
  error: ErrorBody;
}

/** A cursor page; pass next_cursor back as cursor until it is null. */
export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface TokenResponse {
  access_token: string;
  expires_in: number;
  refresh_token: string | null;
  session_id: string;
  user_id: string;
  tenant_id: string | null;
  role: Role;
  state: LoginState;
  signup_token?: string | null;
  token_type?: "bearer";
}

export interface SentResponse {
  sent: boolean;
}

export interface OtpVerifyRequest {
  phone: string;
  code?: string | null;
  signup_ticket?: string | null;
  firm_name?: string | null;
  accept_terms?: true | null;
}

export type ProvisioningStatus = "none" | "pending" | "provisioning" | "ready" | "failed";

export interface Provisioning {
  status: ProvisioningStatus;
  tenant_id: string | null;
  message: string | null;
}

export interface Firm {
  id: string;
  name: string;
  slug: string;
  status: string;
  plan: string;
  timezone: string;
  owner_user_id: string;
  created_at: string;
}

export interface MeUser {
  id: string;
  phone: string | null;
  email: string | null;
  email_verified: boolean;
  name: string | null;
  status: string;
}

export interface MeMembership {
  tenant_id: string;
  firm_name: string | null;
  role: string;
}

export interface Me {
  user: MeUser;
  memberships: MeMembership[];
  current: { tenant_id: string | null; role: Role };
  session_id: string | null;
}

export interface Truck {
  id: string;
  carrier_id: string;
  unit: string;
  equipment: string | null;
  vin: string | null;
  plate: string | null;
  plate_state: string | null;
  max_weight_lbs: number | null;
  created_at: string;
  updated_at: string;
}

export interface TruckCreate {
  carrier_id: string;
  unit: string;
  equipment?: string | null;
  vin?: string | null;
  plate?: string | null;
  plate_state?: string | null;
  max_weight_lbs?: number | null;
}

export interface ConsentState {
  sms: boolean;
  voice: boolean;
  whatsapp: boolean;
  method: string | null;
  recorded_at: string | null;
}

export type DriverStatus = "active" | "inactive";

export interface Driver {
  id: string;
  carrier_id: string;
  name: string | null;
  phone: string | null;
  email: string | null;
  status: string;
  license_state: string | null;
  license_expires_at: string | null;
  consent: ConsentState | null;
  created_at: string;
  updated_at: string;
}

export interface DriverCreate {
  carrier_id: string;
  name: string;
  phone?: string | null;
  email?: string | null;
  status?: DriverStatus | null;
  license_state?: string | null;
  license_expires_at?: string | null;
}

/** Driver changes; null removes an optional field. */
export interface DriverPatch {
  carrier_id?: string | null;
  name?: string | null;
  phone?: string | null;
  email?: string | null;
  status?: DriverStatus | null;
  license_state?: string | null;
  license_expires_at?: string | null;
}

export interface Carrier {
  id: string;
  phone: string | null;
  name: string | null;
  company: string | null;
  mc_number: string | null;
  dot_number: string | null;
  email: string | null;
  equipment: string[];
  home_base: string | null;
  preferred_lanes: Record<string, unknown>[];
  avoid: string[];
  notes: string | null;
  status: string;
  tags: string[];
  insurance_expires_at: string | null;
  dispatch_fee_pct: number | null;
  rate_floor_per_mile: number | null;
  agreement_signed: boolean | null;
  consent: ConsentState | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CarrierCreate {
  phone: string;
  name?: string | null;
  company?: string | null;
  mc_number?: string | null;
  dot_number?: string | null;
  email?: string | null;
  home_base?: string | null;
  status?: "onboarding" | "active" | "paused" | "offboarded" | null;
}

export type ImportEntity = "carriers" | "drivers" | "brokers" | "contacts";
export type ImportStatus = "uploaded" | "validating" | "mapped" | "committing" | "committed" | "failed" | "undoing" | "undone";
export type DuplicateStrategy = "skip" | "update" | "merge";

export interface ImportStats {
  rows: number;
  valid: number;
  invalid: number;
  duplicates_in_file: number;
  needs_approval: number;
  new: number;
  existing: number;
  created: number;
  updated: number;
  merged: number;
  skipped: number;
  rejected: number;
}

export interface ImportOut {
  id: string;
  entity: string;
  source_filename: string;
  file_type: string;
  status: string;
  columns: string[];
  header_row: number | null;
  mapping: Record<string, string | null>;
  suggested_mapping: Record<string, string | null>;
  unmapped_required: string[];
  ignored_consent_columns: string[];
  stats: ImportStats;
  duplicate_strategy: string | null;
  progress: { done: number; total: number } | null;
  undo: { restored: number; removed: number; skipped_modified: number } | null;
  undo_until: string | null;
  created_at: string;
  committed_at: string | null;
  error: string | null;
}

export interface RowError {
  code: string;
  message: string;
  field: string | null;
}

export interface PreviewRow {
  row_no: number;
  cells: Record<string, unknown>;
  values: Record<string, unknown>;
  action: string;
  reason: string | null;
  errors: RowError[];
  match_id: string | null;
}

export interface PreviewOut {
  duplicate_strategy: string;
  counts: Record<string, number>;
  rows: PreviewRow[];
}
