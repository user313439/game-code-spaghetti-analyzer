"""Build settings the app already knows for its demo game, so that game gets the precise (Clang) analysis.

A preset only lists compiler options (language standard, macros, include folders) copied from the game's
own Visual Studio project. The app never runs a project's build scripts. A preset applies only when the
imported source is byte-for-byte the prepared original, so the options are known to match the code.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO = REPO_ROOT / 'docs' / '_demo_phase_v2'
SOURCE_SUFFIXES = {'.c', '.h', '.cpp', '.hpp'}
PRESETS = {
    'opentyrian': {
        'name': 'OpenTyrian',
        'baseline': DEMO / '01_original' / 'source' / 'src',
        'language': 'c',
        'std': 'c17',
        # From visualc/opentyrian.vcxproj (Release, x64, WITH_NETWORK=false).
        'defines': ['TARGET_WIN32', '_CRT_SECURE_NO_WARNINGS', '_WINDOWS', 'NDEBUG'],
        'includes': [DEMO / 'dependencies' / 'SDL2-2.32.10' / 'include'],
    },
}
LIBCLANG = [REPO_ROOT / 'docs' / '_verification' / '2026-10-05-cpp-feasibility' / 'clang20' / 'Library' / 'bin' / 'libclang-13.dll',
            Path(r'C:\Program Files\LLVM\bin\libclang.dll')]


def _tree(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and not p.is_symlink() and p.suffix.lower() in SOURCE_SUFFIXES}


def _version(path: Path) -> tuple:
    try:
        return tuple(int(part) for part in path.name.split('.'))
    except ValueError:
        return ()


def toolchain_includes() -> list[Path] | None:
    # Standard C headers of the installed Visual Studio Build Tools and Windows SDK.
    msvc = [p for base in (Path(r'C:\Program Files (x86)\Microsoft Visual Studio'), Path(r'C:\Program Files\Microsoft Visual Studio'))
            for p in base.glob('*/*/VC/Tools/MSVC/*') if (p / 'include').is_dir()]
    kits = [p for p in Path(r'C:\Program Files (x86)\Windows Kits\10\Include').glob('10.*') if (p / 'ucrt').is_dir()]
    if not msvc or not kits:
        return None
    tools, kit = max(msvc, key=_version), max(kits, key=_version)
    return [tools / 'include', kit / 'ucrt', kit / 'shared', kit / 'um']


def libclang() -> Path | None:
    for candidate in [os.environ.get('GAME_SI_CLANG_LIBRARY'), *LIBCLANG]:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def detect(root: Path) -> list[dict]:
    """Folders under root whose sources equal a preset's prepared original: [{key, name, folder}]."""
    found = []
    for key, preset in PRESETS.items():
        baseline_root = preset['baseline']
        if not baseline_root.is_dir():
            continue
        baseline = _tree(baseline_root)
        marker = min(baseline)   # any file of the original; candidates are the folders that contain it
        for hit in root.rglob(Path(marker).name):
            folder = hit.parent
            for _ in Path(marker).parts[:-1]:
                folder = folder.parent
            try:
                if folder.is_dir() and _tree(folder) == baseline:
                    found.append({'key': key, 'name': preset['name'], 'folder': folder.relative_to(root).as_posix() or '.'})
            except OSError:
                continue
    return found


def match(selected: Path) -> dict | None:
    """The preset folder at or below the folder chosen for analysis, if any."""
    for hit in detect(selected):
        return hit
    return None


def write_database(folder: Path, key: str, output: Path) -> Path:
    """compile_commands.json for every implementation file under folder, with the preset's options."""
    preset = PRESETS[key]
    includes = toolchain_includes()
    if includes is None:
        raise ValueError('정밀 분석에 필요한 Visual Studio Build Tools 또는 Windows SDK 헤더를 찾지 못했습니다.')
    language = preset['language']
    suffixes = {'.c'} if language == 'c' else {'.cpp', '.cc', '.cxx'}
    files = sorted(p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file() and p.suffix.lower() in suffixes)
    entries = [{'directory': str(folder), 'file': rel, 'arguments': [
        'clang', '-x', language, f"-std={preset['std']}", '-fms-extensions', '-fms-compatibility', '-ferror-limit=0',
        *[f'-I{path.as_posix()}' for path in [*includes, *preset['includes']]],
        '-target', 'x86_64-pc-windows-msvc', *[f'-D{name}' for name in preset['defines']],
        '-c', rel, '-o', 'unused.obj']} for rel in files]
    output.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding='utf8')
    return output


def revision_database(options: dict, original: Path, revision: Path, output: Path) -> Path:
    """Compile settings for a revised copy: same options, paths moved from the original folder to the copy."""
    if options.get('preset') in PRESETS:
        folder = revision if options.get('preset_folder', '.') == '.' else revision / options['preset_folder']
        return write_database(folder, options['preset'], output)
    entries = json.loads(Path(options['compile_commands']).read_text('utf8'))
    old = [str(original), original.as_posix()]
    new = [str(revision), revision.as_posix()]

    def moved(value):
        if isinstance(value, str):
            for before, after in zip(old, new):
                value = value.replace(before, after)
            return value
        if isinstance(value, list):
            return [moved(item) for item in value]
        return value
    output.write_text(json.dumps([{key: moved(value) for key, value in entry.items()} for entry in entries],
                                 ensure_ascii=False, indent=1), encoding='utf8')
    return output
