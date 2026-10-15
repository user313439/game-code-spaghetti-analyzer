"""W8 Phase A — G-SI ↔ bug-fix 빈도 검증.

`docs/_planning/plan_final_draft.md` §7.1 의 Phase A 핵심 정량 검증을 수행한다.

핵심 출력은 다음 세 가지 Spearman 순위 상관계수이다.

* ``si_vs_bugfix``    — G-SI-Static vs (해당 클래스 파일의) bug-fix 커밋 횟수
* ``loc_vs_bugfix``   — LOC vs bug-fix (baseline)
* ``cc_vs_bugfix``    — CC max vs bug-fix (baseline)

또한 `git log` 가 변경한 파일 중 분석기로 매핑되지 않은 경로(설정/문서 등)의
횟수를 함께 보고하여, 매핑 누락 또는 sub-directory mismatch 진단을 돕는다.

본 모듈은 외부 통계 라이브러리(scipy 등)에 의존하지 않는다. Spearman 계수와
p-value(정규근사)를 표준 라이브러리만으로 직접 계산한다.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .gitlog import GitLogResult


# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------


@dataclass
class ClassValidationRow:
    fqn: str
    file_path: str          # 분석 대상(sub-directory) 기준 상대 경로
    repo_path: str          # 저장소 루트 기준 전체 경로 (subdir 적용 결과)
    si: float
    cc_max: float
    loc: int
    bugfix_count: int       # 해당 파일을 변경한 bug-fix 커밋 수
    grade: str


@dataclass
class CorrelationStat:
    name: str
    n: int
    spearman_rho: float
    p_value: float | None   # 양측, n>=10 이고 |rho|<1 일 때 정규근사로 산출. 아니면 None.


@dataclass
class FileValidationRow:
    file_path: str
    repo_path: str
    si_max: float           # 파일 내 클래스 si 의 최댓값 (plan §4.1 파일 대표값)
    si_mean: float
    loc_total: int          # 파일 내 클래스 loc 합 (메서드 LOC 합)
    cc_max: float           # 파일 내 클래스 cc_max 의 최댓값
    class_count: int
    bugfix_count: int


@dataclass
class ValidationResult:
    repo_path: str
    subdir: str | None
    since: str | None
    until: str | None
    keywords: list[str]
    total_commits: int
    bugfix_commits: int
    classes_total: int
    classes_with_bugfix: int
    files_total: int
    files_with_bugfix: int          # bug-fix 가 매핑된 분석 파일 수
    unmatched_change_count: int     # bug-fix 변경 파일 중 분석기로 매핑되지 않은 touch 수
    class_correlations: list[CorrelationStat]
    file_correlations: list[CorrelationStat]
    rows: list[ClassValidationRow]
    file_rows: list[FileValidationRow]
    top_bugfix_files: list[tuple[str, int]]
    unmatched_paths_sample: list[tuple[str, int]]
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 공개 진입점
# ---------------------------------------------------------------------------


def run_validation(
    scoring: dict,
    gitlog: GitLogResult,
    subdir: str | None = None,
) -> ValidationResult:
    """`scoring.json` 과 `GitLogResult` 를 합쳐 검증 결과를 산출한다.

    분석 단위는 **클래스** 이다. 같은 파일에 여러 클래스가 있다면 그 파일의
    bug-fix 횟수를 공통으로 부여한다(파일 단위 변경 신호를 클래스 단위 비교에
    반영하는 방식). 이는 plan §7.1 가 허용하는 분석 단위 변환 중 하나이다.
    """
    classes = scoring.get("class_scores", [])
    if not classes:
        raise ValueError("scoring.json 에 class_scores 가 비어 있다 — analyze 를 먼저 실행하라.")

    # subdir → 저장소 루트 기준 prefix
    subdir_prefix = ""
    if subdir:
        subdir_prefix = subdir.replace("\\", "/").strip("/") + "/"

    # git log 결과(저장소 루트 기준 경로) → subdir 내부 상대 경로로 환산
    local_counts: dict[str, int] = {}
    unmatched_prefix_count = 0
    for path, n in gitlog.file_touch_counts.items():
        p = path.replace("\\", "/")
        if subdir_prefix:
            if not p.startswith(subdir_prefix):
                # subdir 외부 — 무시 (이미 path_filter 로 막혔어야 하나 안전망)
                continue
            local = p[len(subdir_prefix):]
        else:
            local = p
        local_counts[local] = local_counts.get(local, 0) + n

    # 분석 대상 파일 집합
    analyzed_files = {c["file_path"].replace("\\", "/") for c in classes}

    # 매핑되지 않은 변경 파일 통계
    unmatched: list[tuple[str, int]] = []
    unmatched_total = 0
    for p, n in local_counts.items():
        if p not in analyzed_files:
            unmatched_total += n
            unmatched.append((p, n))
    unmatched.sort(key=lambda kv: -kv[1])

    # 클래스 row 빌드
    rows: list[ClassValidationRow] = []
    files_with_bugfix: set[str] = set()
    for c in classes:
        fpath = c["file_path"].replace("\\", "/")
        count = local_counts.get(fpath, 0)
        if count > 0:
            files_with_bugfix.add(fpath)
        rows.append(ClassValidationRow(
            fqn=c["fqn"],
            file_path=fpath,
            repo_path=(subdir_prefix + fpath) if subdir_prefix else fpath,
            si=float(c.get("si", 0.0)),
            cc_max=float(c.get("raw", {}).get("cc", 0.0)),
            loc=int(c.get("loc", 0)),
            bugfix_count=count,
            grade=c.get("grade", "?"),
        ))

    classes_with_bugfix = sum(1 for r in rows if r.bugfix_count > 0)

    # 클래스 단위 상관계수 (0 카운트 포함; selection bias 회피)
    si_values = [r.si for r in rows]
    loc_values = [float(r.loc) for r in rows]
    cc_values = [r.cc_max for r in rows]
    bug_values = [float(r.bugfix_count) for r in rows]

    class_correlations: list[CorrelationStat] = []
    for name, x in (
        ("si_vs_bugfix", si_values),
        ("loc_vs_bugfix", loc_values),
        ("cc_vs_bugfix", cc_values),
    ):
        rho, p = spearman(x, bug_values)
        class_correlations.append(CorrelationStat(name=name, n=len(x), spearman_rho=rho, p_value=p))

    # 파일 단위 집계 — git 변경의 자연 단위가 파일이므로 더 직접적인 비교가 가능하다.
    file_rows = _aggregate_files(rows, local_counts)
    f_si = [fr.si_max for fr in file_rows]
    f_loc = [float(fr.loc_total) for fr in file_rows]
    f_cc = [fr.cc_max for fr in file_rows]
    f_bug = [float(fr.bugfix_count) for fr in file_rows]
    file_correlations: list[CorrelationStat] = []
    for name, x in (
        ("file_si_vs_bugfix", f_si),
        ("file_loc_vs_bugfix", f_loc),
        ("file_cc_vs_bugfix", f_cc),
    ):
        rho, p = spearman(x, f_bug)
        file_correlations.append(CorrelationStat(name=name, n=len(x), spearman_rho=rho, p_value=p))

    # 진단 메모
    notes: list[str] = []
    if gitlog.total_commits == 0:
        notes.append("git log가 비어 있다 — repo 경로 또는 since/until 범위를 확인하라.")
    if not gitlog.bugfix_commits:
        notes.append("bug-fix 키워드에 매칭된 커밋이 없다 — 키워드 또는 날짜 범위 확인.")
    if classes_with_bugfix == 0 and gitlog.bugfix_commits:
        notes.append("매칭된 bug-fix 커밋은 있으나 분석된 클래스 파일에 대응되지 않음 — --subdir 옵션 확인.")
    if unmatched_total > 0:
        notes.append(
            f"bug-fix 변경 파일 중 {unmatched_total} 회 touch 가 분석 대상 클래스 파일과 매칭되지 않았다 "
            f"(.cs 외 자산·설정 등). 정상적인 noise 일 수 있음."
        )

    top_bugfix_files = sorted(
        ((p, n) for p, n in local_counts.items() if p in analyzed_files),
        key=lambda kv: -kv[1],
    )[:20]

    return ValidationResult(
        repo_path=gitlog.repo_path,
        subdir=subdir,
        since=gitlog.since,
        until=gitlog.until,
        keywords=list(_DEFAULT_REPORTED_KEYWORDS),
        total_commits=gitlog.total_commits,
        bugfix_commits=len(gitlog.bugfix_commits),
        classes_total=len(rows),
        classes_with_bugfix=classes_with_bugfix,
        files_total=len(file_rows),
        files_with_bugfix=len(files_with_bugfix),
        unmatched_change_count=unmatched_total,
        class_correlations=class_correlations,
        file_correlations=file_correlations,
        rows=rows,
        file_rows=file_rows,
        top_bugfix_files=top_bugfix_files,
        unmatched_paths_sample=unmatched[:20],
        notes=notes,
    )


def _aggregate_files(
    rows: list[ClassValidationRow],
    bugfix_by_path: dict[str, int],
) -> list[FileValidationRow]:
    """클래스 단위 row 를 파일 단위로 묶는다.

    파일 대표값은 plan §4.1 에 따라 si_max 를 사용하고, LOC 는 합산한다.
    bug-fix 카운트는 파일별 commit 수 그대로다.
    """
    by_file: dict[str, list[ClassValidationRow]] = {}
    repo_path_by_file: dict[str, str] = {}
    for r in rows:
        by_file.setdefault(r.file_path, []).append(r)
        repo_path_by_file[r.file_path] = r.repo_path

    out: list[FileValidationRow] = []
    for fpath, group in by_file.items():
        si_values = [g.si for g in group]
        cc_values = [g.cc_max for g in group]
        out.append(FileValidationRow(
            file_path=fpath,
            repo_path=repo_path_by_file[fpath],
            si_max=max(si_values),
            si_mean=sum(si_values) / len(si_values),
            loc_total=sum(g.loc for g in group),
            cc_max=max(cc_values) if cc_values else 0.0,
            class_count=len(group),
            bugfix_count=bugfix_by_path.get(fpath, 0),
        ))
    return out


_DEFAULT_REPORTED_KEYWORDS = (
    "fix", "bug", "crash", "regression", "hotfix", "patch", "defect",
)


# ---------------------------------------------------------------------------
# 통계 — Spearman + 정규근사 p-value
# ---------------------------------------------------------------------------


def spearman(x: list[float], y: list[float]) -> tuple[float, float | None]:
    """Spearman 순위 상관계수와 (가능한 경우) 양측 p-value를 반환한다.

    동률은 평균 순위로 처리한다. p-value 는 Fisher z-변환 후 정규근사로 계산하며,
    n < 10 또는 |rho| == 1 인 경우에는 ``None`` 으로 둔다.
    """
    n = len(x)
    if n != len(y) or n < 3:
        return float("nan"), None
    rx = _rank_with_ties(x)
    ry = _rank_with_ties(y)
    rho = _pearson(rx, ry)
    if math.isnan(rho):
        return rho, None
    if n < 10 or abs(rho) >= 1.0:
        return rho, None
    z = math.atanh(rho) * math.sqrt((n - 3) / 1.06)
    p = 2.0 * (1.0 - _phi(abs(z)))
    return rho, max(0.0, min(1.0, p))


def _rank_with_ties(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda kv: kv[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        # 평균 순위 = ((i+1) + (j+1)) / 2
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg
        i = j + 1
    return ranks


def _pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 2:
        return float("nan")
    mx = sum(x) / n
    my = sum(y) / n
    sxy = 0.0
    sxx = 0.0
    syy = 0.0
    for xi, yi in zip(x, y):
        dx = xi - mx
        dy = yi - my
        sxy += dx * dy
        sxx += dx * dx
        syy += dy * dy
    denom = math.sqrt(sxx * syy)
    if denom == 0.0:
        return float("nan")
    return sxy / denom


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# 직렬화 / 텍스트 요약
# ---------------------------------------------------------------------------


def to_dict(r: ValidationResult) -> dict[str, Any]:
    def _corr(c: CorrelationStat) -> dict[str, Any]:
        return {
            "name": c.name,
            "n": c.n,
            "spearman_rho": None if math.isnan(c.spearman_rho) else round(c.spearman_rho, 4),
            "p_value": None if c.p_value is None else round(c.p_value, 6),
        }

    return {
        "schema_version": "validate-0.2",
        "repo_path": r.repo_path,
        "subdir": r.subdir,
        "since": r.since,
        "until": r.until,
        "keywords": r.keywords,
        "total_commits": r.total_commits,
        "bugfix_commits": r.bugfix_commits,
        "classes_total": r.classes_total,
        "classes_with_bugfix": r.classes_with_bugfix,
        "files_total": r.files_total,
        "files_with_bugfix": r.files_with_bugfix,
        "unmatched_change_count": r.unmatched_change_count,
        "class_correlations": [_corr(c) for c in r.class_correlations],
        "file_correlations": [_corr(c) for c in r.file_correlations],
        "top_bugfix_files": [{"path": p, "count": n} for p, n in r.top_bugfix_files],
        "unmatched_paths_sample": [{"path": p, "count": n} for p, n in r.unmatched_paths_sample],
        "rows": [
            {
                "fqn": row.fqn,
                "file_path": row.file_path,
                "si": round(row.si, 2),
                "grade": row.grade,
                "cc_max": row.cc_max,
                "loc": row.loc,
                "bugfix_count": row.bugfix_count,
            }
            for row in r.rows
        ],
        "file_rows": [
            {
                "file_path": fr.file_path,
                "si_max": round(fr.si_max, 2),
                "si_mean": round(fr.si_mean, 2),
                "loc_total": fr.loc_total,
                "cc_max": fr.cc_max,
                "class_count": fr.class_count,
                "bugfix_count": fr.bugfix_count,
            }
            for fr in r.file_rows
        ],
        "notes": r.notes,
    }


def format_text_summary(r: ValidationResult) -> str:
    def _line(c: CorrelationStat) -> str:
        rho_s = "nan" if math.isnan(c.spearman_rho) else f"{c.spearman_rho:+.4f}"
        p_s = "—" if c.p_value is None else f"{c.p_value:.4g}"
        return f"  {c.name:<22}  n={c.n:>4}  rho={rho_s:>8}  p={p_s}"

    lines: list[str] = []
    lines.append("=== G-SI Validation (Phase A) ===")
    lines.append(f"repo:           {r.repo_path}")
    lines.append(f"subdir:         {r.subdir or '(repo root)'}")
    lines.append(f"date range:     {r.since or '*'} .. {r.until or '*'}")
    lines.append(f"commits seen:   {r.total_commits}")
    lines.append(f"bug-fix found:  {r.bugfix_commits}")
    lines.append(f"classes total:  {r.classes_total}  (with bug-fix: {r.classes_with_bugfix})")
    lines.append(f"files total:    {r.files_total}  (with bug-fix: {r.files_with_bugfix})")
    lines.append(f"unmatched changes (non-class files): {r.unmatched_change_count}")
    lines.append("")
    lines.append("Class-level Spearman correlation (vs file bug-fix count):")
    for c in r.class_correlations:
        lines.append(_line(c))
    lines.append("")
    lines.append("File-level Spearman correlation (vs file bug-fix count):")
    for c in r.file_correlations:
        lines.append(_line(c))
    if r.top_bugfix_files:
        lines.append("")
        lines.append("Top bug-fix touched analysis files:")
        for p, n in r.top_bugfix_files[:10]:
            lines.append(f"  {n:>4}  {p}")
    if r.notes:
        lines.append("")
        lines.append("Notes:")
        for note in r.notes:
            lines.append(f"  - {note}")
    return "\n".join(lines)


def load_scoring(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
