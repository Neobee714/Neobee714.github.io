/**
 * Astro integration: after build, scan all emitted HTML for <img> tags whose
 * src starts with "/_images/", then copy the matching vault asset into the
 * build output directory.
 *
 * The rehype-image-rewrite plugin owns HTML rewriting. This integration is
 * intentionally kept as the final file-copy step because Astro can recreate
 * dist/ after markdown transforms have already run.
 *
 * Each <img> carries the original vault filename in its `alt` attribute,
 * which remark-wikilink writes verbatim. That's the lookup key.
 *
 * Implements REQ-06-1, REQ-06-3 (already lazy via remark), REQ-06-4,
 * REQ-06-6.
 */
import type { AstroIntegration } from 'astro';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { getVaultIndex, normalizeAssetName } from '../vault-index.ts';

// Matches <img ... alt="..." ... src="/_images/..."> OR src-first, alt-last.
const IMG_TAG = /<img\b[^>]*>/gi;
const ATTR = /(\w[\w-]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/g;

export function copyVaultImages(): AstroIntegration {
  return {
    name: 'xyvora:copy-vault-images',
    hooks: {
      'astro:build:done': async ({ dir, logger }) => {
        const distRoot = fileURLToPath(dir);
        const imagesOutDir = path.join(distRoot, '_images');
        const idx = getVaultIndex();

        const copied = new Set<string>();
        let missing = 0;
        let imgTagCount = 0;

        await walkAndProcessHtml(distRoot, async (htmlPath, html) => {
          const tags = html.match(IMG_TAG) ?? [];
          for (const tag of tags) {
            imgTagCount++;
            const attrs = parseAttrs(tag);
            const src = attrs.src ?? '';
            if (!src.startsWith('/_images/')) continue;
            const alt = attrs.alt ?? '';
            const targetKey = alt.toLowerCase();

            const vaultAbsPath = idx.assetsByName.get(targetKey);
            if (!vaultAbsPath) {
              missing++;
              continue;
            }

            const normalized = normalizeAssetName(alt);
            if (copied.has(normalized)) continue;

            try {
              await fs.mkdir(imagesOutDir, { recursive: true });
              await fs.copyFile(
                vaultAbsPath,
                path.join(imagesOutDir, normalized)
              );
              copied.add(normalized);
            } catch (err) {
              logger.warn(
                `Failed to copy ${vaultAbsPath}: ${
                  err instanceof Error ? err.message : String(err)
                }`
              );
            }
          }
        });

        logger.info(
          `Scanned ${imgTagCount} <img> tags; copied ${copied.size} unique assets` +
            (missing > 0 ? `; ${missing} missing (no vault match)` : '')
        );
      },
    },
  };
}

async function walkAndProcessHtml(
  dir: string,
  fn: (htmlPath: string, html: string) => Promise<void>
): Promise<void> {
  let entries;
  try {
    entries = await fs.readdir(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const e of entries) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) {
      await walkAndProcessHtml(full, fn);
    } else if (e.isFile() && e.name.endsWith('.html')) {
      const html = await fs.readFile(full, 'utf8');
      await fn(full, html);
    }
  }
}

function parseAttrs(tag: string): Record<string, string> {
  const result: Record<string, string> = {};
  let m: RegExpExecArray | null;
  const re = new RegExp(ATTR, 'g');
  while ((m = re.exec(tag)) !== null) {
    const key = m[1].toLowerCase();
    const val = m[2] ?? m[3] ?? m[4] ?? '';
    result[key] = decodeHtmlAttr(val);
  }
  return result;
}

function decodeHtmlAttr(s: string): string {
  return s
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)));
}
