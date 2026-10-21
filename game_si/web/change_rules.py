"""Line rules for link refactors: include-only companion edits and move-only declaration changes.

The analyzer spans and the compiler both count lines by '\\n' only, so every rule here splits on
'\\n' and rejects newly introduced control characters (form feed, vertical tab, Unicode line
separators) that other splitters treat as line breaks. Declaration changes are checked on
"logical" lines: backslash continuations joined, comments removed, whitespace runs collapsed.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

C_FAMILY = {'.c', '.h', '.cpp', '.cc', '.cxx', '.hpp'}
# Control characters other than tab/CR/LF, Unicode line breaks, and trigraphs (??/ is a backslash).
UNSAFE = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x85  ]|\\?\\?[=/\'()!<>-]')
RAW_INCLUDE = re.compile(r'^[ \t]*#[ \t]*include[ \t]*(?:<[^<>"\\]+>|"[^"<>\\]+")[ \t]*\r?$')
RAW_USING = re.compile(r'^[ \t]*using[ \t]+(?:static[ \t]+)?[A-Za-z_][\w.]*[ \t]*;[ \t]*\r?$')   # no aliases
LOGICAL_INCLUDE = re.compile(r'^#\s*include\s*(<[^<>"]+>|"[^"<>]+")$')
FORWARD = re.compile(r'^(?:struct|union|enum|class) [A-Za-z_]\w* ?;$')
GUARD = re.compile(r'^_*[A-Z][A-Z0-9_]*_(?:H|HH|HPP|INCLUDED)_*$')
EXTERN_C = [['#ifdef __cplusplus', 'extern "C" {', '#endif'], ['#ifdef __cplusplus', '}', '#endif']]


def unsafe_text(old: str, new: str) -> bool:
    """True when the new text adds a control character or trigraph the old text did not have."""
    found = Counter(m.group() for m in UNSAFE.finditer(new))
    before = Counter(m.group() for m in UNSAFE.finditer(old))
    return any(count > before[ch] for ch, count in found.items())


def raw_lines(text: str) -> list[str]:
    return text.replace('\r\n', '\n').split('\n')


def changed_raw_lines(before: str, after: str):
    import difflib
    old, new = raw_lines(before), raw_lines(after)
    removed, added = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag != 'equal':
            removed += old[i1:i2]
            added += new[j1:j2]
    return [l for l in removed if l.strip()], [l for l in added if l.strip()]


def logical_lines(text: str) -> list[str]:
    """Lines as the compiler sees them after splicing and comment removal, whitespace-normalised."""
    text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\\\n', '')
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in '"\'':
            j = i + 1
            while j < n and text[j] not in (c, '\n'):
                j += 2 if text[j] == '\\' else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith('//', i):
            j = text.find('\n', i)
            i = n if j < 0 else j
        elif text.startswith('/*', i):
            j = text.find('*/', i + 2)
            end = n if j < 0 else j + 2
            out.append(' ' + '\n' * text.count('\n', i, end))
            i = end
        elif c in ' \t':
            j = i
            while j < n and text[j] in ' \t':
                j += 1
            out.append(' ')
            i = j
        else:
            out.append(c)
            i += 1
    return [line.strip() for line in ''.join(out).split('\n') if line.strip()]


def include_target(line: str) -> str | None:
    match = LOGICAL_INCLUDE.match(line)
    return match.group(1)[1:-1] if match else None


def includes(text: str) -> set[str]:
    return {t for t in map(include_target, logical_lines(text)) if t}


def resolves_to(target: str, path: str) -> bool:
    """Whether '#include <target>' could pick up `path` (a relative path) through some include folder."""
    target, path = target.replace('\\', '/').lower(), path.lower()
    return path == target or path.endswith('/' + target)


def companion_ok(before: str, after: str, limit: int = 6) -> bool:
    removed, added = changed_raw_lines(before, after)
    if len(removed) > limit or len(added) > limit:
        return False
    if any(not (RAW_INCLUDE.match(l) or RAW_USING.match(l)) for l in removed + added):
        return False
    # Belt and braces: apart from include/using lines, the compiler must see exactly the same code.
    keep = lambda text: [l for l in logical_lines(text) if not include_target(l) and not RAW_USING.match(l)]
    return keep(before) == keep(after)


def _strip_guard(lines: list[str]) -> list[str]:
    lines = list(lines)
    if lines and lines[0] == '#pragma once':
        lines = lines[1:]
    if len(lines) >= 3 and lines[-1] == '#endif':
        first, second = lines[0].split(' '), lines[1].split(' ')
        if (len(first) == 2 and first[0] == '#ifndef' and GUARD.match(first[1])
                and second == ['#define', first[1]]):
            lines = lines[2:-1]
    for block in EXTERN_C:
        for i in range(len(lines) - 2):
            if lines[i:i + 3] == block:
                lines = lines[:i] + lines[i + 3:]
                break
    return lines


def content(lines, created=False):
    """Lines that carry meaning beyond include structure: these may only be moved, never written anew."""
    if created:
        lines = _strip_guard(lines)
    return [l for l in lines if not include_target(l) and not FORWARD.match(l)]


def declaration_moves(items) -> str | None:
    """items: (path, before, after, created) for declaration targets and new headers.

    Every content line added anywhere must be a line removed from a declaration target, and every
    removed one must reappear: declarations are moved between headers, not invented or dropped.
    Returns an error message or None."""
    import difflib
    removed, added, remaining = Counter(), Counter(), set()
    for path, before, after, created in items:
        if Path(path).suffix.lower() not in C_FAMILY:
            return f'{path}: 선언 정리는 C/C++ 파일만 지원합니다.'
        if created:
            lines = content(logical_lines(after), created=True)
            added.update(lines)
            remaining.update(lines)
            continue
        old, new = logical_lines(before), logical_lines(after)
        remaining.update(content(new))
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
            if tag != 'equal':
                removed.update(content(old[i1:i2]))
                added.update(content(new[j1:j2]))
    invented, dropped = added - removed, removed - added
    if invented:
        return f'선언 정리에서는 기존 선언을 옮기기만 할 수 있습니다. 새로 쓴 줄: {next(iter(invented))[:120]}'
    # A removed duplicate is fine while an identical line is still in one of the changed headers
    # (e.g. the same #define copied into two headers, now kept in one shared header).
    lost = [line for line in dropped if line not in remaining]
    if lost:
        return f'선언 정리에서 지운 선언은 다른 헤더로 옮겨야 합니다. 옮겨지지 않은 줄: {lost[0][:120]}'
    return None
