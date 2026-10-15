"""Canonical CLI integration for the optional native backend (no AI calls)."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from game_si.cli import _build_parser, _print_analysis_status, main
from game_si.diagnostics import summarize_analysis


def native_library():
    library = os.environ.get("GAME_SI_TEST_CLANG_LIBRARY")
    if not library or not Path(library).is_file():
        pytest.skip("Set GAME_SI_TEST_CLANG_LIBRARY for native integration")
    pytest.importorskip("clang.cindex")
    return library


def project(tmp_path, text="int f(int x) { if (x) return 1; return 0; }\n"):
    source = tmp_path / "unit.cpp"
    source.write_text(text, encoding="utf-8")
    db = tmp_path / "compile_commands.json"
    db.write_text(json.dumps([{"directory": str(tmp_path), "file": "unit.cpp",
                               "arguments": ["clang++", "-std=c++17", "unit.cpp"]}]),
                  encoding="utf-8")
    return source, db


def run_cli(source, db, out, *extra):
    return subprocess.run([sys.executable, "-B", "-m", "game_si", "analyze", str(source),
                           "--lang", "cpp", "--cpp-backend", "clang",
                           "--compile-commands", str(db), "--clang-library", native_library(),
                           "--out", str(out), *extra], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=30)


def clang_data(tmp_path, severities=(), methods=True, errors=()):
    source, db = project(tmp_path)
    return {"backend": "clang", "analysis_unit": "implementation_file", "input_path": str(tmp_path),
            "runtime": {"native_version": "clang version 20.1.8", "library": "<lib>&"},
            "configuration": {"path": str(db), "sha256": "abc", "entries": [
                {"path": str(source), "entry_index": 0, "alternatives_count": 1,
                 "directory": str(tmp_path), "arguments": ["-DFLAG=<value>"]}],
                "unregistered_files": [str(tmp_path / "extra.cpp")]},
            "files": [{"path": str(source), "has_code": True, "classes": [
                {"methods": [{"name": "f"}] if methods else []}]}], "errors": list(errors),
            "diagnostics": [], "compiler_diagnostics": [
                {"input_path": str(source), "path": str(tmp_path / "header.hpp"),
                 "severity": severity, "line": 2, "message": "<bad>& diagnostic"}
                for severity in severities]}


def test_parser_defaults_and_analyze_only_options():
    parser = _build_parser()
    args = parser.parse_args(["analyze", "input"])
    assert args.cpp_backend == "tree-sitter"
    assert args.compile_commands is None and args.clang_library is None
    assert args.clang_timeout is None
    with pytest.raises(SystemExit):
        parser.parse_args(["timeseries", ".", "--lang", "cpp", "--out", ".", "--cpp-backend", "clang"])


@pytest.mark.parametrize("options", [
    ["--cpp-backend", "clang"],
    ["--cpp-backend", "clang", "--lang", "csharp", "--compile-commands", "missing.json"],
    ["--compile-commands", "missing.json"], ["--clang-library", "missing.dll"],
    ["--clang-timeout", "1"], ["--cpp-backend", "clang", "--clang-timeout", "nan"],
    ["--cpp-backend", "clang", "--clang-timeout", "inf"],
    ["--cpp-backend", "clang", "--clang-timeout", "0"],
    ["--cpp-backend", "clang", "--clang-timeout", "-1"],
])
def test_cli_rejects_irrelevant_or_invalid_options(tmp_path, options, capsys):
    source, db = project(tmp_path)
    if "--cpp-backend" in options and "--clang-timeout" in options:
        options = [*options, "--compile-commands", str(db)]
    assert main(["analyze", str(source), "--no-score", *options]) == 1
    if "--cpp-backend" in options and "--clang-timeout" in options:
        assert "--clang-timeout" in capsys.readouterr().err


@pytest.mark.parametrize("severities,state,error_files,warning_files", [
    ([], "complete", 0, 0), (["warning"], "complete", 0, 1),
    (["error"], "partial", 1, 0), (["fatal"], "partial", 1, 0),
    (["warning", "error", "fatal"], "partial", 1, 1),
])
def test_native_status_counts_originating_units(tmp_path, severities, state, error_files, warning_files):
    data = clang_data(tmp_path, severities)
    status = summarize_analysis(data, "cpp")
    assert status["state"] == state
    assert status["compiler_error_files"] == error_files
    assert status["compiler_warning_files"] == warning_files
    assert status["syntax_files"] == 0 and status["failed_files"] == 0
    assert status["registered_files"] == 1 and status["unregistered_files"] == 1
    assert status["configuration"] == data["configuration"]
    assert status["runtime"] == data["runtime"]
    assert status["backend"] == "clang" and status["analysis_unit"] == "implementation_file"
    if severities:
        assert status["compiler_diagnostics"][0]["input_path"] == "unit.cpp"
    limits = " ".join(status["limitations"])
    for word in ("파일", "헤더", "동적", "원시", "상대", "설정", "빌드"):
        assert word in limits


def test_native_status_requires_definitions_and_counts_only_worker_failures(tmp_path):
    data = clang_data(tmp_path, methods=False)
    assert summarize_analysis(data, "cpp")["state"] == "failed"
    data["files"][0]["classes"][0]["methods"] = [{"name": "f"}]
    data["errors"] = [{"path": str(tmp_path / "bad.cpp"), "kind": "worker", "message": "crash"}]
    status = summarize_analysis(data, "cpp")
    assert status["state"] == "partial" and status["failed_files"] == 1


def test_native_console_diagnostics_are_capped_and_separate(tmp_path):
    status = summarize_analysis(clang_data(tmp_path, ["warning"] * 25), "cpp")
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        _print_analysis_status(status)
    assert "clang" in out.getvalue()
    assert "구현 파일" in out.getvalue()
    assert err.getvalue().count("<bad>& diagnostic") == 20
    assert "ast.json" in err.getvalue() and "compiler_diagnostics" in err.getvalue()


def test_advisor_omits_macro_methods_and_preserves_normal_selection(tmp_path):
    from game_si.advisor import _select_top_method, _build_snippet
    source, _ = project(tmp_path)
    normal = {"name": "normal", "cyclomatic_complexity": 2, "loc": 1, "start_line": 1, "end_line": 1}
    macro = {**normal, "name": "macro", "cyclomatic_complexity": 90, "is_macro_generated": True}
    assert _select_top_method({"methods": [macro, normal]}) is normal
    assert _select_top_method({"methods": [macro]}) is None
    data = {"files": [{"path": str(source), "classes": [{"fully_qualified_name": "f", "methods": [macro]}]}]}
    assert _build_snippet(data, "f") == ("", None)
    data["files"][0]["classes"][0]["methods"].append(normal)
    assert _build_snippet(data, "f")[1] == "normal"


@pytest.mark.parametrize("text,exit_code,state", [
    ("int f() { return 1; }\n", 0, "complete"),
    ('#warning example\nint f() { return 1; }\n', 0, "complete"),
    ('#error example\nint f() { return 1; }\n', 3, "partial"),
    ('int declaration_only();\n', 1, "failed"),
    ('#include "missing.h"\nint f() { return 1; }\n', 3, "partial"),
])
def test_canonical_native_cli_real_status_and_outputs(tmp_path, text, exit_code, state):
    source, db = project(tmp_path, text)
    out = tmp_path / "out"
    result = run_cli(source, db, out)
    assert result.returncode == exit_code, result.stdout + result.stderr
    ast = json.loads((out / "ast.json").read_text(encoding="utf-8"))
    status = json.loads((out / "analysis_status.json").read_text(encoding="utf-8"))
    assert ast["backend"] == "clang" and status["state"] == state
    assert status["analysis_unit"] == "implementation_file"
    if state != "failed":
        scoring = json.loads((out / "scoring.json").read_text(encoding="utf-8"))
        assert scoring["analysis_status"] == status
        assert (out / "metrics.json").is_file() and (out / "index.html").is_file()
        assert len(scoring["class_scores"]) == 1
    else:
        assert not (out / "scoring.json").exists()


def test_native_dashboard_uses_file_units_without_rewriting_user_content(tmp_path):
    source, db = project(tmp_path)
    result = run_cli(source, db, tmp_path / "out", "--project-name", "클래스 프로젝트 & <sample>")
    assert result.returncode == 0, result.stderr
    view = (tmp_path / "out" / "index.html").read_text(encoding="utf-8")
    assert "분석 구현 파일" in view and "구현 파일 FQN" in view
    assert "클래스 프로젝트 &amp; &lt;sample&gt;" in view
    assert '"project": "클래스 프로젝트 & <sample>"' in view
    assert "분석 클래스" not in view and "이 클래스" not in view
    assert '<details class="help">' in view
    from game_si.report import _render_analysis_status
    status_view = _render_analysis_status(summarize_analysis(clang_data(tmp_path, ["warning", "error"]), "cpp"))
    assert "컴파일 오류" in status_view and "컴파일 경고" in status_view
    assert "등록" in status_view and "미등록" in status_view
    assert 'data-tooltip=' in status_view and '왜 부분 분석인가요?' in status_view
    assert '<bad>& diagnostic' not in status_view
    assert '<lib>&' not in status_view and 'entry_index' not in status_view


@pytest.mark.parametrize("failure", ["missing", "malformed", "intersection", "library"])
def test_native_cli_configuration_failures_mark_stale_outputs(tmp_path, failure):
    source, db = project(tmp_path)
    out = tmp_path / "out"
    assert run_cli(source, db, out).returncode == 0
    library = native_library()
    if failure == "missing":
        db = tmp_path / "absent.json"
    elif failure == "malformed":
        db.write_text("{}", encoding="utf-8")
    elif failure == "intersection":
        db.write_text("[]", encoding="utf-8")
    else:
        library = str(tmp_path / "missing.dll")
    args = ["analyze", str(source), "--lang", "cpp", "--cpp-backend", "clang",
            "--compile-commands", str(db), "--clang-library", library, "--out", str(out)]
    assert main(args) == 1
    assert json.loads((out / "analysis_status.json").read_text(encoding="utf-8"))["state"] == "failed"
    assert json.loads((out / "scoring.json").read_text(encoding="utf-8"))["analysis_status"]["state"] == "failed"
    assert "최신 실행 실패" in (out / "index.html").read_text(encoding="utf-8")


def test_native_save_failure_returns_failed(tmp_path):
    source, db = project(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "ast.json").mkdir()
    result = run_cli(source, db, out)
    assert result.returncode == 1 and "이번 실행은 성공하지 않았" in result.stderr


def test_optional_dependency_is_binding_only():
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert 'clang = ["clang>=20,<21"]' in text


@pytest.mark.parametrize("failure", ["configuration", "library", "save"])
def test_new_native_failure_records_failed_status(tmp_path, failure):
    source, db = project(tmp_path)
    out = tmp_path / "out"
    library = native_library()
    if failure == "configuration":
        db.write_text("[]", encoding="utf-8")
    elif failure == "library":
        library = str(tmp_path / "missing.dll")
    else:
        out.mkdir()
        (out / "ast.json").mkdir()
    assert main(["analyze", str(source), "--lang", "cpp", "--cpp-backend", "clang",
                 "--compile-commands", str(db), "--clang-library", library,
                 "--out", str(out)]) == 1
    status = json.loads((out / "analysis_status.json").read_text(encoding="utf-8"))
    assert status["state"] == "failed" and status["backend"] == "clang"
    assert status["failure_reason"]


def test_legacy_default_and_explicit_backend_outputs_match(tmp_path):
    source, _ = project(tmp_path)
    outputs = []
    statuses = []
    for index, options in enumerate(([], ["--cpp-backend", "tree-sitter"])):
        out = tmp_path / f"out{index}"
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            assert main(["analyze", str(source), "--lang", "cpp", "--out", str(out), *options]) == 0
        ast = json.loads((out / "ast.json").read_text(encoding="utf-8"))
        assert "backend" not in ast
        statuses.append(json.loads((out / "analysis_status.json").read_text(encoding="utf-8")))
        outputs.append(json.loads((out / "scoring.json").read_text(encoding="utf-8")))
        assert "classes=" in stream.getvalue() and "implementation_files=" not in stream.getvalue()
        view = (out / "index.html").read_text(encoding="utf-8")
        assert "분석 클래스" in view and "구현 파일 FQN" not in view
    assert outputs[0] == outputs[1] and statuses[0] == statuses[1]


def test_native_multifile_dependencies_cycle_and_unregistered_scope(tmp_path):
    source, db = project(tmp_path, "int g(); int f() { return g(); }\n")
    other = tmp_path / "클래스.cpp"
    other.write_text("int f(); int g() { return f(); }\n", encoding="utf-8")
    (tmp_path / "unselected.cpp").write_text("int extra() { return 1; }\n", encoding="utf-8")
    entries = json.loads(db.read_text(encoding="utf-8"))
    entries.append({"directory": str(tmp_path), "file": other.name,
                    "arguments": ["clang++", "-std=c++17", other.name]})
    entries.append({**entries[0], "arguments": ["clang++", "-DFEATURE=1", source.name]})
    db.write_text(json.dumps(entries), encoding="utf-8")
    out = tmp_path / "out"
    result = run_cli(tmp_path, db, out)
    assert result.returncode == 0, result.stderr
    ast = json.loads((out / "ast.json").read_text(encoding="utf-8"))
    assert ast["configuration"]["entries"][0]["alternatives_count"] == 1
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    assert len(metrics["cycles"]) == 1
    view = (out / "index.html").read_text(encoding="utf-8")
    assert '"fqn": "clang.file.클래스.cpp"' in view
    assert "그래프 안 구현 파일 검색" in view
    assert "개 구현 파일</strong>" in view and "미등록 1개" in view
    assert any(Path(p).name == 'unselected.cpp' for p in ast['configuration']['unregistered_files'])
    assert ast['configuration']['entries'][0]['entry_index'] == 0
    assert 'entry_index=' not in view and 'alternatives_count=' not in view
    assert "클래스 FQN" not in view


def test_native_macro_methods_never_become_advisor_source_snippets(tmp_path):
    source, db = project(tmp_path, "#define BODY(name) int name(int x) { if (x) return 1; return 0; }\nBODY(generated)\nint normal() { return 1; }\n")
    result = run_cli(source, db, tmp_path / "out", "--no-score")
    assert result.returncode == 0, result.stderr
    ast = json.loads((tmp_path / "out" / "ast.json").read_text(encoding="utf-8"))
    from game_si.advisor import _build_snippet
    cls = ast["files"][0]["classes"][0]
    assert any(m["is_macro_generated"] for m in cls["methods"])
    snippet, name = _build_snippet(ast, cls["fully_qualified_name"])
    assert name == "normal" and snippet.startswith("int normal")


@pytest.mark.parametrize("all_failed", [False, True])
def test_canonical_native_cli_worker_failure_only_at_process_boundary(tmp_path, monkeypatch, all_failed):
    import game_si.clang_analyzer as analyzer
    source, db = project(tmp_path)
    other = tmp_path / "other.cpp"
    other.write_text("int other() { return 2; }\n", encoding="utf-8")
    entries = json.loads(db.read_text(encoding="utf-8"))
    entries.append({"directory": str(tmp_path), "file": "other.cpp", "arguments": ["clang++", "other.cpp"]})
    db.write_text(json.dumps(entries), encoding="utf-8")
    actual = analyzer._run_worker
    def worker(payload, timeout):
        if payload["action"] == "parse" and (all_failed or Path(payload["path"]).name == "other.cpp"):
            raise RuntimeError("worker crashed <details>")
        return actual(payload, timeout)
    monkeypatch.setattr(analyzer, "_run_worker", worker)
    out = tmp_path / "out"
    assert main(["analyze", str(tmp_path), "--lang", "cpp", "--cpp-backend", "clang",
                 "--compile-commands", str(db), "--clang-library", native_library(), "--out", str(out)]) == (1 if all_failed else 3)
    status = json.loads((out / "analysis_status.json").read_text(encoding="utf-8"))
    assert status["failed_files"] == (2 if all_failed else 1)
    assert status["state"] == ("failed" if all_failed else "partial")
    if not all_failed:
        view = (out / "index.html").read_text(encoding="utf-8")
        assert '접근·추출 실패 1개' in view and 'worker crashed <details>' not in view
        assert 'worker crashed <details>' in status['errors'][0]['message']


@pytest.mark.parametrize("no_score", [False, True])
def test_native_console_top_labels_are_file_units_and_functions(tmp_path, no_score):
    source, db = project(tmp_path)
    extra = ["--no-score"] if no_score else []
    result = run_cli(source, db, tmp_path / "out", "--top", "1", *extra)
    assert result.returncode == 0, result.stderr
    label = "functions by Cyclomatic Complexity" if no_score else "implementation files by G-SI-Static"
    assert label in result.stdout
    assert "classes by" not in result.stdout
    if not no_score:
        assert "file_edges=" in result.stdout and "class_edges=" not in result.stdout


@pytest.mark.parametrize("filename", ["metrics.json", "scoring.json", "index.html"])
def test_native_later_save_failure_marks_status_failed(tmp_path, monkeypatch, filename):
    source, db = project(tmp_path)
    original = Path.write_text
    def write(path, *args, **kwargs):
        if path.name == filename:
            raise OSError("결과 저장 실패 <sample>")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "write_text", write)
    out = tmp_path / "out"
    assert main(["analyze", str(source), "--lang", "cpp", "--cpp-backend", "clang",
                 "--compile-commands", str(db), "--clang-library", native_library(), "--out", str(out)]) == 1
    status = json.loads((out / "analysis_status.json").read_text(encoding="utf-8"))
    assert status["state"] == "failed" and "저장 실패" in status["failure_reason"]
    if filename == "index.html":
        assert json.loads((out / "scoring.json").read_text(encoding="utf-8"))["analysis_status"]["state"] == "failed"


def test_native_header_diagnostics_count_two_originating_units(tmp_path):
    source, db = project(tmp_path, '#include "context.hpp"\nint f() { return 1; }\n')
    header = tmp_path / "context.hpp"
    header.write_text('#warning header_warning\n#error header_error\n', encoding="utf-8")
    other = tmp_path / "other.cpp"
    other.write_text('#include "context.hpp"\nint g() { return 2; }\n', encoding="utf-8")
    entries = json.loads(db.read_text(encoding="utf-8"))
    entries.append({"directory": str(tmp_path), "file": other.name, "arguments": ["clang++", other.name]})
    db.write_text(json.dumps(entries), encoding="utf-8")
    out = tmp_path / "out"
    result = run_cli(tmp_path, db, out)
    assert result.returncode == 3, result.stderr
    status = json.loads((out / "analysis_status.json").read_text(encoding="utf-8"))
    assert status["compiler_error_files"] == 2 and status["compiler_warning_files"] == 2
    assert status["failed_files"] == 0 and status["syntax_files"] == 0
    assert {d["path"] for d in status["compiler_diagnostics"]} == {"context.hpp"}


def test_native_c_language_without_outputs_uses_native_backend(tmp_path, capsys):
    source, db = project(tmp_path)
    c_source = tmp_path / "unit.c"
    source.rename(c_source)
    db.write_text(json.dumps([{"directory": str(tmp_path), "file": c_source.name,
                               "arguments": ["clang", "-std=c11", c_source.name]}]), encoding="utf-8")
    assert main(["analyze", str(c_source), "--lang", "c", "--cpp-backend", "clang",
                 "--compile-commands", str(db), "--clang-library", native_library(), "--no-score"]) == 0
    assert "clang · 구현 파일 단위" in capsys.readouterr().out


@pytest.mark.parametrize("previous_backend", ["tree-sitter", "clang"])
def test_native_early_failure_replaces_prior_run_status_metadata(tmp_path, previous_backend):
    source, db = project(tmp_path)
    out = tmp_path / "out"
    if previous_backend == "clang":
        source.write_text('#warning previous_warning\nint previous() { return 1; }\n', encoding="utf-8")
        assert run_cli(source, db, out).returncode == 0
    else:
        assert main(["analyze", str(source), "--lang", "cpp", "--out", str(out)]) == 0
    previous_ast = (out / "ast.json").read_bytes()
    assert main(["analyze", str(source), "--lang", "cpp", "--cpp-backend", "clang",
                 "--compile-commands", str(tmp_path / "missing.json"), "--out", str(out)]) == 1
    status = json.loads((out / "analysis_status.json").read_text(encoding="utf-8"))
    assert status["state"] == "failed" and status["backend"] == "clang"
    assert status["analysis_unit"] == "implementation_file"
    assert status["analyzed_files"] == status["registered_files"] == status["unregistered_files"] == 0
    assert status["compiler_error_count"] == status["compiler_warning_count"] == 0
    assert status["runtime"] == {} and status["configuration"].get("entries", []) == []
    assert status["compiler_diagnostics"] == [] and "missing.json" in status["failure_reason"]
    assert (out / "ast.json").read_bytes() == previous_ast
    assert json.loads((out / "scoring.json").read_text(encoding="utf-8"))["analysis_status"] == status
    assert "최신 실행 실패" in (out / "index.html").read_text(encoding="utf-8")


def test_native_save_failure_preserves_current_attempt_provenance_after_previous_run(tmp_path, monkeypatch):
    source, db = project(tmp_path)
    out = tmp_path / "out"
    assert run_cli(source, db, out).returncode == 0
    source.write_text("int current() { return 2; } int another() { return 3; }\n", encoding="utf-8")
    entries = json.loads(db.read_text(encoding="utf-8"))
    entries[0]["arguments"] = ["clang++", "-DCURRENT=1", source.name]
    db.write_text(json.dumps(entries), encoding="utf-8")
    original = Path.write_text
    def write(path, *args, **kwargs):
        if path.name == "index.html":
            raise OSError("current dashboard save failed")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "write_text", write)
    assert main(["analyze", str(source), "--lang", "cpp", "--cpp-backend", "clang",
                 "--compile-commands", str(db), "--clang-library", native_library(), "--out", str(out)]) == 1
    status = json.loads((out / "analysis_status.json").read_text(encoding="utf-8"))
    current_ast = json.loads((out / "ast.json").read_text(encoding="utf-8"))
    assert status["state"] == "failed" and status["analyzed_files"] == status["registered_files"] == 1
    assert status["configuration"] == current_ast["configuration"]
    assert status["runtime"] == current_ast["runtime"]
    assert "-DCURRENT=1" in status["configuration"]["entries"][0]["arguments"]
    assert status["failure_reason"] == "current dashboard save failed"


def test_native_early_weight_failure_records_latest_native_attempt(tmp_path):
    source, db = project(tmp_path)
    out = tmp_path / "out"
    assert main(["analyze", str(source), "--lang", "cpp", "--out", str(out)]) == 0
    assert main(["analyze", str(source), "--lang", "cpp", "--cpp-backend", "clang",
                 "--compile-commands", str(db), "--out", str(out), "--weights", "custom"]) == 1
    status = json.loads((out / "analysis_status.json").read_text(encoding="utf-8"))
    assert status["backend"] == "clang" and status["analyzed_files"] == 0
    assert status["state"] == "failed" and "weights" in status["failure_reason"]
