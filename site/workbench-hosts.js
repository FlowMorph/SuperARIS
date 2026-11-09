/* Both workbenches and Orca teams share their original story sources. */
(function () {
  "use strict";
  const frame=document.getElementById("orca-demo-frame");
  const panels={herdr:document.getElementById("herdr-demo-panel"),orca:document.getElementById("orca-demo-panel")};
  const texts={
    en:{choose:"Choose a workbench demo",standalone:"Open Orca demo ↗",multiVideos:"Orca multi-model · 1080p / 2×",singleVideos:"Orca single-model · 3 Codex agents",otherMulti:"Multi-model video",otherSingle:"Single-model video",enVideo:"English video",zhVideo:"中文视频",download:"Download"},
    zh:{choose:"选择工作台演示",standalone:"独立打开 Orca 演示 ↗",multiVideos:"Orca 多模型团队 · 1080p / 2×",singleVideos:"Orca 单模型团队 · 三个 Codex Agent",otherMulti:"多模型视频",otherSingle:"单模型视频",enVideo:"English 视频",zhVideo:"中文视频",download:"下载"}
  };
  const badge=document.querySelector(".brand-badge");
  const chips=Array.from(document.querySelectorAll(".hero-role-badges .role-chip"));
  const originalChips=chips.map(chip=>chip.innerHTML);
  let host="herdr";
  let teamMode=new URLSearchParams(location.search).get("team")==="codex"?"codex":"multi";
  function renderTeam() {
    const roles=teamMode==="multi"?["main · Claude Code","engineer · Codex","writer · Gemini / AGY"]:["main · Codex","engineer · Codex","writer · Codex"];
    const colors=teamMode==="multi"?["--cc-coral","--codex-green","--agy-cyan"]:["--codex-green","--codex-green","--codex-green"];
    chips.forEach((chip,index)=>{chip.innerHTML=host==="herdr"?originalChips[index]:'<span class="chip-dot" style="background:var('+colors[index]+')"></span>'+roles[index];});
  }
  function syncFrame() {
    const state=window.SuperARISDemo.getState();
    frame.contentWindow?.postMessage({type:"superaris-host-demo",active:host==="orca",language:state.language,theme:state.theme,teamMode},location.origin);
    const dict={...texts[state.language],videos:teamMode==="multi"?texts[state.language].multiVideos:texts[state.language].singleVideos,other:teamMode==="multi"?texts[state.language].otherSingle:texts[state.language].otherMulti};
    document.querySelectorAll("[data-host-i18n]").forEach(el=>{el.textContent=dict[el.dataset.hostI18n];});
    document.getElementById("host-standalone").href="orca-demo/?lang="+state.language+"&team="+teamMode;
    const prefix=teamMode==="multi"?"orca-multi-demo":"orca-demo";
    document.querySelectorAll("[data-video-language]").forEach(link=>{
      const language=link.dataset.videoLanguage;link.href="media/"+prefix+"-"+language+".mp4";
      if(link.hasAttribute("download"))link.download="SuperARIS-"+prefix+"-"+language+".mp4";
    });
    document.getElementById("orca-other-video").href="media/"+(teamMode==="multi"?"orca-demo":"orca-multi-demo")+"-"+state.language+".mp4";
    renderTeam();
  }
  function selectHost(value) {
    host=value;
    Object.keys(panels).forEach(key=>{panels[key].hidden=key!==host;document.getElementById("host-"+key).setAttribute("aria-selected",String(key===host));});
    window.SuperARISDemo.setHostActive(host==="herdr");
    badge.textContent=host==="herdr"?"Herdr + ARIS Workbench":"Orca + ARIS Workbench";
    syncFrame();
  }
  Object.keys(panels).forEach(key=>document.getElementById("host-"+key).addEventListener("click",()=>selectHost(key)));
  frame.addEventListener("load",syncFrame);
  window.addEventListener("message",event=>{
    if(event.source!==frame.contentWindow || event.origin!==location.origin)return;
    if(event.data?.type==="superaris-team-mode" && ["multi","codex"].includes(event.data.teamMode)) {teamMode=event.data.teamMode;syncFrame();}
    if(event.data?.type==="superaris-demo-size") {const height=Number(event.data.height);if(Number.isFinite(height)&&height>0)frame.style.height=Math.ceil(height)+"px";}
  });
  ["lang-en","lang-zh","themeDarkBtn","themeWarmBtn"].forEach(id=>document.getElementById(id).addEventListener("click",syncFrame));
  window.SuperARISHosts={select:selectHost,getHost:()=>host,getTeamMode:()=>teamMode};
  frame.src="orca-demo/?embedded=1&lang="+window.SuperARISDemo.getState().language+"&team="+teamMode;
  selectHost(new URLSearchParams(location.search).get("host")==="orca"?"orca":"herdr");
})();
