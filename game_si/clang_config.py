"""Read compilation contexts without executing build commands or compilers."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Iterable

from .cpp_analyzer import DEFAULT_EXCLUDE_DIRS, _collect_files


def path_key(path: Path | str) -> str:
    return os.path.normcase(str(Path(path).resolve()))


def _absolute(value: str, directory: Path) -> str:
    path = Path(value)
    return str((path if path.is_absolute() else directory / path).resolve())


_COMPILER = re.compile(r"(?:clang\+\+|clang|clang-cl|gcc|g\+\+|cc|c\+\+|cl)(?:-\d+(?:\.\d+)*)?(?:\.exe)?$")
_PATH_FLAGS = ("-isystem", "-iquote", "-idirafter", "-include", "-imacros",
               "-isysroot", "-resource-dir", "-I")
_VALUE_FLAGS = {"-D", "-U", "-std", "-x", "-target", "--target"}
_SAFE_FLAGS = {"-m32", "-m64", "-pthread", "-nostdinc", "-nostdinc++",
               "-fchar8_t", "-fno-char8_t", "-fPIC", "-fpic", "-fPIE", "-fpie",
               "-fms-extensions", "-fms-compatibility", "-fno-ms-compatibility",
               "-fdeclspec", "-fno-exceptions", "-fexceptions", "-fno-rtti", "-frtti",
               "-fshort-wchar", "-fshort-enums", "-fsigned-char", "-funsigned-char"}
_DROP_FLAGS = {"-c", "-S", "-E", "-g", "-g0", "-g1", "-g2", "-g3", "-pipe",
               "-M", "-MM", "-MD", "-MMD",
               "-MP", "-MG", "-shared", "-static", "-rdynamic", "-Wall", "-Wextra",
               "-Werror", "-w", "-pedantic", "-pedantic-errors"}
_DROP_VALUE = {"-o", "-MF", "-MT", "-MQ", "-L", "-l"}


def normalize_arguments(arguments: list[str], directory: Path, source: Path) -> list[str]:
    """A deliberately bounded whitelist; unsupported flags require an explicit context."""
    if not isinstance(arguments, list) or not arguments or not all(
            isinstance(arg, str) and arg for arg in arguments):
        raise ValueError("compile_commands 항목에는 비어 있지 않은 arguments 문자열 배열이 필요합니다.")
    compiler = arguments[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    if not _COMPILER.fullmatch(compiler):
        raise ValueError(f"지원하지 않는 compiler 또는 wrapper: {arguments[0]}")
    for arg in arguments:
        if arg.startswith("@") or re.search(r"[\n\r\x00;|&`$<>]", arg):
            raise ValueError(f"response file 또는 shell 형태 인자는 허용하지 않습니다: {arg}")
        if any(part.startswith(("-load", "-plugin", "-add-plugin", "-fplugin", "-fpass-plugin",
                                "-Xclang", "-Xpreprocessor")) for part in arg.split(",")):
            raise ValueError(f"plugin/load 또는 forwarded compiler 인자는 허용하지 않습니다: {arg}")
    out = []
    i = 1
    while i < len(arguments):
        arg = arguments[i]
        i += 1
        if not arg.startswith("-") and path_key(_absolute(arg, directory)) == path_key(source):
            continue
        if arg in _PATH_FLAGS or arg in _VALUE_FLAGS or arg in _DROP_VALUE or arg == "--sysroot":
            if i == len(arguments) or arguments[i].startswith("-"):
                raise ValueError(f"인자의 값이 없습니다: {arg}")
            value = arguments[i]
            i += 1
            if arg in _PATH_FLAGS or arg == "--sysroot":
                out.extend([arg, _absolute(value, directory)])
            elif arg in _VALUE_FLAGS:
                out.extend([arg, value])
            continue
        matched = False
        for flag in _PATH_FLAGS:
            if arg.startswith(flag) and len(arg) > len(flag):
                value = arg[len(flag):]
                if value.startswith("-"):
                    raise ValueError(f"지원하지 않는 분석 인자: {arg}")
                if value.startswith("="):
                    value = value[1:]
                    if not value:
                        raise ValueError(f"인자의 값이 없습니다: {arg}")
                    out.extend([flag, _absolute(value, directory)])
                else:
                    out.append(flag + _absolute(value, directory))
                matched = True
                break
        if matched:
            continue
        if arg.startswith("--sysroot="):
            out.append("--sysroot=" + _absolute(arg.split("=", 1)[1], directory))
        elif arg in _SAFE_FLAGS or re.fullmatch(
                r"(?:-std=.+|--?target=.+|-fms-compatibility-version=\d+(?:\.\d+)*|-ferror-limit=\d+)", arg):
            out.append(arg)
        elif arg.startswith(("-D", "-U")) and len(arg) > 2:
            out.append(arg)
        elif re.fullmatch(r"-O(?:[0-3sgz]|fast)?", arg):
            out.append(arg)
        elif arg in _DROP_FLAGS:
            continue
        # Only separated -o is accepted: broad -o prefix matching also swallowed
        # unsupported language options such as -objc and -openmp.
        elif any(arg.startswith(flag) and len(arg) > len(flag) for flag in _DROP_VALUE - {"-o"}):
            continue
        elif arg.startswith("-Wl,"):
            continue
        elif arg in {"/c", "/nologo", "/Zi", "/Z7", "/MD", "/MDd", "/MT", "/MTd", "/EHsc"}:
            continue
        elif re.fullmatch(r"/(?:O[12dxt]|W[0-4]|WX-?)", arg):
            continue
        elif arg in {"/TP", "/TC", "/permissive-"}:
            out.extend(["-x", "c++" if arg == "/TP" else "c"]) if arg != "/permissive-" else None
        elif arg.startswith("/std:"):
            out.append("-std=" + arg[5:])
        elif arg.startswith(("/D", "/U", "/I", "/FI")):
            flag = "/FI" if arg.startswith("/FI") else arg[:2]
            value = arg[len(flag):]
            if not value:
                if i == len(arguments):
                    raise ValueError(f"인자의 값이 없습니다: {arg}")
                value = arguments[i]
                i += 1
            if flag in {"/I", "/FI"}:
                out.extend(["-I" if flag == "/I" else "-include", _absolute(value, directory)])
            else:
                out.append("-" + flag[1:] + value)
        elif arg.startswith(("/Fo", "/Fd", "/Fe")):
            if len(arg) == 3:
                if i == len(arguments):
                    raise ValueError(f"인자의 값이 없습니다: {arg}")
                i += 1
        else:
            raise ValueError(f"지원하지 않는 분석 인자: {arg}")
    if compiler in {"cl", "cl.exe", "clang-cl", "clang-cl.exe"}:
        out.extend(["-fms-extensions", "-fms-compatibility"])
    if (source.suffix.lower() == ".c" and "-x" not in out and re.fullmatch(
            r"(?:clang\+\+|g\+\+|c\+\+)(?:-\d+(?:\.\d+)*)?(?:\.exe)?", compiler)):
        # Index.parse receives no driver executable, so retain the C++ driver's
        # language default where it differs from the source extension.
        out.extend(["-x", "c++"])
    return out


def load_configuration(input_path: Path, compile_commands: Path,
                       excludes: Iterable[str] = ()) -> dict:
    root = Path(input_path).resolve()
    if not root.exists():
        raise ValueError(f"입력 경로가 없습니다: {root}")
    database = Path(compile_commands).resolve()
    try:
        raw = database.read_bytes()
        entries = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"compile_commands.json 읽기 실패: {database}: {exc}") from exc
    if not isinstance(entries, list):
        raise ValueError("compile_commands.json 최상위는 배열이어야 합니다.")
    collection_errors = []
    files = _collect_files(root, DEFAULT_EXCLUDE_DIRS | set(excludes), collection_errors)
    selected = {path_key(path): path.resolve() for path in files}
    grouped: dict[str, list[tuple[int, dict, Path]]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            raise ValueError(f"compile_commands 항목 {index}: file 문자열이 필요합니다.")
        directory_value = entry.get("directory")
        valid_directory = isinstance(directory_value, str) and bool(directory_value)
        directory = Path(_absolute(directory_value, database.parent)) if valid_directory else database.parent
        key = path_key(_absolute(entry["file"], directory))
        if key in selected:
            if not valid_directory:
                raise ValueError(f"compile_commands 항목 {index}: directory 문자열이 필요합니다.")
            grouped.setdefault(key, []).append((index, entry, directory))
    if not grouped:
        raise ValueError("입력 구현 파일과 compile_commands.json 사이에 등록된 교집합(intersection)이 없습니다.")
    normalized = []
    for key, source in selected.items():
        alternatives = grouped.get(key)
        if not alternatives:
            continue
        index, entry, directory = alternatives[0]
        args = normalize_arguments(entry.get("arguments"), directory, source)
        normalized.append({"path": str(source), "directory": str(directory),
                           "arguments": args, "entry_index": index,
                           "alternatives_count": len(alternatives) - 1})
    return {"path": str(database), "sha256": hashlib.sha256(raw).hexdigest(),
            "entries": normalized, "unregistered_files": [str(path) for key, path in
                selected.items() if key not in grouped], "collection_errors": collection_errors}
