import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.dirname(fileURLToPath(import.meta.url));
let html = readFileSync(path.join(root, "panel.html"), "utf8");
html = html.replace("<script>", "<script>window.BAZAAR_HOSTED=true;</script>\n<script>");
const code = readFileSync(path.join(root, "worker.mjs"), "utf8");
mkdirSync(path.join(root, "dist/server"), { recursive: true });
mkdirSync(path.join(root, "dist/.openai"), { recursive: true });
writeFileSync(path.join(root, "dist/server/index.js"), code + "\nexport default createWorker(" + JSON.stringify(html) + ");\n");
writeFileSync(path.join(root, "dist/.openai/hosting.json"), readFileSync(path.join(root, ".openai/hosting.json")));
console.log("Panel Worker built; no game credentials included.");
