"""HTML 대시보드 생성.

단일 파일(single-file) 형태의 HTML을 생성한다. CDN 또는 외부 리소스에 의존하지 않으며,
CSS·SVG·Vanilla JavaScript만 사용한다. 파일 더블클릭으로 어디서든 열린다.

W6에서 다음 섹션을 제공한다.
    - Summary: 총 클래스/메서드 수, 등급 분포, 가중치 표
    - Hotspot Table: G-SI 상위 클래스
    - Module Table: 모듈 단위 집계

W7에서 다음 섹션이 추가될 예정이다.
    - Dependency Graph (Cytoscape.js)
    - Cycle Explorer
"""

from __future__ import annotations

import datetime as _dt
import html
import json
import math
from pathlib import Path
from typing import Any

from .metrics import MetricsResult
from .si import ScoringResult, scoring_to_dict


# 등급별 색상 (CSS, 대시보드 도넛/배지 공통)
GRADE_COLORS = {
    "A": "#3b8e5a",   # 진한 녹색
    "B": "#7fb95a",   # 연두
    "C": "#e3b341",   # 노랑
    "D": "#ef7d3c",   # 주황
    "E": "#d24343",   # 빨강
}


def generate_dashboard(
    project_name: str,
    scoring: ScoringResult,
    metrics: MetricsResult,
    output_path: Path,
    top_n: int = 30,
) -> Path:
    """대시보드 HTML을 생성하고 경로를 반환한다."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    html_doc = _render_html(project_name, scoring, metrics, top_n)
    output_path.write_text(html_doc, encoding="utf-8")
    return output_path


# ---------------------------------------------------------------------------
# 렌더링
# ---------------------------------------------------------------------------


def _render_html(
    project_name: str,
    scoring: ScoringResult,
    metrics: MetricsResult,
    top_n: int,
) -> str:
    analyzed_at = _dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    hotspots = sorted(scoring.class_scores, key=lambda c: -c.si)[:top_n]
    module_rows = sorted(scoring.module_scores, key=lambda m: -m.si_max)
    si_by_fqn = {cs.fqn: cs for cs in scoring.class_scores}

    # 임베드용 데이터 (대시보드 JS에서 사용할 수 있도록 전체 데이터를 객체로 박는다)
    embedded = {
        "project": project_name,
        "analyzed_at": analyzed_at,
        "scoring": scoring_to_dict(scoring),
        "cycle_count": len(metrics.sccs),
    }
    embedded_json = json.dumps(embedded, ensure_ascii=False, indent=None, default=_json_default)

    return _HTML_TEMPLATE.format(
        project_name=html.escape(project_name),
        analyzed_at=analyzed_at,
        summary_cards=_render_summary_cards(scoring, metrics),
        grade_donut=_render_grade_donut(scoring.grade_distribution),
        weights_table=_render_weights_table(scoring.weights),
        hotspot_table=_render_hotspot_table(hotspots),
        module_table=_render_module_table(module_rows),
        dependency_graph=_render_dependency_graph(scoring, metrics, top_n=50),
        cycle_explorer=_render_cycle_explorer(metrics, si_by_fqn),
        embedded_json=embedded_json,
    )


def _json_default(obj: Any) -> Any:
    if isinstance(obj, set):
        return sorted(obj)
    return str(obj)


# ---------------------------------------------------------------------------
# 섹션 빌더
# ---------------------------------------------------------------------------


def _render_summary_cards(scoring: ScoringResult, metrics: MetricsResult) -> str:
    si_values = [c.si for c in scoring.class_scores]
    avg_si = sum(si_values) / len(si_values) if si_values else 0.0
    max_si = max(si_values) if si_values else 0.0
    risk_count = sum(1 for c in scoring.class_scores if c.grade in ("D", "E"))

    cards = [
        ("분석 클래스", f"{scoring.total_classes:,}"),
        ("분석 메서드", f"{scoring.total_methods:,}"),
        ("의존성 순환(SCC ≥ 2)", f"{len(metrics.sccs):,}"),
        ("평균 G-SI", f"{avg_si:.1f}"),
        ("최대 G-SI", f"{max_si:.1f}"),
        ("위험(D/E) 클래스", f"{risk_count:,}"),
    ]
    return "".join(
        f'<div class="card"><div class="card-label">{html.escape(label)}</div>'
        f'<div class="card-value">{html.escape(value)}</div></div>'
        for label, value in cards
    )


def _render_grade_donut(distribution: dict[str, int]) -> str:
    """등급 분포를 SVG 도넛 차트로 렌더링."""
    total = sum(distribution.values()) or 1
    cx, cy, r, stroke = 90, 90, 70, 28
    circumference = 2 * math.pi * r

    segments = []
    offset = 0.0
    legend_items = []
    for grade in "ABCDE":
        count = distribution.get(grade, 0)
        if total <= 0:
            pct = 0.0
        else:
            pct = count / total
        length = pct * circumference
        color = GRADE_COLORS[grade]
        if length > 0:
            segments.append(
                f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
                f'stroke="{color}" stroke-width="{stroke}" '
                f'stroke-dasharray="{length:.3f} {circumference:.3f}" '
                f'stroke-dashoffset="{-offset:.3f}" transform="rotate(-90 {cx} {cy})"/>'
            )
        offset += length
        legend_items.append(
            f'<div class="legend-item">'
            f'<span class="swatch" style="background:{color}"></span>'
            f'<span>{grade}</span>'
            f'<span class="count">{count:,} ({pct * 100:.1f}%)</span>'
            f'</div>'
        )

    return f'''<div class="donut-container">
        <svg viewBox="0 0 180 180" width="180" height="180" class="donut">
            <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#1f2937" stroke-width="{stroke}"/>
            {''.join(segments)}
            <text x="{cx}" y="{cy}" text-anchor="middle" dominant-baseline="central"
                  fill="#cbd5e1" font-size="20" font-weight="600">{total:,}</text>
        </svg>
        <div class="legend">{''.join(legend_items)}</div>
    </div>'''


def _render_weights_table(weights: dict[str, float]) -> str:
    rows = "".join(
        f'<tr><td>{html.escape(k)}</td><td class="num">{v:.3f}</td></tr>'
        for k, v in weights.items()
    )
    return f'''<table class="kv-table">
        <thead><tr><th>항목</th><th>가중치</th></tr></thead>
        <tbody>{rows}</tbody>
    </table>'''


def _render_hotspot_table(hotspots) -> str:
    rows = []
    for i, cs in enumerate(hotspots, 1):
        reasons = ", ".join(cs.top_reasons) if cs.top_reasons else "—"
        rows.append(
            f'<tr data-grade="{cs.grade}">'
            f'<td class="num rank">{i}</td>'
            f'<td><span class="grade-badge" style="background:{GRADE_COLORS[cs.grade]}">{cs.grade}</span></td>'
            f'<td class="num">{cs.si:.1f}</td>'
            f'<td class="fqn" title="{html.escape(cs.fqn)}">{html.escape(cs.fqn)}</td>'
            f'<td class="num">{cs.raw["cc"]:.1f}</td>'
            f'<td class="num">{int(cs.raw["coupling"])}</td>'
            f'<td class="num">{int(cs.raw["global_state"])}</td>'
            f'<td class="num">{int(cs.raw["dependency_cycle"])}</td>'
            f'<td class="num">{cs.raw["game_loop_centrality"]:.2f}</td>'
            f'<td class="reasons">{html.escape(reasons)}</td>'
            f'<td class="path"><code>{html.escape(cs.file_path)}:{cs.start_line}</code></td>'
            f'</tr>'
        )
    body = "".join(rows) if rows else '<tr><td colspan="11" class="empty">분석된 클래스가 없습니다.</td></tr>'

    return f'''<div class="table-controls">
        <input type="text" id="hotspot-filter" placeholder="필터: FQN 또는 파일 경로 부분 일치">
        <select id="grade-filter">
            <option value="">전체 등급</option>
            <option value="E">E (심각)</option>
            <option value="D">D (위험)</option>
            <option value="C">C (주의)</option>
            <option value="B">B (일반)</option>
            <option value="A">A (안전)</option>
        </select>
    </div>
    <table class="hotspot-table" id="hotspot-table">
        <thead><tr>
            <th>#</th><th>등급</th><th data-sort="num" class="sortable">G-SI</th>
            <th data-sort="str" class="sortable">클래스 FQN</th>
            <th data-sort="num" class="sortable">CC</th>
            <th data-sort="num" class="sortable">Coupling</th>
            <th data-sort="num" class="sortable">GlobalState</th>
            <th data-sort="num" class="sortable">CycleSize</th>
            <th data-sort="num" class="sortable">GameLoop</th>
            <th>주요 원인</th><th>위치</th>
        </tr></thead>
        <tbody>{body}</tbody>
    </table>'''


def _render_dependency_graph(
    scoring: ScoringResult,
    metrics: MetricsResult,
    top_n: int = 50,
) -> str:
    """상위 hotspot 클래스와 그 인접 노드를 SVG force-directed 그래프로 렌더링한다.

    좌표는 NetworkX spring_layout으로 Python에서 미리 계산해 SVG에 박아둔다.
    외부 JavaScript 라이브러리(Cytoscape.js 등)에 의존하지 않으면서도
    한눈에 의존성 구조를 파악할 수 있다.
    """
    import networkx as nx

    g = metrics.class_graph
    if g.number_of_nodes() == 0:
        return '<div class="empty">의존성 그래프를 그릴 노드가 없습니다.</div>'

    # 상위 hotspot 중심으로 부분 그래프 추출 (G-SI 상위 top_n + 그 1-홉 이웃)
    hotspot_fqns = [cs.fqn for cs in sorted(scoring.class_scores, key=lambda c: -c.si)[:top_n]]
    seed = set(hotspot_fqns)
    expanded: set[str] = set(seed)
    for fqn in seed:
        if fqn in g:
            expanded.update(g.predecessors(fqn))
            expanded.update(g.successors(fqn))
    subgraph = g.subgraph(expanded).copy()

    if subgraph.number_of_nodes() == 0:
        return '<div class="empty">선택된 hotspot에 의존성 엣지가 없습니다.</div>'

    # spring_layout으로 좌표 계산. seed 고정으로 결과를 결정적으로 만든다.
    pos = nx.spring_layout(
        subgraph,
        k=1.5 / max(1, subgraph.number_of_nodes() ** 0.5),
        iterations=80,
        seed=42,
    )

    width, height, margin = 1100, 620, 40
    si_lookup = {cs.fqn: cs for cs in scoring.class_scores}

    # 좌표 정규화
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    if not xs or not ys or (max(xs) == min(xs)) or (max(ys) == min(ys)):
        return '<div class="empty">레이아웃 좌표를 계산할 수 없습니다.</div>'
    x_range = max(xs) - min(xs)
    y_range = max(ys) - min(ys)

    def project(p):
        x = (p[0] - min(xs)) / x_range * (width - 2 * margin) + margin
        y = (p[1] - min(ys)) / y_range * (height - 2 * margin) + margin
        return x, y

    # 엣지
    edges_svg = []
    for u, v in subgraph.edges():
        x1, y1 = project(pos[u])
        x2, y2 = project(pos[v])
        edges_svg.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="#334155" stroke-width="0.8" stroke-opacity="0.6" marker-end="url(#arrow)"/>'
        )

    # 노드
    nodes_svg = []
    for fqn in subgraph.nodes():
        x, y = project(pos[fqn])
        cs = si_lookup.get(fqn)
        if cs is not None:
            color = GRADE_COLORS[cs.grade]
            radius = 4 + min(12, cs.raw.get("coupling", 0) * 0.3)
            si_text = f"{cs.si:.0f}"
            label = cs.name
        else:
            color = "#475569"
            radius = 3
            si_text = "?"
            label = fqn.rsplit(".", 1)[-1] if "." in fqn else fqn
        nodes_svg.append(
            f'<g class="node" data-fqn="{html.escape(fqn)}">'
            f'<title>{html.escape(fqn)} (G-SI={si_text})</title>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" '
            f'fill="{color}" stroke="#0f172a" stroke-width="1"/>'
            f'<text x="{x:.1f}" y="{y - radius - 3:.1f}" text-anchor="middle" '
            f'fill="#cbd5e1" font-size="9">{html.escape(label)}</text>'
            f'</g>'
        )

    return f'''<div class="graph-meta">
        표시 노드 {subgraph.number_of_nodes()} · 엣지 {subgraph.number_of_edges()} ·
        (G-SI 상위 {top_n}개 hotspot + 1-홉 이웃)
    </div>
    <svg viewBox="0 0 {width} {height}" width="100%" height="{height}" class="depgraph">
        <defs>
            <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                <path d="M0,0 L8,4 L0,8 z" fill="#475569"/>
            </marker>
        </defs>
        <g class="edges">{''.join(edges_svg)}</g>
        <g class="nodes">{''.join(nodes_svg)}</g>
    </svg>'''


def _render_cycle_explorer(metrics: MetricsResult, si_lookup: dict) -> str:
    """크기 ≥ 2 인 SCC 목록을 표시한다. 각 cycle의 멤버 클래스와 평균 G-SI를 보여준다."""
    if not metrics.sccs:
        return '<div class="empty">크기 ≥ 2 인 순환 의존성이 발견되지 않았습니다.</div>'

    sccs_sorted = sorted(metrics.sccs, key=len, reverse=True)

    rows = []
    for idx, scc in enumerate(sccs_sorted, 1):
        members = sorted(scc)
        si_values = [si_lookup[fqn].si for fqn in members if fqn in si_lookup]
        avg_si = sum(si_values) / len(si_values) if si_values else 0.0
        max_si = max(si_values) if si_values else 0.0
        grade = _grade(max_si)
        member_html = "".join(
            f'<li><code title="G-SI={si_lookup[m].si:.1f}" '
            f'class="cycle-member grade-{si_lookup[m].grade}">{html.escape(m)}</code></li>'
            if m in si_lookup else
            f'<li><code class="cycle-member">{html.escape(m)}</code></li>'
            for m in members[:20]
        )
        more = f" ... 외 {len(members) - 20}개" if len(members) > 20 else ""
        rows.append(
            f'<details class="cycle-entry"><summary>'
            f'<span class="cycle-rank">#{idx}</span>'
            f'<span class="grade-badge" style="background:{GRADE_COLORS[grade]}">{grade}</span>'
            f'크기 {len(scc)} · 평균 G-SI {avg_si:.1f} · 최대 {max_si:.1f}'
            f'</summary><ul>{member_html}</ul>{more}</details>'
        )
    return f'<div class="cycle-list">{"".join(rows)}</div>'


def _grade(score: float) -> str:
    """등급 분류 — `_render_grade_donut`과 분리되어 있어 별도 함수로 둔다."""
    if score < 20: return "A"
    if score < 40: return "B"
    if score < 60: return "C"
    if score < 80: return "D"
    return "E"


def _render_module_table(modules) -> str:
    rows = []
    for ms in modules:
        rows.append(
            f'<tr>'
            f'<td>{html.escape(ms.module)}</td>'
            f'<td><span class="grade-badge" style="background:{GRADE_COLORS[ms.grade]}">{ms.grade}</span></td>'
            f'<td class="num">{ms.si_mean:.1f}</td>'
            f'<td class="num">{ms.si_max:.1f}</td>'
            f'<td class="num">{ms.file_count:,}</td>'
            f'<td class="num">{ms.class_count:,}</td>'
            f'</tr>'
        )
    body = "".join(rows) if rows else '<tr><td colspan="6" class="empty">집계할 모듈이 없습니다.</td></tr>'
    return f'''<table class="module-table">
        <thead><tr><th>모듈</th><th>등급</th><th>평균 G-SI</th><th>최대 G-SI</th><th>파일 수</th><th>클래스 수</th></tr></thead>
        <tbody>{body}</tbody>
    </table>'''


# ---------------------------------------------------------------------------
# HTML 템플릿
# ---------------------------------------------------------------------------


_HTML_TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{project_name} — Game Spaghetti Index Report</title>
<style>
  :root {{
    --bg: #0f172a; --panel: #111827; --panel2: #1f2937;
    --fg: #e5e7eb; --muted: #94a3b8; --accent: #60a5fa; --border: #1f2937;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--fg);
    font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
    line-height: 1.5; font-size: 14px;
  }}
  header {{ padding: 24px 32px; background: var(--panel); border-bottom: 1px solid var(--border); }}
  header h1 {{ margin: 0 0 4px 0; font-size: 22px; }}
  header .meta {{ color: var(--muted); font-size: 13px; }}
  main {{ padding: 24px 32px; max-width: 1400px; margin: 0 auto; }}
  section {{ margin-bottom: 32px; }}
  section h2 {{ font-size: 17px; margin: 0 0 12px 0; color: #cbd5e1; }}
  .card-row {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; }}
  .card {{ background: var(--panel); padding: 14px 16px; border-radius: 8px; border: 1px solid var(--border); }}
  .card-label {{ color: var(--muted); font-size: 12px; }}
  .card-value {{ font-size: 22px; font-weight: 600; margin-top: 4px; }}
  .grid-2 {{ display: grid; grid-template-columns: 320px 1fr; gap: 24px; align-items: start; }}
  .panel {{ background: var(--panel); padding: 16px; border-radius: 8px; border: 1px solid var(--border); }}
  .donut-container {{ display: flex; align-items: center; gap: 16px; }}
  .donut {{ flex-shrink: 0; }}
  .legend {{ display: flex; flex-direction: column; gap: 6px; }}
  .legend-item {{ display: flex; align-items: center; gap: 8px; font-size: 13px; }}
  .legend-item .count {{ color: var(--muted); margin-left: auto; }}
  .swatch {{ width: 14px; height: 14px; border-radius: 3px; display: inline-block; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }}
  th {{ background: var(--panel2); color: #cbd5e1; font-weight: 600; position: sticky; top: 0; }}
  th.sortable {{ cursor: pointer; user-select: none; }}
  th.sortable::after {{ content: " ↕"; color: var(--muted); font-size: 11px; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
  td.rank {{ color: var(--muted); }}
  td.fqn {{ font-family: ui-monospace, "Cascadia Code", monospace; font-size: 12px; }}
  td.path code {{ font-size: 11px; color: var(--muted); }}
  td.empty {{ text-align: center; color: var(--muted); padding: 20px; }}
  tr[data-grade="E"] {{ background: rgba(210,67,67,0.07); }}
  tr[data-grade="D"] {{ background: rgba(239,125,60,0.05); }}
  .grade-badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px;
                  color: #fff; font-weight: 600; font-size: 12px; min-width: 22px; text-align: center; }}
  .kv-table th, .kv-table td {{ padding: 6px 10px; }}
  .table-controls {{ display: flex; gap: 8px; margin-bottom: 8px; }}
  .table-controls input, .table-controls select {{
    background: var(--panel2); color: var(--fg); border: 1px solid var(--border);
    padding: 6px 10px; border-radius: 6px; font-size: 13px;
  }}
  .table-controls input {{ flex: 1; }}
  .graph-panel {{ overflow: hidden; }}
  .graph-meta {{ color: var(--muted); font-size: 12px; margin-bottom: 8px; }}
  .depgraph {{ display: block; background: #0b1322; border-radius: 6px; }}
  .depgraph .node:hover circle {{ stroke: var(--accent); stroke-width: 2; }}
  .cycle-list details {{ background: var(--panel2); padding: 10px 12px; border-radius: 6px; margin-bottom: 6px; }}
  .cycle-list summary {{ cursor: pointer; display: flex; gap: 10px; align-items: center; }}
  .cycle-rank {{ color: var(--muted); font-variant-numeric: tabular-nums; }}
  .cycle-list ul {{ margin: 10px 0 0 24px; padding: 0; }}
  .cycle-list li {{ margin-bottom: 2px; }}
  .cycle-member {{ font-family: ui-monospace, monospace; font-size: 12px; padding: 1px 6px;
                   border-radius: 4px; background: rgba(255,255,255,0.05); }}
  .cycle-member.grade-D, .cycle-member.grade-E {{ background: rgba(210,67,67,0.15); }}
  .empty {{ color: var(--muted); padding: 12px; text-align: center; }}
  footer {{ padding: 20px 32px; color: var(--muted); font-size: 12px; text-align: center; border-top: 1px solid var(--border); }}
</style>
</head>
<body>
<header>
  <h1>{project_name} <span style="color: var(--muted); font-weight: 400; font-size: 15px;">Game Spaghetti Index Report</span></h1>
  <div class="meta">분석 시각: {analyzed_at}</div>
</header>
<main>

<section>
  <h2>Summary</h2>
  <div class="card-row">{summary_cards}</div>
</section>

<section>
  <h2>등급 분포 및 가중치</h2>
  <div class="grid-2">
    <div class="panel">{grade_donut}</div>
    <div class="panel">{weights_table}</div>
  </div>
</section>

<section>
  <h2>Hotspot Table (G-SI 상위)</h2>
  {hotspot_table}
</section>

<section>
  <h2>Dependency Graph (G-SI 상위 hotspot 중심)</h2>
  <div class="panel graph-panel">{dependency_graph}</div>
</section>

<section>
  <h2>Cycle Explorer (Strongly Connected Components)</h2>
  <div class="panel">{cycle_explorer}</div>
</section>

<section>
  <h2>Module Summary</h2>
  {module_table}
</section>

</main>
<footer>
  Generated by <code>game-si</code> · static-only metrics (G-SI-Static) · CDN-free single-file report
</footer>

<script>
(function() {{
  const dataRoot = {embedded_json};
  // 향후 W7 그래프에서 dataRoot.scoring을 사용한다.
  window.__GAME_SI__ = dataRoot;

  // ----- Hotspot 테이블 필터 -----
  const textInput = document.getElementById('hotspot-filter');
  const gradeSelect = document.getElementById('grade-filter');
  const table = document.getElementById('hotspot-table');

  function applyFilters() {{
    if (!table) return;
    const needle = (textInput.value || '').toLowerCase();
    const grade = gradeSelect.value;
    table.querySelectorAll('tbody tr').forEach(tr => {{
      const fqnCell = tr.querySelector('.fqn');
      const pathCell = tr.querySelector('.path');
      const text = ((fqnCell ? fqnCell.textContent : '') + ' ' + (pathCell ? pathCell.textContent : '')).toLowerCase();
      const gradeOk = !grade || tr.getAttribute('data-grade') === grade;
      const textOk = !needle || text.includes(needle);
      tr.style.display = (gradeOk && textOk) ? '' : 'none';
    }});
  }}
  if (textInput) textInput.addEventListener('input', applyFilters);
  if (gradeSelect) gradeSelect.addEventListener('change', applyFilters);

  // ----- 정렬 -----
  if (table) {{
    table.querySelectorAll('th.sortable').forEach((th, idx) => {{
      let asc = false;
      th.addEventListener('click', () => {{
        const colIdx = Array.from(th.parentNode.children).indexOf(th);
        const numeric = th.getAttribute('data-sort') === 'num';
        const rows = Array.from(table.querySelectorAll('tbody tr'));
        rows.sort((a, b) => {{
          const av = a.children[colIdx].textContent.trim();
          const bv = b.children[colIdx].textContent.trim();
          if (numeric) {{
            return (parseFloat(av) - parseFloat(bv)) * (asc ? 1 : -1);
          }}
          return av.localeCompare(bv) * (asc ? 1 : -1);
        }});
        const tbody = table.querySelector('tbody');
        rows.forEach(r => tbody.appendChild(r));
        asc = !asc;
      }});
    }});
  }}
}})();
</script>
</body>
</html>
"""
