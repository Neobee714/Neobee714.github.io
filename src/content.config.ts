import { defineCollection, z } from 'astro:content';
import { parseFlexDate } from './lib/date-parser.ts';
import { hasPublishFlag } from './lib/publishing.ts';
import { vaultLoader } from './lib/vault-loader.ts';

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
  Slug: z.string().trim().min(1),
  发布: z.preprocess(hasPublishFlag, z.literal(true)),
  是否锁住: flexBool.optional().default(false),
  日期: flexDate,
  类型: z.string().optional(),
  难度: z.string().optional(),
  操作系统: z.string().optional(),
  简介: z.string().optional().default(''),
  tags: flexTags.optional().default([]),
  状态: z.string().optional(),
});

export type PostFrontmatter = z.infer<typeof postSchema>;

const posts = defineCollection({
  loader: vaultLoader(process.env.ASTRO_VAULT_PATH?.trim() || './vault'),
  schema: postSchema,
});

export const collections = { posts };
