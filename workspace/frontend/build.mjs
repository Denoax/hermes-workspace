import { build } from "esbuild";
import { spawnSync } from "node:child_process";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { createHash } from "node:crypto";
const dir = "../ui/dist";
mkdirSync(dir, { recursive: true });
const css = spawnSync(
  process.execPath,
  [
    "node_modules/@tailwindcss/cli/dist/index.mjs",
    "-i",
    "src/style.css",
    "-o",
    dir + "/app.css",
    "--minify",
  ],
  { stdio: "inherit" },
);
if (css.status !== 0) process.exit(css.status || 1);
await build({
  entryPoints: ["src/main.tsx"],
  bundle: true,
  format: "esm",
  minify: true,
  sourcemap: false,
  target: "es2022",
  outfile: dir + "/app.js",
  define: { "process.env.NODE_ENV": '"production"' },
  alias: { "@": new URL("./src", import.meta.url).pathname },
  external: ["/interface-audio.mjs"],
});
const manifest = {};
for (const name of ["app.js", "app.css"]) {
  const raw = readFileSync(dir + "/" + name);
  manifest[name] = createHash("sha256").update(raw).digest("hex");
}
writeFileSync(dir + "/manifest.json", JSON.stringify(Object.keys(manifest)));
writeFileSync(
  dir + "/identities.json",
  JSON.stringify(manifest, null, 2) + "\n",
);
