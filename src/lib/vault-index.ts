import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import type { PublishedVaultPost } from './vault-source.ts';
import { walkVaultFiles } from './vault-source.ts';

export interface ResolvedVaultAsset {
  absolutePath: string;
  outputName: string;
}

export interface VaultIndex {
  root: string;
  notesByName: Map<string, string>;
  assetCandidatesByName: Map<string, string[]>;
  contentHashByPath: Map<string, string>;
  resolvedAssetsByOutputName: Map<string, string>;
  missingReferences: Set<string>;
}

const CACHE_KEY = '__xyvora_vault_index__';
const SUPPORTED_ASSET_EXTENSIONS = new Set([
  '.png',
  '.jpg',
  '.jpeg',
  '.gif',
  '.webp',
  '.svg',
  '.pdf',
]);

type GlobalWithCache = typeof globalThis & { [CACHE_KEY]?: VaultIndex };

export function primeVaultIndex(index: VaultIndex): void {
  (globalThis as GlobalWithCache)[CACHE_KEY] = index;
}

export function clearVaultIndex(): void {
  delete (globalThis as GlobalWithCache)[CACHE_KEY];
}

export function getVaultIndex(): VaultIndex {
  const index = (globalThis as GlobalWithCache)[CACHE_KEY];
  if (!index) throw new Error('Vault index was not primed');
  return index;
}

export async function buildVaultIndex(
  root: string,
  posts: PublishedVaultPost[],
): Promise<VaultIndex> {
  const absoluteRoot = path.resolve(root);
  const notesByName = new Map<string, string>();
  const referencedBasenames = new Set<string>();

  for (const post of posts) {
    const noteName = path.basename(post.absolutePath, path.extname(post.absolutePath)).toLowerCase();
    notesByName.set(noteName, post.slug);
    for (const target of extractAssetReferences(post.body)) {
      const basename = assetBasename(target);
      if (basename && isSupportedAsset(basename)) referencedBasenames.add(basename.toLowerCase());
    }
  }

  const retainedFiles = (await walkVaultFiles(absoluteRoot))
    .filter((absolutePath) => {
      const basename = path.basename(absolutePath).toLowerCase();
      return referencedBasenames.has(basename) && isSupportedAsset(basename);
    })
    .sort((left, right) => {
      const leftRelative = posixRelative(absoluteRoot, left);
      const rightRelative = posixRelative(absoluteRoot, right);
      return leftRelative < rightRelative ? -1 : leftRelative > rightRelative ? 1 : 0;
    });

  const assetCandidatesByName = new Map<string, string[]>();
  for (const absolutePath of retainedFiles) {
    const key = path.basename(absolutePath).toLowerCase();
    const candidates = assetCandidatesByName.get(key) ?? [];
    candidates.push(absolutePath);
    assetCandidatesByName.set(key, candidates);
  }

  const contentHashByPath = new Map<string, string>();
  const contentHashes = await Promise.all(
    retainedFiles.map(async (absolutePath) => {
      const content = await readFile(absolutePath);
      return createHash('sha256').update(content).digest('hex');
    }),
  );
  for (let index = 0; index < retainedFiles.length; index++) {
    contentHashByPath.set(retainedFiles[index], contentHashes[index]);
  }

  return {
    root: absoluteRoot,
    notesByName,
    assetCandidatesByName,
    contentHashByPath,
    resolvedAssetsByOutputName: new Map(),
    missingReferences: new Set(),
  };
}

export function resolveVaultAsset(
  index: VaultIndex,
  target: string,
  sourceFilePath?: string,
): ResolvedVaultAsset | undefined {
  if (!isLocalAssetTarget(target)) return undefined;
  const cleanedTarget = cleanAssetTarget(target);
  const basename = assetBasename(cleanedTarget);
  if (!basename) return missingAsset(index, cleanedTarget || target);

  const candidates = index.assetCandidatesByName.get(basename.toLowerCase()) ?? [];
  if (candidates.length === 0) return missingAsset(index, basename);

  const selected = selectCandidate(index.root, candidates, cleanedTarget, sourceFilePath);
  if (!selected) {
    throw new Error(`Ambiguous vault asset "${basename}"`);
  }

  const outputName = outputNameForAsset(index, basename, selected, candidates.length > 1);
  registerResolvedAsset(index, outputName, selected);
  return { absolutePath: selected, outputName };
}

function extractAssetReferences(body: string): string[] {
  const references: string[] = [];
  const obsidianEmbed = /!\[\[([^\]]+)\]\]/g;
  let match: RegExpExecArray | null;

  while ((match = obsidianEmbed.exec(body)) !== null) {
    const target = match[1].split('|', 1)[0].trim();
    if (isLocalAssetTarget(target)) references.push(target);
  }

  const markdownImage = /!\[[^\]]*\]\(\s*(?:<([^>\r\n]+)>|([^\s)\r\n]+))(?:\s+(?:"[^"]*"|'[^']*'|\([^)]*\)))?\s*\)/g;
  while ((match = markdownImage.exec(body)) !== null) {
    const target = (match[1] ?? match[2] ?? '').trim();
    if (isLocalAssetTarget(target)) references.push(target);
  }

  return references;
}

function isLocalAssetTarget(target: string): boolean {
  const trimmed = target.trim();
  return (
    trimmed !== '' &&
    !/^https?:\/\//i.test(trimmed) &&
    !trimmed.startsWith('//') &&
    !/^data:/i.test(trimmed)
  );
}

function cleanAssetTarget(target: string): string {
  let cleaned = target.trim();
  if (cleaned.startsWith('<') && cleaned.endsWith('>')) cleaned = cleaned.slice(1, -1).trim();
  cleaned = cleaned.split(/[?#]/, 1)[0].trim();
  try {
    return decodeURIComponent(cleaned);
  } catch {
    return cleaned;
  }
}

function assetBasename(target: string): string {
  const cleaned = cleanAssetTarget(target).replace(/\\/g, '/');
  return path.posix.basename(cleaned);
}

function isSupportedAsset(filename: string): boolean {
  return SUPPORTED_ASSET_EXTENSIONS.has(path.extname(filename).toLowerCase());
}

function posixRelative(root: string, absolutePath: string): string {
  return path.relative(root, absolutePath).split(path.sep).join('/');
}

function selectCandidate(
  root: string,
  candidates: string[],
  target: string,
  sourceFilePath?: string,
): string | undefined {
  const normalizedTarget = target.replace(/[\\/]+/g, path.sep);
  const exactPaths: string[] = [];

  if (sourceFilePath) {
    exactPaths.push(path.resolve(path.dirname(path.resolve(sourceFilePath)), normalizedTarget));
  }

  const rootRelativeTarget = normalizedTarget.replace(/^[/\\]+/, '');
  exactPaths.push(path.resolve(root, rootRelativeTarget));

  for (const exactPath of exactPaths) {
    if (!isInside(root, exactPath)) continue;
    const exact = candidates.find((candidate) => path.resolve(candidate) === exactPath);
    if (exact) return exact;
  }

  if (sourceFilePath) {
    const sourceDirectory = path.dirname(path.resolve(sourceFilePath));
    const sameDirectory = candidates.filter(
      (candidate) => path.dirname(path.resolve(candidate)) === sourceDirectory,
    );
    if (sameDirectory.length === 1) return sameDirectory[0];
  }

  return candidates.length === 1 ? candidates[0] : undefined;
}

function isInside(root: string, candidate: string): boolean {
  const relative = path.relative(root, candidate);
  return (
    relative === '' ||
    (relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative))
  );
}

function outputNameForAsset(
  index: VaultIndex,
  originalName: string,
  absolutePath: string,
  disambiguate: boolean,
): string {
  const normalized = normalizeAssetName(originalName);
  if (!disambiguate) return normalized;

  const extension = path.extname(normalized);
  const stem = path.basename(normalized, extension);
  const contentHash = index.contentHashByPath.get(absolutePath);
  if (!contentHash) throw new Error(`Missing content hash for vault asset: ${absolutePath}`);
  return `${stem}-${contentHash.slice(0, 8)}${extension}`;
}

function registerResolvedAsset(index: VaultIndex, outputName: string, absolutePath: string): void {
  const existingPath = index.resolvedAssetsByOutputName.get(outputName);
  if (!existingPath) {
    index.resolvedAssetsByOutputName.set(outputName, absolutePath);
    return;
  }
  if (existingPath === absolutePath) return;

  const existingHash = index.contentHashByPath.get(existingPath);
  const incomingHash = index.contentHashByPath.get(absolutePath);
  if (!existingHash || !incomingHash || existingHash !== incomingHash) {
    throw new Error(`Vault asset output name collision: ${outputName}`);
  }
}

function missingAsset(index: VaultIndex, target: string): undefined {
  index.missingReferences.add(assetBasename(target) || target);
  return undefined;
}

/**
 * Normalize an asset filename for web output:
 *   "image 1.png"        -> "image-1.png"
 *   "截图_01.png"        -> "img-<hash>.png"
 *   "Capture.PNG"        -> "capture.png"
 */
export function normalizeAssetName(original: string): string {
  const ext = path.extname(original).toLowerCase();
  const stem = path.basename(original, path.extname(original));
  const isAllAscii = /^[\x20-\x7E]+$/.test(stem);
  let normalized: string;

  if (isAllAscii) {
    normalized = stem
      .toLowerCase()
      .replace(/[\s_]+/g, '-')
      .replace(/[^a-z0-9\-.]/g, '')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '');
  } else {
    normalized = `img-${hashStable(original)}`;
  }

  if (!normalized) normalized = 'file';
  return `${normalized}${ext || ''}`;
}

function hashStable(value: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index++) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}
