/**
 * remark plugin: strip Obsidian-only constructs that should not render on the blog.
 *
 *   - ```dataview   / ```dataviewjs   fenced code blocks (Obsidian DB queries)
 *   - ```           fenced code blocks whose body starts with `<%*` (Templater)
 *   - %% comments %% (Obsidian comment syntax, both inline and multi-line)
 *
 * Implements REQ-05-12 (strip %% ... %%) and REQ-05-13 (strip dataview/Templater).
 */
import { visit, SKIP } from 'unist-util-visit';
import type { Root, Code, Text } from 'mdast';

const DATAVIEW_LANGS = new Set(['dataview', 'dataviewjs']);
// Multi-line / inline Obsidian comment: %% ... %%
const OBSIDIAN_COMMENT = /%%[\s\S]*?%%/g;

export function remarkDataviewStrip() {
  return (tree: Root) => {
    // Drop dataview / Templater fenced code blocks.
    visit(tree, 'code', (node: Code, index, parent) => {
      if (index === undefined || !parent) return;

      const lang = (node.lang ?? '').toLowerCase();
      const body = (node.value ?? '').trimStart();

      const isDataview = DATAVIEW_LANGS.has(lang);
      const isTemplater = body.startsWith('<%*') || body.startsWith('<%');

      if (isDataview || isTemplater) {
        (parent as { children: unknown[] }).children.splice(index, 1);
        return [SKIP, index];
      }
    });

    // Strip Obsidian %% ... %% comments from text nodes.
    visit(tree, 'text', (node: Text) => {
      if (typeof node.value !== 'string') return;
      if (!node.value.includes('%%')) return;
      node.value = node.value.replace(OBSIDIAN_COMMENT, '');
    });

    // Also scrub inside paragraph children if %% wraps across the whole paragraph.
    visit(tree, 'paragraph', (para, index, parent) => {
      if (index === undefined || !parent) return;
      // Re-stringify the paragraph's text children to catch patterns that were
      // split across text+formatting nodes. Cheap enough given typical post size.
      let anyContent = false;
      for (const child of para.children) {
        if (child.type === 'text' && child.value.trim() !== '') {
          anyContent = true;
          break;
        }
        if (child.type !== 'text') {
          anyContent = true;
          break;
        }
      }
      if (!anyContent) {
        (parent as { children: unknown[] }).children.splice(index, 1);
        return [SKIP, index];
      }
    });
  };
}
