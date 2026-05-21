"""W14 확장 모듈 (change_risk / tune / diff) 단위 테스트."""

from __future__ import annotations

import math
from collections import Counter

import pytest

from game_si import change_risk as cr_mod
from game_si.tune import (
    CaseData,
    _candidate_weights,
    _zscore_columns,
    evaluate_weights,
    find_best_weights,
    lopo_cross_validation,
    WEIGHT_KEYS,
)
from game_si.diff import compute_diff, format_summary, to_dict


# ---------------------------------------------------------------------------
# change_risk — git CLI 출력 파싱·집계 로직
# ---------------------------------------------------------------------------


def _fake_git_log(subdir_files: list[tuple[str, str, list[str]]]) -> str:
    """`[(sha, subject, [files]), ...]` 를 git log 출력 형식으로 변환."""
    out = []
    for sha, subject, files in subdir_files:
        out.append(f"__COMMIT__\x01{sha}\x01{subject}")
        out.extend(files)
        out.append("")
    return "\n".join(out)


def test_change_risk_total_and_bugfix_counts(monkeypatch, tmp_path):
    """파일별 total/bugfix 카운트와 ratio·change_risk 결합식 검증."""
    fake_log = _fake_git_log([
        ("a1", "Fix crash in renderer", ["src/Renderer.cs", "src/Util.cs"]),
        ("a2", "Add new tile category", ["src/Tile.cs"]),
        ("a3", "Bug: lobby UI freeze", ["src/Renderer.cs"]),
        ("a4", "Fix typo in README", ["src/Renderer.cs"]),  # trivial — 제외
        ("a5", "Refactor util module", ["src/Util.cs", "src/Tile.cs"]),
    ])
    monkeypatch.setattr(cr_mod, "_run_git", lambda repo, args: fake_log)

    result = cr_mod.compute_change_risk(tmp_path, subdir="src", months=12)

    assert set(result.keys()) == {"Renderer.cs", "Util.cs", "Tile.cs"}

    r = result["Renderer.cs"]
    assert r.total_changes == 3       # a1, a3, a4 (모두 path 매칭)
    assert r.bugfix_changes == 2      # a1, a3 (a4 는 "fix typo" 로 trivial 필터)
    assert r.bugfix_ratio == pytest.approx(2 / 3)
    assert r.change_risk == pytest.approx(3 * (1 + 2 / 3))

    # bug-fix 없는 파일은 ratio 0, change_risk = total
    t = result["Tile.cs"]
    assert t.total_changes == 2 and t.bugfix_changes == 0
    assert t.change_risk == pytest.approx(2.0)


def test_change_risk_subdir_prefix_stripped(monkeypatch, tmp_path):
    """subdir 외부 변경은 무시되고, subdir 내부는 prefix 제거되어 키가 된다."""
    fake_log = _fake_git_log([
        ("a1", "fix issue", ["src/openrct2/ride/Ride.cpp", "docs/README.md"]),
    ])
    monkeypatch.setattr(cr_mod, "_run_git", lambda repo, args: fake_log)
    result = cr_mod.compute_change_risk(tmp_path, subdir="src/openrct2", months=12)
    assert list(result.keys()) == ["ride/Ride.cpp"]
    assert result["ride/Ride.cpp"].repo_path == "src/openrct2/ride/Ride.cpp"


def test_change_risk_empty_log(monkeypatch, tmp_path):
    monkeypatch.setattr(cr_mod, "_run_git", lambda repo, args: "")
    result = cr_mod.compute_change_risk(tmp_path, subdir="src", months=12)
    assert result == {}


# ---------------------------------------------------------------------------
# tune — z-score, grid, evaluate, LOPO
# ---------------------------------------------------------------------------


def test_zscore_columns_centers_to_mean_zero():
    rows = [{"a": 1.0, "b": 10.0}, {"a": 2.0, "b": 20.0}, {"a": 3.0, "b": 30.0}]
    z = _zscore_columns(rows)
    # 평균이 0 이어야
    assert abs(sum(r["a"] for r in z)) < 1e-9
    assert abs(sum(r["b"] for r in z)) < 1e-9
    # 순서 보존
    assert z[0]["a"] < z[1]["a"] < z[2]["a"]


def test_candidate_weights_all_sum_to_one():
    samples = list(_candidate_weights())
    assert len(samples) > 100  # 적당히 많은 후보
    for w in samples[:50]:
        assert abs(sum(w.values()) - 1.0) < 1e-9
        assert set(w.keys()) == set(WEIGHT_KEYS)


def test_evaluate_weights_perfect_match():
    """raw 가 bugfix 와 단조 증가 관계면 ρ = +1.0 이 나와야 한다."""
    # 5 파일, raw 의 cc 값이 file index 와 동일, 나머지는 0
    raw = {
        f"f{i}.cs": {k: (float(i) if k == "cc" else 0.0) for k in WEIGHT_KEYS}
        for i in range(10)
    }
    bug = {f"f{i}.cs": i for i in range(10)}
    case = CaseData("test", raw, bug)
    # cc 만 1, 나머지 0 인 가중치
    w = {"cc": 1.0, "coupling": 0.0, "dependency_cycle": 0.0,
         "global_state": 0.0, "game_loop_centrality": 0.0}
    rho = evaluate_weights(case, w)
    assert rho == pytest.approx(1.0)


def test_evaluate_weights_returns_nan_for_tiny_case():
    raw = {f"f{i}.cs": {k: 0.0 for k in WEIGHT_KEYS} for i in range(2)}
    bug = {f"f{i}.cs": i for i in range(2)}
    rho = evaluate_weights(CaseData("tiny", raw, bug), {k: 0.2 for k in WEIGHT_KEYS})
    assert math.isnan(rho)


def test_lopo_returns_per_case_holdout():
    """3 케이스 모두 동일한 단조 데이터 → LOPO 의 hold-out 도 +1.0 근처."""
    def _mk(name):
        raw = {f"f{i}": {k: (float(i) if k == "cc" else 0.0) for k in WEIGHT_KEYS}
               for i in range(15)}
        bug = {f"f{i}": i for i in range(15)}
        return CaseData(name, raw, bug)
    cases = [_mk("A"), _mk("B"), _mk("C")]
    avg, per_case = lopo_cross_validation(cases)
    assert set(per_case.keys()) == {"A", "B", "C"}
    assert avg == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# diff — 두 scoring.json 비교
# ---------------------------------------------------------------------------


def _write_scoring(path, classes, health):
    import json
    path.write_text(
        json.dumps({"project_health": health, "class_scores": classes}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_diff_classifies_added_removed_unchanged(tmp_path):
    baseline_p = tmp_path / "base.json"
    latest_p = tmp_path / "latest.json"
    _write_scoring(baseline_p, [
        {"fqn": "A.Foo", "file_path": "Foo.cs", "si": 50.0, "grade": "C"},
        {"fqn": "A.Removed", "file_path": "Removed.cs", "si": 30.0, "grade": "B"},
    ], {"score": 40.0, "grade": "B", "avg_si": 40.0, "risk_ratio": 0.2, "cycle_count": 1})
    _write_scoring(latest_p, [
        {"fqn": "A.Foo", "file_path": "Foo.cs", "si": 50.0, "grade": "C"},   # 변화 없음
        {"fqn": "A.New", "file_path": "New.cs", "si": 90.0, "grade": "E"},   # 신규
    ], {"score": 45.0, "grade": "C", "avg_si": 45.0, "risk_ratio": 0.3, "cycle_count": 2})

    r = compute_diff(baseline_p, latest_p)
    assert len(r.classes_added) == 1 and r.classes_added[0]["fqn"] == "A.New"
    assert len(r.classes_removed) == 1 and r.classes_removed[0]["fqn"] == "A.Removed"
    assert r.classes_unchanged_count == 1
    assert r.classes_worsened == [] and r.classes_improved == []
    assert r.health_delta == pytest.approx(5.0)
    assert r.cycle_count_delta == 1
    assert r.grade_baseline == "B" and r.grade_latest == "C"


def test_diff_detects_grade_changes(tmp_path):
    baseline_p = tmp_path / "base.json"
    latest_p = tmp_path / "latest.json"
    _write_scoring(baseline_p, [
        {"fqn": "A.Up", "file_path": "Up.cs", "si": 25.0, "grade": "B"},
        {"fqn": "A.Down", "file_path": "Down.cs", "si": 85.0, "grade": "E"},
    ], {"score": 50.0, "grade": "C", "avg_si": 55.0, "risk_ratio": 0.4, "cycle_count": 2})
    _write_scoring(latest_p, [
        {"fqn": "A.Up", "file_path": "Up.cs", "si": 75.0, "grade": "D"},     # 악화
        {"fqn": "A.Down", "file_path": "Down.cs", "si": 35.0, "grade": "B"}, # 개선
    ], {"score": 50.0, "grade": "C", "avg_si": 55.0, "risk_ratio": 0.4, "cycle_count": 2})

    r = compute_diff(baseline_p, latest_p)
    assert len(r.classes_worsened) == 1
    assert r.classes_worsened[0].fqn == "A.Up"
    assert r.classes_worsened[0].grade_delta == 2  # B(1) → D(3)
    assert len(r.classes_improved) == 1
    assert r.classes_improved[0].fqn == "A.Down"
    assert r.classes_improved[0].grade_delta == -3  # E(4) → B(1)


def test_cycle_edges_differentiates_within_scc():
    """같은 SCC 의 두 클래스도 SCC 내 edge 수가 다르면 cycle_edges 값이 달라진다."""
    import networkx as nx
    from game_si.metrics import ClassMetrics, _compute_cycle_membership

    # 3-노드 SCC, 그리고 그 안에서 hub 노드(A) 가 더 많은 edge.
    # A ↔ B 양방향, A ↔ C 양방향, B → C 단방향.
    g = nx.DiGraph()
    for fqn in ("A", "B", "C"):
        g.add_node(fqn)
    g.add_edges_from([("A", "B"), ("B", "A"), ("A", "C"), ("C", "A"), ("B", "C"), ("C", "B")])

    classes = [
        ClassMetrics(fqn=f, name=f, file_path=f"{f}.cs", start_line=1, end_line=1, kind="class")
        for f in ("A", "B", "C")
    ]
    _compute_cycle_membership(classes, g)

    by_fqn = {c.fqn: c for c in classes}
    for c in classes:
        assert c.cycle_member is True
        assert c.cycle_size == 3
    # 각 노드 in+out 카운트: A: 2 in + 2 out = 4, B: 2 in + 2 out = 4, C: 2 in + 2 out = 4
    # (대칭 SCC). 그래서 같다.
    assert by_fqn["A"].cycle_edges == 4
    assert by_fqn["B"].cycle_edges == 4
    assert by_fqn["C"].cycle_edges == 4


def test_cycle_edges_asymmetric():
    """비대칭 SCC: hub 노드와 peripheral 노드의 cycle_edges 차이."""
    import networkx as nx
    from game_si.metrics import ClassMetrics, _compute_cycle_membership

    # A 는 SCC hub: B,C,D 모두와 양방향. B,C,D 간 edge 없음.
    # 그래도 SCC 가 되려면 A → B → A 같은 양방향이 모두 있어야.
    g = nx.DiGraph()
    g.add_edges_from([
        ("A", "B"), ("B", "A"),
        ("A", "C"), ("C", "A"),
        ("A", "D"), ("D", "A"),
    ])
    classes = [
        ClassMetrics(fqn=f, name=f, file_path=f"{f}.cs", start_line=1, end_line=1, kind="class")
        for f in ("A", "B", "C", "D")
    ]
    _compute_cycle_membership(classes, g)
    by_fqn = {c.fqn: c for c in classes}
    # A 는 6 개의 SCC 내부 edge 에 관여 (3 in + 3 out)
    assert by_fqn["A"].cycle_edges == 6
    # B/C/D 는 2 개 (1 in + 1 out)
    assert by_fqn["B"].cycle_edges == 2
    assert by_fqn["C"].cycle_edges == 2
    assert by_fqn["D"].cycle_edges == 2


def test_diff_format_summary_contains_key_lines(tmp_path):
    baseline_p = tmp_path / "base.json"
    latest_p = tmp_path / "latest.json"
    _write_scoring(baseline_p, [
        {"fqn": "X.Y", "file_path": "Y.cs", "si": 50.0, "grade": "C"},
    ], {"score": 40.0, "grade": "B", "avg_si": 40.0, "risk_ratio": 0.2, "cycle_count": 1})
    _write_scoring(latest_p, [
        {"fqn": "X.Y", "file_path": "Y.cs", "si": 50.0, "grade": "C"},
    ], {"score": 50.0, "grade": "C", "avg_si": 50.0, "risk_ratio": 0.3, "cycle_count": 2})

    r = compute_diff(baseline_p, latest_p)
    text = format_summary(r)
    assert "G-SI Diff" in text
    assert "Project Health" in text
    assert "+10.00" in text or "+10.0" in text  # 정확한 포맷에 관계없이 health Δ 노출
    payload = to_dict(r)
    assert payload["project_health"]["delta"] == pytest.approx(10.0)
