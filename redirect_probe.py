#!/usr/bin/env python3
"""Этап 1 (v2): активные цепочки редиректов от APPROVED SOURCES.
Seeds = для каждого хоста из выдачи: КОРЕНЬ https://host/ + целевой URL из СЕРПа.
Плюс раскрытие: корни всех промежуточных хостов, найденных в цепочках (до стабилизации).
UA=Googlebot, ловим HTTP 3xx + meta + JS-regex (без выполнения чужого JS). SSL не верифицируем.
Вывод: data/redirects.json = {"probes": { seed_url: {seed, start_host, chain:[...], final_host, dead} }}
Резюмируемый, инкрементальная запись.

usage: redirect_probe.py <snapshots.json> <out.json>
"""
import json, sys, re, ssl, socket, urllib.request, urllib.error
from urllib.parse import urlsplit, urljoin, urlunsplit, quote
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import threading

SNAP = sys.argv[1] if len(sys.argv) > 1 else 'data/betify_fr_ahrefs.json'
OUT  = sys.argv[2] if len(sys.argv) > 2 else 'data/redirects.json'
UA   = 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
MAX_HOPS = 15
TIMEOUT  = 12
BODY_CAP = 262144
WORKERS  = 24
ROUNDS   = 3      # раскрытие промежуточных хостов

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE

META_RE = re.compile(rb'<meta[^>]+http-equiv=["\']?refresh["\']?[^>]*content=["\']?\s*\d+\s*;\s*url=([^"\'>\s]+)', re.I)
JS_RES = [re.compile(rb'(?:window\.|top\.|document\.)?location(?:\.href|\.assign|\.replace)?\s*(?:=|\()\s*["\']([^"\']+)["\']', re.I),
          re.compile(rb'location\.replace\(\s*["\']([^"\']+)["\']', re.I)]

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None
_opener = urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=CTX))

def host_of(u): return (urlsplit(u).hostname or '').lower()
def norm(h):
    h = (h or '').lower(); return h[4:] if h.startswith('www.') else h

def sanitize(u):
    try:
        p = urlsplit(u); host = p.hostname or ''
        try: host_a = host.encode('idna').decode('ascii') if host else ''
        except Exception: host_a = host.encode('ascii', 'ignore').decode('ascii')
        netloc = host_a + (f':{p.port}' if p.port else '')
        if p.username: netloc = f'{p.username}@' + netloc
        return urlunsplit((p.scheme, netloc, quote(p.path, safe="/%:@!$&'()*+,;=~"),
                           quote(p.query, safe="=&%:@/?!$'()*+,;~"), ''))
    except Exception: return u

def one_request(url):
    req = urllib.request.Request(sanitize(url), headers={'User-Agent': UA, 'Accept': '*/*'})
    try:
        resp = _opener.open(req, timeout=TIMEOUT)
        ct = (resp.headers.get('Content-Type') or '').lower()
        body = resp.read(BODY_CAP) if 'html' in ct or ct == '' else b''
        return resp.getcode(), body, True
    except urllib.error.HTTPError as e:
        loc = e.headers.get('Location')
        if 300 <= e.code < 400 and loc: return e.code, loc, False
        return e.code, b'', True

def find_client_redirect(body, base):
    m = META_RE.search(body)
    if m: return urljoin(base, m.group(1).decode('latin1', 'ignore').strip()), 'meta'
    for rx in JS_RES:
        m = rx.search(body)
        if m:
            tgt = m.group(1).decode('latin1', 'ignore').strip()
            if tgt.startswith(('http', '/')) and 'location' not in tgt.lower():
                return urljoin(base, tgt), 'js'
    return None, None

def follow(start_url):
    chain, visited, url = [], set(), start_url
    for _ in range(MAX_HOPS):
        if url in visited:
            chain.append({'url': url, 'status': None, 'via': 'loop', 'host': host_of(url)}); break
        visited.add(url)
        try:
            status, payload, is_body = one_request(url)
        except Exception as e:
            chain.append({'url': url, 'status': None, 'via': 'error', 'host': host_of(url), 'err': f'{type(e).__name__}: {e}'[:120]})
            return chain, True
        if not is_body:
            chain.append({'url': url, 'status': status, 'via': 'http', 'host': host_of(url)})
            url = urljoin(url, payload); continue
        nxt, via = find_client_redirect(payload, url)
        if nxt and nxt != url:
            chain.append({'url': url, 'status': status, 'via': via, 'host': host_of(url)})
            url = nxt; continue
        chain.append({'url': url, 'status': status, 'via': 'final', 'host': host_of(url)}); break
    return chain, False

# ---- seeds: корни + целевые URL из выдачи ----
d = json.load(open(SNAP))
pair = Counter()
for s in d['snapshots']:
    for r in s['rows']:
        if 'organic' not in (r.get('type') or []): continue
        u = r.get('url', ''); h = host_of(u)
        if h: pair[(h, u)] += 1
rep = {}
for (h, u), c in pair.items():
    if h not in rep or c > rep[h][1]: rep[h] = (u, c)

seeds = {}  # seed_url -> start_host
for h in rep:
    seeds[f'https://{h}/'] = h          # корень (homepage)
    seeds[rep[h][0]] = h                # целевая страница из СЕРПа

try:
    doc = json.load(open(OUT)); results = doc.get('probes', {})
except Exception:
    results = {}

lock = threading.Lock(); done = [0]
def save(): json.dump({'probes': results}, open(OUT, 'w'), ensure_ascii=False)
def work(seed):
    chain, dead = follow(seed)
    final = chain[-1] if chain else {}
    rec = {'seed': seed, 'start_host': host_of(seed), 'chain': chain,
           'final_host': final.get('host'), 'dead': dead}
    with lock:
        results[seed] = rec; done[0] += 1
        if done[0] % 60 == 0: save(); print(f'  {done[0]} ...', flush=True)

for rnd in range(ROUNDS):
    todo = [s for s in seeds if s not in results]
    print(f'round {rnd+1}: seeds={len(seeds)} todo={len(todo)}', flush=True)
    if not todo:
        break
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(work, todo))
    save()
    # раскрытие: корни всех промежуточных хостов из найденных цепочек
    add = 0
    for rec in list(results.values()):
        for c in rec['chain']:
            hh = norm(c.get('host'))
            if hh:
                s = f'https://{hh}/'
                if s not in seeds: seeds[s] = hh; add += 1
    print(f'  раскрыто новых корней: {add}', flush=True)
    if add == 0:
        break
save()
cross = sum(1 for r in results.values() if r['final_host'] and norm(r['final_host']) != norm(r['start_host']) and not r['dead'])
dead = sum(1 for r in results.values() if r['dead'])
print(f'DONE. probes={len(results)} | кросс-хост-финалов={cross} | мёртвых={dead}', flush=True)
