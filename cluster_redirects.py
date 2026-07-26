#!/usr/bin/env python3
"""Union-find кластеризация по цепочкам редиректов (этап 1, v2, graph-aware).

Источник: data/redirects.json {"probes": {seed_url: {chain, start_host, final_host, dead}}}.
Seeds = корни доменов/поддоменов + целевые URL из выдачи (все — approved sources).

Правило рёбер:
  1) СТРОГОЕ ребро a->b: переход между разными хостами, ИСТОЧНИК которого — approved source
     (стартовый seed i==0, т.е. корень/поддомен/целевая из СЕРПа, ИЛИ корневой путь '/').
  2) GRAPH-AWARE: глубокий-путь хоп a->b (источник не approved) засчитываем, ТОЛЬКО если b —
     сам член сети, т.е. b является источником хотя бы одного строгого ребра (его корень
     независимо редиректит в сеть). Это возвращает легит-цепочки через свой /path,
     но НЕ пропускает аффилейт-прокладки (напр. sitegpr.com/go/... -> трекер, который сам никуда с корня не ведёт).

www и без-www — один хост; http->https даёт a==b и отбрасывается.
Сеть = компонента с >=2 разными регистрируемыми доменами.
Вывод: data/clusters.json.
"""
import json, sys
from collections import defaultdict
from urllib.parse import urlsplit

RED = sys.argv[1] if len(sys.argv) > 1 else 'data/redirects.json'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'data/clusters.json'
RRT_GLOB = sys.argv[3] if len(sys.argv) > 3 else 'data/rrt_batch*.json'
EXCLUDED_PATH = sys.argv[4] if len(sys.argv) > 4 else 'data/cluster_excluded_domains.json'
probes = json.load(open(RED))['probes']

try:
    EXCLUDED_DOMAINS = set(json.load(open(EXCLUDED_PATH)))
except FileNotFoundError:
    EXCLUDED_DOMAINS = set()

TWO = {'eu.com','co.uk','org.uk','uk.net','uk.com','co.za','com.au','co.nz','mex.com',
       'in.net','jp.net','co.com','us.com','it.com','fr.uptodown.com',
       'bet.ar','bet.br','com.co'}
def norm(h):
    h = (h or '').lower(); return h[4:] if h.startswith('www.') else h
def registrable(host):
    d = norm(host).lstrip('.'); p = d.split('.')
    if len(p) >= 3 and '.'.join(p[-2:]) in TWO: return '.'.join(p[-3:])
    return '.'.join(p[-2:]) if len(p) >= 2 else d
def excluded(a, b):
    return registrable(a) in EXCLUDED_DOMAINS or registrable(b) in EXCLUDED_DOMAINS

# Мега-платформы как ЦЕЛЬ: ребро сохраняем (хост засчитан живым редиректором и попадает
# в terminals), но склеивать через них компоненты нельзя — на один и тот же play.google.com
# или facebook.com ведут никак не связанные между собой акторы.
NO_JOIN = {'google.com', 'facebook.com', 'youtube.com', 'instagram.com', 'twitter.com',
           'x.com', 'linkedin.com', 'tiktok.com', 'reddit.com', 'pinterest.com',
           'apple.com', 'microsoft.com', 'amazon.com', 'wikipedia.org',
           't.me', 'telegram.org', 'whatsapp.com'}
def nojoin(b):
    return registrable(b) in NO_JOIN
def approved_source(i, url):
    if i == 0: return True
    return (urlsplit(url or '').path or '/') in ('', '/')
def elabel(via, st):
    if via == 'http': return str(st) if st else '3xx'
    if via in ('meta','js'): return via.upper() if via=='js' else 'meta'
    return via or ''

parent = {}
def find(x):
    parent.setdefault(x, x)
    while parent[x] != x:
        parent[x] = parent[parent[x]]; x = parent[x]
    return x
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb: parent[ra] = rb

# --- РЁБРА: множество меток на пару (a,b). Направление источник->цель. ---
import glob, os
edgemap = defaultdict(set)   # (a,b) -> {labels}
softedge = set()             # рёбра canonical/hreflang (для ослабленного фильтра сети)

# 1) редиректы: строгие (approved source) + graph-aware (глубокий хоп на члена сети)
strict, deep = [], []
for seed, rec in probes.items():
    ch = rec.get('chain') or []
    for i in range(len(ch) - 1):
        a, b = norm(ch[i].get('host')), norm(ch[i+1].get('host'))
        if not a or not b or a == b or excluded(a, b): continue
        lab = elabel(ch[i].get('via'), ch[i].get('status'))
        (strict if approved_source(i, ch[i].get('url')) else deep).append((a, b, lab))
A = {a for (a, b, l) in strict}
for a, b, l in strict:
    edgemap[(a, b)].add(l)
    if not nojoin(b): union(a, b)
for a, b, l in deep:
    if b in A:
        edgemap[(a, b)].add(l)
        if not nojoin(b): union(a, b)

# 2) RRT canonical/hreflang
rrt_files = sorted(glob.glob(RRT_GLOB))
rrt_edge_count = 0
for f in rrt_files:
    try: rr = json.load(open(f)).get('results', [])
    except Exception: continue
    for r in rr:
        a = norm(r.get('host'))
        for c in (r.get('cross') or []):
            b = norm(c.get('to'))
            if not a or not b or a == b or excluded(a, b): continue
            for v in (c.get('via') or []):
                edgemap[(a, b)].add(v)              # 'canonical' / 'hreflang'
            if nojoin(b): continue
            softedge.add((a, b))
            union(a, b)
            rrt_edge_count += 1

edges = [(a, b, sorted(labs), (a, b) in softedge) for (a, b), labs in edgemap.items()]

comp = defaultdict(set)
for h in list(parent): comp[find(h)].add(h)
# рёбра внутри компоненты
comp_soft = defaultdict(bool)
for (a, b) in softedge:
    comp_soft[find(a)] = True
# сеть = >=2 регистр. домена ИЛИ есть canonical/hreflang-ребро (правило поддомен-узлов)
clusters = [sorted(m) for r, m in comp.items()
            if len({registrable(h) for h in m}) >= 2 or comp_soft[r]]
clusters.sort(key=lambda m: (len({registrable(h) for h in m}), len(m)), reverse=True)

def terminals(members):
    ms = set(members); t = defaultdict(int)
    for seed, rec in probes.items():
        sh, fh = norm(rec.get('start_host')), norm(rec.get('final_host'))
        if sh in ms and fh and not rec.get('dead') and fh != sh:
            t[fh] += 1
    return dict(sorted(t.items(), key=lambda x: -x[1]))

out, host2cluster = [], {}
for i, members in enumerate(clusters):
    cid = f'C{i+1}'
    for m in members: host2cluster[m] = cid
    out.append({'id': cid, 'size': len(members),
                'regs': sorted({registrable(h) for h in members}),
                'members': members, 'terminals': terminals(members)})
json.dump({'clusters': out, 'host2cluster': host2cluster,
           'edges': [{'src': s, 'dst': d, 'via': v, 'soft': soft} for s, d, v, soft in edges]},
          open(OUT, 'w'), ensure_ascii=False, indent=0)

print(f'редирект-рёбер: строгих {len(strict)} + graph-aware {sum(1 for a,b,l in deep if b in A)} | RRT canonical/hreflang рёбер: {rrt_edge_count} ({len(rrt_files)} батч-файлов)')
print(f'сетей: {len(clusters)}\n')
for c in out[:14]:
    term = ', '.join(f'{k}({v})' for k, v in list(c['terminals'].items())[:2])
    print(f"[{c['id']}] хостов={c['size']:>2} доменов={len(c['regs']):>2} ->{term}")
    print('     ' + ', '.join(c['members'][:16]) + (' …' if c['size'] > 16 else ''))
