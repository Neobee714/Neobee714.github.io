/**
 * Vault index: pre-scan the Obsidian vault to build:
 *   1. Filename (without extension) -> slug  for wikilink resolution
 *   2. Asset filename (basename) -> absolute path  for ![[image]] resolution
 *
 * The index is built lazily on first access and cached in `globalThis` so
 * remark plugins (one instance per markdown file) share the same map.
 */
import fs from 'node:fs';
import path from 'node:path';
import { resolveVaultPath } from './resolve-vault-path.ts';

interface VaultIndex {
  /** vault absolute root path */
  root: string;
  /** filename without .md extension (lowercased) -> published slug */
  notesByName: Map<string, string>;
  /** asset basename (lowercased) -> absolute filesystem path */
  assetsByName: Map<string, string>;
  /** raw markdown files that exist but are not published (for warning) */
  unpublishedNames: Set<string>;
}

const CACHE_KEY = '__xyvora_vault_index__';

type GlobalWithCache = typeof globalThis & { [CACHE_KEY]?: VaultIndex };

export function getVaultIndex(): VaultIndex {
  const g = globalThis as GlobalWithCache;
  if (g[CACHE_KEY]) return g[CACHE_KEY];

  const vaultRaw = process.env.ASTRO_VAULT_PATH?.trim() || './vault';
  const root = resolveVaultPath(vaultRaw);

  const notesByName = new Map<string, string>();
  const assetsByName = new Map<string, string>();
  const unpublishedNames = new Set<string>();

  if (fs.existsSync(root)) {
    scan(root, notesByName, assetsByName, unpublishedNames);
  } else {
    console.warn(`[vault-index] Vault path not found: ${root}`);
  }

  const idx: VaultIndex = { root, notesByName, assetsByName, unpublishedNames };
  g[CACHE_KEY] = idx;
  return idx;
}

function scan(
  dir: string,
  notes: Map<string, string>,
  assets: Map<string, string>,
  unpublished: Set<string>
) {
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }

  for (const e of entries) {
    if (e.name.startsWith('.')) continue;
    if (e.name === 'Templates' || e.name === 'node_modules' || e.name === '.trash')
      continue;

    const full = path.join(dir, e.name);

    if (e.isDirectory()) {
      scan(full, notes, assets, unpublished);
      continue;
    }

    if (!e.isFile()) continue;

    const lower = e.name.toLowerCase();
    const ext = path.extname(lower);

    // Markdown (not translations — wikilinks should target originals)
    if (ext === '.md' && !lower.endsWith('.en.md')) {
      const basename = path.basename(e.name, '.md');
      const key = basename.toLowerCase();
      const raw = safeRead(full);
      const slug = raw ? extractPublishedSlug(raw) : undefined;
      if (slug) {
        notes.set(key, slug);
      } else {
        unpublished.add(key);
      }
      continue;
    }

    // Images / assets
    if (['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.pdf'].includes(ext)) {
      const key = e.name.toLowerCase();
      // Keep first occurrence (deterministic)
      if (!assets.has(key)) {
        assets.set(key, full);
      }
    }
  }
}

function safeRead(p: string): string | undefined {
  try {
    return fs.readFileSync(p, 'utf8');
  } catch {
    return undefined;
  }
}

/**
 * Parse frontmatter scalars just enough to decide if a note is published,
 * and if so, return its Slug. Mirrors the logic in integrations/slug-check.ts.
 */
function extractPublishedSlug(raw: string): string | undefined {
  if (!raw.startsWith('---')) return undefined;
  const end = raw.indexOf('\n---', 3);
  if (end === -1) return undefined;
  const fm = raw.slice(3, end);

  const fields: Record<string, string> = {};
  for (const line of fm.split(/\r?\n/)) {
    const m = line.match(/^([^\s:][^:]*?):\s*(.*)$/);
    if (m) fields[m[1].trim()] = m[2].trim();
  }

  const pub = (fields['发布'] ?? '').toLowerCase();
  if (!['true', 'yes', '是'].includes(pub)) return undefined;

  const status = (fields['状态'] ?? '').toLowerCase();
  if (['进行中', 'draft', 'wip'].includes(status)) return undefined;

  const slug = fields['Slug']?.trim();
  return slug || undefined;
}

/**
 * Normalize an asset filename for web output:
 *   "image 1.png"        -> "image-1.png"
 *   "截图_01.png"        -> "img-<10char-hash>.png"  (non-ASCII stems use a stable hash)
 *   "Capture.PNG"        -> "capture.png"
 */
export function normalizeAssetName(original: string): string {
  const ext = path.extname(original).toLowerCase();
  const stem = path.basename(original, path.extname(original));

  // Accept ASCII letters/digits/common punctuation. Numbers count as ASCII.
  const isAllAscii = /^[\x20-\x7E]+$/.test(stem);
  let normalized: string;

  if (isAllAscii) {
    normalized = stem
      .toLowerCase()
      .replace(/[\s_]+/g, '-')
      .replace(/[^a-z0-9\-\.]/g, '')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '');
  } else {
    // Non-ASCII: replace with a stable 10-char hex hash of the full original
    // name (including extension) to avoid cross-file collisions.
    const hash = hashStable(original);
    normalized = `img-${hash}`;
  }

  if (!normalized) normalized = 'file';
  return `${normalized}${ext || ''}`;
}

function hashStable(s: string): string {
  // FNV-1a 32-bit hash, outputs 8 hex chars. Stable across platforms.
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(16).padStart(8, '0');
}
