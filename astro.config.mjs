// @ts-check
import { defineConfig, envField } from 'astro/config';
import { loadEnv } from 'vite';
import tailwindcss from '@tailwindcss/vite';
import { slugUniquenessCheck } from './src/lib/integrations/slug-check.ts';

// Load variables from .env (including non-PUBLIC_ ones) into process.env
// so the content loader / integrations can read them via process.env.X.
const env = loadEnv(process.env.NODE_ENV || 'development', process.cwd(), '');
for (const key of ['ASTRO_VAULT_PATH', 'PUBLIC_SITE_URL']) {
  if (env[key] && !process.env[key]) {
    process.env[key] = env[key];
  }
}

// https://astro.build/config
export default defineConfig({
  site: process.env.PUBLIC_SITE_URL || 'https://neobee.top',
  integrations: [slugUniquenessCheck()],
  vite: {
    plugins: [tailwindcss()],
  },
});
