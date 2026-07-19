import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import {
  hasPublishFlag,
  isDraftStatus,
  isLockedStatus,
  normalizeFrontmatterScalar,
} from '../src/lib/publishing.ts';

test('SearchModal does not render search data through template innerHTML', () => {
  const source = readFileSync('src/components/SearchModal.astro', 'utf8');

  assert.doesNotMatch(source, /results\.innerHTML\s*=\s*matches/s);
});

test('Homepage reveal keeps headings intact instead of rebuilding per-word DOM', () => {
  const source = readFileSync('src/components/Homepage.astro', 'utf8');

  assert.doesNotMatch(source, /target\.innerHTML\s*=/);
  assert.doesNotMatch(source, /word-reveal/);
  assert.doesNotMatch(source, /document\.createElement\('span'\)/);
});

test('scroll widgets bind global scroll listeners once', () => {
  const backToTop = readFileSync('src/components/BackToTop.astro', 'utf8');
  const readingProgress = readFileSync('src/components/ReadingProgress.astro', 'utf8');

  assert.doesNotMatch(backToTop, /let backToTopScrollBound = false/);
  assert.match(backToTop, /__blogBackToTop/);
  assert.match(backToTop, /if \(!backToTopState\.scrollBound\)/);
  assert.match(backToTop, /if \(!backToTopState\.afterSwapBound\)/);

  assert.doesNotMatch(readingProgress, /let readingProgressScrollBound = false/);
  assert.match(readingProgress, /__blogReadingProgress/);
  assert.match(readingProgress, /if \(!readingProgressState\.scrollBound\)/);
  assert.match(readingProgress, /if \(!readingProgressState\.afterSwapBound\)/);
});

test('TableOfContents cleans observers before reinitializing after navigation', () => {
  const source = readFileSync('src/components/TableOfContents.astro', 'utf8');

  assert.match(source, /__blogToc/);
  assert.match(source, /tocState\.cleanup\(\);/);
  assert.match(source, /if \(!tocState\.afterSwapBound\)/);
  assert.match(source, /window\.removeEventListener\('hashchange'/);
  assert.match(source, /observer\.disconnect\(\)/);
});

test('header toggles use once-bound event delegation for swapped DOM', () => {
  const themeToggle = readFileSync('src/components/ThemeToggle.astro', 'utf8');

  assert.doesNotMatch(themeToggle, /let themeToggleBound = false/);
  assert.match(themeToggle, /__blogThemeToggle/);
  assert.match(themeToggle, /closest\('#theme-toggle'\)/);
});

test('active blog UI contains no English translation experience', () => {
  // Giscus' data-lang config controls the third-party widget locale and is intentionally excluded.
  const giscusSource = readFileSync('src/components/Giscus.astro', 'utf8');
  const activeFiles = [
    'src/components/Header.astro',
    'src/components/Homepage.astro',
    'src/components/PostCard.astro',
    'src/components/FeaturedPost.astro',
    'src/components/TableOfContents.astro',
    'src/components/LockedBanner.astro',
    'src/components/CodeBlockWrapper.astro',
    'src/layouts/PostLayout.astro',
    'src/layouts/BaseLayout.astro',
    'src/pages/post/[slug].astro',
    'src/pages/about.astro',
    'src/pages/404.astro',
    'src/pages/archives.astro',
    'src/pages/categories/index.astro',
    'src/pages/tags/index.astro',
    'src/lib/obsidian-parser.ts',
    'src/lib/theme-init.ts',
    'src/styles/global.css',
  ];
  const activeSources = activeFiles
    .map((file) => readFileSync(file, 'utf8'))
    .join('\n');

  assert.equal(existsSync('src/components/LangToggle.astro'), false);
  assert.match(giscusSource, /data-lang="zh-CN"/);
  assert.doesNotMatch(activeSources, /lang-en|lang-zh|data-lang|LangToggle/);
  assert.doesNotMatch(
    activeSources,
    /getPostWithTranslation|translationsBySlug|translationsBySourceId|postEn|headingsEn/,
  );
});

test('Giscus theme observer is only attached once', () => {
  const source = readFileSync('src/components/Giscus.astro', 'utf8');

  assert.doesNotMatch(source, /let giscusThemeObserverBound = false/);
  assert.match(source, /__blogGiscus/);
  assert.match(source, /if \(document\.getElementById\('giscus-wrapper'\)\)/);
  assert.match(source, /if \(!giscusState\.themeObserverBound\)/);
});

test('MermaidIsland re-renders on swaps and theme changes with strict SVG handling', () => {
  const source = readFileSync('src/components/islands/MermaidIsland.tsx', 'utf8');

  assert.match(source, /securityLevel:\s*'strict'/);
  assert.match(source, /document\.addEventListener\('astro:after-swap'/);
  assert.match(source, /new MutationObserver/);
  assert.match(source, /attributeFilter:\s*\['data-theme'\]/);
  assert.doesNotMatch(source, /el\.innerHTML\s*=\s*svg/);
  assert.match(source, /replaceChildren\(/);
});

test('search modal and preview scripts keep one global after-swap hook', () => {
  const searchModal = readFileSync('src/components/SearchModal.astro', 'utf8');
  const homepage = readFileSync('src/components/Homepage.astro', 'utf8');
  const codeBlocks = readFileSync('src/components/CodeBlockWrapper.astro', 'utf8');

  assert.doesNotMatch(searchModal, /let searchKeyboardBound = false/);
  assert.match(searchModal, /__blogSearchModal/);
  assert.match(searchModal, /if \(!searchState\.keyboardBound\)/);
  assert.match(searchModal, /if \(!searchState\.afterSwapBound\)/);

  assert.match(homepage, /__blogHomepageReveal/);
  assert.match(homepage, /homepageRevealState\.cleanup\(\);/);
  assert.match(homepage, /if \(!homepageRevealState\.afterSwapBound\)/);

  assert.match(codeBlocks, /__blogCodeBlocks/);
  assert.match(codeBlocks, /if \(!codeBlockState\.afterSwapBound\)/);
});

test('tag and category path segments are URL encoded in hrefs', () => {
  const tagsIndex = readFileSync('src/pages/tags/index.astro', 'utf8');
  const categoriesIndex = readFileSync('src/pages/categories/index.astro', 'utf8');
  const postLayout = readFileSync('src/layouts/PostLayout.astro', 'utf8');
  const homepage = readFileSync('src/components/Homepage.astro', 'utf8');

  assert.match(tagsIndex, /\/tags\/\$\{encodeURIComponent\(tag\)\}/);
  assert.match(categoriesIndex, /\/categories\/\$\{encodeURIComponent\(cat\)\}/);
  assert.match(postLayout, /\/tags\/\$\{encodeURIComponent\(tag\)\}/);
  assert.match(homepage, /\/categories\/\$\{encodeURIComponent\(topic\.name\)\}/);
});

test('publishing helpers classify frontmatter flags, drafts, and Slugs', () => {
  assert.equal(hasPublishFlag('"true"'), true);
  assert.equal(hasPublishFlag("'yes'"), true);
  assert.equal(hasPublishFlag('false'), false);
  assert.equal(isDraftStatus('进行中'), true);
  assert.equal(isDraftStatus("'draft'"), true);
  assert.equal(isDraftStatus('writing'), true);
  assert.equal(isDraftStatus('published'), false);
  assert.equal(normalizeFrontmatterScalar('"live-post"'), 'live-post');
  assert.equal(normalizeFrontmatterScalar(undefined), '');
});

test('obsidian parser caches collection-derived post index', () => {
  const source = readFileSync('src/lib/obsidian-parser.ts', 'utf8');

  assert.match(source, /const CACHE_KEY = '__xyvora_post_index__'/);
  assert.match(source, /async function getPostIndex\(\)/);
  assert.match(source, /g\[CACHE_KEY\] = \(async \(\) =>/);
  assert.match(source, /const index = await getPostIndex\(\);/);
  assert.match(source, /const publishedBySlug = new Map/);
});

test('image rewrite keeps build-time copying in the integration layer only', () => {
  const rehypeSource = readFileSync('src/lib/rehype-image-rewrite.ts', 'utf8');
  const integrationSource = readFileSync('src/lib/integrations/copy-vault-images.ts', 'utf8');
  const loaderSource = readFileSync('src/lib/vault-loader.ts', 'utf8');

  assert.doesNotMatch(rehypeSource, /path\.resolve\('dist', '_images'\)/);
  assert.doesNotMatch(rehypeSource, /copyFileSync/);
  assert.doesNotMatch(rehypeSource, /path\.resolve\('public', '_images'\)/);
  assert.match(integrationSource, /reconcileDevVaultAssets/);
  assert.match(integrationSource, /resolvedAssetsByOutputName/);
  assert.doesNotMatch(integrationSource, /walkAndProcessHtml/);
  assert.doesNotMatch(integrationSource, /assetsByName/);
  assert.doesNotMatch(integrationSource, /attrs\.alt/);
  assert.match(loaderSource, /context\.watcher/);
  assert.match(loaderSource, /context\.config\.publicDir/);
});

test('publishing status helpers normalize draft and locked states', () => {
  assert.equal(isDraftStatus(' WIP '), true);
  assert.equal(isDraftStatus('writing'), true);
  assert.equal(isLockedStatus(' 已锁住 '), true);
  assert.equal(isLockedStatus('locked'), true);
});

test('test-render smoke pages are not present in production routes', () => {
  assert.equal(existsSync('src/pages/test-render/index.astro'), false);
  assert.equal(existsSync('src/pages/test-render/[slug].astro'), false);
});

test('unused preview wordmark asset is absent', () => {
  assert.equal(existsSync('public/preview-logo-wordmark.png'), false);
});

test('Python translation tooling and tests are absent', () => {
  const obsoleteFiles = [
    'scripts/check_codeblocks.py',
    'scripts/check_en_quality.py',
    'scripts/translate.py',
    'scripts/translate_summary.py',
    'scripts/lib/__init__.py',
    'scripts/lib/chunker.py',
    'scripts/lib/codeblocks.py',
    'scripts/lib/frontmatter.py',
    'scripts/lib/hash_util.py',
    'scripts/lib/llm_client.py',
    'scripts/lib/translation_paths.py',
    'scripts/requirements.txt',
    'tests/test_translation_paths.py',
    'tests/test_codeblocks.py',
  ];

  assert.deepEqual(obsoleteFiles.filter((file) => existsSync(file)), []);
  assert.equal(existsSync('scripts'), false);
});

test('build workflow contains no translation jobs or credentials', () => {
  const workflow = readFileSync('.github/workflows/build.yml', 'utf8');

  assert.doesNotMatch(workflow, /LLM_(?:API|BASE|MODEL)|VAULT_PUSH_TOKEN/);
  assert.doesNotMatch(workflow, /translate\.py|\.en\.md/);
  assert.doesNotMatch(workflow, /^\s+translate:/im);
  assert.doesNotMatch(workflow, /Setup Python/);
});

test('npm test runs the Node test suite only', () => {
  const packageJson = JSON.parse(readFileSync('package.json', 'utf8'));

  assert.equal(packageJson.scripts['test:python'], undefined);
  assert.equal(packageJson.scripts.test, 'npm run test:node');
  assert.equal(packageJson.scripts['test:node'], 'node --import tsx --test tests/*.test.ts');
});

test('README local setup writes the vault path to the ignored env file', () => {
  const readme = readFileSync('README.md', 'utf8');

  assert.match(readme, /printf 'ASTRO_VAULT_PATH=\/path\/to\/vault\\n' > \.env/);
});
