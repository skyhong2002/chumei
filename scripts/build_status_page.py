#!/usr/bin/env python3
"""Generate the public crawler status page and machine-readable status API."""

from __future__ import annotations

import json
from pathlib import Path

from build_site import page_shell
from chumei_lib import ROOT
from source_status import build_status_payload


OUT_API = ROOT / "site" / "api" / "status.json"
OUT_PAGE = ROOT / "site" / "status" / "index.html"


STYLE = r"""
<style>
.status-page{padding-bottom:48px}.status-page .hero p{max-width:820px}.status-snapshot{display:block;margin-top:6px;font-size:.8rem;color:var(--color-text-muted)}.status-search input{width:100%;height:32px;border:1px solid var(--color-border-subtle);background:var(--color-surface);color:var(--color-text-primary);border-radius:var(--radius-sm,8px);padding:0 var(--space-3,12px);font:inherit;font-size:.8rem}.status-search input::placeholder{color:var(--color-text-muted)}.status-static{cursor:default}.status-static::before{display:none}.status-static:hover{background:var(--color-surface)}.status-service-note,.status-note{margin:8px 0 0;color:var(--color-text-secondary);font-size:.84rem;line-height:1.55}.status-note{margin-top:18px}.status-count{margin:10px 0 2px;color:var(--color-text-muted);font-size:.8rem}.status-message{min-height:1.3em;margin:4px 0;color:var(--color-text-muted);font-size:.82rem}.status-src-table{margin-top:8px;border-top:1px solid var(--color-border-subtle)}.status-src-head,.status-src-row{display:grid;grid-template-columns:minmax(220px,1.3fr) 150px 88px 190px 200px 54px;gap:10px;align-items:center}.status-src-head{position:sticky;top:0;z-index:5;padding:6px;border-bottom:2px solid var(--color-border-strong);background:var(--color-canvas)}.status-src-head span{font-size:.78rem;font-weight:600;color:var(--color-text-muted);white-space:nowrap}.status-src-row{padding:10px 6px;border-bottom:1px solid var(--color-border-subtle);min-height:64px}.status-src-row:hover{background:var(--color-surface-soft)}.status-src-row>*{min-width:0}.status-name{font-size:.95rem;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.status-sub{margin-top:2px;color:var(--color-text-muted);font-size:.76rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.status-backend{font-size:.82rem;color:var(--color-text-secondary)}.status-row-status{position:relative}.status-chip{display:inline-flex;align-items:center;gap:5px;width:max-content;border-radius:var(--radius-pill);padding:3px 8px;background:var(--color-surface-soft);font-size:.74rem;font-weight:600}.status-chip::before{content:"";width:6px;height:6px;border-radius:50%;background:#6a9f75}.status-chip.due::before{background:#d1993f}.status-chip.error::before{background:#c94d4d}.status-error-details{margin-top:2px;color:#b54848;font-size:.7rem}.status-error-details summary{cursor:pointer;list-style:none}.status-error-details summary::-webkit-details-marker{display:none}.status-error-details>div{position:absolute;z-index:20;top:100%;left:0;width:min(360px,calc(100vw - 32px));padding:10px 12px;border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-surface-raised);box-shadow:var(--shadow-raised);color:var(--color-text-secondary);font-size:.75rem;line-height:1.5;overflow-wrap:anywhere}.status-time{font-size:.8rem;font-variant-numeric:tabular-nums}.status-time .status-sub{font-size:.72rem}.status-fetch{justify-self:end;width:42px;height:32px;padding:0;border:1px solid var(--color-border-strong);border-radius:var(--radius-pill);background:none;color:var(--color-text-primary);font:inherit;font-size:.7rem;font-weight:600;cursor:pointer}.status-fetch:hover{background:var(--color-surface-soft)}.status-fetch:disabled{opacity:.42;cursor:not-allowed}.status-more{display:block;margin:14px auto;min-height:32px}@media(max-width:900px){.status-src-head,.status-src-row{grid-template-columns:minmax(190px,1.2fr) 125px 80px 170px 180px 48px}}@media(max-width:700px){.status-src-head{display:none}.status-src-table{margin-top:4px}.status-src-row{grid-template-columns:minmax(0,1fr) auto 42px;grid-template-areas:"name status action" "backend backend action" "recent recent action" "next next action";gap:3px 8px;padding:9px 0;min-height:0}.status-row-name{grid-area:name}.status-backend{grid-area:backend}.status-row-status{grid-area:status}.status-recent{grid-area:recent}.status-next{grid-area:next}.status-fetch{grid-area:action;align-self:center}.status-name{font-size:.87rem}.status-backend,.status-time{font-size:.75rem}.status-time>div{display:inline}.status-time .status-sub{margin-left:8px}.status-time .status-sub::before{content:"· ";}.status-note{margin-top:12px}}
</style>
"""


SCRIPT = r"""
<script>
(() => {
  const state={data:null,auth:false,filter:'',platform:'',status:'',limit:120};
  const fmtTime=value=>{if(!value)return '尚無紀錄';const d=typeof value==='number'?new Date(value*1000):new Date(value);return isNaN(d)?'尚無紀錄':new Intl.DateTimeFormat('zh-TW',{dateStyle:'short',timeStyle:'short',timeZone:'Asia/Taipei'}).format(d)};
  const fmtInterval=h=>{if(h==null)return '累積中';if(h<48)return `${h.toFixed(h<10?1:0)} 小時`;return `${(h/24).toFixed(h<96?1:0)} 天`};
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const chip=(label,count,value,kind)=>`<button class="fchip" data-${kind}-filter="${esc(value)}" aria-pressed="${value===''?'true':'false'}"><span class="fchip-label">${label}</span><span class="fchip-count">${Number(count).toLocaleString()}</span></button>`;
  function renderSummary(){const d=state.data,c=d.counts,a=d.apify||{};document.querySelector('#status-filters').innerHTML=chip('全部',c.sources,'','status')+chip('正常',c.fresh,'ok','status')+chip('等待排程',c.due,'due','status')+chip('錯誤',c.errors,'error','status');const platforms=['Instagram','Facebook','Threads','X','校園公告'];document.querySelector('#platform-filters').innerHTML=chip('全部',c.sources,'','platform')+platforms.map(name=>chip(name,d.sources.filter(s=>s.platform===name).length,name,'platform')).join('');const pacing={RSSHub:'24h／帳號',Instaloader:'18h／帳號',Apify:'7天／粉專'};document.querySelector('#backends').innerHTML=['RSSHub','Instaloader','Apify'].map(name=>{const u=d.apiUsage[name];const extra=name==='Apify'?` · US$${Number(a.usedUsd||0).toFixed(3)}/${Number(a.limitUsd||0).toFixed(2)}`:'';return `<span class="fchip status-static"><strong>${name}</strong> ${pacing[name]} · 24h ${u.requests24h} 次${extra}</span>`}).join('');document.querySelector('#service-note').textContent=a.exhausted?'Apify 本期額度已用完，Facebook 優先抓取會保留在佇列，待下個額度週期再處理。':`Apify 剩餘 US$${Number(a.remainingUsd||0).toFixed(3)}；近 30 天請求 ${d.apiUsage.Apify.requests30d} 次。`;}
  function renderRows(){const q=state.filter.toLowerCase();const rank={error:0,due:1,ok:2};const rows=state.data.sources.filter(s=>(!q||`${s.name} ${s.username} ${s.backend} ${s.kindLabel||''}`.toLowerCase().includes(q))&&(!state.platform||s.platform===state.platform)&&(!state.status||s.status===state.status)).sort((a,b)=>(rank[a.status]-rank[b.status])||((a.nextDue||0)-(b.nextDue||0))||a.name.localeCompare(b.name,'zh-Hant'));const visible=rows.slice(0,state.limit);document.querySelector('#source-count').textContent=`顯示 ${visible.length.toLocaleString()} / ${rows.length.toLocaleString()} 筆`;
    const items=visible.map(s=>`<div class="status-src-row"><div class="status-row-name"><div class="status-name">${esc(s.name)}</div><div class="status-sub">${esc(s.platform)} ${esc(s.kindLabel||'')} · ${esc(s.username)}</div></div><div class="status-backend">${esc(s.backend)}</div><div class="status-row-status"><span class="status-chip ${s.status}">${s.status==='ok'?'正常':s.status==='due'?'等待排程':'錯誤'}</span>${s.lastError?`<details class="status-error-details"><summary>查看詳情</summary><div>${esc(s.lastError)}</div></details>`:''}</div><div class="status-time status-recent"><div>嘗試 ${fmtTime(s.lastAttempt)}</div><div class="status-sub">成功 ${fmtTime(s.lastSuccess)}</div></div><div class="status-time status-next"><div>${fmtTime(s.nextDue)}</div><div class="status-sub">目標 ${fmtInterval(s.targetIntervalHours)} · 實際 ${fmtInterval(s.averageIntervalHours)}</div></div><button class="status-fetch" data-source-request="${esc(s.id)}" ${!state.auth||s.blockedReason?'disabled':''} title="${esc(!state.auth?'登入後可要求優先抓取':s.blockedReason||'加入優先抓取佇列')}">${s.blockedReason?'額度':'先抓'}</button></div>`).join('');const more=visible.length<rows.length?`<button class="filter-expand status-more" data-show-more>顯示更多（還有 ${(rows.length-visible.length).toLocaleString()} 筆）</button>`:'';document.querySelector('#source-rows').innerHTML=items+more||'<p class="status-count">沒有符合的來源。</p>';}
  async function requestFetch(id,button){button.disabled=true;const msg=document.querySelector('#status-message');msg.textContent='正在加入佇列…';try{const r=await fetch('/auth/fetch-requests',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({sourceId:id})});const p=await r.json();if(!r.ok)throw new Error(p.error||'要求失敗');msg.textContent=p.code==='duplicate'?'這個來源已在優先佇列中。':'已加入優先佇列，仍會遵守冷卻與 API 額度。';button.textContent='已排';}catch(e){msg.textContent=e.message;button.disabled=false;}}
  document.addEventListener('click',e=>{const request=e.target.closest('[data-source-request]');if(request){requestFetch(request.dataset.sourceRequest,request);return}if(e.target.closest('[data-show-more]')){state.limit+=120;renderRows();return}const status=e.target.closest('[data-status-filter]');if(status){state.status=status.dataset.statusFilter;state.limit=120;document.querySelectorAll('[data-status-filter]').forEach(x=>x.setAttribute('aria-pressed',String(x===status)));renderRows();return}const platform=e.target.closest('[data-platform-filter]');if(platform){state.platform=platform.dataset.platformFilter;state.limit=120;document.querySelectorAll('[data-platform-filter]').forEach(x=>x.setAttribute('aria-pressed',String(x===platform)));renderRows();}});document.querySelector('#source-search').addEventListener('input',e=>{state.filter=e.target.value;state.limit=120;renderRows()});
  Promise.all([fetch('/api/status.json',{cache:'no-store'}).then(r=>r.json()),fetch('/auth/me',{cache:'no-store'}).then(r=>r.ok?r.json():{authenticated:false}).catch(()=>({authenticated:false}))]).then(([data,me])=>{state.data=data;state.auth=!!me.authenticated;document.querySelector('#snapshot').textContent=`資料快照：${fmtTime(data.generatedAt)} · ${state.auth?'已登入，可要求優先抓取':'登入後可要求優先抓取'}`;renderSummary();renderRows()}).catch(e=>{document.querySelector('#status-message').textContent=`狀態資料讀取失敗：${e.message}`});
})();
</script>
"""


def build() -> dict:
    payload = build_status_payload()
    OUT_API.parent.mkdir(parents=True, exist_ok=True)
    OUT_PAGE.parent.mkdir(parents=True, exist_ok=True)
    OUT_API.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    content = f"""
<section class="status-page">
  <section class="hero"><h1>資料來源狀態</h1><p>查看竹梅每個公開帳號與公告來源的抓取排程。登入後可以要求某個來源優先抓取；系統仍會遵守 Instagram 冷卻與 Apify 額度。<span class="status-snapshot" id="snapshot">資料快照：載入中…</span></p></section>
  <section class="filters" aria-label="來源狀態篩選">
    <div class="filter-row"><span class="label">狀態</span><span class="fgroup" id="status-filters"></span><label class="search-hit status-search"><span class="sr-only">搜尋來源</span><input id="source-search" type="search" placeholder="搜尋名稱、帳號或後端"></label></div>
    <div class="filter-row"><span class="label">平台</span><span class="fgroup" id="platform-filters"></span></div>
    <div class="filter-row"><span class="label">爬法</span><span class="fgroup" id="backends"></span></div>
    <p class="status-service-note" id="service-note"></p>
  </section>
  <p class="status-note">同一個 Instagram 帳號會分成「貼文」與「限時動態」兩列，因為抓法與頻率不同。「實際」需累積至少兩次成功紀錄；沒有新貼文仍算抓取成功。</p>
  <p id="source-count" class="status-count"></p><p id="status-message" class="status-message" role="status"></p>
  <div class="status-src-table"><div class="status-src-head"><span>來源／內容</span><span>爬取方式</span><span>狀態</span><span>最近抓取</span><span>下次／頻率</span><span>優先</span></div><div id="source-rows"></div></div>
</section>{STYLE}{SCRIPT}
"""
    OUT_PAGE.write_text(page_shell("資料來源狀態｜竹梅活動觀測站", "竹梅各公開來源最後與下次爬取時間、實際頻率和 API 使用量。", content, canonical="https://chumei.observe.tw/status/"), encoding="utf-8")
    return payload


if __name__ == "__main__":
    result = build()
    print(f"status: {result['counts']['sources']} sources, {result['counts']['errors']} errors")
