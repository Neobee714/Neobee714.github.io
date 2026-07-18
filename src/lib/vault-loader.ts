import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import type { Loader, LoaderContext } from 'astro/loaders';
import { resolveVaultPath } from './resolve-vault-path.ts';
import { discoverPublishedPosts } from './vault-source.ts';

const WATCH_DEBOUNCE_MS = 50;

function toSiteRelativePath(root: string, absolutePath: string): string | undefined {
  const relative = path.relative(root, absolutePath);
  if (path.isAbsolute(relative) || path.win32.isAbsolute(relative)) return undefined;
  return relative.split(path.sep).join('/');
}

function isInside(root: string, candidate: string): boolean {
  const relative = path.relative(root, path.resolve(candidate));
  return (
    relative === '' ||
    (relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative))
  );
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

async function scanVault(context: LoaderContext, vaultRoot: string): Promise<void> {
  const result = await discoverPublishedPosts(vaultRoot);
  const siteRoot = fileURLToPath(context.config.root);
  const entries: Array<Parameters<LoaderContext['store']['set']>[0]> = [];

  for (const post of result.posts) {
    const data = await context.parseData({
      id: post.id,
      data: post.frontmatter,
      filePath: post.absolutePath,
    });
    const rendered = await context.renderMarkdown(post.raw, {
      fileURL: pathToFileURL(post.absolutePath),
    });

    const filePath = toSiteRelativePath(siteRoot, post.absolutePath);
    entries.push({
      id: post.id,
      data,
      body: post.body,
      ...(filePath === undefined ? {} : { filePath }),
      digest: context.generateDigest(post.raw),
      rendered,
    });
  }

  context.store.clear();
  for (const entry of entries) context.store.set(entry);

  const { markdown, published, drafts, unpublished, missingSlug } = result.stats;
  context.logger.info(
    `Vault scan complete: markdown=${markdown}, published=${published}, drafts=${drafts}, ` +
      `unpublished=${unpublished}, missing Slug=${missingSlug}`,
  );
}

export function vaultLoader(rawPath?: string): Loader {
  type Watcher = NonNullable<LoaderContext['watcher']>;

  let latestContext: LoaderContext;
  let latestRoot = '';
  let attachedWatcher: Watcher | undefined;
  let debounceTimer: ReturnType<typeof setTimeout> | undefined;
  let scanQueue = Promise.resolve();

  const enqueueScan = (context: LoaderContext, vaultRoot: string): Promise<void> => {
    const job = scanQueue.then(() => scanVault(context, vaultRoot));
    scanQueue = job.catch(() => {});
    return job;
  };

  const scheduleRescan = (): void => {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      debounceTimer = undefined;
      const context = latestContext;
      const vaultRoot = latestRoot;
      void enqueueScan(context, vaultRoot).catch((error: unknown) => {
        context.logger.error(`Vault rescan failed: ${errorMessage(error)}`);
      });
    }, WATCH_DEBOUNCE_MS);
  };

  const onVaultChange = (changedPath: string): void => {
    if (isInside(latestRoot, changedPath)) scheduleRescan();
  };

  const onWatcherError = (error: unknown): void => {
    latestContext.logger.error(`Vault watcher error: ${errorMessage(error)}`);
  };

  const bindWatcher = (watcher: LoaderContext['watcher'], vaultRoot: string): void => {
    if (attachedWatcher) {
      for (const event of ['add', 'change', 'unlink'] as const) {
        attachedWatcher.off(event, onVaultChange);
      }
      attachedWatcher.off('error', onWatcherError);
      attachedWatcher = undefined;
    }

    if (!watcher) return;
    watcher.add(vaultRoot);
    for (const event of ['add', 'change', 'unlink'] as const) {
      watcher.on(event, onVaultChange);
    }
    watcher.on('error', onWatcherError);
    attachedWatcher = watcher;
  };

  return {
    name: 'xyvora-vault-loader',
    async load(context) {
      const vaultRoot = resolveVaultPath(rawPath);
      latestContext = context;
      latestRoot = vaultRoot;

      await enqueueScan(context, vaultRoot);
      bindWatcher(context.watcher, vaultRoot);
    },
  };
}
