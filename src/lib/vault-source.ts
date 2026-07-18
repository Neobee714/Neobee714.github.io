import { constants } from 'node:fs';
import { access, readFile, readdir, stat } from 'node:fs/promises';
import path from 'node:path';
import { extractFrontmatter, parseFrontmatter } from '@astrojs/markdown-remark';
import {
  hasPublishFlag,
  isDraftStatus,
  normalizeFrontmatterScalar,
} from './publishing.ts';

const EXCLUDED_DIRECTORIES = new Set([
  '.git',
  '.obsidian',
  '.trash',
  'node_modules',
  'Templates',
]);

export type VaultSourceErrorCode =
  | 'VAULT_UNAVAILABLE'
  | 'MISSING_SLUG'
  | 'DUPLICATE_SLUG'
  | 'INVALID_FRONTMATTER'
  | 'ENGLISH_ARTIFACT'
  | 'NO_POSTS';

export class VaultSourceError extends Error {
  readonly code: VaultSourceErrorCode;

  constructor(code: VaultSourceErrorCode, message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = 'VaultSourceError';
    this.code = code;
  }
}

export interface PublishedVaultPost {
  id: string;
  slug: string;
  absolutePath: string;
  relativePath: string;
  raw: string;
  body: string;
  frontmatter: Record<string, unknown>;
}

export interface VaultScanResult {
  posts: PublishedVaultPost[];
  stats: {
    markdown: number;
    published: number;
    drafts: number;
    unpublished: number;
    missingSlug: number;
  };
}

interface ClassifiedFile {
  absolutePath: string;
  relativePath: string;
  raw: string;
  slug: string;
}

export async function walkVaultFiles(root: string): Promise<string[]> {
  const files: string[] = [];

  async function walk(directory: string): Promise<void> {
    const entries = (await readdir(directory, { withFileTypes: true })).sort((a, b) =>
      a.name.localeCompare(b.name),
    );

    for (const entry of entries) {
      if (entry.isDirectory() && EXCLUDED_DIRECTORIES.has(entry.name)) continue;

      const absolutePath = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        await walk(absolutePath);
      } else if (entry.isFile()) {
        files.push(absolutePath);
      }
    }
  }

  await walk(path.resolve(root));
  return files.sort();
}

function toPosixRelative(root: string, absolutePath: string): string {
  return path.relative(root, absolutePath).split(path.sep).join('/');
}

type ClassificationField = '发布' | '状态' | 'Slug';

const CLASSIFICATION_FIELD = /^(?:"(发布|状态|Slug)"|'(发布|状态|Slug)'|(发布|状态|Slug))\s*:/;

function classificationFieldName(line: string): ClassificationField | undefined {
  const match = line.match(CLASSIFICATION_FIELD);
  return (match?.[1] ?? match?.[2] ?? match?.[3]) as ClassificationField | undefined;
}

function extractClassificationField(raw: string, field: ClassificationField): unknown {
  const block = extractFrontmatter(raw);
  if (block === undefined) return undefined;

  const lines = block.split(/\r?\n/);
  const selectedEntries: string[] = [];

  for (let index = 0; index < lines.length; index++) {
    if (classificationFieldName(lines[index]) !== field) continue;

    let end = index + 1;
    while (
      end < lines.length &&
      (lines[end].trim() === '' || /^\s/.test(lines[end]) || /^\s*#/.test(lines[end]))
    ) {
      end++;
    }
    selectedEntries.push(lines.slice(index, end).join('\n'));
    index = end - 1;
  }

  if (selectedEntries.length === 0) return undefined;
  const synthetic = `---\n${selectedEntries.join('\n')}\n---\n`;
  return parseFrontmatter(synthetic).frontmatter[field];
}

function readClassificationField(
  raw: string,
  field: ClassificationField,
  relativePath: string,
): unknown {
  try {
    return extractClassificationField(raw, field);
  } catch {
    throw new VaultSourceError(
      'INVALID_FRONTMATTER',
      `Invalid ${field} frontmatter in note: ${relativePath}`,
    );
  }
}

function isTextScalar(value: unknown): value is string | boolean {
  return typeof value === 'string' || typeof value === 'boolean';
}

export async function discoverPublishedPosts(root: string): Promise<VaultScanResult> {
  const absoluteRoot = path.resolve(root);
  let files: string[];

  try {
    if (!(await stat(absoluteRoot)).isDirectory()) throw new Error('Path is not a directory');
    await access(absoluteRoot, constants.R_OK);
    files = await walkVaultFiles(absoluteRoot);
  } catch (cause) {
    throw new VaultSourceError(
      'VAULT_UNAVAILABLE',
      `Vault is unavailable or unreadable: ${absoluteRoot}`,
      { cause },
    );
  }

  const markdownFiles = files.filter((file) => file.toLowerCase().endsWith('.md'));
  const englishArtifacts = markdownFiles
    .filter((file) => file.toLowerCase().endsWith('.en.md'))
    .map((file) => toPosixRelative(absoluteRoot, file));

  if (englishArtifacts.length > 0) {
    throw new VaultSourceError(
      'ENGLISH_ARTIFACT',
      `English Markdown artifacts are not allowed (${englishArtifacts.length}):\n${englishArtifacts.join('\n')}`,
    );
  }

  const candidates: ClassifiedFile[] = [];
  const missingSlug: string[] = [];
  let drafts = 0;
  let unpublished = 0;

  for (const absolutePath of markdownFiles) {
    const relativePath = toPosixRelative(absoluteRoot, absolutePath);
    let raw: string;
    try {
      raw = await readFile(absolutePath, 'utf8');
    } catch (cause) {
      throw new VaultSourceError(
        'VAULT_UNAVAILABLE',
        `Vault file is unavailable or unreadable: ${relativePath}`,
        { cause },
      );
    }

    const publishValue = readClassificationField(raw, '发布', relativePath);
    if (publishValue !== undefined && publishValue !== null && !isTextScalar(publishValue)) {
      throw new VaultSourceError(
        'INVALID_FRONTMATTER',
        `Invalid 发布 frontmatter type in note: ${relativePath}`,
      );
    }
    if (!hasPublishFlag(publishValue)) {
      unpublished++;
      continue;
    }

    const statusValue = readClassificationField(raw, '状态', relativePath);
    if (statusValue !== undefined && statusValue !== null && !isTextScalar(statusValue)) {
      throw new VaultSourceError(
        'INVALID_FRONTMATTER',
        `Invalid 状态 frontmatter type in note: ${relativePath}`,
      );
    }
    if (isDraftStatus(statusValue)) {
      drafts++;
      continue;
    }

    const slugValue = readClassificationField(raw, 'Slug', relativePath);
    if (slugValue !== undefined && slugValue !== null && typeof slugValue !== 'string') {
      throw new VaultSourceError(
        'INVALID_FRONTMATTER',
        `Invalid Slug frontmatter type in note: ${relativePath}`,
      );
    }
    const slug = normalizeFrontmatterScalar(slugValue);
    if (!slug) {
      missingSlug.push(relativePath);
      continue;
    }
    candidates.push({ absolutePath, relativePath, raw, slug });
  }

  if (missingSlug.length > 0) {
    throw new VaultSourceError(
      'MISSING_SLUG',
      `Published notes missing Slug (${missingSlug.length}):\n${missingSlug.join('\n')}`,
    );
  }

  const seenSlugs = new Map<string, string>();
  for (const candidate of candidates) {
    const prior = seenSlugs.get(candidate.slug);
    if (prior) {
      throw new VaultSourceError(
        'DUPLICATE_SLUG',
        `Duplicate published Slug "${candidate.slug}":\n${prior}\n${candidate.relativePath}`,
      );
    }
    seenSlugs.set(candidate.slug, candidate.relativePath);
  }

  const posts = candidates.map((candidate): PublishedVaultPost => {
    let parsed: ReturnType<typeof parseFrontmatter>;
    try {
      parsed = parseFrontmatter(candidate.raw);
    } catch {
      throw new VaultSourceError(
        'INVALID_FRONTMATTER',
        `Invalid frontmatter in published note: ${candidate.relativePath}`,
      );
    }

    return {
      id: candidate.relativePath.replace(/\.md$/i, ''),
      slug: candidate.slug,
      absolutePath: candidate.absolutePath,
      relativePath: candidate.relativePath,
      raw: candidate.raw,
      body: parsed.content,
      frontmatter: parsed.frontmatter,
    };
  });

  if (posts.length === 0) {
    throw new VaultSourceError('NO_POSTS', `Vault contains no publishable posts: ${absoluteRoot}`);
  }

  return {
    posts,
    stats: {
      markdown: markdownFiles.length,
      published: posts.length,
      drafts,
      unpublished,
      missingSlug: 0,
    },
  };
}
