# Vault Content Source Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Chinese post publishing independent of Obsidian directory layout, remove every active English-translation feature and artifact, and prevent invalid or empty builds from reaching the VPS.

**Architecture:** A pure vault discovery module scans technical-safe paths and selects posts by frontmatter. A custom Astro loader validates and renders only selected posts, primes a published-only wikilink/resource index, and fails closed on invalid publishing state. GitHub Actions remains the builder and deployer; the VPS continues serving only `dist/`.

**Tech Stack:** Astro 6 Content Collections, TypeScript, Node test runner, `@astrojs/markdown-remark`, Obsidian Markdown, GitHub Actions, rsync, Nginx.

---

## Working Boundaries

This implementation touches two repositories:

- Blog: `/mnt/hgfs/Work/Program/Python/blog`
- Vault: `/mnt/hgfs/Work/Obsidian`

The blog repository starts clean apart from this plan document and the approved-status line in the design document. The vault has a large pre-existing directory migration in progress. Never stage or revert unrelated vault changes. In the vault, stage only tracked `*.en.md` deletions and `.github/workflows/notify.yml`.

Do not push either repository and do not deploy to the VPS during implementation. The existing GitHub workflow will deploy after the user later pushes approved commits.

Do not print `git remote -v` during execution: the local blog remote currently contains an embedded credential. Replacing the remote URL and rotating that credential are separate security follow-ups, not translation-refactor changes.

## File Map

### New blog files

- `src/lib/vault-source.ts`: technical-safe traversal, lightweight publish classification, structured frontmatter parsing, duplicate/zero/English-artifact validation.
- `src/lib/vault-loader.ts`: Astro Loader adapter, schema parsing, Markdown rendering, watcher reloads, index priming.
- `tests/vault-source.test.ts`: temporary-vault behavioral tests.
- `tests/vault-loader.test.ts`: loader/store adapter tests.
- `tests/vault-index.test.ts`: published-only resource resolution tests.

### Modified blog files

- `src/content.config.ts`: use the custom loader and remove translation schema fields.
- `src/lib/publishing.ts`: shared publish-value/status normalization.
- `src/lib/vault-index.ts`: accept discovered posts, index only referenced resource names, detect ambiguity.
- `src/lib/remark-wikilink.ts`: resolve embeds with source-file context.
- `src/lib/rehype-image-rewrite.ts`: resolve Markdown images with source-file context.
- `src/lib/integrations/copy-vault-images.ts`: copy by registered output name instead of `alt`.
- `astro.config.mjs`: remove the duplicate Slug integration.
- `src/lib/obsidian-parser.ts`: keep only the Chinese published index.
- `src/components/Header.astro`: remove language toggle.
- `src/components/Homepage.astro`: remove translation lookup and bilingual spans.
- `src/components/PostCard.astro`: remove translation prop and English content.
- `src/components/FeaturedPost.astro`: remove translation prop and English content.
- `src/components/TableOfContents.astro`: use one Chinese heading list.
- `src/components/LockedBanner.astro`: keep Chinese copy only.
- `src/components/CodeBlockWrapper.astro`: use one Chinese expand label.
- `src/layouts/PostLayout.astro`: remove English post/headings props and bilingual metadata.
- `src/layouts/BaseLayout.astro`: remove `data-lang`.
- `src/pages/post/[slug].astro`: render one Chinese post.
- `src/pages/about.astro`, `src/pages/404.astro`, `src/pages/archives.astro`, `src/pages/categories/index.astro`, `src/pages/tags/index.astro`: remove bilingual wrappers and keep Chinese copy.
- `src/styles/global.css`: remove language visibility selectors.
- `src/lib/theme-init.ts`: initialize theme only.
- `tests/source-safety.test.ts`: assert translation functionality is absent.
- `package.json`, `package-lock.json`: add direct Markdown parser dependency, remove Python test command.
- `.github/workflows/build.yml`: remove translation/Python/vault-write steps.
- `README.md`, `.kiro/steering/project-context.md`: document Chinese-only frontmatter discovery.
- `.env` (ignored local file): remove obsolete `VAULT_PUSH_TOKEN` and `LLM_*` keys without staging the file.

### Deleted blog files

- `src/components/LangToggle.astro`
- `src/lib/integrations/slug-check.ts`
- `scripts/` and all translation-only Python files
- `tests/test_translation_paths.py`
- `tests/test_codeblocks.py`

### Modified/deleted vault files

- Modify `.github/workflows/notify.yml` to listen to all Markdown changes.
- Delete every current `*.en.md`, including untracked files under `50-Published/Translated/`.

---

### Task 1: Published Vault Discovery Core

**Files:**
- Create: `tests/vault-source.test.ts`
- Create: `src/lib/vault-source.ts`
- Modify: `src/lib/publishing.ts`
- Modify: `package.json`
- Modify: `package-lock.json`

- [ ] **Step 1: Add the direct Markdown frontmatter parser dependency**

Run:

```bash
npm install --save-dev @astrojs/markdown-remark@^7.1.1
```

Expected: `package.json` lists `@astrojs/markdown-remark` in `devDependencies`; `npm ls @astrojs/markdown-remark` exits 0.

- [ ] **Step 2: Write failing discovery tests**

Create `tests/vault-source.test.ts` with temporary-vault tests using this shape:

```ts
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, rename, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {
  discoverPublishedPosts,
  VaultSourceError,
} from '../src/lib/vault-source.ts';

async function withVault(run: (root: string) => Promise<void>) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'xyvora-vault-'));
  try {
    await run(root);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

async function note(root: string, relative: string, frontmatter: string, body = '# Demo') {
  const target = path.join(root, relative);
  await mkdir(path.dirname(target), { recursive: true });
  await writeFile(target, `---\n${frontmatter}\n---\n${body}\n`, 'utf8');
}

test('discovers a published post in an arbitrary nested directory', async () => {
  await withVault(async (root) => {
    await note(root, '40-Career/moved/demo.md', '发布: true\nSlug: stable-demo');
    const result = await discoverPublishedPosts(root);
    assert.equal(result.posts.length, 1);
    assert.equal(result.posts[0].slug, 'stable-demo');
    assert.equal(result.posts[0].relativePath, '40-Career/moved/demo.md');
  });
});

test('keeps the public Slug stable after the source file moves', async () => {
  await withVault(async (root) => {
    await note(root, 'old/location/demo.md', '发布: true\nSlug: stable-demo');
    const before = await discoverPublishedPosts(root);
    await mkdir(path.join(root, 'new/location'), { recursive: true });
    await rename(
      path.join(root, 'old/location/demo.md'),
      path.join(root, 'new/location/demo.md')
    );
    const after = await discoverPublishedPosts(root);
    assert.equal(before.posts[0].slug, 'stable-demo');
    assert.equal(after.posts[0].slug, 'stable-demo');
    assert.notEqual(before.posts[0].relativePath, after.posts[0].relativePath);
  });
});

test('skips unpublished notes, drafts, templates and technical directories', async () => {
  await withVault(async (root) => {
    await note(root, 'private.md', '发布: false\nSlug: private');
    await note(root, 'draft.md', '发布: true\nSlug: draft\n状态: writing');
    await note(root, 'Templates/template.md', '发布: true\nSlug: template');
    await note(root, '.trash/old.md', '发布: true\nSlug: old');
    await note(root, 'live.md', '发布: 是\nSlug: live');
    await note(root, 'locked.md', '发布: yes\nSlug: locked\n状态: 已锁住');
    const result = await discoverPublishedPosts(root);
    assert.deepEqual(result.posts.map((post) => post.slug), ['live', 'locked']);
  });
});

test('fails when the vault root is unavailable', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'xyvora-missing-vault-'));
  await rm(root, { recursive: true, force: true });
  await assert.rejects(
    discoverPublishedPosts(root),
    (error: unknown) =>
      error instanceof VaultSourceError && error.code === 'VAULT_UNAVAILABLE'
  );
});

test('fails for published notes without Slug', async () => {
  await withVault(async (root) => {
    await note(root, 'broken.md', '发布: true');
    await assert.rejects(
      discoverPublishedPosts(root),
      (error: unknown) => error instanceof VaultSourceError && error.code === 'MISSING_SLUG'
    );
  });
});

test('fails for duplicate published Slugs', async () => {
  await withVault(async (root) => {
    await note(root, 'a.md', '发布: true\nSlug: duplicate');
    await note(root, 'nested/b.md', '发布: true\nSlug: duplicate');
    await assert.rejects(
      discoverPublishedPosts(root),
      (error: unknown) => error instanceof VaultSourceError && error.code === 'DUPLICATE_SLUG'
    );
  });
});

test('fails when no publishable posts exist', async () => {
  await withVault(async (root) => {
    await note(root, 'private.md', '发布: false\nSlug: private');
    await assert.rejects(
      discoverPublishedPosts(root),
      (error: unknown) => error instanceof VaultSourceError && error.code === 'NO_POSTS'
    );
  });
});

test('fails when an English artifact exists in the effective scan scope', async () => {
  await withVault(async (root) => {
    await note(root, 'live.md', '发布: true\nSlug: live');
    await note(root, 'Translated/live.en.md', '发布: true\nSlug: live\nlang: en');
    await assert.rejects(
      discoverPublishedPosts(root),
      (error: unknown) => error instanceof VaultSourceError && error.code === 'ENGLISH_ARTIFACT'
    );
  });
});

test('fails when a published note has invalid YAML frontmatter', async () => {
  await withVault(async (root) => {
    await writeFile(
      path.join(root, 'broken.md'),
      '---\n发布: true\nSlug: [broken\n---\n# Broken\n',
      'utf8'
    );
    await assert.rejects(
      discoverPublishedPosts(root),
      (error: unknown) =>
        error instanceof VaultSourceError && error.code === 'INVALID_FRONTMATTER'
    );
  });
});
```

- [ ] **Step 3: Run the tests and confirm the missing-module failure**

Run:

```bash
node --import tsx --test tests/vault-source.test.ts
```

Expected: FAIL because `src/lib/vault-source.ts` does not exist.

- [ ] **Step 4: Extend shared publishing normalization**

In `src/lib/publishing.ts`, keep existing draft/locked behavior and add these exact public helpers:

```ts
export function normalizeFrontmatterScalar(raw: unknown): string {
  const value = String(raw ?? '').trim();
  if (value.length >= 2) {
    const first = value[0];
    const last = value[value.length - 1];
    if ((first === '"' && last === '"') || (first === "'" && last === "'")) {
      return value.slice(1, -1).trim();
    }
  }
  return value;
}

export function hasPublishFlag(raw: unknown): boolean {
  if (raw === true) return true;
  return ['true', 'yes', '是'].includes(normalizeFrontmatterScalar(raw).toLowerCase());
}
```

Update `normalizeStatus`, `isDraftStatus`, and `isLockedStatus` parameters from `string | undefined | null` to `unknown` so loader and schema consumers share one contract.

- [ ] **Step 5: Implement the pure discovery module**

Create `src/lib/vault-source.ts` with these exported types and behavior:

```ts
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { extractFrontmatter, parseFrontmatter } from '@astrojs/markdown-remark';
import { hasPublishFlag, isDraftStatus, normalizeFrontmatterScalar } from './publishing.ts';

export type VaultSourceErrorCode =
  | 'VAULT_UNAVAILABLE'
  | 'MISSING_SLUG'
  | 'DUPLICATE_SLUG'
  | 'INVALID_FRONTMATTER'
  | 'ENGLISH_ARTIFACT'
  | 'NO_POSTS';

export class VaultSourceError extends Error {
  constructor(public readonly code: VaultSourceErrorCode, message: string) {
    super(message);
    this.name = 'VaultSourceError';
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

const EXCLUDED_DIRS = new Set(['.git', '.obsidian', '.trash', 'node_modules', 'Templates']);

function toPosix(value: string): string {
  return value.split(path.sep).join('/');
}

function scalarFrontmatter(raw: string): Record<string, string> | null {
  const block = extractFrontmatter(raw);
  if (block === undefined) return null;
  const fields: Record<string, string> = {};
  for (const line of block.split(/\r?\n/)) {
    const match = line.match(/^([^\s:][^:]*?):\s*(.*)$/);
    if (match) fields[match[1].trim()] = match[2].trim();
  }
  return fields;
}

export async function walkVaultFiles(root: string): Promise<string[]> {
  const files: string[] = [];
  async function walk(dir: string): Promise<void> {
    const entries = await fs.readdir(dir, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.isDirectory() && EXCLUDED_DIRS.has(entry.name)) continue;
      const absolute = path.join(dir, entry.name);
      if (entry.isDirectory()) await walk(absolute);
      else if (entry.isFile()) files.push(absolute);
    }
  }
  await walk(root);
  return files.sort((a, b) => a.localeCompare(b));
}

export async function discoverPublishedPosts(root: string): Promise<VaultScanResult> {
  let stat;
  try {
    stat = await fs.stat(root);
  } catch {
    throw new VaultSourceError('VAULT_UNAVAILABLE', `Vault path is not accessible: ${root}`);
  }
  if (!stat.isDirectory()) {
    throw new VaultSourceError('VAULT_UNAVAILABLE', `Vault path is not a directory: ${root}`);
  }

  let files: string[];
  try {
    files = await walkVaultFiles(root);
  } catch (error) {
    throw new VaultSourceError(
      'VAULT_UNAVAILABLE',
      `Vault cannot be read: ${root}: ${error instanceof Error ? error.message : String(error)}`
    );
  }
  const markdown = files.filter((file) => file.toLowerCase().endsWith('.md'));
  const english = markdown.filter((file) => file.toLowerCase().endsWith('.en.md'));
  if (english.length > 0) {
    throw new VaultSourceError(
      'ENGLISH_ARTIFACT',
      `English translation artifacts are unsupported: ${english.map((file) => toPosix(path.relative(root, file))).join(', ')}`
    );
  }

  const posts: PublishedVaultPost[] = [];
  const seen = new Map<string, string>();
  const missingSlugs: string[] = [];
  let drafts = 0;
  let unpublished = 0;

  for (const absolutePath of markdown) {
    const raw = await fs.readFile(absolutePath, 'utf8');
    const scalar = scalarFrontmatter(raw);
    if (!scalar || !hasPublishFlag(scalar['发布'])) {
      unpublished++;
      continue;
    }
    if (isDraftStatus(scalar['状态'])) {
      drafts++;
      continue;
    }
    const slug = normalizeFrontmatterScalar(scalar['Slug']);
    const relativePath = toPosix(path.relative(root, absolutePath));
    if (!slug) {
      missingSlugs.push(relativePath);
      continue;
    }
    const prior = seen.get(slug);
    if (prior) {
      throw new VaultSourceError('DUPLICATE_SLUG', `Duplicate Slug "${slug}": ${prior}, ${relativePath}`);
    }

    let parsed;
    try {
      parsed = parseFrontmatter(raw);
    } catch (error) {
      throw new VaultSourceError(
        'INVALID_FRONTMATTER',
        `Invalid frontmatter in ${relativePath}: ${error instanceof Error ? error.message : String(error)}`
      );
    }
    seen.set(slug, relativePath);
    posts.push({
      id: relativePath.replace(/\.md$/i, ''),
      slug,
      absolutePath,
      relativePath,
      raw,
      body: parsed.content,
      frontmatter: parsed.frontmatter,
    });
  }

  if (missingSlugs.length > 0) {
    throw new VaultSourceError(
      'MISSING_SLUG',
      `Published notes missing Slug: ${missingSlugs.length}; ${missingSlugs.join(', ')}`
    );
  }

  if (posts.length === 0) {
    throw new VaultSourceError('NO_POSTS', `No publishable posts found in ${root}`);
  }

  return {
    posts,
    stats: {
      markdown: markdown.length,
      published: posts.length,
      drafts,
      unpublished,
      missingSlug: 0,
    },
  };
}
```

The `MISSING_SLUG` error message contains the exact count and relative paths. This is the failed-build form of the missing-Slug count; successful scan summaries report `missing Slug: 0`.

- [ ] **Step 6: Run focused and full tests**

Run:

```bash
node --import tsx --test tests/vault-source.test.ts
npm test
```

Expected: the new discovery tests and the full existing suite PASS.

- [ ] **Step 7: Commit the discovery core**

```bash
git add package.json package-lock.json src/lib/publishing.ts src/lib/vault-source.ts tests/vault-source.test.ts
git commit -m "feat: discover published vault posts by metadata"
```

---

### Task 2: Custom Astro Loader and Fail-Closed Content Collection

**Files:**
- Create: `src/lib/vault-loader.ts`
- Create: `tests/vault-loader.test.ts`
- Modify: `src/content.config.ts`
- Modify: `astro.config.mjs`
- Delete: `src/lib/integrations/slug-check.ts`
- Modify: `tests/source-safety.test.ts`

- [ ] **Step 1: Write a failing loader adapter test**

Create `tests/vault-loader.test.ts` with a temporary vault and a complete fake `LoaderContext`:

```ts
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import type { DataStore, LoaderContext } from 'astro/loaders';
import { vaultLoader } from '../src/lib/vault-loader.ts';

test('loads validated vault posts into the Astro data store', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'xyvora-loader-'));
  try {
    const target = path.join(root, 'nested/demo.md');
    await mkdir(path.dirname(target), { recursive: true });
    await writeFile(
      target,
      '---\n发布: true\nSlug: demo\n简介: Summary\n---\n# Demo\n',
      'utf8'
    );

    const entries = new Map<string, any>();
    const store: DataStore = {
      get: (key) => entries.get(key),
      entries: () => [...entries.entries()],
      set: (entry) => (entries.set(entry.id, entry), true),
      values: () => [...entries.values()],
      keys: () => [...entries.keys()],
      delete: (key) => void entries.delete(key),
      clear: () => entries.clear(),
      has: (key) => entries.has(key),
      addModuleImport: () => {},
    };
    const meta = new Map<string, string>();
    const siteRoot = path.join(root, 'site');
    const context = {
      collection: 'posts',
      store,
      meta: {
        get: (key: string) => meta.get(key),
        set: (key: string, value: string) => void meta.set(key, value),
        has: (key: string) => meta.has(key),
        delete: (key: string) => void meta.delete(key),
      },
      logger: { info() {}, warn() {}, error() {}, debug() {} },
      config: { root: pathToFileURL(`${siteRoot}${path.sep}`) },
      parseData: async ({ data }: { data: Record<string, unknown> }) => data,
      renderMarkdown: async () => ({ html: '<h1>Demo</h1>' }),
      generateDigest: () => 'digest',
    } as unknown as LoaderContext;

    await vaultLoader(root).load(context);

    assert.equal(entries.size, 1);
    const entry = entries.get('nested/demo');
    assert.equal(entry.data.Slug, 'demo');
    assert.match(entry.body, /# Demo/);
    assert.equal(entry.digest, 'digest');
    assert.match(entry.rendered.html, /<h1>Demo<\/h1>/);
    assert.equal(entry.filePath.endsWith('nested/demo.md'), true);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
```

- [ ] **Step 2: Run the loader test and verify it fails**

```bash
node --import tsx --test tests/vault-loader.test.ts
```

Expected: FAIL because `src/lib/vault-loader.ts` does not exist.

- [ ] **Step 3: Implement the Astro loader adapter**

Create `src/lib/vault-loader.ts` with this contract:

```ts
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import type { Loader, LoaderContext } from 'astro/loaders';
import { discoverPublishedPosts } from './vault-source.ts';
import { resolveVaultPath } from './resolve-vault-path.ts';

function toPosix(value: string): string {
  return value.split(path.sep).join('/');
}

export function vaultLoader(rawPath?: string): Loader {
  return {
    name: 'xyvora-vault-loader',
    async load(context) {
      const root = resolveVaultPath(rawPath);
      const sync = () => syncVault(root, context);
      await sync();

      if (context.watcher) {
        context.watcher.add(root);
        const reload = async (changedPath: string) => {
          const relative = path.relative(root, changedPath);
          if (relative.startsWith('..') || path.isAbsolute(relative)) return;
          try {
            await sync();
            context.logger.info(`Reloaded vault after ${toPosix(relative)}`);
          } catch (error) {
            context.logger.error(error instanceof Error ? error.message : String(error));
          }
        };
        context.watcher.on('add', reload);
        context.watcher.on('change', reload);
        context.watcher.on('unlink', reload);
      }
    },
  };
}

async function syncVault(root: string, context: LoaderContext): Promise<void> {
  const result = await discoverPublishedPosts(root);
  const siteRoot = fileURLToPath(context.config.root);
  context.store.clear();

  for (const post of result.posts) {
    const data = await context.parseData({
      id: post.id,
      data: post.frontmatter,
      filePath: post.absolutePath,
    });
    const rendered = await context.renderMarkdown(post.raw, {
      fileURL: pathToFileURL(post.absolutePath),
    });
    context.store.set({
      id: post.id,
      data,
      body: post.body,
      filePath: toPosix(path.relative(siteRoot, post.absolutePath)),
      digest: context.generateDigest(post.raw),
      rendered,
    });
  }

  context.logger.info(
    `Vault scan: ${result.stats.markdown} markdown, ${result.stats.published} published, ` +
      `${result.stats.drafts} drafts, ${result.stats.unpublished} unpublished, ` +
      `${result.stats.missingSlug} missing Slug`
  );
}
```

Task 3 will insert resource-index priming before the render loop.

Keep a closure-local `watchersAttached` flag so repeated `load()` calls do not register duplicate listeners. Debounce add/change/unlink events for 50 ms and serialize full rescans through one promise; watcher failures are logged, while the initial `load()` failure is allowed to reject and stop the build.

- [ ] **Step 4: Switch the content collection to the loader**

In `src/content.config.ts`:

- Remove `glob`, `pathToFileURL`, vault path resolution, and every translation field.
- Make `Slug` and `发布` required for entries reaching the collection.
- Configure the collection as:

```ts
const posts = defineCollection({
  loader: vaultLoader(process.env.ASTRO_VAULT_PATH?.trim() || './vault'),
  schema: postSchema,
});
```

Use `hasPublishFlag` from `publishing.ts` to define the strict published-entry field:

```ts
const publishFlag = z.preprocess((value) => hasPublishFlag(value), z.literal(true));

const postSchema = z.object({
  Slug: z.string().trim().min(1),
  发布: publishFlag,
  是否锁住: flexBool.optional().default(false),
  日期: flexDate,
  类型: z.string().optional(),
  难度: z.string().optional(),
  操作系统: z.string().optional(),
  简介: z.string().optional().default(''),
  tags: flexTags.optional().default([]),
  状态: z.string().optional(),
});
```

These are the complete schema fields after cleanup; there are no translation metadata fields.

- [ ] **Step 5: Remove duplicate Slug integration**

Delete `src/lib/integrations/slug-check.ts`. Remove its import and `slugUniquenessCheck()` entry from `astro.config.mjs`. Update `tests/source-safety.test.ts` so publish-rule tests import helpers from `src/lib/publishing.ts` or exercise `discoverPublishedPosts` instead of importing `isPublishedFm`.

- [ ] **Step 6: Run focused loader and safety tests**

```bash
node --import tsx --test tests/vault-source.test.ts tests/vault-loader.test.ts tests/source-safety.test.ts
```

Expected: PASS. Do not run against the real vault yet because real `.en.md` files are intentionally rejected until Task 6.

- [ ] **Step 7: Commit the loader**

```bash
git add astro.config.mjs src/content.config.ts src/lib/vault-loader.ts tests/vault-loader.test.ts tests/source-safety.test.ts
git add -u src/lib/integrations/slug-check.ts
git commit -m "feat: load vault posts through validated metadata"
```

---

### Task 3: Published-Only Wikilink and Asset Index

**Files:**
- Create: `tests/vault-index.test.ts`
- Modify: `src/lib/vault-index.ts`
- Modify: `src/lib/vault-loader.ts`
- Modify: `src/lib/remark-wikilink.ts`
- Modify: `src/lib/rehype-image-rewrite.ts`
- Modify: `src/lib/integrations/copy-vault-images.ts`
- Modify: `tests/source-safety.test.ts`

- [ ] **Step 1: Write failing resource-index tests**

Create `tests/vault-index.test.ts` with a published post at `articles/demo.md` whose body contains `![[used.png]]`, `![[./assets/local.png]]`, and `![[duplicate.png]]`. Add:

- `assets/used.png`
- `articles/assets/local.png`
- `a/duplicate.png` and `b/duplicate.png` with different contents
- an unpublished note referencing `private/unused-private.png`

Call `discoverPublishedPosts(root)`, then `buildVaultIndex(root, result.posts)`, and make these exact assertions:

```ts
assert.equal(index.notesByName.get('demo'), 'demo-slug');
assert.equal(index.assetCandidatesByName.has('unused-private.png'), false);
assert.equal(resolveVaultAsset(index, 'used.png', publishedFile)?.absolutePath, usedPath);
assert.equal(resolveVaultAsset(index, './assets/local.png', publishedFile)?.absolutePath, localPath);
assert.throws(
  () => resolveVaultAsset(index, 'duplicate.png', publishedFile),
  /Ambiguous vault asset/
);
const disambiguated = resolveVaultAsset(index, '../a/duplicate.png', publishedFile);
assert.match(disambiguated?.outputName ?? '', /^duplicate-[a-f0-9]{8}\.png$/);
```

Also assert that an `https://`, protocol-relative or `data:` Markdown image is never added to `assetCandidatesByName`.

- [ ] **Step 2: Run the resource tests and verify failure**

```bash
node --import tsx --test tests/vault-index.test.ts
```

Expected: FAIL because `buildVaultIndex` and `resolveVaultAsset` do not exist.

- [ ] **Step 3: Replace the global full-vault index with a primed index**

Refactor `src/lib/vault-index.ts` to export:

```ts
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

export async function buildVaultIndex(
  root: string,
  posts: PublishedVaultPost[]
): Promise<VaultIndex>;

export function primeVaultIndex(index: VaultIndex): void;
export function getVaultIndex(): VaultIndex;
export function resolveVaultAsset(
  index: VaultIndex,
  target: string,
  sourceFilePath?: string
): ResolvedVaultAsset | undefined;
```

Implementation requirements:

- Build `notesByName` only from `posts`.
- Extract referenced image/resource basenames from `![[...]]` and Markdown `![](...)` in published bodies. Strip Obsidian size aliases, URL query strings and fragments before lookup.
- Ignore `http:`, `https:`, protocol-relative and `data:` targets.
- Walk vault file names but retain candidates only for extracted basenames.
- Precompute SHA-256 for retained candidates in `contentHashByPath`; do not read unrelated resource contents.
- Resolve an exact relative target first, then a same-directory candidate, then a single global candidate.
- Throw `Ambiguous vault asset "name"` when multiple candidates remain.
- Preserve the existing normalized name for unique basenames.
- If a duplicated basename is resolved by relative location, append the first eight SHA-256 characters of file contents before the extension so output names remain stable when the source file moves.
- Register every successful result in `resolvedAssetsByOutputName`; if the same output name points to different content, throw.
- Register unresolved local targets in `missingReferences` so the build summary can report them without logging private note bodies.
- `getVaultIndex()` must throw `Vault index was not primed` instead of silently rescanning the entire vault.

- [ ] **Step 4: Prime the index before Markdown rendering**

In `syncVault()` inside `src/lib/vault-loader.ts`, add before `context.store.clear()`:

```ts
const index = await buildVaultIndex(root, result.posts);
primeVaultIndex(index);
```

This guarantees remark and rehype plugins see only the current validated publication set.

- [ ] **Step 5: Resolve wikilink embeds with source context**

Change `remarkWikilink` to use the transformer signature `(tree, file)`. Pass `typeof file.path === 'string' ? file.path : undefined` into `buildEmbed`. Replace direct `assetsByName` lookup with:

```ts
const resolved = resolveVaultAsset(idx, target, sourcePath);
if (!resolved) {
  return missingImage(target);
}
const src = `/_images/${resolved.outputName}`;
```

Keep published note wikilinks based on `notesByName`. Remove `unpublishedNames` and use one broken-link message for unresolved note targets.

- [ ] **Step 6: Resolve Markdown images with source context**

Change `rehypeImageRewrite` to use `(tree, file)`. Replace basename lookup with:

```ts
const resolved = resolveVaultAsset(
  idx,
  originalName,
  typeof file.path === 'string' ? file.path : undefined
);
```

Use `resolved.outputName` for `props.src` and `resolved.absolutePath` for the existing dev copy. Missing resources still become the visible placeholder.

- [ ] **Step 7: Copy production assets directly from the resolved registry**

In `copy-vault-images.ts`, remove HTML scanning and `alt`-based lookup. During `astro:build:done`, iterate only the assets that remark/rehype successfully registered:

```ts
for (const [outputName, vaultAbsPath] of idx.resolvedAssetsByOutputName) {
  await fs.mkdir(imagesOutDir, { recursive: true });
  await fs.copyFile(vaultAbsPath, path.join(imagesOutDir, outputName));
}
logger.info(
  `Copied ${idx.resolvedAssetsByOutputName.size} published assets; ` +
    `${idx.missingReferences.size} missing references`
);
```

Add `astro:build:start` to remove only the generated `public/_images` directory before Astro copies `public/`, preventing stale dev assets from leaking into `dist`:

```ts
'astro:build:start': async () => {
  await fs.rm(path.resolve('public', '_images'), { recursive: true, force: true });
},
```

This copies image and non-image embeds such as PDFs, and cannot copy an unreferenced private asset. Update the existing source-safety assertion to require iteration over `resolvedAssetsByOutputName` and forbid `walkAndProcessHtml`, `assetsByName`, and `attrs.alt` in this integration.

- [ ] **Step 8: Run resource, Markdown and safety tests**

```bash
node --import tsx --test tests/vault-index.test.ts tests/remark-highlight.test.ts tests/source-safety.test.ts
npm test
```

Expected: PASS, with no full-vault resource fallback.

- [ ] **Step 9: Commit resource isolation**

```bash
git add src/lib/vault-index.ts src/lib/vault-loader.ts src/lib/remark-wikilink.ts src/lib/rehype-image-rewrite.ts src/lib/integrations/copy-vault-images.ts tests/vault-index.test.ts tests/source-safety.test.ts
git commit -m "fix: isolate published vault resources"
```

---

### Task 4: Remove Translation Behavior from the Blog UI

**Files:**
- Modify: `tests/source-safety.test.ts`
- Delete: `src/components/LangToggle.astro`
- Modify: all UI/layout/page files listed in the File Map
- Modify: `src/lib/obsidian-parser.ts`
- Modify: `src/styles/global.css`
- Modify: `src/lib/theme-init.ts`

- [ ] **Step 1: Replace positive translation tests with failing absence tests**

Add a test that reads active source files and asserts:

```ts
test('English translation feature is absent from active source', () => {
  assert.equal(existsSync('src/components/LangToggle.astro'), false);
  const files = [
    'src/components/Header.astro',
    'src/components/Homepage.astro',
    'src/components/PostCard.astro',
    'src/components/FeaturedPost.astro',
    'src/components/TableOfContents.astro',
    'src/components/LockedBanner.astro',
    'src/components/CodeBlockWrapper.astro',
    'src/layouts/PostLayout.astro',
    'src/layouts/BaseLayout.astro',
    'src/pages/post/[slug].astro',
    'src/pages/about.astro',
    'src/pages/404.astro',
    'src/pages/archives.astro',
    'src/pages/categories/index.astro',
    'src/pages/tags/index.astro',
    'src/lib/obsidian-parser.ts',
    'src/lib/theme-init.ts',
    'src/styles/global.css',
  ];
  const source = files.map((file) => readFileSync(file, 'utf8')).join('\n');
  assert.doesNotMatch(source, /lang-en|lang-zh|data-lang|LangToggle/);
  assert.doesNotMatch(source, /getPostWithTranslation|translationsBySlug|postEn|headingsEn/);
});
```

Remove old assertions that require LangToggle and translation maps.

- [ ] **Step 2: Run the safety test and verify failure**

```bash
node --import tsx --test tests/source-safety.test.ts
```

Expected: FAIL because translation code still exists.

- [ ] **Step 3: Simplify the data index and article rendering**

In `obsidian-parser.ts`, make `PostIndex` contain only `published` and `publishedBySlug`; remove translation detection, source normalization and `getPostWithTranslation`.

Replace `src/pages/post/[slug].astro` rendering with one content component:

```astro
const { Content, headings } = await render(post);
const hasMermaid = !locked && (post.body || '').toLowerCase().includes(mermaidFence);
---
<PostLayout post={post} headings={headings} hasMermaid={hasMermaid}>
  {locked ? <LockedBanner /> : <Content />}
</PostLayout>
```

In `PostLayout.astro`, keep props `post`, `headings`, and `hasMermaid`; render `titleZh` and `summaryZh` directly; pass one `headings` array to `TableOfContents`.

- [ ] **Step 4: Remove translation props from cards and homepage**

- `PostCard` and `FeaturedPost` accept only `post`.
- Render `titleZh`, `summaryZh`, `readingMinutes` and Chinese action labels directly.
- `Homepage` removes `getPostWithTranslation`, `translationEntries`, and `translationBySlug`.
- Calls become `<FeaturedPost post={featured} />` and `<PostCard post={post} />`.
- Every bilingual marketing label retains only its existing Chinese text.

- [ ] **Step 5: Remove language state from global layout and widgets**

Apply these exact end states:

```ts
export const THEME_INIT_SCRIPT = `(function(){var d=document.documentElement;var t=localStorage.getItem('theme');if(!t){t=window.matchMedia('(prefers-color-scheme:light)').matches?'light':'dark'}d.setAttribute('data-theme',t)})();`;
```

```astro
<html lang="zh-CN" data-theme="dark">
```

- Remove the first two `data-lang` visibility rules from `global.css`.
- Header imports/renders ThemeToggle but not LangToggle.
- TableOfContents uses one Chinese title and one headings list.
- LockedBanner, About, 404, Archives, Categories and Tags retain only Chinese nodes.
- CodeBlockWrapper sets `expandBtn.textContent = '展开'`.
- Delete `src/components/LangToggle.astro`.

Do not remove `data-lang="zh-CN"` from Giscus; that is the third-party comment widget locale, not the deleted site-language state.

- [ ] **Step 6: Run tests**

```bash
node --import tsx --test tests/source-safety.test.ts
npm test
```

Expected: PASS. `rg -n 'lang-en|lang-zh|getPostWithTranslation|LangToggle' src tests` returns no matches.

- [ ] **Step 7: Commit Chinese-only UI behavior**

```bash
git add src tests/source-safety.test.ts
git commit -m "refactor: remove English blog experience"
```

---

### Task 5: Remove Translation Tooling, CI and Active Documentation

**Files:**
- Modify: `tests/source-safety.test.ts`
- Delete: `scripts/`
- Delete: `tests/test_translation_paths.py`
- Delete: `tests/test_codeblocks.py`
- Modify: `package.json`
- Modify: `.github/workflows/build.yml`
- Modify: `README.md`
- Modify: `.kiro/steering/project-context.md`
- Modify locally only: `.env`

- [ ] **Step 1: Add failing repository-level absence assertions**

Extend `tests/source-safety.test.ts`:

```ts
test('translation tooling and CI hooks are absent', () => {
  assert.equal(existsSync('scripts/translate.py'), false);
  assert.equal(existsSync('scripts/translate_summary.py'), false);
  assert.equal(existsSync('scripts/check_en_quality.py'), false);
  assert.equal(existsSync('scripts/check_codeblocks.py'), false);
  const workflow = readFileSync('.github/workflows/build.yml', 'utf8');
  assert.doesNotMatch(workflow, /LLM_API|VAULT_PUSH_TOKEN|translate\.py|\.en\.md|Setup Python/);
  const pkg = JSON.parse(readFileSync('package.json', 'utf8'));
  assert.equal(pkg.scripts['test:python'], undefined);
  assert.equal(pkg.scripts.test, 'npm run test:node');
});
```

- [ ] **Step 2: Run the test and verify failure**

```bash
node --import tsx --test tests/source-safety.test.ts
```

Expected: FAIL because scripts and workflow references still exist.

- [ ] **Step 3: Delete the Python translation suite**

Delete the four top-level scripts, all translation-only `scripts/lib/*`, `scripts/requirements.txt`, the two Python tests, and empty directories. Confirm:

```bash
find scripts -type f 2>/dev/null
find tests -type f -name 'test_*.py'
```

Expected: no output. Remove `scripts/` if empty.

- [ ] **Step 4: Simplify package test commands**

Set:

```json
"test:node": "node --import tsx --test tests/*.test.ts",
"test": "npm run test:node"
```

Remove `test:python`.

- [ ] **Step 5: Remove translation and Python steps from GitHub Actions**

In `.github/workflows/build.yml`:

- Remove the `workflow_dispatch.inputs.translate` block; keep plain `workflow_dispatch:`.
- Remove Setup Python, Python dependencies, Translate, and Commit translations steps.
- Keep checkout, Node setup, `npm ci`, vault SSH clone, Astro build, rsync, container reload and smoke test unchanged.
- Remove all `LLM_*` and `VAULT_PUSH_TOKEN` references.

- [ ] **Step 6: Update active documentation and local environment**

README architecture becomes:

```text
Obsidian vault -> push -> repository_dispatch -> clone vault -> validate published Chinese posts -> Astro build -> rsync dist -> VPS Nginx
```

Document that `发布: true`, valid `Slug`, and non-draft status control publishing regardless of directory. Remove Python prerequisites and translation/vault-write secrets.

Update `.kiro/steering/project-context.md` current-state sections to the same Chinese-only pipeline. Do not rewrite archived `.kiro/specs/obsidian-blog-migration/*`.

From ignored `.env`, remove only `VAULT_PUSH_TOKEN`, `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL`. Keep `SITE_DISPATCH_TOKEN` and deployment/site variables. Never print the secret values.

Apply that ignored-file cleanup without reading values into output:

```bash
sed -i -E '/^(VAULT_PUSH_TOKEN|LLM_API_KEY|LLM_BASE_URL|LLM_MODEL)=/d' .env
```

The local machine does not have GitHub CLI available, so add an administrator follow-up to remove those same four obsolete names from the blog repository's Actions Secrets page. The workflow no longer references them, so this does not block code verification; do not use the credential embedded in the Git remote to automate secret deletion.

- [ ] **Step 7: Run tests and active-reference scan**

```bash
npm test
rg -n -i 'translate|translation|translated|LLM_API|LLM_MODEL|VAULT_PUSH_TOKEN|\.en\.md' src tests package.json .github README.md .kiro/steering
```

Expected: tests PASS. The scan has no active translation feature references; a safety assertion mentioning `.en.md` is allowed because it prevents regression.

- [ ] **Step 8: Commit tooling removal**

```bash
git add .github/workflows/build.yml README.md .kiro/steering/project-context.md package.json tests/source-safety.test.ts
git add -u scripts tests
git commit -m "chore: remove translation tooling and CI"
```

Do not stage `.env` because it is intentionally ignored.

---

### Task 6: Delete Vault Translations and Generalize Dispatch

**Files:**
- Modify in vault: `.github/workflows/notify.yml`
- Delete in vault: every `*.en.md`

- [ ] **Step 1: Record the vault boundary without changing it**

Run:

```bash
git -C /mnt/hgfs/Work/Obsidian status --short
git -C /mnt/hgfs/Work/Obsidian diff --name-only
git -C /mnt/hgfs/Work/Obsidian diff --cached --name-only | tee /tmp/xyvora-vault-staged-before.txt
find /mnt/hgfs/Work/Obsidian -type f -name '*.en.md' | wc -l
git -C /mnt/hgfs/Work/Obsidian ls-files '*en.md' | wc -l
```

Expected: many pre-existing migration changes; currently 132 working-tree and 132 tracked English files. The temporary file records any user-staged paths without altering them. If counts or staged paths have changed, preserve and report the new observed state.

- [ ] **Step 2: Delete all current English artifacts**

Delete only matching English artifacts:

```bash
find /mnt/hgfs/Work/Obsidian -type f -name '*.en.md' -print -delete
find /mnt/hgfs/Work/Obsidian/50-Published/Translated -depth -type d -empty -delete 2>/dev/null || true
find /mnt/hgfs/Work/Obsidian/Translated -depth -type d -empty -delete 2>/dev/null || true
```

The constrained `-empty` operations cannot delete a directory containing non-English files.

- [ ] **Step 3: Update the vault notification workflow**

Set the workflow trigger to:

```yaml
on:
  push:
    branches: [main]
    paths:
      - '**/*.md'
```

Keep the existing repository-dispatch job and `SITE_DISPATCH_TOKEN` unchanged. Remove the obsolete `.en.md` exclusion.

- [ ] **Step 4: Verify deletion and the exact staging scope**

```bash
find /mnt/hgfs/Work/Obsidian -type f -name '*.en.md' | wc -l
git -C /mnt/hgfs/Work/Obsidian add -u -- ':(glob)**/*.en.md'
git -C /mnt/hgfs/Work/Obsidian add .github/workflows/notify.yml
comm -23 \
  <(git -C /mnt/hgfs/Work/Obsidian diff --cached --name-only | sort) \
  <(sort /tmp/xyvora-vault-staged-before.txt)
```

Expected: first command prints `0`. Every newly staged path printed by `comm` is either `.github/workflows/notify.yml` or ends in `.en.md`. Do not unstage or alter paths captured in the baseline file.

- [ ] **Step 5: Commit only the approved vault cleanup**

```bash
git -C /mnt/hgfs/Work/Obsidian commit --only \
  -m "chore: remove English translations" -- \
  .github/workflows/notify.yml ':(glob)**/*.en.md'
diff -u \
  /tmp/xyvora-vault-staged-before.txt \
  <(git -C /mnt/hgfs/Work/Obsidian diff --cached --name-only)
```

Expected: the commit contains tracked English deletions and the notify workflow only. The final `diff` has no output, proving any pre-existing staged state was preserved; all unrelated vault migration changes remain in the working tree.

---

### Task 7: Real-Vault Build, Artifact Audit and Local Preview

**Files:**
- Verify: `dist/`, `.astro/` (ignored generated output)

- [ ] **Step 1: Run the full automated suite**

```bash
npm test
```

Expected: all Node tests PASS; no Python test command runs.

- [ ] **Step 2: Build against the real Linux vault path**

```bash
set -o pipefail
NO_COLOR=1 ASTRO_VAULT_PATH=/mnt/hgfs/Work/Obsidian npm run build 2>&1 | tee /tmp/xyvora-build.log
PUBLISHED=$(sed -nE 's/.* ([0-9]+) published,.*/\1/p' /tmp/xyvora-build.log | tail -n 1)
test "$PUBLISHED" -gt 0
test "$(find dist/post -type f -name index.html | wc -l)" -eq "$PUBLISHED"
```

Expected: build exits 0, logs a positive published-post count, and generates the same number of post routes. It must not log `SecNotes` as a required root or report zero posts.

- [ ] **Step 3: Audit generated content**

```bash
test "$(find dist/post -mindepth 1 -maxdepth 1 -type d | wc -l)" -gt 0
test "$(wc -c < dist/search-index.json)" -gt 2
test "$(find dist/_images -type f | wc -l)" -gt 0
rg -n '<item>|<entry>' dist/rss.xml
rg -n '/post/' dist/sitemap-0.xml
! rg -n 'lang-en|post-bilingual|English translation is not available' dist
```

Expected: all commands succeed; generated posts, search, copied published assets, RSS and sitemap are non-empty, and the final negative scan finds no translation output.

- [ ] **Step 4: Audit source and both repositories**

```bash
! rg -n 'SecNotes/|Translated/SecNotes|getPostWithTranslation|LangToggle|lang-en|lang-zh' src tests .github README.md .kiro/steering
find /mnt/hgfs/Work/Obsidian -type f -name '*.en.md' | wc -l
git status --short
git -C /mnt/hgfs/Work/Obsidian status --short
```

Expected: no active old-path or translation matches, vault count `0`, blog changes are only intentional plan/implementation files, and unrelated vault migration changes remain untouched.

- [ ] **Step 5: Start a local preview and perform HTTP smoke checks**

Run the preview in a persistent terminal:

```bash
npm run preview -- --host 127.0.0.1 --port 4321
```

From another terminal:

```bash
curl -fsS http://127.0.0.1:4321/ >/dev/null
FIRST_SLUG=$(find dist/post -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | head -n 1)
curl -fsS "http://127.0.0.1:4321/post/${FIRST_SLUG}/" >/dev/null
```

Expected: both requests return HTTP 200. Keep the preview available for the user and report `http://127.0.0.1:4321/`.

- [ ] **Step 6: Review commits and do not deploy**

```bash
git log --oneline -6
git -C /mnt/hgfs/Work/Obsidian log --oneline -3
```

Expected: focused commits for discovery, loader, resources, UI, tooling and vault cleanup. Do not push and do not run the GitHub workflow or any VPS mutation.

---

## Final Verification Checklist

- [ ] `npm test` passes.
- [ ] Real-vault `npm run build` passes with a positive post count.
- [ ] `dist/post`, search, RSS and sitemap contain Chinese articles.
- [ ] Active source contains no translation UI/data/tooling.
- [ ] Vault working tree contains zero `.en.md` files.
- [ ] Vault cleanup commit contains no unrelated migration changes.
- [ ] Obsolete GitHub Actions Secret names are reported as an administrator cleanup item.
- [ ] VPS configuration was not changed.
- [ ] Local preview serves the homepage and a post with HTTP 200.
