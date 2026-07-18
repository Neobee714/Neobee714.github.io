import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';
import type { DataStore, LoaderContext } from 'astro/loaders';
import type { DataEntry } from 'astro:content';
import type { FSWatcher } from 'vite';
import { vaultLoader } from '../src/lib/vault-loader.ts';

interface FakeContext {
  context: LoaderContext;
  entries: Map<string, DataEntry>;
  infoMessages: string[];
  parseCalls: Array<{ id: string; data: Record<string, unknown>; filePath?: string }>;
  renderCalls: Array<{ content: string; fileURL?: URL }>;
  clearCount: () => number;
}

class FakeWatcher {
  readonly watched: string[] = [];
  readonly listeners = new Map<string, Array<(value: any) => void>>();

  add(filePath: string): this {
    this.watched.push(filePath);
    return this;
  }

  on(event: string, listener: (value: any) => void): this {
    const eventListeners = this.listeners.get(event) ?? [];
    eventListeners.push(listener);
    this.listeners.set(event, eventListeners);
    return this;
  }

  off(event: string, listener: (value: any) => void): this {
    const eventListeners = this.listeners.get(event) ?? [];
    this.listeners.set(
      event,
      eventListeners.filter((candidate) => candidate !== listener),
    );
    return this;
  }

  clearListeners(): void {
    this.listeners.clear();
  }

  emit(event: string, value: any): void {
    for (const listener of this.listeners.get(event) ?? []) listener(value);
  }
}

function deferred<T = void>(): {
  promise: Promise<T>;
  resolve: (value: T | PromiseLike<T>) => void;
  reject: (reason?: unknown) => void;
} {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

async function waitFor(predicate: () => boolean, message: string): Promise<void> {
  const deadline = Date.now() + 2_000;
  while (!predicate()) {
    if (Date.now() >= deadline) throw new Error(message);
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
}

async function withTempDirectory(
  run: (directory: string) => Promise<void> | void,
): Promise<void> {
  const directory = mkdtempSync(path.join(tmpdir(), 'vault-loader-'));
  try {
    await run(directory);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

function put(root: string, relativePath: string, raw: string): string {
  const absolutePath = path.join(root, ...relativePath.split('/'));
  mkdirSync(path.dirname(absolutePath), { recursive: true });
  writeFileSync(absolutePath, raw, 'utf8');
  return absolutePath;
}

function publishedMarkdown(slug = 'demo'): string {
  return `---\nSlug: ${slug}\n发布: true\n简介: Nested demo\n---\n# Demo\n`;
}

function makeContext(siteRoot: string, watcher?: FakeWatcher): FakeContext {
  const entries = new Map<string, DataEntry>();
  const metadata = new Map<string, string>();
  const infoMessages: string[] = [];
  const parseCalls: FakeContext['parseCalls'] = [];
  const renderCalls: FakeContext['renderCalls'] = [];
  let clears = 0;

  const store: DataStore = {
    get: (id) => entries.get(id),
    entries: () => [...entries.entries()],
    set: (entry) => {
      entries.set(entry.id, entry);
      return true;
    },
    values: () => [...entries.values()],
    keys: () => [...entries.keys()],
    delete: (id) => {
      entries.delete(id);
    },
    clear: () => {
      clears++;
      entries.clear();
    },
    has: (id) => entries.has(id),
    addModuleImport: () => {},
  };

  const context: LoaderContext = {
    collection: 'posts',
    store,
    meta: {
      get: (key) => metadata.get(key),
      set: (key, value) => metadata.set(key, value),
      has: (key) => metadata.has(key),
      delete: (key) => {
        metadata.delete(key);
      },
    },
    logger: {
      info: (message: string) => infoMessages.push(message),
      warn: () => {},
      error: () => {},
      debug: () => {},
      fork: () => context.logger,
    } as LoaderContext['logger'],
    config: {
      root: pathToFileURL(`${siteRoot}${path.sep}`),
    } as LoaderContext['config'],
    parseData: async (options) => {
      parseCalls.push(options);
      return options.data;
    },
    renderMarkdown: async (content, options) => {
      renderCalls.push({ content, fileURL: options?.fileURL });
      return { html: '<h1>Demo</h1>' };
    },
    generateDigest: (data) => `digest:${String(data).length}`,
    watcher: watcher as FSWatcher | undefined,
  };

  return {
    context,
    entries,
    infoMessages,
    parseCalls,
    renderCalls,
    clearCount: () => clears,
  };
}

test('loads a nested published note through Astro parsing, rendering, and storage', async () => {
  await withTempDirectory(async (siteRoot) => {
    const vaultRoot = path.join(siteRoot, 'vault');
    const raw = publishedMarkdown();
    const absolutePath = put(vaultRoot, 'nested/demo.md', raw);
    const fake = makeContext(siteRoot);
    const loader = vaultLoader(vaultRoot);

    assert.equal(loader.name, 'xyvora-vault-loader');
    await loader.load(fake.context);

    assert.equal(fake.entries.size, 1);
    const entry = fake.entries.get('nested/demo');
    assert.ok(entry);
    assert.equal(entry.data.Slug, 'demo');
    assert.equal(entry.body, '\n# Demo\n');
    assert.equal(entry.digest, `digest:${raw.length}`);
    assert.deepEqual(entry.rendered, { html: '<h1>Demo</h1>' });
    assert.equal(entry.filePath, 'vault/nested/demo.md');
    assert.ok(entry.filePath?.endsWith('nested/demo.md'));
    assert.deepEqual(fake.parseCalls, [
      {
        id: 'nested/demo',
        data: { Slug: 'demo', 发布: true, 简介: 'Nested demo' },
        filePath: absolutePath,
      },
    ]);
    assert.deepEqual(fake.renderCalls, [
      { content: raw, fileURL: pathToFileURL(absolutePath) },
    ]);
    assert.deepEqual(fake.infoMessages, [
      'Vault scan complete: markdown=1, published=1, drafts=0, unpublished=0, missing Slug=0',
    ]);
  });
});

test('rejects an initial scan when the vault has no publishable posts', async () => {
  await withTempDirectory(async (siteRoot) => {
    const vaultRoot = path.join(siteRoot, 'vault');
    put(vaultRoot, 'private.md', '---\n发布: false\n---\nPrivate\n');
    const fake = makeContext(siteRoot);

    await assert.rejects(vaultLoader(vaultRoot).load(fake.context), {
      name: 'VaultSourceError',
      code: 'NO_POSTS',
    });
  });
});

test('preserves the previous store when preparing a later entry fails', async () => {
  await withTempDirectory(async (siteRoot) => {
    const vaultRoot = path.join(siteRoot, 'vault');
    put(vaultRoot, 'a-first.md', publishedMarkdown('first'));
    put(vaultRoot, 'b-second.md', publishedMarkdown('second'));
    const fake = makeContext(siteRoot);
    const previousEntry: DataEntry = {
      id: 'previous',
      data: { Slug: 'previous' },
      body: 'Previous body',
    };
    fake.entries.set(previousEntry.id, previousEntry);
    fake.context.parseData = async (options) => {
      if (options.id === 'b-second') throw new Error('schema rejected second entry');
      return options.data;
    };

    await assert.rejects(vaultLoader(vaultRoot).load(fake.context), /schema rejected second entry/);

    assert.equal(fake.clearCount(), 0);
    assert.deepEqual([...fake.entries.entries()], [['previous', previousEntry]]);
  });
});

test('attaches watcher listeners once and debounces full rescans inside the vault', async () => {
  await withTempDirectory(async (siteRoot) => {
    const vaultRoot = path.join(siteRoot, 'vault');
    const notePath = put(vaultRoot, 'nested/demo.md', publishedMarkdown());
    const watcher = new FakeWatcher();
    const fake = makeContext(siteRoot, watcher);
    const loader = vaultLoader(vaultRoot);

    await loader.load(fake.context);
    watcher.clearListeners();
    await loader.load(fake.context);

    assert.ok(watcher.watched.every((watchedPath) => watchedPath === vaultRoot));
    for (const event of ['add', 'change', 'unlink']) {
      assert.equal(watcher.listeners.get(event)?.length, 1);
    }

    await loader.load(fake.context);
    for (const event of ['add', 'change', 'unlink']) {
      assert.equal(watcher.listeners.get(event)?.length, 1);
    }

    watcher.emit('change', path.join(siteRoot, 'outside.md'));
    await new Promise((resolve) => setTimeout(resolve, 80));
    assert.equal(fake.clearCount(), 3);

    watcher.emit('add', notePath);
    watcher.emit('change', notePath);
    watcher.emit('unlink', notePath);
    await new Promise((resolve) => setTimeout(resolve, 100));
    assert.equal(fake.clearCount(), 4);
  });
});

test('serializes a watcher rescan before a newer load so the newer data wins', async () => {
  await withTempDirectory(async (siteRoot) => {
    const vaultRoot = path.join(siteRoot, 'vault');
    const notePath = put(vaultRoot, 'demo.md', publishedMarkdown('older'));
    const watcher = new FakeWatcher();
    const fake = makeContext(siteRoot, watcher);
    const loader = vaultLoader(vaultRoot);
    await loader.load(fake.context);

    const watcherParseStarted = deferred();
    const concurrentParseStarted = deferred();
    const releaseWatcherParse = deferred();
    let blockNextParse = true;
    let activeParses = 0;
    let maximumActiveParses = 0;
    fake.context.parseData = async (options) => {
      activeParses++;
      maximumActiveParses = Math.max(maximumActiveParses, activeParses);
      if (activeParses > 1) concurrentParseStarted.resolve();
      try {
        if (blockNextParse) {
          blockNextParse = false;
          watcherParseStarted.resolve();
          await releaseWatcherParse.promise;
        }
        return options.data;
      } finally {
        activeParses--;
      }
    };

    watcher.emit('change', notePath);
    await watcherParseStarted.promise;

    writeFileSync(notePath, publishedMarkdown('newer'), 'utf8');
    const newerLoad = loader.load(fake.context);
    const overlappedBeforeRelease = await Promise.race([
      concurrentParseStarted.promise.then(() => true),
      new Promise<false>((resolve) => setTimeout(() => resolve(false), 500)),
    ]);
    releaseWatcherParse.resolve();

    await newerLoad;
    await waitFor(
      () => fake.infoMessages.length === 3,
      'watcher rescan and newer load did not both complete',
    );

    assert.equal(overlappedBeforeRelease, false);
    assert.equal(maximumActiveParses, 1);
    assert.equal(fake.entries.get('demo')?.data.Slug, 'newer');
  });
});
