# Gist Board

A self-hostable GitHub Gist dashboard — activity heatmap, stats, language breakdown, and recent gists. Works as an SVG embed in README files or as a full HTML dashboard.

## Usage

### In a README / `.md` file
```md
![Gist Board](https://yourdomain.com/card/YOUR_USERNAME)
```

### As an iframe
```html
<iframe
  src="https://yourdomain.com/embed/YOUR_USERNAME"
  width="520"
  height="700"
  frameborder="0"
  style="border-radius:12px"
/>
```

### Direct link
```
https://yourdomain.com/embed/YOUR_USERNAME
```

---

## Endpoints

| Endpoint | Returns | Use for |
|---|---|---|
| `GET /card/{username}` | SVG image | README badges |
| `GET /embed/{username}` | HTML page | iframes, direct links |
| `GET /api/{username}` | JSON data | build on top |

### Optional token param (for higher rate limits)
```
/card/torvalds?token=ghp_yourtoken
```

---

## Running locally

```bash
# Install deps
pip install -r requirements.txt

# Run server
python server.py
# → http://localhost:8000
```

## Deploy to Railway / Render

1. Push to GitHub
2. Connect repo on [railway.app](https://railway.app) or [render.com](https://render.com)
3. Set start command: `uvicorn server:app --host 0.0.0.0 --port $PORT`
4. Done — your URL is live

## Deploy to Vercel

Rename `server.py` to use Vercel's serverless format or use the `@vercel/python` runtime:

```
vercel.json → { "builds": [{ "src": "server.py", "use": "@vercel/python" }] }
```

## Optional: GitHub token

Create a token at https://github.com/settings/tokens (no scopes needed for public gists)
and pass it as `?token=` or set env var `GITHUB_TOKEN`.

---

## What it shows

- **Activity heatmap** — 52-week grid, one cell per day, intensity = gists created
- **Stats bar** — total, public, secret, comments, this year
- **Language breakdown** — top languages across all gist files
- **Recent gists** — last 5, with description, language, date, comment count

## Caching

Responses are cached in-memory for 5 minutes per username. For production, swap the in-memory cache in `github.py` for Redis (e.g. Upstash).