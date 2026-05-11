/**
 * remark plugin: convert Obsidian ==highlight== syntax to <mark> elements.
 */
import { visit } from 'unist-util-visit';
import type { Root, Text } from 'mdast';

const HIGHLIGHT_RE = /==(.*?)==/g;

export function remarkHighlight() {
  return (tree: Root) => {
    visit(tree, 'text', (node: Text, index, parent) => {
      if (index === undefined || !parent) return;
      if (!node.value.includes('==')) return;

      const value = node.value;
      const children: any[] = [];
      let lastIdx = 0;

      const re = new RegExp(HIGHLIGHT_RE, 'g');
      let match;
      while ((match = re.exec(value)) !== null) {
        if (match.index > lastIdx) {
          children.push({ type: 'text', value: value.slice(lastIdx, match.index) });
        }
        children.push({
          type: 'html',
          value: `<mark>${match[1]}</mark>`,
        });
        lastIdx = match.index + match[0].length;
      }

      if (lastIdx === 0) return;
      if (lastIdx < value.length) {
        children.push({ type: 'text', value: value.slice(lastIdx) });
      }

      (parent as any).children.splice(index, 1, ...children);
      return index + children.length;
    });
  };
}
