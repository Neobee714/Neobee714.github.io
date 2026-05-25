/**
 * remark plugin: convert Obsidian callout blockquotes into semantic <aside>.
 *
 * Input (Obsidian):
 *   > [!warning] Optional title
 *   > Body line 1
 *   > Body line 2
 *
 * Output (hast via `data.hName` / `data.hProperties`):
 *   <aside class="callout callout-warning" data-callout-type="warning">
 *     <div class="callout-title">
 *       <span class="callout-icon" aria-hidden="true">⚠️</span>
 *       <span class="callout-title-text">Optional title</span>
 *     </div>
 *     <div class="callout-body">
 *       ...markdown children...
 *     </div>
 *   </aside>
 *
 * Supports folding:
 *   > [!note]-  Collapsed by default  -> <details>
 *   > [!tip]+   Expanded by default   -> <details open>
 *
 * Implements REQ-05-6.
 */
import { visit } from 'unist-util-visit';
import type { Root, Blockquote, Paragraph, Text } from 'mdast';

const HEADER = /^\[!(\w+)\]([-+]?)\s*(.*)$/;

// Canonical type -> icon glyph. Unknown types fall back to `.callout-note`.
const TYPE_ICONS: Record<string, string> = {
  note: 'ℹ️',
  abstract: '📄',
  summary: '📄',
  info: 'ℹ️',
  tip: '💡',
  hint: '💡',
  todo: '✅',
  success: '✅',
  check: '✅',
  done: '✅',
  question: '❓',
  help: '❓',
  faq: '❓',
  warning: '⚠️',
  caution: '⚠️',
  attention: '⚠️',
  failure: '❌',
  fail: '❌',
  missing: '❌',
  danger: '🚫',
  error: '🚫',
  bug: '🐛',
  example: '📝',
  quote: '💬',
  cite: '💬',
};

// Alias -> canonical class suffix.
const TYPE_ALIASES: Record<string, string> = {
  summary: 'abstract',
  hint: 'tip',
  check: 'success',
  done: 'success',
  help: 'question',
  faq: 'question',
  caution: 'warning',
  attention: 'warning',
  fail: 'failure',
  missing: 'failure',
  error: 'danger',
  cite: 'quote',
  todo: 'success',
};

function canonicalType(raw: string): string {
  const lower = raw.toLowerCase();
  return TYPE_ALIASES[lower] ?? lower;
}

export function remarkCallout() {
  return (tree: Root) => {
    visit(tree, 'blockquote', (node: Blockquote) => {
      const first = node.children[0];
      if (!first || first.type !== 'paragraph') return;
      const firstChild = (first as Paragraph).children[0];
      if (!firstChild || firstChild.type !== 'text') return;

      const text = (firstChild as Text).value;
      const eol = text.search(/\r?\n/);
      const firstLine = (eol === -1 ? text : text.slice(0, eol)).trimEnd();
      const rest = eol === -1 ? '' : text.slice(eol + (text[eol] === '\r' ? 2 : 1));

      const m = firstLine.match(HEADER);
      if (!m) return;

      const [, rawType, fold, title] = m;
      const type = canonicalType(rawType);
      const icon = TYPE_ICONS[type] || TYPE_ICONS[canonicalType(rawType)] || 'ℹ️';

      // Rewrite first text child: drop the [!type] marker, keep any body text
      // that followed it on subsequent lines of the same text node.
      if (rest) {
        (firstChild as Text).value = rest;
      } else {
        // First text had only the marker. Remove it; if paragraph is now empty,
        // drop the paragraph entirely.
        (first as Paragraph).children.shift();
        if ((first as Paragraph).children.length === 0) {
          node.children.shift();
        }
      }

      // Encode callout metadata via mdast `data` so mdast-util-to-hast will
      // emit the desired element and attributes.
      const tagName = fold ? 'details' : 'aside';
      const extraAttrs: Record<string, string | boolean> = {};
      if (fold === '+') {
        extraAttrs.open = true;
      }

      node.data = node.data || {};
      (node.data as any).hName = tagName;
      (node.data as any).hProperties = {
        className: ['callout', `callout-${type}`],
        'data-callout-type': type,
        ...extraAttrs,
      };

      // Insert a title row as the first child. For <details>, we use <summary>.
      const titleNode: any = {
        type: 'paragraph',
        data: {
          hName: fold ? 'summary' : 'div',
          hProperties: { className: ['callout-title'] },
        },
        children: [
          {
            type: 'html',
            value: `<span class="callout-icon" aria-hidden="true">${icon}</span>`,
          },
          {
            type: 'html',
            value: `<span class="callout-title-text">${escapeHtml(
              title.trim() || capitalize(type)
            )}</span>`,
          },
        ],
      };

      // Wrap the remaining body children in a div for styling hooks.
      const bodyChildren = node.children;
      const bodyWrap: any = {
        type: 'paragraph', // wrapper node; hast tag overridden below
        data: {
          hName: 'div',
          hProperties: { className: ['callout-body'] },
        },
        children: bodyChildren,
      };

      node.children = bodyChildren.length > 0 ? [titleNode, bodyWrap] : [titleNode];
    });
  };
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
