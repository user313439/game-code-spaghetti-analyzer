// Interactive spaghetti map: force / circular layout, zoom, hover focus, filters, plan halos.
function SpaghettiMap(host, opts) {
  const D = window.DATA, W = host.clientWidth, H = host.clientHeight;
  const svg = d3.select(host).append('svg').attr('width', W).attr('height', H);
  const root = svg.append('g');
  const tip = d3.select(host).append('div').attr('class', 'maptooltip').style('opacity', 0);
  const nodes = D.nodes.map(n => ({...n})), byId = Object.fromEntries(nodes.map(n => [n.id, n]));
  const links = D.edges.map(([s, t]) => ({source: byId[s], target: byId[t]}));
  const r = n => 6 + Math.sqrt(n.loc) / 4.5;
  let plan = [], layout = 'force', filter = 'all', focus = null, pinned = null, first = true;

  // layouts are precomputed once
  const sim = d3.forceSimulation(nodes).force('link', d3.forceLink(links).distance(95).strength(.03))
    .force('charge', d3.forceManyBody().strength(-300)).force('x', d3.forceX(W / 2).strength(.07)).force('y', d3.forceY(H / 2).strength(.09))
    .force('collide', d3.forceCollide().radius(d => r(d) + 6)).stop();
  for (let i = 0; i < 360; i++) sim.tick();
  nodes.forEach(n => { n.fx = n.x; n.fy = n.y; });
  const order = [...nodes].sort((a, b) => (b.inCycle - a.inCycle) || (b.si - a.si));
  const R = Math.min(W, H) / 2 - 110;
  order.forEach((n, i) => { const a = i / order.length * 2 * Math.PI - Math.PI / 2; n.cx = W / 2 + R * Math.cos(a); n.cy = H / 2 + R * Math.sin(a); n.ang = a; });
  const P = n => layout === 'force' ? [n.fx, n.fy] : [n.cx, n.cy];
  const path = d => {
    const [ax, ay] = P(d.source), [bx, by] = P(d.target);
    if (layout === 'circle') { const k = .25; return `M${ax},${ay} Q${W/2 + (ax+bx-W)/2*k},${H/2 + (ay+by-H)/2*k} ${bx},${by}`; }
    const mx = (ax + bx) / 2 + (ay - by) * .12, my = (ay + by) / 2 + (bx - ax) * .12; return `M${ax},${ay} Q${mx},${my} ${bx},${by}`;
  };
  const edgeG = root.append('g'), haloG = root.append('g'), nodeG = root.append('g'), labelG = root.append('g');
  const edges = edgeG.selectAll('path').data(links).join('path').attr('fill', 'none');
  const halos = haloG.selectAll('g').data(nodes).join('g');
  halos.append('circle').attr('class', 'halo').attr('fill', 'none').attr('stroke', '#2F6FDB').attr('stroke-width', 3.5);
  halos.append('circle').attr('class', 'hb').attr('r', 9).attr('fill', '#2F6FDB');
  halos.append('text').attr('class', 'hn').attr('fill', '#fff').attr('font-size', 11).attr('font-weight', 800).attr('text-anchor', 'middle').attr('dy', 4);
  const dots = nodeG.selectAll('circle').data(nodes).join('circle').attr('r', r).attr('fill', d => GCOL[d.grade])
    .attr('stroke', '#fff').attr('stroke-width', 2).style('cursor', 'pointer');
  const labels = labelG.selectAll('text').data(nodes).join('text').text(d => d.id).attr('text-anchor', 'middle')
    .attr('font-size', 12).attr('font-weight', 700).attr('fill', '#0F1B2D').attr('paint-order', 'stroke').attr('stroke', '#fff').attr('stroke-width', 4).style('pointer-events', 'none');

  const zoom = d3.zoom().scaleExtent([.5, 5]).on('zoom', e => { root.attr('transform', e.transform); labels.attr('font-size', 12 / e.transform.k).attr('stroke-width', 4 / e.transform.k); });
  svg.call(zoom).on('dblclick.zoom', null);
  svg.on('click', () => { pinned = null; focus = null; paint(); opts.onPick && opts.onPick(null); });

  function visibleEdge(l) {
    if (filter === 'cycle') return l.source.inCycle && l.target.inCycle;
    if (filter === 'plan') return plan.includes(l.source.id) || plan.includes(l.target.id);
    return true;
  }
  function paint() {
    const f = focus || pinned; const T = s => first ? s : s.transition().duration(150);
    const nb = new Set(); if (f) { nb.add(f.id); links.forEach(l => { if (l.source === f) nb.add(l.target.id); if (l.target === f) nb.add(l.source.id); }); }
    T(edges).attr('d', path)
      .attr('stroke', l => f ? (l.source === f ? '#2F6FDB' : l.target === f ? '#E8743B' : '#8FA3C0') : (plan.includes(l.source.id) ? '#2F6FDB' : '#7F93B2'))
      .attr('stroke-opacity', l => !visibleEdge(l) ? 0 : f ? (l.source === f || l.target === f ? .9 : .04) : .26)
      .attr('stroke-width', l => f && (l.source === f || l.target === f) ? 1.8 : 1);
    T(dots).attr('cx', d => P(d)[0]).attr('cy', d => P(d)[1])
      .attr('opacity', d => f ? (nb.has(d.id) ? 1 : .18) : (filter === 'cycle' && !d.inCycle ? .25 : 1));
    halos.attr('display', d => plan.includes(d.id) ? null : 'none').attr('opacity', d => f && !nb.has(d.id) ? .3 : 1);
    halos.select('.halo').attr('cx', d => P(d)[0]).attr('cy', d => P(d)[1]).attr('r', d => r(d) + 5);
    halos.select('.hb').attr('cx', d => P(d)[0] + r(d) + 4).attr('cy', d => P(d)[1] - r(d) - 4);
    halos.select('.hn').attr('x', d => P(d)[0] + r(d) + 4).attr('y', d => P(d)[1] - r(d) - 4).text(d => plan.indexOf(d.id) + 1);
    const circ = layout === 'circle', out = d => r(d) + 8, right = d => Math.cos(d.ang) >= 0;
    labels.attr('text-anchor', d => circ ? (right(d) ? 'start' : 'end') : 'middle').attr('dy', circ ? 4 : 0)
      .attr('font-weight', d => circ && !(d.si >= 88 || plan.includes(d.id)) ? 500 : 700);
    T(labels).attr('x', d => circ ? P(d)[0] + out(d) * Math.cos(d.ang) : P(d)[0]).attr('y', d => circ ? P(d)[1] + out(d) * Math.sin(d.ang) : P(d)[1] - r(d) - 8)
      .attr('opacity', d => f ? (nb.has(d.id) ? 1 : 0) : (circ || d.si >= 88 || plan.includes(d.id) ? 1 : 0));
    first = false;
  }
  dots.on('mouseenter', (e, d) => {
    focus = d; paint();
    tip.html(`<b>${d.id}.c</b><span class="g g${d.grade}">${d.grade} · ${d.si.toFixed(1)}</span><br>${d.loc.toLocaleString()}줄 · 부르는 파일 ${d.fout} · 불리는 파일 ${d.fin}<br>${d.inCycle ? '순환 고리에 포함' : '순환 고리 밖'}${d.topf ? ` · 최고 복잡 함수 ${d.topf[0]} (CC ${d.topf[1]})` : ''}${d.lev ? `<br><em>정리하면 고리에서 ${d.lev}개 파일이 빠질 수 있음</em>` : ''}`)
      .style('opacity', 1);
  }).on('mousemove', e => { const [x, y] = d3.pointer(e, host); tip.style('left', Math.min(x + 14, W - 270) + 'px').style('top', (y + 14) + 'px'); })
    .on('mouseleave', () => { focus = null; tip.style('opacity', 0); paint(); })
    .on('click', (e, d) => { e.stopPropagation(); pinned = d; paint(); opts.onPick && opts.onPick(d); });
  function fitT() {
    const xs = nodes.map(n => P(n)[0]), ys = nodes.map(n => P(n)[1]);
    const x0 = Math.min(...xs) - 30, x1 = Math.max(...xs) + 30, y0 = Math.min(...ys) - 40, y1 = Math.max(...ys) + 30;
    const top = 64, bottom = 56, k = Math.min(W / (x1 - x0), (H - top - bottom) / (y1 - y0), 1.6);
    return d3.zoomIdentity.translate(W / 2 - k * (x0 + x1) / 2, top + (H - top - bottom) / 2 - k * (y0 + y1) / 2).scale(k);
  }
  paint(); svg.call(zoom.transform, fitT());
  return {
    setPlan(p) { plan = p; paint(); }, setLayout(l) { layout = l; paint(); svg.transition().duration(300).call(zoom.transform, fitT()); }, setFilter(f) { filter = f; paint(); },
    zoomBy(k) { svg.transition().call(zoom.scaleBy, k); }, reset() { svg.transition().call(zoom.transform, fitT()); },
    focusOn(id) { pinned = byId[id]; paint(); const [x, y] = P(pinned); svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity.translate(W / 2 - 1.8 * x, H / 2 - 1.8 * y).scale(1.8)); opts.onPick && opts.onPick(pinned); },
  };
}
