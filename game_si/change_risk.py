"""W14 (확장) — ChangeRisk 산출.

plan §4.4 의 ChangeRisk 항목을 산출한다.

> ChangeRisk = 최근 N개월(기본 12개월) 동안 해당 파일을 수정한 커밋 수 +
>              그 중 bug-fix 키워드 매칭 커밋 비율 (두 값을 결합)

본 구현은 두 값을 다음과 같이 결합한다.

    change_risk(file) = total_changes_in_window * (1 + bugfix_ratio)

즉 자주 수정된 파일은 기본 점수가 높고, 그 중 bug-fix 비율이 높으면 추가 가산.
plan 이 정확한 결합식을 명시하지 않았으므로 본 정의를 보고서에 함께 기술한다.

**데이터 누수 방지 (plan §3.2)**: ChangeRisk 는 git 변경 이력 기반이므로 Phase A
의 정답값(bug-fix count) 과 같은 출처를 공유한다. G-SI-Full 은 따라서 검증의
정답값으로 직접 사용되지 않으며, 본 작품은 G-SI-Full 을 **보조 지표**로 분리하여
별도 산출만 한다 (plan 명시).
"""

from __future__ import annotations

import datetime as _dt
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .gitlog import is_bugfix_subject


@dataclass
class ChangeRiskRow:
    file_path: str            # subdir 기준 상대 경로 (subdir 이 None 이면 repo 루트)
    repo_path: str            # 저장소 루트 기준 전체 경로
    total_changes: int        # window 내 commit 수
    bugfix_changes: int       # 그 중 bug-fix subject 매칭 수
    bugfix_ratio: float       # bugfix_changes / total_changes
    change_risk: float        # total_changes * (1 + bugfix_ratio)


def compute_change_risk(
    repo: Path,
    subdir: str | None,
    months: int = 12,
    until: str | None = None,
) -> dict[str, ChangeRiskRow]:
    """저장소 git 로그 기준 파일별 ChangeRisk 값 산출.

    Parameters
    ----------
    repo : Path
        대상 git working tree.
    subdir : str | None
        저장소 루트로부터 분석 대상 서브 디렉토리. 결과 키는 subdir 기준 상대경로.
    months : int
        time window. plan 기본 12 개월.

    Returns
    -------
    dict[str, ChangeRiskRow]
        ``file_path`` (subdir 기준 상대경로, POSIX) → ChangeRiskRow.
    """
    repo = Path(repo).resolve()
    end_date = _dt.date.fromisoformat(until) if until else _dt.datetime.utcnow().date()
    since_date = (end_date - _dt.timedelta(days=months * 30)).isoformat()

    args = [
        "log",
        "--pretty=format:__COMMIT__\x01%H\x01%s",
        "--name-only",
        "--no-merges",
        f"--since={since_date}T00:00:00Z",
    ]
    if until:
        args.append(f"--until={until}T23:59:59Z")
    if subdir:
        args.extend(["--", subdir])

    raw = _run_git(repo, args)

    subdir_prefix = ""
    if subdir:
        subdir_prefix = subdir.replace("\\", "/").strip("/") + "/"

    total_by_file: Counter[str] = Counter()
    bugfix_by_file: Counter[str] = Counter()

    current_subject: str | None = None
    current_is_fix = False
    current_files: list[str] = []

    def _flush() -> None:
        nonlocal current_subject, current_is_fix, current_files
        if current_subject is None:
            return
        for f in current_files:
            total_by_file[f] += 1
            if current_is_fix:
                bugfix_by_file[f] += 1
        current_subject = None
        current_is_fix = False
        current_files = []

    for line in raw.splitlines():
        if line.startswith("__COMMIT__\x01"):
            _flush()
            parts = line.split("\x01", 2)
            if len(parts) < 3:
                continue
            _, _sha, subject = parts
            current_subject = subject
            current_is_fix = is_bugfix_subject(subject)
            current_files = []
        else:
            path = line.strip().replace("\\", "/")
            if not path:
                continue
            if subdir_prefix and not path.startswith(subdir_prefix):
                continue
            current_files.append(path)
    _flush()

    out: dict[str, ChangeRiskRow] = {}
    for repo_relative, total in total_by_file.items():
        bugfix = bugfix_by_file.get(repo_relative, 0)
        ratio = (bugfix / total) if total else 0.0
        # subdir 기준 상대경로로 normalize
        if subdir_prefix and repo_relative.startswith(subdir_prefix):
            local = repo_relative[len(subdir_prefix):]
        else:
            local = repo_relative
        out[local] = ChangeRiskRow(
            file_path=local,
            repo_path=repo_relative,
            total_changes=total,
            bugfix_changes=bugfix,
            bugfix_ratio=ratio,
            change_risk=float(total) * (1.0 + ratio),
        )
    return out


def _run_git(repo: Path, args: list[str]) -> str:
    cmd = ["git", "-C", str(repo), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"git failed: {' '.join(cmd)}\n{(proc.stderr or '').strip()}")
    return proc.stdout
