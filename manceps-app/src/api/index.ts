// The app's single API client and its bound route helpers.
import { API_URL } from "../config";
import { ApiClient } from "./client";
import { authApi, dataApi, importsApi } from "./endpoints";

export const client = new ApiClient({ baseUrl: API_URL });
export const auth = authApi(client);
export const data = dataApi(client);
export const imports = importsApi(client);

export { ApiClient } from "./client";
export { ApiError, friendlyMessage } from "./errors";
export type * from "./types";
