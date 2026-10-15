"""최종판: 실제 점수 계산과 튜닝·검증 분리의 일치 여부."""

import json
import math

import networkx as nx
import pytest

from game_si.metrics import ClassMetrics, MethodMetrics, MetricsResult
from game_si.si import compute_si_static, scoring_to_dict
from game_si.tune import load_case_data, evaluate_weights, run_tune, to_dict, CaseData, WEIGHT_KEYS
from game_si.validate import spearman


def test_tuning_matches_analyzer_with_multiple_classes_per_file(tmp_path):
    classes = []
    methods = []
    # A.cs의 CC와 coupling 최대값은 서로 다른 클래스에 있다.
    for i, (path, cc, coupling) in enumerate([
        ("A.cs", 30, 0), ("A.cs", 1, 30), ("B.cs", 24, 24),
        ("C.cs", 12, 12), ("D.cs", 8, 8), ("E.cs", 2, 2),
        ("Unmatched.cs", 100, 100),
    ]):
        fqn = f"C{i}"
        method = MethodMetrics(f"{fqn}.Tick", fqn, path, "Tick", 1, 2,
                               cc, 2, False, [])
        cls = ClassMetrics(fqn, fqn, path, 1, 2, "class")
        cls.methods = [method]
        cls.cc_top10p_mean = cc
        cls.coupling = coupling
        classes.append(cls)
        methods.append(method)
    metrics = MetricsResult("test", "test", classes, methods, nx.DiGraph(), [])
    weights = {k: (0.5 if k in ("cc", "coupling") else 0.0) for k in WEIGHT_KEYS}
    scoring = scoring_to_dict(compute_si_static(metrics, weights))
    bugs = {"A.cs": 4, "B.cs": 5, "C.cs": 3, "D.cs": 2, "E.cs": 1}
    rows = [{"file_path": p, "bugfix_count": n} for p, n in bugs.items()]
    sp, vp = tmp_path / "scoring.json", tmp_path / "validation.json"
    sp.write_text(json.dumps(scoring), encoding="utf-8")
    vp.write_text(json.dumps({"file_rows": rows}), encoding="utf-8")
    case = load_case_data("example", sp, vp)
    by_file = {r["file_path"]: r["si_max"] for r in scoring["file_scores"]}
    expected, _ = spearman([by_file[p] for p in bugs], list(bugs.values()))
    assert evaluate_weights(case, weights) == pytest.approx(expected)
    # 비교 대상이 아닌 클래스도 포함해 본 분석과 같은 전체 집합으로 표준화한다.
    assert evaluate_weights(case, {k: v * 2 for k, v in weights.items()}) == pytest.approx(expected)


def _case(name, group, ascending=True, n=6):
    raw = {f"f{i}": {k: (float(i) if k == "cc" else 0.0) for k in WEIGHT_KEYS}
           for i in range(n)}
    bugs = {f"f{i}": i if ascending else n - i for i in range(n)}
    return CaseData(name, raw, bugs, project_group=group)


def test_lopo_holds_all_modules_of_a_project_out_together(monkeypatch):
    import game_si.tune as tune
    monkeypatch.setattr(tune, "GRID_STEPS", (0.2,))
    cases = [_case("OpenRA.Game", "OpenRA"), _case("OpenRA.Common", "OpenRA"),
             _case("Doom", "Doom"), _case("RCT", "RCT")]
    result = run_tune(cases)
    payload = to_dict(result)
    assert payload["validation_unit"] == "project"
    assert len(payload["project_folds"]) == 3
    for fold in payload["project_folds"]:
        train = {payload["case_projects"][n] for n in fold["train_cases"]}
        held = {payload["case_projects"][n] for n in fold["holdout_cases"]}
        assert train.isdisjoint(held)
        assert len(held) == 1
        assert set(fold["weights"]) == set(WEIGHT_KEYS)
    openra = next(f for f in payload["project_folds"] if f["project"] == "OpenRA")
    assert set(openra["holdout_cases"]) == {"OpenRA.Game", "OpenRA.Common"}


def test_project_average_is_not_dominated_by_module_count(monkeypatch):
    import game_si.tune as tune
    monkeypatch.setattr(tune, "GRID_STEPS", (0.2,))
    cases = [_case("A1", "A"), _case("A2", "A"),
             _case("B", "B", ascending=False), _case("tiny", "A", n=2)]
    result = run_tune(cases)
    assert result.lopo_default_rho == pytest.approx(0.0)
    assert result.lopo_tuned_rho == pytest.approx(0.0)
    assert math.isnan(result.per_case_default_rho["tiny"])
    assert to_dict(result)["excluded_cases"] == ["tiny"]


def test_change_risk_explicit_end_date_sets_both_window_bounds(monkeypatch, tmp_path):
    from game_si import change_risk
    seen = []
    monkeypatch.setattr(change_risk, "_run_git", lambda repo, args: seen.extend(args) or "")
    change_risk.compute_change_risk(tmp_path, "src", months=12, until="2026-10-03")
    assert "--since=2025-10-08T00:00:00Z" in seen
    assert "--until=2026-10-03T23:59:59Z" in seen


def test_full_cli_accepts_explicit_end_date():
    from game_si.cli import _build_parser
    args = _build_parser().parse_args([
        "score-full", "src", "--repo", ".", "--out", "result",
        "--until", "2026-10-03",
    ])
    assert args.until == "2026-10-03"


def test_tune_cli_accepts_explicit_project_mapping():
    from game_si.cli import _build_parser
    args = _build_parser().parse_args([
        "tune", "--case", "Game=result", "--project-group", "Game=OpenRA",
    ])
    assert args.project_group == ["Game=OpenRA"]


def test_full_result_records_reproducible_window(monkeypatch, tmp_path):
    from pathlib import Path
    from game_si import change_risk
    from game_si.cli import _build_parser, _cmd_score_full
    # Git 프로세스만 격리한다. C 파싱·점수 계산·JSON 저장은 실제 구현을 실행한다.
    monkeypatch.setattr(change_risk, "_run_git", lambda repo, args: "")
    sample = Path(__file__).parent / "samples" / "cpp"
    args = _build_parser().parse_args([
        "score-full", str(sample), "--lang", "c", "--repo", str(tmp_path),
        "--out", str(tmp_path / "out"), "--until", "2026-10-03",
    ])
    assert _cmd_score_full(args) == 0
    payload = json.loads((tmp_path / "out" / "scoring_full.json").read_text(encoding="utf-8"))
    assert payload["change_risk_until"] == "2026-10-03"
    assert payload["change_risk_since"] == "2025-10-08"


def test_advisor_display_discloses_generation_time_metrics():
    from game_si.report import _render_refactoring_guide
    rendered = _render_refactoring_guide({"rows": [{"fqn": "Example", "si": 90}]})
    assert "생성 당시의 지표" in rendered
    assert "현재 분석 결과와 다를 수 있습니다" in rendered


def test_tune_summary_does_not_claim_statistical_equivalence():
    from game_si.tune import TuneResult, format_summary
    weights = {k: 0.2 for k in WEIGHT_KEYS}
    result = TuneResult(weights, weights, {"A": 0.5}, {"A": 0.505}, 0.5, 0.505, 1, 1)
    summary = format_summary(result)
    assert "유의성" in summary
    assert "사실상 동일" not in summary


def test_release_candidate_version_is_consistent():
    import re
    from pathlib import Path
    from game_si import __version__
    config = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    project_version = re.search(r'^version = "([^"]+)"', config, re.MULTILINE).group(1)
    assert project_version == __version__ == "1.0.0rc1"


def test_lopo_rejects_only_one_evaluable_project(monkeypatch):
    import game_si.tune as tune
    monkeypatch.setattr(tune, "GRID_STEPS", (0.2,))
    constant = _case("constant", "B")
    constant.bugfix_by_file = {f: 0 for f in constant.bugfix_by_file}
    with pytest.raises(ValueError, match="at least two projects"):
        run_tune([_case("valid", "A"), constant])


def test_constant_cases_have_specific_exclusion_reason_and_strict_json(monkeypatch):
    import game_si.tune as tune
    monkeypatch.setattr(tune, "GRID_STEPS", (0.2,))
    constant = _case("constant", "A")
    constant.bugfix_by_file = {f: 0 for f in constant.bugfix_by_file}
    payload = to_dict(run_tune([_case("A", "A"), _case("B", "B"), constant]))
    assert payload["exclusion_reasons"]["constant"] == "constant bug-fix counts"
    assert all("constant" not in f["holdout_cases"] for f in payload["project_folds"])
    json.dumps(payload, allow_nan=False)


def test_grid_without_valid_candidates_does_not_fabricate_weights(monkeypatch):
    import game_si.tune as tune
    monkeypatch.setattr(tune, "GRID_STEPS", (0.2,))
    constant = _case("constant", "A")
    constant.bugfix_by_file = {f: 0 for f in constant.bugfix_by_file}
    with pytest.raises(ValueError, match="valid weight"):
        tune.find_best_weights([constant])


def test_tuning_prefers_full_precision_raw(tmp_path):
    raw = {f"f{i}": {k: float(i) if k == "cc" else 0.0 for k in WEIGHT_KEYS}
           for i in range(6)}
    rows = [{"file_path": f, "raw": {k: 0.0 for k in WEIGHT_KEYS}, "raw_exact": r}
            for f, r in raw.items()]
    scoring_path, validation_path = tmp_path / "scoring.json", tmp_path / "validation.json"
    scoring_path.write_text(json.dumps({"class_scores": rows}), encoding="utf-8")
    validation_path.write_text(json.dumps({"file_rows": [
        {"file_path": f, "bugfix_count": i} for i, f in enumerate(raw)
    ]}), encoding="utf-8")
    case = load_case_data("precise", scoring_path, validation_path)
    assert evaluate_weights(case, {k: 0.2 for k in WEIGHT_KEYS}) == pytest.approx(1.0)
    # 본 분석의 직렬화도 반올림 전 raw를 보존한다.
    metrics = MetricsResult("test", "test", [], [], nx.DiGraph(), [])
    cls = ClassMetrics("Example", "Example", "e.cs", 1, 2, "class")
    method = MethodMetrics("Example.Tick", "Example", "e.cs", "Tick", 1, 2, 1, 2, False, [])
    cls.methods = [method]
    cls.cc_top10p_mean = 1.123456789
    metrics.classes = [cls]
    metrics.methods = [method]
    saved = scoring_to_dict(compute_si_static(metrics))["class_scores"][0]
    assert saved["raw_exact"]["cc"] == 1.123456789
    assert saved["raw"]["cc"] == 1.1235


def test_full_cli_invalid_date_reports_error_without_outputs(tmp_path, capsys):
    from game_si.cli import _build_parser, _cmd_score_full
    args = _build_parser().parse_args([
        "score-full", str(tmp_path), "--repo", str(tmp_path),
        "--out", str(tmp_path / "out"), "--until", "2026-13-01",
    ])
    assert _cmd_score_full(args) == 1
    assert "--until" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_lopo_does_not_drop_an_undefined_holdout_module(monkeypatch):
    import game_si.tune as tune
    from game_si.si import DEFAULT_WEIGHTS_STATIC
    equal = {k: 0.2 for k in WEIGHT_KEYS}
    monkeypatch.setattr(tune, "_candidate_weights", lambda: iter([equal, DEFAULT_WEIGHTS_STATIC]))
    conflicting = _case("A1", "A", ascending=False)
    for i, raw in enumerate(conflicting.raw_by_file.values()):
        raw["coupling"] = 5.0 - i
    with pytest.raises(ValueError, match="undefined module correlation"):
        run_tune([conflicting, _case("A2", "A"), _case("B", "B")])
