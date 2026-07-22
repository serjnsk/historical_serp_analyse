#!/usr/bin/env python3
"""Единый интерфейс: таблица по датам + диаграммы сетей в одном HTML с табами.
Цвет сети общий (HSL->hex). Клик по цветной ячейке в таблице открывает диаграмму этой сети.

in : data/betify_fr_ahrefs.json, data/clusters.json, data/redirects.json
out: data/app.html
"""
import json, subprocess, html, colorsys
from urllib.parse import urlsplit
from collections import defaultdict

DOT = '/opt/homebrew/bin/dot'
TOP_N = 100

SNAP = json.load(open('data/betify_fr_ahrefs.json'))
CL   = json.load(open('data/clusters.json'))
PROBES = json.load(open('data/redirects.json'))['probes']
HOST2C = CL['host2cluster']
CINFO  = {c['id']: c for c in CL['clusters']}

def norm(h):
    h = (h or '').lower()
    return h[4:] if h.startswith('www.') else h

def approved_source(i, url):
    """Строгий источник: стартовый seed (i==0) или корневой путь '/'."""
    if i == 0:
        return True
    return (urlsplit(url or '').path or '/') in ('', '/')

def _elabel0(via, status):
    if via == 'http': return str(status) if status else '3xx'
    if via == 'meta': return 'meta'
    if via == 'js':   return 'JS'
    return via or ''

# A = хосты, чей корень/целевая независимо редиректят (источники строгих рёбер) — для graph-aware
A_SRC = set()
for _s, _rec in PROBES.items():
    ch = _rec.get('chain') or []
    for i in range(len(ch) - 1):
        a, b = norm(ch[i].get('host')), norm(ch[i+1].get('host'))
        if a and b and a != b and approved_source(i, ch[i].get('url')):
            A_SRC.add(a)

def edge_ok(i, url, b):
    """То же правило, что в кластеризации: строгий источник ИЛИ глубокий хоп на члена сети (b in A)."""
    return approved_source(i, url) or (b in A_SRC)

# представитель URL узла (для клика): корень, если он редиректит, иначе любой seed хоста
REP = {}
for _s, _rec in PROBES.items():
    sh = norm(_rec.get('start_host'))
    if sh: REP.setdefault(sh, _rec.get('seed') or f'https://{sh}/')

# точный редиректящий URL узла + детали рёбер (откуда->куда) для аудита
OUTURL = {}
EDGE_DETAIL = defaultdict(list)
for _s, _rec in PROBES.items():
    ch = _rec.get('chain') or []
    for i in range(len(ch) - 1):
        a, b = norm(ch[i].get('host')), norm(ch[i+1].get('host'))
        if a and b and a != b and edge_ok(i, ch[i].get('url'), b):
            fu, tu = ch[i].get('url'), ch[i+1].get('url')
            OUTURL.setdefault(a, fu)
            EDGE_DETAIL[(a, b)].append((fu, tu, _elabel0(ch[i].get('via'), ch[i].get('status'))))

def domain_of(u):
    try: return (urlsplit(u).hostname or '').lower()
    except Exception: return ''

def hsl_hex(cid, l=0.82, s=0.70):
    n = int(cid[1:])
    h = ((n * 137.508) % 360) / 360.0
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return '#%02x%02x%02x' % (int(r*255), int(g*255), int(b*255))

def cluster_of(host):
    return HOST2C.get(norm(host))

# ---------- секция 1: таблица по датам ----------
cols = []
for s in SNAP['snapshots']:
    date = s['snapshot'][:10]
    rows = sorted([r for r in s['rows'] if 'organic' in (r.get('type') or [])],
                  key=lambda r: r.get('position', 999))
    out, seen = [], set()
    for r in rows:
        host = domain_of(r.get('url', ''))
        if not host or host in seen: continue
        seen.add(host)
        out.append((r.get('position'), host, r.get('url', ''), r.get('domain_rating'), cluster_of(host)))
        if len(out) >= TOP_N: break
    cols.append((date, out))

def esc(x): return html.escape(str(x))

grid = []
for date, rows in cols:
    grid.append(f'<div class="col"><div class="colh">{esc(date)}</div>')
    for pos, host, url, dr, cid in rows:
        if cid:
            info = CINFO.get(cid, {})
            term = ', '.join(list((info.get('terminals') or {}).keys())[:2])
            tip = f'{cid} · сеть {info.get("size","?")} хостов → {term} · DR={dr}\n{url}'
            grid.append(f'<div class="cell net" style="background:{hsl_hex(cid)}" '
                        f'data-cid="{cid}" title="{esc(tip)}" onclick="openNet(\'{cid}\')">'
                        f'<span class="r">{pos}</span>{esc(host)}</div>')
        else:
            grid.append(f'<div class="cell" title="DR={dr}\n{esc(url)}">'
                        f'<span class="r">{pos}</span>{esc(host)}</div>')
    grid.append('</div>')

# ---------- секция 2: диаграммы сетей ----------
def elabel(via, status):
    if via == 'http': return str(status) if status else '3xx'
    if via == 'meta': return 'meta'
    if via == 'js':   return 'JS'
    return via or ''

EDGES_ALL = CL.get('edges', [])   # рёбра из clusters.json (редиректы + canonical/hreflang, метки уже слиты)
_LORD = {'301':0,'302':1,'307':2,'308':3,'3xx':4,'meta':5,'JS':6,'canonical':7,'hreflang':8}
def _lsort(labs):
    return sorted(labs, key=lambda x: _LORD.get(x, 99))

def edges_for(members):
    ms = set(members)
    agg = {}
    for e in EDGES_ALL:
        a, b = e['src'], e['dst']
        if a in ms and b in ms:
            agg[(a, b)] = e['via']          # уже список слитых меток
    return agg

def darken(cid, l=0.42):
    return hsl_hex(cid, l=l, s=0.65)

def build_dot(c):
    members = c['members']; cid = c['id']
    agg = edges_for(members)
    outdeg = defaultdict(int); indeg = defaultdict(int)
    for (a, b) in agg:
        outdeg[a] += 1; indeg[b] += 1
    terminals = set(norm(t) for t in (c.get('terminals') or {}))
    fill = hsl_hex(cid)
    L = ['digraph G {', 'rankdir=LR; bgcolor="transparent";',
         f'node [shape=box style="rounded,filled" fillcolor="{fill}" fontname="Helvetica" fontsize=11 margin="0.12,0.06"];',
         'edge [fontname="Helvetica" fontsize=9 color="#666" arrowsize=0.7];']
    for h in members:
        is_term = (outdeg[h] == 0) or (h in terminals)
        pen = '2.4' if is_term else '1'
        border = darken(cid) if is_term else '#9aa3ad'
        url = (OUTURL.get(h) or REP.get(h) or f'https://{h}/').replace('"', '%22')
        L.append(f'"{h}" [label="{esc(h)}" URL="{url}" target="_blank" '
                 f'tooltip="{esc(url)}" color="{border}" penwidth={pen}];')
    drawn = set()
    for (a, b), labs in agg.items():
        if (a, b) in drawn: continue
        fwd = ", ".join(_lsort(labs))
        if (b, a) in agg:                        # встречное ребро -> двойная стрелка
            bwd = ", ".join(_lsort(agg[(b, a)]))
            drawn.add((a, b)); drawn.add((b, a))
            lbl = f'{fwd} →\\n← {bwd}'
            L.append(f'"{a}" -> "{b}" [dir=both label="{lbl}" '
                     f'edgetooltip="{esc(a)} →[{esc(fwd)}]  {esc(b)} →[{esc(bwd)}]"];')
        else:
            drawn.add((a, b))
            det = EDGE_DETAIL.get((a, b), [])
            etip = (f'{det[0][0]}  →  {det[0][1]}' if det else f'{a} → {b}').replace('"', '%22')
            L.append(f'"{a}" -> "{b}" [label="{fwd}" '
                     f'edgetooltip="{esc(etip)}" labeltooltip="{esc(etip)}"];')
    L.append('}')
    return '\n'.join(L)

def render_svg(src):
    p = subprocess.run([DOT, '-Tsvg'], input=src.encode(), capture_output=True)
    svg = p.stdout.decode('utf-8', 'ignore')
    i = svg.find('<svg')
    return svg[i:] if i >= 0 else '<svg></svg>'

PBH = defaultdict(list)   # norm start_host -> [probe recs] (корень + SERP-URL)
for _s, _rec in PROBES.items():
    PBH[norm(_rec.get('start_host'))].append(_rec)

clusters = sorted(CL['clusters'], key=lambda c: c['size'], reverse=True)
tabs, panels = [], []
for c in clusters:
    cid = c['id']
    term = ', '.join(list((c.get('terminals') or {}).keys())[:2]) or '—'
    bet = any('betify' in m for m in c['members'])
    badge = '<span class="bg bet">betify</span>' if bet else ''
    tabs.append(f'<li data-t="{cid}" onclick="showNet(\'{cid}\')">'
                f'<span class="cdot" style="background:{hsl_hex(cid)}"></span>'
                f'<b>{cid}</b> · {c["size"]} хостов {badge}<br><span class="term">→ {esc(term)}</span></li>')
    regs = ', '.join(c.get('regs', []))
    # аудит: сырые цепочки для member-хостов (по каждой пробе: корень и/или SERP-URL)
    ms = set(c['members']); audit = []
    for h in sorted(c['members']):
        for rec in PBH.get(h, []):
            ch = rec.get('chain') or []
            cross = any(norm(ch[i].get('host')) != norm(ch[i+1].get('host')) for i in range(len(ch)-1))
            if not ch or not cross: continue
            steps = []
            for i, x in enumerate(ch):
                via = x.get('via'); st = x.get('status')
                tag = _elabel0(via, st) if via != 'final' else 'финал'
                last = (i == len(ch) - 1)
                nb = norm(ch[i+1].get('host')) if not last else None
                skip = (not last) and (not edge_ok(i, x.get('url'), nb))
                mark = '<span class="skip">↳ прокладка, не ребро</span>' if skip else ''
                cls = 'hop dim' if skip else 'hop'
                steps.append(f'<div class="{cls}"><span class="via">{esc(tag)}</span> '
                             f'<a href="{esc(x.get("url",""))}" target="_blank">{esc(x.get("url",""))}</a> {mark}</div>')
            audit.append(f'<div class="chain"><div class="chost">{esc(h)} '
                         f'<span class="seed">({esc(rec.get("seed",""))})</span></div>{"".join(steps)}</div>')
    audit_html = (f'<details><summary>Проверить: сырые цепочки редиректов ({len(audit)})</summary>'
                  f'<div class="chains">{"".join(audit)}</div></details>') if audit else ''
    panels.append(f'''<div class="panel" id="p-{cid}">
      <h2><span class="cdot big" style="background:{hsl_hex(cid)}"></span>{cid} — {c["size"]} хостов ({len(c.get("regs",[]))} доменов)</h2>
      <div class="pmeta">Конечные адреса: <b>{esc(term)}</b> · Домены: {esc(regs)}</div>
      <div class="svgwrap">{render_svg(build_dot(c))}</div>
      {audit_html}</div>''')

HTML = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>betify — сети конкурентов</title><style>
 html,body{{height:100%;margin:0}}
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#111;display:flex;flex-direction:column;height:100vh;overflow:hidden}}
 .topnav{{flex:0 0 auto;display:flex;gap:4px;align-items:center;padding:8px 14px;border-bottom:1px solid #e3e6ea;background:#fff}}
 .topnav .brand{{font-weight:700;font-size:14px;margin-right:14px}}
 .tab{{padding:6px 14px;border-radius:8px;cursor:pointer;font-size:13px;color:#555}}
 .tab.active{{background:#e3efff;color:#1358a8;font-weight:600}}
 .view{{flex:1;min-height:0;display:none}} .view.show{{display:flex;flex-direction:column}}
 /* ---- таблица ---- */
 .subbar{{flex:0 0 auto;padding:8px 14px;font-size:12px;color:#666}}
 .grid{{flex:1;display:flex;gap:6px;overflow:auto;padding:0 14px 0}}
 .col{{min-width:150px;flex:0 0 auto}}
 .colh{{position:sticky;top:0;background:#fafafa;z-index:1;font-weight:600;font-size:11px;padding:5px 3px;border-bottom:2px solid #ddd;margin-bottom:5px;white-space:nowrap}}
 .cell{{font-size:11px;padding:3px 6px;border-radius:4px;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;background:#fff;border:1px solid #eee}}
 .cell.net{{cursor:pointer;border-color:rgba(0,0,0,.08)}}
 .grid.hling .cell{{opacity:.28;transition:opacity .08s}}
 .grid.hling .cell.hl{{opacity:1}}
 .cell.hl{{outline:2px solid rgba(0,0,0,.6);outline-offset:-2px;font-weight:600;position:relative;z-index:2}}
 .cell .r{{color:#888;font-variant-numeric:tabular-nums;margin-right:5px}}
 /* ---- сети ---- */
 .netwrap{{flex:1;min-height:0;display:flex}}
 .side{{flex:0 0 300px;overflow:auto;border-right:1px solid #e3e6ea;padding:10px;background:#fafbfc}}
 .side .sub{{font-size:11px;color:#777;margin:0 0 8px}}
 ul{{list-style:none;margin:0;padding:0}}
 li{{padding:7px 9px;border-radius:7px;cursor:pointer;font-size:12px;margin-bottom:3px;border:1px solid transparent}}
 li:hover{{background:#eef2f6}} li.active{{background:#e3efff;border-color:#a8ccf5}}
 li .term{{color:#888;font-size:11px}}
 .cdot{{width:11px;height:11px;border-radius:3px;display:inline-block;vertical-align:middle;margin-right:5px;border:1px solid rgba(0,0,0,.15)}}
 .cdot.big{{width:14px;height:14px;margin-right:8px}}
 .bg{{font-size:9px;padding:1px 5px;border-radius:6px}} .bg.bet{{background:#dbeeff;color:#1f6fb2}}
 .main{{flex:1;overflow:auto;padding:18px}}
 .panel{{display:none}} .panel.show{{display:block}}
 .panel h2{{font-size:16px;margin:0 0 4px;display:flex;align-items:center}}
 .pmeta{{font-size:12px;color:#666;margin-bottom:14px;max-width:900px;line-height:1.5}}
 .svgwrap{{overflow:auto;border:1px solid #eee;border-radius:8px;padding:14px;background:#fff}}
 details{{margin-top:14px;font-size:12px}} summary{{cursor:pointer;color:#1358a8;font-weight:600}}
 .chains{{margin-top:8px}}
 .chain{{border-left:3px solid #ddd;padding:4px 0 4px 10px;margin-bottom:10px}}
 .chost{{font-weight:600;font-size:12px;margin-bottom:2px}}
 .hop{{font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:820px}}
 .hop .via{{display:inline-block;min-width:38px;color:#b03a2e;font-weight:600}}
 .hop a{{color:#333;text-decoration:none}} .hop a:hover{{text-decoration:underline}}
 .hop.dim{{opacity:.5}} .hop.dim a{{text-decoration:line-through}}
 .skip{{color:#c00;font-size:10px;margin-left:6px}}
 .chost .seed{{color:#999;font-weight:400;font-size:10px}}
</style></head><body>
<div class="topnav">
 <span class="brand">betify · расследование сетей</span>
 <span class="tab active" id="tab-dates" onclick="view('dates')">Таблица по датам</span>
 <span class="tab" id="tab-nets" onclick="view('nets')">Диаграммы сетей ({len(clusters)})</span>
</div>

<div class="view show" id="view-dates">
 <div class="subbar">{len(cols)} снапшотов, {cols[0][0]} — {cols[-1][0]}. Цвет = подтверждённая сеть по редиректам. Наведение — подсветить всю сеть, клик — её диаграмма.</div>
 <div class="grid" id="tgrid">{''.join(grid)}</div>
</div>

<div class="view" id="view-nets">
 <div class="netwrap">
  <div class="side">
   <div class="sub">{len(clusters)} сетей по активным редиректам (301/302/meta/JS). www и без-www — один узел.</div>
   <ul>{''.join(tabs)}</ul>
  </div>
  <div class="main">{''.join(panels)}</div>
 </div>
</div>

<script>
 function view(v){{
   document.querySelectorAll('.view').forEach(e=>e.classList.remove('show'));
   document.getElementById('view-'+v).classList.add('show');
   document.getElementById('tab-dates').classList.toggle('active', v==='dates');
   document.getElementById('tab-nets').classList.toggle('active', v==='nets');
 }}
 const litems=()=>document.querySelectorAll('.side li');
 function showNet(cid){{
   document.querySelectorAll('.panel').forEach(p=>p.classList.remove('show'));
   const p=document.getElementById('p-'+cid); if(p) p.classList.add('show');
   litems().forEach(i=>i.classList.toggle('active', i.dataset.t===cid));
   const act=document.querySelector('.side li.active'); if(act) act.scrollIntoView({{block:'nearest'}});
 }}
 function openNet(cid){{ view('nets'); showNet(cid); }}
 showNet(document.querySelector('.side li').dataset.t);

 // подсветка всей сети при наведении на её ячейку (таблица по датам)
 (function(){{
   const grid=document.getElementById('tgrid');
   const groups={{}};
   grid.querySelectorAll('.cell.net').forEach(el=>{{ (groups[el.dataset.cid]=groups[el.dataset.cid]||[]).push(el); }});
   let cur=null;
   function clear(){{ if(!cur) return; (groups[cur]||[]).forEach(el=>el.classList.remove('hl')); grid.classList.remove('hling'); cur=null; }}
   grid.addEventListener('mouseover', e=>{{
     const c=e.target.closest('.cell.net');
     if(!c){{ return; }}
     const cid=c.dataset.cid;
     if(cid===cur) return;
     clear(); cur=cid;
     (groups[cid]||[]).forEach(el=>el.classList.add('hl'));
     grid.classList.add('hling');
   }});
   grid.addEventListener('mouseleave', clear);
 }})();
</script>
</body></html>'''

open('data/app.html', 'w').write(HTML)
print('written: data/app.html |', len(cols), 'снапшотов |', len(clusters), 'сетей |', round(len(HTML)/1024), 'KB')
