"""Optional compiler-context C/C++ backend, isolated from the parent process."""

from __future__ import annotations

import datetime as _dt
import json
import math
from pathlib import Path
import subprocess
import sys
import time
from typing import Iterable

from .clang_config import load_configuration
from .cpp_analyzer import CppAnalysisResult, SCHEMA_VERSION


def _run_worker(payload: dict, timeout: float) -> dict:
    process = subprocess.run(
        [sys.executable, "-B", "-m", "game_si.clang_worker"],
        input=json.dumps(payload, ensure_ascii=False), capture_output=True,
        text=True, encoding="utf-8", errors="replace", shell=False, timeout=timeout,
        cwd=str(Path(__file__).resolve().parent.parent))
    if process.returncode:
        raise RuntimeError(f"Clang worker 종료 코드 {process.returncode}: {process.stderr[:4096]}")
    try:
        result = json.loads(process.stdout)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Clang worker가 올바른 JSON을 반환하지 않았습니다.") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Clang worker 결과는 JSON 객체여야 합니다.")
    if result.get("error"):
        raise RuntimeError(str(result["error"]))
    return result


def _validate_worker_result(result: dict, path: Path, relative: str) -> tuple[dict, list[dict]]:
    """Reject malformed child data before it enters metrics or symbol indexes."""
    def require(condition):
        if not condition:
            raise RuntimeError("Clang worker 결과 형식이 올바르지 않습니다.")

    def strings(row, keys):
        return all(isinstance(row.get(key), str) for key in keys)

    def string_lists(row, keys):
        return all(isinstance(row.get(key), list) and all(isinstance(value, str)
                   for value in row[key]) for key in keys)

    def integers(row, keys, minimum):
        return all(type(row.get(key)) is int and row[key] >= minimum for key in keys)

    file_node = result.get("file")
    diagnostics = result.get("compiler_diagnostics")
    require(isinstance(file_node, dict) and file_node.get("path") == str(path)
            and file_node.get("relative_path") == relative and integers(file_node, ("loc",), 0)
            and type(file_node.get("has_code")) is bool
            and isinstance(file_node.get("classes"), list) and len(file_node["classes"]) == 1
            and isinstance(diagnostics, list))
    cls = file_node["classes"][0]
    require(isinstance(cls, dict) and strings(cls, ("name", "fully_qualified_name", "kind"))
            and bool(cls["name"]) and cls["fully_qualified_name"] == "clang.file." + relative
            and cls["kind"] == "compilation_unit" and integers(cls, ("start_line", "end_line"), 1)
            and cls["end_line"] >= cls["start_line"] and isinstance(cls.get("methods"), list)
            and string_lists(cls, ("base_types", "referenced_types", "static_member_accesses", "singleton_accesses")))
    for method in cls["methods"]:
        require(isinstance(method, dict) and strings(method, (
                    "name", "signature", "fully_qualified_name", "symbol_id", "owner_symbol_id",
                    "owner_fully_qualified_name", "owner_kind", "return_type"))
                and bool(method["name"]) and bool(method["symbol_id"])
                and integers(method, ("start_line", "end_line", "loc", "cyclomatic_complexity"), 1)
                and method["end_line"] >= method["start_line"]
                and integers(method, ("parameter_count", "indirect_call_count", "external_call_count"), 0)
                and string_lists(method, ("invoked_names", "invoked_symbols", "referenced_type_symbols"))
                and type(method.get("is_game_loop_entry")) is bool
                and type(method.get("is_macro_generated")) is bool
                and isinstance(method.get("calls"), list))
        for call in method["calls"]:
            require(isinstance(call, dict) and strings(call, (
                        "kind", "symbol_id", "name", "fully_qualified_name", "dispatch"))
                    and call["kind"] in {"direct", "indirect"}
                    and call["dispatch"] in {"direct", "compile_time_virtual", "unresolved"}
                    and integers(call, ("line",), 0))
    for diagnostic in diagnostics:
        require(isinstance(diagnostic, dict) and strings(diagnostic, (
                    "severity", "input_path", "path", "message"))
                and diagnostic["severity"] in {"warning", "error", "fatal"}
                and diagnostic["input_path"] == str(path)
                and integers(diagnostic, ("line", "column"), 0))
    return file_node, diagnostics


def analyze_clang(input_path: Path, compile_commands: Path, excludes: Iterable[str] = (),
                  output_path: Path | None = None, clang_library: Path | str | None = None,
                  timeout: float = 60.0, progress=None) -> CppAnalysisResult:
    """Analyze registered implementation files; never silently switch backends.

    Calls use compile-time USRs. File relations approximate implementation-unit
    dependencies rather than claiming an exact semantic class graph.
    `progress(done, total, relative_path)` is called after each file, so a long run can show how far it is.
    """
    started = time.perf_counter()
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout은 유한한 양수(초)여야 합니다.")
    root = Path(input_path).resolve()
    configuration = load_configuration(root, compile_commands, excludes)
    library = str(Path(clang_library).resolve()) if clang_library is not None else None
    if library and not Path(library).is_file():
        raise RuntimeError(f"libclang 라이브러리 파일이 없습니다: {library}")
    common = {"clang_library": library}
    try:
        runtime = _run_worker({**common, "action": "runtime"}, timeout).get("runtime")
        if not isinstance(runtime, dict) or not isinstance(runtime.get("native_version"), str):
            raise RuntimeError("Clang runtime 버전 응답이 올바르지 않습니다.")
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Clang 초기화 실패: {exc}. 호환되는 clang Python bindings와 "
                           "libclang DLL/공유 라이브러리 및 의존성을 설치하고 "
                           "clang_library 경로를 지정하세요.") from exc
    files = []
    errors = list(configuration.pop("collection_errors"))
    diagnostics = []
    total = len(configuration["entries"])
    for done, entry in enumerate(configuration["entries"], 1):
        path = Path(entry["path"])
        try:
            path.read_bytes()  # Report unreadable sources even if libclang would recover an empty TU.
            relative = path.relative_to(root).as_posix() if path != root else path.name
            result = _run_worker({**common, "action": "parse", "path": str(path),
                                  "relative_path": relative, "arguments": entry["arguments"]}, timeout)
            file_node, compiler_diagnostics = _validate_worker_result(result, path, relative)
            files.append(file_node)
            diagnostics.extend(compiler_diagnostics)
        except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
            message = (f"Clang worker timeout ({timeout:g}s)" if isinstance(exc, subprocess.TimeoutExpired)
                       else str(exc))
            errors.append({"path": str(path), "message": message, "kind": "worker"})
        if progress:
            progress(done, total, path.name)
    _map_file_relations(files)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    data = {
        "schema_version": SCHEMA_VERSION,
        "analyzed_at": _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input_path": str(root), "analyzer_version": "clang-analyzer-0.1",
        "backend": "clang", "analysis_unit": "implementation_file",
        "runtime": runtime, "configuration": configuration,
        "limitations": ["File relations approximate implementation-unit dependencies, not an exact class graph.",
                         "Virtual calls identify compile-time declarations; dynamic dispatch is not resolved.",
                         "Indirect calls are recorded without speculative targets.",
                         "CC excludes range-for and nested lambda bodies; default labels count as branches."],
        "summary": {"total_files": len(files), "total_classes": len(files),
                    "total_methods": sum(len(f["classes"][0]["methods"]) for f in files),
                    "total_loc": sum(f["loc"] for f in files), "elapsed_ms": elapsed_ms,
                    "registered_files": len(configuration["entries"]),
                    "unregistered_files": len(configuration["unregistered_files"]),
                    "compiler_warning_count": sum(d["severity"] == "warning" for d in diagnostics),
                    "compiler_error_count": sum(d["severity"] in {"error", "fatal"} for d in diagnostics)},
        "files": files, "errors": errors, "diagnostics": [], "compiler_diagnostics": diagnostics,
    }
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return CppAnalysisResult(data=data, elapsed_ms=elapsed_ms, errors=errors)


def _map_file_relations(files: list[dict]) -> None:
    symbol_units: dict[str, set[str]] = {}
    for file in files:
        cls = file["classes"][0]
        unit = cls["fully_qualified_name"]
        for method in cls["methods"]:
            for key in ("symbol_id", "owner_symbol_id"):
                if method.get(key):
                    symbol_units.setdefault(method[key], set()).add(unit)
    for file in files:
        cls = file["classes"][0]
        references = set()
        for method in cls["methods"]:
            for symbol in (*method["invoked_symbols"], *method["referenced_type_symbols"]):
                references.update(symbol_units.get(symbol, ()))
            method["external_call_count"] = sum(call.get("symbol_id") not in symbol_units
                                                for call in method["calls"] if call["kind"] == "direct")
        references.discard(cls["fully_qualified_name"])
        cls["referenced_types"] = sorted(references)
