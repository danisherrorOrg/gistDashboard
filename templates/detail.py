"""Gist detail page — commit timeline."""
from datetime import datetime, timezone

LANG_COLORS = {
    "Python":"#3572A5","JavaScript":"#f1e05a","TypeScript":"#2b7489",
    "Shell":"#89e051","Ruby":"#701516","Go":"#00ADD8","Rust":"#dea584",
    "C":"#555555","C++":"#f34b7d","Java":"#b07219","HTML":"#e34c26",
    "CSS":"#563d7c","Other":"#8b949e",
}

def lc(lang): return LANG_COLORS.get(lang, "#8b949e")
def _esc(s): return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")


def build_detail_html(detail: dict, username: str) -> str:
    commits   = detail.get("commits", [])
    files     = detail.get("files", [])
    gist_url  = detail.get("url", "#")
    pub_badge = '<span class="badge pub">public</span>' if detail.get("public") else '<span class="badge sec">secret</span>'

    # File tags
    file_tags = "".join(
        f'<span class="file-tag"><span class="dot" style="background:{lc(f.get("language","Other"))}"></span>'
        f'{_esc(f.get("filename",""))}</span>'
        for f in files
    )

    # Commit rows — newest first
    commit_rows = ""
    for i, c in enumerate(commits):
        day   = c.get("day", "")
        adds  = c.get("additions", 0)
        dels  = c.get("deletions", 0)
        total = c.get("total", 0)
        num   = len(commits) - i  # descending commit number
        bar_adds = min(int(adds / max(total, 1) * 80), 80) if total else 0
        bar_dels = min(int(dels / max(total, 1) * 80), 80) if total else 0

        commit_rows += f"""
        <div class="commit-row">
          <div class="commit-left">
            <span class="commit-num">#{num}</span>
            <span class="commit-day">{day}</span>
          </div>
          <div class="commit-bars">
            <div class="bar-wrap">
              <div class="bar add" style="width:{bar_adds}px" title="+{adds}"></div>
              <span class="bar-label add-label">+{adds}</span>
            </div>
            <div class="bar-wrap">
              <div class="bar del" style="width:{bar_dels}px" title="-{dels}"></div>
              <span class="bar-label del-label">-{dels}</span>
            </div>
          </div>
          <div class="commit-total">{total} lines</div>
        </div>"""

    if not commits:
        commit_rows = '<div class="empty">No commit history available.</div>'

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(detail.get('description','Gist'))} — Gist Board</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Unbounded:wght@700;900&display=swap" rel="stylesheet">
<style>
  :root{{--bg:#0d1117;--surface:#161b22;--border:#21262d;--border2:#30363d;
         --accent:#39d353;--text:#e6edf3;--dim:#8b949e;--muted:#484f58}}
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{background:var(--bg);color:var(--text);font-family:'IBM Plex Mono',monospace;font-size:13px}}
  a{{color:inherit;text-decoration:none}}
  .wrap{{max-width:680px;margin:0 auto;padding:24px 16px}}

  .back{{color:var(--dim);font-size:11px;display:inline-flex;align-items:center;gap:6px;
          margin-bottom:20px;padding:5px 10px;border:1px solid var(--border2);border-radius:6px}}
  .back:hover{{color:var(--accent);border-color:var(--accent)}}

  .header{{margin-bottom:20px}}
  .desc{{font-family:'Unbounded',sans-serif;font-size:18px;font-weight:700;
          line-height:1.3;margin-bottom:10px}}
  .meta{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px;font-size:11px;color:var(--dim)}}
  .badge{{font-size:9px;padding:2px 6px;border-radius:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px}}
  .badge.pub{{background:rgba(57,211,83,.1);color:var(--accent);border:1px solid rgba(57,211,83,.3)}}
  .badge.sec{{background:rgba(139,148,158,.1);color:var(--dim);border:1px solid var(--border)}}
  .file-tags{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:16px}}
  .file-tag{{display:inline-flex;align-items:center;gap:5px;padding:3px 8px;
              background:var(--surface);border:1px solid var(--border);border-radius:4px;font-size:11px}}
  .dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
  .gh-link{{display:inline-flex;align-items:center;gap:6px;padding:6px 12px;
             border:1px solid var(--border2);border-radius:6px;font-size:11px;color:var(--dim)}}
  .gh-link:hover{{border-color:var(--accent);color:var(--accent)}}

  .stats-bar{{display:grid;grid-template-columns:repeat(4,1fr);
               border:1px solid var(--border);border-radius:8px;margin-bottom:24px;overflow:hidden}}
  .stat{{padding:12px 8px;text-align:center;border-right:1px solid var(--border)}}
  .stat:last-child{{border-right:none}}
  .stat-val{{font-family:'Unbounded',sans-serif;font-size:20px;font-weight:700;color:var(--accent)}}
  .stat-label{{color:var(--dim);font-size:9px;margin-top:3px;text-transform:uppercase;letter-spacing:.5px}}

  .section-title{{font-size:10px;text-transform:uppercase;letter-spacing:1px;
                   color:var(--dim);margin-bottom:12px;display:flex;align-items:center;gap:8px}}
  .section-title::after{{content:'';flex:1;height:1px;background:var(--border)}}

  .commit-row{{display:flex;align-items:center;gap:12px;padding:8px 12px;
                border-bottom:1px solid rgba(30,30,46,.6);transition:background .1s}}
  .commit-row:hover{{background:rgba(255,255,255,.02)}}
  .commit-row:last-child{{border-bottom:none}}
  .commit-left{{display:flex;flex-direction:column;gap:2px;min-width:110px}}
  .commit-num{{color:var(--muted);font-size:10px}}
  .commit-day{{color:var(--text);font-size:12px}}
  .commit-bars{{flex:1;display:flex;flex-direction:column;gap:4px}}
  .bar-wrap{{display:flex;align-items:center;gap:6px}}
  .bar{{height:6px;border-radius:2px;min-width:2px;transition:width .3s}}
  .bar.add{{background:#26a641}}
  .bar.del{{background:#f85149}}
  .bar-label{{font-size:10px;min-width:36px}}
  .add-label{{color:#39d353}}
  .del-label{{color:#f85149}}
  .commit-total{{color:var(--muted);font-size:10px;min-width:60px;text-align:right}}

  .commits-container{{border:1px solid var(--border);border-radius:8px;overflow:hidden}}
  .empty{{padding:24px;text-align:center;color:var(--muted)}}
  .footer{{text-align:center;color:var(--muted);font-size:10px;padding-top:12px;
            border-top:1px solid var(--border);margin-top:16px}}
</style></head><body>
<div class="wrap">
  <a class="back" href="/embed/{username}">← @{username}</a>

  <div class="header">
    <div class="desc">{_esc(detail.get('description','(no description)'))}</div>
    <div class="meta">
      {pub_badge}
      <span>Created {detail.get('created_at','')}</span>
      <span>Updated {detail.get('updated_at','')}</span>
      <span>💬 {detail.get('comments',0)} comments</span>
    </div>
    <div class="file-tags">{file_tags}</div>
    <a class="gh-link" href="{gist_url}" target="_blank">
      <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor">
        <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
      </svg>
      View on GitHub
    </a>
  </div>

  <div class="stats-bar">
    <div class="stat"><div class="stat-val">{len(files)}</div><div class="stat-label">Files</div></div>
    <div class="stat"><div class="stat-val">{detail.get('total_commits',0)}</div><div class="stat-label">Commits</div></div>
    <div class="stat"><div class="stat-val">+{detail.get('total_additions',0)}</div><div class="stat-label">Additions</div></div>
    <div class="stat"><div class="stat-val">-{detail.get('total_deletions',0)}</div><div class="stat-label">Deletions</div></div>
  </div>

  <div class="section-title">Commit Timeline</div>
  <div class="commits-container">
    {commit_rows}
  </div>

  <div class="footer">gist-board · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</div>
</div>
</body></html>"""