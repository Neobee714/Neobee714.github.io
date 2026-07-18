/** Translate Obsidian wiki links and embeds using the primed published vault index. */
import { visit, SKIP } from 'unist-util-visit';
import type { Root, Text, PhrasingContent } from 'mdast';
import { getVaultIndex, resolveVaultAsset, type VaultIndex } from './vault-index.ts';

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
  const cleanName = name.split(/[?#]/, 1)[0];
  const dot = cleanName.lastIndexOf('.');
  return dot === -1 ? '' : cleanName.slice(dot).toLowerCase();
}

export function remarkWikilink() {
  return (tree: Root, file: { path?: unknown }) => {
    const index = getVaultIndex();
    const sourceFilePath = typeof file?.path === 'string' ? file.path : undefined;

    visit(tree, 'text', (node: Text, childIndex, parent) => {
      if (childIndex === undefined || !parent) return;
      if (typeof node.value !== 'string' || !node.value.includes('[[')) return;

      const value = node.value;
      const output: PhrasingContent[] = [];
      let cursor = 0;
      let match: RegExpExecArray | null;
      const wikiPattern = new RegExp(WIKI_PATTERN, 'g');

      while ((match = wikiPattern.exec(value)) !== null) {
        const [full, bang, inner] = match;
        if (match.index > cursor) {
          output.push({ type: 'text', value: value.slice(cursor, match.index) });
        }

        const pipeIndex = inner.indexOf('|');
        const targetRaw = (pipeIndex === -1 ? inner : inner.slice(0, pipeIndex)).trim();
        const aliasOrSize = pipeIndex === -1 ? '' : inner.slice(pipeIndex + 1).trim();
        const hashIndex = targetRaw.indexOf('#');
        const target = hashIndex === -1 ? targetRaw : targetRaw.slice(0, hashIndex);
        const heading = hashIndex === -1 ? '' : targetRaw.slice(hashIndex + 1);

        output.push(
          bang === '!'
            ? buildEmbed(target, aliasOrSize, index, sourceFilePath)
            : buildWikiLink(target, heading, aliasOrSize, index),
        );
        cursor = match.index + full.length;
      }

      if (cursor === 0) return;
      if (cursor < value.length) output.push({ type: 'text', value: value.slice(cursor) });
      (parent as { children: PhrasingContent[] }).children.splice(childIndex, 1, ...output);
      return [SKIP, childIndex + output.length];
    });
  };
}

function buildEmbed(
  target: string,
  sizeSpec: string,
  index: VaultIndex,
  sourceFilePath?: string,
): PhrasingContent {
  const resolved = resolveVaultAsset(index, target, sourceFilePath);
  const isImage = IMG_EXTS.has(fileExt(target));

  if (!resolved) {
    if (!isImage) {
      return {
        type: 'link',
        url: '#',
        children: [{ type: 'text', value: target }],
        data: { hProperties: { className: ['embed-link'], title: 'Embedded resource' } },
      } as any;
    }
    return {
      type: 'html',
      value: `<span class="missing-image" role="img" aria-label="Missing image">⚠ Missing: ${escapeAttr(target)}</span>`,
    } as any;
  }

  const resourceUrl = `/_images/${resolved.outputName}`;
  if (!isImage) {
    return {
      type: 'link',
      url: resourceUrl,
      children: [{ type: 'text', value: target }],
      data: { hProperties: { className: ['embed-link'], title: 'Embedded resource' } },
    } as any;
  }

  const sizeMatch = sizeSpec ? sizeSpec.match(/^(\d+)(?:x(\d+))?/) : null;
  const width = sizeMatch ? ` width="${Number(sizeMatch[1])}"` : '';
  const height = sizeMatch?.[2] ? ` height="${Number(sizeMatch[2])}"` : '';
  return {
    type: 'html',
    value: `<img src="${resourceUrl}" alt="${escapeAttr(target)}"${width}${height} loading="lazy">`,
  } as any;
}

function buildWikiLink(
  target: string,
  heading: string,
  alias: string,
  index: VaultIndex,
): PhrasingContent {
  const lookupKey = target.replace(/\\/g, '/').split('/').at(-1)?.toLowerCase() ?? '';
  const slug = index.notesByName.get(lookupKey);
  const displayText = alias || target;

  if (slug) {
    const url = heading ? `/post/${slug}/#${headingSlug(heading)}` : `/post/${slug}/`;
    return {
      type: 'link',
      url,
      children: [{ type: 'text', value: displayText }],
      data: { hProperties: { className: ['wiki-link'] } },
    } as any;
  }

  return {
    type: 'html',
    value: `<span class="wiki-link broken" data-broken="true" title="${escapeAttr(`不存在或未发布的链接：${target}`)}">${escapeText(displayText)}</span>`,
  } as any;
}

function escapeAttr(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

function escapeText(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
