import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import {
  discoverPublishedPosts,
  VaultSourceError,
  walkVaultFiles,
} from '../src/lib/vault-source.ts';
import {
  hasPublishFlag,
  isDraftStatus,
  isLockedStatus,
  normalizeFrontmatterScalar,
  normalizeStatus,
} from '../src/lib/publishing.ts';

async function withVault(run: (root: string) => Promise<void> | void): Promise<void> {
  const root = mkdtempSync(path.join(tmpdir(), 'vault-source-'));
  try {
    await run(root);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

function put(root: string, relativePath: string, raw: string): string {
  const absolutePath = path.join(root, ...relativePath.split('/'));
  mkdirSync(path.dirname(absolutePath), { recursive: true });
  writeFileSync(absolutePath, raw, 'utf8');
  return absolutePath;
}

function markdown(frontmatter: string, body = '# Body\n'): string {
  return `---\n${frontmatter}\n---\n${body}`;
}

async function expectVaultError(
  run: () => Promise<unknown>,
  code: VaultSourceError['code'],
): Promise<VaultSourceError> {
  try {
    await run();
  } catch (error) {
    assert.ok(error instanceof VaultSourceError);
    assert.equal(error.code, code);
    return error;
  }
  throw new assert.AssertionError({ message: `Expected ${code}` });
}

test('publishing helpers accept unknown scalar values and recognized flags', () => {
  assert.equal(normalizeFrontmatterScalar('  " yes "  '), 'yes');
  assert.equal(normalizeFrontmatterScalar(" ' locked ' "), 'locked');
  assert.equal(normalizeFrontmatterScalar(42), '42');
  assert.equal(normalizeFrontmatterScalar(null), '');
  assert.equal(hasPublishFlag(true), true);
  assert.equal(hasPublishFlag(' YES '), true);
  assert.equal(hasPublishFlag("'是'"), true);
  assert.equal(hasPublishFlag(false), false);
  assert.equal(hasPublishFlag('no'), false);
  assert.equal(normalizeStatus(' "WIP" '), 'wip');
  assert.equal(isDraftStatus('Writing'), true);
  assert.equal(isLockedStatus('LOCKED'), true);
});

test('walkVaultFiles returns sorted nested files outside excluded directories', async () => {
  await withVault(async (root) => {
    const second = put(root, 'z/second.md', 'second');
    const first = put(root, 'a/first.md', 'first');
    put(root, '.git/ignored.md', 'ignored');
    put(root, '.obsidian/ignored.md', 'ignored');
    put(root, '.trash/ignored.md', 'ignored');
    put(root, 'node_modules/ignored.md', 'ignored');
    put(root, 'Templates/ignored.md', 'ignored');

    assert.deepEqual(await walkVaultFiles(root), [first, second]);
  });
});

test('discovers published posts in arbitrary nested directories', async () => {
  await withVault(async (root) => {
    const absolutePath = put(
      root,
      'Notes/deep/security-note.md',
      markdown('发布: true\nSlug: stable-security-note\ntitle: Security Note', 'Private body\n'),
    );

    const result = await discoverPublishedPosts(root);

    assert.deepEqual(result.stats, {
      markdown: 1,
      published: 1,
      drafts: 0,
      unpublished: 0,
      missingSlug: 0,
    });
    assert.equal(result.posts.length, 1);
    assert.deepEqual(result.posts[0], {
      id: 'Notes/deep/security-note',
      slug: 'stable-security-note',
      absolutePath,
      relativePath: 'Notes/deep/security-note.md',
      raw: markdown('发布: true\nSlug: stable-security-note\ntitle: Security Note', 'Private body\n'),
      body: '\nPrivate body\n',
      frontmatter: {
        发布: true,
        Slug: 'stable-security-note',
        title: 'Security Note',
      },
    });
  });
});

test('moving a source file changes its relative path but preserves its Slug', async () => {
  await withVault(async (root) => {
    const raw = markdown('发布: true\nSlug: permanent-url');
    const original = put(root, 'Inbox/note.md', raw);
    const before = (await discoverPublishedPosts(root)).posts[0];
    const moved = path.join(root, 'Archive', 'renamed.md');
    mkdirSync(path.dirname(moved), { recursive: true });
    renameSync(original, moved);
    const after = (await discoverPublishedPosts(root)).posts[0];

    assert.equal(before.slug, 'permanent-url');
    assert.equal(after.slug, before.slug);
    assert.equal(before.relativePath, 'Inbox/note.md');
    assert.equal(after.relativePath, 'Archive/renamed.md');
  });
});

test('classifies publish flags and drafts without parsing unpublished private notes', async () => {
  await withVault(async (root) => {
    put(root, 'public/standard.md', markdown('发布: true\nSlug: standard'));
    put(root, 'public/chinese.md', markdown('发布: 是\nSlug: chinese'));
    put(root, 'public/locked.md', markdown('发布: yes\n状态: 已锁住\nSlug: locked'));
    put(root, 'draft.md', markdown('发布: true\n状态: 进行中\nSlug: draft'));
    put(root, 'private.md', markdown('发布: no\nprivate: [', 'must not be parsed\n'));
    put(root, 'Templates/template.md', markdown('发布: true\nSlug: template'));
    put(root, '.trash/deleted.md', markdown('发布: true\nSlug: deleted'));

    const result = await discoverPublishedPosts(root);

    assert.deepEqual(result.posts.map(({ slug }) => slug).sort(), ['chinese', 'locked', 'standard']);
    assert.deepEqual(result.stats, {
      markdown: 5,
      published: 3,
      drafts: 1,
      unpublished: 1,
      missingSlug: 0,
    });
  });
});

test('reports an unavailable vault root', async () => {
  await withVault(async (root) => {
    const missing = path.join(root, 'does-not-exist');
    const error = await expectVaultError(
      () => discoverPublishedPosts(missing),
      'VAULT_UNAVAILABLE',
    );
    assert.match(error.message, /does-not-exist/);
  });
});

test('reports every published non-draft note missing a Slug', async () => {
  await withVault(async (root) => {
    put(root, 'one.md', markdown('发布: true'));
    put(root, 'nested/two.md', markdown('发布: yes\nSlug: "  "'));
    put(root, 'draft.md', markdown('发布: true\n状态: draft'));

    const error = await expectVaultError(() => discoverPublishedPosts(root), 'MISSING_SLUG');
    assert.match(error.message, /2/);
    assert.match(error.message, /one\.md/);
    assert.match(error.message, /nested\/two\.md/);
  });
});

test('rejects duplicate published Slugs', async () => {
  await withVault(async (root) => {
    put(root, 'one.md', markdown('发布: true\nSlug: repeated'));
    put(root, 'nested/two.md', markdown('发布: yes\nSlug: repeated'));

    const error = await expectVaultError(() => discoverPublishedPosts(root), 'DUPLICATE_SLUG');
    assert.match(error.message, /repeated/);
    assert.match(error.message, /one\.md/);
    assert.match(error.message, /nested\/two\.md/);
  });
});

test('reports a vault with zero publishable posts', async () => {
  await withVault(async (root) => {
    put(root, 'private.md', markdown('发布: false\nprivate: [', 'private\n'));
    await expectVaultError(() => discoverPublishedPosts(root), 'NO_POSTS');
  });
});

test('rejects any English artifact in the effective scan scope', async () => {
  await withVault(async (root) => {
    put(root, 'published.md', markdown('发布: true\nSlug: published'));
    put(root, 'nested/translation.en.md', markdown('发布: false'));
    put(root, 'Templates/ignored.en.md', markdown('发布: false'));

    const error = await expectVaultError(
      () => discoverPublishedPosts(root),
      'ENGLISH_ARTIFACT',
    );
    assert.match(error.message, /nested\/translation\.en\.md/);
    assert.doesNotMatch(error.message, /ignored/);
  });
});

test('reports invalid YAML only when a note is a publish candidate', async () => {
  await withVault(async (root) => {
    put(
      root,
      'invalid.md',
      markdown('发布: true\nSlug: invalid\nmetadata: [', 'body must not appear in errors\n'),
    );

    const error = await expectVaultError(
      () => discoverPublishedPosts(root),
      'INVALID_FRONTMATTER',
    );
    assert.match(error.message, /invalid\.md/);
    assert.doesNotMatch(error.message, /body must not appear/);
  });
});
