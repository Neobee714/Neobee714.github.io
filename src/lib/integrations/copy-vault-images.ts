/** Copy only assets registered while rendering published vault posts. */
import type { AstroIntegration } from 'astro';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { getVaultIndex } from '../vault-index.ts';

export function copyVaultImages(): AstroIntegration {
  return {
    name: 'xyvora:copy-vault-images',
    hooks: {
      'astro:build:start': async () => {
        await fs.rm(path.resolve('public', '_images'), { recursive: true, force: true });
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
