#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build bike-to-work/index.html from data.json (self-contained, data inlined).

Rebuild after refreshing data.json:  python build.py
"""
import json, io, os, collections, datetime, math

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(io.open(os.path.join(HERE, "data.json"), encoding="utf-8"))

T, Y, C = D["totals"], D["years"], D["couzens"]
A = D["athlete"]
it = lambda n: "{:,}".format(int(round(n))).replace(",", ".")
dc = lambda v, d=1: ("{:.%df}" % d).format(v).replace(".", ",")   # decimale all'italiana

# -------------------------------------------- chart 1: two small multiples per year
# One measure per panel, one axis each. A stacked "commute vs everything else"
# buries the subject: the commute segment is a tenth of the bar.
YRS = [y for y in Y if y["allHours"] > 0]

def year_panel(vals, fmt, unit, aria, ticks_at):
    BW, GAP, PAD, TOP = 34, 13, 40, 26
    w = PAD + len(YRS) * (BW + GAP) - GAP + 8
    base, h = 150, 116
    mx = max(vals) or 1
    out = []
    for v in ticks_at:
        if v > mx * 1.02: continue
        yy = base - v / mx * h
        out.append(f'<line class="grid" x1="{PAD-8}" y1="{yy:.1f}" x2="{w}" y2="{yy:.1f}"></line>'
                   f'<text class="ax r" x="{PAD-13}" y="{yy+4:.1f}">{v}</text>')
    for i, (y, v) in enumerate(zip(YRS, vals)):
        x = PAD + i * (BW + GAP)
        bh = v / mx * h
        if v > 0:
            out.append(f'<rect class="mk comm" x="{x}" y="{base-bh:.1f}" width="{BW}" height="{bh:.1f}" rx="4"'
                       f' data-t="{y["year"]}|{fmt(v)} {unit} · {y["n"]} tratte"></rect>')
            out.append(f'<text class="dl" x="{x+BW/2}" y="{base-bh-6:.1f}">{fmt(v)}</text>')
        out.append(f'<text class="ax yr" x="{x+BW/2}" y="{base+16}">{str(y["year"])[2:]}</text>')
    return f'<svg viewBox="0 0 {w} {170}" role="img" aria-label="{aria}">{"".join(out)}</svg>'

CHART_YEARS = year_panel([y["commuteHours"] for y in YRS], lambda v: f"{v:.0f}", "ore",
                         "Ore di commute per anno", (0, 20, 40, 60, 80))
CHART_SHARE = year_panel([round(y["commuteHours"] / y["allHours"] * 100, 1) for y in YRS],
                         lambda v: f"{v:.0f}", "% del volume",
                         "Quota del volume totale coperta dal commute, per anno", (0, 5, 10, 15))

# ---------------------------------------------------------------- chart 2: departure hour
hh = collections.Counter(int(c["hour"]) for c in D["commutes"])
MH = max(hh.values())
W2, H2 = 640, 170
b2 = []
hours = list(range(4, 21))
bw2 = (W2 - 50) / len(hours) - 6
for i, h in enumerate(hours):
    n = hh.get(h, 0)
    x = 44 + i * ((W2 - 50) / len(hours))
    ht = n / MH * 118
    if n:
        b2.append(f'<rect class="mk comm" x="{x:.1f}" y="{140-ht:.1f}" width="{bw2:.1f}" height="{ht:.1f}" rx="4"'
                  f' data-t="ore {h}:00|{n} partenze"></rect>')
    if h % 2 == 0:
        b2.append(f'<text class="ax" x="{x+bw2/2:.1f}" y="{156}">{h}</text>')
for v in (0, 10, 20, 30):
    if v > MH: continue
    yy = 140 - v / MH * 118
    b2.insert(0, f'<line class="grid" x1="38" y1="{yy:.1f}" x2="{W2}" y2="{yy:.1f}"></line>'
                 f'<text class="ax r" x="32" y="{yy+4:.1f}">{v}</text>')
CHART_HOUR = f'<svg viewBox="0 0 {W2} {H2}" role="img" aria-label="Orario di partenza dei commute">{"".join(b2)}</svg>'

# ---------------------------------------------------------------- chart 3: cumulative hours
cum, tot = [], 0.0
for c in sorted(D["commutes"], key=lambda r: r["date"]):
    tot += c["min"] / 60
    cum.append((c["date"], tot))
d0 = datetime.date.fromisoformat(cum[0][0]).toordinal()
d1 = datetime.date.fromisoformat(cum[-1][0]).toordinal()
W3, H3 = 640, 190
def px(ds): return 44 + (datetime.date.fromisoformat(ds).toordinal() - d0) / (d1 - d0) * (W3 - 56)
def py(v):  return 158 - v / tot * 132
pts = " ".join(f"{px(d):.1f},{py(v):.1f}" for d, v in cum)
g3 = []
for v in (0, 50, 100, 150, 200, 250):
    if v > tot: continue
    g3.append(f'<line class="grid" x1="38" y1="{py(v):.1f}" x2="{W3}" y2="{py(v):.1f}"></line>'
              f'<text class="ax r" x="32" y="{py(v)+4:.1f}">{v}</text>')
for yr in range(2019, 2027):
    try: x = px(f"{yr}-01-01")
    except Exception: continue
    if 44 <= x <= W3:
        g3.append(f'<text class="ax" x="{x:.1f}" y="174">{yr}</text>')
CHART_CUM = (f'<svg viewBox="0 0 {W3} {H3}" role="img" aria-label="Ore di commute cumulate nel tempo">'
             f'{"".join(g3)}<polygon class="area" points="{px(cum[0][0]):.1f},158 {pts} {px(cum[-1][0]):.1f},158"></polygon>'
             f'<polyline class="line reveal-line" points="{pts}"></polyline></svg>')

# ---------------------------------------------------------------- meters
def meter(pct, cls="comm"):
    return f'<div class="meter"><i class="{cls}" style="--w:{min(pct,100):.1f}%"></i></div>'

B40 = C["fromBaseline"]["40"]
RUN = D["sports"].get("Run", {"n": 0, "hours": 0, "km": 0})
YMAP = {y["year"]: y for y in Y}
# full-season reference: the last two complete years
MAINT = (YMAP[2024]["commuteHours"] + YMAP[2025]["commuteHours"]) / 2
YTD26 = (datetime.date(2026, 7, 28) - datetime.date(2026, 1, 1)).days + 1
ANN26 = YMAP[2026]["commuteHours"] / YTD26 * 365
YEARS_TO_50 = 50 - A["age"]
DECLINE = YEARS_TO_50 / 10 * C["declinePerDecade"]
GAIN50 = YEARS_TO_50 * ANN26 * C["rate"]
PROJ50 = A["vo2max"] - DECLINE + GAIN50

run_rows = "".join(
    f'<tr><td>{c["date"]}</td><td>{["lun","mar","mer","gio","ven","sab","dom"][c["dow"]]}</td>'
    f'<td class="n">{c["km"]:.1f}</td><td class="n">{c["min"]}′</td><td>{c["name"] or "—"}</td></tr>'
    for c in sorted(D["runCommutes"], key=lambda r: r["date"]))

tbl_rows = "".join(
    f'<tr><td>{c["date"]}</td><td>{c["sport"]}</td><td class="n">{c["km"]:.1f}</td>'
    f'<td class="n">{c["min"]}</td><td class="n">{c["elev"]}</td><td class="n">{c["tss"]}</td></tr>'
    for c in sorted(D["commutes"], key=lambda r: r["date"], reverse=True))

year_rows = "".join(
    f'<tr><td>{y["year"]}</td><td class="n">{y["allHours"]:.0f}</td><td class="n">{y["commuteHours"]:.1f}</td>'
    f'<td class="n">{(y["commuteHours"]/y["allHours"]*100 if y["allHours"] else 0):.1f}%</td>'
    f'<td class="n">{y["n"]}</td><td class="n">{it(y["km"])}</td></tr>' for y in YRS)

HTML = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bike to work — {T["hours"]:.0f} ore per andare in ufficio</title>
<meta name="description" content="Ogni tratta casa-ufficio in bici e di corsa dal 2019 al 2026, ricostruita dagli stream GPS di intervals.icu, misurata contro il modello di Alan Couzens e i suoi obiettivi 50-at-50.">
<meta property="og:title" content="Bike to work — {T["hours"]:.0f} ore per andare in ufficio">
<meta property="og:description" content="{T["n"]} tratte, {it(T["km"])} km, {it(T["elev"])} m di dislivello. Quanta della forma fisica serve per un VO2max 50 e coperta solo andando al lavoro?">
<style>
:root{{
  color-scheme: light;
  --bg:#f9f9f7; --surface:#fcfcfb; --surface-2:#f2f1ec;
  --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --rule:rgba(11,11,11,.10);
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --good:#0ca30c;
  --rest:#dedcd3;
}}
@media (prefers-color-scheme: dark){{
  :root:where(:not([data-theme=light])){{
    color-scheme: dark;
    --bg:#0d0d0d; --surface:#1a1a19; --surface-2:#232322;
    --ink:#fff; --ink-2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --rule:rgba(255,255,255,.10);
    --s1:#3987e5; --s2:#d95926; --s3:#199e70; --good:#0ca30c;
    --rest:#33332f;
  }}
}}
:root[data-theme=dark]{{
  color-scheme: dark;
  --bg:#0d0d0d; --surface:#1a1a19; --surface-2:#232322;
  --ink:#fff; --ink-2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --rule:rgba(255,255,255,.10);
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --good:#0ca30c;
  --rest:#33332f;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:16px;line-height:1.55;
  max-width:860px;margin:0 auto;padding:38px 20px 90px}}
h1{{font-size:2.15rem;line-height:1.08;letter-spacing:-.02em;font-weight:800}}
h2{{font-size:1.12rem;font-weight:700;letter-spacing:-.01em;margin:0 0 4px}}
h3{{font-size:.78rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}}
p{{color:var(--ink-2)}}
a{{color:var(--s1)}}
.kicker{{font-size:.74rem;text-transform:uppercase;letter-spacing:.16em;color:var(--muted);font-weight:600}}
.lede{{margin-top:12px;font-size:1.05rem;max-width:62ch}}
section{{margin-top:44px}}
.sec-head{{border-top:1px solid var(--rule);padding-top:14px;margin-bottom:16px}}
.sec-head p{{font-size:.92rem;max-width:66ch;margin-top:4px}}

/* hero */
.hero{{margin-top:26px;background:var(--surface);border:1px solid var(--rule);border-radius:14px;padding:24px 22px}}
.hero .fig{{font-size:4.4rem;line-height:.92;font-weight:800;letter-spacing:-.04em;color:var(--s1)}}
.hero .fig small{{font-size:.28em;font-weight:700;letter-spacing:.04em;color:var(--ink-2);margin-left:6px}}
.hero .cap{{color:var(--ink-2);font-size:.95rem;margin-top:8px;max-width:52ch}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(122px,1fr));gap:1px;
  background:var(--rule);border:1px solid var(--rule);border-radius:12px;overflow:hidden;margin-top:18px}}
.tile{{background:var(--surface);padding:13px 14px}}
.tile .v{{font-size:1.45rem;font-weight:700;letter-spacing:-.02em;font-variant-numeric:tabular-nums}}
.tile .k{{font-size:.7rem;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);margin-top:2px}}

/* charts */
figure{{background:var(--surface);border:1px solid var(--rule);border-radius:12px;padding:16px 14px 12px;margin-top:12px}}
figcaption{{font-size:.8rem;color:var(--muted);margin-top:8px;padding:0 4px}}
svg{{width:100%;height:auto;display:block;overflow:visible}}
.grid{{stroke:var(--grid);stroke-width:1}}
.ax{{fill:var(--muted);font-size:11px;text-anchor:middle;font-variant-numeric:tabular-nums}}
.ax.r{{text-anchor:end}}
.dl{{fill:var(--ink-2);font-size:11px;font-weight:700;text-anchor:middle;font-variant-numeric:tabular-nums}}
.mk{{stroke:var(--surface);stroke-width:2}}
.mk.comm{{fill:var(--s1)}}
.mk.rest{{fill:var(--rest)}}
.mk:hover{{filter:brightness(1.12)}}
.line{{fill:none;stroke:var(--s1);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}}
.area{{fill:var(--s1);opacity:.13}}
.multi{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}}
.multi figure{{margin-top:0}}
.pt{{margin:0 0 6px 4px}}
.note{{font-size:.8rem;color:var(--muted);margin-top:8px}}
.ax.yr{{font-size:10px}}
.legend{{display:flex;gap:16px;flex-wrap:wrap;font-size:.78rem;color:var(--ink-2);padding:0 4px;margin-top:10px}}
.legend i{{width:10px;height:10px;border-radius:3px;display:inline-block;margin-right:6px;vertical-align:-1px}}

/* meters */
.meter{{height:9px;background:var(--surface-2);border-radius:5px;overflow:hidden;margin-top:7px}}
.meter i{{display:block;height:100%;width:var(--w);border-radius:5px;background:var(--s1)}}
.meter i.good{{background:var(--good)}}
.meter i.s2{{background:var(--s2)}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-top:12px}}
.card{{background:var(--surface);border:1px solid var(--rule);border-radius:12px;padding:15px 16px}}
.card .v{{font-size:1.9rem;font-weight:800;letter-spacing:-.03em;font-variant-numeric:tabular-nums}}
.card .k{{font-size:.72rem;text-transform:uppercase;letter-spacing:.09em;color:var(--muted)}}
.card .sub{{font-size:.82rem;color:var(--ink-2);margin-top:8px}}
.badge{{display:inline-block;font-size:.68rem;font-weight:700;letter-spacing:.07em;text-transform:uppercase;
  color:var(--good);border:1px solid currentColor;border-radius:99px;padding:1px 7px;margin-left:7px;vertical-align:2px}}

/* tables */
table{{width:100%;border-collapse:collapse;font-size:.86rem;font-variant-numeric:tabular-nums}}
th,td{{text-align:left;padding:7px 9px;border-bottom:1px solid var(--rule)}}
th{{font-size:.68rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:700}}
td.n,th.n{{text-align:right}}
details{{margin-top:12px;background:var(--surface);border:1px solid var(--rule);border-radius:12px;padding:4px 14px 6px}}
summary{{cursor:pointer;font-size:.85rem;font-weight:600;padding:10px 0;color:var(--ink-2)}}
.scroll{{max-height:380px;overflow:auto;margin-bottom:10px}}

/* story card */
.story-wrap{{display:flex;justify-content:center;margin-top:14px}}
.story{{width:min(330px,88vw);aspect-ratio:9/16;border-radius:20px;padding:26px 22px;
  background:linear-gradient(160deg,#12213a 0%,#1a1a19 58%,#2b1509 100%);
  color:#fff;display:flex;flex-direction:column;justify-content:space-between;
  box-shadow:0 18px 40px rgba(0,0,0,.28);border:1px solid rgba(255,255,255,.09)}}
.story .top{{font-size:.68rem;letter-spacing:.2em;text-transform:uppercase;opacity:.62}}
.story .big{{font-size:3.5rem;font-weight:800;line-height:.9;letter-spacing:-.04em}}
.story .big span{{display:block;font-size:.24em;font-weight:600;letter-spacing:.1em;opacity:.7;margin-top:9px;text-transform:uppercase}}
.story .rows{{display:flex;flex-direction:column;gap:9px;font-size:.82rem}}
.story .row{{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid rgba(255,255,255,.13);padding-bottom:7px}}
.story .row b{{font-variant-numeric:tabular-nums;font-weight:700}}
.story .foot{{font-size:.66rem;opacity:.55;letter-spacing:.06em}}

.tip{{position:fixed;z-index:40;pointer-events:none;background:var(--ink);color:var(--bg);
  font-size:.76rem;padding:6px 9px;border-radius:7px;opacity:0;transition:opacity .12s;max-width:220px;line-height:1.35}}
.tip b{{display:block;font-size:.68rem;opacity:.75;font-weight:600}}
.foot{{margin-top:52px;border-top:1px solid var(--rule);padding-top:16px;font-size:.78rem;color:var(--muted)}}
.foot a{{color:var(--muted)}}

/* reveal: fires ONCE per element, never re-armed on touch/scroll */
.reveal{{opacity:0;transform:translateY(10px)}}
.reveal.in{{opacity:1;transform:none;transition:opacity .5s ease,transform .5s ease}}
.reveal-line{{stroke-dasharray:var(--len);stroke-dashoffset:var(--len)}}
.reveal-line.in{{stroke-dashoffset:0;transition:stroke-dashoffset 1.15s ease-out}}
.meter i{{width:0}}
.meter.in i{{width:var(--w);transition:width .9s cubic-bezier(.22,.8,.3,1)}}
@media (prefers-reduced-motion: reduce){{
  .reveal,.reveal.in{{opacity:1;transform:none;transition:none}}
  .reveal-line{{stroke-dasharray:none;stroke-dashoffset:0;transition:none}}
  .meter i{{width:var(--w);transition:none}}
}}
@media (max-width:620px){{
  .multi{{grid-template-columns:1fr}}
  body{{padding:26px 15px 70px;font-size:15px}}
  h1{{font-size:1.7rem}}
  .hero .fig{{font-size:3.2rem}}
}}
</style>
</head>
<body>

<p class="kicker">Michele Merelli · dati intervals.icu · aggiornato {D["generated"]}</p>
<h1>{T["hours"]:.0f} ore per andare<br>in ufficio</h1>
<p class="lede">Ogni tratta casa&ndash;lavoro fatta in bici o di corsa dal 2019 a oggi, ritrovata negli stream GPS
e poi misurata contro il modello di <a href="https://www.alancouzens.com/blog/healthy_aging.html" target="_blank" rel="noopener">Alan Couzens</a>:
quanta della forma fisica che serve per un VO<sub>2</sub>max di 50 &egrave; coperta <em>solo</em> dal tragitto per l'ufficio?</p>

<div class="hero reveal">
  <div class="fig">{T["hours"]:.0f}<small>ore</small></div>
  <div class="cap">{T["n"]} tratte casa&ndash;ufficio, {it(T["km"])} km, {it(T["elev"])} m di dislivello,
  {it(T["kj"])} kJ spinti nei pedali. Media per tratta: {T["avgKm"]} km, {T["avgMin"]} minuti, {T["avgElev"]} m di salita.</div>
  <div class="tiles">
    <div class="tile"><div class="v">{T["n"]}</div><div class="k">tratte</div></div>
    <div class="tile"><div class="v">{it(T["km"])}</div><div class="k">km</div></div>
    <div class="tile"><div class="v">{it(T["elev"])}</div><div class="k">m saliti</div></div>
    <div class="tile"><div class="v">{it(T["tss"])}</div><div class="k">TSS</div></div>
    <div class="tile"><div class="v">{RUN["n"]}</div><div class="k">a piedi</div></div>
  </div>
</div>

<section>
  <div class="sec-head">
    <h3>Metodo</h3>
    <h2>Come si trova un commute che nessuno ha mai etichettato</h2>
    <p>Nessuna attivit&agrave; ha il flag <code>commute</code>. Sono stati scaricati gli stream di latitudine
    di tutte le uscite outdoor e raggruppati i punti di inizio e fine. Ne escono tre luoghi netti:
    <b>casa</b> a 45.806, <b>Bergamo citt&agrave;</b> a 45.687, e un terzo punto strettissimo &mdash;
    <b>45.6594&ndash;45.6605</b>, una finestra di 150 metri su cui 99 uscite invertono la marcia.
    Quello &egrave; l'ufficio. Un commute &egrave; una tratta punto-a-punto casa&harr;ufficio, oppure un anello
    da casa la cui latitudine minima cade dentro quella finestra. I nomi che avevi gi&agrave; messo
    &mdash; <em>Bike 2 Work</em>, <em>Run to work</em>, <em>Ganda to Work</em> &mdash; confermano la classificazione.</p>
  </div>
</section>

<section>
  <div class="sec-head">
    <h3>Storia</h3>
    <h2>Sette anni, una quota stabile attorno al 10%</h2>
    <p>Il commute non &egrave; mai stato il grosso del volume: vale un decimo dell'allenamento totale,
    con lo stacco netto nel 2023 quando l'ufficio si sposta a sud di Bergamo.</p>
  </div>
  <div class="multi">
    <figure class="reveal">
      <h3 class="pt">Ore di commute</h3>
      {CHART_YEARS}
      <figcaption>Ore all'anno spese ad andare al lavoro.</figcaption>
    </figure>
    <figure class="reveal">
      <h3 class="pt">Quota sul volume totale</h3>
      {CHART_SHARE}
      <figcaption>Percento delle ore di allenamento dell'anno.</figcaption>
    </figure>
  </div>
  <p class="note">2022 &egrave; assente dall'archivio intervals.icu; 2026 &egrave; parziale (fino al 28 luglio).</p>
  <figure class="reveal">
    {CHART_CUM}
    <figcaption>Ore di commute cumulate. La pendenza si impenna dal 2023 e non si &egrave; pi&ugrave; appiattita.</figcaption>
  </figure>
  <figure class="reveal">
    {CHART_HOUR}
    <figcaption>Ora di partenza. Il picco &egrave; alle 6 del mattino: il commute &egrave; quasi sempre l'andata, con il rientro fatto altrimenti.</figcaption>
  </figure>
  <details>
    <summary>Tabella per anno</summary>
    <table><thead><tr><th>anno</th><th class="n">ore totali</th><th class="n">ore commute</th><th class="n">quota</th><th class="n">tratte</th><th class="n">km</th></tr></thead>
    <tbody>{year_rows}</tbody></table>
  </details>
</section>

<section>
  <div class="sec-head">
    <h3>Il modello</h3>
    <h2>Couzens: mezzo punto di VO<sub>2</sub>max ogni 100 ore</h2>
    <p>La regola spannometrica di Couzens &egrave; <b>+0,5 ml/kg/min ogni 100 ore</b> di lavoro aerobico,
    e <b>100 ore all'anno</b> come dose che a 30&ndash;40 anni annulla il calo fisiologico di 5 ml/kg/min per decennio.
    Due domande diverse, due risposte diverse.</p>
  </div>

  <div class="cards">
    <div class="card reveal">
      <div class="k">Costruzione</div>
      <div class="v">{B40["commutePct"]:.0f}%</div>
      {meter(B40["commutePct"])}
      <div class="sub">della strada da un VO<sub>2</sub>max sedentario (40) fino a 50.
      Servono {it(B40["hoursNeeded"])} ore: il commute ne ha messe {T["hours"]:.0f}, cio&egrave; <b>+{dc(C["vo2FromCommute"], 2)} ml/kg/min</b>.</div>
    </div>
    <div class="card reveal">
      <div class="k">Mantenimento &middot; 2024&ndash;25</div>
      <div class="v">{MAINT:.0f}%</div>
      {meter(MAINT)}
      <div class="sub">della dose annua da 100 ore che tiene il VO<sub>2</sub>max piatto per sempre.
      Andare al lavoro in bici copre da solo tre quarti dell'antidoto all'invecchiamento aerobico.</div>
    </div>
    <div class="card reveal">
      <div class="k">Controprova</div>
      <div class="v">{C["predictedVo2From40"]}</div>
      {meter(95, "s2")}
      <div class="sub">il VO<sub>2</sub>max che il modello predice da {it(D["career"]["hours"])} ore totali in archivio.
      Garmin ne misura <b>{A["vo2max"]}</b>: la regola della bustina sbaglia di tre punti.</div>
    </div>
  </div>

  <details>
    <summary>Le tre ipotesi di partenza</summary>
    <table><thead><tr><th>baseline</th><th class="n">ore per arrivare a 50</th><th class="n">coperte dal commute</th><th class="n">coperte da tutto</th></tr></thead>
    <tbody>
      {"".join(f'<tr><td>VO2max {b}</td><td class="n">{it(v["hoursNeeded"])}</td><td class="n">{v["commutePct"]:.1f}%</td><td class="n">{v["careerPct"]}%</td></tr>' for b, v in sorted(C["fromBaseline"].items()))}
    </tbody></table>
  </details>
</section>

<section>
  <div class="sec-head">
    <h3>50 at 50</h3>
    <h2>I tre bersagli di Couzens, con diciannove anni di anticipo</h2>
    <p>Couzens propone tre soglie da centrare a cinquant'anni: VO<sub>2</sub>max sopra 50,
    frequenza a riposo sotto 50, HRV sopra 50. A 31 anni sono gi&agrave; tutte e tre dietro le spalle.</p>
  </div>
  <div class="cards">
    <div class="card reveal"><div class="k">VO<sub>2</sub>max <span class="badge">superato</span></div>
      <div class="v">{A["vo2max"]}</div>{meter(100, "good")}
      <div class="sub">bersaglio &gt; 50 &middot; margine +{A["vo2max"]-50}</div></div>
    <div class="card reveal"><div class="k">FC a riposo <span class="badge">superato</span></div>
      <div class="v">{A["restingHR"]}</div>{meter(100, "good")}
      <div class="sub">bersaglio &lt; 50 &middot; margine &minus;{50-A["restingHR"]} bpm</div></div>
    <div class="card reveal"><div class="k">HRV <span class="badge">superato</span></div>
      <div class="v">{A["hrv"]}</div>{meter(100, "good")}
      <div class="sub">bersaglio &gt; 50 ms &middot; margine +{A["hrv"]-50} ms</div></div>
  </div>
  <p class="sub" style="font-size:.84rem;color:var(--muted);margin-top:12px">
    Proiezione al 2045: con il solo commute ({ANN26:.0f} h/anno, il passo 2026) il modello d&agrave;
    &minus;{dc(DECLINE)} di calo contro +{dc(GAIN50)} di stimolo,
    cio&egrave; circa <b>{PROJ50:.0f} a cinquant'anni</b>. Il 62 di oggi resta comunque una stima da orologio, e
    <a href="https://x.com/Alan_Couzens/status/1721903401897001153/photo/1" target="_blank" rel="noopener">Couzens stesso avverte</a>
    che si gonfia quando l'allenamento &egrave; intenso.</p>
</section>

<section>
  <div class="sec-head">
    <h3>A piedi</h3>
    <h2>Le volte in cui il commute si &egrave; fatto correndo</h2>
    <p>{RUN["n"]} tratte, {RUN["hours"]:.1f} ore, {RUN["km"]} km.</p>
  </div>
  <figure style="padding:4px 6px 6px">
    <table><thead><tr><th>data</th><th>g</th><th class="n">km</th><th class="n">durata</th><th>attivit&agrave;</th></tr></thead>
    <tbody>{run_rows}</tbody></table>
  </figure>
</section>

<section>
  <div class="sec-head">
    <h3>Story</h3>
    <h2>La versione da schermo verticale</h2>
    <p>Anteprima 9:16 pronta da screenshottare.</p>
  </div>
  <div class="story-wrap"><div class="story reveal">
    <div class="top">bike to work &middot; 2019&ndash;2026</div>
    <div class="big">{T["hours"]:.0f}<span>ore per andare in ufficio</span></div>
    <div class="rows">
      <div class="row"><span>tratte</span><b>{T["n"]}</b></div>
      <div class="row"><span>chilometri</span><b>{it(T["km"])}</b></div>
      <div class="row"><span>dislivello</span><b>{it(T["elev"])} m</b></div>
      <div class="row"><span>VO<sub>2</sub>max verso 50</span><b>{B40["commutePct"]:.0f}%</b></div>
      <div class="row"><span>dose annua anti-et&agrave;</span><b>{MAINT:.0f}%</b></div>
    </div>
    <div class="foot">intervals.icu &times; modello Couzens</div>
  </div></div>
</section>

<section>
  <div class="sec-head"><h3>Dati</h3><h2>Tutte le tratte</h2></div>
  <details>
    <summary>Apri le {T["n"]} tratte</summary>
    <div class="scroll"><table><thead><tr><th>data</th><th>sport</th><th class="n">km</th><th class="n">min</th><th class="n">m D+</th><th class="n">TSS</th></tr></thead>
    <tbody>{tbl_rows}</tbody></table></div>
  </details>
</section>

<div class="foot">
  Fonti del modello:
  <a href="https://www.alancouzens.com/blog/healthy_aging.html" target="_blank" rel="noopener">Healthy Aging</a> &middot;
  <a href="https://alancouzens.com/blog/VO2Scores.html" target="_blank" rel="noopener">VO2 Scores</a> &middot;
  <a href="https://simplifaster.com/articles/how-trainable-is-vo2-max/" target="_blank" rel="noopener">How trainable is VO2max</a> &middot;
  <a href="https://x.com/Alan_Couzens" target="_blank" rel="noopener">@Alan_Couzens</a><br>
  Dati grezzi: intervals.icu, atleta i302515 &mdash; {it(D["career"]["hours"])} ore in archivio dal {D["career"]["firstYear"]}, 2022 mancante.<br>
  <a href="../">&larr; indice</a> &middot; <a href="../diario-di-un-unno/">Diario di un Unno</a> &middot; <a href="https://ciclopodistica.pages.dev/">Gazzaniga&ndash;Orezzo</a>
</div>

<div class="tip" id="tip"></div>

<script>
(function(){{
  var reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

  // line-draw needs its own length before it can be animated
  document.querySelectorAll('.reveal-line').forEach(function(el){{
    try {{ el.style.setProperty('--len', el.getTotalLength()); }} catch(e) {{}}
  }});

  // Reveal each element exactly once, then stop observing it. Nothing here
  // listens to scroll, touch or resize, so an animation can never re-run.
  var targets = document.querySelectorAll('.reveal,.reveal-line,.meter');
  if (reduce || !('IntersectionObserver' in window)) {{
    targets.forEach(function(el){{ el.classList.add('in'); }});
  }} else {{
    var io = new IntersectionObserver(function(entries){{
      entries.forEach(function(e){{
        if (!e.isIntersecting) return;
        e.target.classList.add('in');
        io.unobserve(e.target);          // one-shot: never re-armed
      }});
    }}, {{ rootMargin: '0px 0px -8% 0px', threshold: 0.12 }});
    targets.forEach(function(el){{ io.observe(el); }});
  }}

  // tooltips
  var tip = document.getElementById('tip');
  function show(e, txt){{
    var p = txt.split('|');
    tip.innerHTML = '<b>' + p[0] + '</b>' + (p[1] || '');
    tip.style.opacity = 1;
    var x = e.clientX + 14, y = e.clientY - 10;
    if (x + 230 > innerWidth) x = e.clientX - 230;
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  }}
  document.querySelectorAll('svg .mk').forEach(function(m){{
    var t = m.getAttribute('data-t'); if (!t) return;
    m.addEventListener('mousemove', function(e){{ show(e, t); }});
    m.addEventListener('mouseleave', function(){{ tip.style.opacity = 0; }});
    m.addEventListener('touchstart', function(e){{ show(e.touches[0], t); }}, {{passive:true}});
  }});
  document.addEventListener('touchend', function(){{ tip.style.opacity = 0; }}, {{passive:true}});
}})();
</script>
</body>
</html>
"""

out = os.path.join(HERE, "index.html")
io.open(out, "w", encoding="utf-8").write(HTML)
print("wrote", out, "%.1f KB" % (len(HTML) / 1024))
print("commutes", T["n"], "hours", T["hours"])
