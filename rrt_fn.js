// RRT extraction function (reconstructed) — тело хранится в localStorage['fn'] и вызывается как:
//   const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
//   await (new AsyncFunction('HOST', localStorage.getItem('fn')))('<host>')
// ВАЖНО: обычный `new Function` НЕ поддерживает await внутри тела (SyntaxError) — нужен именно AsyncFunction.
// Переинжект на новом компьютере: открыть https://search.google.com/u/0/test/rich-results/result?hl=en
//   и выполнить в консоли/через claude-in-chrome:  localStorage.setItem('fn', <содержимое ниже одной строкой>)
// Скрипт: опрашивает результат RRT (англ. статусы), открывает "view tested page", читает HTML из CodeMirror,
//   тянет canonical + hreflang, резолвит относительные URL к HOST, возвращает кросс-хостовые рёбра,
//   аккумулирует в localStorage['rrt'] и возвращает {n,host,status,cross}.

const RRT_FN = `
const sleep = ms => new Promise(r=>setTimeout(r,ms));
const norm = h => (h||'').toLowerCase().replace(/^www\\./,'');
let status='timeout', cross=[];
try {
  // 1) дождаться завершения краула (до ~40с)
  let done=false;
  for (let i=0;i<80;i++){
    const t=(document.body.innerText||'').toLowerCase();
    if (t.includes('crawled successfully')||t.includes('item detected')||t.includes('no items')||t.includes('eligible')||t.includes('valid item')){ done=true; break; }
    if (t.includes('something went wrong')){ status='timeout'; done=false; break; }
    if (t.includes('url is not available to google')||t.includes('crawl failed')){ status='crawl-failed'; done=false; break; }
    await sleep(500);
  }
  if (done){
    const t=(document.body.innerText||'').toLowerCase();
    if (t.includes('crawl')&&(t.includes('not')||t.includes('fail')||t.includes("couldn't"))) status='crawl-failed';
    else status='ok';
    // 2) открыть "view tested page"
    let vt=[...document.querySelectorAll('a,button,span,div')].find(e=>/view tested page/i.test(e.textContent||''));
    if (vt){ vt.click(); await sleep(1200); }
    // 3) прочитать HTML из CodeMirror
    let html='';
    for (let i=0;i<20;i++){
      const cms=document.querySelectorAll('.CodeMirror');
      for (const cm of cms){ if (cm.CodeMirror){ const v=cm.CodeMirror.getValue(); if (v&&v.length>html.length) html=v; } }
      if (html.length>100) break;
      await sleep(400);
    }
    if (html){
      const H=norm(HOST);
      const abs=u=>{ try{ return new URL(u, 'https://'+HOST+'/').href; }catch(e){ return null; } };
      const seen={};
      // canonical
      let m=html.match(/<link[^>]+rel=["']?canonical["']?[^>]*>/ig)||[];
      for (const tag of m){ const u=(tag.match(/href=["']([^"']+)["']/i)||[])[1]; if(!u)continue; const a=abs(u); if(!a)continue; const th=norm(new URL(a).hostname); if(th&&th!==H){ (seen[th]=seen[th]||new Set()).add('canonical'); } }
      // hreflang
      let hm=html.match(/<link[^>]+hreflang=[^>]*>/ig)||[];
      for (const tag of hm){ const u=(tag.match(/href=["']([^"']+)["']/i)||[])[1]; if(!u)continue; const a=abs(u); if(!a)continue; const th=norm(new URL(a).hostname); if(th&&th!==H){ (seen[th]=seen[th]||new Set()).add('hreflang'); } }
      cross=Object.keys(seen).map(th=>({to:th, via:[...seen[th]]}));
    }
  }
} catch(e){ status='timeout'; }
// аккумулировать
let arr=[]; try{ arr=JSON.parse(localStorage.getItem('rrt')||'[]'); }catch(e){}
const rec={host:norm(HOST), status, cross}; arr.push(rec); localStorage.setItem('rrt', JSON.stringify(arr));
return JSON.stringify({n:arr.length, host:rec.host, status, cross});
`.trim();

// Экспорт строки одной командой для setItem (скопировать вывод в setItem на новой машине)
console.log(JSON.stringify(RRT_FN));
