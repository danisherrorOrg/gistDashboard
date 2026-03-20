from datetime import datetime, timezone, timedelta
from analytics import build_analytics

LANG_COLORS = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#2b7489",
    "Shell": "#89e051", "Ruby": "#701516", "Go": "#00ADD8", "Rust": "#dea584",
    "C": "#555555", "C++": "#f34b7d", "Java": "#b07219", "Kotlin": "#F18E33",
    "Swift": "#ffac45", "PHP": "#4F5D95", "HTML": "#e34c26", "CSS": "#563d7c",
    "Markdown": "#083fa1", "JSON": "#292929", "YAML": "#cb171e", "Other": "#8b949e",
}
HEAT_COLORS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]


def lc(lang): return LANG_COLORS.get(lang, LANG_COLORS["Other"])
def hc(n): return HEAT_COLORS[min(n, 4)]


def build_html(data: dict, username: str) -> str:
    p = data["profile"]
    s = data["stats"]
    heatmap = data["heatmap"]
    heatmap_detail = data.get("heatmap_detail", {})
    langs = data["languages"]
    recent = data["recent"]

    CELL, GAP, COLS = 11, 2, 53

    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=364)
    dow = start.weekday()
    start = start - timedelta(days=(dow + 1) % 7)

    # ── Heatmap cells ──────────────────────────────────────────────
    cells = []
    for col in range(COLS):
        for row in range(7):
            day = start + timedelta(days=col * 7 + row)
            if day > today:
                cells.append('<div class="cell empty"></div>')
                continue
            ds = str(day)
            count = heatmap.get(ds, 0)
            detail = heatmap_detail.get(ds, {})
            color = hc(count)


            gt = detail.get("gists_touched", 0)
            ad = detail.get("additions", 0)
            cells.append(
                f'<div class="cell" style="background:{color}" data-tip="{ds}||{count}||{gt}||{ad}"></div>'
            )

    heat_html = "\n".join(cells)

    # ── Month labels ───────────────────────────────────────────────
    # Build list of (col_index, month_label) for first col of each new month
    month_labels = []
    prev_month = None
    for col in range(COLS):
        day = start + timedelta(days=col * 7)
        if day.month != prev_month:
            prev_month = day.month
            month_labels.append((col, day.strftime("%b")))

    month_label_html = ""
    for col, label in month_labels:
        left = col * (CELL + GAP)
        month_label_html += f'<span class="month-label" style="left:{left}px">{label}</span>'

    # ── Language bars ──────────────────────────────────────────────
    total_lang = sum(c for _, c in langs) or 1
    lang_bars = ""
    for lang, count in langs:
        pct = round(count / total_lang * 100, 1)
        lang_bars += f"""
        <div class="lang-row">
          <div class="lang-name">
            <span class="lang-dot" style="background:{lc(lang)}"></span>{lang}
          </div>
          <div class="lang-bar-wrap">
            <div class="lang-bar" style="width:{pct}%;background:{lc(lang)}"></div>
          </div>
          <div class="lang-pct">{count} <span>({pct}%)</span></div>
        </div>"""

    # ── Recent gists ───────────────────────────────────────────────
    recent_html = ""
    for g in recent:
        pub_badge = (
            '<span class="badge pub">public</span>' if g["public"]
            else '<span class="badge sec">secret</span>'
        )
        files = ", ".join(g["files"][:3])
        if len(g["files"]) > 3:
            files += f" +{len(g['files'])-3} more"
        recent_html += f"""
        <a class="gist-card" href="/embed/{username}/gist/{g['id']}">
          <div class="gist-top">
            <span class="gist-lang-dot" style="background:{lc(g['language'])}"></span>
            <span class="gist-desc">{_esc(g['description'])}</span>
            {pub_badge}
          </div>
          <div class="gist-files">{_esc(files)}</div>
          <div class="gist-meta">
            <span>Updated {g['updated_at']}</span>
            <span>💬 {g['comments']}</span>
            <span>🔄 {g.get('commits', 1)} commit{'s' if g.get('commits', 1) != 1 else ''}</span>
          </div>
        </a>"""

    avatar_src = (
        f"data:image/jpeg;base64,{p['avatar_b64']}"
        if p.get("avatar_b64") else p["avatar_url"]
    )

    # Most active month display
    mam = s.get("most_active_month", "—")
    try:
        mam_display = datetime.strptime(mam, "%Y-%m").strftime("%b %Y")
    except Exception:
        mam_display = mam

    # Analytics
    analytics    = build_analytics(data)
    dow_data     = analytics["day_of_week"]    # [{ day, commits }]
    month_data   = analytics["by_month"]       # [{ month, commits }]
    aging        = analytics["aging"]
    peak_day     = analytics["peak_day"]
    peak_month   = analytics["peak_month"]

    # Day-of-week chart bars
    max_dow = max((d["commits"] for d in dow_data), default=1) or 1
    dow_bars = ""
    for d in dow_data:
        h = max(int(d["commits"] / max_dow * 60), 2) if d["commits"] else 2
        active = " active" if d["day"] == peak_day else ""
        tip = d["day"] + ": " + str(d["commits"])
        lbl = d["day"][:1]
        dow_bars += f'<div class="chart-bar-wrap"><div class="chart-bar{active}" style="height:{h}px" title="{tip}"></div><div class="chart-label">{lbl}</div></div>'

    # Month chart bars
    max_mo = max((m["commits"] for m in month_data), default=1) or 1
    mo_bars = ""
    for m in month_data:
        h = max(int(m["commits"] / max_mo * 60), 2) if m["commits"] else 2
        active = " active" if m["month"] == peak_month else ""
        tip = m["month"] + ": " + str(m["commits"])
        lbl = m["month"][:1]
        mo_bars += f'<div class="chart-bar-wrap"><div class="chart-bar{active}" style="height:{h}px" title="{tip}"></div><div class="chart-label">{lbl}</div></div>'

    # Aging report rows (stale only, max 5)
    aging_rows = ""
    for g in aging["stale"][:5]:
        gid  = g["id"]
        desc = _esc(g["description"])
        age  = g["age_days"]
        nc   = g["commits"]
        cs   = "s" if nc != 1 else ""
        aging_rows += (
            f'<a class="aging-row" href="/embed/{username}/gist/{gid}">'
            f'<span class="aging-desc">{desc}</span>'
            f'<span class="aging-meta">{age}d ago · {nc} commit{cs}</span>'
            f'</a>'
        )
    if not aging_rows:
        aging_rows = '<div class="aging-empty">No stale gists — all recently active 🎉</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>@{p['login']} — Gist Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Unbounded:wght@700;900&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0d1117; --surface: #161b22; --surface2: #1c2128;
    --border: #21262d; --border2: #30363d;
    --accent: #39d353; --accent2: #26a641;
    --text: #e6edf3; --text-dim: #8b949e; --text-muted: #484f58;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    background: var(--bg); color: var(--text);
    font-family: 'IBM Plex Mono', monospace; font-size: 13px;
  }}
  a {{ color: inherit; text-decoration: none; }}

  .wrap {{ max-width: 560px; margin: 0 auto; padding: 20px 16px; }}

  /* ── Profile ── */
  .profile {{ display:flex; gap:16px; align-items:flex-start; margin-bottom:20px; }}
  .avatar {{ width:64px; height:64px; border-radius:50%; border:2px solid var(--border2); flex-shrink:0; }}
  .profile-info {{ flex:1; min-width:0; }}
  .profile-name {{ font-family:'Unbounded',sans-serif; font-size:15px; font-weight:700; }}
  .profile-login {{ color:var(--text-dim); font-size:12px; margin-top:2px; }}
  .profile-meta {{ color:var(--text-dim); font-size:11px; margin-top:5px; display:flex; flex-wrap:wrap; gap:10px; }}
  .profile-meta span {{ display:flex; align-items:center; gap:4px; }}
  .profile-follow {{ color:var(--text-dim); font-size:11px; margin-top:6px; }}
  .profile-follow strong {{ color:var(--text); }}
  .gh-link {{
    display:inline-flex; align-items:center; gap:6px; margin-top:10px;
    padding:5px 10px; border:1px solid var(--border2); border-radius:6px;
    font-size:11px; color:var(--text-dim); transition:border-color .15s, color .15s;
  }}
  .gh-link:hover {{ border-color:var(--accent); color:var(--accent); }}

  /* ── Stats bar ── */
  .stats-bar {{
    display:grid; grid-template-columns:repeat(5,1fr);
    border:1px solid var(--border); border-radius:8px;
    margin-bottom:20px; overflow:hidden;
  }}
  @media(max-width:480px) {{
    .stats-bar {{ grid-template-columns:repeat(3,1fr); }}
    .stats-bar .stat:nth-child(4),
    .stats-bar .stat:nth-child(5) {{ border-top:1px solid var(--border); }}
  }}
  .stat {{
    padding:12px 8px; text-align:center;
    border-right:1px solid var(--border);
  }}
  .stat:last-child {{ border-right:none; }}
  .stat-val {{ font-family:'Unbounded',sans-serif; font-size:18px; font-weight:700; color:var(--accent); }}
  .stat-label {{ color:var(--text-dim); font-size:9px; margin-top:3px; text-transform:uppercase; letter-spacing:.5px; }}

  /* ── Section ── */
  .section {{ margin-bottom:20px; }}
  .section-title {{
    font-size:10px; text-transform:uppercase; letter-spacing:1px;
    color:var(--text-dim); margin-bottom:10px;
    display:flex; align-items:center; gap:8px;
  }}
  .section-title::after {{ content:''; flex:1; height:1px; background:var(--border); }}

  /* ── Heatmap ── */
  .heatmap-outer {{ overflow-x:auto; padding-bottom:4px; }}
  .heatmap-months {{
    position:relative; height:16px; margin-bottom:4px;
    width: max-content; min-width: 100%;
  }}
  .month-label {{
    position:absolute; top:0; font-size:10px; color:var(--text-muted); white-space:nowrap;
  }}
  .heatmap {{
    display:grid;
    grid-template-rows:repeat(7,{CELL}px);
    grid-auto-flow:column;
    grid-auto-columns:{CELL}px;
    gap:{GAP}px;
    width:max-content;
  }}
  .cell {{
    width:{CELL}px; height:{CELL}px; border-radius:2px;
    cursor:pointer; transition:transform .12s, box-shadow .12s;
  }}
  .cell:hover {{ transform:scale(1.6); box-shadow:0 0 0 1.5px #39d353; }}
  .cell.empty {{ background:transparent; cursor:default; }}
  .cell.empty:hover {{ transform:none; box-shadow:none; }}

  /* Floating tooltip card */
  #heat-tooltip {{
    position:fixed;
    background:#1c2128;
    border:1px solid #30363d;
    border-radius:6px;
    padding:8px 12px;
    font-size:11px;
    color:#e6edf3;
    pointer-events:none;
    z-index:9999;
    opacity:0;
    transition:opacity .1s;
    box-shadow:0 8px 24px rgba(0,0,0,.5);
    white-space:nowrap;
    min-width:160px;
  }}
  #heat-tooltip.visible {{ opacity:1; }}
  #heat-tooltip .tip-date {{
    color:#8b949e; font-size:10px; margin-bottom:4px;
  }}
  #heat-tooltip .tip-count {{
    color:#e6edf3; font-weight:600; font-size:13px;
  }}
  #heat-tooltip .tip-detail {{
    color:#8b949e; font-size:10px; margin-top:3px;
  }}
  #heat-tooltip .tip-empty {{
    color:#484f58; font-size:11px;
  }}

  .heat-summary {{
    display:flex; align-items:center; justify-content:space-between;
    margin-bottom:8px; flex-wrap:wrap; gap:6px;
  }}
  .heat-sub {{ font-size:11px; color:var(--text-dim); }}
  .heat-legend {{
    display:flex; align-items:center; gap:4px;
    font-size:10px; color:var(--text-muted);
  }}
  .heat-legend .cell {{ cursor:default; }}
  .heat-legend .cell:hover {{ transform:none; }}

  /* Activity breakdown pills */
  .activity-pills {{ display:flex; gap:8px; margin-top:8px; flex-wrap:wrap; }}
  .pill {{
    font-size:10px; padding:2px 8px; border-radius:10px;
    border:1px solid var(--border2); color:var(--text-dim);
  }}
  .pill span {{ color:var(--accent); font-weight:600; }}

  /* ── Language bars ── */
  .lang-row {{
    display:grid; grid-template-columns:110px 1fr 70px;
    align-items:center; gap:10px; margin-bottom:8px;
  }}
  @media(max-width:400px) {{
    .lang-row {{ grid-template-columns:90px 1fr 55px; }}
  }}
  .lang-name {{ display:flex; align-items:center; gap:6px; color:var(--text); font-size:12px; overflow:hidden; }}
  .lang-name span:last-child {{ white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .lang-dot {{ width:10px; height:10px; border-radius:50%; flex-shrink:0; }}
  .lang-bar-wrap {{ background:var(--border); border-radius:3px; height:6px; overflow:hidden; }}
  .lang-bar {{ height:100%; border-radius:3px; transition:width .6s cubic-bezier(.4,0,.2,1); }}
  .lang-pct {{ color:var(--text-dim); font-size:11px; text-align:right; }}
  .lang-pct span {{ color:var(--text-muted); font-size:10px; }}

  /* ── Gist cards ── */
  .gist-card {{
    display:block; padding:12px 14px;
    border:1px solid var(--border); border-radius:8px; margin-bottom:8px;
    transition:border-color .15s, background .15s;
  }}
  .gist-card:hover {{ border-color:var(--border2); background:var(--surface); }}
  .gist-top {{ display:flex; align-items:center; gap:8px; margin-bottom:4px; }}
  .gist-lang-dot {{ width:10px; height:10px; border-radius:50%; flex-shrink:0; }}
  .gist-desc {{ flex:1; font-size:12px; color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .badge {{
    font-size:9px; padding:2px 6px; border-radius:10px; flex-shrink:0;
    text-transform:uppercase; letter-spacing:.5px; font-weight:600;
  }}
  .badge.pub {{ background:rgba(57,211,83,.1); color:var(--accent); border:1px solid rgba(57,211,83,.3); }}
  .badge.sec {{ background:rgba(139,148,158,.1); color:var(--text-dim); border:1px solid var(--border); }}
  .gist-files {{ font-size:10px; color:var(--text-dim); margin-bottom:6px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .gist-meta {{ display:flex; gap:12px; font-size:10px; color:var(--text-muted); }}

  /* ── Charts ── */
  .charts-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
  @media(max-width:480px) {{ .charts-grid {{ grid-template-columns:1fr; }} }}
  .chart-wrap {{ border:1px solid var(--border); border-radius:8px; padding:14px; }}
  .chart-title {{ font-size:10px; color:var(--text-dim); text-transform:uppercase;
                  letter-spacing:.5px; margin-bottom:10px; }}
  .chart-bars {{ display:flex; align-items:flex-end; gap:4px; height:70px; }}
  .chart-bar-wrap {{ display:flex; flex-direction:column; align-items:center; gap:3px; flex:1; }}
  .chart-bar {{ width:100%; border-radius:2px 2px 0 0; background:var(--border2);
                transition:background .15s; min-height:2px; }}
  .chart-bar.active {{ background:var(--accent); }}
  .chart-bar-wrap:hover .chart-bar {{ background:#4d9fff; }}
  .chart-label {{ font-size:9px; color:var(--text-muted); }}

  /* ── Aging ── */
  .aging-row {{ display:flex; justify-content:space-between; align-items:center;
                padding:8px 12px; border-bottom:1px solid rgba(30,30,46,.6);
                text-decoration:none; transition:background .1s; }}
  .aging-row:last-child {{ border-bottom:none; }}
  .aging-row:hover {{ background:rgba(255,255,255,.02); }}
  .aging-desc {{ font-size:12px; color:var(--text); white-space:nowrap; overflow:hidden;
                 text-overflow:ellipsis; max-width:300px; }}
  .aging-meta {{ font-size:10px; color:var(--text-muted); flex-shrink:0; margin-left:10px; }}
  .aging-empty {{ padding:16px; text-align:center; color:var(--text-muted); font-size:11px; }}
  .aging-container {{ border:1px solid var(--border); border-radius:8px; overflow:hidden; }}

  /* ── Skeleton loading ── */
  .skeleton {{ background:var(--surface); border-radius:8px; }}
  @keyframes shimmer {{
    0%   {{ background-position:-400px 0; }}
    100% {{ background-position: 400px 0; }}
  }}
  .skeleton-pulse {{
    background:linear-gradient(90deg,var(--surface) 25%,var(--border) 50%,var(--surface) 75%);
    background-size:400px 100%;
    animation:shimmer 1.4s infinite;
    border-radius:4px;
  }}

  /* ── Footer ── */
  .footer {{
    text-align:center; color:var(--text-muted); font-size:10px;
    padding-top:12px; border-top:1px solid var(--border); margin-top:8px;
  }}
  .footer a {{ color:var(--accent); }}
</style>
</head>
<body>
<div class="wrap">

  <!-- Profile -->
  <div class="profile">
    <img class="avatar" src="{avatar_src}" alt="{p['login']}">
    <div class="profile-info">
      <div class="profile-name">{_esc(p['name'])}</div>
      <div class="profile-login">@{_esc(p['login'])}</div>
      <div class="profile-meta">
        {('<span>🏢 ' + _esc(p['company']) + '</span>') if p.get('company') else ''}
        {('<span>📍 ' + _esc(p['location']) + '</span>') if p.get('location') else ''}
      </div>
      <div class="profile-follow">
        <strong>{p['followers']}</strong> followers &nbsp;·&nbsp;
        <strong>{p['following']}</strong> following
      </div>
      <a class="gh-link" href="{p['html_url']}" target="_blank">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
          <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38
          0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13
          -.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66
          .07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15
          -.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0
          1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82
          1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01
          1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
        </svg>
        View on GitHub
      </a>
    </div>
  </div>

  <!-- Stats -->
  <div class="stats-bar">
    <div class="stat"><div class="stat-val">{s['total']}</div><div class="stat-label">Total</div></div>
    <div class="stat"><div class="stat-val">{s['public']}</div><div class="stat-label">Public</div></div>
    <div class="stat"><div class="stat-val">{s['secret']}</div><div class="stat-label">Secret</div></div>
    <div class="stat"><div class="stat-val">{s['total_comments']}</div><div class="stat-label">Comments</div></div>
    <div class="stat"><div class="stat-val">{s['year_commits']}</div><div class="stat-label">This Year</div></div>
  </div>

  <!-- Heatmap -->
  <div class="section">
    <div class="section-title">Activity</div>
    <div class="heat-summary">
      <span class="heat-sub">
        <strong style="color:var(--text)">{s['year_commits']}</strong>
        action{'s' if s['year_commits'] != 1 else ''} in the last year
      </span>
      <div class="heat-legend">
        Less
        <div class="cell" style="background:{hc(0)}"></div>
        <div class="cell" style="background:{hc(1)}"></div>
        <div class="cell" style="background:{hc(2)}"></div>
        <div class="cell" style="background:{hc(3)}"></div>
        <div class="cell" style="background:{hc(4)}"></div>
        More
      </div>
    </div>
    <div class="activity-pills">
      <div class="pill">📝 Commits &nbsp;<span>{s.get('total_commits', 0)}</span></div>
      <div class="pill">🔥 Most active &nbsp;<span>{mam_display}</span></div>
      <div class="pill">⚡ Current streak &nbsp;<span>{s['current_streak']}d</span></div>
      <div class="pill">🏆 Longest streak &nbsp;<span>{s['longest_streak']}d</span></div>
      <div class="pill">📅 Last active &nbsp;<span>{s['last_active']}</span></div>
    </div>
    <div class="heatmap-outer" style="margin-top:12px">
      <div class="heatmap-months">{month_label_html}</div>
      <div class="heatmap">{heat_html}</div>
    </div>
  </div>

  <!-- Languages -->
  <div class="section">
    <div class="section-title">Languages</div>
    {lang_bars}
  </div>

  <!-- Recent gists -->
  <div class="section">
    <div class="section-title" style="justify-content:space-between">
      <span>Recent Gists</span>
      <a href="/gists/{username}" style="font-size:10px;color:var(--accent);border:1px solid rgba(57,211,83,.3);padding:2px 8px;border-radius:4px;font-weight:normal;letter-spacing:0;text-transform:none">View all {s['total']} →</a>
    </div>
    {recent_html}
  </div>

  <!-- Analytics -->
  <div class="section">
    <div class="section-title">Analytics</div>
    <div class="charts-grid">
      <div class="chart-wrap">
        <div class="chart-title">Day of Week · peak: {peak_day}</div>
        <div class="chart-bars">{dow_bars}</div>
      </div>
      <div class="chart-wrap">
        <div class="chart-title">By Month · peak: {peak_month}</div>
        <div class="chart-bars">{mo_bars}</div>
      </div>
    </div>
  </div>

  <!-- Aging report -->
  <div class="section">
    <div class="section-title">
      Stale Gists
      <span style="color:var(--text-muted);font-size:10px;margin-left:4px;font-weight:normal">
        ({aging['counts']['stale']} of {aging['counts']['total']} not touched in 6+ months)
      </span>
    </div>
    <div class="aging-container">{aging_rows}</div>
  </div>

  <div class="footer">
    gist-board &nbsp;·&nbsp;
    <a href="?user={p['login']}">@{p['login']}</a> &nbsp;·&nbsp;
    {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
  </div>

</div>

  <!-- Floating heatmap tooltip -->
  <div id="heat-tooltip">
    <div class="tip-date" id="tip-date"></div>
    <div id="tip-body"></div>
  </div>

  <script>
    const tooltip = document.getElementById('heat-tooltip');
    const tipDate = document.getElementById('tip-date');
    const tipBody = document.getElementById('tip-body');

    document.querySelectorAll('.heatmap .cell:not(.empty)').forEach(cell => {{
      const raw = cell.dataset.tip || '';

      cell.addEventListener('mouseenter', e => {{
        // Parse data-tip: "2026-03-01||3||2||1" (date||commits||gists||additions)
        const parts = raw.split('||');
        const date   = parts[0] || '';
        const commits = parseInt(parts[1]) || 0;
        const gists   = parseInt(parts[2]) || 0;
        const adds    = parseInt(parts[3]) || 0;

        tipDate.textContent = new Date(date + 'T00:00:00').toLocaleDateString('en-US', {{
          weekday:'short', year:'numeric', month:'short', day:'numeric'
        }});

        if (commits === 0) {{
          tipBody.innerHTML = '<span class="tip-empty">No activity</span>';
        }} else {{
          tipBody.innerHTML =
            '<div class="tip-count">' + commits + ' file commit' + (commits !== 1 ? 's' : '') + '</div>' +
            '<div class="tip-detail">' + gists + ' gist' + (gists !== 1 ? 's' : '') + ' touched' +
            (adds > 0 ? ' · +' + adds + ' lines' : '') + '</div>';
        }}

        tooltip.classList.add('visible');
        moveTooltip(e);
      }});

      cell.addEventListener('mousemove', moveTooltip);

      cell.addEventListener('mouseleave', () => {{
        tooltip.classList.remove('visible');
      }});
    }});

    function moveTooltip(e) {{
      const pad = 14;
      const tw = tooltip.offsetWidth;
      const th = tooltip.offsetHeight;
      let x = e.clientX + pad;
      let y = e.clientY - th - pad;
      // keep inside viewport
      if (x + tw > window.innerWidth - 8)  x = e.clientX - tw - pad;
      if (y < 8) y = e.clientY + pad;
      tooltip.style.left = x + 'px';
      tooltip.style.top  = y + 'px';
    }}
  </script>

</body>
</html>"""


def _esc(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")