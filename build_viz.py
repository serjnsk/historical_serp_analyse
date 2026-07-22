#!/usr/bin/env python3
"""Строит HTML-таймлайн исторического SERP из ответа DataForSEO historical_serps.
Колонки = снапшоты (даты), строки = позиции, цвет = гипотеза о принадлежности сетке.

ВАЖНО: подсветка на этом этапе — ЭВРИСТИКА по неймингу/структуре домена (мягкий сигнал),
а не подтверждённая склейка по 301/canonical/hreflang. Жёсткая верификация — следующий этап.
"""
import json, sys, html, re
from collections import OrderedDict

SRC = sys.argv[1] if len(sys.argv) > 1 else 'data/probe_betify_fr.json'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'data/betify_fr_timeline.html'
BRAND = 'betify'
TOP_N = 15

# --- известные не-сетевые площадки (обзорники, соцсети, каталоги) ---
NEUTRAL = {
    'trustpilot.com', 'youtube.com', 'instagram.com', 'tiktok.com', 'facebook.com',
    'x.com', 'twitter.com', 'play.google.com', 'solo.to', 'reddit.com', 'wikipedia.org',
    'laplanquedujoueur.com', 'galnet.fr', 'themagma.co', 'critiquejeu.info',
    'steinertriple-sport.fr', 'jeux.fm', 'myteam.ai', 'tnbet.fr', 'weecommerce.ca',
    'maxifrance.radio', 'mutuelle-sante.net', 'actuabd.com', 'downdetector.fr',
    'amf-france.org', 'warning-trading.com', 'jouerlignefr.org', 'polkovnik.am',
    'silverstareg.com', 'codepromobetify.com', 'opale-dmcc.com', 'casinobetify.com',
    'betifypro.com',
}

def registrable(domain):
    """Грубое выделение регистрируемого домена (последние 2 метки, с учётом ccTLD-2level)."""
    d = domain.lower().lstrip('.')
    if d.startswith('www.'):
        d = d[4:]
    parts = d.split('.')
    two_level = {'eu.com','co.uk','org.uk','uk.net','com.au','co.nz'}
    if len(parts) >= 3 and '.'.join(parts[-2:]) in two_level:
        return '.'.join(parts[-3:])
    return '.'.join(parts[-2:]) if len(parts) >= 2 else d

def is_neutral(domain):
    reg = registrable(domain)
    return reg in NEUTRAL or any(domain.endswith(n) or reg == n for n in NEUTRAL)

def classify(domain):
    """Возвращает (category, group_key). Эвристика-гипотеза."""
    d = domain.lower()
    reg = registrable(d)
    host = d[4:] if d.startswith('www.') else d
    if reg in ('betify.com',):
        return 'official', 'betify.com'
    if is_neutral(d):
        return 'neutral', None
    has_brand_in_reg = BRAND in reg.split('.')[0]
    sub = host[:-(len(reg)+1)] if host.endswith(reg) and len(host) > len(reg) else ''
    brand_in_sub = BRAND in sub
    if has_brand_in_reg and not brand_in_sub:
        # отдельный домен-зеркало, где бренд в самом имени: betify.ing, betify-fr.top, betify-france-fr.com
        return 'mirror_domain', 'MIRROR:brand-domain'
    if brand_in_sub and not has_brand_in_reg:
        # паразитный поддомен на стороннем домене: betify.univers-med.fr, betifyfr.malokadistro.com
        return 'parasite_sub', 'PARASITE:'+reg
    if has_brand_in_reg and brand_in_sub:
        return 'mirror_domain', 'MIRROR:brand-domain'
    # прочие подозрительные (например cco-nantes.org в #1 — взломанный, но без бренда в имени)
    return 'unknown_susp', 'SUSP:'+reg

CAT_STYLE = {
    'official':      ('#fff34d', '#000', 'Официальный betify.com'),
    'mirror_domain': ('#ff9db0', '#000', 'Домен-зеркало с брендом в имени (гипотеза: сетка)'),
    'parasite_sub':  ('#8fd6ff', '#000', 'Паразитный поддомен на чужом сайте (гипотеза: сетка)'),
    'unknown_susp':  ('#ffcf8f', '#000', 'Подозрительный (в #1, требует проверки)'),
    'neutral':       ('#f0f0f0', '#555', 'Нейтрально (обзор/соцсеть/каталог)'),
}

d = json.load(open(SRC))
snaps = d['tasks'][0]['result'][0]['items']

cols = []  # list of (date, [(rank, domain, url, cat, group)])
for it in snaps:
    date = it['datetime'][:10]
    org = [i for i in (it.get('items') or []) if i['type'] == 'organic']
    org.sort(key=lambda x: x.get('rank_group', 999))
    rows = []
    seen = set()
    for o in org:
        dom = o.get('domain', '')
        if dom in seen:
            continue
        seen.add(dom)
        cat, grp = classify(dom)
        rows.append((o.get('rank_group'), dom, o.get('url', ''), cat, grp))
        if len(rows) >= TOP_N:
            break
    cols.append((date, rows))

# --- HTML ---
def esc(s): return html.escape(str(s))

parts = ['''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>betify FR — исторический SERP timeline</title>
<style>
 body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:24px;background:#fafafa;color:#111}
 h1{font-size:18px;margin:0 0 4px} .sub{color:#666;font-size:13px;margin-bottom:16px}
 .legend{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px;font-size:12px}
 .legend span{display:inline-flex;align-items:center;gap:6px}
 .sw{width:14px;height:14px;border-radius:3px;display:inline-block;border:1px solid rgba(0,0,0,.15)}
 .grid{display:flex;gap:10px;overflow-x:auto;padding-bottom:12px}
 .col{min-width:230px;flex:0 0 auto}
 .colh{font-weight:600;font-size:13px;padding:6px 4px;border-bottom:2px solid #ddd;margin-bottom:6px}
 .cell{font-size:12px;padding:5px 8px;border-radius:5px;margin-bottom:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 .cell .r{color:#888;font-variant-numeric:tabular-nums;margin-right:6px}
 .cell a{color:inherit;text-decoration:none}
 .note{margin-top:20px;font-size:12px;color:#777;max-width:900px;line-height:1.5}
</style></head><body>
<h1>betify · Франция · исторический SERP (DataForSEO)</h1>
<div class="sub">9 снапшотов, июль 2025 — май 2026. Топ-'''+str(TOP_N)+''' органики. Стоимость выборки: $0.001.</div>
<div class="legend">''']
for cat,(bg,fg,label) in CAT_STYLE.items():
    parts.append(f'<span><span class="sw" style="background:{bg}"></span>{esc(label)}</span>')
parts.append('</div><div class="grid">')

for date, rows in cols:
    parts.append(f'<div class="col"><div class="colh">{esc(date)}</div>')
    for rank, dom, url, cat, grp in rows:
        bg, fg, _ = CAT_STYLE[cat]
        title = esc(grp or '')
        parts.append(
            f'<div class="cell" style="background:{bg};color:{fg}" title="{title}\n{esc(url)}">'
            f'<span class="r">{rank}</span><a href="{esc(url)}" target="_blank">{esc(dom)}</a></div>')
    parts.append('</div>')

parts.append('''</div>
<div class="note"><b>Как читать.</b> Каждый столбец — снапшот выдачи Google на указанную дату.
Позиция №1 почти в каждом снапшоте занята новым «зеркалом» бренда (розовый) или взломанным поддоменом (голубой) —
Google банит домен, сеть поднимает следующий. <b>Важно:</b> подсветка здесь — гипотеза по неймингу и структуре
домена (мягкий сигнал). Подтверждённая склейка доменов в одну сетку по жёстким сигналам
(301/302, кросс-доменный canonical, hreflang, Wayback-история) — следующий этап.</div>
</body></html>''')

open(OUT, 'w').write(''.join(parts))
print('written:', OUT)
# сводка групп
from collections import Counter
c = Counter()
for _, rows in cols:
    for r in rows:
        c[r[3]] += 1
print('cells by category:', dict(c))
