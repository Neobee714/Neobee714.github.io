import assert from 'node:assert/strict';
import {
  chmodSync,
  existsSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { discoverPublishedPosts } from '../src/lib/vault-source.ts';
import {
  buildVaultIndex,
  getVaultIndex,
  primeVaultIndex,
  resolveVaultAsset,
} from '../src/lib/vault-index.ts';
import { vaultLoader } from '../src/lib/vault-loader.ts';
import { remarkWikilink } from '../src/lib/remark-wikilink.ts';
import { rehypeImageRewrite } from '../src/lib/rehype-image-rewrite.ts';
import { copyVaultImages } from '../src/lib/integrations/copy-vault-images.ts';

async function withVault(run: (root: string) => Promise<void>): Promise<void> {
  const root = mkdtempSync(path.join(tmpdir(), 'vault-index-'));
  try {
    await run(root);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

function put(root: string, relativePath: string, content: string): string {
  const absolutePath = path.join(root, ...relativePath.split('/'));
  mkdirSync(path.dirname(absolutePath), { recursive: true });
  writeFileSync(absolutePath, content, 'utf8');
  return absolutePath;
}

function note(slug: string, body: string, published = true): string {
  return `---\n发布: ${published}\nSlug: ${slug}\n---\n${body}`;
}

function sha256(content: string): string {
  return createHash('sha256').update(content).digest('hex');
}

test('getVaultIndex requires an explicitly primed index', () => {
  assert.throws(() => getVaultIndex(), /Vault index was not primed/);
});

test('indexes only published notes and assets referenced by published bodies', async () => {
  await withVault(async (root) => {
    const demoPath = put(
      root,
      'articles/demo.md',
      note(
        'demo-slug',
        [
          '![[used.png]]',
          '![[./assets/local.png|320x200]]',
          '![[../a/duplicate.png]]',
          '![[duplicate.png]]',
          '![[guide.pdf#page=2|Guide]]',
          '![spaced](<./assets/space name.jpg?download=1#preview>)',
          '![external](https://example.com/external.png)',
          '![protocol](//example.com/protocol.png)',
          '![inline](data:image/png;base64,AAAA)',
          '![[missing.png]]',
        ].join('\n'),
      ),
    );
    put(root, 'articles/other.md', note('other-slug', '[[demo]]\n'));
    put(root, 'private.md', note('private-slug', '![[private/unused-private.png]]\n', false));

    const usedPath = put(root, 'assets/used.png', 'used');
    const localPath = put(root, 'articles/assets/local.png', 'local');
    const spacedPath = put(root, 'articles/assets/space name.jpg', 'spaced');
    const duplicateA = put(root, 'a/duplicate.png', 'duplicate-a');
    const duplicateB = put(root, 'b/duplicate.png', 'duplicate-b');
    const pdfPath = put(root, 'docs/guide.pdf', 'pdf');
    const privateAsset = put(root, 'private/unused-private.png', 'private');
    const unrelated = put(root, 'assets/unrelated.webp', 'must never be read');
    chmodSync(unrelated, 0o000);

    const discovery = await discoverPublishedPosts(root);
    const index = await buildVaultIndex(root, discovery.posts);

    assert.deepEqual([...index.notesByName.entries()], [
      ['demo', 'demo-slug'],
      ['other', 'other-slug'],
    ]);
    assert.deepEqual(index.assetCandidatesByName.get('used.png'), [usedPath]);
    assert.deepEqual(index.assetCandidatesByName.get('local.png'), [localPath]);
    assert.deepEqual(index.assetCandidatesByName.get('space name.jpg'), [spacedPath]);
    assert.deepEqual(index.assetCandidatesByName.get('duplicate.png'), [duplicateA, duplicateB]);
    assert.deepEqual(index.assetCandidatesByName.get('guide.pdf'), [pdfPath]);
    assert.equal(index.assetCandidatesByName.has('external.png'), false);
    assert.equal(index.assetCandidatesByName.has('protocol.png'), false);
    assert.equal(index.assetCandidatesByName.has('unused-private.png'), false);
    assert.equal(index.assetCandidatesByName.has('unrelated.webp'), false);
    assert.equal(index.contentHashByPath.has(privateAsset), false);
    assert.equal(index.contentHashByPath.has(unrelated), false);
    assert.deepEqual([...index.contentHashByPath.keys()].sort(), [
      duplicateA,
      duplicateB,
      pdfPath,
      localPath,
      spacedPath,
      usedPath,
    ].sort());

    assert.deepEqual(resolveVaultAsset(index, 'used.png', demoPath), {
      absolutePath: usedPath,
      outputName: 'used.png',
    });
    assert.deepEqual(resolveVaultAsset(index, './assets/local.png', demoPath), {
      absolutePath: localPath,
      outputName: 'local.png',
    });
    assert.deepEqual(
      resolveVaultAsset(index, './assets/space name.jpg?download=1#preview', demoPath),
      { absolutePath: spacedPath, outputName: 'space-name.jpg' },
    );
    assert.deepEqual(resolveVaultAsset(index, 'guide.pdf#page=2', demoPath), {
      absolutePath: pdfPath,
      outputName: 'guide.pdf',
    });

    const resolvedDuplicate = resolveVaultAsset(index, '../a/duplicate.png', demoPath);
    assert.deepEqual(resolvedDuplicate, {
      absolutePath: duplicateA,
      outputName: `duplicate-${sha256('duplicate-a').slice(0, 8)}.png`,
    });
    assert.throws(
      () => resolveVaultAsset(index, 'duplicate.png', demoPath),
      /Ambiguous vault asset "duplicate\.png"/,
    );
    assert.equal(resolveVaultAsset(index, 'missing.png', demoPath), undefined);
    assert.equal(resolveVaultAsset(index, 'https://example.com/external.png', demoPath), undefined);
    assert.equal(resolveVaultAsset(index, 'http:example.png', demoPath), undefined);
    assert.equal(resolveVaultAsset(index, 'https:example.png', demoPath), undefined);
    assert.equal(resolveVaultAsset(index, '//example.com/protocol.png', demoPath), undefined);
    assert.equal(resolveVaultAsset(index, 'data:image/png;base64,AAAA', demoPath), undefined);
    assert.deepEqual([...index.missingReferences], ['missing.png']);
    assert.equal(index.resolvedAssetsByOutputName.get('used.png'), usedPath);
    assert.equal(index.resolvedAssetsByOutputName.get(resolvedDuplicate!.outputName), duplicateA);

    primeVaultIndex(index);
    assert.equal(getVaultIndex(), index);
  });
});

test('content hashes keep disambiguated output stable when a duplicate moves', async () => {
  await withVault(async (root) => {
    const source = put(root, 'articles/demo.md', note('demo', '![[../first/same.png]]\n![[same.png]]'));
    const first = put(root, 'first/same.png', 'stable-content');
    put(root, 'second/same.png', 'different-content');
    const posts = (await discoverPublishedPosts(root)).posts;
    const before = await buildVaultIndex(root, posts);
    const beforeName = resolveVaultAsset(before, '../first/same.png', source)?.outputName;

    const movedSource = path.join(root, 'moved', 'same.png');
    mkdirSync(path.dirname(movedSource), { recursive: true });
    writeFileSync(movedSource, 'stable-content', 'utf8');
    rmSync(first);
    const after = await buildVaultIndex(root, posts);
    const afterName = resolveVaultAsset(after, '../moved/same.png', source)?.outputName;

    assert.equal(beforeName, `same-${sha256('stable-content').slice(0, 8)}.png`);
    assert.equal(afterName, beforeName);
  });
});

test('output name collisions permit identical content and reject different content', async () => {
  await withVault(async (root) => {
    const source = put(
      root,
      'demo.md',
      note('demo', '![[collision name.png]]\n![[collision_name.png]]\n![[collision-name.png]]'),
    );
    const first = put(root, 'collision name.png', 'shared');
    const second = put(root, 'collision_name.png', 'shared');
    put(root, 'collision-name.png', 'different');
    const index = await buildVaultIndex(root, (await discoverPublishedPosts(root)).posts);

    assert.equal(resolveVaultAsset(index, 'collision name.png', source)?.absolutePath, first);
    assert.equal(resolveVaultAsset(index, 'collision_name.png', source)?.absolutePath, second);
    assert.throws(
      () => resolveVaultAsset(index, 'collision-name.png', source),
      /output name.*collision-name\.png/i,
    );
  });
});

test('explicit paths outside the vault never fall back to an in-vault basename', async () => {
  await withVault(async (directory) => {
    const root = path.join(directory, 'vault');
    const source = put(
      root,
      'articles/demo.md',
      note(
        'demo',
        '![[../../outside/secret.png]]\n![[..%2F..%2Foutside%2Fsecret.png]]\n![[C:\\outside\\secret.png]]\n![[/assets/root.png]]',
      ),
    );
    const inVaultSecret = put(root, 'assets/secret.png', 'in-vault-secret');
    const rootAsset = put(root, 'assets/root.png', 'root-asset');
    put(directory, 'outside/secret.png', 'outside-secret');
    const index = await buildVaultIndex(root, (await discoverPublishedPosts(root)).posts);

    assert.equal(resolveVaultAsset(index, '../../outside/secret.png', source), undefined);
    assert.equal(resolveVaultAsset(index, '..%2F..%2Foutside%2Fsecret.png', source), undefined);
    assert.equal(resolveVaultAsset(index, 'C:\\outside\\secret.png', source), undefined);
    assert.equal([...index.resolvedAssetsByOutputName.values()].includes(inVaultSecret), false);
    assert.deepEqual(resolveVaultAsset(index, '/assets/root.png', source), {
      absolutePath: rootAsset,
      outputName: 'root.png',
    });
  });
});

test('Markdown AST extraction supports complex images and ignores literal-code embeds', async () => {
  await withVault(async (root) => {
    put(
      root,
      'demo.md',
      note(
        'demo',
        [
          '![nested](./assets/chart_(final).png)',
          '![reference][diagram]',
          '',
          '[diagram]: ./assets/reference.png',
          '',
          '![[real.png]]',
          '`![[inline-code.png]]`',
          '<!-- ![[comment.png]] -->',
          '```md',
          '![[fenced.png]]',
          '![code image](./assets/code-image.png)',
          '```',
        ].join('\n'),
      ),
    );
    const nested = put(root, 'assets/chart_(final).png', 'nested');
    const reference = put(root, 'assets/reference.png', 'reference');
    const real = put(root, 'assets/real.png', 'real');
    const ignored = [
      put(root, 'assets/inline-code.png', 'inline'),
      put(root, 'assets/comment.png', 'comment'),
      put(root, 'assets/fenced.png', 'fenced'),
      put(root, 'assets/code-image.png', 'code-image'),
    ];

    const index = await buildVaultIndex(root, (await discoverPublishedPosts(root)).posts);

    assert.deepEqual(index.assetCandidatesByName.get('chart_(final).png'), [nested]);
    assert.deepEqual(index.assetCandidatesByName.get('reference.png'), [reference]);
    assert.deepEqual(index.assetCandidatesByName.get('real.png'), [real]);
    for (const absolutePath of ignored) {
      assert.equal(index.assetCandidatesByName.has(path.basename(absolutePath)), false);
      assert.equal(index.contentHashByPath.has(absolutePath), false);
    }
  });
});

test('duplicate reference definitions retain the first asset like CommonMark', async () => {
  await withVault(async (root) => {
    const source = put(
      root,
      'demo.md',
      note(
        'demo',
        ['![x][diagram]', '', '[diagram]: first.png', '[diagram]: second.png'].join('\n'),
      ),
    );
    const first = put(root, 'first.png', 'first');
    const second = put(root, 'second.png', 'second');

    const index = await buildVaultIndex(root, (await discoverPublishedPosts(root)).posts);

    assert.deepEqual(index.assetCandidatesByName.get('first.png'), [first]);
    assert.equal(index.contentHashByPath.get(first), sha256('first'));
    assert.deepEqual(resolveVaultAsset(index, 'first.png', source), {
      absolutePath: first,
      outputName: 'first.png',
    });
    assert.equal(index.assetCandidatesByName.has('second.png'), false);
    assert.equal(index.contentHashByPath.has(second), false);
    assert.equal(resolveVaultAsset(index, 'second.png', source), undefined);
  });
});

test('path comparison follows Windows case rules without weakening POSIX', async () => {
  const vaultIndex = await import('../src/lib/vault-index.ts');
  const compare = (vaultIndex as any).vaultPathsEqual;

  assert.equal(typeof compare, 'function');
  assert.equal(compare('C:\\Vault\\Asset.PNG', 'c:\\vault\\asset.png', path.win32), true);
  assert.equal(compare('/Vault/Asset.PNG', '/vault/asset.png', path.posix), false);
});

test('remark and rehype resolve assets relative to the Markdown source file', async () => {
  await withVault(async (root) => {
    const demoPath = put(
      root,
      'articles/demo.md',
      note(
        'demo',
        '![[./assets/local.png|320x200]]\n![[./assets/guide.pdf]]\n[[published|Live]]\n[[private]]',
      ),
    );
    put(root, 'notes/published.md', note('published-slug', '# Published'));
    put(root, 'notes/private.md', note('private-slug', '# Private', false));
    put(root, 'articles/assets/local.png', 'local');
    put(root, 'articles/assets/guide.pdf', 'guide');
    const index = await buildVaultIndex(root, (await discoverPublishedPosts(root)).posts);
    primeVaultIndex(index);

    const embedTree: any = {
      type: 'root',
      children: [{ type: 'paragraph', children: [{ type: 'text', value: '![[./assets/local.png|320x200]]' }] }],
    };
    remarkWikilink()(embedTree, { path: demoPath } as any);
    assert.equal(
      embedTree.children[0].children[0].value,
      '<img src="/_images/local.png" alt="./assets/local.png" width="320" height="200" loading="lazy">',
    );

    const resourceTree: any = {
      type: 'root',
      children: [{ type: 'paragraph', children: [{ type: 'text', value: '![[./assets/guide.pdf]]' }] }],
    };
    remarkWikilink()(resourceTree, { path: demoPath } as any);
    assert.equal(resourceTree.children[0].children[0].url, '/_images/guide.pdf');

    const linkTree: any = {
      type: 'root',
      children: [{ type: 'paragraph', children: [{ type: 'text', value: '[[published|Live]] [[private]]' }] }],
    };
    remarkWikilink()(linkTree, { path: demoPath } as any);
    assert.equal(linkTree.children[0].children[0].url, '/post/published-slug/');
    assert.match(linkTree.children[0].children[2].value, /不存在或未发布的链接/);

    const imageTree: any = {
      type: 'root',
      children: [
        {
          type: 'element',
          tagName: 'p',
          properties: {},
          children: [
            { type: 'element', tagName: 'img', properties: { src: './assets/local.png?raw=1', alt: 'not-a-filename' }, children: [] },
            { type: 'element', tagName: 'img', properties: { src: 'https://example.com/external.png' }, children: [] },
            { type: 'element', tagName: 'img', properties: { src: './assets/missing.png' }, children: [] },
          ],
        },
      ],
    };
    const originalNodeEnv = process.env.NODE_ENV;
    const originalWarn = console.warn;
    process.env.NODE_ENV = 'production';
    console.warn = () => {};
    try {
      rehypeImageRewrite()(imageTree, { path: demoPath } as any);
    } finally {
      console.warn = originalWarn;
      if (originalNodeEnv === undefined) delete process.env.NODE_ENV;
      else process.env.NODE_ENV = originalNodeEnv;
    }
    const images = imageTree.children[0].children;
    assert.equal(images[0].properties.src, '/_images/local.png');
    assert.equal(images[0].properties.alt, 'not-a-filename');
    assert.equal(images[1].properties.src, 'https://example.com/external.png');
    assert.equal(images[2].tagName, 'span');
    assert.equal(index.missingReferences.has('missing.png'), true);
  });
});

test('remark determines encoded image extensions from the resolved asset', async () => {
  await withVault(async (root) => {
    const source = put(
      root,
      'articles/demo.md',
      note('demo', '![[./assets/encoded-image%2Epng]]'),
    );
    put(root, 'articles/assets/encoded-image.png', 'encoded image');
    const index = await buildVaultIndex(root, (await discoverPublishedPosts(root)).posts);
    primeVaultIndex(index);
    const tree: any = {
      type: 'root',
      children: [
        {
          type: 'paragraph',
          children: [{ type: 'text', value: '![[./assets/encoded-image%2Epng]]' }],
        },
      ],
    };

    remarkWikilink()(tree, { path: source } as any);

    assert.equal(tree.children[0].children[0].type, 'html');
    assert.match(tree.children[0].children[0].value, /<img /);
    assert.match(tree.children[0].children[0].value, /\/_images\/encoded-image\.png/);
  });
});

test('remark leaves external Obsidian embeds literal and does not track them as missing', async () => {
  await withVault(async (root) => {
    const syntaxes = [
      '![[http://example.com/image.png]]',
      '![[https://example.com/image.png]]',
      '![[http:example.png]]',
      '![[https:example.png]]',
      '![[//cdn.example.com/image.png]]',
      '![[data:image/png;base64,AAAA]]',
    ];
    put(root, 'demo.md', note('demo', syntaxes.join('\n')));
    const index = await buildVaultIndex(root, (await discoverPublishedPosts(root)).posts);
    primeVaultIndex(index);

    for (const syntax of syntaxes) {
      const tree: any = {
        type: 'root',
        children: [{ type: 'paragraph', children: [{ type: 'text', value: syntax }] }],
      };
      remarkWikilink()(tree, { path: path.join(root, 'demo.md') } as any);
      assert.deepEqual(tree.children[0].children, [{ type: 'text', value: syntax }]);
    }
    assert.deepEqual([...index.missingReferences], []);
  });
});

test('rehype leaves every supported external image form unchanged and untracked', async () => {
  await withVault(async (root) => {
    put(root, 'demo.md', note('demo', '# Images'));
    const index = await buildVaultIndex(root, (await discoverPublishedPosts(root)).posts);
    primeVaultIndex(index);
    const tree: any = {
      type: 'root',
      children: [
        {
          type: 'element',
          tagName: 'p',
          properties: {},
          children: [
            { type: 'element', tagName: 'img', properties: { src: 'http:example.png' }, children: [] },
            { type: 'element', tagName: 'img', properties: { src: 'https:example.png' }, children: [] },
            { type: 'element', tagName: 'img', properties: { src: '//cdn.example.com/image.png' }, children: [] },
            { type: 'element', tagName: 'img', properties: { src: 'data:image/png;base64,AAAA' }, children: [] },
          ],
        },
      ],
    };
    const before = structuredClone(tree);
    const originalWarn = console.warn;
    console.warn = () => {};
    try {
      rehypeImageRewrite()(tree, { path: path.join(root, 'demo.md') } as any);
    } finally {
      console.warn = originalWarn;
    }

    assert.deepEqual(tree, before);
    assert.deepEqual([...index.missingReferences], []);
  });
});

test('remark renders a missing non-image embed as an accessible visible placeholder', async () => {
  await withVault(async (root) => {
    const source = put(root, 'demo.md', note('demo', '![[missing.pdf]]'));
    const index = await buildVaultIndex(root, (await discoverPublishedPosts(root)).posts);
    primeVaultIndex(index);
    const tree: any = {
      type: 'root',
      children: [{ type: 'paragraph', children: [{ type: 'text', value: '![[missing.pdf]]' }] }],
    };

    remarkWikilink()(tree, { path: source } as any);

    const placeholder = tree.children[0].children[0];
    assert.equal(placeholder.type, 'html');
    assert.match(placeholder.value, /class="missing-image"/);
    assert.match(placeholder.value, /role="img"/);
    assert.match(placeholder.value, /aria-label="Missing image"/);
    assert.match(placeholder.value, /Missing: missing\.pdf/);
    assert.deepEqual([...index.missingReferences], ['missing.pdf']);
  });
});

test('loader primes the new index for rendering and restores the previous index on failure', async () => {
  await withVault(async (root) => {
    const vaultRoot = path.join(root, 'vault');
    put(vaultRoot, 'new-note.md', note('new-slug', '# New'));
    const previousIndex = {
      root: vaultRoot,
      notesByName: new Map([['old-note', 'old-slug']]),
      assetCandidatesByName: new Map<string, string[]>(),
      contentHashByPath: new Map<string, string>(),
      resolvedAssetsByOutputName: new Map<string, string>(),
      missingReferences: new Set<string>(),
    };
    primeVaultIndex(previousIndex);

    const entries = new Map<string, any>([['old-note', { id: 'old-note', data: {} }]]);
    let observedNewIndex = false;
    const context: any = {
      store: {
        set: (entry: any) => entries.set(entry.id, entry),
        clear: () => entries.clear(),
      },
      parseData: async ({ data }: any) => data,
      renderMarkdown: async () => {
        observedNewIndex = getVaultIndex().notesByName.get('new-note') === 'new-slug';
        throw new Error('render failed');
      },
      generateDigest: () => 'digest',
      config: { root: pathToFileURL(`${root}${path.sep}`) },
      logger: { info: () => {}, error: () => {}, warn: () => {}, debug: () => {} },
    };

    await assert.rejects(vaultLoader(vaultRoot).load(context), /render failed/);

    assert.equal(observedNewIndex, true);
    assert.equal(getVaultIndex(), previousIndex);
    assert.deepEqual([...entries.keys()], ['old-note']);
  });
});

test('successful real dev loader scans reconcile the configured public image directory', async () => {
  await withVault(async (root) => {
    const vaultRoot = path.join(root, 'vault');
    const publicDirectory = path.join(root, 'site-public');
    const notePath = put(vaultRoot, 'demo.md', note('demo', '![[asset.png]]'));
    put(vaultRoot, 'asset.png', 'current-asset');
    const stalePath = put(publicDirectory, '_images/stale.png', 'stale');
    const entries = new Map<string, any>();
    const watcher = {
      add: () => watcher,
      on: () => watcher,
      off: () => watcher,
    };
    const context: any = {
      store: {
        set: (entry: any) => entries.set(entry.id, entry),
        clear: () => entries.clear(),
      },
      parseData: async ({ data }: any) => data,
      renderMarkdown: async (content: string, options: { fileURL: URL }) => {
        if (content.includes('![[asset.png]]')) {
          resolveVaultAsset(getVaultIndex(), 'asset.png', fileURLToPath(options.fileURL));
        }
        return { html: '<p>demo</p>' };
      },
      generateDigest: () => 'digest',
      config: {
        root: pathToFileURL(`${root}${path.sep}`),
        publicDir: pathToFileURL(`${publicDirectory}${path.sep}`),
      },
      watcher,
      logger: { info: () => {}, error: () => {}, warn: () => {}, debug: () => {} },
    };
    const loader = vaultLoader(vaultRoot);

    await loader.load(context);

    const copiedPath = path.join(publicDirectory, '_images/asset.png');
    assert.equal(readFileSync(copiedPath, 'utf8'), 'current-asset');
    assert.equal(existsSync(stalePath), false);

    writeFileSync(notePath, note('demo', '# No assets'), 'utf8');
    await loader.load(context);
    assert.equal(existsSync(copiedPath), false);
  });
});

test('production integration clears generated dev assets and copies the resolved registry', async () => {
  await withVault(async (root) => {
    const originalDirectory = process.cwd();
    try {
      process.chdir(root);
      const vaultRoot = path.join(root, 'vault');
      const source = put(vaultRoot, 'demo.md', note('demo', '![[asset.png]]\n![[missing.pdf]]'));
      const asset = put(vaultRoot, 'asset.png', 'production-asset');
      const index = await buildVaultIndex(vaultRoot, (await discoverPublishedPosts(vaultRoot)).posts);
      assert.deepEqual(resolveVaultAsset(index, 'asset.png', source), {
        absolutePath: asset,
        outputName: 'asset.png',
      });
      resolveVaultAsset(index, 'missing.pdf', source);
      primeVaultIndex(index);

      put(root, 'public/_images/stale.png', 'stale');
      const integration = copyVaultImages();
      await (integration.hooks['astro:build:start'] as any)({ logger: { info: () => {} } });
      assert.equal(existsSync(path.join(root, 'public/_images')), false);

      const dist = path.join(root, 'dist');
      mkdirSync(dist, { recursive: true });
      const messages: string[] = [];
      await (integration.hooks['astro:build:done'] as any)({
        dir: pathToFileURL(`${dist}${path.sep}`),
        logger: { info: (message: string) => messages.push(message), warn: () => {} },
      });

      assert.equal(readFileSync(path.join(dist, '_images/asset.png'), 'utf8'), 'production-asset');
      assert.match(messages.at(-1) ?? '', /copied 1.*missing 1/i);
    } finally {
      process.chdir(originalDirectory);
    }
  });
});
