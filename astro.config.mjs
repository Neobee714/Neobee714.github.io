// @ts-check
import { defineConfig } from 'astro/config';
import { loadEnv } from 'vite';
import tailwindcss from '@tailwindcss/vite';
import react from '@astrojs/react';

import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import rehypeSlug from 'rehype-slug';
import rehypeAutolinkHeadings from 'rehype-autolink-headings';

import { slugUniquenessCheck } from './src/lib/integrations/slug-check.ts';
import { copyVaultImages } from './src/lib/integrations/copy-vault-images.ts';
import { remarkDataviewStrip } from './src/lib/remark-dataview-strip.ts';
import { remarkCallout } from './src/lib/remark-callout.ts';
import { remarkWikilink } from './src/lib/remark-wikilink.ts';
import { remarkMermaid } from './src/lib/remark-mermaid.ts';
import { rehypeImageRewrite } from './src/lib/rehype-image-rewrite.ts';

// Load ASTRO_VAULT_PATH / PUBLIC_SITE_URL from .env into process.env so
// the content loader and integrations can read them.
const env = loadEnv(process.env.NODE_ENV || 'development', process.cwd(), '');
for (const key of ['ASTRO_VAULT_PATH', 'PUBLIC_SITE_URL']) {
  if (env[key] && !process.env[key]) {
    process.env[key] = env[key];
  }
}

export default defineConfig({
  site: process.env.PUBLIC_SITE_URL || 'https://neobee.top',
  integrations: [react(), slugUniquenessCheck(), copyVaultImages()],
  markdown: {
    remarkPlugins: [
      remarkDataviewStrip, // drop dataview / templater / %%comments%%
      remarkCallout,       // > [!note] -> <aside class="callout ...">
      remarkWikilink,      // [[note]] / ![[image]]
      remarkMermaid,       // ```mermaid -> placeholder div
      remarkMath,          // $...$ / $$...$$
    ],
    rehypePlugins: [
      rehypeSlug,
      [rehypeAutolinkHeadings, { behavior: 'wrap' }],
      rehypeKatex,
      rehypeImageRewrite,
    ],
    shikiConfig: {
      themes: {
        light: 'github-light',
        dark: 'github-dark-dimmed',
      },
      wrap: true,
    },
  },
  vite: {
    plugins: [tailwindcss()],
  },
});
