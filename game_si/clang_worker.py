"""Native libclang worker. stdin/stdout use a single JSON request/response."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from .cpp_analyzer import _count_loc, _is_game_loop_name

_DLL_HANDLES = []


def _runtime(library: str | None):
    try:
        from clang import cindex
    except ImportError as exc:
        raise RuntimeError("clang Python bindings가 없습니다. 호환되는 clang 패키지를 설치하세요.") from exc
    try:
        if library:
            if os.name == "nt" and hasattr(os, "add_dll_directory"):
                _DLL_HANDLES.append(os.add_dll_directory(str(Path(library).parent)))
            cindex.Config.set_library_file(library)
        index = cindex.Index.create()
        version_fn = cindex.conf.lib.clang_getClangVersion
        version_fn.restype = cindex._CXString
        version = str(cindex.conf.lib.clang_getCString(version_fn()))
    except Exception as exc:
        raise RuntimeError(f"libclang 로드 실패: {exc}. bindings/native 버전과 DLL 의존성을 확인하세요.") from exc
    return cindex, index, {"native_version": version, "library": library}


def _qualified(cursor) -> str:
    names = []
    while cursor is not None and cursor.kind.name != "TRANSLATION_UNIT":
        if cursor.spelling:
            names.append(cursor.spelling)
        cursor = cursor.semantic_parent
    return "::".join(reversed(names))


def _symbol_id(cursor, relative: str) -> str:
    """Internal USRs may contain only a basename; qualify their analysis scope."""
    if cursor is None:
        return ""
    usr = cursor.get_usr()
    if usr and cursor.linkage.name in {"INTERNAL", "UNIQUE_EXTERNAL", "NO_LINKAGE"}:
        return f"clang.tu[{relative}]::{usr}"
    return usr


def _body_nodes(cursor):
    """Walk a selected function without entering nested lambda/function bodies."""
    pending = list(reversed(list(cursor.get_children())))
    while pending:
        node = pending.pop()
        if node.kind.name in {"LAMBDA_EXPR", "FUNCTION_DECL", "CXX_METHOD", "CONSTRUCTOR", "DESTRUCTOR", "PARM_DECL"}:
            continue
        yield node
        pending.extend(reversed(list(node.get_children())))


def _method(cursor, macros, cindex, relative):
    owner = cursor.semantic_parent
    owner_name = _qualified(owner)
    calls = []
    globals_ = []
    type_symbols = set()
    raw_type_symbols = set()
    arguments = list(cursor.get_arguments())
    for argument in arguments:
        for reference in _body_nodes(argument):
            if reference.kind.name == "TYPE_REF" and reference.referenced is not None:
                symbol = reference.referenced.get_usr()
                if symbol:
                    raw_type_symbols.add(symbol)
                    type_symbols.add(_symbol_id(reference.referenced, relative))
    cc = 1
    branches = {"IF_STMT", "FOR_STMT", "WHILE_STMT", "DO_STMT", "CASE_STMT",
                "DEFAULT_STMT", "CONDITIONAL_OPERATOR", "CXX_CATCH_STMT"}
    function_kinds = {"FUNCTION_DECL", "CXX_METHOD", "CONSTRUCTOR", "DESTRUCTOR", "FUNCTION_TEMPLATE"}
    for node in _body_nodes(cursor):
        kind = node.kind.name
        if kind in branches:
            cc += 1
        elif kind == "BINARY_OPERATOR":
            if node.binary_operator in {cindex.BinaryOperator.LAnd, cindex.BinaryOperator.LOr}:
                cc += 1
        if kind == "CALL_EXPR":
            ref = node.referenced
            indirect = (ref is None or ref.kind.name not in function_kinds or
                        (ref.spelling == "operator()" and not ref.semantic_parent.spelling))
            virtual = bool(not indirect and ref.kind.name == "CXX_METHOD" and ref.is_virtual_method())
            calls.append({"name": node.spelling, "fully_qualified_name": _qualified(ref) if ref else "",
                          "symbol_id": _symbol_id(ref, relative) if not indirect else "",
                          "raw_symbol_id": ref.get_usr() if not indirect else "",
                          "kind": "indirect" if indirect else "direct",
                          "line": node.location.line,
                          "dispatch": "compile_time_virtual" if virtual else "direct" if not indirect else "unresolved"})
        elif kind in {"DECL_REF_EXPR", "MEMBER_REF_EXPR"}:
            ref = node.referenced
            if ref is not None and ref.kind.name == "VAR_DECL":
                parent = ref.semantic_parent
                if ref.storage_class.name == "STATIC" or (parent and parent.kind.name in {
                        "TRANSLATION_UNIT", "NAMESPACE", "CLASS_DECL", "STRUCT_DECL", "CLASS_TEMPLATE"}):
                    globals_.append(_symbol_id(ref, relative) or _qualified(ref))
        if kind == "TYPE_REF" and node.referenced is not None:
            symbol = node.referenced.get_usr()
            if symbol:
                raw_type_symbols.add(symbol)
                type_symbols.add(_symbol_id(node.referenced, relative))
    expansions = [macro for macro in macros if macro["start_offset"] <= cursor.location.offset < macro["end_offset"]
                  or (macro["start_offset"] == macro["end_offset"] == cursor.location.offset)]
    start = cursor.extent.start.line
    end = cursor.extent.end.line
    direct = [call for call in calls if call["kind"] == "direct"]
    method = {
        "name": cursor.spelling, "signature": cursor.displayname,
        "fully_qualified_name": _qualified(cursor), "symbol_id": _symbol_id(cursor, relative),
        "raw_symbol_id": cursor.get_usr(),
        "owner_symbol_id": _symbol_id(owner, relative), "raw_owner_symbol_id": owner.get_usr() if owner else "",
        "owner_fully_qualified_name": owner_name,
        "owner_kind": owner.kind.name if owner else "",
        "start_line": start, "end_line": end, "parameter_count": len(arguments),
        "return_type": cursor.result_type.spelling,
        "is_static": cursor.storage_class.name == "STATIC" or
                     (cursor.kind.name == "CXX_METHOD" and cursor.is_static_method()),
        "is_async": False, "is_override": False, "cyclomatic_complexity": cc,
        "loc": max(1, end - start + 1), "is_game_loop_entry": _is_game_loop_name(cursor.spelling),
        "invoked_symbols": sorted({call["symbol_id"] for call in direct if call["symbol_id"]}),
        # Root qualification prevents metrics' legacy simple-name fallback from inventing edges.
        "invoked_names": sorted({"::" + call["fully_qualified_name"] for call in direct}),
        "referenced_type_symbols": sorted(type_symbols), "raw_referenced_type_symbols": sorted(raw_type_symbols),
        "calls": calls,
        "indirect_call_count": sum(call["kind"] == "indirect" for call in calls), "external_call_count": 0,
        "is_macro_generated": bool(expansions), "macro_expansions": expansions,
        "expansion_location": {"line": cursor.location.line, "column": cursor.location.column},
    }
    return method, globals_


def _parse(request, cindex, index):
    path = Path(request["path"])
    source = path.read_bytes()
    tu = index.parse(str(path), args=request["arguments"],
                     options=cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)
    path_cache = {}
    def key(value):
        if value not in path_cache:
            path_cache[value] = os.path.normcase(str(Path(value).resolve()))
        return path_cache[value]
    wanted = key(str(path))
    containers = {"TRANSLATION_UNIT", "NAMESPACE", "CLASS_DECL", "STRUCT_DECL", "CLASS_TEMPLATE",
                  "UNEXPOSED_DECL", "LINKAGE_SPEC", "UNION_DECL"}
    functions = {"FUNCTION_DECL", "CXX_METHOD", "CONSTRUCTOR", "DESTRUCTOR", "FUNCTION_TEMPLATE"}
    definitions = []
    macros = []
    pending = [tu.cursor]
    while pending:
        cursor = pending.pop()
        if cursor.kind.name != "TRANSLATION_UNIT":
            file = cursor.location.file
            if file is None or key(file.name) != wanted:
                continue
        kind = cursor.kind.name
        if kind == "MACRO_INSTANTIATION":
            definition = cursor.referenced
            location = definition.location if definition else None
            macros.append({"name": cursor.spelling, "invocation_line": cursor.location.line,
                           "invocation_column": cursor.location.column,
                           "start_offset": cursor.extent.start.offset, "end_offset": cursor.extent.end.offset,
                           "definition_path": location.file.name if location and location.file else None,
                           "definition_line": location.line if location else None})
        elif kind in functions and cursor.is_definition():
            definitions.append(cursor)
        elif kind in containers:
            pending.extend(reversed(list(cursor.get_children())))
    macros.sort(key=lambda m: (m["start_offset"], m["name"]))
    methods = []
    accesses = []
    relative = request["relative_path"]
    for cursor in definitions:
        method, globals_ = _method(cursor, macros, cindex, relative)
        methods.append(method)
        accesses.extend(globals_)
    methods.sort(key=lambda m: (m["start_line"], m["symbol_id"]))
    cls = {"name": path.name, "fully_qualified_name": "clang.file." + relative,
           "namespace": None, "kind": "compilation_unit", "start_line": 1,
           "end_line": max(1, len(source.splitlines())), "is_static": False, "is_partial": False,
           "is_abstract": False, "base_types": [], "referenced_types": [],
           "static_member_accesses": accesses, "singleton_accesses": [], "methods": methods}
    severity = {2: "warning", 3: "error", 4: "fatal"}
    diagnostics = [{"severity": severity[d.severity], "input_path": str(path),
                    "path": d.location.file.name if d.location.file else str(path),
                    "line": d.location.line, "column": d.location.column, "message": d.spelling}
                   for d in tu.diagnostics if d.severity in severity]
    return {"file": {"path": str(path), "relative_path": relative, "loc": _count_loc(source),
                     "classes": [cls], "has_code": bool(source.strip())},
            "compiler_diagnostics": diagnostics}


def main():
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        request = json.load(sys.stdin)
        cindex, index, runtime = _runtime(request.get("clang_library"))
        response = {"runtime": runtime}
        if request.get("action") == "parse":
            response.update(_parse(request, cindex, index))
        elif request.get("action") != "runtime":
            raise ValueError("Unknown Clang worker action.")
    except Exception as exc:
        response = {"error": f"{type(exc).__name__}: {exc}"}
    sys.stdout.reconfigure(encoding="utf-8")
    json.dump(response, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
