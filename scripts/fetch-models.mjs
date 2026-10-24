// Fills models/ with the files models/manifest.json lists, checked by sha256.
//
// tauri build bundles models/ into the app's Resources, so the sidecar loads
// its models from disk and never touches the network. Downloads go through a
// shared cache keyed by sha256 (~/.cache/unseen-servant/models, or
// UNSEEN_MODELS_CACHE), so each worktree links or copies instead of
// downloading again.
// Sources are Hugging Face repos pinned to a revision.
//
//   node scripts/fetch-models.mjs          fetch what is missing or wrong
//   node scripts/fetch-models.mjs --check  only verify (tauri build's hook)
import { createHash } from 'node:crypto';
import { copyFileSync, createReadStream, createWriteStream, existsSync, linkSync, mkdirSync, readFileSync, renameSync, rmSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, relative } from 'node:path';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const modelsDir = join(root, 'models');
const cacheDir = process.env.UNSEEN_MODELS_CACHE || join(homedir(), '.cache', 'unseen-servant', 'models');
const checkOnly = process.argv.includes('--check');
const manifest = JSON.parse(readFileSync(join(modelsDir, 'manifest.json'), 'utf8'));

function sha256(path) {
  return new Promise((resolve, reject) => {
    const hash = createHash('sha256');
    createReadStream(path)
      .on('data', (chunk) => hash.update(chunk))
      .on('end', () => resolve(hash.digest('hex')))
      .on('error', reject);
  });
}

async function matches(path, file) {
  return existsSync(path) && (await sha256(path)) === file.sha256;
}

async function download(model, file, dest) {
  const { hf, revision } = model.source;
  const url = `https://huggingface.co/${hf}/resolve/${revision}/${file.path}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  const partial = `${dest}.partial`;
  const hash = createHash('sha256');
  await pipeline(
    Readable.fromWeb(res.body),
    async function* (chunks) {
      for await (const chunk of chunks) {
        hash.update(chunk);
        yield chunk;
      }
    },
    createWriteStream(partial),
  );
  const got = hash.digest('hex');
  if (got !== file.sha256) {
    rmSync(partial);
    throw new Error(`${url}: sha256 ${got}, manifest says ${file.sha256}`);
  }
  renameSync(partial, dest);
}

const wrong = [];
for (const model of manifest.models) {
  for (const file of model.files) {
    const target = join(modelsDir, model.dir, file.path);
    if (await matches(target, file)) continue;
    if (checkOnly) {
      wrong.push(relative(root, target));
      continue;
    }
    const cached = join(cacheDir, file.sha256);
    if (!(await matches(cached, file))) {
      mkdirSync(cacheDir, { recursive: true });
      rmSync(cached, { force: true });
      console.log(`Downloading ${model.source.hf}/${file.path}`);
      await download(model, file, cached);
    }
    mkdirSync(dirname(target), { recursive: true });
    rmSync(target, { force: true });
    // A hard link costs no space; across volumes, copy.
    try {
      linkSync(cached, target);
    } catch {
      copyFileSync(cached, target);
    }
    console.log(`Placed ${relative(root, target)}`);
  }
}

if (wrong.length) {
  console.error(`Missing or changed model files: ${wrong.join(', ')}. Run \`node scripts/fetch-models.mjs\` before \`tauri build\`.`);
  process.exit(1);
}
