/**
 * Astro integration: fail the build if two published posts share a Slug.
 *
 * This runs at `astro:config:done` (early enough to abort the build)
 * by reading .md files directly from the filesystem — it does NOT use
 * `astro:content`, which is unavailable outside of render contexts.
 *
 * Note: getPublishedPosts() in obsidian-parser.ts also guards against
 * duplicates; this integration is a belt-and-suspenders early check.
 *
 * Implements REQ-03-4.
 */
import type { AstroIntegration } from 'astro';
import fs from 'node:fs/promises';
import path from 'node:path';
import { isDraftStatus, normalizeFrontmatterScalar } from '../publishing.ts';
import { resolveVaultPath } from '../resolve-vault-path.ts';

async function walkMd(dir: string, out: string[] = []): Promise<string[]> {
  let entries;
  try {
    entries = await fs.readdir(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const e of entries) {
    if (e.name.startsWith('.') || e.name === 'Templates' || e.name === 'node_modules') continue;
    const full = path.join(dir, e.name);
    if (e.isDirectory()) {
      await walkMd(full, out);
    } else if (e.isFile() && e.name.endsWith('.md') && !e.name.endsWith('.en.md')) {
      out.push(full);
    }
  }
  return out;
}

function extractFrontmatter(raw: string): Record<string, string> | null {
  if (!raw.startsWith('---')) return null;
  const end = raw.indexOf('\n---', 3);
  if (end === -1) return null;
  const block = raw.slice(3, end);
  const result: Record<string, string> = {};
  for (const line of block.split(/\r?\n/)) {
    // Only match scalar "key: value" lines; list values are handled
    // later by the full YAML parser inside Astro's content pipeline.
    const m = line.match(/^([^\s:][^:]*?):\s*(.*)$/);
    if (m) {
      const [, k, v] = m;
      result[k.trim()] = v.trim();
    }
  }
  return result;
}

export function isPublishedFm(fm: Record<string, string>): boolean {
  return hasPublishFlag(fm) && !isDraftFm(fm) && Boolean(normalizeFrontmatterScalar(fm['Slug']));
}

function hasPublishFlag(fm: Record<string, string>): boolean {
  const v = normalizeFrontmatterScalar(fm['发布']).toLowerCase();
  return v === 'true' || v === 'yes' || v === '是';
}

function isDraftFm(fm: Record<string, string>): boolean {
  return isDraftStatus(fm['状态']);
}

export function slugUniquenessCheck(): AstroIntegration {
  return {
    name: 'xyvora:slug-uniqueness-check',
    hooks: {
      'astro:config:done': async ({ logger }) => {
        const vaultPath =
          process.env.ASTRO_VAULT_PATH?.trim() || './vault';
        const vaultAbs = resolveVaultPath(vaultPath);

        // Only scan SecNotes/ (blog content root)
        const scanRoot = path.join(vaultAbs, 'SecNotes');

        let files: string[];
        try {
          files = await walkMd(scanRoot);
        } catch {
          logger.warn(
            `Slug uniqueness check skipped: vault path not accessible (${scanRoot})`
          );
          return;
        }

        const seen = new Map<string, string>();
        const conflicts: string[] = [];
        let published = 0;
        let missingSlug = 0;

        for (const file of files) {
          const raw = await fs.readFile(file, 'utf8');
          const fm = extractFrontmatter(raw);
          if (!fm) continue;
          if (hasPublishFlag(fm) && !isDraftFm(fm) && !normalizeFrontmatterScalar(fm['Slug'])) {
            missingSlug++;
          }
          if (!isPublishedFm(fm)) continue;

          const slug = normalizeFrontmatterScalar(fm['Slug']);

          published++;
          const prior = seen.get(slug);
          if (prior && prior !== file) {
            conflicts.push(
              `  Slug "${slug}" used by:\n` +
                `    - ${path.relative(vaultAbs, prior)}\n` +
                `    - ${path.relative(vaultAbs, file)}`
            );
          } else {
            seen.set(slug, file);
          }
        }

        if (conflicts.length > 0) {
          const msg =
            `Duplicate Slug detected (${conflicts.length} conflict(s)):\n` +
            conflicts.join('\n');
          logger.error(msg);
          throw new Error(msg);
        }

        logger.info(
          `Slug uniqueness check passed (${published} published posts, ${seen.size} unique slugs)`
        );
        if (missingSlug > 0) {
          logger.warn(
            `Skipped ${missingSlug} published non-draft note(s) without Slug`
          );
        }
      },
    },
  };
}
