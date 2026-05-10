// Publishing pipeline: filter/sort/look-up published posts.
//
// Implements:
//   - REQ-01-2: only 发布:true posts are published
//   - REQ-01-3: missing 发布 -> treated as not-published
//   - REQ-02-1: locked posts still appear in lists/sitemap/RSS
//   - REQ-03-3: missing Slug -> skipped with a WARN log (stderr)
//   - REQ-04-3: status 进行中 -> draft (NOT published even if 发布:true)

import type { CollectionEntry } from 'astro:content';
import { getCollection } from 'astro:content';

export type Post = CollectionEntry<'posts'>;

// Status values that suppress publishing even when 发布:true.
// 状态值中若出现以下任意一种，文章被视为草稿（不发布）。
const DRAFT_STATUS_VALUES = new Set(['进行中', 'draft', 'wip', 'writing']);

// Status values that imply locked (synonymous with 是否锁住:Yes).
// 为了向后兼容 Notion 时代的 `状态: 已锁住` 值，这些值被视为锁住。
const LOCKED_STATUS_VALUES = new Set(['已锁住', 'locked']);

function normalizeStatus(raw: string | undefined): string {
  return (raw ?? '').trim().toLowerCase();
}

/**
 * Is this entry a translation artifact (e.g. `htb bruno.en.md`)?
 */
function isTranslation(post: Post): boolean {
  return post.data.lang === 'en' || post.id.endsWith('.en');
}

/**
 * Normalize "locked" state: accept `是否锁住:Yes` OR legacy `状态:已锁住`.
 */
export function isLocked(post: Post): boolean {
  if (post.data.是否锁住 === true) return true;
  const status = normalizeStatus(post.data.状态);
  return LOCKED_STATUS_VALUES.has(status);
}

/**
 * Is this post publishable? (has 发布:true, has Slug, not draft)
 */
function isPublishable(post: Post): boolean {
  // 发布:true
  if (post.data.发布 !== true) return false;

  // Must have a Slug (REQ-03-3)
  if (!post.data.Slug || post.data.Slug.trim() === '') {
    console.warn(
      `[obsidian-parser] Skipping post without Slug: ${post.id}`
    );
    return false;
  }

  // Status drafts are skipped even if 发布:true
  const status = normalizeStatus(post.data.状态);
  if (DRAFT_STATUS_VALUES.has(status)) {
    return false;
  }

  return true;
}

/**
 * Get all published posts (ORIGINALS ONLY — excludes .en.md translations).
 * Sorted by 日期 descending. Locked posts are included (they still show in
 * lists with the ACCESS DENIED banner on the detail page).
 */
export async function getPublishedPosts(): Promise<Post[]> {
  const all = await getCollection('posts');

  const originals = all.filter((p) => !isTranslation(p) && isPublishable(p));

  // Detect duplicate slugs — fail the build rather than silently drop posts.
  // (Hard failure implements REQ-03-4. Integration in Phase 2.5 will also
  // run this check more formally, but duplicating the guard here is cheap.)
  const seen = new Map<string, string>();
  for (const p of originals) {
    const slug = p.data.Slug!;
    const existing = seen.get(slug);
    if (existing && existing !== p.id) {
      throw new Error(
        `[obsidian-parser] Duplicate Slug "${slug}" found in:\n` +
        `  - ${existing}\n` +
        `  - ${p.id}`
      );
    }
    seen.set(slug, p.id);
  }

  originals.sort((a, b) => {
    const da = a.data.日期?.getTime() ?? 0;
    const db = b.data.日期?.getTime() ?? 0;
    return db - da;
  });

  return originals;
}

/**
 * Look up a post (and its English translation, if any) by Slug.
 */
export async function getPostWithTranslation(
  slug: string
): Promise<{ zh: Post | undefined; en: Post | undefined }> {
  const all = await getCollection('posts');

  const zh = all.find(
    (p) => !isTranslation(p) && p.data.Slug === slug && isPublishable(p)
  );

  // The translation's `source` field stores the original relative path;
  // we match via that when present, otherwise fall back to `Slug` alignment.
  const en = all.find((p) => {
    if (!isTranslation(p)) return false;
    if (p.data.Slug === slug) return true;
    if (p.data.source && zh && p.data.source.endsWith(zh.id + '.md')) return true;
    return false;
  });

  return { zh, en };
}

/**
 * Category extraction: "类型" field. Empty string means "uncategorized".
 */
export function getCategory(post: Post): string {
  return post.data.类型?.trim() || '';
}

/**
 * Format-stable ISO date (YYYY-MM-DD) for a post. Empty string if no date.
 */
export function getDateIso(post: Post): string {
  return post.data.日期 ? post.data.日期.toISOString().slice(0, 10) : '';
}
