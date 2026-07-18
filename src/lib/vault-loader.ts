import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import type { Loader, LoaderContext } from 'astro/loaders';
import { resolveVaultPath } from './resolve-vault-path.ts';
import { discoverPublishedPosts } from './vault-source.ts';

const WATCH_DEBOUNCE_MS = 50;

function toPosixRelative(root: string, absolutePath: string): string {
  return path.relative(root, absolutePath).split(path.sep).join('/');
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
      filePath: toPosixRelative(siteRoot, post.absolutePath),
      digest: context.generateDigest(post.raw),
      rendered,
    });
  }

  const { markdown, published, drafts, unpublished, missingSlug } = result.stats;
  context.logger.info(
    `Vault scan complete: markdown=${markdown}, published=${published}, drafts=${drafts}, ` +
      `unpublished=${unpublished}, missing Slug=${missingSlug}`,
  );
}

export function vaultLoader(rawPath?: string): Loader {
  let latestContext: LoaderContext;
  let latestRoot = '';
  let watcherAttached = false;
  let debounceTimer: ReturnType<typeof setTimeout> | undefined;
  let rescanPromise = Promise.resolve();

  const scheduleRescan = (): void => {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      debounceTimer = undefined;
      rescanPromise = rescanPromise
        .then(() => scanVault(latestContext, latestRoot))
        .catch((error: unknown) => {
          latestContext.logger.error(`Vault rescan failed: ${errorMessage(error)}`);
        });
    }, WATCH_DEBOUNCE_MS);
  };

  return {
    name: 'xyvora-vault-loader',
    async load(context) {
      const vaultRoot = resolveVaultPath(rawPath);
      latestContext = context;
      latestRoot = vaultRoot;

      await scanVault(context, vaultRoot);

      if (!context.watcher || watcherAttached) return;
      watcherAttached = true;
      context.watcher.add(vaultRoot);

      for (const event of ['add', 'change', 'unlink'] as const) {
        context.watcher.on(event, (changedPath) => {
          if (isInside(latestRoot, changedPath)) scheduleRescan();
        });
      }
      context.watcher.on('error', (error) => {
        latestContext.logger.error(`Vault watcher error: ${errorMessage(error)}`);
      });
    },
  };
}
