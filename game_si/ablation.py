"""사전 지정 지표 제거 실험. 결과에 맞춘 가중치 탐색은 수행하지 않는다."""
from __future__ import annotations

import math
import statistics
from collections import defaultdict

from .si import DEFAULT_WEIGHTS_STATIC, _normalize_weights, _percentile_rank, _z_score_rows
from .tune import CaseData, _exclusion_reason
from .validate import spearman


def file_scores_for_weights(case: CaseData, weights: dict[str, float]) -> dict[str, float]:
    """전체 클래스 표준화 → 가중합 → 백분위 반올림 → 파일 최대값."""
    raw = case.class_raw_by_file
    if raw is None:
        raw = {f: [row] for f, row in case.raw_by_file.items()}
    paths = [f for f, rows in raw.items() for _ in rows]
    z = _z_score_rows([row for rows in raw.values() for row in rows])
    w = _normalize_weights(weights, allowed=set(DEFAULT_WEIGHTS_STATIC))
    scores = _percentile_rank([sum(w[k] * row[k] for k in w) for row in z])
    out: dict[str, float] = {}
    for path, score in zip(paths, scores):
        out[path] = max(out.get(path, 0), round(score, 2))
    return out


def run_ablation(cases: list[CaseData], top_n: int = 30) -> dict:
    if top_n < 1 or len({c.name for c in cases}) != len(cases):
        raise ValueError("Top-N은 양수이며 케이스 이름은 중복되지 않아야 합니다.")
    excluded = {c.name: reason for c in cases if (reason := _exclusion_reason(c))}
    eligible = [c for c in cases if c.name not in excluded]
    if not eligible:
        raise ValueError("평가 가능한 케이스가 없습니다.")
    variants = {"default": dict(DEFAULT_WEIGHTS_STATIC)}
    variants.update({f"without_{k}": {key: value for key, value in DEFAULT_WEIGHTS_STATIC.items() if key != k}
                     for k in DEFAULT_WEIGHTS_STATIC})
    variants["cc_coupling_only"] = {k: DEFAULT_WEIGHTS_STATIC[k] for k in ('cc', 'coupling')}
    baseline = {c.name: file_scores_for_weights(c, DEFAULT_WEIGHTS_STATIC) for c in eligible}
    output = {}
    for name, weights in variants.items():
        rows, groups = {}, defaultdict(list)
        for case in eligible:
            scores = file_scores_for_weights(case, weights)
            matched = sorted(set(scores) & set(case.bugfix_by_file))
            rho, _ = spearman([scores[f] for f in matched], [case.bugfix_by_file[f] for f in matched])
            rho = rho if math.isfinite(rho) else None
            top = sorted(matched, key=lambda f: (-scores[f], f))[:top_n]
            default_top = sorted(matched, key=lambda f: (-baseline[case.name][f], f))[:top_n]
            left, right = set(top), set(default_top)
            groups[case.project_group or case.name].append(rho)
            rows[case.name] = dict(rho=rho, matched_files=len(matched),
                                   reason=None if rho is not None else "constant scores: correlation undefined",
                                   top_files=top, actual_top_n=len(top),
                                   top_jaccard_vs_default=len(left & right) / len(left | right),
                                   added_top_files=sorted(left-right), removed_top_files=sorted(right-left))
        group_means = {g: statistics.fmean(values) if all(v is not None for v in values) else None
                       for g, values in groups.items()}
        mean = statistics.fmean(group_means.values()) if all(v is not None for v in group_means.values()) else None
        output[name] = dict(weights=_normalize_weights(weights), cases=rows,
                            project_mean_rho=group_means, grouped_mean_rho=mean)
    return dict(schema_version="ablation-0.1", top_n=top_n,
                protocol="Fixed default weights; remove one metric and renormalize; CC+coupling control. "
                         "Identical matched file sets; equal original-project weight; undefined variants are not dropped.",
                interpretation="Historical bug-fix message proxy association, not future defect prediction or causal evidence. "
                               "Top-N ties use path order; no data-driven weight selection.",
                excluded_cases=excluded, variants=output)
