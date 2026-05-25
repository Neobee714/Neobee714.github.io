/**
 * remarkFilename — extract filename from code block lang string.
 *
 * Syntax: ```python:exploit.py
 *   node.lang  = "python:exploit.py"
 *   → splits into lang="python", filename="exploit.py"
 *   → sets node.lang = "python"
 *   → sets node.data.hProperties.dataFilename = "exploit.py"
 *
 * If lang contains no colon, the node is left untouched.
 */

import type { Root } from 'mdast';
import { visit } from 'unist-util-visit';

export function remarkFilename() {
  return (tree: Root) => {
    visit(tree, 'code', (node) => {
      if (!node.lang || !node.lang.includes(':')) return;

      const idx = node.lang.indexOf(':');
      const lang = node.lang.slice(0, idx);
      const filename = node.lang.slice(idx + 1);

      if (!lang || !filename) return;

      node.lang = lang;

      node.data = node.data || {};
      node.data.hProperties = node.data.hProperties || {};
      (node.data.hProperties as Record<string, unknown>).dataFilename = filename;
    });
  };
}
