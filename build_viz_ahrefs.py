#!/usr/bin/env python3
"""HTML-таймлайн из еженедельных снапшотов Ahrefs (harvest_ahrefs.py).
Колонки = снапшоты, строки = позиции, цвет = гипотеза о принадлежности сетке (эвристика по домену).
usage: build_viz_ahrefs.py <in.json> <out.html>
"""
import json, sys, html
from urllib.parse import urlsplit
from collections import Counter

SRC = sys.argv[1] if len(sys.argv) > 1 else 'data/betify_fr_ahrefs.json'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'data/betify_fr_ahrefs_timeline.html'
BRAND = 'betify'
TOP_N = 100

NEUTRAL = {
    'trustpilot.com','youtube.com','instagram.com','tiktok.com','facebook.com','x.com',
    'twitter.com','play.google.com','solo.to','reddit.com','wikipedia.org','google.com',
    'laplanquedujoueur.com','galnet.fr','themagma.co','critiquejeu.info','steinertriple-sport.fr',
    'jeux.fm','myteam.ai','tnbet.fr','weecommerce.ca','maxifrance.radio','mutuelle-sante.net',
    'actuabd.com','downdetector.fr','amf-france.org','warning-trading.com','jouerlignefr.org',
    'polkovnik.am','silverstareg.com','codepromobetify.com','opale-dmcc.com','casino.jeux.fm',
    'linkedin.com','apps.apple.com','pinterest.com','pinterest.fr',
}

def domain_of(url):
    try:
        h = urlsplit(url).hostname or ''
    except Exception:
        h = ''
    return h.lower()

def registrable(host):
    d = host.lstrip('.')
    if d.startswith('www.'): d = d[4:]
    parts = d.split('.')
    two = {'eu.com','co.uk','org.uk','uk.net','com.au','co.nz','mex.com'}
    if len(parts) >= 3 and '.'.join(parts[-2:]) in two:
        return '.'.join(parts[-3:])
    return '.'.join(parts[-2:]) if len(parts) >= 2 else d

def is_neutral(host):
    return registrable(host) in NEUTRAL

def classify(host):
    reg = registrable(host)
    hostn = host[4:] if host.startswith('www.') else host
    if reg == 'betify.com':
        return 'official', 'betify.com'
    if is_neutral(host):
        return 'neutral', None
    brand_in_reg = BRAND in reg.split('.')[0]
    sub = hostn[:-(len(reg)+1)] if hostn.endswith(reg) and len(hostn) > len(reg) else ''
    brand_in_sub = BRAND in sub
    if brand_in_sub and not brand_in_reg:
        return 'parasite_sub', 'PARASITE:'+reg
    if brand_in_reg:
        return 'mirror_domain', 'MIRROR:'+reg
    return 'unknown_susp', 'SUSP:'+reg

CAT = {
    'official':      ('#fff34d','#000','Официальный betify.com'),
    'mirror_domain': ('#ff9db0','#000','Домен-зеркало с брендом в имени'),
    'parasite_sub':  ('#8fd6ff','#000','Паразитный поддомен на чужом сайте'),
    'unknown_susp':  ('#ffcf8f','#000','Подозрительный (без бренда в имени)'),
    'neutral':       ('#f0f0f0','#555','Нейтрально (обзор/соцсеть)'),
}

# --- подтверждённые сети из этапа 1 (редиректы) ---
try:
    CL = json.load(open('data/clusters.json'))
    HOST2C = CL['host2cluster']
    CINFO = {c['id']: c for c in CL['clusters']}
except Exception:
    HOST2C, CINFO = {}, {}

def cluster_color(cid):
    # золотой угол по номеру кластера -> стабильный различимый цвет
    n = int(cid[1:])
    hue = (n * 137.508) % 360
    return f'hsl({hue:.0f} 70% 82%)'

d = json.load(open(SRC))
snaps = d['snapshots']
cols = []
for s in snaps:
    date = s['snapshot'][:10]
    rows = [r for r in s['rows'] if 'organic' in (r.get('type') or [])]
    rows.sort(key=lambda r: r.get('position', 999))
    out, seen = [], set()
    for r in rows:
        host = domain_of(r.get('url',''))
        if not host or host in seen: continue
        seen.add(host)
        cid = HOST2C.get(host) or HOST2C.get(host[4:] if host.startswith('www.') else 'www.'+host)
        out.append((r.get('position'), host, r.get('url',''), r.get('domain_rating'), cid))
        if len(out) >= TOP_N: break
    cols.append((date, out))

def esc(s): return html.escape(str(s))
P = ['''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>betify FR — Ahrefs SERP timeline</title><style>
 html,body{height:100%}
 body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#fafafa;color:#111;
      display:flex;flex-direction:column;height:100vh;overflow:hidden}
 .head{flex:0 0 auto;padding:14px 18px 8px}
 h1{font-size:17px;margin:0 0 3px} .sub{color:#666;font-size:12px;margin-bottom:10px}
 .legend{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:8px;font-size:12px}
 .legend span{display:inline-flex;align-items:center;gap:5px}
 .sw{width:13px;height:13px;border-radius:3px;display:inline-block;border:1px solid rgba(0,0,0,.15)}
 .note{font-size:11px;color:#888;line-height:1.4;max-width:1100px}
 .grid{flex:1 1 auto;display:flex;gap:6px;overflow:auto;padding:6px 18px 0;align-items:flex-start}
 .col{min-width:150px;flex:0 0 auto}
 .colh{position:sticky;top:0;background:#fafafa;z-index:1;font-weight:600;font-size:11px;padding:5px 3px;
       border-bottom:2px solid #ddd;margin-bottom:5px;white-space:nowrap}
 .cell{font-size:11px;padding:3px 6px;border-radius:4px;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;background:#fff;border:1px solid #eee}
 .cell .r{color:#888;font-variant-numeric:tabular-nums;margin-right:5px}
 .cell a{color:inherit;text-decoration:none}
</style></head><body>
<div class="head">
<h1>betify · Франция · исторический SERP (Ahrefs)</h1>
<div class="sub">'''+str(len(cols))+''' снапшотов, '''+cols[0][0]+''' — '''+cols[-1][0]+'''. Топ-'''+str(TOP_N)+''' органики. Цвет = подтверждённая сеть (общая цепочка редиректов).</div>
<div class="note"><b>Этап 1 — жёсткая склейка по активным редиректам (301/302/307/308 + meta + JS).</b>
Цветом помечены хосты, входящие в одну сеть по редиректам; белые — без активного редиректа или мёртвые (→ Wayback-этап). Наведите на ячейку: сеть и конечный адрес.</div>
</div>
<div class="grid">''']
for date, rows in cols:
    P.append(f'<div class="col"><div class="colh">{esc(date)}</div>')
    for pos, host, url, dr, cid in rows:
        if cid:
            info = CINFO.get(cid, {})
            term = ', '.join(list((info.get('terminals') or {}).keys())[:2])
            style = f'background:{cluster_color(cid)}'
            tip = f'{cid} · сеть из {info.get("size","?")} хостов → {term} · DR={dr}\n{url}'
        else:
            style = 'background:#fff;border:1px solid #eee'
            tip = f'DR={dr}\n{url}'
        P.append(f'<div class="cell" style="{style}" title="{esc(tip)}">'
                 f'<span class="r">{pos}</span><a href="{esc(url)}" target="_blank">{esc(host)}</a></div>')
    P.append('</div>')
P.append('''</div></body></html>''')
open(OUT,'w').write(''.join(P))
print('written:', OUT, '| columns:', len(cols))
c = Counter(r[4] for _,rows in cols for r in rows)
print('cells by category:', dict(c))
# сколько уникальных доменов в каждой «сеточной» категории
mir = sorted({r[1] for _,rows in cols for r in rows if r[4]=='mirror_domain'})
par = sorted({registrable(r[1]) for _,rows in cols for r in rows if r[4]=='parasite_sub'})
print(f'\nуник. mirror-доменов: {len(mir)}'); print('  ', ', '.join(mir))
print(f'уник. parasite-хостов (root): {len(par)}'); print('  ', ', '.join(par))
