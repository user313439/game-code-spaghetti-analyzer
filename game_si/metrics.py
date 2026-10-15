"""정적 메트릭 계산.

본 모듈은 `csharp-analyzer`가 산출한 AST JSON을 받아 다음을 계산한다.

* CC (Cyclomatic Complexity) — 메서드 단위 (analyzer가 이미 산출)
* Coupling — 클래스 단위 fan-in + fan-out (CBO 기반)
* DependencyCycle — 클래스 그래프의 SCC 멤버 여부 및 크기
* GlobalState — 정적 멤버 접근 + 싱글톤 접근 횟수
* GameLoopCentrality — 게임 루프 진입점으로부터의 reachability

산출 결과는 `compute_metrics()`가 반환하는 dict이며, 후속 단계의 G-SI 계산기로 전달된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import Counter
from pathlib import Path
from typing import Any

import networkx as nx


@dataclass
class MethodMetrics:
    fqn: str               # "Namespace.Class.Method"
    class_fqn: str
    file_path: str
    name: str
    start_line: int
    end_line: int
    cc: int                # Cyclomatic Complexity
    loc: int
    is_game_loop_entry: bool
    invoked_names: list[str]
    game_loop_centrality: float = 0.0
    symbol_id: str = ""
    invoked_symbols: list[str] = field(default_factory=list)
    source_fqn: str = ""


@dataclass
class ClassMetrics:
    fqn: str               # "Namespace.Class"
    name: str
    file_path: str
    start_line: int
    end_line: int
    kind: str
    base_types: list[str] = field(default_factory=list)
    referenced_types: list[str] = field(default_factory=list)
    static_member_accesses: list[str] = field(default_factory=list)
    singleton_accesses: list[str] = field(default_factory=list)
    methods: list[MethodMetrics] = field(default_factory=list)

    # 산출 메트릭
    cc_max: int = 0
    cc_mean: float = 0.0
    cc_top10p_mean: float = 0.0
    fan_in: int = 0
    fan_out: int = 0
    coupling: int = 0          # fan_in + fan_out
    cycle_member: bool = False
    cycle_size: int = 0
    cycle_edges: int = 0           # 자신이 관여한 SCC 내부 edge 수 (in + out)
    global_state: int = 0
    game_loop_centrality: float = 0.0
    source_fqn: str = ""


@dataclass
class MetricsResult:
    schema_version: str
    input_path: str
    classes: list[ClassMetrics]
    methods: list[MethodMetrics]
    class_graph: nx.DiGraph
    sccs: list[set[str]]       # 크기 ≥ 2 인 SCC만

    @property
    def class_index(self) -> dict[str, ClassMetrics]:
        return {c.fqn: c for c in self.classes}


# ---------------------------------------------------------------------------
# 메인 진입점
# ---------------------------------------------------------------------------


def compute_metrics(ast_data: dict) -> MetricsResult:
    """AST JSON dict를 받아 ClassMetrics/MethodMetrics를 채워 반환한다."""
    classes, methods = _build_units(ast_data)
    class_graph = _build_class_graph(classes)

    _compute_coupling(classes, class_graph)
    _compute_cycle_membership(classes, class_graph)
    _compute_global_state(classes)
    _compute_method_cc_aggregates(classes)
    _compute_game_loop_centrality(classes, methods)

    sccs = [scc for scc in nx.strongly_connected_components(class_graph) if len(scc) >= 2]

    return MetricsResult(
        schema_version=ast_data.get("schema_version", "?"),
        input_path=ast_data.get("input_path", ""),
        classes=classes,
        methods=methods,
        class_graph=class_graph,
        sccs=sccs,
    )


# ---------------------------------------------------------------------------
# Step 1 — AST에서 단위 객체 구성
# ---------------------------------------------------------------------------


def _build_units(ast_data: dict) -> tuple[list[ClassMetrics], list[MethodMetrics]]:
    classes: list[ClassMetrics] = []
    methods: list[MethodMetrics] = []
    class_counts = Counter(c["fully_qualified_name"] for f in ast_data.get("files", [])
                           for c in f.get("classes", []))

    for f in ast_data.get("files", []):
        file_path = f.get("relative_path") or f.get("path", "")
        for c in f.get("classes", []):
            source_fqn = c["fully_qualified_name"]
            node_fqn = source_fqn
            if class_counts[source_fqn] > 1:
                node_fqn = f"{source_fqn}@{file_path}:{c['start_line']}:{c.get('kind', 'class')}"
            cls = ClassMetrics(
                fqn=node_fqn,
                source_fqn=source_fqn,
                name=c["name"],
                file_path=file_path,
                start_line=c["start_line"],
                end_line=c["end_line"],
                kind=c.get("kind", "class"),
                base_types=list(c.get("base_types", [])),
                referenced_types=list(c.get("referenced_types", [])),
                static_member_accesses=list(c.get("static_member_accesses", [])),
                singleton_accesses=list(c.get("singleton_accesses", [])),
            )
            for m in c.get("methods", []):
                method = MethodMetrics(
                    fqn=f"{cls.fqn}.{m['name']}",
                    class_fqn=cls.fqn,
                    file_path=file_path,
                    name=m["name"],
                    start_line=m["start_line"],
                    end_line=m["end_line"],
                    cc=m["cyclomatic_complexity"],
                    loc=m["loc"],
                    is_game_loop_entry=bool(m.get("is_game_loop_entry", False)),
                    invoked_names=list(m.get("invoked_names", [])),
                    symbol_id=m.get("symbol_id") or "",
                    invoked_symbols=list(m.get("invoked_symbols", [])),
                    source_fqn=f"{source_fqn}.{m['name']}",
                )
                cls.methods.append(method)
                methods.append(method)
            classes.append(cls)

    # 소스 위치를 추가해 오버로드와 플랫폼별 동명 선언을 독립된 노드로 보존한다.
    method_counts = Counter(m.fqn for m in methods)
    for i, m in enumerate(methods):
        if method_counts[m.fqn] > 1:
            m.fqn = f"{m.fqn}@{m.file_path}:{m.start_line}:{i}"

    return classes, methods


# ---------------------------------------------------------------------------
# Step 2 — 클래스 의존성 그래프
# ---------------------------------------------------------------------------


def _build_class_graph(classes: list[ClassMetrics]) -> nx.DiGraph:
    """클래스 간 참조 관계로 directed graph를 구성한다.

    노드는 클래스의 fully-qualified name (FQN)이다.
    엣지 A → B 는 "A 가 B 를 참조한다"를 의미한다.
    참조 출처는 다음 두 가지이다.

    - base_types: A 의 베이스 타입 목록
    - referenced_types: A 내부에서 `new T(...)` 형태로 생성된 타입

    syntactic 분석이므로 타입 이름은 단순 식별자 또는 짧은 dotted path이며,
    프로젝트 내 클래스의 단순 이름(name) 또는 FQN과 매칭되는 항목만 엣지로 사용한다.
    """
    g: nx.DiGraph = nx.DiGraph()
    for c in classes:
        g.add_node(c.fqn, name=c.name, kind=c.kind)

    # 매칭 인덱스: 단순 이름 → FQN 후보, FQN → FQN
    name_to_fqns: dict[str, list[str]] = {}
    for c in classes:
        name_to_fqns.setdefault(c.name, []).append(c.fqn)
        name_to_fqns.setdefault(c.source_fqn or c.fqn, []).append(c.fqn)
    fqn_set = {c.fqn for c in classes}

    for c in classes:
        targets: set[str] = set()
        for ref in (*c.base_types, *c.referenced_types):
            target = _resolve_type_reference(ref, name_to_fqns, fqn_set)
            if target is not None and target != c.fqn:
                targets.add(target)
        for t in sorted(targets):
            g.add_edge(c.fqn, t)

    return g


def _resolve_type_reference(
    ref: str,
    name_to_fqns: dict[str, list[str]],
    fqn_set: set[str],
) -> str | None:
    """타입 참조 문자열을 프로젝트 내 클래스 FQN으로 매핑한다.

    매칭 우선순위:
      1. ref 자체가 프로젝트 FQN과 일치
      2. 수식되지 않은 ref가 단순 이름과 일치하고, 후보가 유일한 경우
      3. 그 외(외부 라이브러리 등)는 매칭 실패 → None
    """
    if not ref:
        return None
    exact = ref.strip().removeprefix("global::")
    if exact in fqn_set:
        return exact
    exact_candidates = list(dict.fromkeys(name_to_fqns.get(exact, [])))
    if exact_candidates:
        return exact_candidates[0] if len(exact_candidates) == 1 else None
    if "." in exact or "::" in exact:
        return None  # 외부/미해결 수식 타입을 동명의 로컬 타입으로 대체하지 않는다.
    # 제네릭 부분 제거: List<Foo> → List
    base = ref.split("<", 1)[0].strip().rstrip("[]?")
    if not base:
        return None

    if base in fqn_set:
        return base

    last = base.rsplit(".", 1)[-1]
    candidates = list(dict.fromkeys(name_to_fqns.get(last, [])))
    if len(candidates) == 1:
        return candidates[0]
    # 동명이클래스가 여러 개인 경우 — semantic 도입 전에는 매칭 불가
    return None


# ---------------------------------------------------------------------------
# Step 3 — Coupling
# ---------------------------------------------------------------------------


def _compute_coupling(classes: list[ClassMetrics], g: nx.DiGraph) -> None:
    for c in classes:
        if c.fqn not in g:
            c.fan_in = 0
            c.fan_out = 0
            c.coupling = 0
            continue
        c.fan_out = g.out_degree(c.fqn)
        c.fan_in = g.in_degree(c.fqn)
        c.coupling = c.fan_in + c.fan_out


# ---------------------------------------------------------------------------
# Step 4 — DependencyCycle (SCC)
# ---------------------------------------------------------------------------


def _compute_cycle_membership(classes: list[ClassMetrics], g: nx.DiGraph) -> None:
    """크기 ≥ 2 인 SCC에 속하는 클래스를 cycle 멤버로 분류 + 세분화 메트릭.

    각 SCC 멤버에 대해:
      * ``cycle_member`` = True
      * ``cycle_size``   = SCC 의 크기
      * ``cycle_edges``  = SCC 내부에서 자신이 관여한 edge 수 (in + out)

    같은 SCC 의 클래스도 SCC 내부 edge 수에 따라 차별화된다 — 깊이 얽힌
    god-class 와 SCC 가장자리의 peripheral 클래스가 같은 점수가 아니다.
    """
    by_fqn = {c.fqn: c for c in classes}
    for scc in nx.strongly_connected_components(g):
        if len(scc) < 2:
            continue
        scc_set = set(scc)
        size = len(scc_set)
        # SCC 내부 edge 만 추출
        in_within: dict[str, int] = {fqn: 0 for fqn in scc_set}
        out_within: dict[str, int] = {fqn: 0 for fqn in scc_set}
        for u in scc_set:
            if u not in g:
                continue
            for v in g.successors(u):
                if v in scc_set:
                    out_within[u] += 1
                    in_within[v] += 1
        for fqn in scc_set:
            c = by_fqn.get(fqn)
            if c is None:
                continue
            c.cycle_member = True
            c.cycle_size = size
            c.cycle_edges = in_within.get(fqn, 0) + out_within.get(fqn, 0)


# ---------------------------------------------------------------------------
# Step 5 — GlobalState
# ---------------------------------------------------------------------------


def _compute_global_state(classes: list[ClassMetrics]) -> None:
    for c in classes:
        c.global_state = len(c.static_member_accesses) + len(c.singleton_accesses)


# ---------------------------------------------------------------------------
# Step 6 — 메서드 CC 집계 (클래스 단위 통계)
# ---------------------------------------------------------------------------


def _compute_method_cc_aggregates(classes: list[ClassMetrics]) -> None:
    for c in classes:
        if not c.methods:
            c.cc_max = 0
            c.cc_mean = 0.0
            c.cc_top10p_mean = 0.0
            continue
        cc_values = sorted((m.cc for m in c.methods), reverse=True)
        c.cc_max = cc_values[0]
        c.cc_mean = sum(cc_values) / len(cc_values)
        # 상위 10% 평균, 단 메서드 수가 적으면 최소 1개 이상은 사용한다.
        top_n = max(1, len(cc_values) // 10)
        c.cc_top10p_mean = sum(cc_values[:top_n]) / top_n


# ---------------------------------------------------------------------------
# Step 7 — GameLoopCentrality
# ---------------------------------------------------------------------------


def _compute_game_loop_centrality(
    classes: list[ClassMetrics],
    methods: list[MethodMetrics],
) -> None:
    """게임 루프 진입점으로부터 도달 가능한 메서드의 reachability depth(역수)를 점수화한다.

    정확한 semantic 심볼을 우선 사용한다. 옛 AST는 전체 이름이 유일할 때만
    연결하며, 단순 이름 fallback은 수식되지 않은 호출에만 허용한다.
    외부 타입과 동명 오버로드를 임의의 로컬 메서드로 연결하지 않는다.

    점수 정의:
        depth=0(진입점 자신) → 1.0
        depth=1               → 0.5
        depth=2               → 0.333
        depth=d               → 1 / (1 + d)
        도달 불가              → 0.0
    """
    # 메서드 호출 그래프 빌드 (메서드 FQN 단위, 단순 이름 매칭)
    g: nx.DiGraph = nx.DiGraph()
    name_to_fqns: dict[str, list[str]] = {}
    exact_to_fqns: dict[str, list[str]] = {}
    symbols: dict[str, list[str]] = {}
    for m in methods:
        g.add_node(m.fqn)
        name_to_fqns.setdefault(m.name, []).append(m.fqn)
        exact_to_fqns.setdefault(m.source_fqn or m.fqn, []).append(m.fqn)
        if m.symbol_id:
            symbols.setdefault(m.symbol_id, []).append(m.fqn)

    for m in methods:
        for symbol in m.invoked_symbols:
            candidates = symbols.get(symbol, [])
            if len(candidates) == 1:
                g.add_edge(m.fqn, candidates[0])
        for inv in m.invoked_names:
            candidates = exact_to_fqns.get(inv, [])
            if not candidates and "." not in inv:
                candidates = name_to_fqns.get(inv.split("<", 1)[0].strip(), [])
            # 후보가 정확히 1개일 때만 엣지 추가 (안전한 매칭)
            if len(candidates) == 1 and candidates[0] != m.fqn:
                g.add_edge(m.fqn, candidates[0])

    # BFS로 진입점으로부터의 최단 거리 측정
    entries = [m.fqn for m in methods if m.is_game_loop_entry]
    if not entries:
        # 진입점이 없으면 모두 0
        return

    depth: dict[str, int] = {}
    for entry in entries:
        if entry not in g:
            continue
        lengths = nx.single_source_shortest_path_length(g, entry)
        for fqn, d in lengths.items():
            if fqn not in depth or d < depth[fqn]:
                depth[fqn] = d

    for m in methods:
        d = depth.get(m.fqn)
        m.game_loop_centrality = (1.0 / (1 + d)) if d is not None else 0.0

    # 클래스 단위 집계: 소속 메서드 중 최댓값
    for c in classes:
        if not c.methods:
            c.game_loop_centrality = 0.0
        else:
            c.game_loop_centrality = max(m.game_loop_centrality for m in c.methods)


# ---------------------------------------------------------------------------
# 직렬화 헬퍼
# ---------------------------------------------------------------------------


def metrics_to_dict(result: MetricsResult) -> dict[str, Any]:
    """MetricsResult를 JSON 직렬화 가능한 dict로 변환한다."""
    g = result.class_graph
    # 클래스별 in/out 이웃 FQN 리스트 (직렬화용). LLM Advisor 가 이를 prompt 에
    # 포함시켜 "이 클래스를 누가 참조하고, 이 클래스가 무엇을 참조하는지" 의 그래프
    # 컨텍스트를 모델에게 전달한다.
    def _neighbors(fqn: str) -> tuple[list[str], list[str]]:
        if fqn not in g:
            return [], []
        # 그래프 엣지: u → v 는 "u 가 v 를 참조" 의미.
        out_n = sorted(g.successors(fqn))       # 이 클래스가 참조하는 것 (fan_out 대상)
        in_n = sorted(g.predecessors(fqn))      # 이 클래스를 참조하는 것 (fan_in 출처)
        return in_n, out_n

    return {
        "schema_version": "metrics-0.2",
        "ast_schema_version": result.schema_version,
        "input_path": result.input_path,
        "classes": [
            {
                "fqn": c.fqn,
                "source_fqn": c.source_fqn or c.fqn,
                "name": c.name,
                "file_path": c.file_path,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "kind": c.kind,
                "cc_max": c.cc_max,
                "cc_mean": round(c.cc_mean, 3),
                "cc_top10p_mean": round(c.cc_top10p_mean, 3),
                "fan_in": c.fan_in,
                "fan_out": c.fan_out,
                "coupling": c.coupling,
                "cycle_member": c.cycle_member,
                "cycle_size": c.cycle_size,
                "cycle_edges": c.cycle_edges,
                "global_state": c.global_state,
                "game_loop_centrality": round(c.game_loop_centrality, 4),
                "method_count": len(c.methods),
                # in/out 이웃 (그래프 컨텍스트, LLM Advisor 가 사용)
                "in_neighbors": _neighbors(c.fqn)[0],
                "out_neighbors": _neighbors(c.fqn)[1],
            }
            for c in result.classes
        ],
        "methods": [
            {
                "fqn": m.fqn,
                "source_fqn": m.source_fqn or m.fqn,
                "symbol_id": m.symbol_id,
                "class_fqn": m.class_fqn,
                "file_path": m.file_path,
                "name": m.name,
                "start_line": m.start_line,
                "end_line": m.end_line,
                "cc": m.cc,
                "loc": m.loc,
                "is_game_loop_entry": m.is_game_loop_entry,
                "game_loop_centrality": round(m.game_loop_centrality, 4),
            }
            for m in result.methods
        ],
        "cycles": [
            {"size": len(scc), "members": sorted(scc)}
            for scc in sorted(result.sccs, key=lambda s: (-len(s), sorted(s)))
        ],
    }


def load_ast(path: Path | str) -> dict:
    """AST JSON 파일을 읽어 dict로 반환한다."""
    import json
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
