import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/** Absolute path of the marketing/ project root. */
export const ROOT_DIR = join(dirname(fileURLToPath(import.meta.url)), "..");
