# Продолжение RRT-прогона с другого компьютера

## Статус на момент сохранения (2026-07-12)
- **Обработано: 421 / 1164 доменов** очереди (dumps 001–032).
- **Осталось: 801 домен** (низкоприоритетный «other»-бакет: крупные легит-сайты + разовые появления в SERP).
- Все ценные betify/casino/paris домены (первые ~274) уже обработаны.
- Приложение `data/app.html` пересобрано: **109 сетей**.

## Что синхронизировано через Google Drive (готово на новой машине)
- `data/rrt_dumps/dump_001.json … dump_032.json` — все результаты RRT.
- `data/rrt_batch2.json` — собранная выгрузка (дедуп по host, приоритет ok>crawl-failed>timeout).
- `data/rrt_queue.json` — очередь доменов (1164).
- `data/clusters.json`, `data/app.html` — текущие сети/приложение.
- `cluster_redirects.py`, `build_app.py`, `redirect_probe.py` — скрипты.
- `rrt_fn.js` — **реконструированная функция извлечения** (см. ниже про переинжект).

## Что НЕ переносится и нужно восстановить на новой машине
1. **Логин Google в браузере claude-in-chrome** — залогиниться в те же Google-аккаунты (для доступа к Rich Results Test).
2. **Функция извлечения в localStorage['fn']** — на новой машине её нет. Переинжект:
   - Открыть `https://search.google.com/u/0/test/rich-results/result?hl=en`
   - В `rrt_fn.js` строка `RRT_FN` — это тело функции. Выполнить в консоли страницы:
     ```js
     localStorage.setItem('fn', <строка из console.log(JSON.stringify(RRT_FN)) в rrt_fn.js>)
     ```
   - Проверить: `await (new Function('HOST', localStorage.getItem('fn')))('shuffle.com')`
     должно вернуть `{n:.., host:'shuffle.com', status:'ok', cross:[{to:'shuffle.bet',via:['hreflang']}]}`.
     Если результат отличается — старую fn достать не удалось (контент-фильтр), сверить логику по этому же файлу.

## Как продолжить прогон
Заново запустить `/loop` с тем же промптом (номер таба claude-in-chrome будет НОВЫЙ — подставить актуальный).
Логика батча (в промпте /loop):
1. Тест 1 домена: navigate + `await (new Function('HOST', localStorage.getItem('fn')))('<host>')`.
   - timeout + тост «Something went wrong» = IP-лимит → backoff 3600с.
   - timeout без тоста = тяжёлый/медленный домен → переизвлечь повторным вызовом fn на загруженной странице (станет ok).
2. Следующие 14 доменов из `rrt_queue.json`, которых нет в `rrt_dumps/*.json` и `rrt_batch*.json` (norm host = strip www).
3. Каждый в РАЗНЫХ ходах: navigate, затем fn-вызов. НЕ совмещать navigate+JS (CDP timeout).
4. После батча: `data/rrt_dumps/dump_033.json` (следующий номер!) массив `{host,status,cross}`; затем `localStorage.setItem('rrt','[]')`.
5. TODO==0 → собрать `rrt_batch2.json`, `python3 cluster_redirects.py`, `python3 build_app.py`.

## Замечание про IP-лимит RRT
Лимит на уровне **IP** (не аккаунта). Прошлый IP `147.45.178.194` давал окна ~8–12 доменов, затем блок на ~1ч.
Смена Google-аккаунта (/u/0/ → /u/1/) НЕ помогает. Помогает **другой exit-IP** (VPN в другой стране).

## Найденные betify-сети / взломанные легит-.fr (ключевое)
- C3 `cesar-group.fr` — 12 хостов betify на взломанных .fr (retdtechfrance, lycee-charlesdegaulle, charlicharger, marcus-strasbourg…).
- C9 `crypto-casinobet.fr` — crypto-casino1.bet и вариации.
- C10 `tsr-recyclage.fr` — germaineparis.fr, bulgarie-dentiste.fr, toncadre.fr, usvck.fr.
- Точечные взломанные .fr → казино: `confluences.fr → meilleurcasinoen-ligne.net`, `bonussandepot.it.com → ambianceloisirs.fr`.
- Легит-мультиязычный шум (свои изолированные кластеры, не betify): casino.guru, bookmaker-ratings.*, bitdegree, egamersworld, beincrypto, tribuna, gravatar, scamdoc.
