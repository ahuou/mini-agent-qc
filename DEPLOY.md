# Deploying the dashboard (Vercel)

**Live:** https://mini-agent-qc.vercel.app

The dashboard runs on Vercel as a single Python Function via Vercel's **FastAPI
preset**. `main.py` (repo root) exposes the ASGI `app`; Vercel detects it and
routes all paths to it. No `vercel.json` is needed.

## Behaviour
- **Mock mode is the free default** — open the link, the analysis auto-runs at $0.
- **Live mode uses the `ANTHROPIC_API_KEY` env var** by default; a visitor can
  paste their own key in the Live field to override it (per-request, never stored).

## Deps live in `pyproject.toml` (important)
Vercel's Python builder uses **`uv`** and installs from **`pyproject.toml`'s
`[project].dependencies`** — *not* `requirements.txt`. So any runtime dep the
deployed app needs (fastapi, uvicorn, python-dotenv, pydantic, anthropic) must be
listed there. (`requirements.txt` is kept for local `pip install`.)
- If you add a web dependency, add it to `pyproject.toml` too.
- If the builder ever installs a stale set, delete the generated `uv.lock` so it
  re-resolves from `pyproject.toml`.

## One-time setup
1. `npm i -g vercel` (or import the GitHub repo at vercel.com/new).
2. In the project dir: `vercel link --yes`.
3. Set production env vars (`vercel env add`, or Project → Settings → Environment Variables):

   | Name | Value |
   |------|-------|
   | `ANTHROPIC_API_KEY` | your `sk-ant-…` key (enables Live for visitors; omit to make it mock-only / strictly BYO-key) |
   | `QC_CACHE_DIR` | `/tmp/qc_pipeline_cache` (the only writable dir on serverless) |

4. `vercel --prod --yes` → live URL.

## Caveats on serverless
- **Cost:** with your key set, every visitor's *Live* click spends your credits (mock stays free).
- **Cache is ephemeral:** `/tmp` resets on cold starts and isn't shared across instances, so the
  token-saving cache is best-effort here (a privacy plus: uploaded docs aren't retained). For a
  persistent cache, run `python -m webapp` on Render/Railway/Fly instead.
- **Uploaded-report JSON viewer** can 404 across cold starts/instances (it reads server-side temp
  files); the bundled-report viewer is unaffected.
- **Never commit the key** — it lives only in Vercel's env vars and your git-ignored local `.env`.
