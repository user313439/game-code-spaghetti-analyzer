"""Git log mining for W8 Phase A validation.

대상 저장소의 commit history를 훑어 bug-fix 커밋을 식별하고,
각 커밋이 변경한 파일 목록을 함께 수집한다. 결과는 `validate.py`가
G-SI 점수와 파일별 bug-fix 횟수의 Spearman 순위 상관을 계산할 때 사용된다.

본 모듈은 `git` CLI 를 subprocess로 호출하므로 별도 파이썬 라이브러리(`pygit2`)
설치가 필요 없다. Windows 콘솔에서의 한글/UTF-8 이슈를 피하기 위해 stdout
인코딩을 UTF-8로 강제한다.

키워드는 `docs/_planning/plan_final_draft.md` §7.1 에 정의된 6종(`fix`, `bug`, `crash`,
`regression`, `hotfix`, `patch`)을 사용한다. `fix typo`, `fix indent` 등
사소한 수정은 별도 필터로 제외한다.
"""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


# 본 키워드는 plan §7.1 의 정의를 따른다.
BUGFIX_KEYWORDS: tuple[str, ...] = (
    "fix", "fixes", "fixed", "fixing",
    "bug", "bugs", "buggy",
    "crash", "crashes", "crashed", "crashing",
    "regression", "regressions",
    "hotfix", "hotfixes",
    "patch", "patches",
    "defect", "defects",
)

# 사소한 수정으로 분류해 제외할 패턴 (소문자 비교).
TRIVIAL_PATTERNS: tuple[str, ...] = (
    "fix typo", "fix typos",
    "fix indent", "fix indents", "fix indentation",
    "fix formatting", "fix format",
    "fix whitespace", "fix spacing",
    "fix spelling",
    "fix comment", "fix comments",
    "fix doc", "fix docs", "fix documentation",
    "fix readme",
)

_KEYWORD_RE = re.compile(
    r"\b(?:" + "|".join(sorted(set(BUGFIX_KEYWORDS), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


@dataclass
class BugFixCommit:
    sha: str
    date: str          # ISO short, e.g. "2026-04-10"
    subject: str
    files: list[str] = field(default_factory=list)


@dataclass
class GitLogResult:
    repo_path: str
    since: str | None
    until: str | None
    path_filter: str | None
    total_commits: int                    # 스캔된 전체 (non-merge) 커밋 수
    bugfix_commits: list[BugFixCommit]    # path_filter 통과 + bug-fix subject + 변경 파일 ≥ 1
    file_touch_counts: Counter            # path → bug-fix 커밋 touch 수 (path_filter 내)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_bugfix_subject(subject: str) -> bool:
    """커밋 subject 가 bug-fix 후보인지 판정한다.

    키워드가 등장하더라도 사소한 수정(`fix typo` 등) 패턴이 있으면 제외한다.
    """
    s = (subject or "").strip().lower()
    if not s:
        return False
    if not _KEYWORD_RE.search(s):
        return False
    for trivial in TRIVIAL_PATTERNS:
        if trivial in s:
            return False
    return True


def collect_bugfix_commits(
    repo_path: Path,
    since: str | None = None,
    until: str | None = None,
    path_filter: str | None = None,
    max_commits: int | None = None,
) -> GitLogResult:
    """대상 저장소를 훑어 bug-fix 커밋과 그 변경 파일을 수집한다.

    Parameters
    ----------
    repo_path : Path
        분석할 git working tree 경로.
    since, until : str | None
        `git log --since/--until` 로 전달되는 날짜 (예: ``"2023-01-01"``).
    path_filter : str | None
        저장소 루트 기준 서브 디렉토리(예: ``"OpenRA.Game"``). 지정 시
        해당 경로 하위에 영향을 준 커밋으로 ``git log`` 를 제한하고,
        그 외 경로의 변경 파일은 결과에서 제외한다.
    max_commits : int | None
        안전 상한. ``None`` 또는 ``0`` 이면 무제한.

    Notes
    -----
    `git log --name-only` 의 출력은 commit-header 와 file-list 가 빈 줄로 구분된다.
    파서 안정성을 위해 ``--pretty=format`` 에 ASCII 제어문자(``\\x01``)와 sentinel
    토큰(``__COMMIT__``)을 함께 사용한다.
    """
    args: list[str] = [
        "log",
        # sentinel + 0x01 구분자 → 본문에 우연히 같은 문자열이 나올 확률 매우 낮음
        "--pretty=format:__COMMIT__\x01%H\x01%ad\x01%s",
        "--name-only",
        "--no-merges",
        "--date=short",
    ]
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")
    if max_commits:
        args.append(f"--max-count={max_commits}")
    if path_filter:
        args.extend(["--", path_filter])

    raw = _run_git(repo_path, args)

    bugfix: list[BugFixCommit] = []
    counter: Counter = Counter()
    total = 0
    current: BugFixCommit | None = None
    is_fix = False

    prefix = None
    if path_filter:
        # `git log` 의 file path 는 항상 POSIX 슬래시이다.
        prefix = path_filter.replace("\\", "/").strip("/") + "/"

    def _flush() -> None:
        if current is None:
            return
        if is_fix and current.files:
            bugfix.append(current)
            for f in current.files:
                counter[f] += 1

    for line in raw.splitlines():
        if line.startswith("__COMMIT__\x01"):
            _flush()
            parts = line.split("\x01", 3)
            if len(parts) < 4:
                current = None
                is_fix = False
                continue
            _, sha, date, subject = parts
            total += 1
            current = BugFixCommit(sha=sha, date=date, subject=subject)
            is_fix = is_bugfix_subject(subject)
        else:
            path = line.strip()
            if not path or current is None:
                continue
            if prefix is not None and not path.startswith(prefix):
                # path_filter 외부 경로 (rename 등으로 끼어들 수 있음) 는 제외
                continue
            current.files.append(path)
    _flush()

    return GitLogResult(
        repo_path=str(repo_path),
        since=since,
        until=until,
        path_filter=path_filter,
        total_commits=total,
        bugfix_commits=bugfix,
        file_touch_counts=counter,
    )


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _run_git(repo_path: Path, args: list[str]) -> str:
    cmd = ["git", "-C", str(repo_path), *args]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git failed (rc={proc.returncode}): {' '.join(cmd)}\n"
            + (proc.stderr or "").strip()
        )
    return proc.stdout
