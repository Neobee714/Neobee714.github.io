/**
 * Theme initialization script — MUST be inlined in <head> to prevent FOUC.
 *
 * BaseLayout should include this as:
 *   <script is:inline>
 *     // paste the content of THEME_INIT_SCRIPT below
 *   </script>
 *
 * Logic:
 *   1. Check localStorage('theme')
 *   2. Fall back to prefers-color-scheme
 *   3. Default to 'dark'
 *   4. Set data-theme on <html> immediately (before paint)
 */

export const THEME_INIT_SCRIPT = `(function(){var t=localStorage.getItem('theme');if(!t){t=window.matchMedia('(prefers-color-scheme:light)').matches?'light':'dark'}document.documentElement.setAttribute('data-theme',t)})();`;
