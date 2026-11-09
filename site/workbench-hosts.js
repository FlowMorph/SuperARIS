/* One Orca story source, embedded alongside the unchanged Herdr story. */
(function () {
  "use strict";
  const frame=document.getElementById("orca-demo-frame");
  const panels={herdr:document.getElementById("herdr-demo-panel"),orca:document.getElementById("orca-demo-panel")};
  const texts={
    en:{choose:"Choose a workbench demo",standalone:"Open Orca demo ↗",videos:"Orca recordings · 1080p / 2×",enVideo:"English video",zhVideo:"中文视频",download:"Download"},
    zh:{choose:"选择工作台演示",standalone:"独立打开 Orca 演示 ↗",videos:"Orca 录屏 · 1080p / 2×",enVideo:"English 视频",zhVideo:"中文视频",download:"下载"}
  };
  const badge=document.querySelector(".brand-badge");
  const chips=Array.from(document.querySelectorAll(".hero-role-badges .role-chip"));
  const originalChips=chips.map(chip=>chip.innerHTML);
  let host="herdr";
  function syncFrame() {
    const state=window.SuperARISDemo.getState();
    frame.contentWindow?.postMessage({type:"superaris-host-demo",active:host==="orca",language:state.language,theme:state.theme},location.origin);
    document.querySelectorAll("[data-host-i18n]").forEach(el=>{ el.textContent=texts[state.language][el.dataset.hostI18n]; });
    document.getElementById("host-standalone").href="orca-demo/?lang="+state.language;
  }
  function selectHost(value) {
    host=value;
    Object.keys(panels).forEach(key=>{
      panels[key].hidden=key!==host;
      document.getElementById("host-"+key).setAttribute("aria-selected",String(key===host));
    });
    window.SuperARISDemo.setHostActive(host==="herdr");
    badge.textContent=host==="herdr"?"Herdr + ARIS Workbench":"Orca + ARIS Workbench";
    chips.forEach((chip,index)=>{
      chip.innerHTML=host==="herdr"?originalChips[index]:'<span class="chip-dot" style="background:var(--codex-green)"></span>'+["main · Codex","engineer · Codex","writer · Codex"][index];
    });
    syncFrame();
  }
  Object.keys(panels).forEach(key=>document.getElementById("host-"+key).addEventListener("click",()=>selectHost(key)));
  frame.addEventListener("load",syncFrame);
  window.addEventListener("message",event=>{
    if(event.source!==frame.contentWindow || event.origin!==location.origin || event.data?.type!=="superaris-demo-size") return;
    const height=Number(event.data.height);
    if(Number.isFinite(height) && height>0) frame.style.height=Math.ceil(height)+"px";
  });
  ["lang-en","lang-zh","themeDarkBtn","themeWarmBtn"].forEach(id=>document.getElementById(id).addEventListener("click",syncFrame));
  window.SuperARISHosts={select:selectHost,getHost:()=>host};
  selectHost(new URLSearchParams(location.search).get("host")==="orca"?"orca":"herdr");
})();
