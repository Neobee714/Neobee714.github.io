/**
 * RSS feed — latest 20 published posts.
 */
import rss from '@astrojs/rss';
import type { APIContext } from 'astro';
import { getPublishedPosts, getDateIso, getPostTitle } from '@/lib/obsidian-parser';

export async function GET(context: APIContext) {
  const posts = await getPublishedPosts();
  const latest = posts.slice(0, 20);

  return rss({
    title: 'Xyvora',
    description: 'Web Security & CTF Notes',
    site: context.site!.toString(),
    items: latest.map((post) => {
      const slug = post.data.Slug!;
      const titleZh = getPostTitle(post);
      const dateStr = getDateIso(post);

      return {
        title: titleZh,
        pubDate: dateStr ? new Date(dateStr) : undefined,
        description: post.data.简介 || titleZh,
        link: `/post/${slug}/`,
      };
    }),
  });
}
