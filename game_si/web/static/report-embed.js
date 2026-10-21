// Only a sandboxed report window sends its size; the workspace checks event.source.
(function() {
  const table=document.getElementById("hotspot-table");
  if(table && !table.parentElement.classList.contains("report-table-scroll")) {
    const wrapper=document.createElement("div");
    wrapper.className="report-table-scroll";
    table.parentElement.insertBefore(wrapper,table);
    wrapper.appendChild(table);
  }
  if(parent===window) return;
  let last="";
  function resize() {
    const style=getComputedStyle(document.body);
    const height=Math.ceil(document.body.getBoundingClientRect().height + parseFloat(style.marginTop||0) + parseFloat(style.marginBottom||0)+4);
    const documentHeight=document.documentElement.scrollHeight, signature=[height,documentHeight,innerHeight].join(":");
    if(signature!==last) { last=signature; parent.postMessage({type:"game-si-report-height",height,documentHeight,viewportHeight:innerHeight},"*"); }
  }
  new ResizeObserver(resize).observe(document.body);
  window.addEventListener("load",resize);
  window.addEventListener("resize",resize);
  resize();
})();
