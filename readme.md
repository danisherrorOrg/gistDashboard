# Gist Board

A self-hostable GitHub Gist dashboard. Point it at any GitHub username and get a full activity dashboard — heatmap, commit history, analytics, language breakdown, and more.

Works as an embeddable SVG badge in README files, an iframe on websites, or a standalone web app.

```
![Gist Board](https://yourdomain.com/card/danisherror)
```

---

## What it does

- **Activity heatmap** — 52-week grid built from real commit timestamps (every revision of every gist counts, not just created/updated dates)
- **Commit timeline** — per-gist commit history with additions/deletions per commit
- **Analytics** — day-of-week patterns, month-by-month activity, aging report (stale vs active gists)
- **Full gist list** — paginated, searchable, filterable by language and visibility
- **Compare two users** — side-by-side stats, heatmaps, and language breakdown
- **Open Graph image** — `/og/{username}` returns a 1200×630 image for link previews
- **SVG card** — `/card/{username}` returns an SVG for README embeds with `?theme=light|dark` and `?compact=1` params
- **In-memory cache** — TTL-based dict cache, no Redis required

---

## Quick start

```bash
git clone https://github.com/yourname/gist-board
cd gist-board

pip install -r requirements.txt

cp .env.example .env
# add your GITHUB_TOKEN to .env

python server.py
# → http://localhost:8000
```

Then open `http://localhost:8000/embed/YOUR_USERNAME`.

---

## GitHub Token

Required. Without it you hit GitHub's 60 req/hour unauthenticated limit instantly (each user fetch makes ~70+ API calls — one per gist to get commit history).

1. Go to https://github.com/settings/tokens
2. Generate new token (classic)
3. No scopes needed — public gists are readable without any permission
4. Add to `.env`:

```
GITHUB_TOKEN=ghp_your_token_here
```

With a token you get 5000 req/hour.

---

## Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Homepage with search |
| `GET` | `/embed/{username}` | Full dashboard |
| `GET` | `/gists/{username}` | Paginated gist list |
| `GET` | `/embed/{username}/gist/{id}` | Single gist + commit timeline |
| `GET` | `/compare/{user1}/{user2}` | Side-by-side comparison |
| `GET` | `/card/{username}` | SVG card for README embeds |
| `GET` | `/og/{username}` | Open Graph PNG/SVG (1200×630) |
| `GET` | `/api/{username}` | Raw JSON — full user data |
| `GET` | `/api/{username}/analytics` | Raw JSON — analytics only |
| `GET` | `/api/{username}/gist/{id}` | Raw JSON — single gist detail |
| `GET` | `/api/cache/stats` | Cache health |
| `DELETE` | `/api/cache/flush` | Flush entire cache |
| `DELETE` | `/api/cache/user/{username}` | Flush one user's cached data |

### Query params

```
/card/{username}?theme=light        # light theme SVG
/card/{username}?compact=1          # compact SVG (no recent gists)
/gists/{username}?page=2            # pagination
/gists/{username}?lang=Python       # filter by language
/gists/{username}?visibility=secret # public | secret | all
/gists/{username}?q=setup           # search descriptions + filenames
/embed/{username}?token=ghp_xxx     # per-request token override
```

---

## Project structure

```
gist-board/
│
├── server.py           # FastAPI app — all routes registered here
├── github.py           # GitHub API layer — fetching, caching, error handling
├── analytics.py        # Derived stats — no API calls, pure computation
├── cache.py            # In-memory TTL cache (dict-based, thread-safe)
├── og.py               # Open Graph image generator
├── svg_builder.py      # SVG card builder (for /card/{username})
├── html_builder.py     # Main dashboard HTML template
│
├── templates/
│   ├── detail.py       # Single gist page + commit timeline
│   ├── compare.py      # Side-by-side user comparison
│   └── gist_list.py    # Paginated full gist list
│
├── requirements.txt
├── .env.example
└── README.md
```

---

## Data flow

Understanding this makes it easy to modify any part independently.

### 1. Request comes in

```
GET /embed/danisherror
        │
        ▼
server.py → embed()
        │
        ▼
github.fetch_user_data("danisherror")
```

### 2. Cache check

```
cache.get("user:danisherror")
        │
   hit ─┤─ miss
        │         │
        │         ▼
        │   fetch from GitHub API (steps 3–5)
        │         │
        └─────────┘
        │
        ▼
   return data
```

### 3. GitHub API calls (on cache miss)

```
GET /users/{username}               → profile info
GET /users/{username}/gists         → list of all gists (paginated, 100/page)
        │
        ▼ for each gist (batched 10 at a time, concurrent):
GET /gists/{id}/commits             → full commit history with timestamps
```

### 4. Data derivation

```
raw gists + commit timestamps
        │
        ├─ heatmap         { "2026-03-17": 3, ... }   (commits per day, last 365 days)
        ├─ heatmap_detail  { "2026-03-17": { commits, gists_touched, additions } }
        ├─ languages       [("Python", 30), ("Shell", 15), ...]
        ├─ recent          last 5 gists (for dashboard preview)
        ├─ all_gists_full  all gists as clean dicts (for list page + analytics)
        └─ stats           { total, public, secret, total_commits, year_commits,
                             longest_streak, current_streak, most_active_month }
```

### 5. Analytics (no extra API calls)

```
fetch_user_data() output
        │
        ▼
analytics.build_analytics(data)
        │
        ├─ day_of_week   [{ day: "Mon", commits: 12 }, ...]
        ├─ by_month      [{ month: "Mar 2026", commits: 8 }, ...]
        ├─ aging         { active: [...], stale: [...], never: [...] }
        ├─ peak_day      "Friday"
        └─ peak_month    "Nov 2025"
```

### 6. Rendering

```
data dict
    │
    ├─ html_builder.build_html()       → dashboard HTML
    ├─ svg_builder.build_svg()         → SVG card
    ├─ templates/detail.py             → gist detail HTML
    ├─ templates/compare.py            → compare HTML
    ├─ templates/gist_list.py          → paginated list HTML
    └─ og.build_og_svg() / PNG         → OG image
```

### 7. Cache storage

```
cache.set("user:{username}",          data, ttl=300)   # 5 min
cache.set("gist:{gist_id}",           data, ttl=600)   # 10 min
cache.set("compare:{u1}:{u2}",        data, ttl=300)   # 5 min
```

---

## Cache

`cache.py` is a standalone TTL dict cache — no Redis, no external deps.

```python
from cache import cache

cache.set("key", value, ttl=300)     # store for 5 min
cache.get("key")                     # None if missing or expired
cache.ttl("key")                     # seconds remaining
cache.touch("key", ttl=60)           # reset expiry
cache.flush_pattern("user:")         # delete all keys with prefix
cache.stats()                        # { keys_live, hit_rate, hits, misses }
```

A background daemon thread purges expired keys every 60 seconds automatically.
Max 500 keys — oldest is evicted when full.

For production with multiple workers, swap `cache.py` for Redis using the same interface.

---

## Error handling

All errors in `github.py` are typed exceptions:

| Exception | Cause | HTTP status |
|---|---|---|
| `UserNotFoundError` | Username doesn't exist or invalid | 404 |
| `RateLimitError` | GitHub rate limit hit (includes reset time) | 429 |
| `NetworkError` | Timeout or connection failure | 503 |
| `GistBoardError` | Any other GitHub API error | 400 |

Each route in `server.py` catches these individually and returns the right status code + a styled error page.

Single-gist commit fetching (`_fetch_gist_commits`) never raises — if one gist fails it returns `[]` and the rest continue. One bad gist doesn't break the whole dashboard.

---

## OG image

`/og/{username}` tries three approaches in order:

1. **playwright** (richest) — screenshots the HTML card. Run `playwright install chromium` once to enable.
2. **cairosvg** — converts SVG to PNG. Install with `pip install cairosvg`.
3. **SVG fallback** (no deps) — returns the card as SVG. Supported by Twitter, Slack, Discord, iMessage.

Add to your own README's HTML head:

```html
<meta property="og:image" content="https://yourdomain.com/og/YOUR_USERNAME">
<meta property="og:image:width"  content="1200">
<meta property="og:image:height" content="630">
```

---

## Deploy

### Railway / Render (easiest)

1. Push to GitHub
2. Connect repo at [railway.app](https://railway.app) or [render.com](https://render.com)
3. Set start command: `uvicorn server:app --host 0.0.0.0 --port $PORT`
4. Add `GITHUB_TOKEN` as an environment variable
5. Done

### Vercel

Vercel Python runtime supports FastAPI. Add `vercel.json`:

```json
{
  "builds": [{ "src": "server.py", "use": "@vercel/python" }],
  "routes": [{ "src": "/(.*)", "dest": "server.py" }]
}
```

Note: Vercel serverless functions are stateless — the in-memory cache resets on each cold start. Use Upstash Redis for persistent caching if needed.

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Contributing

### Adding a new page

1. Create `templates/your_page.py` with a `build_your_page_html(data, ...) -> str` function
2. Add a route in `server.py` that calls `fetch_user_data()` and passes data to your template
3. Add a link to it from the relevant existing page

### Adding a new data field

1. Compute it in `github.py` inside `fetch_user_data()` — all derivation happens there
2. Add it to the `result` dict
3. Use it in any template — it's available in `data["stats"]`, `data["profile"]`, etc.

### Changing cache TTLs

Edit the constants at the top of `github.py`:

```python
TTL_USER    = 300   # dashboard cache (seconds)
TTL_GIST    = 600   # single gist detail cache
TTL_COMPARE = 300   # compare page cache
```

---

## Stack

- **[FastAPI](https://fastapi.tiangolo.com/)** — async Python web framework
- **[httpx](https://www.python-httpx.org/)** — async HTTP client for GitHub API
- **[uvicorn](https://www.uvicorn.org/)** — ASGI server
- **[playwright](https://playwright.dev/python/)** *(optional)* — headless browser for OG image PNG
- **[cairosvg](https://cairosvg.org/)** *(optional)* — SVG to PNG conversion
- **GitHub API v3** — no OAuth needed, public token only

No frontend framework. All HTML is generated server-side as Python f-strings.

---

## License

MIT