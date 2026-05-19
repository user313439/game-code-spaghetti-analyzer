"""Phase B — 외부 정적 분석 도구(Lizard)와 G-SI hotspot 비교 (W13).

`docs/plan_final_draft.md` §7.2 의 Phase B 핵심 정량 비교를 수행한다. Lizard 는
C / C++ / C# / Java 등 다양한 언어를 지원하는 경량 정적 분석 도구로, 함수
단위의 Cyclomatic Complexity 와 LOC, parameter count 를 제공한다.

본 모듈의 산출물:

* **Hotspot Top-N Jaccard**: G-SI 파일 단위 상위 N 과 Lizard 파일 단위 (max CC)
  상위 N 의 집합 유사도.
* **Spearman 상관계수**: 파일 단위 G-SI vs Lizard max CC 의 순위 상관.
* **G-SI 단독 hotspot 사례**: G-SI top-N 에 있지만 Lizard top-N 에 없는 파일.
  plan §7.2 에서 요구하는 "추가 식별 케이스 정성 분석" 의 입력.
* **Lizard 단독 hotspot 사례**: 반대 방향. G-SI 가 놓친 케이스 (있다면).
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .validate import spearman


@dataclass
class LizardFileStat:
    file_path: str          # input root 기준 상대 경로
    max_cc: int
    avg_cc: float
    total_nloc: int
    func_count: int
    max_params: int
    top_func: str            # max_cc 함수 이름


@dataclass
class CompareTopRow:
    rank_gsi: int | None
    rank_lizard: int | None
    file_path: str
    si: float
    grade: str
    lizard_max_cc: int
    lizard_nloc: int


@dataclass
class CompareResult:
    project: str
    scoring_path: str
    analyzed_path: str
    files_analyzed_by_us: int
    files_analyzed_by_lizard: int
    files_matched: int
    top_n: int
    jaccard: dict[int, float]                       # {top_n: jaccard}
    spearman_si_vs_lizard_cc: float
    spearman_p: float | None
    gsi_only_topN: list[CompareTopRow]              # G-SI 만 top-N (정성 분석용)
    lizard_only_topN: list[CompareTopRow]           # Lizard 만 top-N
    common_topN: list[CompareTopRow]                # 양쪽 모두 top-N
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Lizard 호출
# ---------------------------------------------------------------------------


def run_lizard(input_path: Path, root_for_relpath: Path | None = None) -> dict[str, LizardFileStat]:
    """디렉토리를 Lizard 로 분석하고 file_path → LizardFileStat 매핑을 반환한다.

    file_path 는 `root_for_relpath` (기본: input_path) 기준 POSIX 상대경로다.
    """
    import lizard

    root = (root_for_relpath or input_path).resolve()
    input_path = input_path.resolve()

    by_file: dict[str, dict] = {}

    for r in lizard.analyze([str(input_path)]):
        abs_path = Path(r.filename).resolve()
        try:
            relp = abs_path.relative_to(root).as_posix()
        except ValueError:
            relp = abs_path.name
        cur = by_file.setdefault(relp, {
            "max_cc": 0, "cc_sum": 0.0, "func_count": 0, "nloc": 0,
            "max_params": 0, "top_func": "",
        })
        cur["nloc"] = r.nloc
        for func in r.function_list:
            cur["func_count"] += 1
            cur["cc_sum"] += func.cyclomatic_complexity
            if func.cyclomatic_complexity > cur["max_cc"]:
                cur["max_cc"] = func.cyclomatic_complexity
                cur["top_func"] = func.name
            if func.parameter_count > cur["max_params"]:
                cur["max_params"] = func.parameter_count

    out: dict[str, LizardFileStat] = {}
    for relp, d in by_file.items():
        avg = (d["cc_sum"] / d["func_count"]) if d["func_count"] else 0.0
        out[relp] = LizardFileStat(
            file_path=relp,
            max_cc=int(d["max_cc"]),
            avg_cc=avg,
            total_nloc=int(d["nloc"]),
            func_count=int(d["func_count"]),
            max_params=int(d["max_params"]),
            top_func=d["top_func"],
        )
    return out


# ---------------------------------------------------------------------------
# 비교 로직
# ---------------------------------------------------------------------------


def run_comparison(
    scoring: dict,
    lizard_stats: dict[str, LizardFileStat],
    project: str,
    scoring_path: str,
    analyzed_path: str,
    top_ns: tuple[int, ...] = (5, 10, 30),
) -> CompareResult:
    """scoring.json 과 Lizard 결과를 비교한다.

    파일 단위 G-SI 는 plan §4.1 대표값 정의(파일 si_max) 를 따른다.
    """
    # 파일 단위 G-SI: si_max + 대표 grade. (scoring.json 의 file_scores 가 있긴 하나
    # 안정성을 위해 class_scores 에서 직접 max 한다 — file_scores 가 비어있을 수도 있음.)
    by_file_si: dict[str, dict] = defaultdict(lambda: {"si": 0.0, "grade": "A", "fqn": ""})
    for c in scoring.get("class_scores", []):
        fp = c["file_path"].replace("\\", "/")
        if c["si"] >= by_file_si[fp]["si"]:
            by_file_si[fp]["si"] = float(c["si"])
            by_file_si[fp]["grade"] = c.get("grade", "?")
            by_file_si[fp]["fqn"] = c.get("fqn", "")

    our_files = set(by_file_si.keys())
    liz_files = set(lizard_stats.keys())
    matched = our_files & liz_files

    # rank lists (descending by metric)
    gsi_ranking = sorted(matched, key=lambda f: -by_file_si[f]["si"])
    liz_ranking = sorted(matched, key=lambda f: -lizard_stats[f].max_cc)

    rank_gsi = {f: i + 1 for i, f in enumerate(gsi_ranking)}
    rank_liz = {f: i + 1 for i, f in enumerate(liz_ranking)}

    # Spearman: si vs liz_max_cc (matched 파일만)
    if matched:
        si_values = [by_file_si[f]["si"] for f in matched]
        liz_values = [float(lizard_stats[f].max_cc) for f in matched]
        rho, p = spearman(si_values, liz_values)
    else:
        rho, p = float("nan"), None

    # Top-N Jaccard
    jaccard: dict[int, float] = {}
    for n in top_ns:
        top_gsi = set(gsi_ranking[:n])
        top_liz = set(liz_ranking[:n])
        union = top_gsi | top_liz
        jaccard[n] = (len(top_gsi & top_liz) / len(union)) if union else 0.0

    # G-SI / Lizard 단독 top-N (top_ns 의 최댓값 기준)
    n_max = max(top_ns)
    top_gsi_set = set(gsi_ranking[:n_max])
    top_liz_set = set(liz_ranking[:n_max])

    def _row(file_path: str) -> CompareTopRow:
        stat = lizard_stats.get(file_path)
        return CompareTopRow(
            rank_gsi=rank_gsi.get(file_path),
            rank_lizard=rank_liz.get(file_path),
            file_path=file_path,
            si=by_file_si[file_path]["si"],
            grade=by_file_si[file_path]["grade"],
            lizard_max_cc=stat.max_cc if stat else 0,
            lizard_nloc=stat.total_nloc if stat else 0,
        )

    gsi_only = sorted(
        [f for f in top_gsi_set if f not in top_liz_set],
        key=lambda f: rank_gsi[f],
    )
    liz_only = sorted(
        [f for f in top_liz_set if f not in top_gsi_set],
        key=lambda f: rank_liz[f],
    )
    common = sorted(
        [f for f in top_gsi_set & top_liz_set],
        key=lambda f: rank_gsi[f],
    )

    notes: list[str] = []
    if len(matched) < min(len(our_files), len(liz_files)):
        notes.append(
            f"Lizard 가 분석한 {len(liz_files)} 파일 중 {len(matched)} 만 G-SI 분석 파일과 매칭. "
            f"분석기가 본문 .c/.cpp 만 보지만 Lizard 는 헤더도 함께 보는 등 범위 차이일 수 있음."
        )

    return CompareResult(
        project=project,
        scoring_path=scoring_path,
        analyzed_path=analyzed_path,
        files_analyzed_by_us=len(our_files),
        files_analyzed_by_lizard=len(liz_files),
        files_matched=len(matched),
        top_n=n_max,
        jaccard=jaccard,
        spearman_si_vs_lizard_cc=rho,
        spearman_p=p,
        gsi_only_topN=[_row(f) for f in gsi_only],
        lizard_only_topN=[_row(f) for f in liz_only],
        common_topN=[_row(f) for f in common],
        notes=notes,
    )


# ---------------------------------------------------------------------------
# 직렬화 / 요약
# ---------------------------------------------------------------------------


def to_dict(r: CompareResult) -> dict[str, Any]:
    def _row(rw: CompareTopRow) -> dict[str, Any]:
        return {
            "file_path": rw.file_path,
            "rank_gsi": rw.rank_gsi,
            "rank_lizard": rw.rank_lizard,
            "si": round(rw.si, 2),
            "grade": rw.grade,
            "lizard_max_cc": rw.lizard_max_cc,
            "lizard_nloc": rw.lizard_nloc,
        }

    return {
        "schema_version": "compare-0.1",
        "project": r.project,
        "scoring_path": r.scoring_path,
        "analyzed_path": r.analyzed_path,
        "files_analyzed_by_us": r.files_analyzed_by_us,
        "files_analyzed_by_lizard": r.files_analyzed_by_lizard,
        "files_matched": r.files_matched,
        "top_n": r.top_n,
        "jaccard_topN": {str(k): round(v, 4) for k, v in r.jaccard.items()},
        "spearman_si_vs_lizard_cc": (
            None if math.isnan(r.spearman_si_vs_lizard_cc)
            else round(r.spearman_si_vs_lizard_cc, 4)
        ),
        "spearman_p": None if r.spearman_p is None else round(r.spearman_p, 6),
        "gsi_only_topN": [_row(x) for x in r.gsi_only_topN],
        "lizard_only_topN": [_row(x) for x in r.lizard_only_topN],
        "common_topN": [_row(x) for x in r.common_topN],
        "notes": r.notes,
    }


def format_text_summary(r: CompareResult) -> str:
    lines: list[str] = []
    lines.append("=== Phase B: G-SI vs Lizard (max CC) ===")
    lines.append(f"project:       {r.project}")
    lines.append(f"scoring:       {r.scoring_path}")
    lines.append(f"analyzed_path: {r.analyzed_path}")
    lines.append(f"files: us={r.files_analyzed_by_us} liz={r.files_analyzed_by_lizard} matched={r.files_matched}")
    rho = "nan" if math.isnan(r.spearman_si_vs_lizard_cc) else f"{r.spearman_si_vs_lizard_cc:+.4f}"
    p = "—" if r.spearman_p is None else f"{r.spearman_p:.4g}"
    lines.append(f"spearman(si vs liz_max_cc): rho={rho}  p={p}")
    lines.append("")
    lines.append("Top-N Jaccard:")
    for n, j in sorted(r.jaccard.items()):
        lines.append(f"  top-{n:>2}: {j:.3f}")
    lines.append("")
    lines.append(f"Common top-{r.top_n} (양쪽 모두 hotspot, 정렬 = G-SI rank):")
    for rw in r.common_topN[:10]:
        lines.append(
            f"  gsi#{rw.rank_gsi:>2} liz#{rw.rank_lizard:>2} | "
            f"si={rw.si:5.1f} [{rw.grade}] liz_cc={rw.lizard_max_cc:>3}  {rw.file_path}"
        )
    lines.append("")
    lines.append(f"G-SI 단독 top-{r.top_n} (Lizard top-{r.top_n} 에는 없음 — Phase B 정성 분석 후보):")
    for rw in r.gsi_only_topN[:10]:
        lines.append(
            f"  gsi#{rw.rank_gsi:>2} liz#{rw.rank_lizard or '—':>2} | "
            f"si={rw.si:5.1f} [{rw.grade}] liz_cc={rw.lizard_max_cc:>3}  {rw.file_path}"
        )
    lines.append("")
    lines.append(f"Lizard 단독 top-{r.top_n} (G-SI top-{r.top_n} 에는 없음):")
    for rw in r.lizard_only_topN[:10]:
        lines.append(
            f"  gsi#{rw.rank_gsi or '—':>2} liz#{rw.rank_lizard:>2} | "
            f"si={rw.si:5.1f} [{rw.grade}] liz_cc={rw.lizard_max_cc:>3}  {rw.file_path}"
        )
    if r.notes:
        lines.append("")
        lines.append("Notes:")
        for n in r.notes:
            lines.append(f"  - {n}")
    return "\n".join(lines)
