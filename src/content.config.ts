// Content Collections configuration.
//
// Points the `posts` collection at the Obsidian vault located via env var
// ASTRO_VAULT_PATH (e.g. `F:/Work/Obsidian` locally or `./vault` in CI).
//
// Implements:
//   - REQ-04-1 (field mapping, incl. Chinese keys)
//   - REQ-04-2 (flexible date parsing)
//   - REQ-04-3 (status semantics: 进行中 -> draft; 已锁住 -> locked)
//   - REQ-01-1 / 01-2 / 01-3 (scan all .md; only 发布:true)
//   - REQ-03-3 (missing Slug -> skipped with warning)

import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';
import { pathToFileURL } from 'node:url';
import { parseFlexDate } from './lib/date-parser.ts';
import { resolveVaultPath } from './lib/resolve-vault-path.ts';

// Resolve vault path from env. Fallback to `./vault` (CI checkout directory).
const vaultPathRaw = process.env.ASTRO_VAULT_PATH?.trim() || './vault';
const vaultAbsPath = resolveVaultPath(vaultPathRaw);

// Coerce "truthy-like" values into boolean. Accepts:
//   - real booleans
//   - "true" / "yes" / "是" / "y" / "1" / "locked"  -> true
//   - "false" / "no" / "否" / "n" / "0" / ""        -> false
const flexBool = z.preprocess((v) => {
  if (typeof v === 'boolean') return v;
  if (v === null || v === undefined) return false;
  if (typeof v === 'string') {
    const s = v.trim().toLowerCase();
    if (['true', 'yes', '是', 'y', '1', 'locked', '已锁住'].includes(s)) return true;
    if (['false', 'no', '否', 'n', '0', ''].includes(s)) return false;
  }
  return false;
}, z.boolean());

// Parse various date formats into a Date.
const flexDate = z.preprocess((v) => {
  const parsed = parseFlexDate(v);
  return parsed ?? undefined;
}, z.date().optional());

// Normalize tags: array or comma-separated string or empty.
const flexTags = z.preprocess((v) => {
  if (Array.isArray(v)) {
    return v.map((t) => String(t).trim()).filter(Boolean);
  }
  if (typeof v === 'string') {
    return v
      .split(/[,，;；\s]+/)
      .map((t) => t.trim())
      .filter(Boolean);
  }
  return [];
}, z.array(z.string()));

const postSchema = z.object({
  // --- Required for publishing ---
  Slug: z.string().min(1).optional(),
  发布: flexBool.optional().default(false),

  // --- Optional metadata ---
  是否锁住: flexBool.optional().default(false),
  日期: flexDate,
  类型: z.string().optional(),
  难度: z.string().optional(),
  操作系统: z.string().optional(),
  简介: z.string().optional().default(''),
  tags: flexTags.optional().default([]),
  状态: z.string().optional(),

  // --- Fields present on translated copies (`<slug>.en.md`) ---
  lang: z.enum(['zh', 'en']).optional(),
  source: z.string().optional(),
  source_hash: z.string().optional(),
  translated_at: z.string().optional(),
});

export type PostFrontmatter = z.infer<typeof postSchema>;

const posts = defineCollection({
  loader: glob({
    // Only scan notes inside SecNotes/. Root-level helper files like
    // `类型.md` (Obsidian syntax cheat sheet) and `copilot/` conversation
    // logs are excluded.
    pattern: [
      'SecNotes/**/*.md',
      'Translated/SecNotes/**/*.md',
      '!SecNotes/**/Templates/**',
      '!**/.obsidian/**',
      '!**/.trash/**',
    ],
    base: pathToFileURL(vaultAbsPath).href,
  }),
  schema: postSchema,
});

export const collections = { posts };
