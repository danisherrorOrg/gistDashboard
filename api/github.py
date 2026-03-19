from typing import Optional

import httpx
import asyncio
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


async def _fetch_revisions(client, gist_id: str, headers: dict) -> list[str]:
    """
    Fetch all revisions for a gist.
    GET /gists/{gist_id} returns a 'history' array, each item has 'committed_at'.
    Returns a list of date strings like ["2024-11-03", "2024-09-12", ...]
    """
    try:
        resp = await client.get(
            f"https://api.github.com/gists/{gist_id}", headers=headers
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        history = data.get("history", [])
        return [h["committed_at"][:10] for h in history if h.get("committed_at")]
    except Exception:
        return []


async def fetch_user_data(username: str, token: Optional[str]) -> dict:
    cached = _cached(username)
    if cached:
        return cached

    headers = HEADERS.copy()
    if token:
        headers["Authorization"] = f"token {token}"

    async with httpx.AsyncClient(timeout=30) as client:
        # ── Profile ────────────────────────────────────────────────
        profile_resp = await client.get(
            f"https://api.github.com/users/{username}", headers=headers
        )
        if profile_resp.status_code == 404:
            raise ValueError(f"User '{username}' not found")
        if profile_resp.status_code != 200:
            raise ValueError(f"GitHub API error: {profile_resp.status_code}")
        profile = profile_resp.json()

        # Avatar as base64 (needed for SVG embeds)
        avatar_b64 = None
        try:
            av = await client.get(profile.get("avatar_url", ""))
            if av.status_code == 200:
                import base64
                avatar_b64 = base64.b64encode(av.content).decode()
        except Exception:
            pass

        # ── All gists (paginated) ──────────────────────────────────
        all_gists = []
        page = 1
        while True:
            resp = await client.get(
                f"https://api.github.com/users/{username}/gists",
                headers=headers,
                params={"per_page": 100, "page": page},
            )
            gists_page = resp.json()
            if not isinstance(gists_page, list) or not gists_page:
                break
            all_gists.extend(gists_page)
            if len(gists_page) < 100:
                break
            page += 1

        # ── Fetch revisions for every gist (concurrently, batched) ─
        # Each gist detail call returns full history[] with committed_at per revision.
        # We batch 10 at a time to stay well under rate limits.
        gist_revisions: dict[str, list[str]] = {}  # gist_id -> [date, date, ...]

        BATCH = 10
        for i in range(0, len(all_gists), BATCH):
            batch = all_gists[i:i + BATCH]
            results = await asyncio.gather(*[
                _fetch_revisions(client, g["id"], headers) for g in batch
            ])
            for g, dates in zip(batch, results):
                gist_revisions[g["id"]] = dates

    # ── Heatmap from revisions ─────────────────────────────────────
    # Every revision commit_at date counts as 1 activity unit (like a git commit).
    # heatmap_detail: { "2024-11-03": { "commits": N, "gists_touched": set } }
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=364)
    start_str = str(start)

    # day -> { commits: int, gists: set of gist_ids }
    day_data: dict[str, dict] = defaultdict(lambda: {"commits": 0, "gists": set()})

    total_commits = 0
    for g in all_gists:
        gid = g["id"]
        revision_dates = gist_revisions.get(gid, [])
        total_commits += len(revision_dates)
        for day in revision_dates:
            if day >= start_str:
                day_data[day]["commits"] += 1
                day_data[day]["gists"].add(gid)

    # Flat heatmap for rendering
    heatmap: dict[str, int] = {day: v["commits"] for day, v in day_data.items()}

    # heatmap_detail for tooltips (serializable)
    heatmap_detail: dict[str, dict] = {
        day: {"commits": v["commits"], "gists_touched": len(v["gists"])}
        for day, v in day_data.items()
    }

    # ── Languages ──────────────────────────────────────────────────
    lang_count: dict[str, int] = defaultdict(int)
    for g in all_gists:
        for f in g["files"].values():
            lang = f.get("language") or "Other"
            lang_count[lang] += 1
    top_langs = sorted(lang_count.items(), key=lambda x: -x[1])[:6]

    # ── Recent gists ───────────────────────────────────────────────
    recent = sorted(all_gists, key=lambda g: g["updated_at"], reverse=True)[:5]
    recent_clean = [
        {
            "id": g["id"],
            "description": g.get("description") or "(no description)",
            "url": g["html_url"],
            "public": g["public"],
            "created_at": g["created_at"][:10],
            "updated_at": g["updated_at"][:10],
            "comments": g["comments"],
            "files": [f["filename"] for f in g["files"].values()],
            "language": next(
                (f.get("language") for f in g["files"].values() if f.get("language")),
                "Other",
            ),
            "revisions": len(gist_revisions.get(g["id"], [])),
        }
        for g in recent
    ]

    # ── Stats ──────────────────────────────────────────────────────
    total_comments = sum(g["comments"] for g in all_gists)
    public_count = sum(1 for g in all_gists if g["public"])
    year_commits = sum(heatmap.values())

    # Most active month
    month_count: dict[str, int] = defaultdict(int)
    for day, count in heatmap.items():
        month_count[day[:7]] += count
    most_active_month = max(month_count, key=month_count.get) if month_count else "—"

    # Longest streak
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
            "total_commits":      total_commits,
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
    """Return (longest_streak, current_streak) in days."""
    longest = 0
    current = 0
    day = today
    # current streak — walk back from today
    while str(day) in heatmap and heatmap[str(day)] > 0:
        current += 1
        day -= timedelta(days=1)
    # longest streak — scan full year
    streak = 0
    start = today - timedelta(days=364)
    d = start
    while d <= today:
        if heatmap.get(str(d), 0) > 0:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0
        d += timedelta(days=1)
    return longest, current