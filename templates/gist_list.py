"""Full paginated gist list page — /gists/{username}"""
from datetime import datetime, timezone

LANG_COLORS = {
    "Python":"#3572A5","JavaScript":"#f1e05a","TypeScript":"#2b7489",
    "Shell":"#89e051","Ruby":"#701516","Go":"#00ADD8","Rust":"#dea584",
    "C":"#555555","C++":"#f34b7d","Java":"#b07219","Kotlin":"#F18E33",
    "Swift":"#ffac45","PHP":"#4F5D95","HTML":"#e34c26","CSS":"#563d7c",
    "Markdown":"#083fa1","JSON":"#292929","YAML":"#cb171e","Other":"#8b949e",
}

def lc(lang): return LANG_COLORS.get(lang, "#8b949e")
def _esc(s):   return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")


def build_gist_list_html(data: dict, username: str, page: int = 1,
                          per_page: int = 20, lang_filter: str = "",
                          visibility: str = "all", q: str = "") -> str:
    p          = data["profile"]
    all_gists  = data.get("all_gists_full", data.get("recent", []))

    # ── Filter ─────────────────────────────────────────────────────
    filtered = all_gists
    if visibility == "public":
        filtered = [g for g in filtered if g.get("public")]
    elif visibility == "secret":
        filtered = [g for g in filtered if not g.get("public")]
    if lang_filter:
        filtered = [g for g in filtered if g.get("language","").lower() == lang_filter.lower()]
    if q:
        ql = q.lower()
        filtered = [g for g in filtered if
                    ql in g.get("description","").lower() or
                    any(ql in f.lower() for f in g.get("files",[]))]

    # ── Sort — newest updated first ─────────────────────────────────
    filtered = sorted(filtered, key=lambda g: g.get("updated_at",""), reverse=True)

    # ── Paginate ───────────────────────────────────────────────────
    total       = len(filtered)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page        = max(1, min(page, total_pages))
    start       = (page - 1) * per_page
    page_gists  = filtered[start:start + per_page]

    # ── Language options for filter dropdown ───────────────────────
    lang_counts: dict[str, int] = {}
    for g in all_gists:
        l = g.get("language", "Other")
        lang_counts[l] = lang_counts.get(l, 0) + 1
    lang_options = sorted(lang_counts.items(), key=lambda x: -x[1])

    lang_opts_html = '<option value="">All languages</option>'
    for l, c in lang_options:
        sel = 'selected' if l == lang_filter else ''
        lang_opts_html += f'<option value="{_esc(l)}" {sel}>{_esc(l)} ({c})</option>'

    # ── Gist cards ─────────────────────────────────────────────────
    cards_html = ""
    for g in page_gists:
        gid   = g.get("id","")
        desc  = _esc(g.get("description","(no description)"))
        url   = g.get("url","#")
        pub   = g.get("public", True)
        lang  = g.get("language","Other")
        files = g.get("files",[])
        nc    = g.get("commits",1)
        upd   = g.get("updated_at","")
        cre   = g.get("created_at","")
        nf    = g.get("file_count",1)

        badge     = '<span class="badge pub">public</span>' if pub else '<span class="badge sec">secret</span>'
        files_str = _esc(", ".join(files[:3]) + (f" +{len(files)-3} more" if len(files) > 3 else ""))
        color     = lc(lang)

        cards_html += f"""
        <a class="gist-card" href="/embed/{username}/gist/{gid}">
          <div class="gc-top">
            <span class="gc-dot" style="background:{color}"></span>
            <span class="gc-desc">{desc}</span>
            {badge}
          </div>
          <div class="gc-files">{files_str}</div>
          <div class="gc-meta">
            <span>{lang}</span>
            <span>📄 {nf} file{"s" if nf != 1 else ""}</span>
            <span>🔄 {nc} commit{"s" if nc != 1 else ""}</span>
            <span>Updated {upd}</span>
            <span>Created {cre}</span>
            <a class="gc-gh" href="{url}" target="_blank" onclick="event.stopPropagation()">↗ GitHub</a>
          </div>
        </a>"""

    if not cards_html:
        cards_html = '<div class="empty">No gists match your filters.</div>'

    # ── Pagination controls ─────────────────────────────────────────
    def page_url(n):
        params = f"page={n}"
        if lang_filter: params += f"&lang={lang_filter}"
        if visibility != "all": params += f"&visibility={visibility}"
        if q: params += f"&q={q}"
        return f"/gists/{username}?{params}"

    pag_html = ""
    if total_pages > 1:
        # prev
        if page > 1:
            pag_html += f'<a class="pag-btn" href="{page_url(page-1)}">← Prev</a>'
        else:
            pag_html += '<span class="pag-btn disabled">← Prev</span>'

        # page numbers — show window of 5 around current
        lo = max(1, page - 2)
        hi = min(total_pages, page + 2)
        if lo > 1:
            pag_html += f'<a class="pag-btn" href="{page_url(1)}">1</a>'
            if lo > 2: pag_html += '<span class="pag-ellipsis">…</span>'
        for n in range(lo, hi + 1):
            active = 'active' if n == page else ''
            pag_html += f'<a class="pag-btn {active}" href="{page_url(n)}">{n}</a>'
        if hi < total_pages:
            if hi < total_pages - 1: pag_html += '<span class="pag-ellipsis">…</span>'
            pag_html += f'<a class="pag-btn" href="{page_url(total_pages)}">{total_pages}</a>'

        # next
        if page < total_pages:
            pag_html += f'<a class="pag-btn" href="{page_url(page+1)}">Next →</a>'
        else:
            pag_html += '<span class="pag-btn disabled">Next →</span>'

    # ── Visibility tabs ─────────────────────────────────────────────
    def tab(label, vis, count):
        active = 'active' if visibility == vis else ''
        params = f"visibility={vis}"
        if lang_filter: params += f"&lang={lang_filter}"
        if q: params += f"&q={q}"
        return f'<a class="tab {active}" href="/gists/{username}?{params}">{label} <span class="tab-count">{count}</span></a>'

    pub_count = sum(1 for g in all_gists if g.get("public"))
    sec_count = len(all_gists) - pub_count

    tabs_html = (
        tab("All",    "all",    len(all_gists)) +
        tab("Public", "public", pub_count) +
        tab("Secret", "secret", sec_count)
    )

    avatar_src = (
        f"data:image/jpeg;base64,{p['avatar_b64']}"
        if p.get("avatar_b64") else p.get("avatar_url","")
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>@{p['login']} gists — Gist Board</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Unbounded:wght@700;900&display=swap" rel="stylesheet">
<style>
  :root{{--bg:#0d1117;--surface:#161b22;--border:#21262d;--border2:#30363d;
         --accent:#39d353;--text:#e6edf3;--dim:#8b949e;--muted:#484f58}}
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{background:var(--bg);color:var(--text);font-family:'IBM Plex Mono',monospace;font-size:13px}}
  a{{color:inherit;text-decoration:none}}
  .wrap{{max-width:720px;margin:0 auto;padding:24px 16px}}

  /* Header */
  .page-header{{display:flex;align-items:center;gap:14px;margin-bottom:24px}}
  .avatar{{width:48px;height:48px;border-radius:50%;border:2px solid var(--border2);flex-shrink:0}}
  .page-title{{font-family:'Unbounded',sans-serif;font-size:18px;font-weight:700}}
  .page-sub{{color:var(--dim);font-size:11px;margin-top:2px}}
  .header-links{{margin-left:auto;display:flex;gap:8px}}
  .hlink{{padding:5px 10px;border:1px solid var(--border2);border-radius:6px;
           font-size:11px;color:var(--dim)}}
  .hlink:hover{{border-color:var(--accent);color:var(--accent)}}

  /* Toolbar */
  .toolbar{{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;align-items:center}}
  .tabs{{display:flex;gap:0;border:1px solid var(--border);border-radius:6px;overflow:hidden}}
  .tab{{padding:6px 12px;font-size:11px;color:var(--dim);border-right:1px solid var(--border);
         transition:background .1s,color .1s}}
  .tab:last-child{{border-right:none}}
  .tab:hover{{background:var(--surface);color:var(--text)}}
  .tab.active{{background:var(--surface);color:var(--text);font-weight:600}}
  .tab-count{{color:var(--muted);font-size:10px;margin-left:4px}}

  .search-wrap{{flex:1;min-width:140px;position:relative}}
  .search-wrap input{{width:100%;background:var(--bg);border:1px solid var(--border2);
                      border-radius:6px;color:var(--text);font-family:'IBM Plex Mono',monospace;
                      font-size:12px;padding:6px 10px;outline:none}}
  .search-wrap input:focus{{border-color:var(--accent)}}

  select{{background:var(--bg);border:1px solid var(--border2);border-radius:6px;
          color:var(--dim);font-family:'IBM Plex Mono',monospace;font-size:11px;
          padding:6px 8px;outline:none;cursor:pointer}}
  select:focus{{border-color:var(--accent)}}

  /* Result count */
  .result-count{{font-size:11px;color:var(--muted);margin-bottom:12px}}
  .result-count strong{{color:var(--dim)}}

  /* Gist cards */
  .gist-card{{display:block;padding:14px 16px;border:1px solid var(--border);
               border-radius:8px;margin-bottom:8px;transition:border-color .15s,background .15s;
               cursor:pointer}}
  .gist-card:hover{{border-color:var(--border2);background:var(--surface)}}
  .gc-top{{display:flex;align-items:center;gap:8px;margin-bottom:5px}}
  .gc-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}
  .gc-desc{{flex:1;font-size:12px;color:var(--text);white-space:nowrap;
             overflow:hidden;text-overflow:ellipsis}}
  .badge{{font-size:9px;padding:2px 6px;border-radius:10px;flex-shrink:0;
           text-transform:uppercase;letter-spacing:.5px;font-weight:600}}
  .badge.pub{{background:rgba(57,211,83,.1);color:var(--accent);border:1px solid rgba(57,211,83,.3)}}
  .badge.sec{{background:rgba(139,148,158,.1);color:var(--dim);border:1px solid var(--border)}}
  .gc-files{{font-size:10px;color:var(--muted);margin-bottom:6px;
              white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
  .gc-meta{{display:flex;gap:12px;font-size:10px;color:var(--muted);flex-wrap:wrap;align-items:center}}
  .gc-gh{{color:var(--accent);margin-left:auto;font-size:10px;
           padding:2px 6px;border:1px solid rgba(57,211,83,.3);border-radius:4px}}
  .gc-gh:hover{{background:rgba(57,211,83,.1)}}

  /* Pagination */
  .pagination{{display:flex;align-items:center;gap:4px;margin-top:20px;flex-wrap:wrap}}
  .pag-btn{{padding:5px 10px;border:1px solid var(--border);border-radius:4px;
             font-size:11px;color:var(--dim);transition:border-color .1s,color .1s}}
  .pag-btn:hover:not(.disabled):not(.active){{border-color:var(--border2);color:var(--text)}}
  .pag-btn.active{{border-color:var(--accent);color:var(--accent);font-weight:600}}
  .pag-btn.disabled{{opacity:.35;cursor:default}}
  .pag-ellipsis{{color:var(--muted);padding:0 4px;font-size:12px}}

  .empty{{padding:32px;text-align:center;color:var(--muted);border:1px solid var(--border);
           border-radius:8px}}
  .footer{{text-align:center;color:var(--muted);font-size:10px;
            padding-top:12px;border-top:1px solid var(--border);margin-top:16px}}
</style></head><body>
<div class="wrap">

  <!-- Header -->
  <div class="page-header">
    <img class="avatar" src="{avatar_src}" alt="{p['login']}">
    <div>
      <div class="page-title">@{_esc(p['login'])} / gists</div>
      <div class="page-sub">{len(all_gists)} total · {pub_count} public · {sec_count} secret</div>
    </div>
    <div class="header-links">
      <a class="hlink" href="/embed/{username}">← Dashboard</a>
      <a class="hlink" href="{p['html_url']}" target="_blank">GitHub ↗</a>
    </div>
  </div>

  <!-- Toolbar -->
  <div class="toolbar">
    <div class="tabs">{tabs_html}</div>
    <div class="search-wrap">
      <input type="text" id="q-input" placeholder="Search gists…"
             value="{_esc(q)}" onkeydown="if(event.key==='Enter')doSearch()">
    </div>
    <select id="lang-select" onchange="doSearch()">
      {lang_opts_html}
    </select>
  </div>

  <!-- Result count -->
  <div class="result-count">
    Showing <strong>{start+1}–{min(start+per_page, total)}</strong>
    of <strong>{total}</strong> gist{"s" if total != 1 else ""}
    {f'matching <strong>"{_esc(q)}"</strong>' if q else ""}
    {f'in <strong>{_esc(lang_filter)}</strong>' if lang_filter else ""}
  </div>

  <!-- Cards -->
  {cards_html}

  <!-- Pagination -->
  <div class="pagination">{pag_html}</div>

  <div class="footer">
    gist-board · @{_esc(p['login'])} ·
    {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
  </div>
</div>

<script>
  function doSearch() {{
    const q    = document.getElementById('q-input').value.trim()
    const lang = document.getElementById('lang-select').value
    const vis  = new URLSearchParams(location.search).get('visibility') || 'all'
    const params = new URLSearchParams()
    params.set('visibility', vis)
    if (lang) params.set('lang', lang)
    if (q)    params.set('q', q)
    location.href = '/gists/{username}?' + params.toString()
  }}
</script>
</body></html>"""