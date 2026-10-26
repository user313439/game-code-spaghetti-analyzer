const LOGO = `<svg width="30" height="30" viewBox="0 0 32 32" fill="none"><rect width="32" height="32" rx="9" fill="#E8F0FD"/>
<g stroke="#2F6FDB" stroke-width="1.6"><path d="M9 10 L16 16 L23 9 M16 16 L10 23 M16 16 L23 22 M9 10 L10 23 M23 9 L23 22"/></g>
<g fill="#2F6FDB"><circle cx="9" cy="10" r="2.6"/><circle cx="23" cy="9" r="2.6"/><circle cx="16" cy="16" r="3.2"/><circle cx="10" cy="23" r="2.6"/><circle cx="23" cy="22" r="2.6"/></g></svg>`;
const MLAB = {cc:'분기 복잡도', coupling:'연결된 파일', dependency_cycle:'순환 고리', global_state:'전역 변수 접근', game_loop_centrality:'게임 루프 근접'};
const MHELP = {cc:'함수 안의 if·switch·반복이 많을수록 높습니다', coupling:'이 파일이 부르거나 이 파일을 부르는 다른 파일 수', dependency_cycle:'서로 꼬리를 물고 참조하는 고리에 얽힌 정도', global_state:'여러 곳에서 함께 바꾸는 전역 변수를 건드리는 횟수', game_loop_centrality:'매 프레임 실행되는 게임 루프와 가까운 정도'};
const GCOL = {A:'#2E9E6B',B:'#7CB342',C:'#E0A526',D:'#E8743B',E:'#D64545'};
function topbar(active){
  const steps = ['소스 가져오기','엉킴 진단','AI 리팩토링','수정 결과·검증'];
  return `<header class="topbar"><div class="logo">${LOGO}<div>GAME CODE<small>SPAGHETTI ANALYZER</small></div></div>
  <div class="crumb">분석 기록 / <b>OpenTyrian</b></div>
  <nav class="steps">${steps.map((s,i)=>`<span class="step ${i<active?'done':''} ${i===active?'on':''}"><i>${i<active?'✓':i+1}</i>${s}</span>`).join('')}</nav>
  <button class="icon-btn" title="다크 모드">☾</button></header>`;
}
function reasons(t){ // top-2 metric reasons in plain words
  return Object.entries(t.pct).sort((a,b)=>b[1]-a[1]).slice(0,2).map(([k])=>k);
}
function drawGraph(svg, opts={}){
  const W = svg.clientWidth, H = svg.clientHeight, D = window.DATA;
  const nodes = D.nodes.map(n=>({...n})), byId = Object.fromEntries(nodes.map(n=>[n.id,n]));
  const links = D.edges.map(([s,t])=>({source:s,target:t}));
  const r = n => 4 + Math.sqrt(n.loc)/6;
  const sim = d3.forceSimulation(nodes).force('link', d3.forceLink(links).id(d=>d.id).distance(90).strength(.03))
    .force('charge', d3.forceManyBody().strength(-380)).force('center', d3.forceCenter(W/2, H/2))
    .force('collide', d3.forceCollide().radius(d=>r(d)+4)).stop();
  for (let i=0;i<320;i++) sim.tick();
  nodes.forEach(n=>{n.x=Math.max(30,Math.min(W-30,n.x)); n.y=Math.max(30,Math.min(H-30,n.y));});
  const g = d3.select(svg);
  const hot = new Set(opts.highlight||[]);
  g.append('g').selectAll('path').data(links).join('path')
    .attr('d', d=>{const a=d.source,b=d.target,mx=(a.x+b.x)/2+(a.y-b.y)*.15,my=(a.y+b.y)/2+(b.x-a.x)*.15;return `M${a.x},${a.y} Q${mx},${my} ${b.x},${b.y}`})
    .attr('fill','none').attr('stroke', d=>hot.has(d.source.id)?'#D64545':'#9DB0CC')
    .attr('stroke-opacity', d=>hot.has(d.source.id)?.45:.22).attr('stroke-width', d=>hot.has(d.source.id)?1.4:1);
  const node = g.append('g').selectAll('g').data(nodes).join('g').attr('transform',d=>`translate(${d.x},${d.y})`);
  node.append('circle').attr('r',r).attr('fill',d=>GCOL[d.grade]).attr('fill-opacity',d=>hot.size&&!hot.has(d.id)?.55:.95)
    .attr('stroke','#fff').attr('stroke-width',2);
  node.filter(d=>d.si>=88 || hot.has(d.id)).append('text').text(d=>d.id).attr('y',d=>-r(d)-6).attr('text-anchor','middle')
    .attr('font-size',12).attr('font-weight',700).attr('fill','#0F1B2D').attr('paint-order','stroke').attr('stroke','#fff').attr('stroke-width',4);
}
