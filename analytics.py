"""
analytics.py — derived stats from already-fetched gist data.
No extra API calls — works purely from fetch_user_data() output.
"""

from collections import defaultdict
from datetime import datetime, timezone, timedelta

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def commit_day_distribution(heatmap: dict) -> list[dict]:
    """Commits grouped by day of week from heatmap."""
    counts = defaultdict(int)
    for day_str, count in heatmap.items():
        try:
            dt = datetime.strptime(day_str, "%Y-%m-%d")
            counts[DAYS[dt.weekday()]] += count
        except Exception:
            pass
    return [{"day": d, "commits": counts[d]} for d in DAYS]


def commit_month_distribution(heatmap: dict) -> list[dict]:
    """Commits grouped by month, last 12 months in order."""
    counts: dict[str, int] = defaultdict(int)
    for day_str, count in heatmap.items():
        try:
            counts[day_str[:7]] += count
        except Exception:
            pass
    today = datetime.now(timezone.utc)
    result = []
    for i in range(11, -1, -1):
        dt = today - timedelta(days=30 * i)
        key = dt.strftime("%Y-%m")
        result.append({"month": dt.strftime("%b %Y"), "key": key, "commits": counts.get(key, 0)})
    return result


def aging_report(all_gists: list[dict], stale_days: int = 180) -> dict:
    """Split gists into active / stale / throwaway."""
    today = datetime.now(timezone.utc).date()
    cutoff = str(today - timedelta(days=stale_days))
    active, stale, never = [], [], []

    for g in all_gists:
        updated = (g.get("updated_at") or "")[:10]
        created = (g.get("created_at") or "")[:10]
        desc    = g.get("description") or ""
        commits = g.get("commits", 1)

        try:
            age_days = (today - datetime.strptime(updated, "%Y-%m-%d").date()).days if updated else 0
        except Exception:
            age_days = 0

        entry = {
            "id":          g.get("id", ""),
            "description": desc or "(no description)",
            "url":         g.get("html_url", g.get("url", "#")),
            "public":      g.get("public", True),
            "updated_at":  updated,
            "created_at":  created,
            "language":    g.get("language", "Other"),
            "commits":     commits,
            "files":       g.get("files", []),
            "file_count":  g.get("file_count", 1),
            "comments":    g.get("comments", 0),
            "age_days":    age_days,
        }

        if not desc and commits <= 1:
            never.append(entry)
        elif updated and updated < cutoff:
            stale.append(entry)
        else:
            active.append(entry)

    stale.sort(key=lambda x: x["updated_at"], reverse=True)
    active.sort(key=lambda x: x["updated_at"], reverse=True)

    return {
        "active": active, "stale": stale, "never": never,
        "stale_days": stale_days,
        "counts": {"active": len(active), "stale": len(stale), "never": len(never), "total": len(all_gists)},
    }


def build_analytics(data: dict) -> dict:
    heatmap   = data.get("heatmap", {})
    all_gists = data.get("all_gists_full", data.get("recent", []))
    dow       = commit_day_distribution(heatmap)
    months    = commit_month_distribution(heatmap)

    def peak(items, lk, vk):
        if not items: return "—"
        best = max(items, key=lambda x: x[vk])
        return best[lk] if best[vk] > 0 else "—"

    return {
        "day_of_week": dow,
        "by_month":    months,
        "aging":       aging_report(all_gists),
        "peak_day":    peak(dow, "day", "commits"),
        "peak_month":  peak(months, "month", "commits"),
    }