"""회귀 테스트: 식별자, 정확한 호출 연결, 상대 순위와 동점 정렬."""
import pytest
from pathlib import Path

from game_si.metrics import compute_metrics, metrics_to_dict
from game_si.si import compute_si_static, scoring_to_dict
from game_si.compare import LizardFileStat, run_comparison


def method(name, line=1, **extra):
    return dict(name=name, start_line=line, end_line=line, loc=1,
                cyclomatic_complexity=1, **extra)


def unit(fqn, methods=(), line=1, **extra):
    return dict(fully_qualified_name=fqn, name=fqn.rsplit('.', 1)[-1],
                start_line=line, end_line=line + 10, methods=list(methods), **extra)


def ast(*classes):
    return {"files": [{"relative_path": "test.cs", "classes": list(classes)}]}


def test_qualified_call_does_not_require_globally_unique_method_name():
    result = compute_metrics(ast(
        unit("Game.A", [method("Update", is_game_loop_entry=True, invoked_names=["Game.B.Work"])]),
        unit("Game.B", [method("Work")]), unit("Game.C", [method("Work")]),
    ))
    assert result.class_index["Game.B"].game_loop_centrality == .5
    assert result.class_index["Game.C"].game_loop_centrality == 0


def test_external_qualified_call_does_not_connect_to_local_namesake():
    result = compute_metrics(ast(
        unit("Game.A", [method("Update", is_game_loop_entry=True, invoked_names=["External.B.Work"])]),
        unit("Game.B", [method("Work")]),
    ))
    assert result.class_index["Game.B"].game_loop_centrality == 0


def test_overloads_have_unique_nodes_and_semantic_calls_select_one():
    result = compute_metrics(ast(unit("Game.A", [
        method("Update", is_game_loop_entry=True, invoked_symbols=["M:Game.A.Work(System.Int32)"]),
        method("Work", 2, symbol_id="M:Game.A.Work(System.Int32)"),
        method("Work", 3, symbol_id="M:Game.A.Work(System.String)"),
    ])))
    assert len({m.fqn for m in result.methods}) == 3
    assert [m.game_loop_centrality for m in result.methods] == [1, .5, 0]


def test_duplicate_classes_are_preserved_without_arbitrary_type_resolution():
    data = {"files": [dict(relative_path=p, classes=[unit("Shared", [method("Work")])])
                      for p in ["a.cpp", "b.cpp"]]}
    data["files"].append(dict(relative_path="c.cpp", classes=[unit("Caller", referenced_types=["Shared"])]))
    result = compute_metrics(data)
    assert len(result.class_index) == 3
    assert len(result.class_graph) == 3
    assert result.class_index["Caller"].fan_out == 0
    assert len({m.fqn for m in result.methods}) == 2


def test_generic_reference_is_resolved_before_stripping_type_parameters():
    result = compute_metrics(ast(unit("Game.Box"), unit("Game.Box<T>"),
                                 unit("Game.Caller", referenced_types=["Game.Box<T>"])))
    assert set(result.class_graph.successors("Game.Caller")) == {"Game.Box<T>"}


def test_external_qualified_type_never_connects_to_local_namesake():
    result = compute_metrics(ast(unit('Game.Widget'), unit('Game.Caller', referenced_types=['External.Widget'])))
    assert result.class_index['Game.Caller'].fan_out == 0


def test_large_finite_weights_do_not_overflow_normalization():
    result = compute_si_static(compute_metrics(ast(unit('A'))), {'cc': 1e308, 'coupling': 1e308})
    assert result.weights == {'cc': .5, 'coupling': .5}


def test_large_integer_weights_do_not_overflow_total_validation():
    result = compute_si_static(compute_metrics(ast(unit('A'))), {'cc': 10**308, 'coupling': 10**308})
    assert result.weights == {'cc': .5, 'coupling': .5}


def test_identical_classes_explicitly_report_uninformative_relative_ranking():
    scoring = scoring_to_dict(compute_si_static(compute_metrics(ast(unit("A"), unit("B"), unit("C")))))
    assert [c["si"] for c in scoring["class_scores"]] == [100, 100, 100]
    assert scoring["ranking_info"]["informative"] is False
    assert scoring["ranking_info"]["scope"] == "within_analysis_relative"
    assert scoring["ranking_info"]["largest_tie_fraction"] == 1


@pytest.mark.parametrize("weights", [dict(cc=1, coupling=-1), dict(unknown=1), dict(cc=0), dict(cc=float('nan')),
                                    dict(cc=True), dict(cc=10**400), [], 'invalid'])
def test_invalid_weights_fail_explicitly(weights):
    with pytest.raises(ValueError):
        compute_si_static(compute_metrics(ast(unit("A"))), weights)


@pytest.mark.parametrize('payload', ['null', '[]', '1', '"hello"', '{"cc": -1}', '{"cc": true}'])
def test_custom_weights_json_is_validated_before_analysis(payload, tmp_path):
    from game_si.cli import _resolve_weights
    path = tmp_path / 'weights.json'
    path.write_text(payload, encoding='utf-8')
    with pytest.raises(ValueError):
        _resolve_weights('custom', path)


def test_cli_rejects_invalid_weights_without_partial_analysis_outputs(tmp_path, capsys):
    from game_si.cli import main
    path = tmp_path / 'weights.json'
    path.write_text('null', encoding='utf-8')
    out = tmp_path / 'output'
    assert main(['analyze', str(Path(__file__).parent/'samples'/'IdentityCases.cs'),
                 '--weights', 'custom', '--weights-file', str(path), '--out', str(out)]) == 1
    assert not out.exists()
    assert '[error]' in capsys.readouterr().err


def test_comparison_ties_are_ordered_by_path():
    names = ["z.cs", "a.cs", "m.cs", "b.cs", "q.cs"]
    scoring = {"class_scores": [dict(file_path=n, si=100, grade="E") for n in names]}
    stats = {n: LizardFileStat(n, 1, 1, 1, 1, 0, "Work") for n in names}
    result = run_comparison(scoring, stats, "test", "", "", top_ns=(3,))
    assert [r.file_path for r in result.common_topN] == sorted(names)[:3]


def test_equal_size_cycles_are_serialized_in_stable_name_order():
    data = ast(unit('C', referenced_types=['D']), unit('D', referenced_types=['C']),
               unit('A', referenced_types=['B']), unit('B', referenced_types=['A']))
    cycles = metrics_to_dict(compute_metrics(data))['cycles']
    assert [c['members'] for c in cycles] == [['A', 'B'], ['C', 'D']]


def test_real_roslyn_preserves_generic_types_and_overload_call_identity():
    from game_si.analyzer import analyze
    data = analyze(Path(__file__).parent / "samples" / "IdentityCases.cs").data
    result = compute_metrics(data)
    assert "IdentityCases.Box" in result.class_index
    assert "IdentityCases.Box<T>" in result.class_index
    assert set(result.class_graph.successors("IdentityCases.Factory")) == {"IdentityCases.Box<T>"}
    work = result.class_index["IdentityCases.Worker"].methods
    assert [m.game_loop_centrality for m in work] == [.5, 0]
    assert result.class_index["IdentityCases.OtherWorker"].game_loop_centrality == 0
    local_work = result.class_index['IdentityCases.LocalLoop'].methods[1]
    assert local_work.game_loop_centrality == 0


def test_ablation_uses_same_file_population_and_reports_undefined_variants():
    from game_si.ablation import run_ablation
    from game_si.tune import CaseData
    from game_si.si import DEFAULT_WEIGHTS_STATIC
    rows = {f"{i}.cs": {k: float(i if k == 'cc' else 0) for k in DEFAULT_WEIGHTS_STATIC}
            for i in range(5)}
    case = CaseData("sample", rows, {f"{i}.cs": i for i in range(5)}, "project")
    result = run_ablation([case], top_n=2)
    assert result['variants']['default']['grouped_mean_rho'] == 1
    assert result['variants']['without_cc']['grouped_mean_rho'] is None
    assert result['variants']['without_cc']['cases']['sample']['matched_files'] == 5
    assert result['variants']['without_cc']['cases']['sample']['rho'] is None
    assert len(result['variants']) == 7


def test_ablation_class_pipeline_matches_real_scoring():
    from game_si.ablation import file_scores_for_weights
    from game_si.tune import CaseData
    from game_si.si import DEFAULT_WEIGHTS_STATIC
    data = ast(*(unit(f"C{i}", [dict(method('Work'), cyclomatic_complexity=i+1)]) for i in range(5)))
    for i, c in enumerate(data['files'][0]['classes']):
        data['files'].append(dict(relative_path=f'{i}.cs', classes=[c]))
    data['files'] = data['files'][1:]
    scoring = scoring_to_dict(compute_si_static(compute_metrics(data)))
    raw = {r['file_path']: [r['raw_exact']] for r in scoring['class_scores']}
    case = CaseData('sample', {f: r[0] for f, r in raw.items()}, {}, class_raw_by_file=raw)
    assert file_scores_for_weights(case, DEFAULT_WEIGHTS_STATIC) == {
        f['file_path']: f['si_max'] for f in scoring['file_scores']}


def test_dashboard_explains_all_tied_scores_without_absolute_quality_verdict():
    from game_si.report import _render_help_box, _render_health_hero
    result = compute_metrics(ast(unit('A'), unit('B')))
    view = _render_help_box() + _render_health_hero(compute_si_static(result), result)
    assert '절대 품질' in view
    assert '모두 동점' in view
    assert '안전 ·' not in view and 'E</span> 심각' not in view
    assert '코드베이스입니다' not in view
