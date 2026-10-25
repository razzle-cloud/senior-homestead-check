#!/usr/bin/env python3
"""Builds the static pages in ../public from findings.json and geo.json.
Re-run after refreshing those two files from Supabase."""
import json
import math
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "public"
F = json.load(open(HERE / "findings.json"))
G = json.load(open(HERE / "geo.json"))

NAV = [("index.html", "Check your address"), ("findings.html", "What we found"), ("about.html", "About the data")]


NAV_ES = [("es.html", "Revise su dirección"), ("hallazgos.html", "Hallazgos"), ("datos.html", "Sobre los datos")]
CTA = {"en": ("apply.html", "How to apply"), "es": ("solicitar.html", "Cómo solicitar")}
LOGO = ('<svg class="mark" viewBox="0 0 32 32" aria-hidden="true" focusable="false"><rect width="32" height="32" rx="7" fill="#1f4e79"/>'
        '<rect x="7" y="8" width="18" height="3" rx="1" fill="#fff"/><rect x="7" y="14.5" width="18" height="4" rx="1" fill="#e8836b"/>'
        '<rect x="7" y="22" width="11" height="3" rx="1" fill="#fff"/></svg>')
ICON = {
  "offices": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M2 21h20M4 21V9.5L8.5 6 13 9.5V21M13 21v-9h7v9M7 21v-4h3v4M16 15h1.5M16 18h1.5"/></svg>',
  "birthday": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4M8.5 15.5l2.5 2.5 4.5-4.5"/></svg>',
  "phone": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M5 3.5h3.5l2 5-2.5 1.6a11.5 11.5 0 0 0 5.9 5.9l1.6-2.5 5 2v3.5a2 2 0 0 1-2 2A17 17 0 0 1 3 5.5a2 2 0 0 1 2-2z"/></svg>',
}


def tips(cards):
    """Row of tip cards: cards = [(icon, heading, text)]."""
    return '<ul class="tips">' + "".join(
        f'<li class="tip"><span class="tip-icon">{ICON[i]}</span><h3>{h}</h3><p>{t}</p></li>' for i, h, t in cards) + "</ul>"
UI = {
  "en": dict(skip="Skip to content", brand="Senior Homestead Check",
             tag="Helping Decatur seniors keep their tax breaks", navlabel="Main",
             desc="Check whether your City of Decatur home has every property tax exemption it qualifies for.",
             foot1="A student civic-technology project for the Congressional App Challenge. Not affiliated with the City of Decatur or DeKalb County. General information only, not tax or legal advice; each office decides every application.",
             foot2='Records as of September 2026. <a href="about.html#mistakes">Report a mistake</a>. <a href="partners.html">Partner sign-in</a>', home="index.html"),
  "es": dict(skip="Ir al contenido", brand="Senior Homestead Check",
             tag="Exenciones para los mayores de Decatur", navlabel="Principal",
             desc="Revise si su vivienda en la Ciudad de Decatur tiene todas las exenciones de impuestos a la propiedad que le corresponden.",
             foot1="Un proyecto estudiantil de tecnología cívica para el Congressional App Challenge. No está afiliado con la Ciudad de Decatur ni con el Condado de DeKalb. Información general solamente, no es asesoría tributaria ni legal; cada oficina decide cada solicitud.",
             foot2='Registros a septiembre de 2026. <a href="datos.html#errores">Reportar un error</a>.', home="es.html"),
}


def page(fname, title, body, scripts="", desc="", lang="en", alt=None):
    u = UI[lang]
    cur = ' aria-current="page"'
    items = NAV if lang == "en" else NAV_ES
    en_attr = ' lang="en" hreflang="en"'
    nav = "".join(f'<li><a href="{h}"{cur if h == fname else ""}>{t}</a></li>' for h, t in items)
    cta_href, cta_text = CTA[lang]
    nav += f'<li class="cta-item"><a class="cta" href="{cta_href}"{cur if cta_href == fname else ""}>{cta_text}</a></li>'
    if lang == "en":
        switch = f'<a class="lang" href="{alt or "es.html"}" lang="es" hreflang="es">Español</a>'
    else:
        switch = f'<a class="lang" href="{alt or "index.html"}"{en_attr}>English</a>'
    html = f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{escape(desc or u['desc'])}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
<link rel="stylesheet" href="styles.css">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='6' fill='%231f4e79'/%3E%3Crect x='7' y='9' width='18' height='3' fill='%23fff'/%3E%3Crect x='7' y='15' width='18' height='4' fill='%23e8836b'/%3E%3Crect x='7' y='22' width='12' height='3' fill='%23fff'/%3E%3C/svg%3E">
</head>
<body>
<a class="skip" href="#main">{u['skip']}</a>
<header class="site-head"><div class="inner">
  <a class="brand" href="{u['home']}">{LOGO}<span>{u['brand']}<small>{u['tag']}</small></span></a>
  <nav aria-label="{u['navlabel']}"><ul>{nav}</ul></nav>
  {switch}
</div></header>
<main id="main">
{body}
</main>
<footer class="site-foot"><div class="inner">
  <p>{u['foot1']}</p>
  <p>{u['foot2']}</p>
</div></footer>
{scripts}
</body>
</html>"""
    (OUT / fname).write_text(html)


# ------------------------------------------------------------------ charts
def hbar(rows, fmt="{:.0f}%", maxv=100, hl=None, w=640, label_w=210, bar_h=26, gap=12, unit_title=""):
    """Horizontal bar chart; rows = [(label, value, tooltip)]."""
    h = len(rows) * (bar_h + gap) + 8
    plot = w - label_w - 70
    out = [f'<svg class="wide" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(unit_title)}">']
    for i, (lab, v, tip) in enumerate(rows):
        y = 4 + i * (bar_h + gap)
        bw = max(2, plot * v / maxv)
        cls = "bar hl" if hl and hl(lab) else "bar"
        out.append(f'<text x="{label_w - 10}" y="{y + bar_h * .68:.1f}" text-anchor="end" font-size="15">{escape(lab)}</text>')
        out.append(f'<rect class="track" x="{label_w}" y="{y}" width="{plot}" height="{bar_h}" rx="4"/>')
        out.append(f'<rect class="{cls}" x="{label_w}" y="{y}" width="{bw:.1f}" height="{bar_h}" rx="4"><title>{escape(tip)}</title></rect>')
        out.append(f'<text class="val" x="{label_w + bw + 8:.1f}" y="{y + bar_h * .68:.1f}" font-size="15">{fmt.format(v)}</text>')
    out.append("</svg>")
    return "".join(out)


def hbar_narrow(rows, fmt="{:.0f}%", maxv=100, hl=None, unit_title=""):
    """Phone version: each label sits above its bar, so text stays full size on small screens."""
    w, bar_h, row_h = 360, 22, 58
    h = len(rows) * row_h
    plot = w - 62
    out = [f'<svg class="narrow" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(unit_title)}">']
    for i, (lab, v, tip) in enumerate(rows):
        y = i * row_h
        bw = max(2, plot * v / maxv)
        cls = "bar hl" if hl and hl(lab) else "bar"
        out.append(f'<text x="0" y="{y + 17}" font-size="15">{escape(lab)}</text>')
        out.append(f'<rect class="track" x="0" y="{y + 25}" width="{plot}" height="{bar_h}" rx="4"/>')
        out.append(f'<rect class="{cls}" x="0" y="{y + 25}" width="{bw:.1f}" height="{bar_h}" rx="4"><title>{escape(tip)}</title></rect>')
        out.append(f'<text class="val" x="{bw + 8:.1f}" y="{y + 25 + bar_h * .75:.1f}" font-size="15">{fmt.format(v)}</text>')
    out.append("</svg>")
    return "".join(out)


def chart(rows, hl=None, label_w=210, unit_title=""):
    return hbar(rows, hl=hl, label_w=label_w, unit_title=unit_title) + hbar_narrow(rows, hl=hl, unit_title=unit_title)


fr = F["filing_rates"]
cohort_order = ["bought before 1990", "bought 1990-99", "bought 2000-09", "bought 2010-14", "bought 2015-19",
                "bought 2020-22", "bought 2023-24", "bought 2025"]
coh = {r["segment"]: r for r in fr if r["segment_type"] == "purchase_cohort"}
cohort_rows = [(s.replace("bought ", "Bought ").replace("-", "–"), coh[s]["pct_both"],
                f'{coh[s]["filed_both"]:,} of {coh[s]["households"]:,} homes have both; {coh[s]["county_only"]} county only, {coh[s]["city_only"]} city only')
               for s in cohort_order]
chart_cohort = chart(cohort_rows, hl=lambda l: l.startswith("Bought 202"), unit_title="Share of homes with a homestead exemption at both offices, by year bought")

tk = [r for r in F["senior_takeup"] if r["value_band"] == "all values"]
tk_label = {"any city senior exemption": "Any city senior exemption", "GH-2 (65+, no income test)": "GH-2, 65+ (no income test)",
            "70+ school exemption (S-3/S-6 or S-2)": "School, 70+ (no income test)", "GH-3 (62+, income)": "GH-3, 62+ (income test)"}
tk_rows = [(tk_label[r["benefit"]], r["pct_claiming"], f'{r["claiming"]} of {r["households"]} households whose DeKalb records already show they qualify') for r in tk]
tk_rows.sort(key=lambda r: -r[1])
chart_takeup = chart(tk_rows, hl=lambda l: "(income test)" in l, label_w=250, unit_title="Share of eligible seniors claiming each city exemption")

# proven gap table
gs = F["gap_summary"]
order = ["COUNTY_BASIC_MISSING", "CITY_BASIC_MISSING", "GH3_MISSING", "GH2_MISSING", "SCHOOL_70_MISSING"]
plain = {
    "COUNTY_BASIC_MISSING": ("DeKalb homestead, though the city's is on file", "DeKalb County"),
    "CITY_BASIC_MISSING": ("City homestead (GH-1), though DeKalb's is on file", "City"),
    "GH3_MISSING": ("City GH-3, with age 62+ and low income already shown to DeKalb", "City"),
    "GH2_MISSING": ("City GH-2, with age 65+ already shown", "City"),
    "SCHOOL_70_MISSING": ("City school exemption for 70+, with age already shown", "City"),
}
gap_rows = []
for code in order:
    rs = [r for r in gs if r["gap_code"] == code and r["status"] == "proven"]
    hh = sum(r["households"] for r in rs)
    rel = sum((r["relief_city_tax_per_year"] or 0) + (r["relief_county_tax_per_year"] or 0) for r in rs)
    if code == "COUNTY_BASIC_MISSING":
        reltxt = "$780,000–$830,000"
    else:
        reltxt = f"${round(rel, -3):,.0f}"
    hl = ' class="hl"' if code == "COUNTY_BASIC_MISSING" else ""
    gap_rows.append(f'<tr{hl}><td>{plain[code][0]}</td><td>{plain[code][1]}</td><td class="num">{hh:,.0f}</td><td class="num">{reltxt}</td></tr>')
gap_table = ('<div class="table-wrap"><table><thead><tr><th>Missing exemption</th><th>Office</th><th class="num">Homes</th>'
             '<th class="num">Relief missed per year</th></tr></thead><tbody>' + "".join(gap_rows) + "</tbody></table></div>")


# ------------------------------------------------------------------ map
def project(lon, lat, bbox, w):
    minx, miny, maxx, maxy = bbox
    k = math.cos(math.radians((miny + maxy) / 2))
    sx = w / ((maxx - minx) * k)
    return (lon - minx) * k * sx, (maxy - lat) * sx


def rings(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    return geom["coordinates"]


pts = [p for poly in rings(G["city"]) for ring in poly for p in ring]
bbox = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
W = 520
H = project(bbox[0], bbox[1], bbox, W)[1]


def rdp(pts, eps=1.2):
    if len(pts) < 3:
        return pts
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    dx, dy = x2 - x1, y2 - y1
    n = math.hypot(dx, dy) or 1e-9
    dmax, idx = 0, 0
    for i in range(1, len(pts) - 1):
        d = abs(dy * pts[i][0] - dx * pts[i][1] + x2 * y1 - y2 * x1) / n
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        return rdp(pts[:idx + 1], eps)[:-1] + rdp(pts[idx:], eps)
    return [pts[0], pts[-1]]


def path(geom):
    d = []
    for poly in rings(geom):
        for ring in poly:
            pts = [project(x, y, bbox, W) for x, y in ring]
            m = len(pts) // 2
            xy = rdp(pts[:m + 1])[:-1] + rdp(pts[m:])
            if len(xy) < 3:
                continue
            d.append("M" + "L".join(f"{x:.0f},{y:.0f}" for x, y in xy) + "Z")
    return "".join(d)


def path_rel(rings_ll, eps=1.3):
    """Compact SVG path with relative coordinates, for maps with many small shapes."""
    d = []
    for ring in rings_ll:
        pts = [project(x, y, bbox, W) for x, y in ring]
        m = len(pts) // 2
        xy = [(round(x), round(y)) for x, y in rdp(pts[:m + 1], eps)[:-1] + rdp(pts[m:], eps)]
        xy = [q for i, q in enumerate(xy) if i == 0 or q != xy[i - 1]]
        if len(xy) < 3:
            continue
        seg = [f"M{xy[0][0]},{xy[0][1]}l"]
        seg.append(" ".join(f"{x2 - x1},{y2 - y1}" for (x1, y1), (x2, y2) in zip(xy, xy[1:])))
        d.append("".join(seg) + "z")
    return "".join(d).replace(" -", "-")


def centroid(geom):
    best = max((ring for poly in rings(geom) for ring in poly[:1]), key=lambda r: len(r))
    xy = [project(x, y, bbox, W) for x, y in best]
    a = cx = cy = 0
    for (x1, y1), (x2, y2) in zip(xy, xy[1:] + xy[:1]):
        c = x1 * y2 - x2 * y1
        a += c; cx += (x1 + x2) * c; cy += (y1 + y2) * c
    a /= 2
    return (cx / (6 * a), cy / (6 * a)) if a else xy[0]


tstats = {t["tract_geoid"]: t for t in F["tracts"]}
steps = [(0, "#c9dbea"), (20, "#8fb3d3"), (22, "#4f7fae")]   # one hue, light to dark


def tcolor(p):
    c = steps[0][1]
    for lo, col in steps:
        if p >= lo:
            c = col
    return c


MAP_TEXT = {
    "en": dict(aria="Share of homes with a proven or likely gap, by census tract", tract="Tract",
               few="{name}: fewer than 25 homes, not shown", tip="{name}: {g} of {h} homes ({p:.0f}%) have a gap",
               legend=["Under 20%", "20% to 22%", "22% or more"], legend_few="Fewer than 25 homes"),
    "es": dict(aria="Porcentaje de viviendas con una exención que falta, comprobada o probable, por sector censal", tract="Sector censal",
               few="{name}: menos de 25 viviendas, no se muestra", tip="{name}: {g} de {h} viviendas ({p:.0f}%) tienen una exención que falta",
               legend=["Menos de 20%", "De 20% a 22%", "22% o más"], legend_few="Menos de 25 viviendas"),
}


def make_map(lang):
    T = MAP_TEXT[lang]
    parts = [f'<svg viewBox="-6 -6 {W + 12} {H + 12:.0f}" role="img" aria-label="{escape(T["aria"])}">',
             '<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
             '<rect width="6" height="6" fill="var(--wash)"/><line x1="0" y1="0" x2="0" y2="6" stroke="var(--rule)" stroke-width="2"/></pattern></defs>']
    labels = []
    for t in G["tracts"]:
        st = tstats.get(t["id"], {})
        pct = st.get("pct_with_gap")
        name = st.get("tract_name") or f"Census Tract {int(t['id'][5:9])}.{t['id'][9:]}".replace(".00", "")
        name = name.replace("Census Tract", T["tract"])
        if pct is None:
            fill, tip = "url(#hatch)", T["few"].format(name=name)
        else:
            fill = tcolor(pct)
            tip = T["tip"].format(name=name, g=st["homes_with_gap"], h=f"{st['homes']:,}", p=pct)
            cx, cy = centroid(t["geom"])
            labels.append(f'<text x="{cx:.0f}" y="{cy:.0f}" text-anchor="middle">{pct:.0f}%</text>')
        parts.append(f'<path class="tract" d="{path(t["geom"])}" fill="{fill}"><title>{escape(tip)}</title></path>')
    parts.append(f'<path class="city" d="{path(G["city"])}"/>')
    parts += labels
    parts.append("</svg>")
    leg = ('<div class="legend">' + "".join(f'<span><i style="background:{c}"></i>{lab}</span>'
                                           for (lo, c), lab in zip(steps, T["legend"])) +
           f'<span><i style="background:repeating-linear-gradient(45deg,var(--wash) 0 3px,var(--rule) 3px 5px)"></i>{T["legend_few"]}</span></div>')
    return "".join(parts), leg


map_svg, legend = make_map("en")

# ------------------------------------------------------------------ block map (public)
# Shares are binned into ranges; blocks with fewer than 10 homes are hatched. No counts are published.
BLK = json.load(open(HERE / "blocks_map.json"))
BSTEPS = ["#dbe7f2", "#a9c6e0", "#6f9cc6", "#2f5f8f"]
BLOCK_TEXT = {
    "en": dict(aria="Share of homes with a proven missing exemption, by census block",
               legend=["Under 10%", "10% to 20%", "20% to 30%", "30% or more"],
               tip="{r} of homes in this block have a proven gap", few="Fewer than 10 homes, not shown"),
    "es": dict(aria="Porcentaje de viviendas con una exención que falta comprobada, por manzana censal",
               legend=["Menos de 10%", "De 10% a 20%", "De 20% a 30%", "30% o más"],
               tip="{r} de las viviendas de esta manzana tienen una exención que falta comprobada", few="Menos de 10 viviendas, no se muestra"),
}


def make_block_map(lang):
    T = BLOCK_TEXT[lang]
    city_d = path(G["city"])
    parts = [f'<svg viewBox="-6 -6 {W + 12} {H + 12:.0f}" role="img" aria-label="{escape(T["aria"])}">',
             '<defs><pattern id="bhatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
             '<rect width="5" height="5" fill="var(--wash)"/><line x1="0" y1="0" x2="0" y2="5" stroke="var(--rule)" stroke-width="2"/></pattern>'
             f'<clipPath id="cityclip"><path d="{city_d}"/></clipPath></defs>',
             f'<path d="{city_d}" fill="var(--paper)"/>', '<g clip-path="url(#cityclip)">']
    for band in (-1, 0, 1, 2, 3):          # one shape per range, so each tooltip appears once
        d = "".join(path_rel(blk["rings"]) for blk in BLK.values() if blk["band"] == band)
        if not d:
            continue
        fill = "url(#bhatch)" if band < 0 else BSTEPS[band]
        tip = T["few"] if band < 0 else T["tip"].format(r=T["legend"][band])
        parts.append(f'<path class="block" d="{d}" fill="{fill}"><title>{escape(tip)}</title></path>')
    parts.append("</g>")
    parts.append(f'<path class="city" d="{city_d}"/>')
    parts.append("</svg>")
    leg = ('<div class="legend">' + "".join(f'<span><i style="background:{c}"></i>{lab}</span>' for c, lab in zip(BSTEPS, T["legend"])) +
           f'<span><i style="background:repeating-linear-gradient(45deg,var(--wash) 0 3px,var(--rule) 3px 5px)"></i>{T["few"].split(",")[0]}</span></div>')
    return "".join(parts), leg


block_svg, block_legend = make_block_map("en")

unf = F["unfiled"][0]

# ------------------------------------------------------------------ pages
index_body = f"""
<section class="hero band">
  <div>
    <h1>Is your home getting every property tax break it qualifies for?</h1>
    <p class="lede">Each exemption has to be claimed separately with DeKalb County and with the city, and many homeowners miss one. Check your address in seconds.</p>
    <form id="lookup-form" class="lookup" autocomplete="off">
      <label for="address">Your street address</label>
      <div class="row">
        <input id="address" name="address" type="text" inputmode="text" placeholder="For example, 123 Main St" required>
        <button type="submit">Check my address</button>
      </div>
      <p class="hint">City of Decatur homes only. Add a unit number for condos.</p>
    </form>
  </div>
  <aside class="bill" aria-label="Example of a city tax bill">
    <h2>Example: part of a 2026 City of Decatur tax bill</h2>
    <ol>
      <li><span class="what">City general levy</span><span class="lead"></span><span class="amt">$3,962.00</span></li>
      <li><span class="what">Homestead exemption, GH‑1</span><span class="lead"></span><span class="amt">−$446.00</span></li>
      <li class="missing"><span class="what">Age 65+ exemption, GH‑2</span><span class="lead"></span><span class="amt">not on bill</span></li>
      <li class="total"><span class="what">You pay</span><span class="lead"></span><span class="amt">$3,516.00</span></li>
    </ol>
    <p class="note">Every exemption is its own line on the bill. When one was never applied for, it simply isn't there, and the owner pays the difference: $167 a year for GH-2 on this bill.</p>
  </aside>
</section>
<div id="results" aria-live="polite"></div>

<aside class="callout">
  <span class="tip-icon">{ICON['offices']}</span>
  <p><strong>Bought your home in the last few years?</strong> Filing for a homestead with DeKalb at closing doesn't cover the City of Decatur. Each office needs its own application. <a href="apply.html">See how to apply to both</a>.</p>
</aside>

<section>
  <h2>What the check looks at</h2>
  <div class="two-col">
    <div><h3>Both offices' records</h3><p>Your 2026 city tax bill lists the city exemptions you have. DeKalb County's records list the county's. The check puts them side by side.</p></div>
    <div><h3>Gaps between them</h3><p>If one office has a homestead on file and the other doesn't, or DeKalb's records already show an owner's age and the city's matching exemption is missing, the check tells you which form to file.</p></div>
    <div><h3>Nothing about you</h3><p>The check only uses public property records. It doesn't ask your name, age or income, and it doesn't keep the addresses people type.</p></div>
  </div>
</section>

<section class="facts band-dark" aria-label="Key numbers">
  <div class="fact"><strong>1,259</strong><span>Decatur homes whose own records show a missing exemption</span></div>
  <div class="fact"><strong>$1.2 million</strong><span>a year in property tax those homeowners don't need to pay</span></div>
  <div class="fact"><strong>1 in 4</strong><span>owners who bought in 2020–22 still have a homestead at only one office</span></div>
</section>
<p><a href="findings.html">Read what we found</a> or <a href="apply.html">see how to apply</a>.</p>
"""
page("index.html", "Senior Homestead Check · Decatur, GA", index_body, '<script src="lookup.js" defer></script>', alt="es.html")

findings_body = f"""
<h1>What we found</h1>
<p class="lede">At least 1,259 City of Decatur households that already qualify, on the evidence of their own filings, are paying about $1.2 million a year more in property tax than they need to.</p>
<p>The problem is mostly not who qualifies. It's a system that makes relief something homeowners must claim, claim twice at two offices, and claim again at each age milestone.</p>

<h2>The gaps the records prove</h2>
<p>These homes already have the evidence on file at one office. The other office's matching exemption is missing.</p>
{gap_table}
<p class="small muted"><span class="hl-key"></span> The highlighted row is the biggest gap: about two-thirds of all the relief missed. Some homes have more than one gap. County figures are modelled from what recent filers receive and are shown as a range. Another 225 homes where an owner is shown to be 65+ may qualify for a city school exemption depending on income; they are not counted in the total.</p>

<h2>Where it breaks: two offices, two forms</h2>
<p>Owners who bought decades ago nearly all hold a homestead at both offices. Recent buyers often file with DeKalb at closing and never file the city's separate form, and the gap doesn't close by itself.</p>
<figure class="chart">{chart_cohort}
<figcaption>Share of likely owner-occupied homes with a homestead exemption at both the City of Decatur and DeKalb County, by year of purchase. Recent buyers are highlighted. City of Decatur 2026 tax bills and DeKalb County records.</figcaption></figure>

<h2>Where it breaks: income tests</h2>
<p>When a city exemption depends only on age, nearly every senior whose DeKalb records show their age also claims it. When the city adds an income test with a different definition of income, take-up falls to about half.</p>
<figure class="chart">{chart_takeup}
<figcaption>Share of households claiming each city exemption, among households whose DeKalb exemption already shows they meet the age (and for GH-3, income) requirement. 2026 tax year.</figcaption></figure>

<h2>Every neighborhood has gaps</h2>
<p>In almost every part of the city, close to one home in five already has a proven gap. It isn't one neighborhood's problem.</p>
<figure class="map">{block_svg}{block_legend}
<figcaption>Share of homes in the analysis with a proven missing exemption, by 2020 census block, within city limits. Blocks with fewer than 10 homes are hatched, and the map shows ranges, not exact counts. Unshaded areas have no homes in the analysis.</figcaption></figure>

<h2>Seniors who have never filed</h2>
<p>Census counts suggest about {round(unf['median'], -1):.0f} senior-headed owner households in Decatur have no senior exemption at all (90% range: {round(unf['low_5pct'], -1):.0f} to {round(unf['high_95pct'], -1):.0f}). Public records can't show who they are, because the only age information in them comes from exemptions already filed. That's why the address check lists every senior exemption, so owners can see which ones they haven't claimed.</p>

<h2>What would fix it</h2>
<ol class="steps">
  <li><strong>One homestead, recognized by both offices.</strong> The city could accept DeKalb's homestead approvals, or both could use one application.</li>
  <li><strong>Age-only exemptions granted when age is already proven.</strong> GH-2 and the 70+ school exemption have no income test.</li>
  <li><strong>Accept DeKalb's income finding.</strong> A DeKalb senior exemption capped at $37,500 of Georgia net income already meets the city's GH-3 limit.</li>
  <li><strong>Reach buyers at closing</strong> with one notice covering both applications and both deadlines.</li>
  <li><strong>Contact the households with proven gaps,</strong> without implying anyone did something wrong.</li>
</ol>
<p class="small muted">No one is being billed in error: both offices apply the exemptions on file, as the law requires. Wider take-up shifts some tax to other owners rather than cutting revenue dollar for dollar. See <a href="about.html">About the data</a> for methods and limits.</p>
"""
page("findings.html", "What we found · Senior Homestead Check", findings_body, alt="hallazgos.html",
     desc="How many City of Decatur homeowners are missing property tax exemptions, and why.")

apply_body = """
<h1>How to apply</h1>
<p class="lede">In the City of Decatur you apply to two offices. Each exemption is a separate application, and none is added automatically when you reach a new age.</p>

<div class="two-col">
<section class="panel">
  <h2 style="margin-top:0">City of Decatur</h2>
  <p>Covers city taxes and Decatur's school taxes (GH-1, GH-2, GH-3 and the S exemptions).</p>
  <p><strong>Deadline:</strong> April 1 for that year's taxes. File by March 15 to see it on the first bill.</p>
  <p><strong>Online:</strong> application forms on the <a href="https://www.decaturga.com/adminservices/page/homestead-exemption-information">city's homestead exemption page</a>.</p>
  <p><strong>In person:</strong> Administrative Services, City Hall, 509 N. McDonough St., Decatur, 8 a.m. to 5 p.m., Monday to Friday.</p>
  <p><strong>Phone:</strong> <a href="tel:+14043704100">404-370-4100</a></p>
</section>
<section class="panel">
  <h2 style="margin-top:0">DeKalb County</h2>
  <p>Covers DeKalb County taxes (the basic H1 homestead and county senior exemptions).</p>
  <p><strong>Deadline:</strong> DeKalb accepts applications from January 1. Filing by April 1 is safest; check the county's page for the current cut-off.</p>
  <p><strong>Online:</strong> the <a href="https://dekalbtaxga.gov/file-homestead-exemption">Tax Commissioner's homestead page</a> links to online filing for basic and senior exemptions.</p>
  <p><strong>In person or by mail:</strong> any Tax Commissioner office, year-round.</p>
  <p><strong>Phone:</strong> <a href="tel:+14042984000">404-298-4000</a></p>
</section>
</div>

<h2>Tips</h2>
""" + tips([
    ("offices", "Bought recently?", "Check that you filed with <em>both</em> offices. Filing with DeKalb at closing doesn't cover the city."),
    ("birthday", "Turned 62, 65, 70 or 80?", "Look at the list below again. New exemptions don't start on their own."),
    ("phone", "Not sure?", "Call the office. Staff can tell you what's on file and which forms fit."),
]) + """

<h2>What to bring</h2>
<ul>
  <li><strong>For a basic homestead:</strong> proof you own and live in the home, such as a Georgia driver's license or ID showing the address. DeKalb also asks for vehicle registration in DeKalb.</li>
  <li><strong>For age-based exemptions:</strong> a Georgia ID or birth certificate.</li>
  <li><strong>For exemptions with an income limit:</strong> last year's income tax return, or your Social Security benefit statement (SSA-1099) if you don't file taxes.</li>
</ul>

<h2>City exemptions for owners 62 and older</h2>
<div class="table-wrap"><table>
<thead><tr><th>Code</th><th>Age</th><th>Income limit</th><th>Amount</th></tr></thead>
<tbody>
<tr><td><strong>GH-2</strong></td><td>65+</td><td>None</td><td>$15,000</td></tr>
<tr><td><strong>GH-3</strong></td><td>62+</td><td>Georgia taxable income under $60,000</td><td>$25,000</td></tr>
<tr><td><strong>GS-1</strong></td><td>62+</td><td>Household income under $25,000</td><td>$50,000</td></tr>
<tr><td><strong>S-1</strong></td><td>62+</td><td>Under $10,000, not counting retirement income</td><td>$10,000</td></tr>
<tr><td><strong>S-5</strong></td><td>65–69</td><td>Federal adjusted gross income under $62,000</td><td>$200,000</td></tr>
<tr><td><strong>S-3 / S-6</strong></td><td>70+</td><td>None</td><td>$50,000 / $200,000</td></tr>
<tr><td><strong>S-2</strong></td><td>80+</td><td>Federal adjusted gross income under $40,000</td><td>All school taxes</td></tr>
</tbody></table></div>
<p class="small muted">Amounts are taken off the home's taxable value, not off the bill. Source: City of Decatur, 2026. DeKalb's senior exemptions (H3 to H10) have their own age and income rules; see the county's page.</p>

"""
page("apply.html", "How to apply · Senior Homestead Check", apply_body, alt="solicitar.html",
     desc="Where, when and how to apply for City of Decatur and DeKalb County homestead exemptions.")

about_body = """
<h1>About the data</h1>
<p class="lede">Everything on this site comes from public property records and the U.S. Census.</p>

<h2>Sources</h2>
<ul>
  <li>City of Decatur 2026 tax bills, which list each exemption as a line item (<a href="https://www.decaturgatax.com/taxes#/WildfireSearch">city tax search</a>).</li>
  <li>DeKalb County Tax Commissioner exemption and ownership records (<a href="https://dekalbtaxga.gov/">dekalbtaxga.gov</a>) and DeKalb property appraisal records.</li>
  <li>City of Decatur and DeKalb County parcel maps (<a href="https://dcgis-dekalbgis.hub.arcgis.com/">DeKalb GIS open data</a>).</li>
  <li>U.S. Census Bureau, American Community Survey 2020–2024 and the 2020 Census (<a href="https://data.census.gov/">data.census.gov</a>).</li>
</ul>
<p>Records were collected in September and October 2026 for about 7,700 residential parcels in the City of Decatur, using a slow, rate-limited process so the public sites weren't burdened.</p>

<h2>How gaps are found</h2>
<p>A gap is counted as <strong>proven</strong> only when one office's records already show the owner meets the requirement for an exemption the other office hasn't applied. For example, DeKalb has a homestead on file but the city bill has none. Ages are taken only from exemptions already on file and are never guessed about individuals.</p>
<p>City savings are each missing exemption multiplied by the 2026 city tax rates; this method matches the credits on 99.8% of 2026 city bills. County savings are modelled from what recent county filers receive and are about 7% high overall, so they're shown as a range.</p>

<h2>Limits</h2>
<ul>
  <li>Public records don't show income or exact age, so exemptions with income tests can only be flagged as "worth checking".</li>
  <li>Some homes may not be the owner's main residence, which every homestead exemption requires.</li>
  <li>Records change. An application filed after September 2026 won't show here until the next update.</li>
</ul>

<h2>Privacy</h2>
<ul>
  <li>The address check shows only what is already public for that address, and never shows owner names.</li>
  <li>Addresses typed into the check aren't stored. To prevent misuse, the site keeps a scrambled, daily-changing code for each visitor for two days to limit how many lookups one person can make.</li>
  <li>The partner outreach list and map, which include names and mailing addresses from public records and show individual homes, are available only to approved organizations after signing in, and every view is logged. The public maps on this site show only ranges for areas of 10 or more homes.</li>
</ul>

<h2 id="mistakes">Report a mistake</h2>
<p>If the check shows something wrong for your home, the official record is what each office has on file: call the city at <a href="tel:+14043704100">404-370-4100</a> or DeKalb at <a href="tel:+14042984000">404-298-4000</a>. To tell us about an error on this site, contact the project team through the person who shared it with you.</p>
"""
page("about.html", "About the data · Senior Homestead Check", about_body, alt="datos.html")

partners_body = """
<h1>Partner outreach list</h1>
<p class="lede">For organizations helping Decatur homeowners apply for exemptions they've missed. Sign in with the account you were given.</p>

<div id="loading-view"><p class="muted">Loading…</p></div>
<script>setTimeout(function(){var l=document.getElementById("loading-view");if(l&&!l.hidden){l.innerHTML='<p class="warn">The sign-in page could not load. Check your connection and reload the page.</p>';}},10000);</script>

<div id="signin-view" hidden>
  <form id="signin-form" class="signin">
    <label>Email<input id="email" type="email" autocomplete="username" required></label>
    <label>Password<input id="password" type="password" autocomplete="current-password" required></label>
    <div><button type="submit">Sign in</button></div>
    <p id="signin-error" class="small" style="color:var(--accent-ink)" role="alert"></p>
  </form>
  <p class="small muted">Accounts are created by the project team for approved partners only. To request access, contact the person who shared this site with you.</p>
</div>

<div id="denied-view" hidden>
  <p class="warn">You're signed in, but this account isn't approved for the outreach list. Contact the project team to request access.</p>
  <p><button class="quiet" id="signout2" type="button">Sign out</button></p>
</div>

<div id="list-view" hidden>
  <p class="warn"><strong>Handle with care.</strong> Use this list only to offer help with exemption applications. Don't share it, and don't suggest anyone has done something wrong. Every view and download is recorded.</p>
  <p class="small">Signed in as <span id="who"></span>. <button class="quiet" id="signout" type="button" style="min-height:auto;padding:.2rem .6rem">Sign out</button></p>
  <div class="toolbar">
    <fieldset id="groups" class="chips" style="border:0;padding:0;margin:0">
      <legend class="small" style="font-weight:700;margin-bottom:.3rem">Show homes with</legend>
      <label><input type="checkbox" value="proven" checked> Proven gaps</label>
      <label><input type="checkbox" value="likely" checked> Likely gaps</label>
      <label><input type="checkbox" value="long_tenure" checked> Owner since before 1990, no senior exemption</label>
      <label><input type="checkbox" value="possible"> Possible county senior gap</label>
    </fieldset>
    <label>Search<input id="search" type="search" placeholder="Street, owner or ZIP"></label>
    <label>Sort by<select id="sort"><option value="address">Address</option><option value="savings">Estimated savings</option><option value="since">Owner since</option></select></label>
    <button id="export" type="button" class="quiet">Download CSV</button>
  </div>
  <div class="tabs" role="tablist" aria-label="View">
    <button type="button" role="tab" id="tab-list" aria-selected="true" aria-controls="list-panel">List</button>
    <button type="button" role="tab" id="tab-map" aria-selected="false" aria-controls="map-panel">Map</button>
    <strong id="count"></strong>
  </div>
  <div id="list-panel" role="tabpanel" aria-labelledby="tab-list">
  <div class="table-wrap"><table id="list">
    <thead><tr><th>Property</th><th>Owner of record</th><th>Mailing address</th><th>Why it's listed</th><th class="num">City $/yr</th><th class="num">County $/yr</th></tr></thead>
    <tbody></tbody>
  </table></div>
  <div class="pager"><button id="prev" class="quiet" type="button">Previous</button><span id="pageinfo"></span><button id="next" class="quiet" type="button">Next</button></div>
  </div>
  <div id="map-panel" role="tabpanel" aria-labelledby="tab-map" hidden>
    <div class="pmap-wrap">
      <div class="pmap">
        <canvas id="pmap" tabindex="0" role="img" aria-label="Map of City of Decatur homes, colored by the reason each is on the outreach list. The list view has the same homes in text."></canvas>
        <div class="pmap-zoom"><button type="button" id="pmap-in" aria-label="Zoom in">+</button><button type="button" id="pmap-out" aria-label="Zoom out">&minus;</button><button type="button" id="pmap-fit" class="small">City</button></div>
        <div class="pmap-tip" id="pmap-tip" hidden></div>
        <p class="pmap-status" id="pmap-status" hidden></p>
      </div>
      <div class="pmap-side">
        <div id="pmap-legend"></div>
        <label class="small"><input type="checkbox" id="pmap-labels" checked> Street names when zoomed in</label>
        <div id="pmap-detail"></div>
        <p class="small muted">The filters and search above apply to the map. Drag to move, scroll or pinch to zoom, click a home for details. Please don't share screenshots that show individual homes.</p>
      </div>
    </div>
  </div>
  <p class="small muted">Proven: the other office's records already show eligibility. Likely: depends on income or turning 70. Possible: DeKalb senior exemptions have income limits that records can't confirm. Savings are estimates.</p>
</div>
"""
page("partners.html", "Partner sign-in · Senior Homestead Check", partners_body, '<script type="module" src="partners.js"></script>')

# ------------------------------------------------------------------ Spanish pages
es_index_body = """
<section class="hero band">
  <div>
    <h1>¿Su vivienda recibe todas las exenciones de impuestos que le corresponden?</h1>
    <p class="lede">Cada exención se solicita por separado con el Condado de DeKalb y con la Ciudad, y muchos propietarios se pierden alguna. Revise su dirección en segundos.</p>
    <form id="lookup-form" class="lookup" autocomplete="off">
      <label for="address">Su dirección</label>
      <div class="row">
        <input id="address" name="address" type="text" inputmode="text" placeholder="Por ejemplo, 123 Main St" required>
        <button type="submit">Revisar mi dirección</button>
      </div>
      <p class="hint">Solo viviendas dentro de la Ciudad de Decatur. Para condominios, agregue el número de unidad.</p>
    </form>
  </div>
  <aside class="bill" aria-label="Ejemplo de una factura de impuestos de la Ciudad">
    <h2>Ejemplo: parte de una factura de impuestos 2026 de la Ciudad de Decatur</h2>
    <ol>
      <li><span class="what">Impuesto general de la Ciudad</span><span class="lead"></span><span class="amt">$3,962.00</span></li>
      <li><span class="what">Exención homestead, GH‑1</span><span class="lead"></span><span class="amt">−$446.00</span></li>
      <li class="missing"><span class="what">Exención por edad 65+, GH‑2</span><span class="lead"></span><span class="amt">no aparece</span></li>
      <li class="total"><span class="what">Usted paga</span><span class="lead"></span><span class="amt">$3,516.00</span></li>
    </ol>
    <p class="note">Cada exención aparece como una línea en la factura. Si nunca se solicitó, simplemente no aparece y el propietario paga la diferencia: $167 al año por la GH-2 en esta factura.</p>
  </aside>
</section>
<div id="results" aria-live="polite"></div>

<aside class="callout">
  <span class="tip-icon">""" + ICON["offices"] + """</span>
  <p><strong>¿Compró su vivienda en los últimos años?</strong> La solicitud homestead que se hace con DeKalb al cerrar la compra no cubre a la Ciudad de Decatur. Cada oficina necesita su propia solicitud. <a href="solicitar.html">Vea cómo solicitar en ambas</a>.</p>
</aside>

<section>
  <h2>Qué revisamos</h2>
  <div class="two-col">
    <div><h3>Los registros de ambas oficinas</h3><p>Su factura de impuestos 2026 de la Ciudad muestra las exenciones de la Ciudad. Los registros del Condado de DeKalb muestran las del Condado. La revisión los compara lado a lado.</p></div>
    <div><h3>Las diferencias entre ellas</h3><p>Si una oficina tiene su exención homestead y la otra no, o si los registros de DeKalb ya muestran la edad de un propietario y falta la exención correspondiente de la Ciudad, le indicamos qué formulario presentar.</p></div>
    <div><h3>Nada sobre usted</h3><p>Solo usamos registros públicos de propiedades. No le pedimos su nombre, edad ni ingresos, y no guardamos las direcciones que se escriben.</p></div>
  </div>
</section>

<section class="facts band-dark" aria-label="Cifras clave">
  <div class="fact"><strong>1,259</strong><span>viviendas en Decatur cuyos propios registros muestran una exención que falta</span></div>
  <div class="fact"><strong>$1.2 millones</strong><span>al año en impuestos que esos propietarios no tendrían que pagar</span></div>
  <div class="fact"><strong>1 de cada 4</strong><span>propietarios que compraron en 2020–22 tiene la exención homestead en una sola oficina</span></div>
</section>
<p><a href="hallazgos.html">Lea los hallazgos</a> o <a href="solicitar.html">vea cómo solicitar</a>.</p>
"""
page("es.html", "Senior Homestead Check: revise su dirección", es_index_body, '<script src="lookup.js" defer></script>', lang="es")

es_apply_body = """
<h1>Cómo solicitar</h1>
<p class="lede">En la Ciudad de Decatur hay que solicitar en dos oficinas. Cada exención es una solicitud aparte, y ninguna se agrega automáticamente al cumplir una nueva edad.</p>

<div class="two-col">
<section class="panel">
  <h2 style="margin-top:0">Ciudad de Decatur</h2>
  <p>Cubre los impuestos de la Ciudad y los impuestos escolares de Decatur (GH-1, GH-2, GH-3 y las exenciones S).</p>
  <p><strong>Fecha límite:</strong> 1 de abril para los impuestos de ese año. Presente su solicitud antes del 15 de marzo para que aparezca en la primera factura.</p>
  <p><strong>En línea:</strong> formularios en la <a href="https://www.decaturga.com/adminservices/page/homestead-exemption-information" lang="en">página de exenciones homestead de la Ciudad</a> (en inglés).</p>
  <p><strong>En persona:</strong> Administrative Services, City Hall, 509 N. McDonough St., Decatur, de 8 a.m. a 5 p.m., de lunes a viernes.</p>
  <p><strong>Teléfono:</strong> <a href="tel:+14043704100">404-370-4100</a></p>
</section>
<section class="panel">
  <h2 style="margin-top:0">Condado de DeKalb</h2>
  <p>Cubre los impuestos del Condado de DeKalb (la exención básica H1 y las exenciones del condado para personas mayores).</p>
  <p><strong>Fecha límite:</strong> DeKalb acepta solicitudes desde el 1 de enero. Lo más seguro es presentarla antes del 1 de abril; confirme la fecha límite actual en la página del Condado.</p>
  <p><strong>En línea:</strong> la <a href="https://dekalbtaxga.gov/file-homestead-exemption" lang="en">página de exenciones homestead del Recaudador de Impuestos</a> (en inglés) tiene enlaces para solicitar en línea.</p>
  <p><strong>En persona o por correo:</strong> en cualquier oficina del Recaudador de Impuestos (Tax Commissioner), todo el año.</p>
  <p><strong>Teléfono:</strong> <a href="tel:+14042984000">404-298-4000</a></p>
</section>
</div>

<h2>Consejos</h2>
""" + tips([
    ("offices", "¿Compró recientemente?", "Verifique que presentó la solicitud en <em>ambas</em> oficinas. La solicitud que se hace con DeKalb al cerrar la compra no cubre a la Ciudad."),
    ("birthday", "¿Cumplió 62, 65, 70 u 80 años?", "Revise otra vez la lista de abajo. Las exenciones nuevas no se aplican solas."),
    ("phone", "¿Tiene dudas?", "Llame a la oficina. Pregunte si hay alguien que pueda atenderle en español, o vaya con una persona de confianza que le ayude."),
]) + """

<h2>Qué debe llevar</h2>
<ul>
  <li><strong>Para la exención homestead básica:</strong> prueba de que es dueño y vive en la vivienda, como una licencia de conducir o identificación de Georgia con esa dirección. DeKalb también pide el registro de su vehículo en DeKalb.</li>
  <li><strong>Para exenciones por edad:</strong> identificación de Georgia o acta de nacimiento.</li>
  <li><strong>Para exenciones con límite de ingresos:</strong> su declaración de impuestos del año anterior, o el estado de beneficios del Seguro Social (SSA-1099) si no presenta declaración.</li>
</ul>

<h2>Exenciones de la Ciudad para propietarios de 62 años o más</h2>
<div class="table-wrap"><table>
<thead><tr><th>Código</th><th>Edad</th><th>Límite de ingresos</th><th>Monto</th></tr></thead>
<tbody>
<tr><td><strong>GH-2</strong></td><td>65+</td><td>Ninguno</td><td>$15,000</td></tr>
<tr><td><strong>GH-3</strong></td><td>62+</td><td>Ingreso tributable de Georgia menor de $60,000</td><td>$25,000</td></tr>
<tr><td><strong>GS-1</strong></td><td>62+</td><td>Ingreso del hogar menor de $25,000</td><td>$50,000</td></tr>
<tr><td><strong>S-1</strong></td><td>62+</td><td>Menor de $10,000, sin contar ingresos de jubilación</td><td>$10,000</td></tr>
<tr><td><strong>S-5</strong></td><td>65–69</td><td>Ingreso bruto ajustado federal menor de $62,000</td><td>$200,000</td></tr>
<tr><td><strong>S-3 / S-6</strong></td><td>70+</td><td>Ninguno</td><td>$50,000 / $200,000</td></tr>
<tr><td><strong>S-2</strong></td><td>80+</td><td>Ingreso bruto ajustado federal menor de $40,000</td><td>Todos los impuestos escolares</td></tr>
</tbody></table></div>
<p class="small muted">Los montos se restan del valor tributable de la vivienda, no de la factura. Fuente: Ciudad de Decatur, 2026. Las exenciones del Condado de DeKalb para personas mayores (H3 a H10) tienen sus propias reglas de edad e ingresos; consulte la página del Condado.</p>

"""
page("solicitar.html", "Cómo solicitar · Senior Homestead Check", es_apply_body, lang="es", alt="apply.html",
     desc="Dónde, cuándo y cómo solicitar las exenciones homestead de la Ciudad de Decatur y del Condado de DeKalb.")


# ------------------------------------------------------------------ Spanish findings (hallazgos.html)
coh_es = {"bought before 1990": "Compraron antes de 1990", "bought 1990-99": "Compraron en 1990–99",
          "bought 2000-09": "Compraron en 2000–09", "bought 2010-14": "Compraron en 2010–14",
          "bought 2015-19": "Compraron en 2015–19", "bought 2020-22": "Compraron en 2020–22",
          "bought 2023-24": "Compraron en 2023–24", "bought 2025": "Compraron en 2025"}
cohort_rows_es = [(coh_es[s_], coh[s_]["pct_both"],
                   f'{coh[s_]["filed_both"]:,} de {coh[s_]["households"]:,} viviendas tienen ambas; {coh[s_]["county_only"]} solo del Condado, {coh[s_]["city_only"]} solo de la Ciudad')
                  for s_ in cohort_order]
chart_cohort_es = chart(cohort_rows_es, hl=lambda l: l.startswith("Compraron en 202"), label_w=230,
                       unit_title="Porcentaje de viviendas con exención homestead en ambas oficinas, según el año de compra")
tk_label_es = {"any city senior exemption": "Cualquier exención para mayores", "GH-2 (65+, no income test)": "GH-2, 65+ (sin límite de ingresos)",
               "70+ school exemption (S-3/S-6 or S-2)": "Escolar, 70+ (sin límite de ingresos)", "GH-3 (62+, income)": "GH-3, 62+ (con límite de ingresos)"}
tk_rows_es = [(tk_label_es[r["benefit"]], r["pct_claiming"], f'{r["claiming"]} de {r["households"]} hogares cuyos registros de DeKalb ya muestran que califican') for r in tk]
tk_rows_es.sort(key=lambda r: -r[1])
chart_takeup_es = chart(tk_rows_es, hl=lambda l: "(con límite" in l, label_w=300,
                       unit_title="Porcentaje de personas mayores que califican y reclaman cada exención de la Ciudad")
plain_es = {
    "COUNTY_BASIC_MISSING": ("Homestead de DeKalb, aunque la de la Ciudad está registrada", "Condado de DeKalb"),
    "CITY_BASIC_MISSING": ("Homestead de la Ciudad (GH-1), aunque la de DeKalb está registrada", "Ciudad"),
    "GH3_MISSING": ("GH-3 de la Ciudad, con edad de 62+ e ingresos bajos ya demostrados ante DeKalb", "Ciudad"),
    "GH2_MISSING": ("GH-2 de la Ciudad, con edad de 65+ ya demostrada", "Ciudad"),
    "SCHOOL_70_MISSING": ("Exención escolar de la Ciudad para 70+, con la edad ya demostrada", "Ciudad"),
}
gap_rows_es = []
for code in order:
    rs = [r for r in gs if r["gap_code"] == code and r["status"] == "proven"]
    hh = sum(r["households"] for r in rs)
    rel = sum((r["relief_city_tax_per_year"] or 0) + (r["relief_county_tax_per_year"] or 0) for r in rs)
    reltxt = "$780,000–$830,000" if code == "COUNTY_BASIC_MISSING" else f"${round(rel, -3):,.0f}"
    hl = ' class="hl"' if code == "COUNTY_BASIC_MISSING" else ""
    gap_rows_es.append(f'<tr{hl}><td>{plain_es[code][0]}</td><td>{plain_es[code][1]}</td><td class="num">{hh:,.0f}</td><td class="num">{reltxt}</td></tr>')
gap_table_es = ('<div class="table-wrap"><table><thead><tr><th>Exención que falta</th><th>Oficina</th><th class="num">Viviendas</th>'
                '<th class="num">Alivio perdido al año</th></tr></thead><tbody>' + "".join(gap_rows_es) + "</tbody></table></div>")
map_svg_es, legend_es = make_map("es")
block_svg_es, block_legend_es = make_block_map("es")

es_findings_body = f"""
<h1>Hallazgos</h1>
<p class="lede">Al menos 1,259 hogares de la Ciudad de Decatur que ya califican, según sus propios registros, pagan unos $1.2 millones al año más de impuestos a la propiedad de lo necesario.</p>
<p>El problema casi nunca es quién califica. Es un sistema que obliga a los propietarios a reclamar el alivio, a reclamarlo dos veces en dos oficinas y a reclamarlo de nuevo con cada edad clave.</p>

<h2>Las exenciones que faltan, según los registros</h2>
<p>Estas viviendas ya tienen la prueba registrada en una oficina. Falta la exención correspondiente de la otra oficina.</p>
{gap_table_es}
<p class="small muted"><span class="hl-key"></span> La fila resaltada es la que más pesa: cerca de dos tercios de todo el alivio que se pierde. Algunas viviendas tienen más de una exención que falta. Las cifras del Condado se calculan a partir de lo que reciben quienes solicitaron recientemente y se muestran como un rango. Otras 225 viviendas donde consta un propietario de 65 años o más podrían calificar para una exención escolar de la Ciudad según sus ingresos; no se incluyen en el total.</p>

<h2>Dónde falla: dos oficinas, dos formularios</h2>
<p>Casi todos los que compraron hace décadas tienen la exención homestead en ambas oficinas. Los compradores recientes a menudo la solicitan con DeKalb al cerrar la compra y nunca presentan el formulario aparte de la Ciudad, y eso no se corrige solo.</p>
<figure class="chart">{chart_cohort_es}
<figcaption>Porcentaje de viviendas que probablemente habitan sus dueños con exención homestead tanto en la Ciudad de Decatur como en el Condado de DeKalb, según el año de compra. Se resaltan los compradores recientes. Facturas de impuestos 2026 de la Ciudad de Decatur y registros del Condado de DeKalb.</figcaption></figure>

<h2>Dónde falla: los límites de ingresos</h2>
<p>Cuando una exención de la Ciudad depende solo de la edad, casi todas las personas mayores cuyos registros de DeKalb muestran su edad también la reclaman. Cuando la Ciudad agrega un límite de ingresos con otra definición de ingresos, la participación baja a cerca de la mitad.</p>
<figure class="chart">{chart_takeup_es}
<figcaption>Porcentaje de hogares que reclaman cada exención de la Ciudad, entre los hogares cuya exención de DeKalb ya muestra que cumplen el requisito de edad (y, para la GH-3, de ingresos). Año fiscal 2026.</figcaption></figure>

<h2>Pasa en todos los vecindarios</h2>
<p>En casi todas partes de la ciudad, cerca de una de cada cinco viviendas ya tiene una exención que falta comprobada. No es un problema de un solo vecindario.</p>
<figure class="map">{block_svg_es}{block_legend_es}
<figcaption>Porcentaje de viviendas del análisis con una exención que falta comprobada, por manzana censal de 2020, dentro de los límites de la ciudad. Las manzanas con menos de 10 viviendas aparecen rayadas, y el mapa muestra rangos, no cifras exactas. Las zonas sin color no tienen viviendas en el análisis.</figcaption></figure>

<h2>Personas mayores que nunca han presentado una solicitud</h2>
<p>Los datos del Censo sugieren que unos {round(unf['median'], -1):.0f} hogares propietarios encabezados por una persona mayor en Decatur no tienen ninguna exención para mayores (rango del 90%: {round(unf['low_5pct'], -1):.0f} a {round(unf['high_95pct'], -1):.0f}). Los registros públicos no pueden mostrar quiénes son, porque la única información de edad que contienen viene de exenciones ya presentadas. Por eso la revisión de direcciones muestra todas las exenciones para mayores, para que cada propietario vea cuáles no ha reclamado.</p>

<h2>Qué lo resolvería</h2>
<ol class="steps">
  <li><strong>Una sola exención homestead, reconocida por ambas oficinas.</strong> La Ciudad podría aceptar las aprobaciones de DeKalb, o ambas podrían usar una sola solicitud.</li>
  <li><strong>Conceder las exenciones que dependen solo de la edad cuando la edad ya está comprobada.</strong> La GH-2 y la exención escolar para mayores de 70 no tienen límite de ingresos.</li>
  <li><strong>Aceptar la determinación de ingresos de DeKalb.</strong> Una exención de DeKalb para mayores con un tope de $37,500 de ingreso neto de Georgia ya cumple el límite de la GH-3 de la Ciudad.</li>
  <li><strong>Llegar a los compradores al cerrar la compra</strong> con un solo aviso que explique ambas solicitudes y ambas fechas límite.</li>
  <li><strong>Contactar a los hogares a los que les falta una exención comprobada,</strong> sin dar a entender que alguien hizo algo mal.</li>
</ol>
<p class="small muted">A nadie se le está cobrando por error: ambas oficinas aplican las exenciones registradas, como exige la ley. Una mayor participación traslada parte del impuesto a otros propietarios en lugar de reducir la recaudación dólar por dólar. Vea <a href="datos.html">Sobre los datos</a> para conocer los métodos y sus límites.</p>
"""
page("hallazgos.html", "Hallazgos · Senior Homestead Check", es_findings_body, lang="es", alt="findings.html",
     desc="Cuántos propietarios de la Ciudad de Decatur no reciben exenciones de impuestos a la propiedad que les corresponden, y por qué.")

# ------------------------------------------------------------------ Spanish about (datos.html)
es_about_body = """
<h1>Sobre los datos</h1>
<p class="lede">Todo lo que aparece en este sitio proviene de registros públicos de propiedades y del Censo de EE. UU.</p>

<h2>Fuentes</h2>
<ul>
  <li>Facturas de impuestos 2026 de la Ciudad de Decatur, que muestran cada exención como una línea aparte (<a href="https://www.decaturgatax.com/taxes#/WildfireSearch" lang="en">búsqueda de impuestos de la Ciudad</a>, en inglés).</li>
  <li>Registros de exenciones y de propiedad del Recaudador de Impuestos del Condado de DeKalb (<a href="https://dekalbtaxga.gov/" lang="en">dekalbtaxga.gov</a>) y registros de tasación de propiedades de DeKalb.</li>
  <li>Mapas de parcelas de la Ciudad de Decatur y del Condado de DeKalb (<a href="https://dcgis-dekalbgis.hub.arcgis.com/" lang="en">datos abiertos de GIS de DeKalb</a>).</li>
  <li>Oficina del Censo de EE. UU., Encuesta sobre la Comunidad Estadounidense 2020–2024 y Censo 2020 (<a href="https://data.census.gov/">data.census.gov</a>).</li>
</ul>
<p>Los registros se recopilaron en septiembre y octubre de 2026 para unas 7,700 parcelas residenciales de la Ciudad de Decatur, con un proceso lento y limitado para no sobrecargar los sitios públicos.</p>

<h2>Cómo se encuentran las exenciones que faltan</h2>
<p>Una exención que falta se cuenta como <strong>comprobada</strong> solo cuando los registros de una oficina ya muestran que el propietario cumple el requisito de una exención que la otra oficina no ha aplicado. Por ejemplo, DeKalb tiene registrada una exención homestead pero la factura de la Ciudad no tiene ninguna. Las edades se toman solo de exenciones ya registradas y nunca se adivinan para ninguna persona.</p>
<p>El ahorro en la Ciudad se calcula multiplicando cada exención que falta por las tasas de impuestos de la Ciudad de 2026; este método coincide con los créditos del 99.8% de las facturas de 2026. El ahorro en el Condado se estima a partir de lo que reciben quienes solicitaron recientemente y resulta cerca de un 7% alto en general, por eso se muestra como un rango.</p>

<h2>Límites</h2>
<ul>
  <li>Los registros públicos no muestran los ingresos ni la edad exacta, así que las exenciones con límite de ingresos solo pueden marcarse como "vale la pena revisar".</li>
  <li>Algunas viviendas podrían no ser la residencia principal del propietario, algo que exige toda exención homestead.</li>
  <li>Los registros cambian. Una solicitud presentada después de septiembre de 2026 no aparecerá aquí hasta la próxima actualización.</li>
</ul>

<h2>Privacidad</h2>
<ul>
  <li>La revisión de direcciones muestra solo lo que ya es público para esa dirección, y nunca muestra el nombre de los propietarios.</li>
  <li>Las direcciones que se escriben en la revisión no se guardan. Para evitar abusos, el sitio guarda durante dos días un código codificado por visitante, que cambia cada día, para limitar cuántas búsquedas puede hacer una persona.</li>
  <li>La lista y el mapa de contacto para organizaciones aliadas, que incluyen nombres y direcciones postales de registros públicos y muestran viviendas individuales, solo están disponibles para organizaciones aprobadas después de iniciar sesión, y se registra cada consulta. Los mapas públicos de este sitio solo muestran rangos para zonas de 10 viviendas o más.</li>
</ul>

<h2 id="errores">Reportar un error</h2>
<p>Si la revisión muestra algo incorrecto sobre su vivienda, el registro oficial es lo que tiene cada oficina: llame a la Ciudad al <a href="tel:+14043704100">404-370-4100</a> o a DeKalb al <a href="tel:+14042984000">404-298-4000</a>. Para avisarnos de un error en este sitio, comuníquese con el equipo del proyecto a través de la persona que le compartió el sitio.</p>
"""
page("datos.html", "Sobre los datos · Senior Homestead Check", es_about_body, lang="es", alt="about.html",
     desc="De dónde vienen los datos de este sitio, cómo se encuentran las exenciones que faltan y cómo se protege la privacidad.")

(OUT / "robots.txt").write_text("User-agent: *\nDisallow: /partners.html\n")
print("built", sorted(p.name for p in OUT.iterdir()))
