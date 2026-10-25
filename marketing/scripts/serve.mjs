// Static server for a snapshot of the prebuilt app (marketing/.appdist) with SPA fallback to index.html.
// Usage: node scripts/serve.mjs [port] [dir]
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { ROOT_DIR } from "./paths.mjs";

const PORT = Number(process.argv[2] ?? 4791);
const DIR = process.argv[3] ?? join(ROOT_DIR, ".appdist");
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".png": "image/png", ".jpg": "image/jpeg", ".otf": "font/otf", ".svg": "image/svg+xml", ".json": "application/json", ".woff2": "font/woff2" };

if (!existsSync(join(DIR, "index.html"))) throw new Error(`No index.html in ${DIR}; copy manceps-app/dist there first`);

createServer((req, res) => {
  const path = normalize(decodeURIComponent((req.url ?? "/").split("?")[0])).replace(/^(\.\.[/\\])+/, "");
  let file = join(DIR, path);
  if (!file.startsWith(DIR) || !existsSync(file) || statSync(file).isDirectory()) file = join(DIR, "index.html");
  res.writeHead(200, { "Content-Type": TYPES[extname(file)] ?? "application/octet-stream", "Cache-Control": "no-store" });
  createReadStream(file).pipe(res);
}).listen(PORT, "127.0.0.1", () => console.log(`serving ${DIR} on http://127.0.0.1:${PORT}/`));
