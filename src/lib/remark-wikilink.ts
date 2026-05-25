/**
 * remark plugin: translate Obsidian wiki-style links.
 *
 *   ![[image.png]]                 -> <img src="/_images/image.png">
 *   ![[image.png|300]]             -> <img src="..." width="300">
 *   ![[image.png|300x200]]         -> <img width="300" height="200">
 *   [[note-name]]                  -> <a href="/post/<slug>/">note-name</a>
 *   [[note-name|Display]]          -> <a href="/post/<slug>/">Display</a>
 *   [[note-name#heading]]          -> <a href="/post/<slug>/#heading-slug">
 *
 * Broken links (target not published / not found) get class "wiki-link broken"
 * and the anchor href becomes "#" plus a title attr explaining.
 *
 * Implements REQ-05-1, REQ-05-2, REQ-05-3, REQ-05-4, REQ-05-5.
 */
import { visit, SKIP } from 'unist-util-visit';
import type { Root, Text, PhrasingContent } from 'mdast';
import { getVaultIndex, normalizeAssetName } from './vault-index.ts';

// Pattern (not a shared /g instance — lastIndex would leak across files).
const WIKI_PATTERN = String.raw`(!?)\[\[([^\]]+)\]\]`;

const IMG_EXTS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg']);

function headingSlug(heading: string): string {
  return heading
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^\w\u4e00-\u9fff\-]/g, '');
}

function fileExt(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot === -1 ? '' : name.slice(dot).toLowerCase();
}

export function remarkWikilink() {
  return (tree: Root) => {
    const idx = getVaultIndex();

    visit(tree, 'text', (node: Text, index, parent) => {
      if (index === undefined || !parent) return;
      if (typeof node.value !== 'string') return;
      if (!node.value.includes('[[')) return;

      const value = node.value;
      const out: PhrasingContent[] = [];
      let cursor = 0;
      let m: RegExpExecArray | null;

      const wikiRe = new RegExp(WIKI_PATTERN, 'g');
      while ((m = wikiRe.exec(value)) !== null) {
        const [full, bang, inner] = m;

        if (m.index > cursor) {
          out.push({ type: 'text', value: value.slice(cursor, m.index) });
        }

        const pipeIdx = inner.indexOf('|');
        const hasPipe = pipeIdx !== -1;
        const targetRaw = (hasPipe ? inner.slice(0, pipeIdx) : inner).trim();
        const aliasOrSize = hasPipe ? inner.slice(pipeIdx + 1).trim() : '';

        const hashIdx = targetRaw.indexOf('#');
        const target = hashIdx === -1 ? targetRaw : targetRaw.slice(0, hashIdx);
        const heading = hashIdx === -1 ? '' : targetRaw.slice(hashIdx + 1);

        if (bang === '!') {
          out.push(buildEmbed(target, aliasOrSize, idx));
        } else {
          out.push(buildWikiLink(target, heading, aliasOrSize, idx));
        }

        cursor = m.index + full.length;
      }

      if (cursor === 0) return;

      if (cursor < value.length) {
        out.push({ type: 'text', value: value.slice(cursor) });
      }

      (parent as { children: PhrasingContent[] }).children.splice(
        index,
        1,
        ...out
      );
      return [SKIP, index + out.length];
    });
  };
}

function buildEmbed(
  target: string,
  sizeSpec: string,
  idx: ReturnType<typeof getVaultIndex>
): PhrasingContent {
  const ext = fileExt(target);
  if (!IMG_EXTS.has(ext)) {
    const href = idx.assetsByName.has(target.toLowerCase())
      ? '/_images/' + normalizeAssetName(target)
      : '#';
    return {
      type: 'link',
      url: href,
      children: [{ type: 'text', value: target }],
      data: {
        hProperties: {
          className: ['embed-link'],
          title: 'Embedded resource',
        },
      },
    } as any;
  }

  const normalized = normalizeAssetName(target);
  const src = '/_images/' + normalized;

  const known = idx.assetsByName.has(target.toLowerCase());
  if (!known) {
    return {
      type: 'html',
      value: `<span class="missing-image" role="img" aria-label="Missing image">⚠ Missing: ${escapeAttr(
        target
      )}</span>`,
    } as any;
  }

  const widthMatch = sizeSpec ? sizeSpec.match(/^(\d+)(?:x(\d+))?/) : null;
  const sizeAttrs: Record<string, string | number> = {};
  if (widthMatch) {
    sizeAttrs.width = Number(widthMatch[1]);
    if (widthMatch[2]) sizeAttrs.height = Number(widthMatch[2]);
  }

  // Emit as raw HTML so we control all attributes (mdast-util-to-hast
  // strips unknown hProperties on image nodes in some edge cases).
  const widthAttr =
    'width' in sizeAttrs ? ` width="${sizeAttrs.width}"` : '';
  const heightAttr =
    'height' in sizeAttrs ? ` height="${sizeAttrs.height}"` : '';

  return {
    type: 'html',
    value: `<img src="${src}" alt="${escapeAttr(
      target
    )}"${widthAttr}${heightAttr} loading="lazy">`,
  } as any;
}

function buildWikiLink(
  target: string,
  heading: string,
  _alias: string,
  idx: ReturnType<typeof getVaultIndex>
): PhrasingContent {
  const lookupKey = target.toLowerCase();
  const slug = idx.notesByName.get(lookupKey);
  const displayText = _alias || target;

  if (slug) {
    const url = heading
      ? `/post/${slug}/#${headingSlug(heading)}`
      : `/post/${slug}/`;
    return {
      type: 'link',
      url,
      children: [{ type: 'text', value: displayText }],
      data: { hProperties: { className: ['wiki-link'] } },
    } as any;
  }

  const isUnpublished = idx.unpublishedNames.has(lookupKey);
  const title = isUnpublished
    ? `未发布：${target}`
    : `不存在的链接：${target}`;

  return {
    type: 'html',
    value: `<span class="wiki-link broken" data-broken="true" title="${escapeAttr(
      title
    )}">${escapeText(displayText)}</span>`,
  } as any;
}

function escapeAttr(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}
function escapeText(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
