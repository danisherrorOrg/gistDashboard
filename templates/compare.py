"""Compare two users side-by-side."""
from datetime import datetime, timezone

LANG_COLORS = {
    "Python":"#3572A5","JavaScript":"#f1e05a","TypeScript":"#2b7489",
    "Shell":"#89e051","Go":"#00ADD8","Rust":"#dea584","Other":"#8b949e",
}
HEAT_COLORS = ["#161b22","#0e4429","#006d32","#26a641","#39d353"]

def lc(lang): return LANG_COLORS.get(lang, "#8b949e")
def hc(n): return HEAT_COLORS[min(n, 4)]
def _esc(s): return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")


def _user_col(data: dict, side: str) -> str:
    """Render one user column. side = 'left' | 'right'."""
    if "error" in data:
        return f'<div class="col-error">{_esc(data["error"])}</div>'

    p  = data["profile"]
    s  = data["stats"]
    langs = data.get("languages", [])

    avatar_src = (
        f"data:image/jpeg;base64,{p['avatar_b64']}"
        if p.get("avatar_b64") else p.get("avatar_url","")
    )

    # Mini heatmap — 26 weeks
    from datetime import timedelta
    heatmap = data.get("heatmap", {})
    today   = datetime.now(timezone.utc).date()
    start   = today - timedelta(days=181)
    cells   = ""
    for col in range(26):
        col_html = ""
        for row in range(7):
            day = start + timedelta(days=col*7+row)
            if day > today:
                col_html += '<div class="hcell" style="background:transparent"></div>'
                continue
            n = min(heatmap.get(str(day), 0), 4)
            col_html += f'<div class="hcell" style="background:{hc(n)}" title="{day}: {heatmap.get(str(day),0)}"></div>'
        cells += f'<div class="hcol">{col_html}</div>'

    # Languages
    total_lang = sum(c for _, c in langs) or 1
    lang_bars  = ""
    for lang, count in langs[:4]:
        pct = round(count / total_lang * 100)
        lang_bars += f"""<div class="lang-row">
          <span class="ldot" style="background:{lc(lang)}"></span>
          <span class="lname">{lang}</span>
          <div class="lbar-wrap"><div class="lbar" style="width:{pct}%;background:{lc(lang)}"></div></div>
          <span class="lpct">{pct}%</span>
        </div>"""

    align = "left" if side == "left" else "right"

    return f"""
    <div class="user-col {side}">
      <div class="user-header">
        <img class="avatar" src="{avatar_src}" alt="{p['login']}">
        <div>
          <div class="uname">{_esc(p.get('name',''))}</div>
          <div class="ulogin"><a href="/embed/{p['login']}">@{p['login']}</a></div>
          {('<div class="uloc">📍 ' + _esc(p.get('location','')) + '</div>') if p.get('location') else ''}
        </div>
      </div>
      <div class="user-stats">
        <div class="ustat"><span class="uval">{s['total']}</span><span class="ulbl">Gists</span></div>
        <div class="ustat"><span class="uval">{s['total_commits']}</span><span class="ulbl">Commits</span></div>
        <div class="ustat"><span class="uval">{s['year_commits']}</span><span class="ulbl">This Year</span></div>
        <div class="ustat"><span class="uval">{s['longest_streak']}d</span><span class="ulbl">Streak</span></div>
      </div>
      <div class="user-heat"><div class="heat-grid">{cells}</div></div>
      <div class="user-langs">{lang_bars}</div>
    </div>"""


def build_compare_html(data: dict, user1: str, user2: str) -> str:
    d1 = data.get("user1", {})
    d2 = data.get("user2", {})

    col1 = _user_col(d1, "left")
    col2 = _user_col(d2, "right")

    # Winner badges per metric
    def winner(key, reverse=False):
        v1 = d1.get("stats", {}).get(key, 0) if "error" not in d1 else -1
        v2 = d2.get("stats", {}).get(key, 0) if "error" not in d2 else -1
        if v1 == v2: return "tie"
        return "left" if (v1 > v2) != reverse else "right"

    badges = {
        "total":         winner("total"),
        "total_commits": winner("total_commits"),
        "year_commits":  winner("year_commits"),
        "longest_streak": winner("longest_streak"),
    }

    def badge_row(label, key):
        w = badges[key]
        l1 = d1.get("stats", {}).get(key, "—") if "error" not in d1 else "—"
        l2 = d2.get("stats", {}).get(key, "—") if "error" not in d2 else "—"
        left_w  = '🏆' if w == 'left'  else ''
        right_w = '🏆' if w == 'right' else ''
        tie     = '=' if w == 'tie' else ''
        return f"""<div class="vs-row">
          <span class="vs-val {'winner' if w=='left' else ''}">{left_w} {l1}</span>
          <span class="vs-label">{label} {tie}</span>
          <span class="vs-val {'winner' if w=='right' else ''}">{l2} {right_w}</span>
        </div>"""

    vs_rows = (
        badge_row("Gists",       "total") +
        badge_row("Commits",     "total_commits") +
        badge_row("This Year",   "year_commits") +
        badge_row("Streak",      "longest_streak")
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta property="og:title" content="@{user1} vs @{user2} — Gist Board">
<title>@{user1} vs @{user2} — Gist Board</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Unbounded:wght@700;900&display=swap" rel="stylesheet">
<style>
  :root{{--bg:#0d1117;--surface:#161b22;--border:#21262d;--border2:#30363d;
         --accent:#39d353;--text:#e6edf3;--dim:#8b949e;--muted:#484f58}}
  *{{margin:0;padding:0;box-sizing:border-box}} body{{background:var(--bg);color:var(--text);
     font-family:'IBM Plex Mono',monospace;font-size:13px}} a{{color:inherit;text-decoration:none}}

  .wrap{{max-width:900px;margin:0 auto;padding:24px 16px}}
  .page-title{{font-family:'Unbounded',sans-serif;font-size:24px;font-weight:900;
                text-align:center;margin-bottom:4px}}
  .page-sub{{color:var(--dim);font-size:11px;text-align:center;margin-bottom:28px}}
  .back{{color:var(--dim);font-size:11px;display:inline-flex;align-items:center;gap:6px;
          margin-bottom:20px;padding:5px 10px;border:1px solid var(--border2);border-radius:6px}}
  .back:hover{{color:var(--accent);border-color:var(--accent)}}

  /* VS scorecard */
  .vs-card{{border:1px solid var(--border);border-radius:8px;margin-bottom:24px;overflow:hidden}}
  .vs-row{{display:grid;grid-template-columns:1fr auto 1fr;padding:10px 16px;
            border-bottom:1px solid rgba(30,30,46,.6);align-items:center}}
  .vs-row:last-child{{border-bottom:none}}
  .vs-val{{font-size:14px;font-weight:600;color:var(--dim)}}
  .vs-val.winner{{color:var(--accent)}}
  .vs-val:first-child{{text-align:left}}
  .vs-val:last-child{{text-align:right}}
  .vs-label{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;text-align:center}}

  /* Two-column layout */
  .cols{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
  @media(max-width:600px){{.cols{{grid-template-columns:1fr}}}}

  .user-col{{border:1px solid var(--border);border-radius:8px;padding:16px;background:var(--surface)}}
  .user-col.left{{border-top:2px solid var(--accent)}}
  .user-col.right{{border-top:2px solid #4d9fff}}

  .user-header{{display:flex;gap:12px;align-items:flex-start;margin-bottom:14px}}
  .avatar{{width:52px;height:52px;border-radius:50%;border:2px solid var(--border2);flex-shrink:0}}
  .uname{{font-family:'Unbounded',sans-serif;font-size:13px;font-weight:700}}
  .ulogin{{color:var(--dim);font-size:11px;margin-top:2px}}
  .ulogin a:hover{{color:var(--accent)}}
  .uloc{{color:var(--muted);font-size:10px;margin-top:3px}}

  .user-stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:4px;margin-bottom:14px}}
  .ustat{{text-align:center;padding:8px 4px;background:var(--bg);border-radius:4px}}
  .uval{{display:block;font-family:'Unbounded',sans-serif;font-size:14px;font-weight:700;color:var(--accent)}}
  .ulbl{{display:block;font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-top:2px}}

  .user-heat{{margin-bottom:14px;overflow-x:auto}}
  .heat-grid{{display:flex;gap:2px;width:max-content}}
  .hcol{{display:flex;flex-direction:column;gap:2px}}
  .hcell{{width:8px;height:8px;border-radius:1px}}

  .user-langs .lang-row{{display:grid;grid-template-columns:12px 70px 1fr 28px;
                           align-items:center;gap:6px;margin-bottom:6px}}
  .ldot{{width:10px;height:10px;border-radius:50%}}
  .lname{{font-size:11px;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
  .lbar-wrap{{background:var(--border);border-radius:2px;height:5px;overflow:hidden}}
  .lbar{{height:100%;border-radius:2px}}
  .lpct{{font-size:10px;color:var(--muted);text-align:right}}

  .col-error{{color:var(--dim);padding:20px;text-align:center}}
  .footer{{text-align:center;color:var(--muted);font-size:10px;padding-top:12px;
            border-top:1px solid var(--border);margin-top:16px}}
</style></head><body>
<div class="wrap">
  <a class="back" href="/">← Home</a>
  <div class="page-title">@{user1} <span style="color:var(--dim)">vs</span> @{user2}</div>
  <div class="page-sub">Gist activity comparison</div>

  <div class="vs-card">{vs_rows}</div>

  <div class="cols">{col1}{col2}</div>

  <div class="footer">gist-board · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</div>
</div>
</body></html>"""