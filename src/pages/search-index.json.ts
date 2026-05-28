/**
 * Build-time endpoint that generates /search-index.json
 * containing published posts data for client-side search.
 */
import type { APIRoute } from 'astro';
import { getPublishedPosts, getCategory, getPostTitle } from '@/lib/obsidian-parser';

export const GET: APIRoute = async () => {
  const posts = await getPublishedPosts();

  const index = posts.map((post) => {
    const titleZh = getPostTitle(post);
    return {
      slug: post.data.Slug!,
      titleZh,
      category: getCategory(post),
      tags: post.data.tags || [],
      summary: post.data.简介 || '',
    };
  });

  return new Response(JSON.stringify(index), {
    headers: { 'Content-Type': 'application/json' },
  });
};
