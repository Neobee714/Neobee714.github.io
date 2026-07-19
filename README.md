# Xyvora

Astro 静态博客，内容源自私有 Obsidian vault。站点源代码公开，文章内容不存放在本仓库中。

## Local Development

```bash
# Prerequisite: Node.js 22+
# Replace /path/to/vault with the path to your local Obsidian vault
printf 'ASTRO_VAULT_PATH=/path/to/vault\n' > .env

# Install dependencies
npm install

# Dev server
npm run dev

# Tests and production build
npm test
npm run build
```

## Architecture

```text
Obsidian vault -> push -> repository_dispatch -> clone vault
  -> validate published Chinese posts -> Astro build -> rsync dist -> VPS Nginx
```

The GitHub Actions workflow clones the private vault with an SSH deploy key, builds the static site on the Actions runner, synchronizes `dist/` to the VPS, and reloads the `neobee-blog` container. The site is served by Nginx at `https://xyvora.me`.

## Publishing

Notes may live anywhere in the vault. A note is published only when all of these conditions are met:

- `发布` is `true`, `yes`, or `是`.
- `Slug` is present and valid.
- `状态` is not a draft state such as `进行中`, `draft`, `wip`, or `writing`.

Edit notes in Obsidian and push the vault repository. Its workflow sends `repository_dispatch` to this repository, which validates the vault and deploys the rebuilt site.

## Secrets

### Site repository (`Neobee714/Neobee714.github.io`)

| Secret | Purpose |
|---|---|
| `VAULT_SSH_KEY` | SSH private key used to clone the vault repository |
| `VPS_SSH_KEY` | SSH private key used to deploy to the VPS |
| `VPS_HOST` | VPS IP address or hostname |
| `VPS_USER` | VPS SSH user |
| `VPS_PATH` | Remote destination for `dist/` |
| `VPS_COMPOSE_DIR` | Docker Compose root on the VPS |
| `GOOGLE_SITE_VERIFICATION` | Google Search Console verification string |
| `PUBLIC_CF_ANALYTICS_TOKEN` | Cloudflare Web Analytics token |
| `PUBLIC_GISCUS_REPO_ID` | Giscus repository ID |
| `PUBLIC_GISCUS_CATEGORY` | Giscus discussion category name |
| `PUBLIC_GISCUS_CATEGORY_ID` | Giscus discussion category ID |

### Vault repository (`Neobee714/obsidian-vault`)

| Secret | Purpose |
|---|---|
| `SITE_DISPATCH_TOKEN` | Token used to send `repository_dispatch` to the site repository |

## Google Search Console Verification

1. Add the `GOOGLE_SITE_VERIFICATION` Actions secret.
2. Push or manually run the build workflow.
3. Verify ownership in Google Search Console.
