#!/usr/bin/env python3
"""Собирает ВСЕ исторические снапшоты SERP из Ahrefs serp-overview методом
шага-по-снапшотам (walk-back): каждый запрос возвращает ровно один новый снапшот,
без дублей и пропусков. API на date=X отдаёт ближайший снапшот с update_date <= X.

Алгоритм: cursor=date_to; запрос -> снапшот S; записать; cursor = дата(S) - 1 день; повтор,
пока снапшоты не кончатся или не уйдём раньше date_from.

usage: harvest_ahrefs.py <keyword> <country> <date_from> <date_to> <out.json>
"""
import json, sys, os, time, urllib.request, urllib.parse
from datetime import date, timedelta

KEY = os.environ['AHREFS_KEY']
kw       = sys.argv[1]
country  = sys.argv[2]
d_from   = date.fromisoformat(sys.argv[3])
d_to     = date.fromisoformat(sys.argv[4])
out      = sys.argv[5]
TOP      = 100
SELECT   = 'position,type,url,title,domain_rating,update_date'
MAX_REQ  = 400  # предохранитель

def fetch(d):
    qs = urllib.parse.urlencode({
        'select': SELECT, 'country': country, 'keyword': kw,
        'top_positions': TOP, 'date': f'{d.isoformat()}T23:59:59',
    })
    url = f'https://api.ahrefs.com/v3/serp-overview/serp-overview?{qs}'
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {KEY}'})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r).get('positions') or []
        except Exception as e:
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))

results = {}
# merge-режим: если файл уже есть — подгружаем существующие снапшоты, добавляем новые
if os.path.exists(out):
    try:
        _ex = json.load(open(out))
        for s in _ex.get('snapshots', []):
            results[s['snapshot']] = s
        print(f'merge: загружено {len(results)} существующих снапшотов', flush=True)
    except Exception:
        pass
cursor = d_to
reqs = 0
misses = 0
MISS_STEP  = 5    # на сколько дней шагать назад через дыру
MISS_LIMIT = 12   # столько пустых ответов подряд (=60 дн) считаем концом истории
while cursor >= d_from and reqs < MAX_REQ:
    rows = fetch(cursor)
    reqs += 1
    # Пустой ответ != конец истории: API отдаёт снапшот только если он есть рядом с
    # запрошенной датой, а в ряду попадаются дыры по 3-4 недели. Поэтому на пустом
    # ответе перешагиваем дыру, а обрываемся лишь после MISS_LIMIT попыток подряд.
    snap = rows[0].get('update_date') if rows else None
    if not snap:
        misses += 1
        if misses >= MISS_LIMIT:
            print(f'  стоп: {MISS_LIMIT} пустых ответов подряд '
                  f'(просмотрено {MISS_LIMIT*MISS_STEP} дн назад от {cursor.isoformat()})', flush=True)
            break
        cursor = cursor - timedelta(days=MISS_STEP)
        continue
    misses = 0
    if snap in results:            # защита от зацикливания
        cursor = cursor - timedelta(days=1)
        continue
    results[snap] = {'snapshot': snap, 'rows': rows}
    org = sum(1 for r in rows if 'organic' in (r.get('type') or []))
    print(f'  [{reqs:3}] {snap[:10]}  org={org}', flush=True)
    # инкрементальная запись — прогресс не теряется при обрыве
    _snaps = sorted(results.values(), key=lambda s: s['snapshot'])
    json.dump({'keyword': kw, 'country': country, 'snapshots': _snaps},
              open(out, 'w'), ensure_ascii=False)
    cursor = date.fromisoformat(snap[:10]) - timedelta(days=1)

errors = 0
print(f'requests: {reqs} | unique snapshots: {len(results)}')
snaps = sorted(results.values(), key=lambda s: s['snapshot'])
json.dump({'keyword': kw, 'country': country, 'snapshots': snaps},
          open(out, 'w'), ensure_ascii=False)
print(f'unique snapshots: {len(snaps)} | errors: {errors} | -> {out}')
for s in snaps:
    org = [r for r in s['rows'] if 'organic' in (r.get('type') or [])]
    top = org[0]['url'] if org else (s['rows'][0].get('url') if s['rows'] else '?')
    print(f"  {s['snapshot'][:10]}  ({len(org)} org)  #1={str(top)[:55]}")
