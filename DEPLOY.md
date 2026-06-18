# Deploying the dashboard (Vercel)

The dashboard runs on Vercel as a single Python Function (FastAPI). The repo
already contains everything needed: `api/index.py` (entrypoint), `vercel.json`
(routes every path to it + bundles the data/template), and `.vercelignore`.

## Behaviour once deployed
- **Mock mode is the free default** — anyone who opens the link can run the full
  analysis at $0, no key, no setup.
- **Live mode uses your key by default.** If you set `ANTHROPIC_API_KEY` as a
  Vercel env var (below), visitors can flip to Live and it just works on your key.
- **A visitor can paste their own key** in the Live field to override yours for
  their session (sent per-request, never logged or stored).

## One-time setup
1. **Push this repo to GitHub** (or use the Vercel CLI: `npm i -g vercel`).
2. **Import the project** at [vercel.com/new](https://vercel.com/new) (or run
   `vercel` in this directory). No framework preset needed — `vercel.json` drives it.
3. **Add environment variables** (Project → Settings → Environment Variables,
   or `vercel env add`):

   | Name | Value | Why |
   |------|-------|-----|
   | `ANTHROPIC_API_KEY` | `sk-ant-…` (your key) | Makes Live work for visitors on your key. **Omit it to make the demo mock-only / strictly BYO-key.** |
   | `QC_CACHE_DIR` | `/tmp/qc_pipeline_cache` | Writable cache path on serverless. |

4. **Deploy:** `vercel --prod` (or push to the connected branch). Share the URL.

## Notes & caveats
- **Cost:** with your key set, every visitor's *Live* click spends your credits
  (mock stays free). Fine for a small demo key; otherwise omit the key and let
  reviewers bring their own.
- **Serverless filesystem is ephemeral:** the extraction cache lives in `/tmp`
  and resets on cold starts, so the token-saving benefit is reduced vs. a
  persistent host. Mock + per-request live are unaffected.
- **Persistent alternative:** Render / Railway / Fly.io run `python -m webapp`
  as a long-lived process (persistent cache, env vars in their dashboards) — a
  smoother fit if you want the cache to stick.
- **Never commit the key.** It lives only in Vercel's env vars (and your local
  git-ignored `.env`); `.vercelignore` keeps `.env` out of the upload.
- If a deploy can't find the sample reports, widen `includeFiles` in `vercel.json`.
