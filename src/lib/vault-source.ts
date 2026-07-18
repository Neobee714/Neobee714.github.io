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

function extractScalarFields(raw: string): Record<string, string> {
  const block = extractFrontmatter(raw);
  if (block === undefined) return {};

  const fields: Record<string, string> = {};
  for (const line of block.split(/\r?\n/)) {
    const match = line.match(/^([^\s:][^:]*?):\s*(.*)$/);
    if (match) fields[match[1].trim()] = match[2].trim();
  }
  return fields;
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

    const fields = extractScalarFields(raw);
    if (!hasPublishFlag(fields['发布'])) {
      unpublished++;
      continue;
    }
    if (isDraftStatus(fields['状态'])) {
      drafts++;
      continue;
    }

    const slug = normalizeFrontmatterScalar(fields['Slug']);
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
    } catch (cause) {
      throw new VaultSourceError(
        'INVALID_FRONTMATTER',
        `Invalid frontmatter in published note: ${candidate.relativePath}`,
        { cause },
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
