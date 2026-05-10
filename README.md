# Xyvora

Astro 静态博客，内容源自 Obsidian vault。源代码公开，文章内容存放在私有 vault 仓库中。

## Local Development

```bash
# Prerequisites: Node.js 22+, Python 3.11+
npm install
pip install -r scripts/requirements.txt

# Set vault path in .env
echo "ASTRO_VAULT_PATH=F:/Work/Obsidian" > .env

# Dev server
npm run dev

# Build
npm run build
```

## Architecture

```
Obsidian vault → push → vault-repo → repository_dispatch → site-repo Actions
```

Actions pipeline:
1. Clone vault (SSH deploy key)
2. Translate (Python + OpenAI-compatible API via OpenRouter)
3. Build (Astro)
4. rsync dist/ to VPS
5. `docker compose up -d --no-deps neobee-blog`

VPS: `neobee-blog` (nginx:alpine serving dist/) behind `neobee-nginx` reverse proxy.

## Secrets

### Site-repo (`Neobee714/Neobee714.github.io`)

| Secret | Purpose |
|--------|---------|
| `VAULT_SSH_KEY` | SSH private key to clone vault-repo |
| `VAULT_PUSH_TOKEN` | PAT to push translated `.en.md` back to vault-repo |
| `VPS_SSH_KEY` | SSH private key for rsync deploy to VPS |
| `VPS_HOST` | VPS IP or hostname |
| `VPS_USER` | SSH user on VPS |
| `VPS_PATH` | Remote path for dist/ on VPS |
| `VPS_COMPOSE_DIR` | Docker Compose root on VPS |
| `LLM_API_KEY` | API key for translation LLM |
| `LLM_BASE_URL` | Base URL for OpenAI-compatible endpoint |
| `LLM_MODEL` | Model identifier for translation |
| `GOOGLE_SITE_VERIFICATION` | Google Search Console verification string |
| `PUBLIC_CF_ANALYTICS_TOKEN` | Cloudflare Web Analytics token |
| `PUBLIC_GISCUS_REPO_ID` | Giscus repository ID |
| `PUBLIC_GISCUS_CATEGORY` | Giscus discussion category name |
| `PUBLIC_GISCUS_CATEGORY_ID` | Giscus discussion category ID |

### Vault-repo (`Neobee714/obsidian-vault`)

| Secret | Purpose |
|--------|---------|
| `SITE_DISPATCH_TOKEN` | PAT to trigger `repository_dispatch` on site-repo |

## Adding / Modifying / Deleting Articles

Just edit in Obsidian and `git push` the vault. CI handles the rest — translation, build, and deployment are fully automated.

## Google Search Console Verification

1. Add `GOOGLE_SITE_VERIFICATION` secret with the verification string
2. Push or re-run workflow to trigger a rebuild
3. Verify ownership in Google Search Console
