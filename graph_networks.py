#!/usr/bin/env python3
"""Блок-схемы сетей конкурентов: по каждому кластеру редиректов строим ориентированный граф
(домен -> домен, подпись = тип редиректа), рендерим Graphviz dot в SVG и собираем в HTML с вкладками.

usage: graph_networks.py
in : data/clusters.json, data/redirects.json
out: data/networks_graphs.html
"""
import json, subprocess, html
from collections import defaultdict

DOT = '/opt/homebrew/bin/dot'
CL  = json.load(open('data/clusters.json'))
RED = json.load(open('data/redirects.json'))

def elabel(via, status):
    if via == 'http': return str(status) if status else '3xx'
    if via == 'meta': return 'meta'
    if via == 'js':   return 'JS'
    return via or ''

def edges_for(members):
    ms = set(members)
    agg = {}  # (s,d) -> set(labels)
    for h in members:
        chain = (RED.get(h) or {}).get('chain') or []
        for i in range(len(chain) - 1):
            a, b = chain[i].get('host'), chain[i+1].get('host')
            if a and b and a != b and a in ms and b in ms:
                lab = elabel(chain[i].get('via'), chain[i].get('status'))
                agg.setdefault((a, b), set()).add(lab)
    return agg

def build_dot(c):
    members = c['members']
    agg = edges_for(members)
    outdeg = defaultdict(int); indeg = defaultdict(int)
    for (a, b) in agg:
        outdeg[a] += 1; indeg[b] += 1
    terminals = set((c.get('terminals') or {}).keys())
    L = ['digraph G {', 'rankdir=LR; bgcolor="transparent";',
         'node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=11 margin="0.12,0.06"];',
         'edge [fontname="Helvetica" fontsize=9 color="#666" arrowsize=0.7];']
    for h in members:
        is_term = (outdeg[h] == 0) or (h in terminals)
        is_src  = indeg[h] == 0
        bet = 'betify' in h
        if is_term:
            fill, pen, col = '#ffd5cc', '#d43f2a', '2'
        elif bet:
            fill, pen, col = '#dbeeff', '#4a90d9', '1'
        else:
            fill, pen, col = '#eef0f2', '#b7bec6', '1'
        role = ' ⬤ финал' if is_term else (' ▸ вход' if is_src else '')
        lbl = html.escape(h) + (f'\\n{role.strip()}' if role else '')
        L.append(f'"{h}" [label="{lbl}" fillcolor="{fill}" color="{pen}" penwidth={col}];')
    for (a, b), labs in agg.items():
        lab = '/'.join(sorted(labs))
        L.append(f'"{a}" -> "{b}" [label="{lab}"];')
    L.append('}')
    return '\n'.join(L)

def render_svg(dot_src):
    p = subprocess.run([DOT, '-Tsvg'], input=dot_src.encode(), capture_output=True)
    svg = p.stdout.decode('utf-8', 'ignore')
    i = svg.find('<svg')
    return svg[i:] if i >= 0 else '<svg></svg>'

clusters = sorted(CL['clusters'], key=lambda c: c['size'], reverse=True)

tabs, panels = [], []
for c in clusters:
    cid = c['id']
    term = ', '.join(list((c.get('terminals') or {}).keys())[:2]) or '—'
    bet = any('betify' in m for m in c['members'])
    badge = '<span class="bg bet">betify</span>' if bet else ''
    tabs.append(f'<li data-t="{cid}"><b>{cid}</b> · {c["size"]} хостов {badge}<br><span class="term">→ {html.escape(term)}</span></li>')
    svg = render_svg(build_dot(c))
    regs = ', '.join(c.get('regs', []))
    panels.append(f'''<div class="panel" id="p-{cid}">
      <h2>{cid} — сеть из {c["size"]} хостов ({len(c.get("regs",[]))} доменов)</h2>
      <div class="meta">Конечные адреса: <b>{html.escape(term)}</b> · Домены: {html.escape(regs)}</div>
      <div class="svgwrap">{svg}</div></div>''')

HTML = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>Сети конкурентов betify — блок-схемы редиректов</title><style>
 html,body{{height:100%;margin:0}}
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#111;display:flex;height:100vh;overflow:hidden}}
 .side{{flex:0 0 300px;overflow:auto;border-right:1px solid #e3e6ea;padding:12px;background:#fafbfc}}
 .side h1{{font-size:14px;margin:0 0 4px}} .side .sub{{font-size:11px;color:#777;margin-bottom:10px}}
 ul{{list-style:none;margin:0;padding:0}}
 li{{padding:8px 10px;border-radius:7px;cursor:pointer;font-size:12px;margin-bottom:3px;border:1px solid transparent}}
 li:hover{{background:#eef2f6}} li.active{{background:#e3efff;border-color:#a8ccf5}}
 li .term{{color:#888;font-size:11px}}
 .bg{{font-size:9px;padding:1px 5px;border-radius:6px;vertical-align:middle}}
 .bg.bet{{background:#dbeeff;color:#1f6fb2}}
 .main{{flex:1;overflow:auto;padding:20px}}
 .panel{{display:none}} .panel.show{{display:block}}
 .panel h2{{font-size:16px;margin:0 0 4px}}
 .meta{{font-size:12px;color:#666;margin-bottom:14px;max-width:900px;line-height:1.5}}
 .svgwrap{{overflow:auto;border:1px solid #eee;border-radius:8px;padding:14px;background:#fff}}
 .legend{{font-size:11px;color:#777;margin-top:10px}}
 .legend span{{display:inline-flex;align-items:center;gap:5px;margin-right:16px}}
 .dot{{width:12px;height:12px;border-radius:3px;display:inline-block;border:1px solid rgba(0,0,0,.15)}}
</style></head><body>
<div class="side">
 <h1>Сети конкурентов «betify»</h1>
 <div class="sub">{len(clusters)} сетей по активным редиректам. Клик — блок-схема сети.</div>
 <ul>{''.join(tabs)}</ul>
</div>
<div class="main">
 {''.join(panels)}
 <div class="legend" style="position:fixed;bottom:10px;left:320px">
   <span><span class="dot" style="background:#dbeeff"></span>betify-хост</span>
   <span><span class="dot" style="background:#ffd5cc;border-color:#d43f2a"></span>конечный адрес</span>
   <span><span class="dot" style="background:#eef0f2"></span>прочий хост</span>
 </div>
</div>
<script>
 const items=document.querySelectorAll('.side li');
 function show(id){{
   document.querySelectorAll('.panel').forEach(p=>p.classList.remove('show'));
   document.getElementById('p-'+id).classList.add('show');
   items.forEach(i=>i.classList.toggle('active', i.dataset.t===id));
 }}
 items.forEach(i=>i.onclick=()=>show(i.dataset.t));
 show(items[0].dataset.t);
</script>
</body></html>'''

open('data/networks_graphs.html', 'w').write(HTML)
print('written: data/networks_graphs.html |', len(clusters), 'сетей')
