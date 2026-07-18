/** Rewrite local Markdown images through the primed published vault index. */
import path from 'node:path';
import { visit, SKIP } from 'unist-util-visit';
import { getVaultIndex, isExternalTarget, resolveVaultAsset } from './vault-index.ts';

export function rehypeImageRewrite() {
  return (tree: any, file: { path?: unknown }) => {
    const index = getVaultIndex();
    const sourceFilePath = typeof file?.path === 'string' ? file.path : undefined;

    visit(tree, 'element', (node: any, childIndex: number | undefined, parent: any) => {
      if (node.tagName !== 'img') return;
      const properties = (node.properties ||= {});
      const rawSource = String(properties.src ?? '').trim();
      if (!rawSource || isExternalTarget(rawSource)) return;

      const resolved = resolveVaultAsset(index, rawSource, sourceFilePath);
      const originalName = displayName(rawSource);
      if (!resolved) {
        console.warn(`[rehype-image-rewrite] Missing image: ${originalName}`);
        if (parent && childIndex !== undefined) {
          parent.children.splice(childIndex, 1, missingImageNode(originalName));
          return [SKIP, childIndex];
        }
        return;
      }

      properties.src = `/_images/${resolved.outputName}`;
      properties.loading = properties.loading || 'lazy';
      properties.alt = properties.alt || originalName;
    });
  };
}

function displayName(source: string): string {
  const withoutQuery = source.split(/[?#]/, 1)[0];
  try {
    return path.basename(decodeURIComponent(withoutQuery));
  } catch {
    return path.basename(withoutQuery);
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
