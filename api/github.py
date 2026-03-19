import httpx
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional
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


async def fetch_user_data(username: str, token: Optional[str]) -> dict:
    cached = _cached(username)
    if cached:
        return cached

    headers = HEADERS.copy()
    if token:
        headers["Authorization"] = f"token {token}"

    async with httpx.AsyncClient(timeout=20) as client:
        # Profile
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

        # All gists (paginated)
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

    # ── Heatmap ────────────────────────────────────────────────────
    # Count both created_at AND updated_at per gist as activity.
    # Each gist contributes at most once per day (deduped by gist id+day).
    # heatmap_detail: { "2024-11-03": { "created": 2, "updated": 3 } }
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=364)
    start_str = str(start)

    heatmap_detail: dict[str, dict] = defaultdict(lambda: {"created": 0, "updated": 0})
    seen: set = set()  # (gist_id, day) pairs to avoid double-counting same-day create+update

    for g in all_gists:
        gid = g["id"]
        created_day = g["created_at"][:10]
        updated_day = g["updated_at"][:10]

        if created_day >= start_str:
            key = (gid, created_day, "created")
            if key not in seen:
                seen.add(key)
                heatmap_detail[created_day]["created"] += 1

        # Only count update if it's a different day than creation
        if updated_day >= start_str and updated_day != created_day:
            key = (gid, updated_day, "updated")
            if key not in seen:
                seen.add(key)
                heatmap_detail[updated_day]["updated"] += 1

    # Flat heatmap: total activity per day
    heatmap: dict[str, int] = {
        day: v["created"] + v["updated"]
        for day, v in heatmap_detail.items()
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
        }
        for g in recent
    ]

    # ── Stats ──────────────────────────────────────────────────────
    total_comments = sum(g["comments"] for g in all_gists)
    public_count = sum(1 for g in all_gists if g["public"])
    year_activity = sum(heatmap.values())
    year_created = sum(v["created"] for v in heatmap_detail.values())
    year_updated = sum(v["updated"] for v in heatmap_detail.values())

    # Most active month
    month_count: dict[str, int] = defaultdict(int)
    for day, count in heatmap.items():
        month_count[day[:7]] += count
    most_active_month = max(month_count, key=month_count.get) if month_count else "—"

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
            "total":            len(all_gists),
            "public":           public_count,
            "secret":           len(all_gists) - public_count,
            "total_comments":   total_comments,
            "last_active":      all_gists[0]["updated_at"][:10] if all_gists else "—",
            "year_activity":    year_activity,
            "year_created":     year_created,
            "year_updated":     year_updated,
            "most_active_month": most_active_month,
        },
        "heatmap":        dict(heatmap),
        "heatmap_detail": {k: dict(v) for k, v in heatmap_detail.items()},
        "languages":      top_langs,
        "recent":         recent_clean,
    }

    _store(username, result)
    return result