import traceback
import os
import asyncio
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from cache import cache
from github import (
    fetch_user_data, fetch_gist_detail, fetch_compare_data,
    UserNotFoundError, RateLimitError, GistBoardError, NetworkError,
)
from svg_builder  import build_svg
from html_builder import build_html
from analytics    import build_analytics
from og           import generate_og_image

# Background refresh registry: username -> asyncio.Task
_refresh_tasks: dict = {}


app = FastAPI(title="Gist Board", docs_url=None, redoc_url=None)


def _token(request: Request) -> Optional[str]:
    return request.query_params.get("token")


def _trigger_background_refresh(username: str, token: Optional[str]):
    """Stale-while-revalidate: kick off a background fetch after serving cache."""
    key = username.lower()
    task = _refresh_tasks.get(key)
    if task and not task.done():
        return  # already refreshing
    async def _refresh():
        try:
            cache.delete(f"user:{key}")
            await fetch_user_data(username, token)
        except Exception:
            pass
        finally:
            _refresh_tasks.pop(key, None)
    _refresh_tasks[key] = asyncio.create_task(_refresh())


# ── SVG card ──────────────────────────────────────────────────────────────────
@app.get("/card/{username}")
async def card(request: Request, username: str):
    """
    SVG card for README embeds.
    ?theme=dark|light  ?compact=1  ?token=...
    """
    try:
        data   = await fetch_user_data(username, _token(request))
        theme  = request.query_params.get("theme", "dark")
        compact = request.query_params.get("compact", "0") == "1"
        svg    = build_svg(data, theme=theme, compact=compact)
        return Response(content=svg, media_type="image/svg+xml",
            headers={"Cache-Control": "s-maxage=3600, stale-while-revalidate=1800",
                     "Access-Control-Allow-Origin": "*"})
    except UserNotFoundError as e: return _svg_error("User not found", str(e))
    except RateLimitError    as e: return _svg_error("Rate limit", str(e))
    except NetworkError      as e: return _svg_error("Network error", str(e))
    except Exception         as e:
        traceback.print_exc()
        return _svg_error("Error", str(e))


# ── HTML dashboard ────────────────────────────────────────────────────────────
@app.get("/embed/{username}", response_class=HTMLResponse)
async def embed(request: Request, username: str):
    try:
        data = await fetch_user_data(username, _token(request))
        _trigger_background_refresh(username, _token(request))
        html = build_html(data, username)
        return HTMLResponse(content=html,
            headers={"Cache-Control": "s-maxage=3600, stale-while-revalidate=1800",
                     "Access-Control-Allow-Origin": "*"})
    except UserNotFoundError as e: return HTMLResponse(_html_error("User not found",    str(e), "404"), status_code=404)
    except RateLimitError    as e: return HTMLResponse(_html_error("Rate limit exceeded", str(e), "429"), status_code=429)
    except NetworkError      as e: return HTMLResponse(_html_error("Network error",      str(e), "503"), status_code=503)
    except GistBoardError    as e: return HTMLResponse(_html_error("Error",              str(e), "400"), status_code=400)
    except Exception         as e:
        print(traceback.format_exc())
        return HTMLResponse(_html_error("Unexpected error", str(e), "500"), status_code=500)


# ── Gist detail ───────────────────────────────────────────────────────────────
@app.get("/embed/{username}/gist/{gist_id}", response_class=HTMLResponse)
async def gist_detail(request: Request, username: str, gist_id: str):
    try:
        detail = await fetch_gist_detail(gist_id, _token(request))
        from templates.detail import build_detail_html
        html = build_detail_html(detail, username)
        return HTMLResponse(content=html,
            headers={"Cache-Control": "s-maxage=1800", "Access-Control-Allow-Origin": "*"})
    except UserNotFoundError as e: return HTMLResponse(_html_error("Gist not found",   str(e), "404"), status_code=404)
    except RateLimitError    as e: return HTMLResponse(_html_error("Rate limit",        str(e), "429"), status_code=429)
    except NetworkError      as e: return HTMLResponse(_html_error("Network error",     str(e), "503"), status_code=503)
    except Exception         as e:
        print(traceback.format_exc())
        return HTMLResponse(_html_error("Unexpected error", str(e), "500"), status_code=500)


# ── Compare ───────────────────────────────────────────────────────────────────
@app.get("/compare/{user1}/{user2}", response_class=HTMLResponse)
async def compare(request: Request, user1: str, user2: str):
    try:
        data = await fetch_compare_data(user1, user2, _token(request))
        from templates.compare import build_compare_html
        html = build_compare_html(data, user1, user2)
        return HTMLResponse(content=html,
            headers={"Cache-Control": "s-maxage=1800", "Access-Control-Allow-Origin": "*"})
    except RateLimitError as e: return HTMLResponse(_html_error("Rate limit", str(e), "429"), status_code=429)
    except NetworkError   as e: return HTMLResponse(_html_error("Network error", str(e), "503"), status_code=503)
    except Exception      as e:
        print(traceback.format_exc())
        return HTMLResponse(_html_error("Unexpected error", str(e), "500"), status_code=500)


# ── Open Graph image ──────────────────────────────────────────────────────────
@app.get("/og/{username}")
async def og(request: Request, username: str):
    try:
        data             = await fetch_user_data(username, _token(request))
        content, mime    = await generate_og_image(data)
        return Response(content=content, media_type=mime,
            headers={"Cache-Control": "s-maxage=3600", "Access-Control-Allow-Origin": "*"})
    except UserNotFoundError as e:
        return HTMLResponse(_html_error("User not found", str(e), "404"), status_code=404)
    except RateLimitError as e:
        return HTMLResponse(_html_error("Rate limit", str(e), "429"), status_code=429)
    except Exception as e:
        traceback.print_exc()
        return Response(content=b"", media_type="image/png", status_code=500)


# ── JSON API ──────────────────────────────────────────────────────────────────
@app.get("/api/{username}")
async def api_user(request: Request, username: str):
    try:
        data = await fetch_user_data(username, _token(request))
        out  = {k: v for k, v in data.items() if k != "profile" or True}
        out["profile"].pop("avatar_b64", None)
        out.pop("all_gists_full", None)
        return JSONResponse(content=out, headers={"Access-Control-Allow-Origin": "*"})
    except UserNotFoundError as e: return JSONResponse({"error": "user_not_found",  "message": str(e)}, status_code=404)
    except RateLimitError    as e: return JSONResponse({"error": "rate_limit",       "message": str(e)}, status_code=429)
    except NetworkError      as e: return JSONResponse({"error": "network_error",    "message": str(e)}, status_code=503)
    except Exception         as e:
        traceback.print_exc()
        return JSONResponse({"error": "internal_error", "message": str(e)}, status_code=500)


@app.get("/api/{username}/gist/{gist_id}")
async def api_gist(request: Request, username: str, gist_id: str):
    try:
        detail = await fetch_gist_detail(gist_id, _token(request))
        return JSONResponse(content=detail, headers={"Access-Control-Allow-Origin": "*"})
    except UserNotFoundError as e: return JSONResponse({"error": "not_found",  "message": str(e)}, status_code=404)
    except RateLimitError    as e: return JSONResponse({"error": "rate_limit", "message": str(e)}, status_code=429)
    except Exception         as e:
        traceback.print_exc()
        return JSONResponse({"error": "internal_error", "message": str(e)}, status_code=500)


@app.get("/api/{username}/analytics")
async def api_analytics(request: Request, username: str):
    try:
        data      = await fetch_user_data(username, _token(request))
        analytics = build_analytics(data)
        return JSONResponse(content=analytics, headers={"Access-Control-Allow-Origin": "*"})
    except UserNotFoundError as e: return JSONResponse({"error": "user_not_found", "message": str(e)}, status_code=404)
    except RateLimitError    as e: return JSONResponse({"error": "rate_limit",     "message": str(e)}, status_code=429)
    except Exception         as e:
        traceback.print_exc()
        return JSONResponse({"error": "internal_error", "message": str(e)}, status_code=500)


# ── Cache admin ──────────────────────────────────────────────────────────────
@app.get("/api/cache/stats")
async def cache_stats():
    """Cache health — keys, hit rate, TTLs."""
    return JSONResponse(cache.stats())


@app.delete("/api/cache/flush")
async def cache_flush():
    """Flush entire cache."""
    n = cache.flush()
    return JSONResponse({"flushed": n})


@app.delete("/api/cache/user/{username}")
async def cache_flush_user(username: str):
    """Flush all cached data for a specific user."""
    n  = cache.delete(f"user:{username.lower()}")
    n += cache.delete(f"compare:{username.lower()}:*")  # best effort
    n += cache.flush_pattern(f"compare:{username.lower()}:")
    return JSONResponse({"flushed_keys": n, "username": username})


# ── Homepage ──────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def home():
    return HTMLResponse(_HOME_HTML)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _html_error(title: str, msg: str = "", code: str = "") -> str:
    colors = {"404":"#8b949e","429":"#f0883e","503":"#f0883e","500":"#f85149","400":"#f85149"}
    color  = colors.get(code, "#f85149")
    return (
        '<!DOCTYPE html><html><head><meta charset="UTF-8">'
        '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&display=swap" rel="stylesheet">'
        '<style>body{background:#0d1117;color:#e6edf3;font-family:"IBM Plex Mono",monospace;'
        'min-height:100vh;display:flex;align-items:center;justify-content:center;padding:40px;margin:0}'
        '.box{max-width:480px;width:100%}'
        f'.code{{font-size:64px;font-weight:600;color:{color};line-height:1;margin-bottom:12px}}'
        '.title{font-size:18px;font-weight:600;margin-bottom:8px}'
        '.msg{color:#8b949e;font-size:12px;line-height:1.6;margin-bottom:24px}'
        '.back{display:inline-block;padding:8px 16px;border:1px solid #30363d;border-radius:6px;'
        'color:#8b949e;font-size:12px;text-decoration:none}'
        '.back:hover{border-color:#39d353;color:#39d353}'
        '</style></head><body><div class="box">'
        f'<div class="code">{code}</div><div class="title">{title}</div>'
        f'<div class="msg">{msg}</div>'
        '<a class="back" href="/">← Back to search</a>'
        '</div></body></html>'
    )


def _svg_error(title: str, msg: str = "") -> Response:
    short = (msg or title)[:70]
    svg = (
        '<svg width="495" height="90" xmlns="http://www.w3.org/2000/svg">'
        '<rect width="495" height="90" rx="8" fill="#0d1117"/>'
        '<rect width="495" height="2" rx="1" fill="#f85149"/>'
        f'<text x="20" y="32" fill="#f85149" font-size="13" font-weight="600" font-family="monospace">{title}</text>'
        f'<text x="20" y="52" fill="#8b949e" font-size="11" font-family="monospace">{short}</text>'
        '<text x="20" y="72" fill="#484f58" font-size="10" font-family="monospace">gist-board</text>'
        '</svg>'
    )
    return Response(content=svg, media_type="image/svg+xml")


_HOME_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gist Board</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Unbounded:wght@700;900&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:#0d1117;color:#e6edf3;font-family:'IBM Plex Mono',monospace;
       min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:40px}
  h1{font-family:'Unbounded',sans-serif;font-size:clamp(28px,6vw,56px);font-weight:900;
     line-height:1;margin-bottom:8px;text-align:center}
  h1 span{color:#39d353}
  .sub{color:#8b949e;font-size:12px;margin-bottom:48px;text-align:center}
  .search{display:flex;gap:8px;width:100%;max-width:480px;margin-bottom:16px}
  input{flex:1;background:#161b22;border:1px solid #30363d;border-radius:6px;
        color:#e6edf3;font-family:'IBM Plex Mono',monospace;font-size:13px;
        padding:12px 14px;outline:none;transition:border-color .2s}
  input:focus{border-color:#39d353;box-shadow:0 0 0 3px rgba(57,211,83,.12)}
  input::placeholder{color:#484f58}
  button{background:#238636;border:1px solid #2ea043;border-radius:6px;
         color:#fff;font-family:'IBM Plex Mono',monospace;font-size:13px;font-weight:600;
         padding:12px 18px;cursor:pointer;white-space:nowrap}
  button:hover{background:#2ea043}
  .compare-row{display:flex;gap:8px;width:100%;max-width:480px;align-items:center}
  .compare-row input{flex:1}
  .compare-row span{color:#484f58;font-size:12px;flex-shrink:0}
  .btn-secondary{background:transparent;border:1px solid #30363d;color:#8b949e;
                 padding:10px 14px;border-radius:6px;font-family:'IBM Plex Mono',monospace;
                 font-size:12px;cursor:pointer;white-space:nowrap}
  .btn-secondary:hover{border-color:#39d353;color:#39d353}
  .eps{margin-top:48px;width:100%;max-width:540px}
  .ep-title{color:#8b949e;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin-bottom:12px}
  .ep{background:#161b22;border:1px solid #21262d;border-radius:6px;padding:12px 14px;margin-bottom:8px;font-size:11px}
  .ep .m{color:#39d353;margin-right:8px}.ep .p{color:#e6edf3}
  .ep .d{color:#8b949e;margin-top:4px}
  code{color:#79c0ff;background:#0d1117;padding:2px 5px;border-radius:3px;font-size:10px}
</style></head><body>
  <h1>Gist<span>Board</span></h1>
  <p class="sub">GitHub Gist dashboard — activity, analytics & more</p>

  <div class="search">
    <input id="u" type="text" placeholder="GitHub username" autocomplete="off" autofocus>
    <button onclick="go()">View →</button>
  </div>

  <div class="compare-row">
    <input id="u1" type="text" placeholder="user one">
    <span>vs</span>
    <input id="u2" type="text" placeholder="user two">
    <button class="btn-secondary" onclick="compare()">Compare</button>
  </div>

  <div class="eps">
    <div class="ep-title">Endpoints</div>
    <div class="ep"><span class="m">GET</span><span class="p">/embed/{username}</span>
      <div class="d">Full dashboard</div></div>
    <div class="ep"><span class="m">GET</span><span class="p">/embed/{username}/gist/{id}</span>
      <div class="d">Gist detail + commit timeline</div></div>
    <div class="ep"><span class="m">GET</span><span class="p">/compare/{user1}/{user2}</span>
      <div class="d">Side-by-side comparison</div></div>
    <div class="ep"><span class="m">GET</span><span class="p">/card/{username}?theme=dark&compact=1</span>
      <div class="d">SVG for README: <code>![](https://yourdomain.com/card/username)</code></div></div>
    <div class="ep"><span class="m">GET</span><span class="p">/og/{username}</span>
      <div class="d">Open Graph PNG for link previews</div></div>
    <div class="ep"><span class="m">GET</span><span class="p">/api/{username}/analytics</span>
      <div class="d">Raw JSON analytics data</div></div>
  </div>

  <script>
    document.getElementById('u').addEventListener('keydown', e => e.key==='Enter' && go())
    function go(){ const u=document.getElementById('u').value.trim(); if(u) location.href='/embed/'+u }
    function compare(){
      const u1=document.getElementById('u1').value.trim()
      const u2=document.getElementById('u2').value.trim()
      if(u1&&u2) location.href='/compare/'+u1+'/'+u2
    }
  </script>
</body></html>"""


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)