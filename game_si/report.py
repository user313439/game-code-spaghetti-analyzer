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

    # 임베드용 데이터 — JS가 Hotspot Table 동적 렌더링, 그래프 검색 등에 사용한다.
    embedded = {
        "project": project_name,
        "analyzed_at": analyzed_at,
        "hotspot_top_n": top_n,
        "grade_colors": GRADE_COLORS,
        "all_classes": json.loads(_hotspot_data_payload(scoring)),
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
    return '''<details class="help" open>
    <summary>이 대시보드 읽는 법 (펼치기 / 접기)</summary>
    <div class="help-body">
        <p><strong>Game Spaghetti Index (G-SI)</strong>는 게임 코드의 각 클래스가
        얼마나 다른 코드와 얽혀 있는지를 0~100점으로 측정한 지표입니다.
        <strong>점수가 높을수록 위험</strong>합니다.</p>
        <ul>
            <li><strong>Project Health</strong> — 프로젝트 전체의 종합 점수 하나.
                평균 G-SI, 위험 클래스 비율, 순환 의존성 수, 평균 결합도 4가지를 합쳐
                "이 프로젝트의 스파게티 정도"를 한 숫자로 답합니다.</li>
            <li><strong>Summary 카드</strong> — 분석 규모 요약(클래스/메서드/순환 수, 평균·최대·위험 클래스 수).</li>
            <li><strong>등급 분포 도넛</strong> — 프로젝트 안의 모든 클래스를
                A(안전) ~ E(심각)로 나눠 보여줍니다. 비율 자체는 percentile rank 정의상 거의 균등(A~E 각 20%)에 가깝습니다.</li>
            <li><strong>Hotspot Table</strong> — <em>가장 위험한 클래스 상위 N개</em>만
                골라 보여줍니다. 등급 필터를 선택하면 <strong>그 등급 안에서 다시 상위 N개</strong>를 보여주도록
                표가 재계산됩니다.</li>
            <li><strong>Dependency Graph</strong> — 위험 클래스와 그 이웃들이 어떻게
                연결되어 있는지 시각화. 위의 검색창에 이름을 치거나 등급을 선택하면 매칭 노드가
                강조되고, 마우스를 노드 위에 올리면 우측 패널에 상세 정보가 표시됩니다.</li>
            <li><strong>Cycle Explorer</strong> — <code>A → B → C → A</code> 처럼 서로 참조해서 빙빙 도는
                클래스 묶음을 보여줍니다. 한 곳만 고쳐도 다른 곳이 영향받기 쉬워 위험한 패턴입니다.</li>
            <li><strong>Module Summary</strong> — 클래스 단위 점수를 <strong>최상위 폴더 단위로 집계</strong>한 표.
                "이 폴더(모듈) 안 클래스들이 평균적으로 얼마나 위험한가"를 봅니다.</li>
        </ul>
        <p class="help-grade">
            등급 의미 →
            <span class="grade-badge" style="background:#3b8e5a">A</span> 안전 ·
            <span class="grade-badge" style="background:#7fb95a">B</span> 일반 ·
            <span class="grade-badge" style="background:#e3b341">C</span> 보통 ·
            <span class="grade-badge" style="background:#ef7d3c">D</span> 리팩토링 후보 ·
            <span class="grade-badge" style="background:#d24343">E</span> 심각 (변경 전 영향 분석 필요)
        </p>
        <p class="help-tip">💡 화면 곳곳의 항목에 <strong>마우스를 잠시 올려두면</strong> 그 항목이 무엇인지 설명이 표시됩니다.</p>
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
                <div data-tooltip="프로젝트 내 모든 클래스의 G-SI 점수 평균. 종합 점수에 45% 기여">
                    <span class="hs-label">평균 G-SI</span><span class="hs-value">{ph.avg_si:.1f}</span></div>
                <div data-tooltip="G-SI 60 이상(D·E 등급)인 클래스의 비율. 종합 점수에 25% 기여">
                    <span class="hs-label">위험(D+E) 비율</span><span class="hs-value">{ph.risk_ratio * 100:.1f}%</span></div>
                <div data-tooltip="순환 참조에 빠진 클래스 묶음의 수(크기 ≥ 2). 종합 점수에 15% 기여">
                    <span class="hs-label">순환 의존성</span><span class="hs-value">{ph.cycle_count}</span></div>
                <div data-tooltip="클래스 한 개당 평균적으로 몇 개의 다른 클래스와 연결되는지(fan-in + fan-out 평균). 종합 점수에 15% 기여">
                    <span class="hs-label">평균 결합도</span><span class="hs-value">{ph.avg_coupling:.2f}</span></div>
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
        ("분석 클래스", f"{scoring.total_classes:,}",
         "Roslyn으로 파싱한 클래스 · 구조체 · 인터페이스 · 레코드의 합계"),
        ("분석 메서드", f"{scoring.total_methods:,}",
         "분석된 모든 메서드와 생성자의 합계"),
        ("의존성 순환(SCC ≥ 2)", f"{len(metrics.sccs):,}",
         "A→B→C→A처럼 서로 참조해서 빙빙 도는 클래스 묶음의 개수. 적을수록 좋음"),
        ("평균 G-SI", f"{avg_si:.1f}",
         "모든 클래스의 G-SI 점수 평균. 0~100, 낮을수록 깔끔한 코드베이스"),
        ("최대 G-SI", f"{max_si:.1f}",
         "이 프로젝트에서 가장 위험한 한 클래스의 G-SI 점수"),
        ("위험(D/E) 클래스", f"{risk_count:,}",
         "G-SI가 60 이상인 클래스 수. 변경 시 주의가 필요한 클래스"),
    ]
    return "".join(
        f'<div class="card" data-tooltip="{html.escape(tip)}">'
        f'<div class="card-label">{html.escape(label)}</div>'
        f'<div class="card-value">{html.escape(value)}</div></div>'
        for label, value, tip in cards
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
    tooltips = {
        "cc": "Cyclomatic Complexity — 메서드 안의 if/for/case 등 분기 수",
        "coupling": "Coupling — 다른 클래스와 얼마나 연결되어 있는지 (fan-in + fan-out)",
        "dependency_cycle": "DependencyCycle — 순환 참조에 빠졌는지, 묶음의 크기는 얼마인지",
        "global_state": "GlobalState — 전역/static 변수와 싱글톤 인스턴스에 얼마나 의존하는지",
        "game_loop_centrality": "GameLoopCentrality — Tick/Update/Render 등 게임 루프 진입점에서 얼마나 가까운지",
    }
    rows = "".join(
        f'<tr><td data-tooltip="{html.escape(tooltips.get(k, ""))}">{html.escape(k)}</td>'
        f'<td class="num">{v:.3f}</td></tr>'
        for k, v in weights.items()
    )
    return f'''<table class="kv-table">
        <thead><tr><th>항목</th><th class="num">가중치</th></tr></thead>
        <tbody>{rows}</tbody>
    </table>'''


def _render_hotspot_table(hotspots, top_n: int) -> str:
    """표 골격만 렌더링. 본문은 클라이언트 측에서 등급 필터에 따라 동적으로 그린다."""
    notice = (
        f'<div class="table-notice">'
        f'기본은 전체 클래스 중 <strong>G-SI 상위 {top_n}개</strong>를 표시합니다. '
        f'특정 등급(A~E)을 선택하면 <strong>그 등급 안에서</strong> 상위 {top_n}개를 다시 보여줍니다. '
        f'전체 등급 분포는 위 도넛 차트에서 확인하세요.'
        f'</div>'
    )

    def th(label: str, sort: str | None = None, tip: str | None = None, num: bool = False) -> str:
        parts = ['<th']
        classes: list[str] = []
        if sort:
            classes.append("sortable")
            parts.append(' data-sort="' + sort + '"')
        if num:
            classes.append("num")
        if classes:
            parts.append(' class="' + " ".join(classes) + '"')
        if tip:
            parts.append(' data-tooltip="' + html.escape(tip) + '"')
        parts.append('>')
        parts.append(label)
        parts.append('</th>')
        return ''.join(parts)

    return f'''{notice}
    <div class="table-controls">
        <input type="text" id="hotspot-filter" placeholder="텍스트 검색: FQN 또는 파일 경로 부분 일치">
        <select id="grade-filter">
            <option value="">전체 등급에서 상위 {top_n}</option>
            <option value="E">E 등급만 (심각)</option>
            <option value="D">D 등급만 (리팩토링 후보)</option>
            <option value="C">C 등급만 (보통)</option>
            <option value="B">B 등급만 (일반)</option>
            <option value="A">A 등급만 (안전)</option>
        </select>
        <span id="hotspot-count" class="hotspot-count"></span>
    </div>
    <table class="hotspot-table" id="hotspot-table">
        <thead><tr>
            <th class="num" data-tooltip="G-SI 점수 기준 등수">#</th>
            <th data-tooltip="A(안전, 하위 20%) ~ E(심각, 상위 20%)">등급</th>
            {th("G-SI", sort="num", num=True, tip="0~100. 프로젝트 내 분포 백분위. 높을수록 위험")}
            {th("클래스 FQN", sort="str", tip="네임스페이스를 포함한 정규 이름")}
            {th("CC", sort="num", num=True, tip="Cyclomatic Complexity. 메서드 안의 if/for/case 등 분기 수. 클래스 단위는 상위 10% 평균")}
            {th("Coupling", sort="num", num=True, tip="다른 클래스를 참조하는 수(fan-out) + 참조받는 수(fan-in)")}
            {th("GlobalState", sort="num", num=True, tip="전역(static) 변수와 싱글톤 인스턴스에 접근한 횟수")}
            {th("CycleSize", sort="num", num=True, tip="순환 참조에 빠진 묶음의 크기. 0이면 순환에 포함되지 않음")}
            {th("GameLoop", sort="num", num=True, tip="Tick/Update/Render 같은 진입점으로부터의 가까움. 1.0이면 진입점 그 자체")}
            <th data-tooltip="이 클래스가 위험으로 분류된 가장 큰 두 항목">주요 원인</th>
            <th data-tooltip="파일 경로 : 시작 라인">위치</th>
        </tr></thead>
        <tbody id="hotspot-tbody"></tbody>
    </table>'''


def _hotspot_data_payload(scoring) -> str:
    """모든 클래스 점수를 JS가 다룰 수 있는 가벼운 dict 배열로 직렬화."""
    payload = []
    for cs in scoring.class_scores:
        payload.append({
            "fqn": cs.fqn,
            "file_path": cs.file_path,
            "start_line": cs.start_line,
            "grade": cs.grade,
            "si": round(cs.si, 1),
            "cc": round(cs.raw.get("cc", 0), 1),
            "coupling": int(cs.raw.get("coupling", 0)),
            "global_state": int(cs.raw.get("global_state", 0)),
            "dependency_cycle": int(cs.raw.get("dependency_cycle", 0)),
            "game_loop_centrality": round(cs.raw.get("game_loop_centrality", 0), 2),
            "top_reasons": cs.top_reasons,
        })
    return json.dumps(payload, ensure_ascii=False)


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

    # 상위 hotspot 중심으로 부분 그래프 추출.
    #
    # 큰 코드베이스(예: OpenRA.Mods.Common)에서는 top_n + 1-홉 이웃이 수백 개로 폭발해
    # 화면이 점들로 덮여 인터랙션이 어렵다. 보기 좋은 범위로 노드 수를 제한한다.
    MAX_NODES = 150
    hotspot_fqns = [cs.fqn for cs in sorted(scoring.class_scores, key=lambda c: -c.si)[:top_n]]
    seed = [fqn for fqn in hotspot_fqns if fqn in g]
    expanded: list[str] = list(seed)  # 순서 보존을 위해 list 사용
    seen = set(seed)

    # seed 각각의 1-홉 이웃을 G-SI 점수가 높은 순서로 우선 채운다.
    si_rank = {cs.fqn: i for i, cs in enumerate(sorted(scoring.class_scores, key=lambda c: -c.si))}
    neighbor_candidates: list[str] = []
    for fqn in seed:
        for nb in list(g.predecessors(fqn)) + list(g.successors(fqn)):
            if nb not in seen:
                neighbor_candidates.append(nb)
                seen.add(nb)
    neighbor_candidates.sort(key=lambda n: si_rank.get(n, 10**9))
    for nb in neighbor_candidates:
        if len(expanded) >= MAX_NODES:
            break
        expanded.append(nb)

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

    width, height, margin = 1400, 720, 50
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
    <div class="graph-controls">
        <input type="text" id="graph-search" placeholder="그래프 안 클래스 검색 (이름의 일부 입력)">
        <div class="grade-toggle" id="graph-grade-toggle">
            <span class="gt-label">등급 강조:</span>
            <button data-grade="" class="gt-btn gt-active">전체</button>
            <button data-grade="A" class="gt-btn">A</button>
            <button data-grade="B" class="gt-btn">B</button>
            <button data-grade="C" class="gt-btn">C</button>
            <button data-grade="D" class="gt-btn">D</button>
            <button data-grade="E" class="gt-btn">E</button>
        </div>
        <span class="graph-match-count" id="graph-match-count"></span>
        <div class="graph-zoom" id="graph-zoom">
            <button id="zoom-in" data-tooltip="확대 (또는 마우스 휠 위)">＋</button>
            <button id="zoom-out" data-tooltip="축소 (또는 마우스 휠 아래)">−</button>
            <button id="zoom-reset" data-tooltip="원래 크기로 복귀">리셋</button>
        </div>
    </div>
    <div class="graph-tip">💡 <strong>그래프 사용법</strong> — 마우스 휠로 확대/축소, 드래그로 이동, 노드 위에 마우스를 올리면 우측에 상세 정보가 표시됩니다.</div>
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
            <div class="info-empty">노드 위에 마우스를 올리면<br>여기에 상세 정보가 나타납니다.<br><br>
            아래 검색창에 클래스 이름을 입력하거나 등급 버튼을 누르면<br>해당 노드가 강조됩니다.</div>
        </aside>
    </div>
    <script id="graph-node-info" type="application/json">{info_json}</script>'''


def _render_cycle_explorer(metrics: MetricsResult, si_lookup: dict) -> str:
    """크기 ≥ 2 인 SCC 목록을 표시한다. 각 cycle의 멤버 클래스와 평균 G-SI를 보여준다."""
    # 섹션 상단의 ⓘ 토글이 설명을 대체하므로 내부 intro는 비워둔다.
    intro = ""

    total = len(metrics.sccs)
    if total == 0:
        count_card = (
            '<div class="cycle-count cycle-count-zero" '
            'data-tooltip="크기가 2 이상인 순환 의존성이 하나도 발견되지 않았습니다. 좋은 신호입니다.">'
            '<div class="cc-number">0</div>'
            '<div class="cc-label">발견된 순환 묶음 (전체)</div>'
            '<div class="cc-hint">✅ 좋은 신호 — 클래스들이 한 방향으로 흐름</div>'
            '</div>'
        )
        return intro + count_card

    # 카운트 카드 — 이 숫자가 "전체"임을 명확히
    sccs_sorted = sorted(metrics.sccs, key=len, reverse=True)
    largest = len(sccs_sorted[0])
    count_card = (
        f'<div class="cycle-count" '
        f'data-tooltip="이 프로젝트 전체에서 발견된 순환 의존성 묶음의 수입니다. 상위 N개가 아니라 전부 표시됩니다.">'
        f'<div class="cc-number">{total}</div>'
        f'<div class="cc-label">발견된 순환 묶음 (전체)</div>'
        f'<div class="cc-hint">가장 큰 묶음의 크기: <strong>{largest}개 클래스</strong></div>'
        f'</div>'
    )

    rows = [intro, count_card]
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
        tip = (
            f"이 묶음 안의 {len(scc)}개 클래스는 서로 참조 사슬을 이루고 있어 "
            f"한 클래스를 수정하면 나머지에도 영향이 갈 수 있습니다."
        )
        rows.append(
            f'<details class="cycle-entry" data-tooltip="{html.escape(tip)}"><summary>'
            f'<span class="cycle-rank">#{idx}</span>'
            f'<span class="grade-badge" style="background:{GRADE_COLORS[grade]}">{grade}</span>'
            f'<span class="cycle-stat">크기 <strong>{len(scc)}</strong></span>'
            f'<span class="cycle-stat">평균 G-SI <strong>{avg_si:.1f}</strong></span>'
            f'<span class="cycle-stat">최대 <strong>{max_si:.1f}</strong></span>'
            f'</summary><ul>{member_html}</ul>{more}</details>'
        )
    return f'{rows[0]}{rows[1]}<div class="cycle-list">{"".join(rows[2:])}</div>'


def _grade(score: float) -> str:
    """등급 분류 — `_render_grade_donut`과 분리되어 있어 별도 함수로 둔다."""
    if score < 20: return "A"
    if score < 40: return "B"
    if score < 60: return "C"
    if score < 80: return "D"
    return "E"


def _render_module_table(modules) -> str:
    # 섹션 상단의 ⓘ 토글이 설명을 대체하므로 내부 intro는 더 이상 그리지 않는다.
    intro = ""
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
    return f'''{intro}
    <table class="module-table">
        <thead><tr>
            <th data-tooltip="분석 입력 폴더 바로 아래의 1단계 폴더 이름. (root)는 폴더에 들어있지 않고 분석 폴더 바로 아래에 놓인 .cs 파일들">모듈</th>
            <th data-tooltip="모듈 내 클래스 평균을 기준으로 한 등급">등급</th>
            <th class="num" data-tooltip="모듈 내 모든 클래스의 G-SI 평균">평균 G-SI</th>
            <th class="num" data-tooltip="모듈에서 가장 위험한 클래스 하나의 G-SI">최대 G-SI</th>
            <th class="num" data-tooltip="모듈에 속한 .cs 파일 수">파일 수</th>
            <th class="num" data-tooltip="모듈에 속한 클래스 · 구조체 · 인터페이스 · 레코드의 합">클래스 수</th>
        </tr></thead>
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
  section h2 {{ font-size: 17px; margin: 0; color: #cbd5e1; }}
  .sec-head {{ display: flex; gap: 12px; align-items: baseline; margin-bottom: 12px;
               padding-bottom: 6px; border-bottom: 1px solid var(--border); }}
  .sec-info {{ background: transparent; color: var(--accent); border: 1px solid var(--border);
               padding: 2px 10px; border-radius: 999px; font-size: 11px; cursor: pointer;
               white-space: nowrap; transition: all 0.1s; }}
  .sec-info:hover {{ background: rgba(96,165,250,0.1); border-color: var(--accent); }}
  .sec-info[aria-expanded="true"] {{ background: var(--accent); color: #0b1322; border-color: var(--accent); }}
  .sec-explain {{ background: rgba(96,165,250,0.06); border-left: 3px solid var(--accent);
                  padding: 14px 18px; margin-bottom: 12px; font-size: 13px; line-height: 1.7;
                  color: #cbd5e1; border-radius: 0 6px 6px 0; }}
  .sec-explain strong {{ color: #e5e7eb; }}
  .sec-explain em {{ color: var(--accent); font-style: normal; }}
  .sec-explain code {{ background: rgba(255,255,255,0.08); padding: 1px 6px;
                        border-radius: 3px; font-size: 12px; }}
  .sec-explain p {{ margin: 0 0 10px 0; }}
  .sec-explain p:last-child {{ margin-bottom: 0; }}
  .sec-explain ul {{ margin: 6px 0 10px 0; padding-left: 22px; }}
  .sec-explain li {{ margin-bottom: 4px; }}
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
  th.num, td.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
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

  /* Hotspot notice / count */
  .table-notice {{ background: rgba(96, 165, 250, 0.07); border: 1px solid rgba(96, 165, 250, 0.25);
                   border-radius: 6px; padding: 10px 14px; margin-bottom: 12px; font-size: 13px;
                   color: #cbd5e1; }}
  .table-notice strong {{ color: var(--accent); }}
  .hotspot-count {{ color: var(--muted); font-size: 12px; align-self: center; }}

  /* 섹션 소개 문구 */
  .section-intro {{ background: rgba(96, 165, 250, 0.05); border-left: 3px solid var(--accent);
                    padding: 10px 14px; margin-bottom: 12px; font-size: 13px; color: #cbd5e1;
                    border-radius: 0 6px 6px 0; }}
  .section-intro strong {{ color: #e5e7eb; }}
  .section-intro code {{ background: rgba(255,255,255,0.08); padding: 1px 6px;
                          border-radius: 3px; font-size: 12px; }}

  /* Custom tooltip — [data-tooltip] 속성이 있는 요소 hover 시 표시 */
  [data-tooltip] {{ position: relative; cursor: help; }}
  [data-tooltip]::after {{
    content: attr(data-tooltip);
    position: absolute; left: 50%; bottom: calc(100% + 6px);
    transform: translateX(-50%);
    background: #020617; color: #f1f5f9; padding: 8px 10px; border-radius: 6px;
    font-size: 12px; line-height: 1.4; font-weight: 400;
    white-space: normal; width: max-content; max-width: 260px;
    text-align: left; pointer-events: none; opacity: 0;
    transition: opacity 0.12s; z-index: 100;
    border: 1px solid #334155;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  }}
  [data-tooltip]:hover::after {{ opacity: 1; }}
  th[data-tooltip] {{ cursor: help; }}

  /* Graph controls — 검색 + 등급 토글 */
  .graph-controls {{ display: flex; gap: 12px; align-items: center; margin-bottom: 10px;
                     flex-wrap: wrap; }}
  .graph-controls input {{
    background: var(--panel2); color: var(--fg); border: 1px solid var(--border);
    padding: 6px 10px; border-radius: 6px; font-size: 13px; flex: 1; min-width: 280px;
  }}
  .grade-toggle {{ display: flex; gap: 4px; align-items: center; }}
  .gt-label {{ color: var(--muted); font-size: 12px; margin-right: 4px; }}
  .gt-btn {{ background: var(--panel2); color: var(--muted); border: 1px solid var(--border);
             padding: 4px 12px; border-radius: 6px; font-size: 12px; font-weight: 600;
             cursor: pointer; transition: all 0.1s; }}
  .gt-btn:hover {{ color: var(--fg); border-color: #475569; }}
  .gt-btn.gt-active {{ color: #fff; }}
  .gt-btn[data-grade="A"].gt-active {{ background: #3b8e5a; border-color: #3b8e5a; }}
  .gt-btn[data-grade="B"].gt-active {{ background: #7fb95a; border-color: #7fb95a; }}
  .gt-btn[data-grade="C"].gt-active {{ background: #e3b341; border-color: #e3b341; color: #111; }}
  .gt-btn[data-grade="D"].gt-active {{ background: #ef7d3c; border-color: #ef7d3c; }}
  .gt-btn[data-grade="E"].gt-active {{ background: #d24343; border-color: #d24343; }}
  .gt-btn[data-grade=""].gt-active {{ background: var(--accent); border-color: var(--accent); }}
  .graph-match-count {{ color: var(--muted); font-size: 12px; }}
  .graph-zoom {{ display: flex; gap: 4px; }}
  .graph-zoom button {{ background: var(--panel2); color: var(--fg); border: 1px solid var(--border);
                         padding: 4px 12px; border-radius: 6px; font-size: 13px; cursor: pointer;
                         font-weight: 600; min-width: 38px; }}
  .graph-zoom button:hover {{ background: #1f2a3a; border-color: var(--accent); }}
  .graph-tip {{ background: rgba(96,165,250,0.06); border-radius: 4px;
                padding: 8px 12px; margin-bottom: 10px; font-size: 12px; color: #cbd5e1; }}
  .graph-tip strong {{ color: var(--accent); }}
  .depgraph {{ cursor: grab; }}
  .depgraph.dragging {{ cursor: grabbing; }}

  /* 검색 매치 강조 */
  .depgraph .node.search-match circle {{
    stroke: #fff; stroke-width: 2.5;
    filter: drop-shadow(0 0 6px rgba(96, 165, 250, 0.9));
  }}
  .depgraph .node.search-match text {{ opacity: 1; font-weight: 700; font-size: 11px; fill: #fff; }}
  .depgraph.has-search .node:not(.search-match):not(.hl):not(.hl-neighbor) {{ opacity: 0.25; }}

  .help-body .help-tip {{ margin-top: 10px; padding: 8px 12px; background: rgba(96,165,250,0.06);
                           border-radius: 4px; font-size: 12px; }}
  .cycle-count {{ background: var(--panel2); border-radius: 8px; padding: 16px 20px;
                  display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px;
                  border-left: 4px solid #d24343; max-width: 480px; }}
  .cycle-count-zero {{ border-left-color: #3b8e5a; }}
  .cc-number {{ font-size: 36px; font-weight: 800; line-height: 1; color: #f1f5f9;
                font-variant-numeric: tabular-nums; }}
  .cc-label {{ color: var(--muted); font-size: 13px; }}
  .cc-hint {{ color: #cbd5e1; font-size: 12px; margin-top: 4px; }}
  .cycle-list details {{ background: var(--panel2); padding: 10px 12px; border-radius: 6px; margin-bottom: 6px; }}
  .cycle-list summary {{ cursor: pointer; display: flex; gap: 12px; align-items: center; }}
  .cycle-stat {{ color: #cbd5e1; font-size: 13px; }}
  .cycle-stat strong {{ color: #f1f5f9; font-variant-numeric: tabular-nums; }}
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
  <div class="sec-head">
    <h2>Project Health</h2>
    <button class="sec-info" data-target="help-health" aria-expanded="false">ⓘ 이 섹션이 뭔가요?</button>
  </div>
  <div class="sec-explain" id="help-health" hidden>
    <p><strong>이 프로젝트의 스파게티 정도를 한 숫자로 답하는 종합 점수</strong>입니다. 0~100 점, 점수가 높을수록 코드가 전반적으로 엉켜 있다는 뜻입니다.</p>
    <p>다음 네 가지 신호를 가중 평균합니다.</p>
    <ul>
      <li><strong>평균 G-SI (45%)</strong> — 프로젝트 안 모든 클래스의 G-SI 점수를 단순 평균. 가장 큰 비중.</li>
      <li><strong>위험(D+E) 비율 (25%)</strong> — G-SI 60 이상(=D 등급 이상)인 클래스가 전체에서 차지하는 비율을 0~100 점으로 환산.</li>
      <li><strong>순환 의존성 수 (15%)</strong> — A→B→C→A 처럼 서로 참조해서 빙빙 도는 묶음의 개수. 로그 스케일 적용(0 → 0점, 1 → 30점, 5 → 70점, 20 이상 → 100점).</li>
      <li><strong>평균 결합도 (15%)</strong> — 클래스 한 개당 평균적으로 몇 개의 다른 클래스와 연결되는지(fan-in+fan-out 평균). 평균 10 이상이면 100점으로 saturate.</li>
    </ul>
    <p>등급 기준은 다른 점수와 동일하게 A(0~19) · B(20~39) · C(40~59) · D(60~79) · E(80~100) 입니다. 발표 슬라이드에 "이 프로젝트는 C 등급(47점) — 평균 수준의 코드베이스" 같은 한 줄 요약으로 쓰기 좋은 숫자입니다.</p>
  </div>
  {health_hero}
</section>

<section>
  <div class="sec-head">
    <h2>Summary</h2>
    <button class="sec-info" data-target="help-summary" aria-expanded="false">ⓘ 이 섹션이 뭔가요?</button>
  </div>
  <div class="sec-explain" id="help-summary" hidden>
    <p>분석 규모와 위험 신호를 6개 숫자로 압축한 카드 묶음입니다.</p>
    <ul>
      <li><strong>분석 클래스</strong> — Roslyn으로 파싱한 class · struct · interface · record · enum의 총 개수.</li>
      <li><strong>분석 메서드</strong> — 분석된 모든 메서드와 생성자(.ctor)의 합. enum 항목, 자동 속성은 카운트하지 않습니다.</li>
      <li><strong>의존성 순환(SCC ≥ 2)</strong> — 크기가 2 이상인 강한 연결 요소(Strongly Connected Component). 적을수록 좋고, 0이면 의존성이 한 방향으로 흐른다는 좋은 신호입니다.</li>
      <li><strong>평균 G-SI</strong> — 클래스 단위 G-SI 점수의 단순 평균. Project Health의 가장 큰 입력입니다.</li>
      <li><strong>최대 G-SI</strong> — 이 프로젝트에서 가장 위험한 한 클래스의 G-SI. 보통 95~100점이 나옵니다 (percentile rank 특성상).</li>
      <li><strong>위험(D/E) 클래스</strong> — G-SI 60 이상인 클래스의 수. 변경할 때 영향 분석과 테스트 보강이 필요한 클래스들입니다.</li>
    </ul>
    <p>각 카드에 마우스를 올리면 동일한 설명이 풍선으로 표시됩니다.</p>
  </div>
  <div class="card-row">{summary_cards}</div>
</section>

<section>
  <div class="sec-head">
    <h2>등급 분포 및 가중치</h2>
    <button class="sec-info" data-target="help-dist" aria-expanded="false">ⓘ 이 섹션이 뭔가요?</button>
  </div>
  <div class="sec-explain" id="help-dist" hidden>
    <p><strong>왼쪽 도넛</strong>은 프로젝트 안의 모든 클래스를 등급별로 나눠 비율을 보여줍니다. G-SI 점수는 프로젝트 내부의 분포에서 percentile rank로 계산하므로, 다섯 등급(A~E)이 각각 약 20% 씩 거의 균등하게 분포하는 것이 정상입니다.</p>
    <p>이 도넛이 의미하는 것은 절대적인 위험도가 아니라 <strong>"이 프로젝트 안에서의 상대적 위치"</strong>입니다. 다른 프로젝트와 직접 비교하려면 raw 점수 분포(평균 G-SI, 최대 G-SI 등)를 함께 봐야 합니다.</p>
    <p><strong>오른쪽 표</strong>는 G-SI 산식에서 각 항목이 어느 정도 비중으로 가중 평균되는지 정리한 것입니다. 각 항목 이름에 마우스를 올리면 무엇을 측정하는지 한국어 설명이 풍선으로 나타납니다. 본 작품은 default 가중치로 산식의 신뢰도를 확보하고, 후속 단계에서 데이터 기반 튜닝(<code>--weights tuned</code>) 옵션을 추가할 예정입니다.</p>
  </div>
  <div class="grid-2">
    <div class="panel">{grade_donut}</div>
    <div class="panel">{weights_table}</div>
  </div>
</section>

<section>
  <div class="sec-head">
    <h2>Hotspot Table (G-SI 상위)</h2>
    <button class="sec-info" data-target="help-hotspot" aria-expanded="false">ⓘ 이 섹션이 뭔가요?</button>
  </div>
  <div class="sec-explain" id="help-hotspot" hidden>
    <p><strong>위험한 순서로 정렬된 클래스 목록</strong>입니다. 기본은 전체 클래스 중 G-SI 상위 N개를 보여주며, 두 가지 방법으로 표를 좁힐 수 있습니다.</p>
    <ul>
      <li><strong>등급 필터</strong> — A~E 중 하나를 선택하면 <em>그 등급 안에서 다시 상위 N개</em>를 골라 표를 새로 그립니다. "B 등급 안에서 가장 위험한 30개"처럼 봅니다.</li>
      <li><strong>텍스트 검색</strong> — 클래스의 정규 이름(FQN)이나 파일 경로 일부를 입력하면 일치하는 클래스만 남깁니다. 등급 필터와 동시 적용 가능합니다.</li>
    </ul>
    <p><strong>컬럼별 의미</strong> — 헤더에 마우스를 올리면 각 컬럼이 무엇을 측정하는지 설명이 표시됩니다. 컬럼 헤더를 클릭하면 그 항목 기준으로 정렬됩니다(다시 누르면 역순). 우측 카운터는 "현재 보이는 행 수 / 조건을 만족하는 전체 / 프로젝트 전체"를 보여줍니다.</p>
    <p><strong>주요 원인</strong> 컬럼은 G-SI 점수에 가장 크게 기여한 두 항목을 알려 줍니다. 예를 들어 "cc, global_state" 는 그 클래스가 분기가 많고 전역 상태에 강하게 의존한다는 뜻입니다.</p>
  </div>
  {hotspot_table}
</section>

<section>
  <div class="sec-head">
    <h2>Dependency Graph (G-SI 상위 hotspot 중심)</h2>
    <button class="sec-info" data-target="help-graph" aria-expanded="false">ⓘ 이 섹션이 뭔가요?</button>
  </div>
  <div class="sec-explain" id="help-graph" hidden>
    <p><strong>위험 클래스 주변의 참조 관계</strong>를 점과 선으로 그린 그래프입니다.</p>
    <ul>
      <li><strong>점(노드) = 클래스</strong>. 색은 등급(A 녹색 ~ E 빨강), 크기는 결합도(다른 클래스와 연결된 정도)에 비례합니다.</li>
      <li><strong>선(엣지) = 한 클래스가 다른 클래스를 참조하는 의존성</strong>. 화살표 방향은 "이 클래스를 사용한다"의 방향입니다.</li>
      <li><strong>표시 범위</strong> — G-SI 상위 hotspot 부터 채우고 그 인접 클래스까지 포함하되, 노드 수가 최대 150개를 넘지 않도록 제한합니다. 그래서 작은 프로젝트는 그래프 전체가, 큰 프로젝트는 가장 위험한 영역만 표시됩니다.</li>
    </ul>
    <p><strong>사용법</strong></p>
    <ul>
      <li><strong>마우스 휠</strong> — 커서 위치를 중심으로 확대 / 축소.</li>
      <li><strong>드래그</strong> — 보이는 영역 이동(pan).</li>
      <li><strong>＋ / − / 리셋 버튼</strong> — 중앙 기준 확대 / 축소 / 처음 배율로 복귀.</li>
      <li><strong>노드 hover</strong> — 그 클래스가 진해지고 인접 노드 / 엣지만 강조, 나머지는 흐려짐. 우측 패널에 FQN · G-SI · 등급 · 메트릭 · fan-in/out · 인접 클래스 샘플이 표시됩니다.</li>
      <li><strong>검색</strong> — 이름의 일부를 입력하면 매칭 노드가 흰 후광으로 강조됩니다. 매칭 안 된 노드는 흐려지지만 hover로 인접 관계는 그대로 볼 수 있습니다.</li>
      <li><strong>등급 강조 버튼</strong> — A~E 중 하나를 누르면 그 등급 노드만 강조. 검색과 동시 적용 가능합니다.</li>
    </ul>
  </div>
  <div class="panel graph-panel">{dependency_graph}</div>
</section>

<section>
  <div class="sec-head">
    <h2>Cycle Explorer (Strongly Connected Components)</h2>
    <button class="sec-info" data-target="help-cycle" aria-expanded="false">ⓘ 이 섹션이 뭔가요?</button>
  </div>
  <div class="sec-explain" id="help-cycle" hidden>
    <p><strong>A → B → C → A 처럼 서로 참조해서 빙빙 도는 클래스 묶음</strong>(Strongly Connected Component, SCC)을 모은 섹션입니다.</p>
    <p>일반적으로 의존성은 한 방향으로 흘러야 합니다(예: UI → 로직 → 데이터). 그런데 두 클래스가 서로를 참조하기 시작하면, 한쪽을 수정할 때 반드시 다른 쪽도 함께 신경 써야 합니다. 이런 묶음이 3개, 4개로 커지면 영향 범위 추적이 사실상 불가능에 가까워집니다. 그래서 SCC는 리팩토링 1순위 후보입니다.</p>
    <p>본 섹션의 <strong>카운트 카드 숫자가 곧 프로젝트 안의 모든 SCC 수</strong>입니다. 상위 N개를 보여주는 것이 아니라 전부 나열합니다. 프로젝트마다 수치가 다른데, 예를 들어 OpenRA.Game 모듈은 5개, OpenRA.Mods.Common 모듈은 4개의 묶음이 있습니다.</p>
    <p>각 항목을 클릭하면 그 묶음에 속한 클래스 FQN 목록이 펼쳐집니다. 묶음 안의 모든 클래스가 동일한 SCC에 있다는 사실 자체가 이미 위험 신호이므로, 점수가 낮은 클래스라도 함께 정리 대상이 됩니다.</p>
  </div>
  <div class="panel">{cycle_explorer}</div>
</section>

<section>
  <div class="sec-head">
    <h2>Module Summary</h2>
    <button class="sec-info" data-target="help-module" aria-expanded="false">ⓘ 이 섹션이 뭔가요?</button>
  </div>
  <div class="sec-explain" id="help-module" hidden>
    <p>클래스 단위로 계산된 G-SI 점수를 <strong>최상위 폴더(모듈) 단위로 집계</strong>한 표입니다. "이 폴더 안 클래스들이 평균적으로 얼마나 위험한가"를 한눈에 봅니다.</p>
    <p><strong>컬럼 의미</strong></p>
    <ul>
      <li><strong>모듈</strong> — 분석 입력 폴더 바로 아래의 1단계 폴더 이름. 예를 들어 OpenRA.Game을 분석하면 Network, Server, Map 등이 모듈로 잡힙니다. <code>(root)</code>는 폴더 안에 들어있지 않고 분석 폴더 바로 밑에 놓인 .cs 파일들을 한 모듈로 묶은 것입니다.</li>
      <li><strong>등급</strong> — 모듈 내 클래스 평균 G-SI를 기준으로 한 A~E 등급.</li>
      <li><strong>평균 G-SI</strong> — 모듈에 속한 모든 클래스의 G-SI 평균. 모듈 전체의 위험도를 가장 잘 대표하는 값입니다.</li>
      <li><strong>최대 G-SI</strong> — 모듈에서 가장 위험한 클래스 하나의 G-SI. 평균은 낮은데 최대만 높다면 그 모듈에 핀포인트 hotspot이 있다는 신호입니다.</li>
      <li><strong>파일 수 · 클래스 수</strong> — 모듈에 속한 .cs 파일과 클래스(struct, interface, record 포함)의 개수.</li>
    </ul>
    <p>모듈 단위로 보면 어느 컴포넌트가 통째로 정리 대상인지, 아니면 특정 클래스만 문제인지 빠르게 판단할 수 있습니다.</p>
  </div>
  {module_table}
</section>

</main>
<footer>
  Generated by <code>game-si</code> · static-only metrics (G-SI-Static) · CDN-free single-file report
</footer>

<script>
(function() {{
  const dataRoot = {embedded_json};
  window.__GAME_SI__ = dataRoot;
  const GRADE_COLORS = dataRoot.grade_colors;
  const TOP_N = dataRoot.hotspot_top_n || 30;
  const ALL_CLASSES = dataRoot.all_classes || [];

  // ----- Hotspot Table 동적 렌더링 -----
  const textInput = document.getElementById('hotspot-filter');
  const gradeSelect = document.getElementById('grade-filter');
  const tbody = document.getElementById('hotspot-tbody');
  const countSpan = document.getElementById('hotspot-count');

  function escapeHtml(s) {{
    return String(s).replace(/[&<>"']/g, c => ({{
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }})[c]);
  }}

  let sortKey = 'si';
  let sortAsc = false;

  function renderHotspots() {{
    if (!tbody) return;
    const needle = (textInput.value || '').toLowerCase();
    const grade = gradeSelect.value;

    // 1) 등급/텍스트 필터로 후보 추출
    let candidates = ALL_CLASSES.filter(c => {{
      if (grade && c.grade !== grade) return false;
      if (needle) {{
        const text = (c.fqn + ' ' + c.file_path).toLowerCase();
        if (!text.includes(needle)) return false;
      }}
      return true;
    }});

    // 2) 정렬
    candidates.sort((a, b) => {{
      const av = a[sortKey];
      const bv = b[sortKey];
      const cmp = (typeof av === 'number') ? (av - bv) : String(av).localeCompare(String(bv));
      return cmp * (sortAsc ? 1 : -1);
    }});

    const totalMatched = candidates.length;
    const shown = candidates.slice(0, TOP_N);

    // 3) DOM 렌더링
    if (shown.length === 0) {{
      tbody.innerHTML = '<tr><td colspan="11" class="empty">조건에 맞는 클래스가 없습니다.</td></tr>';
    }} else {{
      tbody.innerHTML = shown.map((c, i) => {{
        const reasons = (c.top_reasons && c.top_reasons.length) ? c.top_reasons.join(', ') : '—';
        const color = GRADE_COLORS[c.grade] || '#475569';
        return `<tr data-grade="${{c.grade}}">
          <td class="num rank">${{i + 1}}</td>
          <td><span class="grade-badge" style="background:${{color}}">${{c.grade}}</span></td>
          <td class="num">${{c.si.toFixed(1)}}</td>
          <td class="fqn" title="${{escapeHtml(c.fqn)}}">${{escapeHtml(c.fqn)}}</td>
          <td class="num">${{c.cc.toFixed(1)}}</td>
          <td class="num">${{c.coupling}}</td>
          <td class="num">${{c.global_state}}</td>
          <td class="num">${{c.dependency_cycle}}</td>
          <td class="num">${{c.game_loop_centrality.toFixed(2)}}</td>
          <td class="reasons">${{escapeHtml(reasons)}}</td>
          <td class="path"><code>${{escapeHtml(c.file_path)}}:${{c.start_line}}</code></td>
        </tr>`;
      }}).join('');
    }}

    if (countSpan) {{
      if (grade || needle) {{
        countSpan.textContent = `${{shown.length}} / ${{totalMatched}} 개 표시 (전체 ${{ALL_CLASSES.length}})`;
      }} else {{
        countSpan.textContent = `${{shown.length}} / ${{ALL_CLASSES.length}} 개 표시`;
      }}
    }}
  }}

  if (textInput) textInput.addEventListener('input', renderHotspots);
  if (gradeSelect) gradeSelect.addEventListener('change', renderHotspots);

  // 컬럼 정렬: 헤더 클릭으로 sortKey 변경
  const sortableHeaders = {{
    2: 'si', 3: 'fqn', 4: 'cc', 5: 'coupling',
    6: 'global_state', 7: 'dependency_cycle', 8: 'game_loop_centrality'
  }};
  const table = document.getElementById('hotspot-table');
  if (table) {{
    table.querySelectorAll('th.sortable').forEach(th => {{
      th.addEventListener('click', () => {{
        const colIdx = Array.from(th.parentNode.children).indexOf(th);
        const key = sortableHeaders[colIdx];
        if (!key) return;
        if (sortKey === key) {{
          sortAsc = !sortAsc;
        }} else {{
          sortKey = key;
          sortAsc = (key === 'fqn');  // 이름은 오름차순 디폴트, 수치는 내림차순
        }}
        renderHotspots();
      }});
    }});
  }}

  renderHotspots();

  // ----- Dependency Graph 인터랙션 -----
  // GRADE_COLORS는 이미 위에서 dataRoot.grade_colors로 선언되어 있다 (중복 선언 금지).
  const graphSvg = document.getElementById('depgraph');
  const graphInfo = document.getElementById('graph-info');
  const nodeInfoScript = document.getElementById('graph-node-info');
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

    // ----- Dependency Graph 검색 & 등급 토글 -----
    const graphSearch = document.getElementById('graph-search');
    const gradeToggle = document.getElementById('graph-grade-toggle');
    const matchCount = document.getElementById('graph-match-count');

    function getNodeGrade(nodeEl) {{
      const idx = nodeEl.getAttribute('data-idx');
      const info = nodeInfo[idx];
      return info ? info.grade : null;
    }}

    function applyGraphSearch() {{
      const needle = (graphSearch ? graphSearch.value : '').trim().toLowerCase();
      const activeGradeBtn = gradeToggle ? gradeToggle.querySelector('.gt-active') : null;
      const gradeFilter = activeGradeBtn ? activeGradeBtn.getAttribute('data-grade') : '';
      const hasFilter = !!(needle || gradeFilter);

      let matched = 0;
      allNodes.forEach(node => {{
        const fqn = (node.getAttribute('data-fqn') || '').toLowerCase();
        const grade = getNodeGrade(node);
        const textOk = !needle || fqn.includes(needle);
        const gradeOk = !gradeFilter || grade === gradeFilter;
        if (hasFilter && textOk && gradeOk) {{
          node.classList.add('search-match');
          matched++;
        }} else {{
          node.classList.remove('search-match');
        }}
      }});
      graphSvg.classList.toggle('has-search', hasFilter);

      if (matchCount) {{
        if (hasFilter) {{
          matchCount.textContent = `${{matched}}개 노드 강조됨`;
        }} else {{
          matchCount.textContent = '';
        }}
      }}
    }}

    if (graphSearch) graphSearch.addEventListener('input', applyGraphSearch);
    if (gradeToggle) {{
      gradeToggle.querySelectorAll('.gt-btn').forEach(btn => {{
        btn.addEventListener('click', () => {{
          gradeToggle.querySelectorAll('.gt-btn').forEach(b => b.classList.remove('gt-active'));
          btn.classList.add('gt-active');
          applyGraphSearch();
        }});
      }});
    }}

    graphSvg.addEventListener('mouseleave', () => {{
      clearHl();
      graphInfo.innerHTML = '<div class="info-empty">노드 위에 마우스를 올리면<br>여기에 상세 정보가 나타납니다.<br><br>아래 검색창에 클래스 이름을 입력하거나 등급 버튼을 누르면<br>해당 노드가 강조됩니다.</div>';
    }});

    // ----- Dependency Graph zoom / pan -----
    const initialVB = graphSvg.getAttribute('viewBox').split(' ').map(Number);
    let vb = {{ x: initialVB[0], y: initialVB[1], w: initialVB[2], h: initialVB[3] }};

    function applyVB() {{
      graphSvg.setAttribute('viewBox', `${{vb.x}} ${{vb.y}} ${{vb.w}} ${{vb.h}}`);
    }}

    function zoomAt(factor, focusX, focusY) {{
      // focusX/Y in viewBox coords
      const newW = vb.w / factor;
      const newH = vb.h / factor;
      // 최소·최대 줌 제한
      if (newW < initialVB[2] * 0.1 || newW > initialVB[2] * 4) return;
      vb.x = focusX - (focusX - vb.x) / factor;
      vb.y = focusY - (focusY - vb.y) / factor;
      vb.w = newW;
      vb.h = newH;
      applyVB();
    }}

    graphSvg.addEventListener('wheel', (e) => {{
      e.preventDefault();
      const pt = graphSvg.createSVGPoint();
      pt.x = e.clientX; pt.y = e.clientY;
      const sp = pt.matrixTransform(graphSvg.getScreenCTM().inverse());
      const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      zoomAt(factor, sp.x, sp.y);
    }}, {{ passive: false }});

    let dragging = false, dragStart = null;
    graphSvg.addEventListener('mousedown', (e) => {{
      if (e.target.closest('.node')) return; // 노드 위에서는 hover 동작 우선
      dragging = true;
      dragStart = {{ x: e.clientX, y: e.clientY, vbX: vb.x, vbY: vb.y }};
      graphSvg.classList.add('dragging');
    }});
    window.addEventListener('mousemove', (e) => {{
      if (!dragging) return;
      const rect = graphSvg.getBoundingClientRect();
      const scaleX = vb.w / rect.width;
      const scaleY = vb.h / rect.height;
      vb.x = dragStart.vbX - (e.clientX - dragStart.x) * scaleX;
      vb.y = dragStart.vbY - (e.clientY - dragStart.y) * scaleY;
      applyVB();
    }});
    window.addEventListener('mouseup', () => {{
      dragging = false;
      graphSvg.classList.remove('dragging');
    }});

    const zoomIn = document.getElementById('zoom-in');
    const zoomOut = document.getElementById('zoom-out');
    const zoomReset = document.getElementById('zoom-reset');
    if (zoomIn) zoomIn.addEventListener('click', () => zoomAt(1.25, vb.x + vb.w / 2, vb.y + vb.h / 2));
    if (zoomOut) zoomOut.addEventListener('click', () => zoomAt(1 / 1.25, vb.x + vb.w / 2, vb.y + vb.h / 2));
    if (zoomReset) zoomReset.addEventListener('click', () => {{
      vb = {{ x: initialVB[0], y: initialVB[1], w: initialVB[2], h: initialVB[3] }};
      applyVB();
    }});
  }}

  // ----- 섹션 헤더 ⓘ 설명 토글 -----
  document.querySelectorAll('.sec-info').forEach(btn => {{
    btn.addEventListener('click', () => {{
      const targetId = btn.getAttribute('data-target');
      const target = document.getElementById(targetId);
      if (!target) return;
      const isHidden = target.hasAttribute('hidden');
      if (isHidden) {{
        target.removeAttribute('hidden');
        btn.setAttribute('aria-expanded', 'true');
        btn.textContent = '✕ 설명 닫기';
      }} else {{
        target.setAttribute('hidden', '');
        btn.setAttribute('aria-expanded', 'false');
        btn.textContent = 'ⓘ 이 섹션이 뭔가요?';
      }}
    }});
  }});
}})();
</script>
</body>
</html>
"""
