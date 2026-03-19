from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn
from typing import Optional
from api.github import fetch_user_data
from api.svg_builder import build_svg
from api.html_builder import build_html

app = FastAPI(title="Gist Board", docs_url=None, redoc_url=None)


def _token(request: Request) -> Optional[str]:
    return request.query_params.get("token")


# ── SVG card — for README / .md embeds ────────────────────────────────────────
@app.get("/card/{username}")
async def card(username: str, request: Request):
    """
    Returns an SVG card.
    Usage in markdown:
      ![Gist Board](https://yourdomain.com/card/torvalds)
    """
    try:
        data = await fetch_user_data(username, _token(request))
        svg = build_svg(data)
        return Response(
            content=svg,
            media_type="image/svg+xml",
            headers={
                "Cache-Control": "s-maxage=3600, stale-while-revalidate=1800",
                "Access-Control-Allow-Origin": "*",
            },
        )
    except ValueError as e:
        return _svg_error(str(e))
    except Exception as e:
        return _svg_error(f"Error: {e}")


# ── HTML embed — for iframes / direct links ───────────────────────────────────
@app.get("/embed/{username}", response_class=HTMLResponse)
async def embed(username: str, request: Request):
    """
    Returns a full HTML dashboard.
    Usage as iframe:
      <iframe src="https://yourdomain.com/embed/torvalds" width="520" height="700"/>
    Direct link:
      https://yourdomain.com/embed/torvalds
    """
    try:
        data = await fetch_user_data(username, _token(request))
        html = build_html(data, username)
        return HTMLResponse(
            content=html,
            headers={
                "Cache-Control": "s-maxage=3600, stale-while-revalidate=1800",
                "Access-Control-Allow-Origin": "*",
            },
        )
    except ValueError as e:
        return HTMLResponse(_html_error(str(e)), status_code=404)
    except Exception as e:
        return HTMLResponse(_html_error(str(e)), status_code=500)


# ── Raw JSON — for anyone who wants to build on top ───────────────────────────
@app.get("/api/{username}")
async def api(username: str, request: Request):
    try:
        data = await fetch_user_data(username, _token(request))
        # strip avatar b64 from api response (too large)
        data["profile"].pop("avatar_b64", None)
        return JSONResponse(
            content=data,
            headers={"Access-Control-Allow-Origin": "*"},
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Homepage ──────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def home():
    return HTMLResponse(HOME_HTML)


HOME_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gist Board</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Unbounded:wght@700;900&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:#0d1117;color:#e6edf3;font-family:'IBM Plex Mono',monospace;
       min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:40px}
  h1{font-family:'Unbounded',sans-serif;font-size:clamp(28px,6vw,56px);font-weight:900;
     color:#e6edf3;line-height:1;margin-bottom:8px;text-align:center}
  h1 span{color:#39d353}
  .sub{color:#8b949e;font-size:12px;margin-bottom:48px;text-align:center}
  .search{display:flex;gap:8px;width:100%;max-width:420px}
  input{flex:1;background:#161b22;border:1px solid #30363d;border-radius:6px;
        color:#e6edf3;font-family:'IBM Plex Mono',monospace;font-size:13px;
        padding:12px 14px;outline:none;transition:border-color .2s}
  input:focus{border-color:#39d353;box-shadow:0 0 0 3px rgba(57,211,83,.15)}
  input::placeholder{color:#484f58}
  button{background:#238636;border:1px solid #2ea043;border-radius:6px;
         color:#fff;font-family:'IBM Plex Mono',monospace;font-size:13px;font-weight:600;
         padding:12px 18px;cursor:pointer;transition:background .15s;white-space:nowrap}
  button:hover{background:#2ea043}
  .endpoints{margin-top:48px;width:100%;max-width:520px}
  .ep-title{color:#8b949e;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin-bottom:12px}
  .ep{background:#161b22;border:1px solid #21262d;border-radius:6px;
      padding:12px 14px;margin-bottom:8px;font-size:11px}
  .ep .method{color:#39d353;margin-right:8px}
  .ep .path{color:#e6edf3}
  .ep .desc{color:#8b949e;margin-top:4px}
  .ep code{color:#79c0ff;background:#0d1117;padding:2px 5px;border-radius:3px;font-size:10px}
</style>
</head>
<body>
  <h1>Gist<span>Board</span></h1>
  <p class="sub">GitHub Gist dashboard — heatmap, stats, languages & recent gists</p>

  <div class="search">
    <input id="u" type="text" placeholder="GitHub username" autocomplete="off" autofocus>
    <button onclick="go()">View →</button>
  </div>

  <div class="endpoints">
    <div class="ep-title">Endpoints</div>
    <div class="ep">
      <span class="method">GET</span><span class="path">/card/{username}</span>
      <div class="desc">SVG card for README: <code>![](https://yourdomain.com/card/torvalds)</code></div>
    </div>
    <div class="ep">
      <span class="method">GET</span><span class="path">/embed/{username}</span>
      <div class="desc">HTML dashboard — direct link or <code>&lt;iframe&gt;</code></div>
    </div>
    <div class="ep">
      <span class="method">GET</span><span class="path">/api/{username}</span>
      <div class="desc">Raw JSON data</div>
    </div>
  </div>

  <script>
    document.getElementById('u').addEventListener('keydown', e => e.key==='Enter' && go())
    function go(){
      const u = document.getElementById('u').value.trim()
      if(u) window.location.href = '/embed/' + u
    }
  </script>
</body>
</html>"""


def _svg_error(msg: str) -> Response:
    svg = f"""<svg width="495" height="80" xmlns="http://www.w3.org/2000/svg">
  <rect width="495" height="80" rx="8" fill="#0d1117"/>
  <text x="20" y="36" fill="#f85149" font-size="13" font-family="monospace">Error</text>
  <text x="20" y="56" fill="#8b949e" font-size="11" font-family="monospace">{msg[:60]}</text>
</svg>"""
    return Response(content=svg, media_type="image/svg+xml")


def _html_error(msg: str) -> str:
    return f"""<html><body style="background:#0d1117;color:#f85149;font-family:monospace;padding:40px">
    <h2>Error</h2><p style="color:#8b949e;margin-top:8px">{msg}</p></body></html>"""


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)