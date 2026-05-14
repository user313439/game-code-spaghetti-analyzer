"""G-SI (Game Spaghetti Index) 산출.

본 모듈은 `metrics.MetricsResult`를 입력으로 받아
계획서(`docs/plan_final_draft.md` §4)의 정의에 따라 점수를 산출한다.

처리 절차:
    1. 항목별 raw 값을 추출 (CC, Coupling, DependencyCycle, GlobalState, GameLoopCentrality)
    2. Z-score 표준화 (프로젝트 내부 기준)
    3. 가중합 계산 (G-SI-Static / G-SI-Full)
    4. Percentile rank로 0~100 변환
    5. 등급 분류 (A~E)
    6. 클래스 → 파일 → 모듈로 집계

`G-SI-Static` 만 본 모듈에서 산출한다. `G-SI-Full`은 Git 변경 이력(`ChangeRisk`)이
필요하므로 후속 단계에서 별도 모듈로 추가한다.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any

from .metrics import ClassMetrics, MetricsResult, MethodMetrics


# ---------------------------------------------------------------------------
# 가중치 — `plan_final_draft.md` §4.2
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS_STATIC: dict[str, float] = {
    "cc": 0.30,
    "coupling": 0.25,
    "dependency_cycle": 0.15,
    "global_state": 0.15,
    "game_loop_centrality": 0.15,
}


# ---------------------------------------------------------------------------
# 등급표 — `plan_final_draft.md` §4.7
# ---------------------------------------------------------------------------


def _grade(score: float) -> str:
    if score < 20: return "A"
    if score < 40: return "B"
    if score < 60: return "C"
    if score < 80: return "D"
    return "E"


# ---------------------------------------------------------------------------
# 산출 결과 모델
# ---------------------------------------------------------------------------


@dataclass
class ClassScore:
    fqn: str
    name: str
    file_path: str
    module: str
    start_line: int
    end_line: int
    kind: str
    # raw 메트릭 값 (대시보드에서 표시)
    raw: dict[str, float] = field(default_factory=dict)
    # 표준화된 값
    z: dict[str, float] = field(default_factory=dict)
    # 가중합 (정규화 전)
    raw_score: float = 0.0
    # 최종 G-SI (0~100)
    si: float = 0.0
    grade: str = "A"
    # 주요 위험 원인 (큰 z 값 기준 상위)
    top_reasons: list[str] = field(default_factory=list)


@dataclass
class FileScore:
    file_path: str
    module: str
    si_mean: float = 0.0
    si_max: float = 0.0
    grade: str = "A"
    class_count: int = 0
    loc: int = 0


@dataclass
class ModuleScore:
    module: str
    si_mean: float = 0.0
    si_max: float = 0.0
    grade: str = "A"
    class_count: int = 0
    file_count: int = 0


@dataclass
class ScoringResult:
    weights: dict[str, float]
    class_scores: list[ClassScore]
    file_scores: list[FileScore]
    module_scores: list[ModuleScore]
    grade_distribution: dict[str, int]  # {"A": n, ...}
    total_classes: int
    total_methods: int


# ---------------------------------------------------------------------------
# 메인 진입점
# ---------------------------------------------------------------------------


def compute_si_static(
    metrics: MetricsResult,
    weights: dict[str, float] | None = None,
) -> ScoringResult:
    """`metrics.MetricsResult`에서 G-SI-Static 점수를 산출한다."""
    w = _normalize_weights(weights or DEFAULT_WEIGHTS_STATIC)

    if not metrics.classes:
        return ScoringResult(
            weights=w,
            class_scores=[],
            file_scores=[],
            module_scores=[],
            grade_distribution={g: 0 for g in "ABCDE"},
            total_classes=0,
            total_methods=0,
        )

    # 1) raw 추출
    rows: list[dict[str, float]] = []
    for c in metrics.classes:
        rows.append({
            "cc": float(_class_cc_representative(c)),
            "coupling": float(c.coupling),
            "dependency_cycle": float(c.cycle_size if c.cycle_member else 0),
            "global_state": float(c.global_state),
            "game_loop_centrality": float(c.game_loop_centrality),
        })

    # 2) Z-score 표준화 (프로젝트 내부 기준)
    z_rows = _z_score_rows(rows)

    # 3) 가중합
    raw_scores = [
        sum(w[k] * z_rows[i][k] for k in w)
        for i in range(len(rows))
    ]

    # 4) Percentile rank로 0~100 변환
    si_values = _percentile_rank(raw_scores)

    # 5) ClassScore 조립
    class_scores: list[ClassScore] = []
    for c, raw, z, raw_score, si in zip(metrics.classes, rows, z_rows, raw_scores, si_values):
        cs = ClassScore(
            fqn=c.fqn,
            name=c.name,
            file_path=c.file_path,
            module=_module_of(c.file_path),
            start_line=c.start_line,
            end_line=c.end_line,
            kind=c.kind,
            raw=raw,
            z=z,
            raw_score=raw_score,
            si=si,
            grade=_grade(si),
            top_reasons=_top_reasons(z, w),
        )
        class_scores.append(cs)

    # 6) 파일/모듈 집계
    file_scores = _aggregate_files(class_scores, metrics)
    module_scores = _aggregate_modules(file_scores)

    grade_dist = {g: 0 for g in "ABCDE"}
    for cs in class_scores:
        grade_dist[cs.grade] += 1

    return ScoringResult(
        weights=w,
        class_scores=class_scores,
        file_scores=file_scores,
        module_scores=module_scores,
        grade_distribution=grade_dist,
        total_classes=len(metrics.classes),
        total_methods=len(metrics.methods),
    )


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _normalize_weights(w: dict[str, float]) -> dict[str, float]:
    """가중치 합이 1이 되도록 정규화한다. 구현되지 않은 항목이 있을 때를 대비."""
    total = sum(v for v in w.values() if v > 0)
    if total <= 0:
        # 폴백: 모든 항목 동등
        keys = list(DEFAULT_WEIGHTS_STATIC.keys())
        return {k: 1.0 / len(keys) for k in keys}
    return {k: v / total for k, v in w.items()}


def _class_cc_representative(c: ClassMetrics) -> float:
    """클래스 단위 CC 대표값. `plan_final_draft.md` §4.1 — 상위 10% 평균."""
    return c.cc_top10p_mean if c.methods else 0.0


def _z_score_rows(rows: list[dict[str, float]]) -> list[dict[str, float]]:
    if not rows:
        return []
    keys = list(rows[0].keys())
    stats: dict[str, tuple[float, float]] = {}
    for k in keys:
        values = [r[k] for r in rows]
        mean = statistics.fmean(values)
        # 표준편차가 0이면 1로 두어 0/0을 피한다.
        try:
            stdev = statistics.pstdev(values) or 1.0
        except statistics.StatisticsError:
            stdev = 1.0
        stats[k] = (mean, stdev)

    z_rows: list[dict[str, float]] = []
    for r in rows:
        z = {k: (r[k] - stats[k][0]) / stats[k][1] for k in keys}
        z_rows.append(z)
    return z_rows


def _percentile_rank(values: list[float]) -> list[float]:
    """프로젝트 내 분포에서 각 값의 percentile rank를 0~100으로 반환.

    수식: pr(x) = (# of values ≤ x) / N * 100
    동률은 같은 순위가 된다.
    """
    n = len(values)
    if n == 0:
        return []
    sorted_values = sorted(values)
    ranks: list[float] = []
    for v in values:
        # bisect_right로 v 이하인 항목 개수 계산
        from bisect import bisect_right
        count = bisect_right(sorted_values, v)
        ranks.append(count / n * 100.0)
    return ranks


def _top_reasons(z: dict[str, float], weights: dict[str, float], top_n: int = 2) -> list[str]:
    """기여도가 큰 항목 이름 상위 N개를 반환 (z * weight 기준)."""
    contributions = [(k, z[k] * weights.get(k, 0.0)) for k in z]
    contributions.sort(key=lambda kv: -kv[1])
    return [k for k, _ in contributions[:top_n] if contributions[0][1] > 0]


def _module_of(file_path: str) -> str:
    """파일 경로의 최상위 디렉토리를 모듈 이름으로 사용한다.

    예: "OpenRA.Game/Network/UnitOrders.cs" → "OpenRA.Game"
    """
    if not file_path:
        return "(root)"
    parts = file_path.replace("\\", "/").split("/")
    if len(parts) < 2:
        return "(root)"
    return parts[0]


def _aggregate_files(
    class_scores: list[ClassScore],
    metrics: MetricsResult,
) -> list[FileScore]:
    by_path: dict[str, list[ClassScore]] = {}
    for cs in class_scores:
        by_path.setdefault(cs.file_path, []).append(cs)

    file_loc: dict[str, int] = {}
    for c in metrics.classes:
        # 클래스의 LOC 합으로 파일 LOC를 근사한다 (정확하진 않지만 ranking에는 충분).
        file_loc[c.file_path] = file_loc.get(c.file_path, 0)

    files: list[FileScore] = []
    for path, group in by_path.items():
        si_values = [cs.si for cs in group]
        files.append(FileScore(
            file_path=path,
            module=_module_of(path),
            si_mean=statistics.fmean(si_values),
            si_max=max(si_values),
            grade=_grade(max(si_values)),
            class_count=len(group),
            loc=0,
        ))
    return files


def _aggregate_modules(file_scores: list[FileScore]) -> list[ModuleScore]:
    by_module: dict[str, list[FileScore]] = {}
    for fs in file_scores:
        by_module.setdefault(fs.module, []).append(fs)

    modules: list[ModuleScore] = []
    for mod, group in by_module.items():
        si_values = [fs.si_max for fs in group]
        modules.append(ModuleScore(
            module=mod,
            si_mean=statistics.fmean(si_values),
            si_max=max(si_values),
            grade=_grade(statistics.fmean(si_values)),
            class_count=sum(fs.class_count for fs in group),
            file_count=len(group),
        ))
    return modules


# ---------------------------------------------------------------------------
# 직렬화
# ---------------------------------------------------------------------------


def scoring_to_dict(result: ScoringResult) -> dict[str, Any]:
    return {
        "schema_version": "si-0.1",
        "weights": result.weights,
        "total_classes": result.total_classes,
        "total_methods": result.total_methods,
        "grade_distribution": result.grade_distribution,
        "class_scores": [
            {
                "fqn": cs.fqn,
                "name": cs.name,
                "file_path": cs.file_path,
                "module": cs.module,
                "start_line": cs.start_line,
                "end_line": cs.end_line,
                "kind": cs.kind,
                "raw": {k: round(v, 4) for k, v in cs.raw.items()},
                "z": {k: round(v, 4) for k, v in cs.z.items()},
                "raw_score": round(cs.raw_score, 4),
                "si": round(cs.si, 2),
                "grade": cs.grade,
                "top_reasons": cs.top_reasons,
            }
            for cs in result.class_scores
        ],
        "file_scores": [
            {
                "file_path": fs.file_path,
                "module": fs.module,
                "si_mean": round(fs.si_mean, 2),
                "si_max": round(fs.si_max, 2),
                "grade": fs.grade,
                "class_count": fs.class_count,
            }
            for fs in result.file_scores
        ],
        "module_scores": [
            {
                "module": ms.module,
                "si_mean": round(ms.si_mean, 2),
                "si_max": round(ms.si_max, 2),
                "grade": ms.grade,
                "class_count": ms.class_count,
                "file_count": ms.file_count,
            }
            for ms in result.module_scores
        ],
    }
