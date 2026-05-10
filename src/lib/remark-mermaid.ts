/**
 * remark plugin: replace ```mermaid code blocks with a placeholder <div>
 * that the client-side MermaidIsland (Phase 4) will hydrate.
 *
 * Implements REQ-05-10.
 */
import { visit, SKIP } from 'unist-util-visit';
import type { Root, Code } from 'mdast';

export function remarkMermaid() {
  return (tree: Root) => {
    visit(tree, 'code', (node: Code, index, parent) => {
      if (index === undefined || !parent) return;
      if ((node.lang ?? '').toLowerCase() !== 'mermaid') return;

      const source = node.value ?? '';
      const html = {
        type: 'html',
        value: `<div class="mermaid-placeholder" data-mermaid>${escapeHtml(
          source
        )}</div>`,
      };
      (parent as { children: unknown[] }).children.splice(index, 1, html);
      return [SKIP, index];
    });
  };
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
