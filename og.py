"""
og.py — Open Graph image for /og/{username}

Strategy (in order, no extra deps required):
  1. playwright installed  → screenshot HTML card as PNG (richest)
  2. cairosvg installed    → convert SVG card to PNG
  3. fallback              → return the OG card as SVG (works in most link previews)

Usage in HTML head:
  <meta property="og:image" content="https://yourdomain.com/og/danisherror">
  <meta property="og:image:width"  content="1200">
  <meta property="og:image:height" content="630">
"""

from datetime import datetime, timezone, timedelta

LANG_COLORS = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#2b7489",
    "Shell": "#89e051", "Go": "#00ADD8", "Rust": "#dea584", "Ruby": "#701516",
    "C": "#555555", "C++": "#f34b7d", "Java": "#b07219", "HTML": "#e34c26",
    "CSS": "#563d7c", "Other": "#8b949e",
}
HEAT_COLORS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]


async def generate_og_image(data: dict) -> tuple[bytes, str]:
    """
    Returns (content_bytes, media_type).
    Tries PNG first, falls back to SVG — both work as og:image.
    """
    # Try playwright
    try:
        png = await _playwright_og(data)
        return png, "image/png"
    except Exception:
        pass

    # Try cairosvg
    try:
        png = _cairosvg_og(data)
        return png, "image/png"
    except Exception:
        pass

    # Fallback: return SVG (supported by Twitter, Slack, Discord, iMessage)
    svg = build_og_svg(data)
    return svg.encode(), "image/svg+xml"


# ── Playwright (richest output) ────────────────────────────────────────────────

async def _playwright_og(data: dict) -> bytes:
    from playwright.async_api import async_playwright
    html = _build_og_html(data)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page    = await browser.new_page(viewport={"width": 1200, "height": 630})
        await page.set_content(html, wait_until="domcontentloaded")
        await page.wait_for_timeout(300)   # let fonts/layout settle
        png = await page.screenshot(type="png", clip={"x":0,"y":0,"width":1200,"height":630})
        await browser.close()
    return png


# ── CairoSVG fallback ──────────────────────────────────────────────────────────

def _cairosvg_og(data: dict) -> bytes:
    import cairosvg
    svg = build_og_svg(data)
    return cairosvg.svg2png(bytestring=svg.encode(), output_width=1200, output_height=630)


# ── SVG OG card (no deps, works everywhere) ────────────────────────────────────

def build_og_svg(data: dict) -> str:
    p     = data["profile"]
    s     = data["stats"]
    langs = data.get("languages", [])

    W, H = 1200, 630

    # Avatar
    avatar_el = ""
    if p.get("avatar_b64"):
        avatar_el = (
            f'<clipPath id="av"><circle cx="88" cy="88" r="52"/></clipPath>'
            f'<image href="data:image/jpeg;base64,{p["avatar_b64"]}" '
            f'x="36" y="36" width="104" height="104" clip-path="url(#av)"/>'
        )
    else:
        avatar_el = '<circle cx="88" cy="88" r="52" fill="#21262d"/>'

    # Stats blocks
    stats = [
        (str(s.get("total", 0)),          "Gists"),
        (str(s.get("total_commits", 0)),  "Commits"),
        (str(s.get("year_commits", 0)),   "This Year"),
        (f"{s.get('longest_streak', 0)}d", "Streak"),
    ]
    stat_blocks = ""
    for i, (val, label) in enumerate(stats):
        x = 80 + i * 240
        stat_blocks += (
            f'<text x="{x}" y="390" fill="#39d353" font-size="52" font-weight="700" '
            f'font-family="monospace">{_esc(val)}</text>'
            f'<text x="{x}" y="418" fill="#8b949e" font-size="16" font-family="monospace">'
            f'{label}</text>'
        )

    # Language dots
    lang_els = ""
    lx = 80
    for lang, _ in langs[:5]:
        c = LANG_COLORS.get(lang, "#8b949e")
        lang_els += (
            f'<circle cx="{lx + 7}" cy="560" r="7" fill="{c}"/>'
            f'<text x="{lx + 20}" y="565" fill="#8b949e" font-size="18" font-family="monospace">'
            f'{_esc(lang)}</text>'
        )
        lx += len(lang) * 11 + 40

    # Mini heatmap — 26 weeks, bottom right
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=181)
    heatmap = data.get("heatmap", {})
    CELL, GAP = 14, 3
    hmap_x0 = W - 26 * (CELL + GAP) - 60
    hmap_y0 = 490
    heat_els = ""
    for col in range(26):
        for row in range(7):
            day = start + timedelta(days=col * 7 + row)
            if day > today:
                continue
            n   = min(heatmap.get(str(day), 0), 4)
            x   = hmap_x0 + col * (CELL + GAP)
            y   = hmap_y0 + row * (CELL + GAP)
            heat_els += f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" fill="{HEAT_COLORS[n]}"/>'

    name  = _esc(p.get("name", p.get("login", "")))
    login = _esc(p.get("login", ""))
    loc   = _esc(p.get("location", ""))
    loc_el = f'<text x="160" y="108" fill="#8b949e" font-size="18" font-family="monospace">📍 {loc}</text>' if loc else ""

    return f"""<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}"
  xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">

  <!-- Background -->
  <rect width="{W}" height="{H}" fill="#0d1117"/>
  <rect x="40" y="40" width="{W-80}" height="{H-80}" rx="16" fill="#161b22"
        stroke="#21262d" stroke-width="1"/>

  <!-- Top accent line -->
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%"   stop-color="#39d353" stop-opacity="0"/>
      <stop offset="50%"  stop-color="#39d353" stop-opacity="1"/>
      <stop offset="100%" stop-color="#39d353" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <rect x="200" y="40" width="800" height="2" fill="url(#g)"/>

  <!-- Avatar -->
  {avatar_el}

  <!-- Name + login -->
  <text x="160" y="82" fill="#e6edf3" font-size="36" font-weight="700"
        font-family="monospace">{name}</text>
  <text x="160" y="104" fill="#8b949e" font-size="20" font-family="monospace">@{login}</text>
  {loc_el}

  <!-- Divider -->
  <line x1="80" y1="140" x2="{W-80}" y2="140" stroke="#21262d" stroke-width="1"/>

  <!-- Stats -->
  {stat_blocks}

  <!-- Divider -->
  <line x1="80" y1="440" x2="{W-80}" y2="440" stroke="#21262d" stroke-width="1"/>

  <!-- Languages -->
  {lang_els}

  <!-- Heatmap -->
  {heat_els}

  <!-- Brand -->
  <text x="{W-100}" y="{H-20}" fill="#30363d" font-size="14" font-family="monospace"
        text-anchor="end">gist-board</text>
</svg>"""


# ── HTML template for playwright screenshot ────────────────────────────────────

def _build_og_html(data: dict) -> str:
    p     = data["profile"]
    s     = data["stats"]
    langs = data.get("languages", [])

    avatar_src = (
        f"data:image/jpeg;base64,{p['avatar_b64']}"
        if p.get("avatar_b64") else p.get("avatar_url", "")
    )

    lang_dots = ""
    for lang, _ in langs[:5]:
        c = LANG_COLORS.get(lang, "#8b949e")
        lang_dots += (
            f'<span style="display:inline-flex;align-items:center;gap:6px;'
            f'margin-right:16px;font-size:14px;color:#8b949e">'
            f'<span style="width:12px;height:12px;border-radius:50%;background:{c}"></span>'
            f'{_esc(lang)}</span>'
        )

    today  = datetime.now(timezone.utc).date()
    start  = today - timedelta(days=181)
    heatmap = data.get("heatmap", {})
    cells  = ""
    for col in range(26):
        col_html = ""
        for row in range(7):
            day = start + timedelta(days=col * 7 + row)
            if day > today:
                col_html += '<div style="width:12px;height:12px;border-radius:2px;background:transparent"></div>'
                continue
            n = min(heatmap.get(str(day), 0), 4)
            col_html += f'<div style="width:12px;height:12px;border-radius:2px;background:{HEAT_COLORS[n]}"></div>'
        cells += f'<div style="display:flex;flex-direction:column;gap:3px">{col_html}</div>'

    loc_html = f'<span style="color:#8b949e;font-size:14px">📍 {_esc(p.get("location",""))}</span>' if p.get("location") else ""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{width:1200px;height:630px;background:#0d1117;display:flex;
        align-items:center;justify-content:center;font-family:monospace;overflow:hidden}}
  .card{{width:1120px;height:550px;background:#161b22;border-radius:16px;
         border:1px solid #21262d;padding:52px 60px;display:flex;
         flex-direction:column;justify-content:space-between;position:relative}}
  .card::after{{content:'';position:absolute;top:0;left:15%;right:15%;height:2px;
                background:linear-gradient(90deg,transparent,#39d353,transparent)}}
  .top{{display:flex;align-items:center;gap:24px}}
  .avatar{{width:88px;height:88px;border-radius:50%;border:2px solid #30363d;flex-shrink:0}}
  .name{{font-size:34px;font-weight:700;color:#e6edf3;line-height:1.1}}
  .login{{font-size:16px;color:#8b949e;margin-top:4px;display:flex;gap:16px;align-items:center}}
  .stats{{display:flex;gap:48px}}
  .sv{{font-size:44px;font-weight:700;color:#39d353;line-height:1}}
  .sl{{font-size:12px;color:#8b949e;margin-top:4px;text-transform:uppercase;letter-spacing:.5px}}
  .bottom{{display:flex;justify-content:space-between;align-items:flex-end}}
  .heat{{display:flex;gap:3px}}
  .brand{{font-size:12px;color:#484f58}}
</style></head>
<body><div class="card">
  <div class="top">
    <img class="avatar" src="{avatar_src}">
    <div>
      <div class="name">{_esc(p.get('name', p.get('login','')))}</div>
      <div class="login">
        <span>@{_esc(p.get('login',''))}</span>
        {loc_html}
      </div>
    </div>
  </div>
  <div class="stats">
    <div><div class="sv">{s.get('total',0)}</div><div class="sl">Gists</div></div>
    <div><div class="sv">{s.get('total_commits',0)}</div><div class="sl">Commits</div></div>
    <div><div class="sv">{s.get('year_commits',0)}</div><div class="sl">This Year</div></div>
    <div><div class="sv">{s.get('longest_streak',0)}d</div><div class="sl">Longest Streak</div></div>
  </div>
  <div class="bottom">
    <div style="display:flex;flex-wrap:wrap;gap:4px">{lang_dots}</div>
    <div style="text-align:right">
      <div class="heat">{cells}</div>
      <div class="brand" style="margin-top:8px">gist-board</div>
    </div>
  </div>
</div></body></html>"""


def _esc(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")