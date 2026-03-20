from typing import Optional

import httpx
import asyncio
import os
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta

HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

_cache: dict = {}
TTL = 300  # 5 minutes


def _cached(username: str):
    entry = _cache.get(username)
    if entry and time.time() - entry["ts"] < TTL:
        return entry["data"]
    return None


def _store(username: str, data: dict):
    _cache[username] = {"data": data, "ts": time.time()}


async def _fetch_gist_commits(client, gist_id: str, headers: dict) -> list[dict]:
    """
    GET /gists/{gist_id}/commits
    Returns list of { committed_at, change_status: { additions, deletions, total } }
    Paginates until all commits are fetched.
    """
    all_commits = []
    page = 1
    while True:
        try:
            resp = await client.get(
                f"https://api.github.com/gists/{gist_id}/commits",
                headers=headers,
                params={"per_page": 100, "page": page},
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            if not isinstance(data, list) or not data:
                break
            for c in data:
                if c.get("committed_at"):
                    cs = c.get("change_status", {})
                    all_commits.append({
                        "day":       c["committed_at"][:10],
                        "additions": cs.get("additions", 0),
                        "deletions": cs.get("deletions", 0),
                        "total":     cs.get("total", 0),
                    })
            if len(data) < 100:
                break
            page += 1
        except Exception:
            break
    return all_commits


async def fetch_user_data(username: str, token: Optional[str]) -> dict:
    cached = _cached(username)
    if cached:
        return cached

    # query param > env var
    token = token or os.environ.get("GITHUB_TOKEN")

    headers = HEADERS.copy()
    if token:
        headers["Authorization"] = f"token {token}"

    async with httpx.AsyncClient(timeout=30) as client:

        # ── 1. User profile ────────────────────────────────────────
        profile_resp = await client.get(
            f"https://api.github.com/users/{username}", headers=headers
        )
        if profile_resp.status_code == 404:
            raise ValueError(f"User '{username}' not found")
        if profile_resp.status_code == 403:
            raise ValueError("GitHub rate limit hit — add a GITHUB_TOKEN to your .env")
        if profile_resp.status_code != 200:
            raise ValueError(f"GitHub API error: {profile_resp.status_code}")
        profile = profile_resp.json()

        # Avatar as base64 (for SVG embeds)
        avatar_b64 = None
        try:
            av = await client.get(profile.get("avatar_url", ""))
            if av.status_code == 200:
                import base64
                avatar_b64 = base64.b64encode(av.content).decode()
        except Exception:
            pass

        # ── 2. All gists (paginated) ───────────────────────────────
        all_gists = []
        page = 1
        while True:
            resp = await client.get(
                f"https://api.github.com/users/{username}/gists",
                headers=headers,
                params={"per_page": 100, "page": page},
            )
            if resp.status_code != 200:
                break
            gists_page = resp.json()
            if not isinstance(gists_page, list) or not gists_page:
                break
            all_gists.extend(gists_page)
            if len(gists_page) < 100:
                break
            page += 1

        # ── 3. Commits for every gist (batched concurrent) ─────────
        # GET /gists/{id}/commits  →  one entry per commit, with committed_at
        BATCH = 10
        gist_commits: dict[str, list[dict]] = {}  # gist_id -> [commit, ...]

        for i in range(0, len(all_gists), BATCH):
            batch = all_gists[i:i + BATCH]
            results = await asyncio.gather(*[
                _fetch_gist_commits(client, g["id"], headers) for g in batch
            ])
            for g, commits in zip(batch, results):
                gist_commits[g["id"]] = commits

    # ── 4. Build heatmap from commit timestamps ────────────────────
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=364)
    start_str = str(start)

    # day -> { commits, gists_touched, additions, deletions }
    day_data: dict[str, dict] = defaultdict(lambda: {
        "commits":       0,
        "gists_touched": set(),
        "additions":     0,
        "deletions":     0,
    })

    total_commits_alltime = 0

    for g in all_gists:
        gid = g["id"]
        commits = gist_commits.get(gid, [])
        total_commits_alltime += len(commits)

        for c in commits:
            day = c["day"]
            if day >= start_str:
                day_data[day]["commits"]       += 1
                day_data[day]["gists_touched"].add(gid)
                day_data[day]["additions"]     += c["additions"]
                day_data[day]["deletions"]     += c["deletions"]

    # Flat heatmap: commit count per day
    heatmap: dict[str, int] = {
        day: v["commits"] for day, v in day_data.items()
    }

    # Serialisable detail for tooltips
    heatmap_detail: dict[str, dict] = {
        day: {
            "commits":       v["commits"],
            "gists_touched": len(v["gists_touched"]),
            "additions":     v["additions"],
            "deletions":     v["deletions"],
        }
        for day, v in day_data.items()
    }

    # ── 5. Languages ───────────────────────────────────────────────
    lang_count: dict[str, int] = defaultdict(int)
    for g in all_gists:
        for f in g["files"].values():
            lang = f.get("language") or "Other"
            lang_count[lang] += 1
    top_langs = sorted(lang_count.items(), key=lambda x: -x[1])[:6]

    # ── 6. Recent gists ────────────────────────────────────────────
    recent = sorted(all_gists, key=lambda g: g["updated_at"], reverse=True)[:5]
    recent_clean = [
        {
            "id":          g["id"],
            "description": g.get("description") or "(no description)",
            "url":         g["html_url"],
            "public":      g["public"],
            "created_at":  g["created_at"][:10],
            "updated_at":  g["updated_at"][:10],
            "comments":    g["comments"],
            "files":       [f["filename"] for f in g["files"].values()],
            "file_count":  len(g["files"]),
            "language":    next(
                (f.get("language") for f in g["files"].values() if f.get("language")),
                "Other",
            ),
            "commits":     len(gist_commits.get(g["id"], [])),
        }
        for g in recent
    ]

    # ── 7. Stats ───────────────────────────────────────────────────
    total_comments = sum(g["comments"] for g in all_gists)
    public_count   = sum(1 for g in all_gists if g["public"])
    year_commits   = sum(heatmap.values())

    month_count: dict[str, int] = defaultdict(int)
    for day, count in heatmap.items():
        month_count[day[:7]] += count
    most_active_month = max(month_count, key=month_count.get) if month_count else "—"

    longest_streak, current_streak = _streaks(heatmap, today)

    result = {
        "profile": {
            "login":        profile.get("login", username),
            "name":         profile.get("name") or profile.get("login", username),
            "bio":          profile.get("bio") or "",
            "avatar_url":   profile.get("avatar_url", ""),
            "avatar_b64":   avatar_b64,
            "html_url":     profile.get("html_url", f"https://github.com/{username}"),
            "followers":    profile.get("followers") or 0,
            "following":    profile.get("following") or 0,
            "location":     profile.get("location") or "",
            "company":      profile.get("company") or "",
            "public_repos": profile.get("public_repos") or 0,
            "public_gists": profile.get("public_gists") or 0,
        },
        "stats": {
            "total":              len(all_gists),
            "public":             public_count,
            "secret":             len(all_gists) - public_count,
            "total_comments":     total_comments,
            "total_commits":      total_commits_alltime,
            "last_active":        all_gists[0]["updated_at"][:10] if all_gists else "—",
            "year_commits":       year_commits,
            "most_active_month":  most_active_month,
            "longest_streak":     longest_streak,
            "current_streak":     current_streak,
        },
        "heatmap":        heatmap,
        "heatmap_detail": heatmap_detail,
        "languages":      top_langs,
        "recent":         recent_clean,
    }

    _store(username, result)
    return result


def _streaks(heatmap: dict, today) -> tuple[int, int]:
    """Return (longest_streak_days, current_streak_days)."""
    # current streak — walk back from today
    current = 0
    day = today
    while str(day) in heatmap and heatmap[str(day)] > 0:
        current += 1
        day -= timedelta(days=1)

    # longest streak — scan full year window
    longest = 0
    streak = 0
    d = today - timedelta(days=364)
    while d <= today:
        if heatmap.get(str(d), 0) > 0:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0
        d += timedelta(days=1)

    return longest, current