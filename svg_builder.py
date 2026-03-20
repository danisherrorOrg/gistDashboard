from datetime import datetime, timezone, timedelta

# Language → color map (GitHub-style)
LANG_COLORS = {
    "Python": "#3572A5",
    "JavaScript": "#f1e05a",
    "TypeScript": "#2b7489",
    "Shell": "#89e051",
    "Ruby": "#701516",
    "Go": "#00ADD8",
    "Rust": "#dea584",
    "C": "#555555",
    "C++": "#f34b7d",
    "Java": "#b07219",
    "Kotlin": "#F18E33",
    "Swift": "#ffac45",
    "PHP": "#4F5D95",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "Markdown": "#083fa1",
    "JSON": "#292929",
    "YAML": "#cb171e",
    "Other": "#8b949e",
}

HEAT_COLORS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]


def heat_color(count: int) -> str:
    if count == 0:
        return HEAT_COLORS[0]
    elif count == 1:
        return HEAT_COLORS[1]
    elif count == 2:
        return HEAT_COLORS[2]
    elif count == 3:
        return HEAT_COLORS[3]
    return HEAT_COLORS[4]


def lang_color(lang: str) -> str:
    return LANG_COLORS.get(lang, LANG_COLORS["Other"])


def build_svg(data: dict, theme: str = 'dark', compact: bool = False) -> str:
    # Theme
    if theme == "light":
        bg, surface, text_col, dim_col, border_col = "#ffffff", "#f6f8fa", "#24292f", "#656d76", "#d0d7de"
    else:
        bg, surface, text_col, dim_col, border_col = "#0d1117", "#161b22", "#e6edf3", "#8b949e", "#21262d"

    p = data["profile"]
    s = data["stats"]
    heatmap = data["heatmap"]
    langs = data["languages"]
    recent = data["recent"]

    W = 495
    # Heights of sections
    H_HEADER = 90
    H_STATS = 52
    H_HEAT = 100
    H_LANG = 60
    H_RECENT = 22 * len(recent) + 28
    H_TOTAL = H_HEADER + H_STATS + H_HEAT + H_LANG + H_RECENT + 24

    # ── Heatmap grid ──
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=364)
    # Align to Sunday
    dow = start.weekday()  # Mon=0
    start = start - timedelta(days=(dow + 1) % 7)

    CELL = 10
    GAP = 2
    COLS = 53
    heat_x0 = 20
    heat_y0 = H_HEADER + H_STATS + 24

    heat_rects = []
    for col in range(COLS):
        for row in range(7):
            day = start + timedelta(days=col * 7 + row)
            if day > today:
                continue
            ds = str(day)
            count = heatmap.get(ds, 0)
            x = heat_x0 + col * (CELL + GAP)
            y = heat_y0 + row * (CELL + GAP)
            color = heat_color(count)
            tip = f"{ds}: {count} gist{'s' if count != 1 else ''}"
            heat_rects.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" '
                f'fill="{color}"><title>{tip}</title></rect>'
            )

    # ── Language bars ──
    lang_y0 = H_HEADER + H_STATS + H_HEAT + 16
    total_lang = sum(c for _, c in langs) or 1
    lang_bar_w = W - 40
    lang_rects = []
    lx = 20
    for lang, count in langs:
        w = int(lang_bar_w * count / total_lang)
        if w < 2:
            w = 2
        lang_rects.append(
            f'<rect x="{lx}" y="{lang_y0}" width="{w}" height="8" rx="2" fill="{lang_color(lang)}"/>'
        )
        lx += w

    lang_labels = []
    label_x = 20
    label_y = lang_y0 + 20
    for lang, count in langs[:5]:
        pct = round(count / total_lang * 100)
        lang_labels.append(
            f'<circle cx="{label_x + 5}" cy="{label_y - 4}" r="4" fill="{lang_color(lang)}"/>'
            f'<text x="{label_x + 13}" y="{label_y}" fill="{dim_col}" font-size="10">'
            f'{lang} {pct}%</text>'
        )
        label_x += 80
        if label_x > W - 80:
            break

    # ── Recent gists ──
    recent_y0 = H_HEADER + H_STATS + H_HEAT + H_LANG + 20
    recent_rows = []
    for i, g in enumerate(recent):
        ry = recent_y0 + i * 22
        pub_icon = "⬡" if g["public"] else "⬢"
        pub_color = "#39d353" if g["public"] else "#8b949e"
        desc = g["description"][:48] + ("…" if len(g["description"]) > 48 else "")
        lc = lang_color(g["language"])
        recent_rows.append(
            f'<circle cx="28" cy="{ry + 1}" r="4" fill="{lc}"/>'
            f'<text x="38" y="{ry + 5}" fill="{text_col}" font-size="11">{_esc(desc)}</text>'
            f'<text x="{W - 20}" y="{ry + 5}" fill="{dim_col}" font-size="10" text-anchor="end">{g["updated_at"]}</text>'
        )

    # ── Avatar ──
    avatar_el = ""
    if p.get("avatar_b64"):
        avatar_el = (
            f'<clipPath id="av"><circle cx="40" cy="40" r="28"/></clipPath>'
            f'<image href="data:image/jpeg;base64,{p["avatar_b64"]}" '
            f'x="12" y="12" width="56" height="56" clip-path="url(#av)"/>'
        )
    else:
        avatar_el = f'<circle cx="40" cy="40" r="28" fill="#21262d"/>'

    # ── Assemble SVG ──
    svg = f"""<svg width="{W}" height="{H_TOTAL if not compact else H_HEADER + H_STATS + H_HEAT + 24}" viewBox="0 0 {W} {H_TOTAL}"
  xmlns="http://www.w3.org/2000/svg"
  xmlns:xlink="http://www.w3.org/1999/xlink"
  style="background:#0d1117;border-radius:12px;font-family:'Segoe UI',sans-serif;">

  <defs>
    <style>
      text {{ font-family: 'Segoe UI', -apple-system, sans-serif; }}
      .mono {{ font-family: 'Courier New', monospace; }}
    </style>
    <!-- shimmer animation -->
    <linearGradient id="shimmer" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0"/>
      <stop offset="50%" stop-color="#ffffff" stop-opacity="0.04"/>
      <stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>
      <animateTransform attributeName="gradientTransform" type="translate"
        from="-1 0" to="2 0" dur="3s" repeatCount="indefinite"/>
    </linearGradient>
  </defs>

  <!-- BG -->
  <rect width="{W}" height="{H_TOTAL if not compact else H_HEADER + H_STATS + H_HEAT + 24}" rx="12" fill="{bg}"/>
  <rect width="{W}" height="{H_TOTAL if not compact else H_HEADER + H_STATS + H_HEAT + 24}" rx="12" fill="url(#shimmer)"/>

  <!-- Top border accent -->
  <rect x="0" y="0" width="{W}" height="2" rx="1" fill="#39d353" opacity="0.8"/>

  <!-- ── HEADER ── -->
  {avatar_el}
  <text x="80" y="36" fill="{text_col}" font-size="16" font-weight="600">{_esc(p["name"])}</text>
  <text x="80" y="52" fill="{dim_col}" font-size="12">@{_esc(p["login"])}</text>
  <text x="80" y="70" fill="{dim_col}" font-size="11">{_esc(p["bio"][:60])}</text>
  <text x="{W - 20}" y="36" fill="{dim_col}" font-size="11" text-anchor="end">
    {s["followers"]} followers · {s["following"]} following
  </text>

  <!-- divider -->
  <line x1="20" y1="{H_HEADER}" x2="{W - 20}" y2="{H_HEADER}" stroke="{border_col}" stroke-width="1"/>

  <!-- ── STATS ROW ── -->
  {_stat_block(20,  H_HEADER + 16, str(s["total"]),          "Total Gists")}
  {_stat_block(130, H_HEADER + 16, str(s["public"]),         "Public")}
  {_stat_block(230, H_HEADER + 16, str(s["secret"]),         "Secret")}
  {_stat_block(330, H_HEADER + 16, str(s["total_comments"]), "Comments")}
  {_stat_block(420, H_HEADER + 16, str(s["year_count"]),     "This Year")}

  <!-- divider -->
  <line x1="20" y1="{H_HEADER + H_STATS}" x2="{W - 20}" y2="{H_HEADER + H_STATS}" stroke="{border_col}" stroke-width="1"/>

  <!-- ── HEATMAP ── -->
  <text x="20" y="{H_HEADER + H_STATS + 14}" fill="{dim_col}" font-size="10">
    {s["year_count"]} gist{'s' if s["year_count"] != 1 else ''} in the last year
  </text>
  {''.join(heat_rects)}

  <!-- divider -->
  <line x1="20" y1="{H_HEADER + H_STATS + H_HEAT}" x2="{W - 20}" y2="{H_HEADER + H_STATS + H_HEAT}" stroke="{border_col}" stroke-width="1"/>

  <!-- ── LANGUAGES ── -->
  <text x="20" y="{lang_y0 - 6}" fill="{dim_col}" font-size="10">LANGUAGES</text>
  {''.join(lang_rects)}
  {''.join(lang_labels)}

  <!-- divider -->
  <line x1="20" y1="{H_HEADER + H_STATS + H_HEAT + H_LANG}" x2="{W - 20}" y2="{H_HEADER + H_STATS + H_HEAT + H_LANG}" stroke="{border_col}" stroke-width="1"/>

  <!-- ── RECENT GISTS ── -->
  <text x="20" y="{recent_y0 - 8}" fill="{dim_col}" font-size="10">RECENT GISTS</text>
  {''.join(recent_rows)}

  <!-- footer -->
  <text x="{W // 2}" y="{H_TOTAL - 8}" fill="#30363d" font-size="9" text-anchor="middle">
    gist-board · updated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
  </text>
</svg>"""
    return svg


def _stat_block(x, y, value, label):
    return (
        f'<text x="{x}" y="{y + 14}" fill="{text_col}" font-size="18" font-weight="700">{value}</text>'
        f'<text x="{x}" y="{y + 28}" fill="{dim_col}" font-size="10">{label}</text>'
    )


def _esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )