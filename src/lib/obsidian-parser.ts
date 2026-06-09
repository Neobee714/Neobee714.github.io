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
import { isDraftStatus, isLockedStatus } from './publishing.ts';

export type Post = CollectionEntry<'posts'>;

interface PostIndex {
  published: Post[];
  publishedBySlug: Map<string, Post>;
  translationsBySlug: Map<string, Post>;
  translationsBySourceId: Map<string, Post>;
}

const CACHE_KEY = '__xyvora_post_index__';

type GlobalWithCache = typeof globalThis & {
  [CACHE_KEY]?: Promise<PostIndex>;
};

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
  return isLockedStatus(post.data.状态);
}

/**
 * Is this post publishable? (has 发布:true, has Slug, not draft)
 */
function isPublishable(post: Post): boolean {
  // 发布:true
  if (post.data.发布 !== true) return false;

  // Must have a Slug (REQ-03-3)
  if (!post.data.Slug || post.data.Slug.trim() === '') {
    return false;
  }
  // Status drafts are skipped even if 发布:true
  if (isDraftStatus(post.data.状态)) {
    return false;
  }

  return true;
}

async function getPostIndex() {
  const g = globalThis as GlobalWithCache;
  if (!g[CACHE_KEY]) {
    g[CACHE_KEY] = (async () => buildPostIndex(await getCollection('posts')))().catch((error) => {
      delete g[CACHE_KEY];
      throw error;
    });
  }
  return g[CACHE_KEY];
}

function buildPostIndex(all: Post[]): PostIndex {
  const published: Post[] = [];
  const publishedBySlug = new Map<string, Post>();
  const translationsBySlug = new Map<string, Post>();
  const translationsBySourceId = new Map<string, Post>();

  for (const post of all) {
    if (isTranslation(post)) {
      const slug = post.data.Slug?.trim();
      if (slug) {
        translationsBySlug.set(slug, post);
      }

      const sourceId = getTranslationSourceId(post);
      if (sourceId) {
        translationsBySourceId.set(sourceId, post);
      }
      continue;
    }

    if (!isPublishable(post)) continue;

    const slug = post.data.Slug!;
    const existing = publishedBySlug.get(slug);
    if (existing && existing !== post) {
      throw new Error(
        `[obsidian-parser] Duplicate Slug "${slug}" found in:\n` +
        `  - ${existing.id}\n` +
        `  - ${post.id}`
      );
    }

    publishedBySlug.set(slug, post);
    published.push(post);
  }

  published.sort((a, b) => {
    const da = a.data.日期?.getTime() ?? 0;
    const db = b.data.日期?.getTime() ?? 0;
    return db - da;
  });

  return {
    published,
    publishedBySlug,
    translationsBySlug,
    translationsBySourceId,
  };
}

function getTranslationSourceId(post: Post): string | undefined {
  const source = post.data.source?.trim();
  if (!source) return undefined;
  return normalizeNoteRef(source);
}

function getPostSourceId(post: Post): string {
  if (post.filePath) {
    return normalizeNoteRef(post.filePath);
  }
  return normalizeNoteRef(post.id);
}

function normalizeNoteRef(value: string): string {
  const normalized = value.replace(/\\/g, '/').split('/').pop() || value;
  return normalized.replace(/\.en\.md$/i, '').replace(/\.md$/i, '').trim().toLowerCase();
}

/**
 * Get all published posts (ORIGINALS ONLY — excludes .en.md translations).
 * Sorted by 日期 descending. Locked posts are included (they still show in
 * lists with the ACCESS DENIED banner on the detail page).
 */
export async function getPublishedPosts(): Promise<Post[]> {
  const index = await getPostIndex();
  return index.published;
}

/**
 * Look up a post (and its English translation, if any) by Slug.
 */
export async function getPostWithTranslation(
  slug: string
): Promise<{ zh: Post | undefined; en: Post | undefined }> {
  const index = await getPostIndex();
  const zh = index.publishedBySlug.get(slug);
  const en =
    index.translationsBySlug.get(slug) ||
    (zh ? index.translationsBySourceId.get(getPostSourceId(zh)) : undefined);

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

/**
 * Category display name mapping for SEO titles.
 * Maps internal 类型 values to human-readable platform names.
 */
const CATEGORY_DISPLAY_NAMES: Record<string, string> = {
  'HTB': 'HackTheBox',
  'MazeSec': 'MazeSec',
  'PWN': 'CTF PWN',
  'Web应用': 'Web Security',
  'PortSwigger': 'PortSwigger',
  '提权': 'Privilege Escalation',
  '方法论': 'Methodology',
  'PHP利用': 'PHP Exploitation',
};

export function getCategoryDisplayName(category: string): string {
  return CATEGORY_DISPLAY_NAMES[category] || category;
}

/**
 * Extract display title for a post.
 * Priority:
 *   1. First `# H1` heading from the markdown body (most reliable)
 *   2. Source note filename (without .md extension)
 *   3. Slugified post.id fallback
 */
export function getPostTitle(post: Post): string {
  // Priority 1: Extract first H1 from markdown body
  const body = post.body || '';
  const h1Match = body.match(/^#\s+(.+)$/m);
  if (h1Match) {
    return h1Match[1].trim();
  }

  // Priority 2: Source note filename
  const filePath = post.filePath;
  if (filePath) {
    const normalized = filePath.replace(/\\/g, '/');
    const filename = normalized.split('/').pop() || '';
    const title = filename.replace(/\.en\.md$/i, '').replace(/\.md$/i, '');
    if (title) return title;
  }

  // Priority 3: Slugified fallback
  const segments = post.id.replace(/\.md$/, '').split('/');
  return segments[segments.length - 1];
}
