"""
og.py — Generate Open Graph PNG images for /og/{username}
Uses playwright to screenshot a minimal HTML card at 1200x630.
Falls back to SVG-based PNG via cairosvg if playwright not installed.
"""

import asyncio
import base64
from svg_builder import build_svg


async def generate_og_image(data: dict) -> bytes:
    """
    Returns PNG bytes for the OG image.
    Tries playwright first (rich), falls back to SVG->PNG (basic).
    """
    try:
        return await _playwright_og(data)
    except Exception:
        return await _svg_og(data)


async def _playwright_og(data: dict) -> bytes:
    from playwright.async_api import async_playwright

    html = _build_og_html(data)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox"])
        page    = await browser.new_page(viewport={"width": 1200, "height": 630})
        await page.set_content(html, wait_until="networkidle")
        png = await page.screenshot(type="png", clip={"x":0,"y":0,"width":1200,"height":630})
        await browser.close()
    return png


async def _svg_og(data: dict) -> bytes:
    """Fallback: convert SVG card to PNG via cairosvg."""
    try:
        import cairosvg
        svg_str = build_svg(data)
        return cairosvg.svg2png(bytestring=svg_str.encode(), output_width=1200, output_height=630)
    except ImportError:
        # Last resort: return a minimal 1x1 transparent PNG
        import struct, zlib
        def png_chunk(name, data):
            c = zlib.crc32(name + data) & 0xffffffff
            return struct.pack('>I', len(data)) + name + data + struct.pack('>I', c)
        ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
        idat = zlib.compress(b'\x00\xff\xff\xff')
        return b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', ihdr) + png_chunk(b'IDAT', idat) + png_chunk(b'IEND', b'')


def _build_og_html(data: dict) -> str:
    p  = data["profile"]
    s  = data["stats"]
    langs = data.get("languages", [])

    avatar_src = (
        f"data:image/jpeg;base64,{p['avatar_b64']}"
        if p.get("avatar_b64") else p.get("avatar_url", "")
    )

    # Language dots
    lang_colors = {
        "Python":"#3572A5","JavaScript":"#f1e05a","TypeScript":"#2b7489",
        "Shell":"#89e051","Go":"#00ADD8","Rust":"#dea584","Ruby":"#701516",
        "Other":"#8b949e",
    }
    lang_dots = ""
    for lang, count in langs[:4]:
        c = lang_colors.get(lang, "#8b949e")
        lang_dots += f'<span style="display:inline-flex;align-items:center;gap:5px;margin-right:14px;font-size:13px;color:#8b949e"><span style="width:10px;height:10px;border-radius:50%;background:{c};display:inline-block"></span>{lang}</span>'

    # Heatmap mini — 26 weeks × 7 days
    from datetime import datetime, timezone, timedelta
    heatmap = data.get("heatmap", {})
    heat_colors = ["#161b22","#0e4429","#006d32","#26a641","#39d353"]
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=181)
    cells = ""
    for col in range(26):
        col_cells = ""
        for row in range(7):
            day = start + timedelta(days=col*7+row)
            if day > today:
                col_cells += f'<div style="width:10px;height:10px;border-radius:2px;background:transparent"></div>'
                continue
            n = min(heatmap.get(str(day), 0), 4)
            col_cells += f'<div style="width:10px;height:10px;border-radius:2px;background:{heat_colors[n]}"></div>'
        cells += f'<div style="display:flex;flex-direction:column;gap:2px">{col_cells}</div>'

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Unbounded:wght@700;900&display=swap" rel="stylesheet">
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{width:1200px;height:630px;background:#0d1117;display:flex;align-items:center;
        justify-content:center;font-family:"IBM Plex Mono",monospace;overflow:hidden}}
  .card{{width:1100px;height:540px;background:#161b22;border-radius:16px;
         border:1px solid #21262d;padding:56px 64px;display:flex;flex-direction:column;
         justify-content:space-between;position:relative;overflow:hidden}}
  .card::before{{content:'';position:absolute;top:0;left:60px;right:60px;height:2px;
                 background:linear-gradient(90deg,transparent,#39d353,transparent)}}
  .top{{display:flex;align-items:center;gap:28px}}
  .avatar{{width:80px;height:80px;border-radius:50%;border:2px solid #30363d}}
  .name{{font-family:"Unbounded",sans-serif;font-size:32px;font-weight:900;color:#e6edf3;line-height:1.1}}
  .login{{font-size:15px;color:#8b949e;margin-top:4px}}
  .stats{{display:flex;gap:40px}}
  .stat-val{{font-family:"Unbounded",sans-serif;font-size:36px;font-weight:700;color:#39d353;line-height:1}}
  .stat-label{{font-size:11px;color:#8b949e;margin-top:4px;text-transform:uppercase;letter-spacing:.5px}}
  .bottom{{display:flex;justify-content:space-between;align-items:flex-end}}
  .langs{{display:flex;flex-wrap:wrap;gap:4px}}
  .heat{{display:flex;gap:2px}}
  .brand{{font-size:12px;color:#484f58}}
</style></head>
<body><div class="card">
  <div class="top">
    <img class="avatar" src="{avatar_src}">
    <div>
      <div class="name">{p.get('name','')}</div>
      <div class="login">@{p.get('login','')}{' · ' + p.get('location','') if p.get('location') else ''}</div>
    </div>
  </div>
  <div class="stats">
    <div><div class="stat-val">{s.get('total',0)}</div><div class="stat-label">Gists</div></div>
    <div><div class="stat-val">{s.get('total_commits',0)}</div><div class="stat-label">Commits</div></div>
    <div><div class="stat-val">{s.get('year_commits',0)}</div><div class="stat-label">This Year</div></div>
    <div><div class="stat-val">{s.get('longest_streak',0)}d</div><div class="stat-label">Longest Streak</div></div>
  </div>
  <div class="bottom">
    <div>
      <div class="langs">{lang_dots}</div>
    </div>
    <div style="text-align:right">
      <div class="heat">{cells}</div>
      <div class="brand" style="margin-top:8px">gist-board</div>
    </div>
  </div>
</div></body></html>"""