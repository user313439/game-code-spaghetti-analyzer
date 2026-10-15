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

**LOPO**: 원본 프로젝트를 통째로 제외한다. 같은 프로젝트의 여러 모듈은
train/hold-out에 나뉘지 않는다. 프로젝트별 평균 ρ를 동일 가중 평균한다.

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
from .si import _z_score_rows, _percentile_rank, _normalize_weights


WEIGHT_KEYS = ("cc", "coupling", "dependency_cycle", "global_state", "game_loop_centrality")

# 5차원 grid search. 각 weight 는 0.05 ~ 0.40 (step 0.05) 중에서.
GRID_STEPS = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40)


@dataclass
class CaseData:
    """튜닝에 사용할 케이스 데이터.

    raw_by_file : 파일 목록 및 단일 클래스 입력의 raw metric
    bugfix_by_file : 파일 단위 bug-fix 카운트 (validate 산출물)
    class_raw_by_file : 실제 scoring의 클래스별 raw metric (집계 전)
    입력 데이터는 생성 후 변경하지 않는다 (표준화 결과를 재사용).
    """
    name: str
    raw_by_file: dict[str, dict[str, float]]
    bugfix_by_file: dict[str, int]
    project_group: str | None = None
    class_raw_by_file: dict[str, list[dict[str, float]]] | None = None
    _z_by_file: dict[str, list[dict[str, float]]] | None = field(default=None, init=False, repr=False)
    raw_precision: str = "full precision (in-memory)"


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
    case_projects: dict[str, str] = field(default_factory=dict)
    project_folds: list[dict] = field(default_factory=list)
    exclusion_reasons: dict[str, str] = field(default_factory=dict)
    input_precision: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 데이터 로더
# ---------------------------------------------------------------------------


def load_case_data(
    case_name: str, scoring_path: Path, validation_path: Path,
    project_group: str | None = None,
) -> CaseData:
    """`scoring.json` (raw 메트릭) + `validation.json` (bug-fix 카운트) 로 케이스 데이터 구성.

    클래스 raw를 보존하여 본 분석과 동일한 순서로 점수를 재계산한다.
    bug-fix count는 validation.json의 file_rows 또는 rows에서 추출.
    프로젝트 그룹은 명시값 또는 validation의 저장소 경로에서 결정한다.
    """
    with open(scoring_path, "r", encoding="utf-8") as f:
        scoring = json.load(f)
    with open(validation_path, "r", encoding="utf-8") as f:
        validation = json.load(f)

    # 파일 단위 raw — 클래스 raw 의 max (파일 대표값)
    raw_by_file: dict[str, dict[str, float]] = {}
    class_raw_by_file: dict[str, list[dict[str, float]]] = {}
    for c in scoring.get("class_scores", []):
        fp = c["file_path"].replace("\\", "/")
        raw = c.get("raw_exact", c.get("raw", {}))
        class_raw_by_file.setdefault(fp, []).append({
            k: float(raw.get(k, 0.0)) for k in WEIGHT_KEYS
        })
        cur = raw_by_file.setdefault(fp, {k: 0.0 for k in WEIGHT_KEYS})
        for k in WEIGHT_KEYS:
            v = float(raw.get(k, 0.0))
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
            bugfix_by_file[fp] = max(bugfix_by_file.get(fp, 0), cnt)

    if project_group is None:
        repo = str(validation.get("repo_path", "")).replace("\\", "/").rstrip("/")
        project_group = repo.rsplit("/", 1)[-1] if repo else case_name
    case = CaseData(case_name, raw_by_file, bugfix_by_file, project_group, class_raw_by_file)
    case.raw_precision = ("full precision (raw_exact)" if all(
        "raw_exact" in c for c in scoring.get("class_scores", [])
    ) else "legacy rounded raw (approximate)")
    return case


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

    모든 클래스 기준 표준화 → 가중합 → 백분위(소수 둘째 자리) → 파일 최대값.
    저장된 scoring.json을 사용하는 validate와 동일한 계산·반올림을 적용한다.
    """
    matched_files = [f for f in case.raw_by_file if f in case.bugfix_by_file]
    if len(matched_files) < MIN_SAMPLES_FOR_CORRELATION:
        return float("nan")
    if case._z_by_file is None:
        raw = case.class_raw_by_file
        if raw is None:
            raw = {f: [row] for f, row in case.raw_by_file.items()}
        paths = [f for f, rows in raw.items() for _ in rows]
        z_rows = _z_score_rows([row for rows in raw.values() for row in rows])
        case._z_by_file = {}
        for path, z in zip(paths, z_rows):
            case._z_by_file.setdefault(path, []).append(z)
    w = _normalize_weights(weights)
    class_paths = [f for f, rows in case._z_by_file.items() for _ in rows]
    raw_scores = [sum(w[k] * z[k] for k in w)
                  for rows in case._z_by_file.values() for z in rows]
    file_scores: dict[str, float] = {}
    for path, score in zip(class_paths, _percentile_rank(raw_scores)):
        file_scores[path] = max(file_scores.get(path, 0.0), round(score, 2))
    si_scores = [file_scores[f] for f in matched_files]
    bug = [float(case.bugfix_by_file[f]) for f in matched_files]
    rho, _ = spearman(si_scores, bug)
    return rho


def matched_files_count(case: CaseData) -> int:
    """case 의 raw_by_file 중 bug-fix 데이터가 있는 파일 수."""
    return sum(1 for f in case.raw_by_file if f in case.bugfix_by_file)


def _exclusion_reason(case: CaseData) -> str | None:
    """기본값과 공정하게 비교할 수 있는 사례를 사전에 결정한다."""
    from .si import DEFAULT_WEIGHTS_STATIC
    matched = [f for f in case.raw_by_file if f in case.bugfix_by_file]
    if len(matched) < MIN_SAMPLES_FOR_CORRELATION:
        return "insufficient samples (n < 5 files with bugfix data)"
    if len({case.bugfix_by_file[f] for f in matched}) < 2:
        return "constant bug-fix counts"
    rho = evaluate_weights(case, DEFAULT_WEIGHTS_STATIC)
    if rho != rho:
        return "undefined default correlation (constant scores)"
    return None


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
    evaluation_cache: dict | None = None,
) -> tuple[dict[str, float], float, int]:
    """주어진 케이스들의 평균 ρ 최대화 weight 탐색. (best_weights, best_score, n_evaluated)"""
    best_w = None
    best_score = float("-inf")
    n = 0
    for w in _candidate_weights():
        rhos = {}
        for c in cases:
            key = (c.name, tuple(w[k] for k in WEIGHT_KEYS))
            if evaluation_cache is not None and key in evaluation_cache:
                rho = evaluation_cache[key]
            else:
                rho = evaluate_weights(c, w)
                if evaluation_cache is not None:
                    evaluation_cache[key] = rho
            rhos[c.name] = rho
        valid = [r for r in rhos.values() if r == r]
        if len(valid) != len(cases):
            continue
        score = rho_aggregator(valid) if rho_aggregator else _project_mean(cases, rhos)
        n += 1
        if score > best_score:
            best_score = score
            best_w = w
    if best_w is None:
        raise ValueError("No valid weight candidates with an evaluable correlation.")
    return best_w, best_score, n


# ---------------------------------------------------------------------------
# LOPO
# ---------------------------------------------------------------------------


def _project_mean(cases: list[CaseData], rhos: dict[str, float]) -> float:
    groups: dict[str, list[float]] = {}
    for case in cases:
        rho = rhos[case.name]
        if rho == rho:
            groups.setdefault(case.project_group or case.name, []).append(rho)
    means = [sum(vals) / len(vals) for vals in groups.values()]
    return sum(means) / len(means) if means else float("nan")


def lopo_cross_validation(
    cases: list[CaseData], evaluation_cache: dict | None = None,
    fold_details: list[dict] | None = None,
) -> tuple[float, dict[str, float]]:
    """같은 원본 프로젝트의 모든 모듈을 함께 hold-out한다.

    Returns
    -------
    (avg_holdout_rho, per_case_holdout_rho)
    """
    holdout: dict[str, float] = {}
    valid_cases = [c for c in cases if _exclusion_reason(c) is None]
    projects = list(dict.fromkeys(c.project_group or c.name for c in valid_cases))
    if len(projects) < 2:
        raise ValueError("LOPO requires at least two projects with evaluable correlations.")
    for project in projects:
        train = [c for c in valid_cases if (c.project_group or c.name) != project]
        held = [c for c in valid_cases if (c.project_group or c.name) == project]
        best_w, _, _ = find_best_weights(train, evaluation_cache=evaluation_cache)
        rhos = {c.name: evaluate_weights(c, best_w) for c in held}
        if any(v != v for v in rhos.values()):
            raise ValueError(f"LOPO hold-out project {project} has an undefined module correlation.")
        holdout[project] = _project_mean(held, rhos)
        if holdout[project] != holdout[project]:
            raise ValueError(f"LOPO hold-out project {project} has no evaluable correlation.")
        if fold_details is not None:
            fold_details.append({
                "project": project, "train_cases": [c.name for c in train],
                "holdout_cases": [c.name for c in held], "weights": best_w,
                "per_case_holdout_rho": {k: round(v, 4) if v == v else None for k, v in rhos.items()},
                "holdout_rho": round(holdout[project], 4),
            })
    valid = [v for v in holdout.values() if v == v]
    return (sum(valid) / len(valid)) if valid else float("nan"), holdout


# ---------------------------------------------------------------------------
# 메인 진입점
# ---------------------------------------------------------------------------


def run_tune(cases: list[CaseData]) -> TuneResult:
    from .si import DEFAULT_WEIGHTS_STATIC

    default_w = dict(DEFAULT_WEIGHTS_STATIC)
    if len({c.name for c in cases}) != len(cases):
        raise ValueError("Case names must be unique.")
    cache: dict = {}
    # default 평가
    default_per_case = {c.name: evaluate_weights(c, default_w) for c in cases}
    exclusions = {c.name: reason for c in cases if (reason := _exclusion_reason(c)) is not None}
    valid_cases = [c for c in cases if c.name not in exclusions]
    if len({c.project_group or c.name for c in valid_cases}) < 2:
        raise ValueError("LOPO requires at least two projects with evaluable correlations.")
    # tuned 평가 — 전체 케이스로 최적
    tuned_w, tuned_avg, n_eval = find_best_weights(valid_cases, evaluation_cache=cache)
    tuned_per_case = {c.name: (float("nan") if c.name in exclusions else evaluate_weights(c, tuned_w))
                      for c in cases}
    # LOPO
    lopo_default = _project_mean(cases, default_per_case)
    folds: list[dict] = []
    lopo_tuned, _ = lopo_cross_validation(cases, evaluation_cache=cache, fold_details=folds)

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
        case_projects={c.name: c.project_group or c.name for c in cases},
        project_folds=folds,
        exclusion_reasons=exclusions,
        input_precision={c.name: c.raw_precision for c in cases},
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
        "schema_version": "tune-0.3",
        "scoring_method": "class z-score -> weighted sum -> percentile (2 decimals) -> file max",
        "validation_unit": "project",
        "aggregation": "equal-weight mean of within-project mean correlations",
        "case_projects": r.case_projects,
        "project_folds": r.project_folds,
        "input_precision": r.input_precision,
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
        "excluded_reason": "see per-case exclusion_reasons",
        "exclusion_reasons": r.exclusion_reasons,
        "lopo_default_rho": round(r.lopo_default_rho, 4),
        "lopo_tuned_rho": round(r.lopo_tuned_rho, 4),
        "lopo_note": "all modules of a held-out project are excluded from training; small cases skipped",
    }


def format_summary(r: TuneResult) -> str:
    import math
    out: list[str] = []
    out.append("=== Weight Tuning (plan §4.6) ===")
    out.append("scoring: class z-score -> percentile (2 decimals) -> file maximum")
    out.append("aggregation: equal project weight; modules of one project held out together")
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
                f"  {name:<26} excluded: {r.exclusion_reasons.get(name, 'undefined correlation')}"
            )
            excluded.append(name)
            continue
        diff = t - d
        out.append(f"  {name:<26} {d:>+10.4f} {t:>+10.4f} {diff:>+8.4f}")
    out.append("")
    if excluded:
        out.append(
            "* excluded 케이스는 표본 부족 또는 상수값 때문에 상관을 계산할 수 없다. "
            "각 사례의 제외 이유를 위에 표시하며 프로젝트 평균과 학습에서 제외한다."
        )
        out.append("")
    out.append("LOPO (Leave-One-Project-Out) cross-validation [excluded 케이스 제외]:")
    out.append(f"  default (project mean ρ):     {r.lopo_default_rho:+.4f}")
    out.append(f"  tuned (hold-out ρ avg):       {r.lopo_tuned_rho:+.4f}")
    delta = r.lopo_tuned_rho - r.lopo_default_rho
    out.append(f"  Δ (tuned − default):          {delta:+.4f}")
    for fold in r.project_folds:
        out.append(f"  held out {fold['project']}: ρ={fold['holdout_rho']:+.4f}; "
                   + " ".join(f"{k}={v:.2f}" for k, v in fold["weights"].items()))
    out.append("")
    out.append("평균 차이는 기술 통계이며, 개선 또는 동등성의 통계적 유의성 검정은 수행하지 않았다.")
    out.append("전체 데이터로 선택한 tuned 가중치의 per-case 값은 학습 결과이며, fold별 hold-out 값과 구분한다.")
    return "\n".join(out)
