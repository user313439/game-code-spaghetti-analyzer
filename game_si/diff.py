"""W14 (확장) — 두 G-SI 분석 결과의 변화 비교 (CI 품질 게이트 기반).

plan §6.3 의 "GitHub Actions 에서 동작 가능한 품질 게이트 샘플" 의 분석 모듈.

입력: 두 개의 ``scoring.json`` 경로 (baseline / latest).
출력:
- project_health 변화량 (점수 + 등급)
- avg_si / risk_ratio / cycle_count 변화
- 등급이 변한 클래스 목록 (특히 악화된 것)
- 신규 / 사라진 클래스
- exit code: ``--fail-if-worse-than N`` 옵션으로 health Δ > N 일 때 비-0 반환

CI 사용 예:
    python -m game_si diff main.scoring.json pr.scoring.json --fail-if-worse-than 3
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


GRADE_RANK = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}


@dataclass
class ClassChange:
    fqn: str
    file_path: str
    si_baseline: float
    si_latest: float
    grade_baseline: str
    grade_latest: str
    delta: float          # si_latest - si_baseline (양수 = 악화)
    grade_delta: int      # grade_rank 차 (양수 = 악화)


@dataclass
class DiffResult:
    baseline_path: str
    latest_path: str

    # 프로젝트 단위
    health_baseline: float
    health_latest: float
    health_delta: float
    avg_si_delta: float
    risk_ratio_delta: float
    cycle_count_delta: int
    grade_baseline: str
    grade_latest: str

    # 클래스 단위
    classes_added: list[dict]
    classes_removed: list[dict]
    classes_improved: list[ClassChange]   # 등급 좋아진 것 (grade_delta < 0)
    classes_worsened: list[ClassChange]   # 등급 나빠진 것 (grade_delta > 0)
    classes_unchanged_count: int

    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 메인 로직
# ---------------------------------------------------------------------------


def compute_diff(baseline_path: Path, latest_path: Path) -> DiffResult:
    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline = json.load(f)
    with open(latest_path, "r", encoding="utf-8") as f:
        latest = json.load(f)

    bh = baseline.get("project_health") or {}
    lh = latest.get("project_health") or {}

    health_b = float(bh.get("score", 0.0))
    health_l = float(lh.get("score", 0.0))

    b_by_fqn = {c["fqn"]: c for c in baseline.get("class_scores", [])}
    l_by_fqn = {c["fqn"]: c for c in latest.get("class_scores", [])}

    added = [c for fqn, c in l_by_fqn.items() if fqn not in b_by_fqn]
    removed = [c for fqn, c in b_by_fqn.items() if fqn not in l_by_fqn]

    improved: list[ClassChange] = []
    worsened: list[ClassChange] = []
    unchanged = 0
    for fqn, lc in l_by_fqn.items():
        bc = b_by_fqn.get(fqn)
        if bc is None:
            continue
        gb = bc.get("grade", "?")
        gl = lc.get("grade", "?")
        gd = GRADE_RANK.get(gl, 0) - GRADE_RANK.get(gb, 0)
        change = ClassChange(
            fqn=fqn,
            file_path=lc.get("file_path", ""),
            si_baseline=float(bc.get("si", 0.0)),
            si_latest=float(lc.get("si", 0.0)),
            grade_baseline=gb,
            grade_latest=gl,
            delta=float(lc.get("si", 0.0)) - float(bc.get("si", 0.0)),
            grade_delta=gd,
        )
        if gd > 0:
            worsened.append(change)
        elif gd < 0:
            improved.append(change)
        else:
            unchanged += 1

    worsened.sort(key=lambda c: (-c.grade_delta, -c.delta))
    improved.sort(key=lambda c: (c.grade_delta, c.delta))

    notes: list[str] = []
    if not b_by_fqn:
        notes.append("baseline 의 class_scores 가 비어 있다.")
    if not l_by_fqn:
        notes.append("latest 의 class_scores 가 비어 있다.")

    return DiffResult(
        baseline_path=str(baseline_path),
        latest_path=str(latest_path),
        health_baseline=health_b,
        health_latest=health_l,
        health_delta=health_l - health_b,
        avg_si_delta=float(lh.get("avg_si", 0.0)) - float(bh.get("avg_si", 0.0)),
        risk_ratio_delta=float(lh.get("risk_ratio", 0.0)) - float(bh.get("risk_ratio", 0.0)),
        cycle_count_delta=int(lh.get("cycle_count", 0)) - int(bh.get("cycle_count", 0)),
        grade_baseline=str(bh.get("grade", "?")),
        grade_latest=str(lh.get("grade", "?")),
        classes_added=added,
        classes_removed=removed,
        classes_improved=improved,
        classes_worsened=worsened,
        classes_unchanged_count=unchanged,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# 직렬화 / 요약
# ---------------------------------------------------------------------------


def to_dict(r: DiffResult) -> dict[str, Any]:
    def _cc(c: ClassChange) -> dict[str, Any]:
        return {
            "fqn": c.fqn,
            "file_path": c.file_path,
            "si_baseline": round(c.si_baseline, 2),
            "si_latest": round(c.si_latest, 2),
            "grade_baseline": c.grade_baseline,
            "grade_latest": c.grade_latest,
            "delta": round(c.delta, 2),
            "grade_delta": c.grade_delta,
        }

    return {
        "schema_version": "diff-0.1",
        "baseline_path": r.baseline_path,
        "latest_path": r.latest_path,
        "project_health": {
            "baseline": round(r.health_baseline, 2),
            "latest": round(r.health_latest, 2),
            "delta": round(r.health_delta, 2),
            "grade_baseline": r.grade_baseline,
            "grade_latest": r.grade_latest,
        },
        "avg_si_delta": round(r.avg_si_delta, 2),
        "risk_ratio_delta": round(r.risk_ratio_delta, 4),
        "cycle_count_delta": r.cycle_count_delta,
        "classes_added": [{"fqn": c["fqn"], "grade": c.get("grade"), "si": c.get("si")} for c in r.classes_added],
        "classes_removed": [{"fqn": c["fqn"], "grade": c.get("grade"), "si": c.get("si")} for c in r.classes_removed],
        "classes_worsened": [_cc(c) for c in r.classes_worsened],
        "classes_improved": [_cc(c) for c in r.classes_improved],
        "classes_unchanged_count": r.classes_unchanged_count,
        "notes": r.notes,
    }


def format_summary(r: DiffResult) -> str:
    arrow = lambda d: ("↑ 악화" if d > 0 else ("↓ 개선" if d < 0 else "≈ 변화 없음"))
    out: list[str] = []
    out.append("=== G-SI Diff (baseline → latest) ===")
    out.append(f"baseline: {r.baseline_path}")
    out.append(f"latest:   {r.latest_path}")
    out.append("")
    out.append(f"Project Health:  {r.health_baseline:.2f} ({r.grade_baseline}) → "
               f"{r.health_latest:.2f} ({r.grade_latest})   "
               f"Δ {r.health_delta:+.2f} {arrow(r.health_delta)}")
    out.append(f"avg G-SI:        Δ {r.avg_si_delta:+.2f}")
    out.append(f"risk_ratio:      Δ {r.risk_ratio_delta*100:+.2f}%")
    out.append(f"cycle_count:     Δ {r.cycle_count_delta:+d}")
    out.append("")
    out.append(f"classes added:    {len(r.classes_added)}")
    out.append(f"classes removed:  {len(r.classes_removed)}")
    out.append(f"classes worsened: {len(r.classes_worsened)}")
    out.append(f"classes improved: {len(r.classes_improved)}")
    out.append(f"classes unchanged: {r.classes_unchanged_count}")
    if r.classes_worsened:
        out.append("")
        out.append("Top 10 worsened classes:")
        for cc in r.classes_worsened[:10]:
            out.append(
                f"  [{cc.grade_baseline}→{cc.grade_latest}] {cc.si_baseline:6.2f}→{cc.si_latest:6.2f} "
                f"(Δ {cc.delta:+5.2f})  {cc.fqn}"
            )
    if r.classes_improved:
        out.append("")
        out.append("Top 5 improved classes:")
        for cc in r.classes_improved[:5]:
            out.append(
                f"  [{cc.grade_baseline}→{cc.grade_latest}] {cc.si_baseline:6.2f}→{cc.si_latest:6.2f} "
                f"(Δ {cc.delta:+5.2f})  {cc.fqn}"
            )
    if r.notes:
        out.append("")
        for n in r.notes:
            out.append(f"  ! {n}")
    return "\n".join(out)
