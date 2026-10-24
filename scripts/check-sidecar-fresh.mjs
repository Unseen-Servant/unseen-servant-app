// Refuses a `tauri build` whose bundled sidecar is older than its source.
//
// `tauri build` bundles whatever sits in src-tauri/binaries/, so a sidecar
// change since the last scripts/build-sidecar.sh would ship stale. Runs ahead
// of the frontend build in beforeBuildCommand. CI skips it: release.yml builds
// its sidecars from the sources it checked out, and a Windows cache hit keeps
// the cached binaries' old mtimes through Copy-Item.
import { readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

if (process.env.CI) process.exit(0);

const root = fileURLToPath(new URL('..', import.meta.url));
const triple = process.env.TAURI_ENV_TARGET_TRIPLE;
const ext = process.env.TAURI_ENV_PLATFORM === 'windows' ? '.exe' : '';
// Tests, evals and build output don't ship; dot-dirs cover .venv and caches.
const SKIP = new Set(['tests', 'evals', 'build', 'dist', 'chroma_db', '__pycache__']);

function fail(why) {
  console.error(`${why} Run \`bash scripts/build-sidecar.sh\` before \`tauri build\`.`);
  process.exit(1);
}

if (!triple) fail('TAURI_ENV_TARGET_TRIPLE is unset: this check runs as tauri build\'s beforeBuildCommand.');

let newest = { path: '', mtime: 0 };
function consider(path) {
  const { mtimeMs } = statSync(path);
  if (mtimeMs > newest.mtime) newest = { path, mtime: mtimeMs };
}
function walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!SKIP.has(entry.name) && !entry.name.startsWith('.')) walk(path);
    } else if (entry.name.endsWith('.py')) {
      consider(path);
    }
  }
}

walk(join(root, 'sidecar'));
for (const file of ['sidecar/pyproject.toml', 'sidecar/uv.lock', 'sidecar/.python-version', 'scripts/build-sidecar.sh']) {
  consider(join(root, file));
}

// build.rs writes an empty placeholder so cargo can compile without it.
const llama = join(root, 'src-tauri', 'binaries', `llama-server-${triple}${ext}`);
let llamaSize = 0;
try {
  llamaSize = statSync(llama).size;
} catch {}
if (!llamaSize) {
  console.error(`${relative(root, llama)} is missing. Run \`bash scripts/build-llama-server.sh\` before \`tauri build\`.`);
  process.exit(1);
}

for (const name of ['legend-lore-sidecar', 'legend-lore-mcp']) {
  const binary = join(root, 'src-tauri', 'binaries', `${name}-${triple}${ext}`);
  let mtime;
  try {
    mtime = statSync(binary).mtimeMs;
  } catch {
    fail(`${relative(root, binary)} is missing.`);
  }
  if (mtime < newest.mtime) {
    fail(`${relative(root, binary)} is older than ${relative(root, newest.path)}.`);
  }
}
