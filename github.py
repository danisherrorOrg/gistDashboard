from typing import Optional

import httpx
import asyncio
import os
import time
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta

log = logging.getLogger("gist-board")

HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

_cache: dict = {}
TTL = 300  # 5 minutes


# ── Custom exceptions ──────────────────────────────────────────────────────────

class GistBoardError(Exception):
    """Base — always has a user-friendly message."""
    pass

class UserNotFoundError(GistBoardError):
    pass

class RateLimitError(GistBoardError):
    pass

class NetworkError(GistBoardError):
    pass


# ── Cache helpers ──────────────────────────────────────────────────────────────

def _cached(username: str):
    entry = _cache.get(username.lower())
    if entry and time.time() - entry["ts"] < TTL:
        return entry["data"]
    return None


def _store(username: str, data: dict):
    _cache[username.lower()] = {"data": data, "ts": time.time()}


# ── Rate-limit aware response checker ─────────────────────────────────────────

def _check_response(resp: httpx.Response, context: str = "") -> None:
    """Raise a typed exception for any non-2xx GitHub response."""
    status = resp.status_code

    if status == 200:
        return  # all good

    # Try to get GitHub's error message
    try:
        body = resp.json()
        gh_msg = body.get("message", "")
    except Exception:
        gh_msg = resp.text[:120]

    if status == 401:
        raise GistBoardError(
            f"Invalid or expired GitHub token. Re-generate it at "
            f"https://github.com/settings/tokens [{context}]"
        )
    if status == 403:
        reset_ts = resp.headers.get("x-ratelimit-reset")
        reset_str = ""
        if reset_ts:
            try:
                reset_dt = datetime.fromtimestamp(int(reset_ts), tz=timezone.utc)
                reset_str = f" Resets at {reset_dt.strftime('%H:%M UTC')}."
            except Exception:
                pass
        remaining = resp.headers.get("x-ratelimit-remaining", "?")
        raise RateLimitError(
            f"GitHub rate limit exceeded (remaining: {remaining}).{reset_str} "
            f"Set GITHUB_TOKEN in your .env to get 5000 req/hr instead of 60. [{context}]"
        )
    if status == 404:
        raise UserNotFoundError(f"Not found: {context}")
    if status == 422:
        raise GistBoardError(f"GitHub rejected the request: {gh_msg} [{context}]")
    if status >= 500:
        raise NetworkError(
            f"GitHub is having issues (HTTP {status}). Try again in a moment. [{context}]"
        )

    raise GistBoardError(f"Unexpected response HTTP {status}: {gh_msg} [{context}]")


# ── Per-gist commit fetcher ────────────────────────────────────────────────────

async def _fetch_gist_commits(
    client: httpx.AsyncClient,
    gist_id: str,
    headers: dict,
) -> list[dict]:
    """
    GET /gists/{gist_id}/commits  (paginated)
    Returns [{ day, additions, deletions, total }, ...]
    Never raises — returns [] on any failure so one bad gist doesn't kill the page.
    """
    all_commits = []
    page = 1
    while True:
        try:
            resp = await client.get(
                f"https://api.github.com/gists/{gist_id}/commits",
                headers=headers,
                params={"per_page": 100, "page": page},
                timeout=15,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            log.warning("Timeout/network fetching commits for gist %s (page %d): %s", gist_id, page, e)
            break
        except Exception as e:
            log.warning("Unexpected error fetching commits for gist %s: %s", gist_id, e)
            break

        # Rate limit mid-way through: stop gracefully, return what we have
        if resp.status_code == 403:
            log.warning("Rate limit hit fetching commits for gist %s — partial data returned", gist_id)
            break
        if resp.status_code == 404:
            log.warning("Gist %s not found when fetching commits (deleted?)", gist_id)
            break
        if resp.status_code != 200:
            log.warning("HTTP %d fetching commits for gist %s", resp.status_code, gist_id)
            break

        try:
            data = resp.json()
        except Exception as e:
            log.warning("JSON decode error for gist %s commits: %s", gist_id, e)
            break

        if not isinstance(data, list) or not data:
            break

        for c in data:
            try:
                if not c.get("committed_at"):
                    continue
                cs = c.get("change_status") or {}
                all_commits.append({
                    "day":       c["committed_at"][:10],
                    "additions": int(cs.get("additions") or 0),
                    "deletions": int(cs.get("deletions") or 0),
                    "total":     int(cs.get("total") or 0),
                })
            except Exception as e:
                log.warning("Skipping malformed commit entry in gist %s: %s", gist_id, e)
                continue

        if len(data) < 100:
            break
        page += 1

    return all_commits


# ── Main fetch ─────────────────────────────────────────────────────────────────

async def fetch_user_data(username: str, token: Optional[str]) -> dict:
    # Basic username validation
    username = username.strip()
    if not username:
        raise UserNotFoundError("Username cannot be empty.")
    if len(username) > 39 or not all(c.isalnum() or c == "-" for c in username):
        raise UserNotFoundError(f"'{username}' is not a valid GitHub username.")

    cached = _cached(username)
    if cached:
        return cached

    # Token priority: arg > env var
    token = token or os.environ.get("GITHUB_TOKEN")
    if not token:
        log.warning("No GITHUB_TOKEN set — unauthenticated requests limited to 60/hr")

    headers = HEADERS.copy()
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        async with httpx.AsyncClient(timeout=20) as client:

            # ── 1. User profile ───────────────────────────────────
            try:
                profile_resp = await client.get(
                    f"https://api.github.com/users/{username}", headers=headers
                )
            except httpx.TimeoutException:
                raise NetworkError("Request to GitHub timed out. Check your connection.")
            except httpx.NetworkError as e:
                raise NetworkError(f"Cannot reach GitHub: {e}")

            _check_response(profile_resp, f"GET /users/{username}")
            profile = profile_resp.json()

            if not isinstance(profile, dict) or "login" not in profile:
                raise GistBoardError("GitHub returned unexpected profile data.")

            # Avatar as base64 (needed for SVG embeds; skip silently if fails)
            avatar_b64 = None
            try:
                av = await client.get(profile.get("avatar_url", ""), timeout=8)
                if av.status_code == 200:
                    import base64
                    avatar_b64 = base64.b64encode(av.content).decode()
            except Exception as e:
                log.info("Could not fetch avatar: %s", e)

            # ── 2. All gists (paginated) ──────────────────────────
            all_gists = []
            page = 1
            while True:
                try:
                    resp = await client.get(
                        f"https://api.github.com/users/{username}/gists",
                        headers=headers,
                        params={"per_page": 100, "page": page},
                    )
                except (httpx.TimeoutException, httpx.NetworkError) as e:
                    log.warning("Network error fetching gists page %d: %s", page, e)
                    break

                if resp.status_code == 403:
                    _check_response(resp, f"GET /users/{username}/gists page {page}")
                if resp.status_code != 200:
                    log.warning("HTTP %d fetching gists page %d — stopping pagination", resp.status_code, page)
                    break

                try:
                    gists_page = resp.json()
                except Exception:
                    log.warning("JSON decode error on gists page %d", page)
                    break

                if not isinstance(gists_page, list) or not gists_page:
                    break
                all_gists.extend(gists_page)
                if len(gists_page) < 100:
                    break
                page += 1

            # ── 3. Commits for every gist (batched, concurrent) ───
            BATCH = 10
            gist_commits: dict[str, list[dict]] = {}

            for i in range(0, len(all_gists), BATCH):
                batch = all_gists[i:i + BATCH]
                try:
                    results = await asyncio.gather(*[
                        _fetch_gist_commits(client, g["id"], headers)
                        for g in batch
                    ], return_exceptions=False)
                except Exception as e:
                    log.warning("Batch %d gather error: %s — skipping batch", i // BATCH, e)
                    results = [[] for _ in batch]

                for g, commits in zip(batch, results):
                    gist_commits[g["id"]] = commits if isinstance(commits, list) else []

    except (UserNotFoundError, RateLimitError, GistBoardError, NetworkError):
        raise  # re-raise typed errors as-is
    except Exception as e:
        log.exception("Unhandled error in fetch_user_data")
        raise GistBoardError(f"Something went wrong: {e}")

    # ── 4. Build heatmap ──────────────────────────────────────────
    today = datetime.now(timezone.utc).date()
    start_str = str(today - timedelta(days=364))

    day_data: dict[str, dict] = defaultdict(lambda: {
        "commits":       0,
        "gists_touched": set(),
        "additions":     0,
        "deletions":     0,
    })

    total_commits_alltime = 0

    for g in all_gists:
        gid = g.get("id", "")
        commits = gist_commits.get(gid, [])
        total_commits_alltime += len(commits)
        for c in commits:
            day = c.get("day", "")
            if day and day >= start_str:
                day_data[day]["commits"]       += 1
                day_data[day]["gists_touched"].add(gid)
                day_data[day]["additions"]     += c.get("additions", 0)
                day_data[day]["deletions"]     += c.get("deletions", 0)

    heatmap: dict[str, int] = {d: v["commits"] for d, v in day_data.items()}
    heatmap_detail: dict[str, dict] = {
        d: {
            "commits":       v["commits"],
            "gists_touched": len(v["gists_touched"]),
            "additions":     v["additions"],
            "deletions":     v["deletions"],
        }
        for d, v in day_data.items()
    }

    # ── 5. Languages ──────────────────────────────────────────────
    lang_count: dict[str, int] = defaultdict(int)
    for g in all_gists:
        for f in (g.get("files") or {}).values():
            lang = (f.get("language") if f else None) or "Other"
            lang_count[lang] += 1
    top_langs = sorted(lang_count.items(), key=lambda x: -x[1])[:6]

    # ── 6. Recent gists ───────────────────────────────────────────
    def _safe_gist(g: dict) -> dict:
        files = g.get("files") or {}
        filenames = [f["filename"] for f in files.values() if f and f.get("filename")]
        language = next(
            (f.get("language") for f in files.values() if f and f.get("language")),
            "Other",
        )
        return {
            "id":          g.get("id", ""),
            "description": g.get("description") or "(no description)",
            "url":         g.get("html_url", "#"),
            "public":      g.get("public", True),
            "created_at":  (g.get("created_at") or "")[:10],
            "updated_at":  (g.get("updated_at") or "")[:10],
            "comments":    g.get("comments") or 0,
            "files":       filenames,
            "file_count":  len(files),
            "language":    language,
            "commits":     len(gist_commits.get(g.get("id", ""), [])),
        }

    try:
        recent_sorted = sorted(
            all_gists,
            key=lambda g: g.get("updated_at") or "",
            reverse=True,
        )[:5]
        recent_clean = [_safe_gist(g) for g in recent_sorted]
    except Exception as e:
        log.warning("Error building recent gists: %s", e)
        recent_clean = []

    # ── 7. Stats ──────────────────────────────────────────────────
    total_comments = sum(g.get("comments") or 0 for g in all_gists)
    public_count   = sum(1 for g in all_gists if g.get("public"))
    year_commits   = sum(heatmap.values())

    month_count: dict[str, int] = defaultdict(int)
    for day, count in heatmap.items():
        if len(day) >= 7:
            month_count[day[:7]] += count
    most_active_month = max(month_count, key=month_count.get) if month_count else "—"

    longest_streak, current_streak = _streaks(heatmap, today)

    last_active = "—"
    if all_gists:
        try:
            last_active = sorted(
                (g.get("updated_at") or "" for g in all_gists), reverse=True
            )[0][:10]
        except Exception:
            pass

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
            "total":             len(all_gists),
            "public":            public_count,
            "secret":            len(all_gists) - public_count,
            "total_comments":    total_comments,
            "total_commits":     total_commits_alltime,
            "last_active":       last_active,
            "year_commits":      year_commits,
            "most_active_month": most_active_month,
            "longest_streak":    longest_streak,
            "current_streak":    current_streak,
        },
        "heatmap":          heatmap,
        "heatmap_detail":   heatmap_detail,
        "languages":        top_langs,
        "recent":           recent_clean,
        "all_gists_full":   [_safe_gist_summary(g, gist_commits) for g in all_gists],
    }

    _store(username, result)
    return result


def _safe_gist_summary(g: dict, gist_commits: dict) -> dict:
    files = g.get("files") or {}
    return {
        "id":          g.get("id", ""),
        "description": g.get("description") or "",
        "url":         g.get("html_url", "#"),
        "public":      g.get("public", True),
        "created_at":  (g.get("created_at") or "")[:10],
        "updated_at":  (g.get("updated_at") or "")[:10],
        "comments":    g.get("comments") or 0,
        "files":       [f["filename"] for f in files.values() if f and f.get("filename")],
        "file_count":  len(files),
        "language":    next((f.get("language") for f in files.values() if f and f.get("language")), "Other"),
        "commits":     len(gist_commits.get(g.get("id", ""), [])),
    }


def _streaks(heatmap: dict, today) -> tuple[int, int]:
    current = 0
    day = today
    while heatmap.get(str(day), 0) > 0:
        current += 1
        day -= timedelta(days=1)
    longest = 0
    streak  = 0
    d = today - timedelta(days=364)
    while d <= today:
        if heatmap.get(str(d), 0) > 0:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0
        d += timedelta(days=1)
    return longest, current


# ── Gist detail ────────────────────────────────────────────────────────────────

async def fetch_gist_detail(gist_id: str, token: Optional[str]) -> dict:
    """Full commit timeline for a single gist."""
    token = token or os.environ.get("GITHUB_TOKEN")
    headers = HEADERS.copy()
    if token:
        headers["Authorization"] = f"token {token}"

    async with httpx.AsyncClient(timeout=20) as client:
        # Gist metadata
        try:
            resp = await client.get(
                f"https://api.github.com/gists/{gist_id}", headers=headers
            )
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            raise NetworkError(f"Cannot reach GitHub: {e}")
        _check_response(resp, f"GET /gists/{gist_id}")
        gist = resp.json()

        # All commits
        commits = await _fetch_gist_commits(client, gist_id, headers)

    files = gist.get("files") or {}
    return {
        "id":          gist.get("id", gist_id),
        "description": gist.get("description") or "(no description)",
        "url":         gist.get("html_url", "#"),
        "public":      gist.get("public", True),
        "created_at":  (gist.get("created_at") or "")[:10],
        "updated_at":  (gist.get("updated_at") or "")[:10],
        "comments":    gist.get("comments") or 0,
        "owner":       (gist.get("owner") or {}).get("login", ""),
        "files": [
            {
                "filename": f.get("filename", ""),
                "language": f.get("language") or "Other",
                "size":     f.get("size") or 0,
                "raw_url":  f.get("raw_url", ""),
            }
            for f in files.values() if f
        ],
        "commits": commits,  # [{ day, additions, deletions, total }]
        "total_commits":    len(commits),
        "total_additions":  sum(c.get("additions", 0) for c in commits),
        "total_deletions":  sum(c.get("deletions", 0) for c in commits),
    }


# ── Compare two users ──────────────────────────────────────────────────────────

async def fetch_compare_data(user1: str, user2: str, token: Optional[str]) -> dict:
    """Fetch both users in parallel, return merged comparison dict."""
    try:
        results = await asyncio.gather(
            fetch_user_data(user1, token),
            fetch_user_data(user2, token),
            return_exceptions=True,
        )
    except Exception as e:
        raise GistBoardError(f"Compare failed: {e}")

    out = {}
    for i, (uname, result) in enumerate(zip([user1, user2], results)):
        if isinstance(result, Exception):
            out[f"user{i+1}"] = {"error": str(result), "username": uname}
        else:
            out[f"user{i+1}"] = result

    return out