"""tree-sitter 기반 C / C++ AST 추출기 (W9~W10).

`csharp-analyzer` 가 산출하는 ast.json 과 **동일한 스키마**(`docs/ast-schema.md` v0.2)
로 결과를 생성한다. 동일 스키마이므로 `metrics.compute_metrics` 와
`si.compute_si_static` 파이프라인이 추가 수정 없이 그대로 동작한다.

본 모듈은 tree-sitter 의 syntactic 분석만 수행한다. plan §5.1 에 명시한 대로
매크로/템플릿의 완전한 의미 분석은 본 작품 범위 밖이다. 정확도가 필요한
경우에는 ``compile_commands.json`` 기반 clang tooling 으로 보강하는 것을
후속 작업으로 둔다.

PoC 단위:
* **클래스** — 한 .c/.cpp 파일은 한 개의 합성 "compilation_unit" 클래스로 매핑한다.
  C++ 의 `class` / `struct` 선언은 별도 ClassNode 로 추가한다.
* **메서드** — `function_definition` 및 C++ method definition.
* **invoked_names** — 함수 본문의 `call_expression` 함수명.
* **referenced_types** — `#include` 디렉티브의 파일 stem + 본문에서 등장한
  type_identifier. metrics 의 클래스 그래프 빌더가 이 stem 을 다른 compilation
  unit 의 simple name 과 syntactic 매칭한다.
* **static_member_accesses** — 파일 내 `static`/`extern` 전역 변수 식별자가
  함수 본문에서 등장한 횟수 (중복 포함). GlobalState 메트릭의 입력.
* **is_game_loop_entry** — 이름 패턴: `MainLoop`, `*Tick`, `*Frame`, `Render`,
  `Update`, `*Update`, `*Draw`.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from tree_sitter import Language, Node, Parser

try:
    import tree_sitter_c as _ts_c
except ImportError:  # pragma: no cover
    _ts_c = None

try:
    import tree_sitter_cpp as _ts_cpp
except ImportError:  # pragma: no cover
    _ts_cpp = None


SCHEMA_VERSION = "0.2"  # csharp-analyzer 와 동일 스키마
ANALYZER_VERSION = "cpp-analyzer-0.2"


# ---------------------------------------------------------------------------
# 언어 dispatch
# ---------------------------------------------------------------------------


C_EXTENSIONS = {".c", ".h"}
CPP_EXTENSIONS = {".cpp", ".cxx", ".cc", ".hpp", ".hxx", ".hh", ".inl"}
SUPPORTED_EXTENSIONS = C_EXTENSIONS | CPP_EXTENSIONS

# 분석에서 본문 함수까지 들여다보는 확장자 (헤더는 1차 PoC 에서는 선언만 봄)
BODY_EXTENSIONS = {".c", ".cpp", ".cxx", ".cc"}

DEFAULT_EXCLUDE_DIRS = {
    ".git", "node_modules", "build", "Build", "out", "Out",
    "dist", "vendor", "third_party", "thirdparty",
    "__pycache__", ".vs", ".vscode", "obj", "bin",
    # Doom/OpenRCT2 ports often vendor SDLs / opl emulator in vendored trees:
    "textscreen", "midiproc",
}


# 게임 루프 진입점 이름 패턴 (plan §4.4 + Chocolate Doom 관습 일부)
_GAME_LOOP_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^MainLoop$", re.IGNORECASE),
    re.compile(r"^D_DoomLoop$"),
    re.compile(r".*Tick$"),
    re.compile(r".*Frame$"),
    re.compile(r"^Render$|^Render[A-Z_].*"),
    re.compile(r"^Draw$|^.*Draw$"),
    re.compile(r"^Update$|^.*Update$"),
    re.compile(r"^On[A-Z_].*"),
]


def _is_game_loop_name(name: str) -> bool:
    return any(p.match(name) for p in _GAME_LOOP_PATTERNS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass
class CppAnalysisResult:
    data: dict
    elapsed_ms: int
    errors: list[dict]


def analyze_cpp(
    input_path: Path,
    excludes: Iterable[str] = (),
    output_path: Path | None = None,
) -> CppAnalysisResult:
    """디렉토리/파일을 tree-sitter 로 분석하고 ast.json 호환 dict 를 반환한다."""
    input_path = Path(input_path).resolve()
    excludes_set = DEFAULT_EXCLUDE_DIRS | set(excludes)
    start = time.perf_counter()

    file_nodes: list[dict] = []
    errors: list[dict] = []
    diagnostics: list[dict] = []
    files_to_parse = _collect_files(input_path, excludes_set, errors)
    parser_cache: dict[str, Parser] = {}

    total_loc = 0
    total_classes = 0
    total_methods = 0

    for path in files_to_parse:
        try:
            file_node = _analyze_file(path, input_path, parser_cache)
        except Exception as exc:  # tree-sitter 에러는 파일별로 격리한다
            errors.append({"path": str(path), "message": str(exc)})
            continue
        file_nodes.append(file_node)
        diagnostics.extend(file_node.pop('diagnostics', []))
        total_loc += file_node.get("loc", 0)
        total_classes += len(file_node.get("classes", []))
        for c in file_node.get("classes", []):
            total_methods += len(c.get("methods", []))

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    data: dict = {
        "schema_version": SCHEMA_VERSION,
        "analyzed_at": _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input_path": str(input_path),
        "analyzer_version": ANALYZER_VERSION,
        "summary": {
            "total_files": len(file_nodes),
            "total_classes": total_classes,
            "total_methods": total_methods,
            "total_loc": total_loc,
            "elapsed_ms": elapsed_ms,
        },
        "files": file_nodes,
        "errors": errors,
        "diagnostics": diagnostics,
    }

    if output_path is not None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return CppAnalysisResult(data=data, elapsed_ms=elapsed_ms, errors=errors)


# ---------------------------------------------------------------------------
# 파일 수집 / 파서 셋업
# ---------------------------------------------------------------------------


def _collect_files(root: Path, excludes: set[str], errors: list[dict] | None = None) -> list[Path]:
    """본문이 있는 .c/.cpp/.cc/.cxx 파일만 수집한다.

    헤더(.h/.hpp/...)는 함수 정의가 거의 없어 분석 단위로 적절하지 않고, .c 와
    같은 stem 을 가질 경우 ClassNode 의 FQN 충돌을 일으키므로 PoC 에서는 제외한다.
    헤더의 의존성은 본문 파일의 `#include` 디렉티브로 충분히 회수된다.
    """
    if root.is_file():
        return [root] if root.suffix.lower() in BODY_EXTENSIONS else []
    out: list[Path] = []
    def on_error(exc):
        if errors is not None:
            errors.append(dict(path=str(exc.filename or root), message=str(exc)))
    for directory, subdirs, files in os.walk(root, onerror=on_error):
        subdirs[:] = sorted(name for name in subdirs if name not in excludes)
        for name in files:
            path = Path(directory) / name
            if path.suffix.lower() in BODY_EXTENSIONS:
                out.append(path)
    return sorted(out)


def _get_parser(lang: str, cache: dict[str, Parser]) -> Parser:
    if lang in cache:
        return cache[lang]
    if lang == "c":
        if _ts_c is None:
            raise RuntimeError("tree-sitter-c 가 설치되어 있지 않다. `pip install tree-sitter-c` 후 다시 실행.")
        language = Language(_ts_c.language())
    elif lang == "cpp":
        if _ts_cpp is None:
            raise RuntimeError("tree-sitter-cpp 가 설치되어 있지 않다. `pip install tree-sitter-cpp` 후 다시 실행.")
        language = Language(_ts_cpp.language())
    else:  # pragma: no cover
        raise ValueError(f"unsupported language: {lang}")
    parser = Parser(language)
    cache[lang] = parser
    return parser


def _detect_language(path: Path) -> str:
    return "cpp" if path.suffix.lower() in CPP_EXTENSIONS else "c"


# ---------------------------------------------------------------------------
# 파일 단위 분석
# ---------------------------------------------------------------------------


def _analyze_file(path: Path, root: Path, parser_cache: dict[str, Parser]) -> dict:
    src = path.read_bytes()
    lang = _detect_language(path)
    parser = _get_parser(lang, parser_cache)
    tree = parser.parse(src)
    root_node = tree.root_node
    diagnostics = []
    if root_node.has_error:
        pending = [root_node]
        location = root_node.start_point
        while pending:
            node = pending.pop()
            if node.type == 'ERROR' or node.is_missing:
                location = node.start_point
                break
            pending.extend(reversed(node.children))
        diagnostics.append(dict(path=str(path), kind='syntax', line=location[0] + 1,
                                message='문법 오류 또는 파서가 해석하지 못한 구문이 있습니다. '
                                        '복구 가능한 부분을 추출했으므로 결과가 불완전할 수 있습니다.'))

    # 1) #include 디렉티브 (referenced_types 의 stem 후보)
    includes = _extract_includes(root_node, src)

    # 2) 파일 전역 static / extern 변수 식별자 집합
    global_var_names = _extract_global_var_names(root_node, src)

    # 3) C++ 클래스/struct 정의 (간단한 식별, namespace 추적 없음)
    cpp_classes: list[dict] = []
    if lang == "cpp":
        cpp_classes = _extract_cpp_classes(root_node, src, path, root,
                                           global_var_names, includes)

    # 4) 파일 최상위 함수 (또는 C 함수) — synthetic compilation_unit 클래스로 묶음
    free_functions = _extract_free_functions(
        root_node, src, path, root,
        global_var_names=global_var_names,
        # C++ 에서는 클래스 본문 내 method 는 cpp_classes 가 가져갔으므로 중복 방지
        skip_in_class_methods=(lang == "cpp"),
    )

    # 5) 결과 조립
    relative_path = path.relative_to(root).as_posix() if path != root else path.name
    loc = _count_loc(src)

    classes: list[dict] = []
    if free_functions or not cpp_classes:
        # PoC 우선: 한 파일 = 한 compilation_unit. C++ 라도 free function 이 있으면 추가.
        synthetic = _make_synthetic_class(
            path=path,
            file_relpath=relative_path,
            methods=free_functions,
            includes=includes,
            global_var_names=global_var_names,
            start_line=1,
            end_line=root_node.end_point[0] + 1,
        )
        classes.append(synthetic)
    classes.extend(cpp_classes)

    # 메서드의 내부 helper 키(`_global_accesses`)는 직렬화에서 제외한다.
    for cls in classes:
        for m in cls.get("methods", []):
            m.pop("_global_accesses", None)

    return {
        "path": str(path),
        "relative_path": relative_path,
        "loc": loc,
        "classes": classes,
        "diagnostics": diagnostics,
        "has_code": any(child.type != 'comment' for child in root_node.named_children),
    }


def _make_synthetic_class(
    path: Path,
    file_relpath: str,
    methods: list[dict],
    includes: list[str],
    global_var_names: set[str],
    start_line: int,
    end_line: int,
) -> dict:
    """C 파일 또는 C++ free-function 들을 묶어 1 개의 가상 클래스로 표현."""
    stem = path.stem
    name = stem
    # 정규화: ascii 만 사용해 fully_qualified_name 충돌 회피
    fqn_parent = file_relpath.rsplit("/", 1)[0] if "/" in file_relpath else ""
    fqn = f"{fqn_parent.replace('/', '.')}.{stem}" if fqn_parent else stem
    referenced_types = sorted({_include_stem(h) for h in includes if _include_stem(h)})
    return {
        "name": name,
        "fully_qualified_name": fqn,
        "namespace": fqn_parent.replace("/", ".") if fqn_parent else None,
        "kind": "compilation_unit",
        "start_line": start_line,
        "end_line": end_line,
        "is_static": False,
        "is_partial": False,
        "is_abstract": False,
        "base_types": [],
        "referenced_types": referenced_types,
        "static_member_accesses": _global_accesses_across(methods, global_var_names),
        "singleton_accesses": [],
        "methods": methods,
    }


def _include_stem(include_path: str) -> str:
    """`#include "foo/bar.h"` → `bar`. 시스템 헤더(<...>) 는 무시 가능하지만, 어차피 매칭 안되므로 그대로 통과."""
    if not include_path:
        return ""
    p = include_path.replace("\\", "/")
    last = p.rsplit("/", 1)[-1]
    return last.rsplit(".", 1)[0]


def _global_accesses_across(methods: list[dict], global_var_names: set[str]) -> list[str]:
    """모든 메서드의 global access 를 모아 클래스 단위 카운트로 묶는다."""
    out: list[str] = []
    for m in methods:
        out.extend(m.get("_global_accesses", []))
    return out


# ---------------------------------------------------------------------------
# 노드 탐색
# ---------------------------------------------------------------------------


def _extract_includes(root: Node, src: bytes) -> list[str]:
    """`#include` 디렉티브의 경로 문자열 목록을 반환한다."""
    out: list[str] = []
    for n in _walk(root):
        if n.type == "preproc_include":
            for child in n.children:
                if child.type in ("string_literal", "system_lib_string"):
                    s = src[child.start_byte:child.end_byte].decode("utf-8", "replace")
                    out.append(s.strip('"<>'))
                    break
    return out


def _extract_global_var_names(root: Node, src: bytes) -> set[str]:
    """파일 범위(`_file_scope_items`) 변수 선언에서 식별자 이름을 모은다.

    PoC: ``static`` / ``extern`` 한정 + 일반 전역 변수도 포함 (C 에서는 디폴트가 external linkage).
    함수 정의나 클래스 멤버는 제외.
    """
    out: set[str] = set()
    for child in _file_scope_items(root, src):
        if child.type != "declaration":
            continue
        # function declaration 은 제외 (parameter_list 가 자식에 있음)
        if any(c.type == "function_declarator" for c in _walk(child)):
            continue
        for ident in _walk(child):
            if ident.type == "identifier":
                # init_declarator 의 첫 identifier 가 변수명
                parent = ident.parent
                if parent and parent.type in ("init_declarator", "declaration"):
                    out.add(src[ident.start_byte:ident.end_byte].decode("utf-8", "replace"))
                    break
        # array_declarator, pointer_declarator 안의 식별자도 포함
        for arr in _walk(child):
            if arr.type in ("array_declarator", "pointer_declarator"):
                for ident in _walk(arr):
                    if ident.type == "identifier":
                        out.add(src[ident.start_byte:ident.end_byte].decode("utf-8", "replace"))
                        break
    # 'NULL' 등 매크로 흔한 식별자 제외 (보수적이지 않게)
    out.discard("NULL")
    out.discard("nullptr")
    return out


def _extract_free_functions(
    root: Node,
    src: bytes,
    path: Path,
    project_root: Path,
    global_var_names: set[str],
    skip_in_class_methods: bool,
) -> list[dict]:
    """파일 범위(`_file_scope_items`)의 `function_definition` 노드를 메서드 dict 리스트로 변환."""
    methods: list[dict] = []
    for child in _file_scope_items(root, src):
        if child.type != "function_definition":
            continue
        m = _function_to_method(child, src, global_var_names)
        if m is not None:
            methods.append(m)
    return methods


# Children of these nodes are still at file scope. The basic analysis does not run the preprocessor,
# so it reads every #if/#ifdef branch, except the dead code of a literal `#if 0`.
_FILE_SCOPE_CONTAINERS = {"namespace_definition", "linkage_specification", "template_declaration", "declaration_list",
                          "preproc_if", "preproc_ifdef", "preproc_elif", "preproc_elifdef", "preproc_else"}


def _file_scope_items(root: Node, src: bytes):
    """파일 범위의 선언·정의 노드를 순서대로 산출한다.

    파일 최상위뿐 아니라 namespace, extern "C" 블록, template, #if/#ifdef 분기 안의 노드도
    파일 범위로 본다. 클래스 본문과 함수 본문 안으로는 들어가지 않는다.
    """
    stack = list(reversed(root.children))
    while stack:
        node = stack.pop()
        if node.type not in _FILE_SCOPE_CONTAINERS:
            yield node
            continue
        children = node.children
        if node.type in ("namespace_definition", "linkage_specification"):
            body = node.child_by_field_name("body")
            children = [body] if body is not None else []
        elif node.type == "preproc_if":
            condition = node.child_by_field_name("condition")
            if condition is not None and src[condition.start_byte:condition.end_byte].strip() == b"0":
                alternative = node.child_by_field_name("alternative")
                children = [alternative] if alternative is not None else []
        stack.extend(reversed(children))


def _extract_cpp_classes(
    root: Node,
    src: bytes,
    path: Path,
    project_root: Path,
    global_var_names: set[str],
    includes: list[str],
) -> list[dict]:
    """C++ `class_specifier` / `struct_specifier` 를 ClassNode 리스트로 변환.

    **namespace 추적**: 각 class/struct 의 ancestor chain 에서 `namespace_definition`
    노드들의 이름을 누적해 FQN 을 ``Namespace.Class`` 형식으로 구성한다.
    C++17 nested namespace (``namespace A::B { ... }``) 도 `::` → `.` 로 변환.

    **nested class 추적**: 외부 class/struct 안의 class/struct 도 ancestor chain
    에서 인지해 FQN 에 포함 (예: ``OuterClass.InnerStruct``).
    """
    out: list[dict] = []
    for n in _walk(root):
        if n.type not in ("class_specifier", "struct_specifier"):
            continue
        name_node = n.child_by_field_name("name")
        if name_node is None:
            continue
        name = src[name_node.start_byte:name_node.end_byte].decode("utf-8", "replace")
        body = n.child_by_field_name("body")
        if body is None:
            continue

        ns_chain, outer_classes = _enclosing_scopes(n, src)
        prefix_parts = ns_chain + outer_classes
        fqn = ".".join(prefix_parts + [name]) if prefix_parts else name
        namespace_text = ".".join(ns_chain) if ns_chain else None

        methods: list[dict] = []
        for c in body.children:
            if c.type == "function_definition":
                m = _function_to_method(c, src, global_var_names, class_prefix=name)
                if m is not None:
                    methods.append(m)
        base_types = _extract_base_clause(n, src)
        out.append({
            "name": name,
            "fully_qualified_name": fqn,
            "namespace": namespace_text,
            "kind": "class" if n.type == "class_specifier" else "struct",
            "start_line": n.start_point[0] + 1,
            "end_line": n.end_point[0] + 1,
            "is_static": False,
            "is_partial": False,
            "is_abstract": False,
            "base_types": base_types,
            "referenced_types": sorted({_include_stem(h) for h in includes if _include_stem(h)}),
            "static_member_accesses": _global_accesses_across(methods, global_var_names),
            "singleton_accesses": [],
            "methods": methods,
        })
    return out


def _enclosing_scopes(class_node: Node, src: bytes) -> tuple[list[str], list[str]]:
    """class_node 의 ancestor chain 을 따라 enclosing namespace + outer class 누적.

    Returns
    -------
    (namespaces, outer_classes) — 둘 다 outermost → innermost 순서.

    nested namespace (``namespace A::B::C { ... }``) 는 `::` 를 `.` 로 변환해
    단일 항목으로 추가한다.
    """
    namespaces: list[str] = []
    outers: list[str] = []
    cur = class_node.parent
    while cur is not None:
        if cur.type == "namespace_definition":
            name_node = cur.child_by_field_name("name")
            if name_node is not None:
                ns_text = src[name_node.start_byte:name_node.end_byte].decode("utf-8", "replace")
                # C++17 nested-namespace (A::B::C) → 단일 dotted string
                ns_text = ns_text.replace("::", ".").strip()
                if ns_text:
                    namespaces.append(ns_text)
        elif cur.type in ("class_specifier", "struct_specifier"):
            outer_name = cur.child_by_field_name("name")
            if outer_name is not None:
                outers.append(
                    src[outer_name.start_byte:outer_name.end_byte].decode("utf-8", "replace")
                )
        cur = cur.parent
    return list(reversed(namespaces)), list(reversed(outers))


def _extract_base_clause(class_node: Node, src: bytes) -> list[str]:
    out: list[str] = []
    for c in class_node.children:
        if c.type == "base_class_clause":
            for ident in _walk(c):
                if ident.type in ("type_identifier", "identifier"):
                    out.append(src[ident.start_byte:ident.end_byte].decode("utf-8", "replace"))
    # dedup, preserve order
    seen: set[str] = set()
    deduped: list[str] = []
    for x in out:
        if x not in seen:
            seen.add(x)
            deduped.append(x)
    return deduped


def _function_to_method(
    node: Node,
    src: bytes,
    global_var_names: set[str],
    class_prefix: str | None = None,
) -> dict | None:
    name = _function_name(node, src)
    if not name:
        return None

    body = node.child_by_field_name("body")
    if body is None:
        return None

    cc = _cyclomatic_complexity(body)
    invoked = sorted(_invoked_names(body, src))
    global_accesses = _global_accesses(body, src, global_var_names)
    loc = node.end_point[0] - node.start_point[0] + 1
    parameter_count = _parameter_count(node)
    return_type = _return_type(node, src)
    signature = _signature(node, src)

    method = {
        "name": name,
        "signature": signature,
        "start_line": node.start_point[0] + 1,
        "end_line": node.end_point[0] + 1,
        "parameter_count": parameter_count,
        "return_type": return_type,
        "is_static": "static" in signature.split("(")[0].split(),
        "is_async": False,
        "is_override": False,
        "cyclomatic_complexity": cc,
        "loc": loc,
        "invoked_names": invoked,
        "is_game_loop_entry": _is_game_loop_name(name),
        # 클래스 단위 집계 시 사용할 helper
        "_global_accesses": global_accesses,
    }
    return method


def _function_name(node: Node, src: bytes) -> str | None:
    """function_definition 노드의 함수 이름을 추출한다."""
    declarator = node.child_by_field_name("declarator")
    if declarator is None:
        return None
    # 가장 안쪽 function_declarator 찾기 (pointer_declarator 가 감쌀 수 있음)
    target = declarator
    visited = 0
    while target is not None and target.type != "function_declarator" and visited < 8:
        next_decl = target.child_by_field_name("declarator")
        if next_decl is None:
            break
        target = next_decl
        visited += 1
    if target is None or target.type != "function_declarator":
        # fallback: walk
        for n in _walk(declarator):
            if n.type == "function_declarator":
                target = n
                break
        else:
            return None
    inner = target.child_by_field_name("declarator")
    if inner is None:
        return None
    if inner.type == "identifier":
        return src[inner.start_byte:inner.end_byte].decode("utf-8", "replace")
    if inner.type == "field_identifier":
        return src[inner.start_byte:inner.end_byte].decode("utf-8", "replace")
    if inner.type == "qualified_identifier":
        # C++: A::B::Foo → Foo
        text = src[inner.start_byte:inner.end_byte].decode("utf-8", "replace")
        return text.rsplit("::", 1)[-1]
    if inner.type == "destructor_name":
        text = src[inner.start_byte:inner.end_byte].decode("utf-8", "replace")
        return text  # `~ClassName`
    # 마지막 시도: 식별자 노드를 찾아 반환
    for n in _walk(inner):
        if n.type in ("identifier", "field_identifier"):
            return src[n.start_byte:n.end_byte].decode("utf-8", "replace")
    return None


def _parameter_count(node: Node) -> int:
    """function_declarator 의 parameter_list 안 parameter_declaration 수."""
    for n in _walk(node):
        if n.type == "parameter_list":
            cnt = 0
            for c in n.children:
                if c.type in ("parameter_declaration", "variadic_parameter_declaration"):
                    cnt += 1
            # 매개변수가 (void) 인 경우 0
            if cnt == 1:
                only = next((c for c in n.children if c.type == "parameter_declaration"), None)
                if only is not None and only.text.strip() == b"void":
                    return 0
            return cnt
    return 0


def _return_type(node: Node, src: bytes) -> str:
    """function_definition 의 return type 필드."""
    rt = node.child_by_field_name("type")
    if rt is None:
        return ""
    return src[rt.start_byte:rt.end_byte].decode("utf-8", "replace").strip()


def _signature(node: Node, src: bytes) -> str:
    """선언 헤더(반환 타입 + declarator)를 한 줄 문자열로 표현."""
    # body 시작 직전까지의 텍스트
    body = node.child_by_field_name("body")
    if body is None:
        return ""
    sig_bytes = src[node.start_byte:body.start_byte]
    text = sig_bytes.decode("utf-8", "replace").strip()
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# Cyclomatic Complexity / 호출·전역 추출
# ---------------------------------------------------------------------------


# tree-sitter-c / tree-sitter-cpp 의 제어 흐름 노드 타입
_CC_BRANCH_TYPES = {
    "if_statement", "while_statement", "for_statement", "do_statement",
    "case_statement",                # switch 의 각 case (default 포함하지만 default 는 별도 처리)
    "conditional_expression",        # 삼항 ?:
    "catch_clause",                  # C++ try/catch
}

_CC_BINARY_OPS_AND_OR = {"&&", "||"}


def _cyclomatic_complexity(body: Node) -> int:
    """McCabe CC. 시작값 1, 분기 노드/연산자마다 +1.

    `default` case 와 일반 case 의 구분: tree-sitter 의 ``case_statement`` 노드는
    case 와 default 둘 다 같은 타입을 사용한다. 차별화하려면 텍스트의 첫 토큰을 본다.
    여기서는 `default` 라도 +1 로 처리해 단순화한다 (csharp-analyzer 와 차이는 미미).
    """
    cc = 1
    for n in _walk(body):
        if n.type in _CC_BRANCH_TYPES:
            cc += 1
        elif n.type == "binary_expression":
            op_field = n.child_by_field_name("operator")
            if op_field is not None:
                op_text = (op_field.text or b"").decode("utf-8", "replace")
                if op_text in _CC_BINARY_OPS_AND_OR:
                    cc += 1
    return cc


def _invoked_names(body: Node, src: bytes) -> set[str]:
    """함수 본문의 `call_expression` 에서 호출 대상의 마지막 식별자만 모은다."""
    out: set[str] = set()
    for n in _walk(body):
        if n.type == "call_expression":
            callee = n.child_by_field_name("function")
            if callee is None:
                continue
            name = _callee_simple_name(callee, src)
            if name:
                out.add(name)
    return out


def _callee_simple_name(node: Node, src: bytes) -> str | None:
    """call_expression.function 에서 simple name 추출.

    - `foo(x)`        → `foo`
    - `obj.bar(x)`    → `bar`
    - `ns::Foo::Bar()` → `Bar`
    - `obj->baz(x)`   → `baz`
    """
    if node.type == "identifier":
        return src[node.start_byte:node.end_byte].decode("utf-8", "replace")
    if node.type == "field_expression":
        field = node.child_by_field_name("field")
        if field is not None:
            return src[field.start_byte:field.end_byte].decode("utf-8", "replace")
    if node.type == "qualified_identifier":
        text = src[node.start_byte:node.end_byte].decode("utf-8", "replace")
        return text.rsplit("::", 1)[-1]
    # fallback: 마지막 identifier
    last: str | None = None
    for n in _walk(node):
        if n.type in ("identifier", "field_identifier"):
            last = src[n.start_byte:n.end_byte].decode("utf-8", "replace")
    return last


def _global_accesses(body: Node, src: bytes, global_var_names: set[str]) -> list[str]:
    """함수 본문에서 전역 변수 식별자가 사용된 횟수만큼 이름을 모은다 (중복 허용)."""
    if not global_var_names:
        return []
    out: list[str] = []
    for n in _walk(body):
        if n.type != "identifier":
            continue
        # call_expression.function 의 identifier 는 함수 호출이므로 제외
        if n.parent is not None and n.parent.type == "call_expression" and \
                n.parent.child_by_field_name("function") is n:
            continue
        name = src[n.start_byte:n.end_byte].decode("utf-8", "replace")
        if name in global_var_names:
            out.append(name)
    return out


# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------


def _walk(node: Node):
    """노드와 모든 후손을 deterministic 한 순서로 산출한다."""
    stack = [node]
    while stack:
        cur = stack.pop()
        yield cur
        # 자식을 역순으로 push 해 prefix-order 유지
        for c in reversed(cur.children):
            stack.append(c)


def _count_loc(src: bytes) -> int:
    """비주석·비공백 줄 수."""
    in_block = False
    count = 0
    for raw in src.splitlines():
        try:
            line = raw.decode("utf-8", "replace")
        except Exception:
            continue
        s = line.strip()
        if not s:
            continue
        if in_block:
            if "*/" in s:
                in_block = False
                after = s.split("*/", 1)[1].strip()
                if after and not after.startswith("//"):
                    count += 1
            continue
        if s.startswith("//"):
            continue
        if s.startswith("/*"):
            if "*/" not in s[2:]:
                in_block = True
            else:
                # /* ... */ on same line
                tail = s.split("*/", 1)[1].strip()
                if tail and not tail.startswith("//"):
                    count += 1
            continue
        count += 1
    return count
