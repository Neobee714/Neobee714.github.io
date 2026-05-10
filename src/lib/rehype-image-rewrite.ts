/**
 * rehype plugin: rewrite local Obsidian image references to stable web paths.
 *
 * - External http(s) images are left unchanged.
 * - Local images are resolved through the vault asset index.
 * - Resolved files are copied to dist/_images/<normalized-name>.
 * - Missing files become <span class="missing-image">Missing: ...</span>.
 */
import fs from 'node:fs';
import path from 'node:path';
import { visit, SKIP } from 'unist-util-visit';
import { getVaultIndex, normalizeAssetName } from './vault-index.ts';

const copied = new Set<string>();

export function rehypeImageRewrite() {
  return (tree: any) => {
    const idx = getVaultIndex();

    visit(tree, 'element', (node: any, index: number | undefined, parent: any) => {
      if (node.tagName !== 'img') return;
      const props = (node.properties ||= {});
      const rawSrc = String(props.src ?? '').trim();
      if (!rawSrc || isExternal(rawSrc) || rawSrc.startsWith('data:')) return;

      const originalName = getOriginalName(rawSrc, props.alt);
      const assetPath = idx.assetsByName.get(originalName.toLowerCase());

      if (!assetPath) {
        console.warn(`[rehype-image-rewrite] Missing image: ${originalName}`);
        if (parent && index !== undefined) {
          parent.children.splice(index, 1, missingImageNode(originalName));
          return [SKIP, index];
        }
        return;
      }

      const normalized = normalizeAssetName(originalName);
      copyAsset(assetPath, normalized);

      props.src = `/_images/${normalized}`;
      props.loading = props.loading || 'lazy';
      props.alt = props.alt || originalName;
    });
  };
}

function isExternal(src: string): boolean {
  return /^https?:\/\//i.test(src) || src.startsWith('//');
}

function getOriginalName(src: string, alt: unknown): string {
  const altText = typeof alt === 'string' ? alt.trim() : '';
  if (altText) return altText;

  const withoutQuery = src.split(/[?#]/, 1)[0];
  const decoded = decodeURIComponent(withoutQuery);
  return path.basename(decoded);
}

function copyAsset(assetPath: string, normalized: string): void {
  if (copied.has(normalized)) return;

  const outDir = path.resolve('dist', '_images');
  const outFile = path.join(outDir, normalized);

  try {
    fs.mkdirSync(outDir, { recursive: true });
    fs.copyFileSync(assetPath, outFile);
    copied.add(normalized);
  } catch (err) {
    console.warn(
      `[rehype-image-rewrite] Failed to copy ${assetPath}: ${
        err instanceof Error ? err.message : String(err)
      }`
    );
  }
}

function missingImageNode(name: string) {
  return {
    type: 'element',
    tagName: 'span',
    properties: {
      className: ['missing-image'],
      role: 'img',
      ariaLabel: 'Missing image',
    },
    children: [{ type: 'text', value: `Missing: ${name}` }],
  };
}
