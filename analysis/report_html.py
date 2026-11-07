"""Render analysis.json (analyze.py) as one self-contained HTML report with inline SVG charts.

    python -m analysis.report_html analysis.json report.html

The text uses ASD-STE100 Simplified Technical English. It names no private individuals or firms.
"""
import html
import json
import sys

E = html.escape


def n(x):
    return f"{int(x or 0):,}"


def gb(b):
    return f"{(b or 0) / 1e9:.1f} GB"


def hbar(rows, label_w=230, fmt=n, note=""):
    """Horizontal bars, one series, value label at the bar end. rows: [(label, value)]."""
    rows = [(str(a), float(b or 0)) for a, b in rows]
    mx = max([b for _, b in rows] + [1])
    bh, gap, w = 22, 8, 640
    plot = w - label_w - 70
    h = len(rows) * (bh + gap) + 4
    out = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="{E(note)}">']
    for i, (lab, v) in enumerate(rows):
        y = i * (bh + gap) + 2
        bw = max(2, plot * v / mx)
        out.append(f'<g class="mark"><title>{E(lab)}: {fmt(v)}</title>'
                   f'<text x="{label_w - 10}" y="{y + bh / 2 + 4}" text-anchor="end" class="lab">{E(lab[:38])}</text>'
                   f'<rect x="{label_w}" y="{y}" width="{bw:.1f}" height="{bh}" rx="4" class="bar"/>'
                   f'<text x="{label_w + bw + 6}" y="{y + bh / 2 + 4}" class="val">{fmt(v)}</text></g>')
    out.append("</svg>")
    return "".join(out)


def vbar(rows, fmt=n, note="", every=1, h=240):
    """Vertical bars over an ordered axis (years, decades). rows: [(label, value)]."""
    rows = [(str(a), float(b or 0)) for a, b in rows]
    mx = max([b for _, b in rows] + [1])
    w, left, bottom, top = 640, 44, 28, 14
    plot_w, plot_h = w - left - 8, h - bottom - top
    step = plot_w / max(1, len(rows))
    bw = max(3, step - 3)
    ticks = [mx * k / 4 for k in range(5)]
    out = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="{E(note)}">']
    for t in ticks:
        y = top + plot_h - plot_h * t / mx
        out.append(f'<line x1="{left}" x2="{w - 8}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>'
                   f'<text x="{left - 6}" y="{y + 4:.1f}" text-anchor="end" class="tick">{fmt(t)}</text>')
    for i, (lab, v) in enumerate(rows):
        x = left + i * step + 1.5
        bh_ = plot_h * v / mx
        y = top + plot_h - bh_
        out.append(f'<g class="mark"><title>{E(lab)}: {fmt(v)}</title>'
                   f'<rect x="{x:.1f}" y="{top}" width="{step:.1f}" height="{plot_h}" class="hit"/>'
                   f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{max(bh_, 1):.1f}" rx="{min(4, bw / 2):.1f}" class="bar"/></g>')
        if i % every == 0 or i == len(rows) - 1:
            out.append(f'<text x="{x + bw / 2:.1f}" y="{h - 10}" text-anchor="middle" class="tick">{E(lab)}</text>')
    out.append(f'<line x1="{left}" x2="{w - 8}" y1="{top + plot_h}" y2="{top + plot_h}" class="axis"/></svg>')
    return "".join(out)


def table(head, rows, num_cols=()):
    th = "".join(f'<th class="{"num" if i in num_cols else ""}">{E(h)}</th>' for i, h in enumerate(head))
    body = "".join("<tr>" + "".join(
        f'<td class="{"num" if i in num_cols else ""}">{E(n(c) if i in num_cols else str(c if c is not None else "–"))}</td>'
        for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<div class="tw"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


CSS = """
:root{
  /* Layout: one reading column, figures full column width, a tile row for the measured scope */
  --bg:#f6f7f8; --surface:#ffffff; --ink:#15191d; --ink-2:#4a535c; --muted:#6c7680; --rule:#d9dee3;
  --bar:#2a78d6; --hit:transparent; --flag:#b4541a; --flag-bg:#fbefe6;
  --display:"Source Serif 4", Georgia, serif; --body:"Public Sans", system-ui, sans-serif;
  --mono:"IBM Plex Mono", ui-monospace, monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#131619; --surface:#1b1f23; --ink:#eef1f3; --ink-2:#bcc4cb; --muted:#8f99a3; --rule:#2e353b;
  --bar:#3987e5; --flag:#ec9a66; --flag-bg:#2c2219; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#131619; --surface:#1b1f23; --ink:#eef1f3; --ink-2:#bcc4cb; --muted:#8f99a3; --rule:#2e353b;
  --bar:#3987e5; --flag:#ec9a66; --flag-bg:#2c2219; color-scheme:dark}
body{background:var(--bg);color:var(--ink);font:15px/1.6 var(--body)}
.wrap{max-width:860px;margin:0 auto;padding-block:32px 64px;
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
h1,h2,h3{font-family:var(--display);text-wrap:balance;line-height:1.2;margin:0}
h1{font-size:2.1rem;font-weight:600}
h2{font-size:1.45rem;font-weight:600;margin-top:44px;padding-top:18px;border-top:1px solid var(--rule)}
h3{font-size:1.05rem;font-weight:600;margin-top:22px;font-family:var(--body)}
p,li{max-width:68ch;color:var(--ink-2)} p{margin:10px 0}
.eyebrow{font:500 12px/1 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.lede{font-size:1.05rem;color:var(--ink-2)}
.tiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:22px 0}
@media (max-width:560px){.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}}
.tile{background:var(--surface);border:1px solid var(--rule);border-radius:8px;padding:14px 16px;min-width:0}
.tile b{display:block;font:600 1.6rem/1.1 var(--display);font-variant-numeric:tabular-nums;color:var(--ink)}
.tile span{font-size:.82rem;color:var(--muted)}
figure{margin:16px 0 8px;background:var(--surface);border:1px solid var(--rule);border-radius:8px;padding:14px 14px 8px;min-width:0}
figcaption{font-size:.85rem;color:var(--muted);margin-bottom:8px}
.chart{width:100%;height:auto;display:block}
.chart .bar{fill:var(--bar)} .chart .hit{fill:var(--hit)}
.chart .mark:hover .bar{opacity:.78}
.chart .lab,.chart .val,.chart .tick{fill:var(--ink-2);font:12px var(--body);font-variant-numeric:tabular-nums}
.chart .val{fill:var(--ink)} .chart .tick{fill:var(--muted);font-size:11px}
.chart .grid{stroke:var(--rule);stroke-width:1} .chart .axis{stroke:var(--muted);stroke-width:1}
.flag{background:var(--flag-bg);border-left:3px solid var(--flag);padding:10px 14px;border-radius:0 6px 6px 0;margin:12px 0}
.flag p,.flag li{color:var(--ink)} .flag strong{color:var(--flag)}
.tw{overflow-x:auto;margin:12px 0} table{border-collapse:collapse;width:100%;font-size:.88rem}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--rule);vertical-align:top}
th{font-weight:600;color:var(--muted);font-size:.78rem;text-transform:uppercase;letter-spacing:.04em}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
code{font:13px var(--mono);background:var(--surface);border:1px solid var(--rule);padding:1px 5px;border-radius:4px}
ul{padding-left:20px} li{margin:4px 0}
.foot{margin-top:40px;font-size:.82rem;color:var(--muted)}
"""


def build(a, repair):
    st = dict((r[0], r[1]) for r in a["doc_status"])
    docs_total = sum(st.values())
    stored_n, stored_b, median_b = a["doc_bytes_stored"][0]
    lang = dict((r[0], r[1]) for r in a["pages_lang"])
    pages_total = sum(lang.values())
    col = dict((str(r[0]), (r[1], r[2])) for r in a["colonies"])
    cstat = a["colony_status"]
    br = a["boundary_rows"][0]
    dup = a["duplicates"][0]
    tt = a["tenders_total"][0]
    wa = a["work_awards"][0]
    ef = a["enlistment_files"][0]
    lr = a["listing_rows"][0]
    deb = dict((r[0], r[1]) for r in a["debarments"])
    broken = st.get("broken", 0)
    scope = a.get("scope", {})
    hp = (a.get("hindi_parity") or [[0, 0]])[0]
    alt = (a.get("award_letter_text") or [[0, 0, 0, 0, 0, 0]])[0]

    years = [(y, c) for y, c in a["rows_per_year"] if y and 1990 <= y <= 2026]
    s = []
    s.append(f"""<title>DDA Website Data Audit</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Public+Sans:wght@400;600&family=Source+Serif+4:opsz,wght@8..60,600&display=swap">
<style>{CSS}</style>
<div class="wrap">
<p class="eyebrow">s1d labs &middot; scraper family dda &middot; {E(a['_generated_at'][:10])}</p>
<h1>DDA website data audit</h1>
<p class="lede">This report gives the measured scope of the public website of the Delhi Development Authority
(<code>dda.gov.in</code>), the checks of the scraped data, and the findings from the data. It uses ASD-STE100
Simplified Technical English. It names no private individuals or firms.</p>
<div class="tiles">
 <div class="tile"><b>{n(scope.get('pages', pages_total))}</b><span>unique HTML pages found ({n(pages_total)} scraped)</span></div>
 <div class="tile"><b>{n(scope.get('documents', docs_total))}</b><span>unique documents found</span></div>
 <div class="tile"><b>{n(stored_n)}</b><span>documents stored ({gb(stored_b)})</span></div>
 <div class="tile"><b>{n(lr[0])}</b><span>listing rows (title, date, file)</span></div>
 <div class="tile"><b>{n(col.get('1731', (0, 0))[0])}</b><span>unauthorised colonies as a table</span></div>
 <div class="tile"><b>{n(broken)}</b><span>document links that return HTTP 404</span></div>
</div>
<p>{"The scrape is complete: every page and every document that the site delivers is stored." if pages_total >= scope.get('pages', 0)
 else f"The scrape continues. {n(scope.get('pages', pages_total) - pages_total)} pages are still in the queue."}
All counts on this page come from the workspace database tables (schema <code>dda</code>) at the time shown above.</p>
""")

    # verification
    s.append(f"""<h2>1. Verification of the scrape</h2>
<p>We checked the stored records against the site structure. The checks found five defects in the first version
of the scraper and three more during the run. We fixed all of them. The table gives each defect and its effect.</p>
{table(["Check", "Result", "Action"], [
        ["One spelling per URL", "221 pages were scraped twice (http:// and https://). 27 documents had two spellings (space and %20).", "One canonical URL. 2,871 pages became 2,649."],
        ["HTML entities in links", "157 document links were lost. The crawler read '&amp;' in a file name as text.", "Links are unescaped. The repair pass adds the files."],
        ["Pager coverage", "395 listing pages were not reached. Example: 191 of 285 pages of the tender archive.", "Every page 1..N of a listing is queued. The repair pass fetches them."],
        ["Failed downloads", f"{n(broken)} documents return HTTP 404 on the site.", "They are recorded once as broken links. No retries."],
        ["Files the server never delivers", "The server cuts one 40 MB PDF at the same byte on every try. The pool ran about 38 runner jobs an hour for 3 such files.", "After 10 tries the file is recorded as unretrievable."],
        ["Discovery of files", "A file linked as a page was read in full (more than 400 MB).", "Discovery reads the headers first."],
        ["Large downloads", "A dropped connection during a 40 MB file stopped a worker process.", "The item fails and the worker continues."],
        ["Dates", "Two-digit years became 20xx (1986 was stored as 2086).", "Two-digit years now resolve to the past."],
    ])}
<p>{E(repair)}</p>
""")

    # colonies
    s.append(f"""<h2>2. Unauthorised colonies (PM-UDAY)</h2>
<p>The site publishes the list of {n(col.get('1731', (0, 0))[0])} unauthorised colonies (excluding affluent colonies) and a
list of {n(col.get('affluent', (0, 0))[0])} colonies inhabited by the affluent section of society. Both are text PDF files.
We extracted all rows without OCR. The table <code>dda.unauthorised_colonies</code> and the file
<code>data/unauthorised_colonies.csv</code> hold the result.</p>
<p>The page <code>/delineated-boundary</code> holds a second table with {n(br[0])} rows. Each row gives the boundary map of one colony.
We joined the two tables on the registration number.</p>
<figure><figcaption>Boundary status of the 1,731 colonies (count of colonies)</figcaption>
{hbar([(r[0], r[1]) for r in cstat], note="Boundary status of the 1,731 unauthorised colonies")}</figure>
<ul>
<li>{n(br[5])} boundary rows have the remark that the boundary can not be delineated as per the SOP. {n(br[6])} of these give the reason that the shapefile of the colony is not available.</li>
<li>All {n(br[2])} final boundary maps have an upload date between {E(str(br[3]))} and {E(str(br[4]))}. The table has no update after August 2020.</li>
<li>{n(a['boundary_not_in_list'][0][0])} boundary rows have a registration number that is not in the list of 1,731 colonies.</li>
<li>The list of 1,731 colonies has {n(a['colony_dup_reg'][0][0])} registration number that occurs two times.</li>
<li>{n(col.get('1731', (0, 0))[1])} of the 1,731 colony entries give a postal district (for example "Delhi-41"). We converted it to a PIN code.</li>
</ul>
<div class="flag"><p><strong>Indicator.</strong> About 1 colony in 5 has no final boundary on the site
({n(sum(r[1] for r in cstat if r[0] != 'final boundary published'))} of 1,731). The final boundary is the base for the
PM-UDAY ownership process. The public table shows no change since 2020.</p></div>
""")

    # tenders
    have = dict((r[0], r[1]) for r in a["tenders_fy"])
    first = min(int(k[:4]) for k in have) if have else 2019
    fy = [(f"{y}-{(y + 1) % 100:02d}", have.get(f"{y}-{(y + 1) % 100:02d}", 0)) for y in range(max(first, 2015), 2027)]
    s.append(f"""<h2>3. Tenders, work awards and debarments</h2>
<p>The tender pages and the tender archive give {n(tt[0])} tender rows with {n(tt[1])} different NIT numbers. We read the
office code and the financial year from each NIT number (for example <code>07/EE/HCD-10/DDA/2026-27</code>).
The full tender process runs on the central e-procurement portal. The DDA site keeps the notice and the documents.</p>
<figure><figcaption>Tender rows on the DDA site by financial year (from the NIT number)</figcaption>
{vbar([(k[2:], v) for k, v in fy], note="Tender rows by financial year")}</figure>
<div class="flag"><p><strong>Coverage note.</strong> The first scrape read only 94 of the 285 pages of the tender archive, so
it showed almost no tenders for 2022-23 to 2024-25. The repair pass read all 285 pages. The chart now shows these years.</p></div>
<ul>
<li>{n(tt[3])} tender rows ({tt[3] * 100 / max(tt[0], 1):.1f}%) are marked "re-invited". A re-invited tender had no valid bid in the first call.</li>
<li>The site has {n(wa[0])} work award letters. {n(wa[1])} of them give the NIT number of the tender.</li>
<li>The site has {n(deb.get('order', 0))} debarment or suspension orders and {n(deb.get('withdrawal', 0))} withdrawals of such orders.
Most orders are from 2022 to 2025.</li>
</ul>
<h3>Offices with the most tender rows</h3>
{table(["Office code (from the NIT number)", "Tender rows"], [(r[0], r[1]) for r in a["tender_offices"][:10]], num_cols=(1,))}
""")

    # history
    laa = [(r[0], r[1]) for r in a["land_acq_decade"] if r[0] != "(no year)"]
    am = [(f"{r[0]}s", r[1]) for r in a["authority_meetings"]]
    s.append(f"""<h2>4. Historical records</h2>
<p>The site keeps old records that are not easy to find with the site navigation. The data makes them searchable.</p>
<figure><figcaption>Land acquisition awards by decade of the award (from the award number; {n(sum(r[1] for r in a['land_acq_decade'] if r[0] == '(no year)'))} awards have no year in the number)</figcaption>
{vbar(laa, note="Land acquisition awards by decade", h=200)}</figure>
<p>The villages with the most awards are {", ".join(E(r[0].title()) for r in a["land_acq_villages"][:5])}.</p>
<figure><figcaption>Authority meeting agendas and minutes by decade</figcaption>
{vbar(am, note="Authority meeting records by decade", h=200)}</figure>
<figure><figcaption>Dated listing rows by year, 1990 to 2026 (site publishing activity)</figcaption>
{vbar(years, note="Dated listing rows by year", every=4)}</figure>
<p>{n(lr[1])} of {n(lr[0])} listing rows have a date. The count increases strongly after 2019. Older material is mostly in archive sections.</p>
""")

    # documents
    s.append(f"""<h2>5. Documents</h2>
<p>The stored documents use {gb(stored_b)}. The median file is {median_b / 1e6:.1f} MB. Most files are PDF. The table
<code>dda.documents</code> gives the status, size and SHA-256 of each file.</p>
<figure><figcaption>Stored documents by file size</figcaption>
{hbar([(r[0], r[1]) for r in a["doc_size_bands"]], label_w=150, note="Stored documents by size")}</figure>
<figure><figcaption>Documents by site folder (all statuses, top 12)</figcaption>
{hbar([(r[0], r[1]) for r in a["doc_folders"][:12]], label_w=170, note="Documents by folder")}</figure>
<ul>
<li><strong>Duplicate files:</strong> {n(dup[0])} files occur at more than one URL. The extra copies are {n(dup[1])} files ({gb(dup[2])}). One file occurs {n(dup[3])} times.</li>
<li><strong>Very large files:</strong> {n(a['doc_size_bands'][-1][1])} files are 100 MB or larger. The largest is {gb(a['doc_largest'][0][2])}. These are mostly scanned orders and agendas.</li>
<li><strong>Empty file:</strong> {n(a['doc_empty'][0][0])} PDF file has 0 bytes.</li>
<li><strong>Size label:</strong> the listing shows a size for {n(lr[3])} rows. For {n(a['size_mismatch'][0][0])} rows, the stored file is more than 20% larger or smaller than the label.</li>
</ul>
""")

    # site quality
    s.append(f"""<h2>6. Site quality and security indicators</h2>
<p>These are indicators, not findings of wrongdoing.</p>
<figure><figcaption>Broken document links (HTTP 404) by folder</figcaption>
{hbar([(r[0], r[1]) for r in a["broken_by_folder"]], label_w=150, note="Broken links by folder")}</figure>
<ul>
<li><strong>Legacy TLS.</strong> The server needs legacy TLS renegotiation. Modern clients refuse it by default.</li>
<li><strong>Incomplete certificate chain.</strong> The server does not send its intermediate certificate.</li>
<li><strong>Links to raw IP addresses.</strong> Some pages link to services by IP address over plain HTTP.</li>
<li><strong>Link to a staging server.</strong> One page links to a vendor staging host on port 91.</li>
<li><strong>Plain HTTP links.</strong> {n(a['external_http'][0][0])} external links use <code>http://</code>. Most go to the DDA online services portal.</li>
<li><strong>Hindi mirror.</strong> The site has {n(lang.get('hi', 0))} Hindi pages and {n(lang.get('en', 0))} English pages. Only {n(hp[1])} of {n(hp[0])} English pages have a Hindi page at the same path (a lower bound).</li>
</ul>
<h3>Sections with no new dated entry for a long time</h3>
{table(["Section (category)", "Latest date", "Rows"], [(r[0], r[1], r[2]) for r in a["latest_by_category"][:8]], num_cols=(2,))}
<div class="flag"><p><strong>Privacy indicator.</strong> The archive of registered contractors links {n(ef[0])} files.
They include {n(ef[1])} bank solvency certificates and {n(ef[2])} application forms. Many registered contractors are
sole proprietors, so these files can hold personal and financial data. We did not open or extract these files.
{f"Also, {n(alt[1])} of {n(alt[0])} award letters with a text layer print a bank account number of the contractor (counted, not stored in the report)." if alt[0] else ""}
We recommend that DDA reviews whether these files must stay public.</p></div>
""")

    # eprocure
    eps = dict((r[0], r[1]) for r in a.get("ep_stage", []))
    ep_total = sum(eps.values())
    epl = (a.get("ep_links") or [[0, 0, 0, 0]])[0]
    ar = (a.get("ep_award_ratio") or [[0, 0, 0]])[0]
    alst = dict((r[0], r[1]) for r in a.get("ep_award_letter_stage", []))
    epy = [(str(r[0]), r[1]) for r in a.get("ep_years", []) if r[0] and r[0] <= 2026]
    single = [(str(r[0]), r[3] * 100.0 / r[4]) for r in a.get("ep_years", []) if r[0] and r[4]]
    peers = a.get("ep_peer_awarded", [])
    award_id_note = (f"{n(alt[2])} award letters print the eprocure Tender ID itself; {n(alt[4])} of these tenders show "
                     f"\"in evaluation\" on eprocure." if alt[2] else "")
    if ep_total:
        s.append(f"""<h2>7. DDA on the central e-procurement portal</h2>
<p>DDA runs its tenders on the central e-procurement portal (<code>eprocure.gov.in</code>). The team database already holds
{n(ep_total)} DDA tenders from that portal, with tender value, EMD, bid counts and stage. The DDA site keeps the notices and the
award letters. Both use the same NIT reference, so we linked them by number, office and financial year
(<code>link_eprocure.py</code>).</p>
<ul>
<li>{n(epl[1])} of {n(epl[0])} tender rows on the DDA site ({epl[1] * 100 / max(epl[0], 1):.1f}%) link to an eprocure tender.</li>
<li>{n(epl[3])} of {n(epl[2])} award letters with an NIT number link to an eprocure tender.</li>
</ul>
<figure><figcaption>DDA tenders published on eprocure by year</figcaption>
{vbar(epy, note="DDA tenders on eprocure by year", every=2)}</figure>
<figure><figcaption>Share of DDA tenders with exactly one bid, by year (% of tenders with bids)</figcaption>
{vbar(single, fmt=lambda v: f"{v:.1f}%", note="Single-bid share by year", every=2, h=200)}</figure>
<div class="flag"><p><strong>Indicator.</strong> Only {n(eps.get('awarded', 0))} of {n(ep_total)} DDA tenders
({eps.get('awarded', 0) * 100 / ep_total:.1f}%) reach the stage "awarded" on eprocure. {n(eps.get('in evaluation', 0))}
({eps.get('in evaluation', 0) * 100 / ep_total:.1f}%) stay "in evaluation". Of the tenders with an award letter on the DDA site,
{n(alst.get('in evaluation', 0))} still show "in evaluation" on eprocure. DDA publishes the award on its own site, not on the portal.
{award_id_note}</p></div>
<h3>Awarded share of the largest buyers on eprocure</h3>
{table(["Organisation code", "Tenders", "Awarded on eprocure (%)"], [(r[0], r[1], f"{r[2]:.1f}") for r in peers], num_cols=(1,))}
<ul>
<li>Where eprocure shows an award, the median award is {ar[1]:.2f} times the estimated value ({n(ar[0])} tenders).
{n(ar[2])} of them ({ar[2] * 100 / max(ar[0], 1):.1f}%) are below the estimate.</li>
<li>The tables <code>dda.eprocure_tenders</code>, <code>dda.tender_links</code> and <code>dda.award_links</code> hold the link.
They have no bidder names.</li>
</ul>
""")

    pc = a.get("pdf_census") or {}
    if pc:
        bf = sorted(pc.get("by_folder", {}).items(), key=lambda kv: -kv[1]["sampled"])[:10]
        s.append(f"""<h2>8. Text in the documents (no OCR)</h2>
<p>We opened a random sample of {n(pc.get('sampled'))} stored PDF files and read the text layer of the first pages. A page with
fewer than 25 characters counts as a scanned page. This measures the OCR work for later.</p>
<ul>
<li><strong>{pc.get('text_layer_share', 0) * 100:.1f}%</strong> of the sampled PDF files have a text layer. The rest are scans and need OCR.</li>
<li>{pc.get('hindi_share', 0) * 100:.1f}% of the sampled files have Hindi text. The median file has {n(pc.get('median_pages'))} pages.</li>
<li>Tender notices: {pc.get('tender_text_share', 0) * 100:.1f}% have a text layer. The estimated cost was found in
{n(pc.get('tender_cost_found'))} of {n(pc.get('tender_sampled'))} sampled notices and the EMD in {n(pc.get('tender_emd_found'))}.
eprocure already gives these values for the linked tenders.</li>
</ul>
{table(["Folder", "Sampled", "With text layer"], [(k, v["sampled"], v["text"]) for k, v in bf], num_cols=(1, 2))}
""")
    dt = (a.get("doc_text") or [[0, 0, 0, 0]])[0]
    if dt[0]:
        s.append(f"""<h3>Full-text table</h3>
<p><code>extract_text.py</code> reads the text layer of the stored PDF files into <code>dda.document_text</code>, with a
full-text index. It read {n(dt[0])} of {n(dt[3])} stored PDF files (the files over 25 MB are left out; they are
mostly scans). {n(dt[1])} of them ({dt[1] * 100 / max(dt[0], 1):.1f}%) have text ({n(dt[2])} characters). The rest are scans for OCR later.
The table shows how many documents contain some search words.</p>
{table(["Search words", "Documents that match"], [(r[0], r[1]) for r in a.get("doc_text_search", [])], num_cols=(1,))}
""")

    s.append("""<h2>9. More scope and next steps</h2>
<p>These are the next sources and tasks. Each one is public data. None needs a login.</p>
""" + table(["Scope", "What it gives", "Size or effort"], [
        ["Award letters to eprocure", "Award date and contractor for tenders that eprocure shows as in evaluation", "Text PDF; link table exists"],
        ["Values from the full text", "Award amounts and dates from award letters; areas from land awards", "Text exists for about half the files"],
        ["OCR of scanned PDFs", "Text of old orders, agendas, Authority minutes since 1959", "Large; for later"],
        ["Authority meeting agendas", "Decisions of the Authority by date, 1959 to now", "About 470 files, many scanned"],
        ["Land acquisition awards", "Village, award number and year for about 1,800 awards", "Rows exist; PDFs give area and amount"],
        ["Layout plans and KMZ maps", "Boundaries of parks, plots and colonies as map files", "About 700 KMZ files"],
        ["Hindi mirror", "Check which English listings have no Hindi page", "Data exists"],
        ["STF portal and DDA Greens", "Enforcement notices; plantation counts", "Small public pages"],
        ["Change watch", "New tenders, notices and orders each week", "Re-run discovery; seed_queue adds only new keys"],
    ]) + "\n")

    # how to use
    s.append("""<h2>10. How to use the data</h2>
<p>The workspace database <code>ws_trideep</code>, schema <code>dda</code>, holds the data. Metabase shows it as
"Workspace: trideep". The repository <code>s1d-labs/dda</code> holds the code.</p>
""" + table(["Table or view", "Content"], [
        ["pages", "One row per HTML page: language, section, category, title, counts"],
        ["documents", "One row per document: status (stored, broken, unretrievable), size, SHA-256, source page"],
        ["listing_rows", "One row per listing row: serial, title, date, size label, file"],
        ["html_tables", "Every row of every plain HTML table on the site"],
        ["tenders / work_awards / debarments", "Tender notices with NIT, office and year; award letters; debarment orders"],
        ["land_acq_awards", "Land acquisition awards: award number, village, year"],
        ["unauthorised_colonies / delineated_boundaries", "PM-UDAY colony lists and boundary maps"],
        ["colony_boundary_status (view)", "Boundary status of each colony"],
        ["duplicate_files / size_mismatch / broken_links (views)", "Data quality checks"],
        ["eprocure_tenders / tender_links / award_links", "DDA tenders on eprocure and their link to the site rows"],
    ]) + """
<p>To refresh: run <code>python -m analysis.build_db --html DIR</code>, then <code>python -m analysis.analyze</code>, then
<code>python -m analysis.report_html analysis.json report.html</code>.</p>
<h2>11. Limits</h2>
<ul>
<li>Three documents can not be downloaded: the server cuts the transfer or refuses the link.</li>
<li>The eprocure data comes from the team database. Its stage reflects the last time the team scraped that tender.</li>
<li>The login, OTP and captcha portals of DDA are separate systems. We did not access them.</li>
<li>We did not use OCR. Scanned PDF files are stored for later work.</li>
<li>Dates come from the listing text. A row without a printed date has no date.</li>
</ul>
<p class="foot">Source: public pages and files of dda.gov.in, scraped by the s1d labs scrape pool through an India proxy.
Generated by report_html.py from analysis.json.</p>
</div>""")
    return "\n".join(s)


def main():
    src, dst = (sys.argv[1:3] + [None, None])[:2]
    a = json.load(open(src or "reports/analysis.json"))
    repair = a.get("_repair_note") or (
        "The repair pass of 2026-11-05 read all 116 paged listings again. It added 397 pages and 3,988 documents "
        "to the scope. The tender archive now has all 285 pages. 76 internal page links return HTTP 404 on the site.")
    open(dst or "report.html", "w").write(build(a, repair))
    print("wrote", dst or "report.html")


if __name__ == "__main__":
    main()
