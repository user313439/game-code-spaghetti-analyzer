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
        help_box=_render_help_box(),
        health_hero=_render_health_hero(scoring, metrics),
        summary_cards=_render_summary_cards(scoring, metrics),
        grade_donut=_render_grade_donut(scoring.grade_distribution),
        weights_table=_render_weights_table(scoring.weights),
        hotspot_table=_render_hotspot_table(hotspots, top_n),
        module_table=_render_module_table(module_rows),
        dependency_graph=_render_dependency_graph(scoring, metrics, top_n=50),
        cycle_explorer=_render_cycle_explorer(metrics, si_by_fqn),
        embedded_json=embedded_json,
    )


def _render_help_box() -> str:
    """대시보드 상단에 두는 \"이 대시보드 읽는 법\" 도움말 박스."""
    return '''<details class="help">
    <summary>이 대시보드 읽는 법 (펼치기)</summary>
    <div class="help-body">
        <p><strong>Game Spaghetti Index (G-SI)</strong>는 게임 코드의 각 클래스가
        얼마나 다른 코드와 얽혀 있는지를 0~100점으로 측정한 지표입니다.
        <strong>점수가 높을수록 위험</strong>합니다.</p>
        <ul>
            <li><strong>Project Health</strong> — 프로젝트 전체에 대한 종합 점수.
                평균 G-SI, 위험 클래스 비율, 순환 의존성 수, 평균 결합도를 함께 본
                "이 프로젝트의 스파게티 정도" 한 개입니다.</li>
            <li><strong>등급 분포 도넛</strong> — 프로젝트 안의 모든 클래스를
                A(안전) ~ E(심각)로 나눠 보여줍니다. <strong>모든 클래스의 분포</strong>를 한눈에 봅니다.</li>
            <li><strong>Hotspot Table</strong> — <em>가장 위험한 상위 N개</em>만
                골라서 보여주는 표입니다. 그래서 등급은 대부분 D나 E이고,
                이는 정상입니다. 다른 등급의 클래스를 보고 싶다면 등급 필터를 사용하세요.</li>
            <li><strong>Dependency Graph</strong> — 위험 클래스와 그 이웃들이 어떻게
                연결되어 있는지 시각화. 마우스를 노드 위에 올리면 자세한 정보가 우측 패널에 나타납니다.</li>
            <li><strong>Cycle Explorer</strong> — A→B→C→A처럼 순환 참조에 빠진
                클래스 묶음을 보여줍니다. 순환은 변경 영향을 추적하기 어렵게 만드는
                대표적 위험 신호입니다.</li>
        </ul>
        <p class="help-grade">
            등급 의미 →
            <span class="grade-badge" style="background:#3b8e5a">A</span> 안전 ·
            <span class="grade-badge" style="background:#7fb95a">B</span> 일반 ·
            <span class="grade-badge" style="background:#e3b341">C</span> 보통 ·
            <span class="grade-badge" style="background:#ef7d3c">D</span> 리팩토링 후보 ·
            <span class="grade-badge" style="background:#d24343">E</span> 심각 (변경 전 영향 분석 필요)
        </p>
    </div>
</details>'''


def _render_health_hero(scoring: ScoringResult, metrics: MetricsResult) -> str:
    """프로젝트 종합 점수(Project Health)를 큰 히어로 카드로 표시."""
    ph = scoring.project_health
    if ph is None:
        return ""
    color = GRADE_COLORS[ph.grade]
    desc = _health_description(ph)
    return f'''<div class="health-hero">
        <div class="health-circle" style="border-color:{color}">
            <div class="health-grade" style="color:{color}">{ph.grade}</div>
            <div class="health-score">{ph.score:.0f}</div>
            <div class="health-unit">/ 100</div>
        </div>
        <div class="health-info">
            <div class="health-title">Project Health</div>
            <div class="health-desc">{desc}</div>
            <div class="health-stats">
                <div><span class="hs-label">평균 G-SI</span><span class="hs-value">{ph.avg_si:.1f}</span></div>
                <div><span class="hs-label">위험(D+E) 비율</span><span class="hs-value">{ph.risk_ratio * 100:.1f}%</span></div>
                <div><span class="hs-label">순환 의존성</span><span class="hs-value">{ph.cycle_count}</span></div>
                <div><span class="hs-label">평균 결합도</span><span class="hs-value">{ph.avg_coupling:.2f}</span></div>
            </div>
        </div>
    </div>'''


def _health_description(ph) -> str:
    g = ph.grade
    if g == "A":
        return "전반적으로 깔끔하게 정리된 코드베이스입니다."
    if g == "B":
        return "일부 주의 항목이 있으나 전반적으로 양호한 코드베이스입니다."
    if g == "C":
        return "평균 수준의 코드베이스. 일부 모듈에서 결합도와 순환을 주기적으로 점검하세요."
    if g == "D":
        return "리팩토링 후보 클래스가 적지 않습니다. Hotspot Table 상위 항목부터 분리·정리를 권장합니다."
    return "위험도가 높은 코드베이스. 변경 전 영향 분석과 테스트 보강이 필요한 클래스가 다수 존재합니다."


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


def _render_hotspot_table(hotspots, top_n: int) -> str:
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

    notice = (
        f'<div class="table-notice">'
        f'<strong>이 표는 G-SI 상위 {top_n}개</strong>만 표시합니다. '
        f'전체 등급 분포는 위 도넛에서 확인하세요. '
        f'특정 등급만 보려면 오른쪽 등급 필터를 사용하면 됩니다.'
        f'</div>'
    )

    return f'''{notice}
    <div class="table-controls">
        <input type="text" id="hotspot-filter" placeholder="필터: FQN 또는 파일 경로 부분 일치">
        <select id="grade-filter">
            <option value="">전체 등급 (이 표 안에서)</option>
            <option value="E">E 등급만 (심각)</option>
            <option value="D">D 등급만 (리팩토링 후보)</option>
            <option value="C">C 등급만 (보통)</option>
            <option value="B">B 등급만 (일반)</option>
            <option value="A">A 등급만 (안전)</option>
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

    # 각 노드의 정수 인덱스를 부여 (DOM 셀렉터 단순화)
    fqn_to_idx = {fqn: i for i, fqn in enumerate(subgraph.nodes())}

    # 엣지
    edges_svg = []
    for u, v in subgraph.edges():
        x1, y1 = project(pos[u])
        x2, y2 = project(pos[v])
        edges_svg.append(
            f'<line class="edge" data-src="{fqn_to_idx[u]}" data-dst="{fqn_to_idx[v]}" '
            f'x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="#334155" stroke-width="0.8" stroke-opacity="0.6" marker-end="url(#arrow)"/>'
        )

    # 노드 + 인접 정보 (info panel용)
    node_info_payload: dict[str, dict] = {}
    nodes_svg = []
    for fqn, i in fqn_to_idx.items():
        x, y = project(pos[fqn])
        cs = si_lookup.get(fqn)
        if cs is not None:
            color = GRADE_COLORS[cs.grade]
            radius = 6 + min(14, cs.raw.get("coupling", 0) * 0.3)
            si_text = f"{cs.si:.0f}"
            label = cs.name
            payload = {
                "fqn": cs.fqn,
                "grade": cs.grade,
                "si": cs.si,
                "raw": cs.raw,
                "top_reasons": cs.top_reasons,
                "file_path": cs.file_path,
                "start_line": cs.start_line,
            }
        else:
            color = "#475569"
            radius = 4
            si_text = "?"
            label = fqn.rsplit(".", 1)[-1] if "." in fqn else fqn
            payload = {"fqn": fqn, "grade": "?", "si": None}

        # 인접 정보
        in_neighbors = list(subgraph.predecessors(fqn))
        out_neighbors = list(subgraph.successors(fqn))
        payload["fan_in"] = len(in_neighbors)
        payload["fan_out"] = len(out_neighbors)
        payload["neighbor_idxs"] = [fqn_to_idx[n] for n in in_neighbors + out_neighbors]
        payload["sample_neighbors"] = {
            "in": [n.rsplit(".", 1)[-1] for n in in_neighbors[:5]],
            "out": [n.rsplit(".", 1)[-1] for n in out_neighbors[:5]],
        }
        node_info_payload[str(i)] = payload

        nodes_svg.append(
            f'<g class="node" data-idx="{i}" data-fqn="{html.escape(fqn)}">'
            f'<title>{html.escape(fqn)} (G-SI={si_text})</title>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" '
            f'fill="{color}" stroke="#0f172a" stroke-width="1.2"/>'
            f'<text x="{x:.1f}" y="{y - radius - 3:.1f}" text-anchor="middle" '
            f'fill="#cbd5e1" font-size="10">{html.escape(label)}</text>'
            f'</g>'
        )

    info_json = json.dumps(node_info_payload, ensure_ascii=False)

    return f'''<div class="graph-meta">
        표시 노드 {subgraph.number_of_nodes()} · 엣지 {subgraph.number_of_edges()} ·
        (G-SI 상위 {top_n}개 hotspot + 1-홉 이웃) ·
        <em>마우스를 노드에 올리면 우측에 상세 정보가 나타납니다.</em>
    </div>
    <div class="graph-wrap">
        <svg viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" class="depgraph" id="depgraph">
            <defs>
                <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                    <path d="M0,0 L8,4 L0,8 z" fill="#64748b"/>
                </marker>
            </defs>
            <g class="edges">{''.join(edges_svg)}</g>
            <g class="nodes">{''.join(nodes_svg)}</g>
        </svg>
        <aside class="graph-info" id="graph-info">
            <div class="info-empty">노드 위에 마우스를 올리면<br>여기에 상세 정보가 나타납니다.</div>
        </aside>
    </div>
    <script id="graph-node-info" type="application/json">{info_json}</script>'''


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
  .graph-meta em {{ color: var(--accent); font-style: normal; }}
  .graph-wrap {{ display: grid; grid-template-columns: 1fr 280px; gap: 12px; align-items: stretch; }}
  .depgraph {{ display: block; background: #0b1322; border-radius: 6px; width: 100%; height: 620px; }}
  .depgraph .node {{ cursor: pointer; transition: opacity 0.15s; }}
  .depgraph .node text {{ pointer-events: none; opacity: 0.7; }}
  .depgraph .node:hover circle {{ stroke: var(--accent); stroke-width: 3; }}
  .depgraph .node:hover text {{ opacity: 1; font-weight: 600; font-size: 12px; }}
  .depgraph.has-hover .node:not(.hl):not(.hl-neighbor) {{ opacity: 0.18; }}
  .depgraph.has-hover .edge:not(.hl-edge) {{ stroke-opacity: 0.08; }}
  .depgraph .edge.hl-edge {{ stroke: var(--accent); stroke-width: 1.6; stroke-opacity: 1; }}
  .graph-info {{ background: #0b1322; border-radius: 6px; padding: 14px; min-height: 620px;
                 font-size: 13px; overflow-y: auto; }}
  .graph-info .info-empty {{ color: var(--muted); text-align: center; padding-top: 60px; line-height: 1.6; }}
  .graph-info .info-fqn {{ font-family: ui-monospace, monospace; font-size: 12px;
                            word-break: break-all; color: #e2e8f0; margin-bottom: 8px; }}
  .graph-info .info-grade {{ display: inline-block; padding: 4px 12px; border-radius: 999px;
                              color: #fff; font-weight: 700; font-size: 13px; }}
  .graph-info .info-si {{ font-size: 28px; font-weight: 700; margin-left: 8px; }}
  .graph-info dl {{ display: grid; grid-template-columns: max-content 1fr; gap: 4px 12px;
                    margin: 12px 0; font-size: 12px; }}
  .graph-info dt {{ color: var(--muted); }}
  .graph-info dd {{ margin: 0; text-align: right; font-variant-numeric: tabular-nums; }}
  .graph-info .info-section {{ margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border); }}
  .graph-info .info-section h4 {{ font-size: 11px; color: var(--muted); margin: 0 0 4px 0;
                                    text-transform: uppercase; letter-spacing: 0.04em; }}
  .graph-info code.neighbor {{ display: inline-block; background: rgba(255,255,255,0.06);
                                padding: 1px 6px; border-radius: 4px; font-size: 11px;
                                margin: 2px 4px 2px 0; }}

  /* Project Health hero card */
  .health-hero {{ display: flex; gap: 24px; align-items: center; background: var(--panel);
                  padding: 24px; border-radius: 10px; border: 1px solid var(--border); }}
  .health-circle {{ width: 140px; height: 140px; border-radius: 50%; border: 6px solid;
                    display: flex; flex-direction: column; align-items: center; justify-content: center;
                    flex-shrink: 0; background: var(--panel2); }}
  .health-grade {{ font-size: 36px; font-weight: 800; line-height: 1; }}
  .health-score {{ font-size: 28px; font-weight: 600; margin-top: 4px; color: var(--fg); }}
  .health-unit {{ color: var(--muted); font-size: 12px; }}
  .health-info {{ flex: 1; }}
  .health-title {{ font-size: 13px; color: var(--muted); text-transform: uppercase;
                   letter-spacing: 0.05em; margin-bottom: 4px; }}
  .health-desc {{ font-size: 15px; margin-bottom: 14px; line-height: 1.5; }}
  .health-stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }}
  .health-stats > div {{ background: var(--panel2); padding: 10px 12px; border-radius: 6px;
                          display: flex; flex-direction: column; }}
  .hs-label {{ color: var(--muted); font-size: 12px; }}
  .hs-value {{ font-size: 18px; font-weight: 600; margin-top: 2px; }}

  /* Help box */
  .help {{ background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
           padding: 12px 16px; margin-bottom: 24px; }}
  .help > summary {{ cursor: pointer; color: var(--accent); font-weight: 600; user-select: none; }}
  .help-body {{ margin-top: 12px; font-size: 13px; line-height: 1.6; color: #cbd5e1; }}
  .help-body ul {{ padding-left: 22px; }}
  .help-body li {{ margin-bottom: 6px; }}
  .help-body .help-grade {{ margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border); font-size: 12px; }}
  .help-body .help-grade .grade-badge {{ margin: 0 4px; }}

  /* Hotspot notice */
  .table-notice {{ background: rgba(96, 165, 250, 0.07); border: 1px solid rgba(96, 165, 250, 0.25);
                   border-radius: 6px; padding: 10px 14px; margin-bottom: 12px; font-size: 13px;
                   color: #cbd5e1; }}
  .table-notice strong {{ color: var(--accent); }}
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

{help_box}

<section>
  <h2>Project Health</h2>
  {health_hero}
</section>

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

  // ----- Dependency Graph 인터랙션 -----
  const graphSvg = document.getElementById('depgraph');
  const graphInfo = document.getElementById('graph-info');
  const nodeInfoScript = document.getElementById('graph-node-info');
  const GRADE_COLORS = {{ A: '#3b8e5a', B: '#7fb95a', C: '#e3b341', D: '#ef7d3c', E: '#d24343' }};
  if (graphSvg && graphInfo && nodeInfoScript) {{
    const nodeInfo = JSON.parse(nodeInfoScript.textContent);
    const allNodes = graphSvg.querySelectorAll('.node');
    const allEdges = graphSvg.querySelectorAll('.edge');

    function clearHl() {{
      graphSvg.classList.remove('has-hover');
      allNodes.forEach(n => n.classList.remove('hl', 'hl-neighbor'));
      allEdges.forEach(e => e.classList.remove('hl-edge'));
    }}

    function renderInfo(idx) {{
      const info = nodeInfo[idx];
      if (!info) return;
      const color = GRADE_COLORS[info.grade] || '#475569';
      const reasons = (info.top_reasons && info.top_reasons.length)
        ? info.top_reasons.join(', ') : '—';
      const raw = info.raw || {{}};
      const inList = (info.sample_neighbors && info.sample_neighbors.in.length)
        ? info.sample_neighbors.in.map(n => `<code class="neighbor">${{n}}</code>`).join('')
        : '<span style="color: var(--muted); font-size: 11px;">없음</span>';
      const outList = (info.sample_neighbors && info.sample_neighbors.out.length)
        ? info.sample_neighbors.out.map(n => `<code class="neighbor">${{n}}</code>`).join('')
        : '<span style="color: var(--muted); font-size: 11px;">없음</span>';
      graphInfo.innerHTML = `
        <div class="info-fqn">${{info.fqn}}</div>
        <div>
          <span class="info-grade" style="background:${{color}}">${{info.grade}}</span>
          <span class="info-si">${{info.si !== null ? info.si.toFixed(0) : '?'}}</span>
          <span style="color: var(--muted); font-size: 13px;">/ 100</span>
        </div>
        <dl>
          <dt>Cyclomatic Complexity</dt><dd>${{(raw.cc || 0).toFixed(1)}}</dd>
          <dt>Coupling</dt><dd>${{Math.round(raw.coupling || 0)}}</dd>
          <dt>Global State</dt><dd>${{Math.round(raw.global_state || 0)}}</dd>
          <dt>Cycle Size</dt><dd>${{Math.round(raw.dependency_cycle || 0)}}</dd>
          <dt>Game Loop Centrality</dt><dd>${{(raw.game_loop_centrality || 0).toFixed(2)}}</dd>
          <dt>Fan-in / Fan-out</dt><dd>${{info.fan_in || 0}} / ${{info.fan_out || 0}}</dd>
        </dl>
        <div class="info-section">
          <h4>주요 위험 원인</h4>
          <div style="font-size: 12px;">${{reasons}}</div>
        </div>
        <div class="info-section">
          <h4>이 클래스를 참조하는 클래스 (샘플)</h4>
          <div>${{inList}}</div>
        </div>
        <div class="info-section">
          <h4>이 클래스가 참조하는 클래스 (샘플)</h4>
          <div>${{outList}}</div>
        </div>
      `;
    }}

    function highlight(node) {{
      clearHl();
      graphSvg.classList.add('has-hover');
      node.classList.add('hl');
      const idx = node.getAttribute('data-idx');
      const info = nodeInfo[idx];
      const neighborIdxs = new Set((info && info.neighbor_idxs) || []);
      allNodes.forEach(n => {{
        const ni = n.getAttribute('data-idx');
        if (neighborIdxs.has(parseInt(ni, 10))) n.classList.add('hl-neighbor');
      }});
      allEdges.forEach(e => {{
        const src = parseInt(e.getAttribute('data-src'), 10);
        const dst = parseInt(e.getAttribute('data-dst'), 10);
        if (src === parseInt(idx, 10) || dst === parseInt(idx, 10)) {{
          e.classList.add('hl-edge');
        }}
      }});
      renderInfo(idx);
    }}

    allNodes.forEach(node => {{
      node.addEventListener('mouseenter', () => highlight(node));
    }});
    graphSvg.addEventListener('mouseleave', () => {{
      clearHl();
      graphInfo.innerHTML = '<div class="info-empty">노드 위에 마우스를 올리면<br>여기에 상세 정보가 나타납니다.</div>';
    }});
  }}
}})();
</script>
</body>
</html>
"""
