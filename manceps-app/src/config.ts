// Build-time configuration read from Vite env variables (see .env.example).

/** Local backend used when VITE_API_URL is not set. */
const DEFAULT_API_URL = "http://127.0.0.1:8000";

/** Base URL of the Manceps API, without a trailing slash. */
export const API_URL: string = (import.meta.env.VITE_API_URL || DEFAULT_API_URL).replace(/\/+$/, "");
