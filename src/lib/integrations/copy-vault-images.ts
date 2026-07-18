/** Copy only assets registered while rendering published vault posts. */
import type { AstroIntegration } from 'astro';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { getVaultIndex, type VaultIndex } from '../vault-index.ts';

let reconciliationSequence = 0;

function isMissingPath(error: unknown): boolean {
  return (error as NodeJS.ErrnoException)?.code === 'ENOENT';
}

export async function reconcileDevVaultAssets(
  index: VaultIndex,
  publicDirectory: URL | string,
): Promise<void> {
  const publicRoot =
    publicDirectory instanceof URL ? fileURLToPath(publicDirectory) : path.resolve(publicDirectory);
  const outputDirectory = path.join(publicRoot, '_images');
  const suffix = `${process.pid}-${Date.now()}-${reconciliationSequence++}`;
  const stagedDirectory = path.join(publicRoot, `._images-next-${suffix}`);
  const previousDirectory = path.join(publicRoot, `._images-previous-${suffix}`);
  const resolvedAssets = [...index.resolvedAssetsByOutputName.entries()].sort(([left], [right]) =>
    left.localeCompare(right),
  );
  let previousMoved = false;
  let stagedInstalled = false;

  try {
    await fs.mkdir(stagedDirectory, { recursive: true });
    for (const [outputName, absolutePath] of resolvedAssets) {
      await fs.copyFile(absolutePath, path.join(stagedDirectory, outputName));
    }

    try {
      await fs.rename(outputDirectory, previousDirectory);
      previousMoved = true;
    } catch (error) {
      if (!isMissingPath(error)) throw error;
    }

    await fs.rename(stagedDirectory, outputDirectory);
    stagedInstalled = true;
    if (previousMoved) {
      await fs.rm(previousDirectory, { recursive: true, force: true }).catch(() => {});
    }
  } catch (cause) {
    await fs.rm(stagedDirectory, { recursive: true, force: true }).catch(() => {});
    if (previousMoved && !stagedInstalled) {
      await fs.rename(previousDirectory, outputDirectory).catch(() => {});
    }
    throw new Error(`Failed to reconcile ${resolvedAssets.length} dev vault assets`, { cause });
  }
}

export function copyVaultImages(): AstroIntegration {
  let publicDirectory = path.resolve('public');

  return {
    name: 'xyvora:copy-vault-images',
    hooks: {
      'astro:config:done': ({ config }) => {
        publicDirectory = fileURLToPath(config.publicDir);
      },
      'astro:build:start': async () => {
        await fs.rm(path.join(publicDirectory, '_images'), { recursive: true, force: true });
      },
      'astro:build:done': async ({ dir, logger }) => {
        const index = getVaultIndex();
        const outputDirectory = path.join(fileURLToPath(dir), '_images');
        const resolvedAssets = [...index.resolvedAssetsByOutputName.entries()].sort(([left], [right]) =>
          left.localeCompare(right),
        );
        let copied = 0;

        if (resolvedAssets.length > 0) {
          await fs.mkdir(outputDirectory, { recursive: true });
        }
        for (const [outputName, absolutePath] of resolvedAssets) {
          try {
            await fs.copyFile(absolutePath, path.join(outputDirectory, outputName));
            copied++;
          } catch (error) {
            logger.warn(
              `Failed to copy ${absolutePath}: ${
                error instanceof Error ? error.message : String(error)
              }`,
            );
          }
        }

        logger.info(
          `Vault assets: copied ${copied}; missing ${index.missingReferences.size}`,
        );
      },
    },
  };
}
