"""Render reports/analysis.json (analysis.analyze) as one self-contained HTML audit report.

    python -m analysis.report_html reports/analysis.json reports/dda-audit.html

Plain HTML and CSS with inline SVG charts. GSAP 3.12.5 and ScrollTrigger (analysis/vendor/, inlined, so the file
works offline) add a hero intro, counting numbers, bars that grow on scroll and section reveals. Without
JavaScript, or with "reduce motion" set, the page is complete and static. Light and dark themes follow the system.

The text uses ASD-STE100 Simplified Technical English. It names no private individuals or firms.
"""
import html
import json
import os
import sys

E = html.escape
HERE = os.path.dirname(os.path.abspath(__file__))


def n(x):
    try:
        return f"{int(round(float(x or 0))):,}"
    except (TypeError, ValueError):
        return str(x)


def pct(a, b):
    return f"{(a or 0) * 100 / b:.1f}%" if b else "–"


def gb(b):
    return f"{(b or 0) / 1e9:.1f} GB"


def first(a, key, default=None):
    rows = a.get(key) or []
    return rows[0] if rows else (default if default is not None else [])


# ---------------------------------------------------------------- charts (inline SVG, one series each)

def hbar(rows, label_w=230, fmt=n, note=""):
    rows = [(str(a), float(b or 0)) for a, b in rows]
    if not rows:
        return '<p class="muted">No data yet.</p>'
    mx = max([b for _, b in rows] + [1])
    bh, gap, w = 22, 9, 680
    plot = w - label_w - 80
    h = len(rows) * (bh + gap) + 4
    out = [f'<svg class="chart hbar" viewBox="0 0 {w} {h}" role="img" aria-label="{E(note)}">']
    for i, (lab, v) in enumerate(rows):
        y = i * (bh + gap) + 2
        bw = max(2, plot * v / mx)
        out.append(f'<g class="mark"><title>{E(lab)}: {fmt(v)}</title>'
                   f'<text x="{label_w - 12}" y="{y + bh / 2 + 4}" text-anchor="end" class="lab">{E(lab[:40])}</text>'
                   f'<rect x="{label_w}" y="{y}" width="{plot}" height="{bh}" rx="4" class="track"/>'
                   f'<rect x="{label_w}" y="{y}" width="{bw:.1f}" height="{bh}" rx="4" class="bar"/>'
                   f'<text x="{label_w + bw + 8}" y="{y + bh / 2 + 4}" class="val">{fmt(v)}</text></g>')
    out.append("</svg>")
    return "".join(out)


def vbar(rows, fmt=n, note="", every=1, h=240, highlight=()):
    rows = [(str(a), float(b or 0)) for a, b in rows]
    if not rows:
        return '<p class="muted">No data yet.</p>'
    mx = max([b for _, b in rows] + [1])
    w, left, bottom, top = 680, 48, 28, 14
    plot_w, plot_h = w - left - 8, h - bottom - top
    step = plot_w / max(1, len(rows))
    bw = max(3, step - 4)
    out = [f'<svg class="chart vbar" viewBox="0 0 {w} {h}" role="img" aria-label="{E(note)}">']
    for k in range(5):
        t = mx * k / 4
        y = top + plot_h - plot_h * t / mx
        out.append(f'<line x1="{left}" x2="{w - 8}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>'
                   f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" class="tick">{fmt(t)}</text>')
    for i, (lab, v) in enumerate(rows):
        x = left + i * step + 2
        bh_ = max(plot_h * v / mx, 1)
        y = top + plot_h - bh_
        cls = "bar hi" if lab in highlight else "bar"
        out.append(f'<g class="mark"><title>{E(lab)}: {fmt(v)}</title>'
                   f'<rect x="{x:.1f}" y="{top}" width="{step:.1f}" height="{plot_h}" class="hit"/>'
                   f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh_:.1f}" rx="{min(4, bw / 2):.1f}" class="{cls}"/></g>')
        if i % every == 0 or i == len(rows) - 1:
            out.append(f'<text x="{x + bw / 2:.1f}" y="{h - 9}" text-anchor="middle" class="tick">{E(lab)}</text>')
    out.append(f'<line x1="{left}" x2="{w - 8}" y1="{top + plot_h}" y2="{top + plot_h}" class="axis"/></svg>')
    return "".join(out)


def table(head, rows, num_cols=()):
    if not rows:
        return '<p class="muted">No data yet.</p>'
    th = "".join(f'<th class="{"num" if i in num_cols else ""}">{E(h)}</th>' for i, h in enumerate(head))
    body = "".join("<tr>" + "".join(
        f'<td class="{"num" if i in num_cols else ""}">{E(n(c) if i in num_cols and isinstance(c, (int, float)) else str(c if c is not None else "–"))}</td>'
        for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<div class="tw reveal"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def fig(caption, svg):
    return f'<figure class="reveal"><figcaption>{caption}</figcaption>{svg}</figure>'


def flag(kind, text):
    return f'<div class="flag reveal"><span class="tag">{E(kind)}</span><p>{text}</p></div>'


def tile(value, label, raw=None):
    data = f' data-count="{raw}"' if raw is not None else ""
    return f'<div class="tile"><b{data}>{value}</b><span>{label}</span></div>'


# ---------------------------------------------------------------- page

CSS = """
:root{
  /* Layout: a reading column with a sticky contents rail on wide screens; figures use the column width */
  --bg:#f4f6f8; --surface:#ffffff; --ink:#14181c; --ink-2:#47515a; --muted:#6b7680; --rule:#dce1e6;
  --accent:#1f5fbf; --accent-soft:#e6eefb; --bar:#2a78d6; --track:#eef1f4; --hi:#d9822b;
  --flag:#a8521d; --flag-bg:#fbf0e7; --good:#1f7a4d;
  --display:"Source Serif 4", "Iowan Old Style", Georgia, serif;
  --body:"Public Sans", "Segoe UI", system-ui, -apple-system, sans-serif;
  --mono:"IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
  color-scheme: light;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#101316; --surface:#181c20; --ink:#eef1f3; --ink-2:#bec6cd; --muted:#8e99a3; --rule:#2b3238;
  --accent:#6ea8ff; --accent-soft:#1b2a40; --bar:#3987e5; --track:#22282e; --hi:#e59a4c;
  --flag:#efa06a; --flag-bg:#2a2019; --good:#5cc08b; color-scheme: dark}}
:root[data-theme="dark"]{
  --bg:#101316; --surface:#181c20; --ink:#eef1f3; --ink-2:#bec6cd; --muted:#8e99a3; --rule:#2b3238;
  --accent:#6ea8ff; --accent-soft:#1b2a40; --bar:#3987e5; --track:#22282e; --hi:#e59a4c;
  --flag:#efa06a; --flag-bg:#2a2019; --good:#5cc08b; color-scheme: dark}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font:15.5px/1.65 var(--body);-webkit-font-smoothing:antialiased}
.progress{position:fixed;inset:0 0 auto 0;height:3px;background:var(--accent);transform-origin:0 50%;transform:scaleX(0);z-index:20}
.top{position:sticky;top:0;z-index:10;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(8px);
  border-bottom:1px solid var(--rule)}
.top .in{max-width:1180px;margin:0 auto;padding:10px max(16px,env(safe-area-inset-right,0px)) 10px max(16px,env(safe-area-inset-left,0px));
  display:flex;gap:16px;align-items:center;justify-content:space-between;font:500 12px/1 var(--mono);letter-spacing:.06em;
  text-transform:uppercase;color:var(--muted)}
.top b{color:var(--ink);font-weight:600}
.layout{max-width:1180px;margin:0 auto;display:grid;grid-template-columns:1fr;gap:40px;
  padding:32px max(16px,env(safe-area-inset-right,0px)) 80px max(16px,env(safe-area-inset-left,0px))}
@media (min-width:1100px){.layout{grid-template-columns:230px minmax(0,1fr)}}
.toc{display:none}
@media (min-width:1100px){.toc{display:block;position:sticky;top:64px;align-self:start;max-height:calc(100vh - 80px);overflow:auto;
  font-size:13px;border-left:1px solid var(--rule);padding-left:14px}}
.toc a{display:block;color:var(--muted);text-decoration:none;padding:4px 0 4px 10px;margin-left:-15px;border-left:2px solid transparent}
.toc a:hover{color:var(--ink)}
.toc a.active{color:var(--accent);border-left-color:var(--accent);font-weight:600}
main{min-width:0;max-width:880px}
h1,h2,h3{font-family:var(--display);text-wrap:balance;line-height:1.18;margin:0}
h1{font-size:clamp(2rem,4.2vw,3rem);font-weight:600;letter-spacing:-.01em}
h2{font-size:1.6rem;font-weight:600;margin-top:64px;display:flex;gap:12px;align-items:baseline}
h2 .no{font:600 13px/1 var(--mono);color:var(--accent);background:var(--accent-soft);padding:6px 8px;border-radius:6px}
h3{font:600 1rem/1.3 var(--body);margin-top:26px}
p,li{color:var(--ink-2);max-width:70ch} p{margin:12px 0}
strong{color:var(--ink)}
.eyebrow{font:500 12px/1 var(--mono);letter-spacing:.09em;text-transform:uppercase;color:var(--muted)}
.lede{font-size:1.1rem;color:var(--ink-2)}
.hero{padding:8px 0 4px}
.tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:26px 0 8px}
@media (max-width:820px){.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}}
.tile{background:var(--surface);border:1px solid var(--rule);border-radius:12px;padding:16px 16px 14px;min-width:0}
.tile b{display:block;font:600 1.75rem/1.05 var(--display);font-variant-numeric:tabular-nums;color:var(--ink)}
.tile span{display:block;margin-top:6px;font-size:.82rem;color:var(--muted);line-height:1.35}
.findings{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-top:22px}
@media (max-width:820px){.findings{grid-template-columns:1fr}}
.finding{display:block;text-decoration:none;background:var(--surface);border:1px solid var(--rule);border-radius:12px;padding:16px 18px;
  min-width:0;transition:border-color .2s}
.finding:hover{border-color:var(--accent)}
.finding .k{font:600 1.5rem/1.1 var(--display);color:var(--accent)}
.finding h3{margin:6px 0 4px;font-size:.98rem;color:var(--ink)}
.finding p{margin:0;font-size:.9rem}
figure{margin:18px 0 10px;background:var(--surface);border:1px solid var(--rule);border-radius:12px;padding:16px 16px 10px;min-width:0}
figcaption{font-size:.86rem;color:var(--muted);margin-bottom:10px}
.chart{width:100%;height:auto;display:block;overflow:visible}
.chart .bar{fill:var(--bar)} .chart .bar.hi{fill:var(--hi)} .chart .track{fill:var(--track)} .chart .hit{fill:transparent}
.chart .mark:hover .bar{opacity:.8}
.chart .lab,.chart .val,.chart .tick{fill:var(--ink-2);font:12px var(--body);font-variant-numeric:tabular-nums}
.chart .val{fill:var(--ink);font-weight:600} .chart .tick{fill:var(--muted);font-size:11px}
.chart .grid{stroke:var(--rule);stroke-width:1} .chart .axis{stroke:var(--muted);stroke-width:1}
.flag{display:flex;gap:12px;align-items:flex-start;background:var(--flag-bg);border:1px solid color-mix(in srgb,var(--flag) 35%,transparent);
  border-radius:12px;padding:14px 16px;margin:16px 0}
.flag p{margin:0;color:var(--ink)}
.tag{flex:none;font:600 11px/1 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--flag);
  border:1px solid currentColor;border-radius:999px;padding:5px 8px;margin-top:2px}
.tw{overflow-x:auto;margin:14px 0;background:var(--surface);border:1px solid var(--rule);border-radius:12px}
table{border-collapse:collapse;width:100%;font-size:.88rem}
th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--rule);vertical-align:top}
tr:last-child td{border-bottom:0}
th{font-weight:600;color:var(--muted);font-size:.74rem;text-transform:uppercase;letter-spacing:.05em;background:color-mix(in srgb,var(--track) 60%,transparent)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
code{font:12.5px var(--mono);background:var(--track);padding:1px 6px;border-radius:5px;word-break:break-word}
ul{padding-left:20px} li{margin:6px 0}
.muted{color:var(--muted)}
.foot{margin-top:56px;padding-top:18px;border-top:1px solid var(--rule);font-size:.84rem;color:var(--muted)}
a{color:var(--accent)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}
.anim .tile,.anim .finding,.anim .bar{will-change:transform}
"""

JS = r"""
(function () {
  if (!window.gsap || !window.ScrollTrigger) return;          // the page is complete without animation
  gsap.registerPlugin(ScrollTrigger);
  var mm = gsap.matchMedia();
  mm.add({ motion: "(prefers-reduced-motion: no-preference)" }, function () {
    document.documentElement.classList.add("anim");
    gsap.defaults({ ease: "power3.out", duration: 0.8 });

    // reading progress
    gsap.to(".progress", { scaleX: 1, ease: "none", scrollTrigger: { start: 0, end: "max", scrub: 0.3 } });

    // hero: one sequence
    var tl = gsap.timeline();
    tl.from(".hero .eyebrow", { y: 12, autoAlpha: 0, duration: 0.5 })
      .from(".hero h1", { y: 24, autoAlpha: 0 }, "-=0.25")
      .from(".hero .lede", { y: 16, autoAlpha: 0 }, "-=0.5")
      .from(".hero .tile", { y: 22, autoAlpha: 0, stagger: 0.06 }, "-=0.45");

    // counting numbers (the final text is already in the HTML)
    gsap.utils.toArray("[data-count]").forEach(function (el) {
      var end = parseFloat(el.getAttribute("data-count")), text = el.textContent, o = { v: 0 };
      if (!isFinite(end)) return;
      tl.to(o, { v: end, duration: 1.4, ease: "power2.out",
        onUpdate: function () { el.textContent = Math.round(o.v).toLocaleString("en-IN"); },
        onComplete: function () { el.textContent = text; } }, 0.35);
    });

    // key findings and the rest: reveal once, in batches
    gsap.set(".finding, .reveal", { autoAlpha: 0, y: 26 });
    ScrollTrigger.batch(".finding, .reveal", {
      start: "top 88%", once: true,
      onEnter: function (els) { gsap.to(els, { autoAlpha: 1, y: 0, stagger: 0.08, overwrite: true }); }
    });

    // bars grow when their chart comes into view
    gsap.utils.toArray(".hbar").forEach(function (svg) {
      gsap.from(svg.querySelectorAll(".bar"), { scaleX: 0, transformOrigin: "0% 50%", stagger: 0.04, duration: 0.9,
        scrollTrigger: { trigger: svg, start: "top 85%", once: true } });
      gsap.from(svg.querySelectorAll(".val"), { autoAlpha: 0, x: -8, stagger: 0.04, delay: 0.3,
        scrollTrigger: { trigger: svg, start: "top 85%", once: true } });
    });
    gsap.utils.toArray(".vbar").forEach(function (svg) {
      gsap.from(svg.querySelectorAll(".bar"), { scaleY: 0, transformOrigin: "50% 100%", stagger: 0.025, duration: 0.8,
        scrollTrigger: { trigger: svg, start: "top 85%", once: true } });
    });
  });

  // contents rail: mark the section in view (also with reduced motion: no animation, only a class)
  gsap.utils.toArray("main section[id]").forEach(function (sec) {
    var link = document.querySelector('.toc a[href="#' + sec.id + '"]');
    if (!link) return;
    ScrollTrigger.create({ trigger: sec, start: "top 40%", end: "bottom 40%",
      toggleClass: { targets: link, className: "active" } });
  });
})();
"""


def vendor(name):
    p = os.path.join(HERE, "vendor", name)
    return open(p).read() if os.path.exists(p) else ""


def build(a):
    st = dict((r[0], r[1]) for r in a.get("doc_status", []))
    docs_total = sum(st.values())
    stored_n, stored_b, median_b = (first(a, "doc_bytes_stored") + [0, 0, 0])[:3]
    lang = dict((r[0], r[1]) for r in a.get("pages_lang", []))
    pages_total = sum(lang.values())
    scope = a.get("scope", {})
    col = dict((str(r[0]), (r[1], r[2])) for r in a.get("colonies", []))
    cstat = a.get("colony_status", [])
    br = first(a, "boundary_rows", [0] * 7)
    dup = first(a, "duplicates", [0] * 4)
    tt = first(a, "tenders_total", [0] * 4)
    wa = first(a, "work_awards", [0] * 3)
    ef = first(a, "enlistment_files", [0] * 5)
    lr = first(a, "listing_rows", [0] * 4)
    deb = dict((r[0], r[1]) for r in a.get("debarments", []))
    broken = st.get("broken", 0)
    hp = first(a, "hindi_parity", [0, 0])
    alt = first(a, "award_letter_text", [0] * 6)
    eps = dict((r[0], r[1]) for r in a.get("ep_stage", []))
    ep_total = sum(eps.values())
    epl = first(a, "ep_links", [0, 0, 0, 0])
    ar = first(a, "ep_award_ratio", [0, 0, 0])
    alst = dict((r[0], r[1]) for r in a.get("ep_award_letter_stage", []))
    aw = first(a, "award_summary", [0] * 10)
    dt = first(a, "doc_text", [0, 0, 0, 0])
    pc = a.get("pdf_census") or {}
    gp = first(a, "greens_parks", [0] * 8)
    gdash = dict((r[0], r[1]) for r in a.get("greens_dashboard", []))
    gother = {r[0]: r for r in a.get("greens_other", [])}
    stfk = {r[0]: r for r in a.get("stf_kinds", [])}
    watch = a.get("watch") or []
    gen = E(a.get("_generated_at", "")[:10])
    final_pub = sum(r[1] for r in cstat if r[0] == "final boundary published")
    ccount = col.get("1731", (0, 0))[0]
    award_letter_tenders = sum(alst.values())

    S = []
    toc = [("findings", "Key findings"), ("verification", "1. Verification"), ("colonies", "2. Unauthorised colonies"),
           ("tenders", "3. Tenders and awards"), ("eprocure", "4. DDA on eprocure"), ("awards", "5. Award values"),
           ("history", "6. Historical records"), ("documents", "7. Documents"), ("text", "8. Text in documents"),
           ("quality", "9. Site quality and privacy"), ("stf", "10. Special Task Force"), ("greens", "11. DDA Greens"),
           ("watch", "12. Weekly watch"), ("next", "13. Next steps"), ("use", "14. How to use the data"),
           ("limits", "15. Limits")]
    S.append(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>DDA Website Data Audit</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Public+Sans:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,600&display=swap">
<style>{CSS}</style></head><body>
<div class="progress" aria-hidden="true"></div>
<header class="top"><div class="in"><span><b>DDA website data audit</b> &middot; s1d labs</span><span>family dda &middot; {gen}</span></div></header>
<div class="layout">
<nav class="toc" aria-label="Contents">{"".join(f'<a href="#{i}">{E(t)}</a>' for i, t in toc)}</nav>
<main>
<section class="hero">
<p class="eyebrow">Delhi Development Authority &middot; dda.gov.in &middot; scope, verification, findings</p>
<h1>DDA website data audit</h1>
<p class="lede">This report gives the measured scope of the public website of the Delhi Development Authority, the checks
of the scraped data, and the findings from the data. It uses ASD-STE100 Simplified Technical English. It names no private
individuals or firms.</p>
<div class="tiles">
{tile(n(scope.get('pages', pages_total)), f"unique HTML pages found ({n(pages_total)} scraped)", scope.get('pages', pages_total))}
{tile(n(scope.get('documents', docs_total)), "unique document links found", scope.get('documents', docs_total))}
{tile(n(stored_n), f"documents stored ({gb(stored_b)})", stored_n)}
{tile(n(lr[0]), "listing rows (title, date, file)", lr[0])}
{tile(n(ccount), "unauthorised colonies as a table", ccount)}
{tile(n(ep_total), "DDA tenders on eprocure, linked", ep_total)}
{tile(n(dt[0]), f"PDF files read for text ({n(dt[1])} with text)", dt[0])}
{tile(n(broken), "document links that return HTTP 404", broken)}
</div>
<p class="muted">The scrape is complete: every page and every document that the site delivers is stored. All counts come from
the workspace database (schema <code>dda</code>) on {gen}.</p>
</section>
""")

    # key findings
    cards = [
        ("eprocure", pct(eps.get("awarded", 0), ep_total), "Awards are not on the central portal",
         f"Only {n(eps.get('awarded', 0))} of {n(ep_total)} DDA tenders reach &ldquo;awarded&rdquo; on eprocure. "
         f"{n(alst.get('in evaluation', 0))} of {n(award_letter_tenders)} tenders with an award letter on the DDA site stay &ldquo;in evaluation&rdquo; there."),
        ("colonies", f"{n(final_pub)} / {n(ccount)}", "Colony boundaries stopped in 2020",
         f"Final boundary maps exist for {n(final_pub)} of {n(ccount)} unauthorised colonies. The last upload is {E(str(br[4]))}."),
        ("awards", f"{aw[4] or 0:.2f}&times;", "Awards far below the estimate",
         f"The median award is {aw[4] or 0:.2f} times the estimated cost in {n(aw[3])} award letters. "
         f"{n(aw[5])} of them are below 70% of the estimate."),
        ("quality", n(ef[1] + ef[2]), "Contractor documents are public",
         f"{n(ef[1])} bank solvency certificates and {n(ef[2])} application forms are on the site. "
         f"{n(alt[1])} award letters print a bank account number."),
        ("text", pct(dt[1], dt[0]), "Half of the PDFs are scans",
         f"{n(dt[1])} of {n(dt[0])} PDF files have a text layer and are searchable. The rest need OCR."),
        ("greens", pct((gother.get('Shrub') or [0, 0, 0])[1], (gother.get('Shrub') or [0, 0, 1])[2]), "Plantation species not recorded",
         f"In DDA Greens, the species of {n((gother.get('Shrub') or [0, 0])[1])} of {n((gother.get('Shrub') or [0, 0, 0])[2])} "
         f"planted shrubs is &ldquo;Other&rdquo;."),
    ]
    S.append('<section id="findings"><h2><span class="no">&#9733;</span>Key findings</h2>'
             '<p>These are indicators, not findings of wrongdoing. Each card links to its section.</p><div class="findings">'
             + "".join(f'<a class="finding" href="#{i}"><div class="k">{k}</div><h3>{E(t)}</h3><p>{d}</p></a>'
                       for i, k, t, d in cards) + "</div></section>")

    # 1 verification
    S.append(f"""<section id="verification"><h2><span class="no">01</span>Verification of the scrape</h2>
<p class="reveal">We checked the stored records against the site structure, the bucket and the hub. The checks found these defects.
We fixed all of them. The table gives each defect and its effect.</p>
{table(["Check", "Result", "Action"], [
        ["One spelling per URL", "221 pages were scraped two times (http:// and https://). 27 documents had two spellings (space and %20).", "One canonical URL."],
        ["HTML entities in links", "157 document links were lost. The crawler read '&amp;' in a file name as text.", "Links are unescaped. The repair pass added the files."],
        ["Pager coverage", "395 listing pages were not reached, for example 191 of 285 pages of the tender archive.", "Every page 1 to N of a listing is queued. The repair pass added 397 pages and 3,988 documents."],
        ["Tender gap", "The first scrape showed almost no tenders for 2022-23 to 2024-25. It was the pager defect above.", "The full archive gives 512 tender rows for 2022-23 alone."],
        ["Failed downloads", f"{n(broken)} documents return HTTP 404 on the site.", "One broken-link record each. No retries."],
        ["Files never delivered", "The server cuts one 40 MB PDF at the same byte on every try. The pool ran about 38 runner jobs an hour to retry 3 files.", "After 10 tries a file is recorded as unretrievable. The last 2 items were closed on 7 Nov 2026. No retries since."],
        ["Large downloads", "A dropped connection during a 40 MB file stopped a worker process.", "The item fails and the worker continues."],
        ["Dates", "Two-digit years became 20xx (1986 was stored as 2086).", "Two-digit years resolve to the past."],
        ["CI", "One check run failed: a test imported psycopg2, which CI does not install.", "Lazy imports. CI is green."],
        ["Bucket", f"HEAD check of all {n(stored_n)} stored files.", "All present. All sizes match."],
    ])}</section>""")

    # 2 colonies
    S.append(f"""<section id="colonies"><h2><span class="no">02</span>Unauthorised colonies (PM-UDAY)</h2>
<p class="reveal">The site publishes the list of {n(ccount)} unauthorised colonies (excluding affluent colonies) and a list of
{n(col.get('affluent', (0, 0))[0])} colonies inhabited by the affluent section of society, as text PDF files. We extracted all
rows without OCR (<code>dda.unauthorised_colonies</code>, <code>data/unauthorised_colonies.csv</code>). The page
<code>/delineated-boundary</code> holds {n(br[0])} boundary rows. We joined both on the registration number.</p>
{fig("Boundary status of the 1,731 colonies (number of colonies)", hbar([(r[0], r[1]) for r in cstat], note="Boundary status"))}
<ul class="reveal">
<li>{n(br[5])} boundary rows say the boundary can not be delineated as per the SOP. {n(br[6])} of these say the shapefile of the colony is not available.</li>
<li>All {n(br[2])} final boundary maps have an upload date between {E(str(br[3]))} and {E(str(br[4]))}.</li>
<li>{n(first(a, 'boundary_not_in_list', [0])[0])} boundary rows have a registration number that is not in the list of 1,731 colonies.
The list has {n(first(a, 'colony_dup_reg', [0])[0])} registration number that occurs two times.</li>
</ul>
{flag("Indicator", f"About 1 colony in 4 has no final boundary on the site ({n(ccount - final_pub)} of {n(ccount)}). The final boundary is the base for the PM-UDAY ownership process. The public table shows no change since 2020.")}
</section>""")

    # 3 tenders
    have = dict((r[0], r[1]) for r in a.get("tenders_fy", []))
    fy = [(f"{y}-{(y + 1) % 100:02d}", have.get(f"{y}-{(y + 1) % 100:02d}", 0)) for y in range(2015, 2027)]
    S.append(f"""<section id="tenders"><h2><span class="no">03</span>Tenders, work awards and debarments</h2>
<p class="reveal">The tender pages and the tender archive give {n(tt[0])} tender rows with {n(tt[1])} different NIT numbers.
We read the office code and the financial year from each NIT number (for example <code>07/EE/HCD-10/DDA/2026-27</code>).</p>
{fig("Tender rows on the DDA site by financial year (from the NIT number)", vbar([(k[2:], v) for k, v in fy], note="Tender rows by year", highlight=("22-23",)))}
<ul class="reveal">
<li>{n(tt[3])} tender rows ({pct(tt[3], tt[0])}) are marked &ldquo;re-invited&rdquo;: the first call had no valid bid.</li>
<li>The site has {n(wa[0])} work award letters. {n(wa[1])} of them give the NIT number of the tender.</li>
<li>The site has {n(deb.get('order', 0))} debarment or suspension orders and {n(deb.get('withdrawal', 0))} withdrawals of such orders.</li>
</ul>
<h3>Offices with the most tender rows</h3>
{table(["Office code (from the NIT number)", "Tender rows"], [(r[0], r[1]) for r in a.get("tender_offices", [])[:10]], num_cols=(1,))}
</section>""")

    # 4 eprocure
    epy = [(str(r[0]), r[1]) for r in a.get("ep_years", []) if r[0] and r[0] <= 2026]
    single = [(str(r[0]), r[3] * 100.0 / r[4]) for r in a.get("ep_years", []) if r[0] and r[4]]
    lm = dict((r[0], r[1]) for r in a.get("link_match", []))
    S.append(f"""<section id="eprocure"><h2><span class="no">04</span>DDA on the central e-procurement portal</h2>
<p class="reveal">DDA runs its tenders on <code>eprocure.gov.in</code>. The team database holds {n(ep_total)} DDA tenders from that
portal, with value, EMD, bid counts and stage. The DDA site keeps the notices and the award letters. Both use the same NIT
reference, so we linked them by number, office and financial year (<code>analysis.link_eprocure</code>). Office names are
written in many ways (&ldquo;Hort. 3&rdquo;, &ldquo;HD-III&rdquo;, &ldquo;EE(E)/ELD-10&rdquo;, zone parts); the link uses one spelling.</p>
<ul class="reveal">
<li><strong>{n(epl[1])} of {n(epl[0])}</strong> tender rows on the DDA site ({pct(epl[1], epl[0])}) link to an eprocure tender:
{n(lm.get('key', 0))} by the key and {n(lm.get('office token', 0))} by an office token (&ldquo;NMD-2(ND-3)&rdquo; = &ldquo;EE/NMD-2&rdquo;).</li>
<li>{n(epl[3])} of {n(epl[2])} award letters with an NIT number link to an eprocure tender.</li>
</ul>
{table(["Site tender rows without a link", "Rows"], [(r[0], r[1]) for r in a.get("unlinked_reasons", [])], num_cols=(1,))}
{fig("DDA tenders published on eprocure by year", vbar(epy, note="DDA tenders by year", every=2))}
{fig("Share of DDA tenders with exactly one bid, by year (% of tenders with bids)", vbar(single, fmt=lambda v: f"{v:.1f}%", note="Single-bid share", every=2, h=200))}
{flag("Indicator", f"Only {n(eps.get('awarded', 0))} of {n(ep_total)} DDA tenders ({pct(eps.get('awarded', 0), ep_total)}) reach the stage &ldquo;awarded&rdquo; on eprocure; {n(eps.get('in evaluation', 0))} ({pct(eps.get('in evaluation', 0), ep_total)}) stay &ldquo;in evaluation&rdquo;. Of {n(award_letter_tenders)} eprocure tenders with an award letter on the DDA site, {n(alst.get('in evaluation', 0))} still show &ldquo;in evaluation&rdquo;. {n(alt[2])} award letters print the eprocure Tender ID itself; {n(alt[4])} of these tenders show &ldquo;in evaluation&rdquo;. DDA publishes the award on its own site, not on the portal.")}
<h3>Awarded share of the largest buyers on eprocure</h3>
{table(["Organisation code", "Tenders", "Awarded on eprocure"], [(r[0], r[1], f"{r[2]:.1f}%") for r in a.get("ep_peer_awarded", [])], num_cols=(1,))}
<p class="reveal">Where eprocure shows an award, the median award is {ar[1] or 0:.2f} times the estimated value ({n(ar[0])} tenders).</p>
</section>""")

    # 5 award values
    S.append(f"""<section id="awards"><h2><span class="no">05</span>Award values from the award letters</h2>
<p class="reveal">eprocure has almost no award data for DDA, so we read the award letters on the DDA site. {n(aw[0])} letters have a
text layer (often an old, noisy OCR layer). <code>analysis.extract_awards</code> reads the estimated cost and the awarded amount by their
labels, and never takes an amount next to a guarantee, an FDR or an account number. A &ldquo;% below the estimated cost&rdquo;
gives the amount when it is missing.</p>
<div class="tiles">
{tile(n(aw[1]), "letters with the estimated cost", aw[1])}
{tile(n(aw[2]), "letters with the awarded amount", aw[2])}
{tile(n(aw[3]), "with a plausible ratio (0.3 to 1.6)", aw[3])}
{tile(f"&#8377; {aw[9] or 0:,.1f} cr", "awarded in these letters")}
</div>
{fig("Awarded amount as a share of the estimated cost (number of letters)", hbar([(r[0], r[1]) for r in a.get("award_ratio_bands", [])], label_w=120, note="Award ratio"))}
<ul class="reveal">
<li>The median award is <strong>{aw[4] or 0:.2f}</strong> times the estimated cost. {n(aw[5])} of {n(aw[3])} letters ({pct(aw[5], aw[3])}) are below 70% of the estimate.</li>
<li>Check against eprocure: {n(aw[6])} letters link to an eprocure tender; in {n(aw[7])} of them the estimated cost equals the eprocure tender value (within 2%), in {n(aw[8])} it differs.</li>
<li>The table <code>dda.award_values</code> holds amounts, dates and keys only, no names.</li>
</ul>
{flag("Indicator", f"Many works are awarded far below the estimate: {n(aw[5])} of {n(aw[3])} letters at less than 70% of it. Very low bids can show inflated estimates or abnormally low bids. Check this with the full text of the tenders.")}
</section>""")

    # 6 history
    laa = [(r[0], r[1]) for r in a.get("land_acq_decade", []) if r[0] != "(no year)"]
    am = [(f"{r[0]}s", r[1]) for r in a.get("authority_meetings", [])]
    years = [(str(y), c) for y, c in a.get("rows_per_year", []) if y and 1990 <= y <= 2026]
    S.append(f"""<section id="history"><h2><span class="no">06</span>Historical records</h2>
<p class="reveal">The site keeps old records that are not easy to find with the site navigation. The tables make them searchable.</p>
{fig(f"Land acquisition awards by decade of the award ({n(sum(r[1] for r in a.get('land_acq_decade', []) if r[0] == '(no year)'))} awards have no year in the number)", vbar(laa, note="Land acquisition awards", h=200))}
<p class="reveal">The villages with the most awards are {", ".join(E(str(r[0]).title()) for r in a.get("land_acq_villages", [])[:5])}.</p>
{fig("Authority meeting agendas and minutes by decade", vbar(am, note="Authority meetings", h=200))}
{fig("Dated listing rows by year, 1990 to 2026 (site publishing activity)", vbar(years, note="Listing rows by year", every=4))}
</section>""")

    # 7 documents
    S.append(f"""<section id="documents"><h2><span class="no">07</span>Documents</h2>
<p class="reveal">The stored documents use {gb(stored_b)}. The median file is {(median_b or 0) / 1e6:.1f} MB. Most files are PDF.
<code>dda.documents</code> gives the status, size, SHA-256 and bucket key of each file.</p>
{fig("Stored documents by file size", hbar([(r[0], r[1]) for r in a.get("doc_size_bands", [])], label_w=150, note="Documents by size"))}
{fig("Documents by site folder (top 12)", hbar([(r[0], r[1]) for r in a.get("doc_folders", [])[:12]], label_w=170, note="Documents by folder"))}
<ul class="reveal">
<li><strong>Duplicate files:</strong> {n(dup[0])} files occur at more than one URL; {n(dup[1])} extra copies ({gb(dup[2])}). One file has {n(dup[3])} URLs.</li>
<li><strong>Very large files:</strong> {n((a.get('doc_size_bands') or [[0, 0]])[-1][1])} files are 100 MB or larger, mostly scanned orders and agendas.</li>
<li><strong>Empty file:</strong> {n(first(a, 'doc_empty', [0])[0])} PDF file has 0 bytes.</li>
<li><strong>Size label:</strong> for {n(first(a, 'size_mismatch', [0])[0])} listing rows, the stored file is more than 20% larger or smaller than the size the site shows.</li>
</ul></section>""")

    # 8 text
    S.append(f"""<section id="text"><h2><span class="no">08</span>Text in the documents (no OCR)</h2>
<p class="reveal"><code>analysis.extract_text</code> read the text layer of {n(dt[0])} of {n(dt[3])} stored PDF files (files over
25 MB are left out; they are mostly scans). <strong>{n(dt[1])} ({pct(dt[1], dt[0])})</strong> have text, {n(dt[2])} characters in all.
The rest are scans for OCR later. <code>dda.document_text</code> has a full-text index.</p>
{table(["Search words", "Documents that match"], [(r[0], r[1]) for r in a.get("doc_text_search", [])], num_cols=(1,))}
<p class="reveal">A random sample of {n(pc.get('sampled', 0))} PDF files gave {pc.get('text_layer_share', 0) * 100:.1f}% with a text
layer and {pc.get('hindi_share', 0) * 100:.1f}% with Hindi text. In tender notices, the estimated cost was readable in
{n(pc.get('tender_cost_found', 0))} of {n(pc.get('tender_sampled', 0))} sampled notices; eprocure gives these values for the linked tenders.</p>
</section>""")

    # 9 quality and privacy
    S.append(f"""<section id="quality"><h2><span class="no">09</span>Site quality, security and privacy</h2>
<p class="reveal">These are indicators, not findings of wrongdoing.</p>
{fig("Broken document links (HTTP 404) by folder", hbar([(r[0], r[1]) for r in a.get("broken_by_folder", [])], label_w=150, note="Broken links"))}
<ul class="reveal">
<li><strong>Legacy TLS.</strong> The server needs legacy TLS renegotiation. Modern clients refuse it by default.</li>
<li><strong>Incomplete certificate chain.</strong> The server does not send its intermediate certificate.</li>
<li><strong>Links to raw IP addresses.</strong> Some pages link to services by IP address over plain HTTP.</li>
<li><strong>Link to a staging server.</strong> One page links to a vendor staging host on port 91.</li>
<li><strong>Plain HTTP links.</strong> {n(first(a, 'external_http', [0])[0])} external links use <code>http://</code>.</li>
<li><strong>Hindi mirror.</strong> Only {n(hp[1])} of {n(hp[0])} English pages have a Hindi page at the same path (a lower bound).</li>
</ul>
<h3>Sections with no new dated entry for a long time</h3>
{table(["Section (category)", "Latest date", "Rows"], [(r[0], r[1], r[2]) for r in a.get("latest_by_category", [])[:8]], num_cols=(2,))}
{flag("Privacy", f"The archive of registered contractors links {n(ef[0])} files: {n(ef[1])} bank solvency certificates and {n(ef[2])} application forms. Many contractors are sole proprietors, so these files can hold personal and financial data. Also, {n(alt[1])} of {n(alt[0])} award letters with a text layer print a bank account number of the contractor. We did not open or extract these files, and we counted only. We recommend that DDA reviews whether these files must stay public.")}
</section>""")

    # 10 STF
    stf_rows = [(k, v[1], v[2], f"{v[3] or '–'} to {v[4] or '–'}", f"{v[5] or '–'} to {v[6] or '–'}") for k, v in stfk.items()]
    S.append(f"""<section id="stf"><h2><span class="no">10</span>Special Task Force portal (stf.dda.org.in)</h2>
<p class="reveal">The Special Task Force acts against misuse and encroachment of land in Delhi under an order of the Supreme
Court. Its portal publishes the agendas and the minutes of its meetings. The project <code>dda-stf</code> stores the public pages
and the files. The login, the complaint forms and the lists of named officers are left out.</p>
{table(["Kind", "Files", "Stored", "Meeting numbers", "Upload dates"], stf_rows, num_cols=(1, 2))}
{fig("STF files by upload year (from the file name)", vbar([(str(r[0]), r[1]) for r in a.get("stf_years", [])], note="STF files by year", h=200))}
<p class="reveal">Tables: <code>dda.stf_documents</code> (kind, meeting number, upload date, size, bucket key) and <code>dda.stf_pages</code>.</p>
</section>""")

    # 11 Greens
    S.append(f"""<section id="greens"><h2><span class="no">11</span>DDA Greens plantation portal</h2>
<p class="reveal">DDA Greens reports the plantation drive in DDA parks through a public JSON API. The project <code>dda-greens</code>
stores the dashboard, the list of parks and, for each park, the summary and the species counts. Officer pages and
the details of single plantations are left out.</p>
<div class="tiles">
{tile(n(gdash.get('totalPlantation')), "plants planted (dashboard)", gdash.get('totalPlantation'))}
{tile(n(gdash.get('totalTargetPlantation')), "plantation target", gdash.get('totalTargetPlantation'))}
{tile(f"{gdash.get('completedPercentage', 0) or 0:.1f}%", "of the target done")}
{tile(n(gp[0]), f"parks with a summary (average {gp[1] or 0}% done)", gp[0])}
</div>
{fig("Parks by share of the target done", hbar([(r[0], r[1]) for r in a.get("greens_pct_bands", [])], label_w=130, note="Parks by completion"))}
<ul class="reveal">
<li>{n(gp[2])} parks report 100% or more of their target; {n(gp[3])} report less than half.</li>
<li>Species recorded as &ldquo;Other&rdquo;: {n((gother.get('Shrub') or [0, 0])[1])} of {n((gother.get('Shrub') or [0, 0, 0])[2])} shrubs and
{n((gother.get('Tree') or [0, 0])[1])} of {n((gother.get('Tree') or [0, 0, 0])[2])} trees in the species summaries.</li>
</ul>
{table(["Type", "Species", "Plants"], [(r[0], r[1], r[2]) for r in a.get("greens_top_species", [])], num_cols=(2,))}
</section>""")

    # 12 watch
    wrows = [(w.get("week"), w.get("listings_read"), w.get("new_documents"), w.get("stored_documents"), w.get("new_pages"))
             for w in watch]
    S.append(f"""<section id="watch"><h2><span class="no">12</span>Weekly change watch</h2>
<p class="reveal">Every Monday at 02:30 UTC, the GitHub Actions workflow <code>watch</code> puts one item into the project
<code>dda-watch</code>. The hub gives it to a pool worker with an India proxy. The worker reads the first page of every
listing (about 120 requests), compares the links with the known scope, and stores each new page and file.</p>
{table(["Week", "Listings read", "New files", "Files stored", "New page links"], wrows, num_cols=(1, 2, 3, 4))}
</section>""")

    # 13 next
    S.append("""<section id="next"><h2><span class="no">13</span>More scope and next steps</h2>
<p class="reveal">Each item uses public data. None needs a login.</p>""" + table(["Scope", "What it gives", "Size or effort"], [
        ["OCR of scanned PDFs", "Text of old orders, agendas and Authority minutes since 1959", "About 10,500 files; decision needed"],
        ["Award values for the scanned letters", "Awarded amount for the letters that have no text", "After OCR"],
        ["STF minutes", "Decisions of each STF meeting (encroachment, misuse)", "335 files, text layer to check"],
        ["Land acquisition awards", "Area and amount for about 1,800 awards", "PDF text or OCR"],
        ["Layout plans and KMZ maps", "Boundaries of parks, plots and colonies as map files", "About 700 KMZ files"],
        ["Hindi parity by title", "English listings with no Hindi page", "Data exists"],
        ["Fold the watch into the main projects", "Monthly discovery on the box, then Setup", "A few hundred requests"],
    ]) + "</section>")

    # 14 use
    S.append("""<section id="use"><h2><span class="no">14</span>How to use the data</h2>
<p class="reveal">The workspace database <code>ws_trideep</code>, schema <code>dda</code>, holds the data. Metabase shows it as
&ldquo;Workspace: trideep&rdquo;. The repository <code>s1d-labs/dda</code> holds the code.</p>""" + table(["Table or view", "Content"], [
        ["pages / documents", "One row per HTML page / per document (status, size, SHA-256, bucket key)"],
        ["listing_rows / html_tables", "Rows of the Drupal listings / of every plain HTML table"],
        ["tenders / work_awards / debarments", "Tender notices (NIT, office, year), award letters, debarment orders"],
        ["eprocure_tenders / tender_links / award_links / tender_unlinked", "DDA tenders on eprocure and the link to the site rows"],
        ["award_values", "Estimated cost and awarded amount from the award letters"],
        ["land_acq_awards", "Land acquisition awards: number, village, year"],
        ["unauthorised_colonies / delineated_boundaries / colony_boundary_status", "PM-UDAY colony lists and boundary status"],
        ["document_text", "Text layer of the stored PDFs, with a full-text index"],
        ["stf_documents / stf_pages", "Special Task Force agendas, minutes and pages"],
        ["greens_parks / greens_species / greens_dashboard", "DDA Greens plantation figures"],
        ["duplicate_files / size_mismatch / broken_links", "Data quality views"],
    ]) + """<p class="reveal">To refresh everything: <code>eval "$(mybucket env)"; python -m analysis.refresh --html /tmp/dda-html --sync</code>.</p>
</section>""")

    # 15 limits
    S.append("""<section id="limits"><h2><span class="no">15</span>Limits</h2><ul class="reveal">
<li>3 documents are not delivered by the server; they are recorded as unretrievable.</li>
<li>The eprocure data comes from the team database; its stage is as old as the team's last eprocure scrape.</li>
<li>The login, OTP and captcha portals of DDA are separate systems. We did not access them.</li>
<li>No OCR was used. Values from noisy text layers can be wrong; the checks against eprocure show how often.</li>
<li>Dates come from the listing text. A row without a printed date has no date.</li>
</ul></section>""")

    S.append(f"""<p class="foot">Source: public pages, files and APIs of dda.gov.in, stf.dda.org.in and ddagreens.dda.org.in, scraped by
the s1d labs scrape pool. Generated by <code>analysis.report_html</code> from <code>reports/analysis.json</code> on {gen}.
Animation: GSAP 3.12.5 with ScrollTrigger (GreenSock standard license), inlined.</p>
</main></div>
<script>{vendor("gsap.min.js")}</script>
<script>{vendor("ScrollTrigger.min.js")}</script>
<script>{JS}</script>
</body></html>""")
    return "\n".join(S)


def main():
    src, dst = (sys.argv[1:3] + [None, None])[:2]
    a = json.load(open(src or "reports/analysis.json"))
    out = build(a)
    with open(dst or "reports/dda-audit.html", "w") as f:
        f.write(out)
    print("wrote", dst or "reports/dda-audit.html", f"({len(out) // 1024} KB)")


if __name__ == "__main__":
    main()
