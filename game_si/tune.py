"""W14 (확장) — 가중치 튜닝 + Leave-One-Project-Out 교차 검증.

plan §4.6 의 가중치 운용 방식을 구현한다.

1. 각 가중치 후보에 대해 G-SI-Static 을 산출한다 — 본 구현은 이미 산출된
   `scoring.json` 의 raw 메트릭을 재사용해 z-score → percentile rank 재계산
   만 수행하므로 빠르다 (수 ms / 케이스).
2. 동일 분석 단위(파일 단위)의 bug-fix 커밋 빈도와의 Spearman 순위 상관계수를
   계산한다.
3. Leave-One-Project-Out 교차 검증으로 과적합을 완화한다.

**search 전략**: 5 차원 가중치를 0.05 step grid 로 탐색. 각 weight ∈ [0.05, 0.40],
합 = 1 제약. raw point 가 ~3000 개 정도라 평가는 빠르다.

**LOPO**: K=4 케이스. 각 폴드에서 3 케이스로 평균 ρ 최대 가중치 찾기 → 빠진 1
케이스에서 그 가중치로 ρ 측정. 4 폴드 평균을 LOPO 성능으로 보고.

본 모듈은 scipy 의존성 없이 표준 라이브러리만으로 동작한다 (Spearman 은
`validate.spearman` 재사용).
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .validate import spearman


WEIGHT_KEYS = ("cc", "coupling", "dependency_cycle", "global_state", "game_loop_centrality")

# 5차원 grid search. 각 weight 는 0.05 ~ 0.40 (step 0.05) 중에서.
GRID_STEPS = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40)


@dataclass
class CaseData:
    """튜닝에 사용할 케이스 데이터.

    raw_by_file : 파일 단위 raw metric (cc/coupling/...)
    bugfix_by_file : 파일 단위 bug-fix 카운트 (validate 산출물)
    """
    name: str
    raw_by_file: dict[str, dict[str, float]]
    bugfix_by_file: dict[str, int]


@dataclass
class TuneResult:
    default_weights: dict[str, float]
    tuned_weights: dict[str, float]
    per_case_default_rho: dict[str, float]
    per_case_tuned_rho: dict[str, float]
    lopo_default_rho: float
    lopo_tuned_rho: float
    grid_size: int
    n_evaluated: int


# ---------------------------------------------------------------------------
# 데이터 로더
# ---------------------------------------------------------------------------


def load_case_data(case_name: str, scoring_path: Path, validation_path: Path) -> CaseData:
    """`scoring.json` (raw 메트릭) + `validation.json` (bug-fix 카운트) 로 케이스 데이터 구성.

    파일 단위로 집계: scoring.json 의 class_scores 를 file_path 별로 묶어
    raw 메트릭의 max 값(파일 대표값) 을 사용. bug-fix count 는 validation.json
    의 file_rows 또는 rows 에서 추출.
    """
    with open(scoring_path, "r", encoding="utf-8") as f:
        scoring = json.load(f)
    with open(validation_path, "r", encoding="utf-8") as f:
        validation = json.load(f)

    # 파일 단위 raw — 클래스 raw 의 max (파일 대표값)
    raw_by_file: dict[str, dict[str, float]] = {}
    for c in scoring.get("class_scores", []):
        fp = c["file_path"].replace("\\", "/")
        cur = raw_by_file.setdefault(fp, {k: 0.0 for k in WEIGHT_KEYS})
        for k in WEIGHT_KEYS:
            v = float(c.get("raw", {}).get(k, 0.0))
            if v > cur[k]:
                cur[k] = v

    # bug-fix count by file
    bugfix_by_file: dict[str, int] = {}
    for fr in validation.get("file_rows", []):
        fp = fr["file_path"].replace("\\", "/")
        bugfix_by_file[fp] = int(fr.get("bugfix_count", 0))
    # fallback: rows (class-level) — 파일 기준 max
    if not bugfix_by_file:
        for row in validation.get("rows", []):
            fp = row["file_path"].replace("\\", "/")
            cnt = int(row.get("bugfix_count", 0))
            if cnt > bugfix_by_file.get(fp, 0):
                bugfix_by_file[fp] = cnt

    return CaseData(name=case_name, raw_by_file=raw_by_file, bugfix_by_file=bugfix_by_file)


# ---------------------------------------------------------------------------
# 평가 — 주어진 weight 로 파일 단위 G-SI 산출 + Spearman ρ 측정
# ---------------------------------------------------------------------------


def _zscore_columns(matrix: list[dict[str, float]]) -> list[dict[str, float]]:
    if not matrix:
        return []
    keys = list(matrix[0].keys())
    stats: dict[str, tuple[float, float]] = {}
    for k in keys:
        vals = [r[k] for r in matrix]
        m = sum(vals) / len(vals)
        var = sum((v - m) ** 2 for v in vals) / len(vals)
        sd = var ** 0.5 or 1.0
        stats[k] = (m, sd)
    out = []
    for r in matrix:
        out.append({k: (r[k] - stats[k][0]) / stats[k][1] for k in keys})
    return out


MIN_SAMPLES_FOR_CORRELATION = 5  # n<5 인 케이스는 평가 불가 (insufficient samples)


def evaluate_weights(case: CaseData, weights: dict[str, float]) -> float:
    """주어진 가중치로 file 단위 G-SI(raw_score) 산출 후 bug-fix 와 Spearman ρ.

    matched files 가 ``MIN_SAMPLES_FOR_CORRELATION`` (5) 미만이면 NaN.
    LOPO 평균 등 후속 집계에서는 NaN 케이스를 명시적으로 제외하며, 텍스트
    요약에서는 "excluded: insufficient samples (n<5)" 로 표시한다.

    Percentile rank 변환은 단조 함수라 Spearman 값에는 영향 없음 → 생략.
    """
    matched_files = [f for f in case.raw_by_file if f in case.bugfix_by_file]
    if len(matched_files) < MIN_SAMPLES_FOR_CORRELATION:
        return float("nan")
    rows = [case.raw_by_file[f] for f in matched_files]
    z_rows = _zscore_columns(rows)
    si_scores = [sum(weights[k] * z[k] for k in WEIGHT_KEYS) for z in z_rows]
    bug = [float(case.bugfix_by_file[f]) for f in matched_files]
    rho, _ = spearman(si_scores, bug)
    return rho


def matched_files_count(case: CaseData) -> int:
    """case 의 raw_by_file 중 bug-fix 데이터가 있는 파일 수."""
    return sum(1 for f in case.raw_by_file if f in case.bugfix_by_file)


# ---------------------------------------------------------------------------
# Grid search
# ---------------------------------------------------------------------------


def _candidate_weights() -> Iterable[dict[str, float]]:
    """5 차원 가중치 grid. 합 = 1 (±0.001 허용)."""
    for combo in itertools.product(GRID_STEPS, repeat=len(WEIGHT_KEYS)):
        total = sum(combo)
        if abs(total - 1.0) > 1e-9:
            continue
        yield dict(zip(WEIGHT_KEYS, combo))


def find_best_weights(
    cases: list[CaseData],
    rho_aggregator=None,
) -> tuple[dict[str, float], float, int]:
    """주어진 케이스들의 평균 ρ 최대화 weight 탐색. (best_weights, best_score, n_evaluated)"""
    if rho_aggregator is None:
        rho_aggregator = lambda rhos: sum(rhos) / len(rhos) if rhos else float("nan")

    best_w = None
    best_score = float("-inf")
    n = 0
    for w in _candidate_weights():
        rhos = [evaluate_weights(c, w) for c in cases]
        rhos = [r for r in rhos if r == r]  # NaN 제거
        if not rhos:
            continue
        score = rho_aggregator(rhos)
        n += 1
        if score > best_score:
            best_score = score
            best_w = w
    return best_w or {k: 1.0 / len(WEIGHT_KEYS) for k in WEIGHT_KEYS}, best_score, n


# ---------------------------------------------------------------------------
# LOPO
# ---------------------------------------------------------------------------


def lopo_cross_validation(cases: list[CaseData]) -> tuple[float, dict[str, float]]:
    """Leave-One-Project-Out: K=len(cases). 매 폴드에서 K-1 으로 best weight 찾고,
    빠진 케이스에서 ρ 측정. 모든 폴드의 hold-out ρ 평균을 반환.

    Returns
    -------
    (avg_holdout_rho, per_case_holdout_rho)
    """
    holdout: dict[str, float] = {}
    for i, held in enumerate(cases):
        train = [c for j, c in enumerate(cases) if j != i]
        best_w, _, _ = find_best_weights(train)
        rho = evaluate_weights(held, best_w)
        holdout[held.name] = rho
    valid = [v for v in holdout.values() if v == v]
    return (sum(valid) / len(valid)) if valid else float("nan"), holdout


# ---------------------------------------------------------------------------
# 메인 진입점
# ---------------------------------------------------------------------------


def run_tune(cases: list[CaseData]) -> TuneResult:
    from .si import DEFAULT_WEIGHTS_STATIC

    default_w = dict(DEFAULT_WEIGHTS_STATIC)
    # default 평가
    default_per_case = {c.name: evaluate_weights(c, default_w) for c in cases}
    # tuned 평가 — 전체 케이스로 최적
    tuned_w, tuned_avg, n_eval = find_best_weights(cases)
    tuned_per_case = {c.name: evaluate_weights(c, tuned_w) for c in cases}
    # LOPO
    lopo_default_rhos = list(default_per_case.values())
    lopo_default = sum(r for r in lopo_default_rhos if r == r) / max(1, sum(1 for r in lopo_default_rhos if r == r))
    lopo_tuned, _ = lopo_cross_validation(cases)

    # grid_size 추정
    grid_total = sum(1 for _ in _candidate_weights())

    return TuneResult(
        default_weights=default_w,
        tuned_weights=tuned_w,
        per_case_default_rho=default_per_case,
        per_case_tuned_rho=tuned_per_case,
        lopo_default_rho=lopo_default,
        lopo_tuned_rho=lopo_tuned,
        grid_size=grid_total,
        n_evaluated=n_eval,
    )


# ---------------------------------------------------------------------------
# 직렬화 / 요약
# ---------------------------------------------------------------------------


def to_dict(r: TuneResult) -> dict:
    import math
    excluded = [
        name for name in r.per_case_default_rho
        if math.isnan(r.per_case_default_rho[name])
        or math.isnan(r.per_case_tuned_rho.get(name, float("nan")))
    ]
    return {
        "schema_version": "tune-0.2",
        "grid_size": r.grid_size,
        "n_evaluated": r.n_evaluated,
        "min_samples_for_correlation": MIN_SAMPLES_FOR_CORRELATION,
        "default_weights": r.default_weights,
        "tuned_weights": r.tuned_weights,
        "per_case_default_rho": {
            k: (None if math.isnan(v) else round(v, 4))
            for k, v in r.per_case_default_rho.items()
        },
        "per_case_tuned_rho": {
            k: (None if math.isnan(v) else round(v, 4))
            for k, v in r.per_case_tuned_rho.items()
        },
        "excluded_cases": excluded,
        "excluded_reason": "insufficient samples (n < 5 files with bugfix data)",
        "lopo_default_rho": round(r.lopo_default_rho, 4),
        "lopo_tuned_rho": round(r.lopo_tuned_rho, 4),
        "lopo_note": "excluded cases are skipped in LOPO averages",
    }


def format_summary(r: TuneResult) -> str:
    import math
    out: list[str] = []
    out.append("=== Weight Tuning (plan §4.6) ===")
    out.append(f"grid size: {r.grid_size:,} candidates")
    out.append(f"evaluated: {r.n_evaluated:,}")
    out.append("")
    out.append("default weights: " + " ".join(f"{k}={v:.2f}" for k, v in r.default_weights.items()))
    out.append("tuned weights:   " + " ".join(f"{k}={v:.2f}" for k, v in r.tuned_weights.items()))
    out.append("")
    out.append(f"per-case file-level Spearman ρ (vs file bug-fix count, n≥{MIN_SAMPLES_FOR_CORRELATION} required):")
    out.append(f"  {'case':<26} {'default':>10} {'tuned':>10} {'Δ':>8}")
    excluded: list[str] = []
    for name in r.per_case_default_rho:
        d = r.per_case_default_rho[name]
        t = r.per_case_tuned_rho.get(name, float("nan"))
        if math.isnan(d) or math.isnan(t):
            out.append(
                f"  {name:<26} {'excluded: insufficient samples (n<5)':>42}"
            )
            excluded.append(name)
            continue
        diff = t - d
        out.append(f"  {name:<26} {d:>+10.4f} {t:>+10.4f} {diff:>+8.4f}")
    out.append("")
    if excluded:
        out.append(
            "* excluded 케이스는 분석 가능한 파일 수가 5 개 미만이라 Spearman "
            "상관계수가 통계적으로 평가 불가능하다. 단일 진입점 프로그램 "
            "구조에서 G-SI 동작을 보여주는 표본 부족 사례로 별도 표시한다."
        )
        out.append("")
    out.append("LOPO (Leave-One-Project-Out) cross-validation [excluded 케이스 제외]:")
    out.append(f"  default (avg of per-case ρ):  {r.lopo_default_rho:+.4f}")
    out.append(f"  tuned (hold-out ρ avg):       {r.lopo_tuned_rho:+.4f}")
    delta = r.lopo_tuned_rho - r.lopo_default_rho
    out.append(f"  Δ (tuned − default):          {delta:+.4f}")
    out.append("")
    if delta > 0.01:
        out.append("→ tuned weights 가 LOPO 검증에서 default 대비 개선됨.")
    elif delta < -0.01:
        out.append("→ tuned weights 가 LOPO 에서 overfitting 신호 (개선 못 함).")
    else:
        out.append("→ tuned weights 의 LOPO 성능이 default 와 사실상 동일.")
    return "\n".join(out)
