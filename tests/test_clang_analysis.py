"""Optional compiler backend: configuration, isolation, and real tiny sources."""

import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def database(tmp_path, arguments=None, entries=None):
    source = tmp_path / "unit.cpp"
    source.write_text("int f() { return 1; }\n", encoding="utf-8")
    db = tmp_path / "compile_commands.json"
    if entries is None:
        entries = [{"directory": ".", "file": "unit.cpp",
                    "arguments": arguments or ["clang++", "-c", "unit.cpp"]}]
    db.write_text(json.dumps(entries), encoding="utf-8")
    return source, db


def config(root, db):
    return importlib.import_module("game_si.clang_config").load_configuration(root, db)


def test_configuration_resolves_paths_and_records_first_duplicate(tmp_path):
    source, db = database(tmp_path, entries=[
        {"directory": ".", "file": "unit.cpp", "arguments": [
            "clang++", "-Iinc", "-include", "forced.h", "-DFEATURE=1",
            "-std=c++17", "-c", "unit.cpp", "-o", "unit.o"]},
        {"directory": ".", "file": "unit.cpp", "arguments": [
            "clang++", "-DFEATURE=2", "unit.cpp"]},
        {"directory": ".", "file": "outside.cpp", "command": "unsafe shell"},
    ])
    unregistered = tmp_path / "extra.c"
    unregistered.write_text("int extra;\n", encoding="utf-8")
    result = config(tmp_path, db)
    entry = result["entries"][0]
    assert entry["path"] == str(source.resolve())
    assert entry["directory"] == str(tmp_path.resolve())
    assert entry["arguments"] == ["-I" + str((tmp_path / "inc").resolve()),
                                  "-include", str((tmp_path / "forced.h").resolve()),
                                  "-DFEATURE=1", "-std=c++17"]
    assert entry["entry_index"] == 0
    assert entry["alternatives_count"] == 1
    assert result["sha256"] == hashlib.sha256(db.read_bytes()).hexdigest()
    assert result["unregistered_files"] == [str(unregistered.resolve())]


@pytest.mark.parametrize("arguments", [
    ["ccache", "clang++", "unit.cpp"], ["sh", "-c", "clang++ unit.cpp"],
    ["clang++", "@flags.rsp", "unit.cpp"],
    ["clang++", "-fplugin=evil.dll", "unit.cpp"],
    ["clang++", "-Xclang", "-load", "evil.dll", "unit.cpp"],
    ["clang++", "-Xpreprocessor", "-fplugin=evil.dll", "unit.cpp"],
    ["clang++", "-DVALUE=$(cmd)", "unit.cpp"],
    ["clang++", "unit.cpp;", "unit.cpp"],
    ["clang++", "-unknown-option", "unit.cpp"],
])
def test_configuration_rejects_untrusted_arguments(tmp_path, arguments):
    _, db = database(tmp_path, arguments)
    with pytest.raises(ValueError):
        config(tmp_path, db)


def test_configuration_rejects_command_only_and_empty_intersection(tmp_path):
    source, db = database(tmp_path, entries=[
        {"directory": ".", "file": "unit.cpp", "command": "clang++ unit.cpp"}])
    with pytest.raises(ValueError, match="arguments"):
        config(source, db)
    db.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="intersection|등록|교집합"):
        config(source, db)


@pytest.mark.parametrize("contents", ["not json", "{}", '[{"file":"unit.cpp"}]'])
def test_configuration_rejects_malformed_database(tmp_path, contents):
    source, db = database(tmp_path)
    db.write_text(contents, encoding="utf-8")
    with pytest.raises(ValueError):
        config(source, db)


def test_configuration_missing_database_and_excluded_sources(tmp_path):
    source, db = database(tmp_path)
    with pytest.raises(ValueError):
        config(source, tmp_path / "missing.json")
    excluded = tmp_path / "build"
    excluded.mkdir()
    (excluded / "hidden.cpp").write_text("int hidden;", encoding="utf-8")
    db.write_text(json.dumps([{"directory": ".", "file": "build/hidden.cpp",
                               "arguments": ["clang++", "build/hidden.cpp"]}]),
                  encoding="utf-8")
    module = importlib.import_module("game_si.clang_config")
    with pytest.raises(ValueError):
        module.load_configuration(tmp_path, db)


def analyze(*args, **kwargs):
    return importlib.import_module("game_si.clang_analyzer").analyze_clang(*args, **kwargs)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), "bad"])
def test_invalid_timeout_is_configuration_error(tmp_path, timeout):
    source, db = database(tmp_path)
    with pytest.raises(ValueError, match="timeout"):
        analyze(source, db, timeout=timeout)


def test_missing_explicit_library_is_actionable(tmp_path):
    source, db = database(tmp_path)
    with pytest.raises(RuntimeError, match="Clang|clang|libclang"):
        analyze(source, db, clang_library=tmp_path / "missing.dll")


@pytest.fixture
def native_library():
    library = os.environ.get("GAME_SI_TEST_CLANG_LIBRARY")
    if not library or not Path(library).is_file():
        pytest.skip("Optional native Clang runtime unavailable; set GAME_SI_TEST_CLANG_LIBRARY.")
    try:
        from clang import cindex  # noqa: F401
    except ImportError:
        pytest.skip("Optional Clang Python bindings unavailable.")
    return Path(library)


@pytest.fixture
def native_project(tmp_path):
    fixture = Path(__file__).parent / "samples" / "clang"
    for path in fixture.iterdir():
        shutil.copy2(path, tmp_path / path.name)
    entries = [{"directory": ".", "file": name, "arguments": [
        "clang" if name.endswith(".c") else "clang++", "-I.", "-DFEATURE=1",
        "-std=c11" if name.endswith(".c") else "-std=c++17", "-c", name]}
        for name in ["main.cpp", "provider.cpp", "simple.c"]]
    db = tmp_path / "compile_commands.json"
    db.write_text(json.dumps(entries), encoding="utf-8")
    return tmp_path, db


def methods(result):
    return [m for f in result.data["files"] for c in f["classes"] for m in c["methods"]]


def test_real_cpp_identity_macro_context_and_file_graph(native_project, native_library):
    root, db = native_project
    result = analyze(root, db, clang_library=native_library)
    assert not result.errors
    assert not result.data["compiler_diagnostics"]
    assert result.data["backend"] == "clang"
    assert result.data["analysis_unit"] == "implementation_file"
    assert isinstance(result.data["runtime"]["native_version"], str)
    assert "clang" in result.data["runtime"]["native_version"].lower()
    all_methods = methods(result)
    names = [m["name"] for m in all_methods]
    assert "Inline" not in names and "inactive" not in names
    assert {"alpha", "beta", "Node", "~Node", "Update", "active", "over", "c_macro", "c_loop"} <= set(names)
    overloads = [m for m in all_methods if m["name"] == "over"]
    assert len(overloads) == len({m["symbol_id"] for m in overloads}) == 2
    assert all(method["symbol_id"] == method["raw_symbol_id"] for method in overloads)
    update = next(m for m in all_methods if m["name"] == "Update")
    assert update["owner_fully_qualified_name"] == "N::Node"
    assert update["fully_qualified_name"] == "N::Node::Update"
    assert update["owner_symbol_id"]
    assert update["cyclomatic_complexity"] == 11
    assert update["start_line"] == 10 and update["end_line"] == 24
    assert {m["symbol_id"] for m in overloads} <= set(update["invoked_symbols"])
    assert update["indirect_call_count"] == 1
    for name, macro_name in [("alpha", "MAKE_ALPHA"), ("beta", "MAKE_BETA")]:
        macro = next(m for m in all_methods if m["name"] == name)
        assert macro["is_macro_generated"]
        assert macro["macro_expansions"][0]["name"] == macro_name
        assert macro["macro_expansions"][0]["invocation_line"] == macro["start_line"]
    units = {f["relative_path"]: f["classes"][0] for f in result.data["files"]}
    assert all(len(f["classes"]) == 1 for f in result.data["files"])
    assert "clang.file.provider.cpp" in units["main.cpp"]["referenced_types"]
    assert any("global_state" in ref for ref in units["main.cpp"]["static_member_accesses"])
    assert any("counter" in ref for ref in units["main.cpp"]["static_member_accesses"])
    assert all("local" not in ref for ref in units["main.cpp"]["static_member_accesses"])
    assert next(m for m in all_methods if m["name"] == "c_loop")["cyclomatic_complexity"] == 7
    from game_si.metrics import compute_metrics
    metrics = compute_metrics(result.data)
    assert metrics.class_graph.has_edge("clang.file.main.cpp", "clang.file.provider.cpp")
    repeat = analyze(root, db, clang_library=native_library)
    assert result.data["files"] == repeat.data["files"]


@pytest.mark.parametrize("source", [
    '#include "missing_header.h"\nint recovered() { return 1; }\n',
    'int good() { return 1; }\nint broken() { return unknown_value; }\n',
    'int good() { return 1; }\nint broken() { return ; }\n',
])
def test_native_diagnostics_keep_recovered_methods(tmp_path, native_library, source):
    path, db = database(tmp_path)
    path.write_text(source, encoding="utf-8")
    result = analyze(path, db, clang_library=native_library)
    assert not result.errors
    diagnostics = result.data["compiler_diagnostics"]
    assert any(d["severity"] in {"error", "fatal"} for d in diagnostics)
    assert all(d["input_path"] == str(path.resolve()) for d in diagnostics)
    assert any(m["name"] in {"good", "recovered"} for m in methods(result))
    assert result.data["diagnostics"] == []


@pytest.mark.parametrize("failure", ["crash", "timeout", "json"])
def test_worker_failures_are_isolated_to_each_file(tmp_path, monkeypatch, failure):
    source, db = database(tmp_path)
    module = importlib.import_module("game_si.clang_analyzer")
    seen = []
    def fake_run(command, **kwargs):
        seen.append((command, kwargs))
        payload = json.loads(kwargs["input"])
        if payload["action"] == "runtime":
            return subprocess.CompletedProcess(command, 0, json.dumps({
                "runtime": {"native_version": "test boundary"}}), "")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return subprocess.CompletedProcess(command, 7 if failure == "crash" else 0,
                                           "invalid JSON", "worker crashed")
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    reported = []
    result = analyze(source, db, progress=lambda *step: reported.append(step))
    assert reported == [(1, 1, source.name)]   # a file that failed still counts as read
    assert len(result.errors) == 1
    assert result.errors[0]["path"] == str(source.resolve())
    assert result.data["summary"]["total_files"] == 0
    assert all(command[:3] == [sys.executable, "-B", "-m"] and
               kwargs["shell"] is False for command, kwargs in seen)


def test_result_save_failure_is_not_reported_as_success(native_project, native_library):
    root, db = native_project
    with pytest.raises((OSError, RuntimeError)):
        analyze(root, db, output_path=root, clang_library=native_library)


def test_preprocessing_flags_and_equals_include_paths_are_preserved(tmp_path):
    source, db = database(tmp_path, ["clang++", "-fno-char8_t", "-fchar8_t",
                                   "-fPIC", "-fPIE", "-resource-dir=resource",
                                   "-isysroot=sdk", "unit.cpp"])
    entry = config(source, db)["entries"][0]
    assert entry["arguments"] == ["-fno-char8_t", "-fchar8_t", "-fPIC", "-fPIE",
                                  "-resource-dir", str((tmp_path / "resource").resolve()),
                                  "-isysroot", str((tmp_path / "sdk").resolve())]


def test_only_first_duplicate_configuration_is_validated(tmp_path):
    source, db = database(tmp_path, entries=[
        {"directory": ".", "file": "unit.cpp", "arguments": ["clang++", "unit.cpp"]},
        {"directory": ".", "file": "unit.cpp", "arguments": ["ccache", "@unsafe.rsp"]},
        {"file": "unrelated.cpp", "command": "unsafe"},
    ])
    entry = config(source, db)["entries"][0]
    assert entry["alternatives_count"] == 1 and entry["arguments"] == []


def test_relative_database_directory_is_based_on_database_location(tmp_path):
    source, db = database(tmp_path)
    build_dir = tmp_path / "config"
    build_dir.mkdir()
    nested_db = build_dir / "compile_commands.json"
    nested_db.write_text(json.dumps([{"directory": "..", "file": "unit.cpp", "arguments": [
        "clang++", "-Iheaders", "-include", "forced.h", str(source)]}]), encoding="utf-8")
    entry = config(source, nested_db)["entries"][0]
    assert entry["arguments"] == ["-I" + str((tmp_path / "headers").resolve()),
                                  "-include", str((tmp_path / "forced.h").resolve())]


def test_native_pic_macro_context_and_range_for_policy(tmp_path, native_library):
    source, db = database(tmp_path, ["clang++", "-fPIC", "-std=c++17", "unit.cpp"])
    source.write_text('#ifdef __PIC__\nint pic_enabled() { return 1; }\n#endif\n'
                      'int ranged() { int items[2]={1,2}; for (int x : items) { if (x) return x; } return 0; }\n',
                      encoding="utf-8")
    result = analyze(source, db, clang_library=native_library)
    assert not result.errors
    by_name = {m["name"]: m for m in methods(result)}
    assert "pic_enabled" in by_name
    assert by_name["ranged"]["cyclomatic_complexity"] == 2


def test_existing_but_invalid_native_library_fails_preflight(tmp_path, native_library):
    source, db = database(tmp_path)
    library = tmp_path / "not-a-library.dll"
    library.write_text("not executable", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Clang.*초기화|libclang"):
        analyze(source, db, clang_library=library)


def test_worker_failure_does_not_prevent_next_real_file(tmp_path, native_library, monkeypatch):
    source, db = database(tmp_path, entries=[
        {"directory": ".", "file": "unit.cpp", "arguments": ["clang++", "unit.cpp"]},
        {"directory": ".", "file": "z.cpp", "arguments": ["clang++", "z.cpp"]},
    ])
    second = tmp_path / "z.cpp"
    second.write_text("int survives() { return 2; }", encoding="utf-8")
    module = importlib.import_module("game_si.clang_analyzer")
    real_run = module.subprocess.run
    def crashing_run(command, **kwargs):
        request = json.loads(kwargs["input"])
        if request.get("path") == str(source):
            return subprocess.CompletedProcess(command, 11, "", "native crash")
        return real_run(command, **kwargs)
    monkeypatch.setattr(module.subprocess, "run", crashing_run)
    result = analyze(tmp_path, db, clang_library=native_library)
    assert len(result.errors) == 1
    assert [m["name"] for m in methods(result)] == ["survives"]


def test_worker_valid_json_with_invalid_schema_is_file_error(tmp_path, monkeypatch):
    source, db = database(tmp_path)
    module = importlib.import_module("game_si.clang_analyzer")
    def invalid_schema(command, **kwargs):
        request = json.loads(kwargs["input"])
        response = {"runtime": {"native_version": "boundary"}} if request["action"] == "runtime" else {
            "file": {"path": str(source), "classes": [{"methods": []}]}, "compiler_diagnostics": []}
        return subprocess.CompletedProcess(command, 0, json.dumps(response), "")
    monkeypatch.setattr(module.subprocess, "run", invalid_schema)
    result = analyze(source, db)
    assert len(result.errors) == 1 and result.data["files"] == []


def test_source_read_failure_is_file_error(tmp_path, monkeypatch):
    source, db = database(tmp_path)
    module = importlib.import_module("game_si.clang_analyzer")
    monkeypatch.setattr(module, "_run_worker", lambda payload, timeout: {
        "runtime": {"native_version": "boundary"}})
    real_read = Path.read_bytes
    def denied_read(path):
        if path == source:
            raise PermissionError("source denied")
        return real_read(path)
    monkeypatch.setattr(Path, "read_bytes", denied_read)
    result = analyze(source, db)
    assert result.errors[0]["message"] == "source denied"


def test_external_name_does_not_make_false_local_call_edge(tmp_path, native_library):
    source, db = database(tmp_path, entries=[
        {"directory": ".", "file": "unit.cpp", "arguments": ["clang++", "unit.cpp"]},
        {"directory": ".", "file": "other.cpp", "arguments": ["clang++", "other.cpp"]},
    ])
    source.write_text("namespace External { int helper(); }\nint MainLoop() { return External::helper(); }",
                      encoding="utf-8")
    (tmp_path / "other.cpp").write_text("static int helper() { return 0; }", encoding="utf-8")
    result = analyze(tmp_path, db, clang_library=native_library)
    from game_si.metrics import compute_metrics
    computed = compute_metrics(result.data)
    other = next(m for m in computed.methods if m.name == "helper")
    assert other.game_loop_centrality == 0
    entry = next(m for m in methods(result) if m["name"] == "MainLoop")
    assert entry["external_call_count"] == 1


@pytest.mark.parametrize("flag", ["-load", "-loadevil", "-plugin=evil", "-Wl,-load,evil",
                                  "-Wl,-plugin,evil", "-fpass-plugin=evil"])
def test_loader_flags_are_rejected_even_when_shaped_like_link_options(tmp_path, flag):
    source, db = database(tmp_path, ["clang++", flag, "unit.cpp"])
    with pytest.raises(ValueError):
        config(source, db)


def test_static_storage_default_args_virtual_calls_and_parameter_types(tmp_path, native_library):
    source, db = database(tmp_path, entries=[
        {"directory": ".", "file": "unit.cpp", "arguments": ["clang++", "-std=c++17", "unit.cpp"]},
        {"directory": ".", "file": "owner.cpp", "arguments": ["clang++", "-std=c++17", "owner.cpp"]},
    ])
    (tmp_path / "owner.hpp").write_text('struct Owner { static int work(); virtual int choose(); };',
                                        encoding="utf-8")
    (tmp_path / "owner.cpp").write_text('#include "owner.hpp"\nint Owner::work() { return 1; }\n'
                                        'int Owner::choose() { return 2; }', encoding="utf-8")
    source.write_text('#include "owner.hpp"\nint f(Owner *owner, int x = true ? 1 : 2) {\n'
                      'static int shared; int ordinary = 0; shared++;\n'
                      'return owner->choose() + shared + ordinary; }', encoding="utf-8")
    result = analyze(tmp_path, db, clang_library=native_library)
    assert not result.errors
    by_name = {m["name"]: m for m in methods(result)}
    assert by_name["f"]["cyclomatic_complexity"] == 1
    assert by_name["work"]["is_static"]
    assert any(call["dispatch"] == "compile_time_virtual" for call in by_name["f"]["calls"])
    unit = next(f["classes"][0] for f in result.data["files"] if f["relative_path"] == "unit.cpp")
    assert sum("shared" in access for access in unit["static_member_accesses"]) == 2
    assert all("ordinary" not in access for access in unit["static_member_accesses"])
    assert "clang.file.owner.cpp" in unit["referenced_types"]
    assert by_name["f"]["referenced_type_symbols"]


def test_synthetic_unit_ids_preserve_distinct_relative_paths(tmp_path, native_library):
    first = tmp_path / "a.b" / "c.cpp"
    second = tmp_path / "a" / "b.c.cpp"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("int first() { return 1; }", encoding="utf-8")
    second.write_text("int second() { return 2; }", encoding="utf-8")
    _, db = database(tmp_path, entries=[{"directory": ".", "file": str(path),
                                       "arguments": ["clang++", str(path)]} for path in [first, second]])
    result = analyze(tmp_path, db, clang_library=native_library)
    assert len({f["classes"][0]["fully_qualified_name"] for f in result.data["files"]}) == 2


@pytest.mark.parametrize("flag", ["-include-pch", "-isystem-after", "-iquote-unsupported",
                                  "-objc", "-objc++", "-objcmt-migrate-literals", "-openmp",
                                  "-other", "-include=", "-I="])
def test_unsupported_prefix_options_are_not_treated_as_paths_or_outputs(tmp_path, flag):
    source, db = database(tmp_path, ["clang++", flag, "unit.cpp"])
    with pytest.raises(ValueError, match="지원하지|값"):
        config(source, db)


@pytest.mark.parametrize("flag", ["-I", "-isystem", "-iquote", "-include", "-resource-dir", "-isysroot"])
def test_equals_path_arguments_are_normalized_to_separate_values(tmp_path, flag):
    source, db = database(tmp_path, ["clang++", flag + "=context", "unit.cpp"])
    assert config(source, db)["entries"][0]["arguments"] == [
        flag, str((tmp_path / "context").resolve())]


@pytest.mark.parametrize("flag", ["-I", "-isystem", "-iquote", "-include"])
def test_native_equals_includes_retain_header_semantics(tmp_path, native_library, flag):
    include_dir = tmp_path / "headers"
    include_dir.mkdir()
    (include_dir / "context.hpp").write_text("#define HEADER_VALUE 7\n", encoding="utf-8")
    value = "headers/context.hpp" if flag == "-include" else "headers"
    source, db = database(tmp_path, ["clang++", flag + "=" + value, "unit.cpp"])
    source.write_text(('' if flag == "-include" else '#include "context.hpp"\n') +
                      "int header_context() { return HEADER_VALUE; }\n", encoding="utf-8")
    result = analyze(source, db, clang_library=native_library)
    assert not result.errors
    assert not result.data["compiler_diagnostics"]
    assert [method["name"] for method in methods(result)] == ["header_context"]


@pytest.mark.parametrize("scope,field,value", [
    ("method", "invoked_symbols", [{}]),
    ("method", "referenced_type_symbols", [[]]),
    ("method", "symbol_id", {}),
    ("method", "owner_symbol_id", []),
    ("method", "name", []),
    ("method", "cyclomatic_complexity", "1"),
    ("method", "cyclomatic_complexity", 0),
    ("method", "loc", -1),
    ("method", "start_line", 0),
    ("method", "end_line", 0),
    ("method", "is_game_loop_entry", "false"),
    ("method", "is_macro_generated", []),
    ("file", "has_code", "false"),
    ("method", "calls", [{"kind": "direct", "symbol_id": {}, "line": 1}]),
    ("class", "name", {}),
    ("class", "static_member_accesses", [{}]),
    ("diagnostic", "severity", []),
    ("diagnostic", "input_path", []),
    ("diagnostic", "path", {}),
    ("diagnostic", "message", None),
    ("diagnostic", "line", -1),
])
def test_malformed_worker_schema_is_rejected_before_next_real_file(
        tmp_path, native_library, monkeypatch, scope, field, value):
    source, db = database(tmp_path, entries=[
        {"directory": ".", "file": "unit.cpp", "arguments": ["clang++", "unit.cpp"]},
        {"directory": ".", "file": "z.cpp", "arguments": ["clang++", "z.cpp"]},
    ])
    (tmp_path / "z.cpp").write_text("int survives() { return 2; }", encoding="utf-8")
    module = importlib.import_module("game_si.clang_analyzer")
    real_run = module.subprocess.run
    def corrupting_run(command, **kwargs):
        completed = real_run(command, **kwargs)
        request = json.loads(kwargs["input"])
        if request.get("path") == str(source):
            response = json.loads(completed.stdout)
            if scope == "diagnostic":
                row = {"severity": "warning", "input_path": str(source), "path": str(source),
                       "line": 1, "column": 1, "message": "boundary warning"}
                row[field] = value
                response["compiler_diagnostics"] = [row]
            else:
                cls = response["file"]["classes"][0]
                row = (response["file"] if scope == "file" else
                       cls["methods"][0] if scope == "method" else cls)
                row[field] = value
            return subprocess.CompletedProcess(command, 0, json.dumps(response), completed.stderr)
        return completed
    monkeypatch.setattr(module.subprocess, "run", corrupting_run)
    result = analyze(tmp_path, db, clang_library=native_library)
    assert len(result.errors) == 1 and result.errors[0]["path"] == str(source)
    assert [method["name"] for method in methods(result)] == ["survives"]
    assert result.data["compiler_diagnostics"] == []
    from game_si.metrics import compute_metrics
    assert all(method.game_loop_centrality == 0 for method in compute_metrics(result.data).methods)


@pytest.mark.parametrize("compiler", ["clang++", "g++", "c++", "clang++-20.exe", "g++-13", "c++-13.exe"])
def test_cpp_driver_preserves_default_language_for_c_extension(tmp_path, native_library, compiler):
    source = tmp_path / "cpp_context.c"
    source.write_text("template<class T> T identity(T value) { return value; }\n"
                      "int use() { return identity(1); }\n", encoding="utf-8")
    db = tmp_path / "compile_commands.json"
    db.write_text(json.dumps([{"directory": ".", "file": source.name,
                              "arguments": [compiler, "-c", source.name]}]), encoding="utf-8")
    result = analyze(source, db, clang_library=native_library)
    assert not result.errors
    assert not result.data["compiler_diagnostics"]
    assert result.data["configuration"]["entries"][0]["arguments"] == ["-x", "c++"]
    assert {method["name"] for method in methods(result)} == {"identity", "use"}


@pytest.mark.parametrize("compiler,flags", [
    ("clang++", ["-x", "c"]), ("g++-13", ["-x", "c"]),
    ("clang-cl", ["/TC"]), ("cl.exe", ["/TC"]),
    ("clang", []), ("gcc", []),
])
def test_explicit_c_language_and_normal_c_drivers_are_preserved(tmp_path, native_library, compiler, flags):
    source = tmp_path / "c_context.c"
    source.write_text("#ifdef __cplusplus\n#error expected C language\n#endif\n"
                      "int c_context(void) { return 1; }\n", encoding="utf-8")
    db = tmp_path / "compile_commands.json"
    db.write_text(json.dumps([{"directory": ".", "file": source.name,
                              "arguments": [compiler, *flags, source.name]}]), encoding="utf-8")
    result = analyze(source, db, clang_library=native_library)
    assert not result.errors
    assert not result.data["compiler_diagnostics"]
    assert [method["name"] for method in methods(result)] == ["c_context"]
    args = result.data["configuration"]["entries"][0]["arguments"]
    assert args[:2] == ["-x", "c"] if flags else args == []


@pytest.mark.parametrize("optimization,expected", [("-O0", "unoptimized"), ("-O2", "optimized"),
                                                   ("-Os", "optimized")])
def test_optimization_flags_preserve_preprocessor_context(tmp_path, native_library, optimization, expected):
    source, db = database(tmp_path, ["clang++", optimization, "unit.cpp"])
    source.write_text("#ifdef __OPTIMIZE__\nint optimized() { return 1; }\n#else\n"
                      "int unoptimized() { return 0; }\n#endif\n", encoding="utf-8")
    result = analyze(source, db, clang_library=native_library)
    assert not result.errors and not result.data["compiler_diagnostics"]
    assert [method["name"] for method in methods(result)] == [expected]
    assert result.data["configuration"]["entries"][0]["arguments"] == [optimization]


def test_same_basename_internal_symbols_stay_in_their_translation_units(tmp_path, native_library):
    entries = []
    for directory, entry_name in [("a", "MainLoop"), ("b", "secondary")]:
        source = tmp_path / directory / "shared.cpp"
        source.parent.mkdir()
        source.write_text("namespace { struct Local { static int work(); };\n"
                          "int Local::work() { return 1; } }\n"
                          "static int helper() { return Local::work(); }\n"
                          f"int {entry_name}() {{ return helper(); }}\n", encoding="utf-8")
        entries.append({"directory": ".", "file": source.relative_to(tmp_path).as_posix(),
                        "arguments": ["clang++", "-std=c++17", str(source)]})
    db = tmp_path / "compile_commands.json"
    db.write_text(json.dumps(entries), encoding="utf-8")
    result = analyze(tmp_path, db, clang_library=native_library)
    assert not result.errors and not result.data["compiler_diagnostics"]
    from game_si.metrics import compute_metrics
    computed = compute_metrics(result.data)
    assert list(computed.class_graph.edges) == []
    assert computed.sccs == []
    helper_metrics = {method.file_path: method for method in computed.methods if method.name == "helper"}
    assert helper_metrics["a/shared.cpp"].game_loop_centrality == 0.5
    assert helper_metrics["b/shared.cpp"].game_loop_centrality == 0
    by_file = {file["relative_path"]: {method["name"]: method for method in file["classes"][0]["methods"]}
               for file in result.data["files"]}
    first, second = by_file["a/shared.cpp"], by_file["b/shared.cpp"]
    assert first["helper"]["raw_symbol_id"] == second["helper"]["raw_symbol_id"]
    assert first["helper"]["symbol_id"] != second["helper"]["symbol_id"]
    assert first["work"]["raw_owner_symbol_id"] == second["work"]["raw_owner_symbol_id"]
    assert first["work"]["owner_symbol_id"] != second["work"]["owner_symbol_id"]
    assert first["MainLoop"]["invoked_symbols"] == [first["helper"]["symbol_id"]]
    assert first["MainLoop"]["calls"][0]["raw_symbol_id"] == first["helper"]["raw_symbol_id"]
    assert first["helper"]["invoked_symbols"] == [first["work"]["symbol_id"]]
    assert first["work"]["owner_symbol_id"] in first["helper"]["referenced_type_symbols"]
    assert first["work"]["raw_owner_symbol_id"] in first["helper"]["raw_referenced_type_symbols"]
