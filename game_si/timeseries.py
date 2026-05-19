"""W14 Phase D — G-SI 시계열 분석.

`docs/plan_final_draft.md` §7.4 의 Phase D 확장 실험을 수행한다.

* 대상 repo 의 git history 에서 균등 간격으로 N 개 커밋을 샘플링한다.
* 각 시점에서 별도 git worktree 를 만들어 분석을 수행 — **원본 working tree
  는 절대 흔들지 않는다**.
* 시점별 `project_health.score`, `avg_si`, `risk_ratio`, `cycle_count`,
  `grade_distribution` 을 수집해 시계열로 저장한다.
* `bug-fix 커밋 활동` 도 시점 사이 구간별로 카운트해 함께 시각화한다.
* 산출물: `timeseries.json` + `timeseries.html` (단일 파일 SVG 차트).

워크플로:

    python -m game_si timeseries <repo> --lang c --subdir src --samples 12 \\
        --out reports/<case> --project-name "Chocolate Doom"

본 모듈은 plan §3.2 의 time-split 검증의 기반도 제공한다 — 과거 시점의
G-SI 와 이후 bug-fix 활동을 함께 추적할 수 있다.
"""

from __future__ import annotations

import datetime as _dt
import html
import json
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from .gitlog import collect_bugfix_commits


SCHEMA_VERSION = "timeseries-0.1"

GRADE_COLORS = {
    "A": "#3b8e5a",
    "B": "#7fb95a",
    "C": "#e3b341",
    "D": "#ef7d3c",
    "E": "#d24343",
}


@dataclass
class TimeSeriesPoint:
    sha: str
    short_sha: str
    date: str          # ISO short (YYYY-MM-DD)
    subject: str
    health_score: float
    health_grade: str
    avg_si: float
    risk_ratio: float
    cycle_count: int
    classes_total: int
    methods_total: int
    grade_distribution: dict[str, int]
    bugfix_commits_since_prev: int  # 직전 시점 이후 ~ 현재 시점까지의 bug-fix 커밋 수
    analysis_elapsed_ms: int


@dataclass
class TimeSeriesResult:
    project: str
    repo: str
    subdir: str | None
    lang: str
    samples: int
    since: str | None
    until: str | None
    points: list[TimeSeriesPoint]
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 핵심 로직
# ---------------------------------------------------------------------------


def run_timeseries(
    repo: Path,
    lang: str,
    subdir: str | None,
    samples: int,
    project_name: str,
    since: str | None = None,
    until: str | None = None,
    progress: bool = True,
) -> TimeSeriesResult:
    """주어진 저장소에 대해 시계열 G-SI 측정을 수행한다."""
    repo = Path(repo).resolve()
    commits = _list_commits(repo, subdir=subdir, since=since, until=until)
    if not commits:
        raise RuntimeError("git log 결과가 비어 있다. since/until 또는 subdir 확인.")
    sampled = _sample_commits(commits, samples)
    if progress:
        print(f"[timeseries] total_commits={len(commits)}  sampled={len(sampled)}", flush=True)

    bugfix_commit_set = _collect_bugfix_shas(repo, subdir=subdir, since=since, until=until)
    if progress:
        print(f"[timeseries] bug-fix commits in range: {len(bugfix_commit_set)}", flush=True)

    points: list[TimeSeriesPoint] = []
    notes: list[str] = []

    # 직전 시점 이후 ~ 현재 시점 사이의 bug-fix 커밋 수
    prev_idx = -1
    for i, (sha, date, subject) in enumerate(sampled):
        if progress:
            print(
                f"[timeseries] {i+1}/{len(sampled)}  {date}  {sha[:10]}  {subject[:60]}",
                flush=True,
            )
        with _temp_worktree(repo, sha) as worktree_path:
            target = (worktree_path / subdir) if subdir else worktree_path
            if not target.exists():
                notes.append(f"{sha[:10]} ({date}): subdir 미존재 — skip")
                continue
            try:
                ph_dict, scoring_dict, ast_summary = _run_analysis(target, lang)
            except Exception as exc:  # 시점별 실패는 격리
                notes.append(f"{sha[:10]} ({date}): 분석 실패 — {exc}")
                continue

        # bug-fix 활동 카운트: 이전 sampled 시점 이후 ~ 현재 시점 (포함) 사이
        cur_pos = _find_position(commits, sha)
        if prev_idx < 0:
            count_since_prev = 0
        else:
            prev_sha = sampled[i - 1][0]
            prev_pos = _find_position(commits, prev_sha)
            window = [c[0] for c in commits[cur_pos:prev_pos]]  # 시간 역순 슬라이스
            count_since_prev = sum(1 for s in window if s in bugfix_commit_set)
        prev_idx = i

        points.append(TimeSeriesPoint(
            sha=sha,
            short_sha=sha[:10],
            date=date,
            subject=subject,
            health_score=float(ph_dict.get("score", 0.0)),
            health_grade=str(ph_dict.get("grade", "?")),
            avg_si=float(ph_dict.get("avg_si", 0.0)),
            risk_ratio=float(ph_dict.get("risk_ratio", 0.0)),
            cycle_count=int(ph_dict.get("cycle_count", 0)),
            classes_total=int(scoring_dict.get("total_classes", 0)),
            methods_total=int(scoring_dict.get("total_methods", 0)),
            grade_distribution=dict(scoring_dict.get("grade_distribution", {})),
            bugfix_commits_since_prev=count_since_prev,
            analysis_elapsed_ms=int(ast_summary.get("elapsed_ms", 0)),
        ))

    if not points:
        notes.append("샘플링된 모든 시점에서 분석에 실패했다.")

    return TimeSeriesResult(
        project=project_name,
        repo=str(repo),
        subdir=subdir,
        lang=lang,
        samples=samples,
        since=since,
        until=until,
        points=points,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# git 헬퍼
# ---------------------------------------------------------------------------


def _run_git(repo: Path, args: list[str], check: bool = True) -> str:
    cmd = ["git", "-C", str(repo), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and proc.returncode != 0:
        raise RuntimeError(f"git failed: {' '.join(cmd)}\n{(proc.stderr or '').strip()}")
    return proc.stdout


def _list_commits(
    repo: Path,
    subdir: str | None,
    since: str | None,
    until: str | None,
) -> list[tuple[str, str, str]]:
    """(sha, date, subject) 튜플 리스트. 최신 → 오래된 순서."""
    args = [
        "log",
        "--pretty=format:%H\x01%ad\x01%s",
        "--no-merges",
        "--date=short",
    ]
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")
    if subdir:
        args.extend(["--", subdir])
    text = _run_git(repo, args)
    out: list[tuple[str, str, str]] = []
    for line in text.splitlines():
        parts = line.split("\x01", 2)
        if len(parts) == 3:
            out.append((parts[0], parts[1], parts[2]))
    return out


def _sample_commits(
    commits: list[tuple[str, str, str]],
    samples: int,
) -> list[tuple[str, str, str]]:
    """commits 는 최신 → 오래된 순. 결과는 **오래된 → 최신** 순으로 균등 간격 N개."""
    if samples <= 0 or not commits:
        return []
    if samples >= len(commits):
        return list(reversed(commits))
    # 오래된 → 최신 순으로 뒤집은 뒤 균등 간격으로 픽
    chronological = list(reversed(commits))
    n = len(chronological)
    # 마지막 인덱스가 포함되도록 endpoint 보정
    if samples == 1:
        return [chronological[-1]]
    step = (n - 1) / (samples - 1)
    picked: list[tuple[str, str, str]] = []
    for i in range(samples):
        idx = round(i * step)
        idx = max(0, min(n - 1, idx))
        c = chronological[idx]
        if not picked or picked[-1][0] != c[0]:
            picked.append(c)
    return picked


def _find_position(commits: list[tuple[str, str, str]], sha: str) -> int:
    """commits (최신→오래된 순) 내 sha 의 인덱스. 없으면 -1."""
    for i, (s, _, _) in enumerate(commits):
        if s == sha:
            return i
    return -1


def _collect_bugfix_shas(
    repo: Path,
    subdir: str | None,
    since: str | None,
    until: str | None,
) -> set[str]:
    """gitlog 모듈 재사용으로 bug-fix 커밋 SHA 집합을 추출."""
    result = collect_bugfix_commits(
        repo_path=repo,
        since=since,
        until=until,
        path_filter=subdir,
    )
    return {c.sha for c in result.bugfix_commits}


class _temp_worktree:
    """git worktree add ... <sha> 컨텍스트 매니저.

    종료 시 worktree remove 까지 자동 처리. 원본 working tree 에 영향 없음.
    """

    def __init__(self, repo: Path, sha: str) -> None:
        self.repo = repo
        self.sha = sha
        self.path: Path | None = None

    def __enter__(self) -> Path:
        # tempfile 로 디렉토리 이름을 만들지만 미리 제거 — git worktree add 가
        # 디렉토리를 새로 만들어야 한다.
        tmp_root = Path(tempfile.gettempdir()) / "game_si_timeseries"
        tmp_root.mkdir(parents=True, exist_ok=True)
        suffix = f"{self.sha[:8]}_{_dt.datetime.utcnow().strftime('%H%M%S%f')}"
        wt_path = tmp_root / f"wt_{suffix}"
        _run_git(self.repo, ["worktree", "add", "--detach", str(wt_path), self.sha])
        self.path = wt_path
        return wt_path

    def __exit__(self, *exc_info) -> None:
        if self.path is None:
            return
        # worktree remove --force; 실패해도 무시
        _run_git(self.repo, ["worktree", "remove", "--force", str(self.path)], check=False)
        # 잔여 디렉토리가 있으면 강제 삭제
        if self.path.exists():
            shutil.rmtree(self.path, ignore_errors=True)


# ---------------------------------------------------------------------------
# 시점별 분석
# ---------------------------------------------------------------------------


def _run_analysis(target: Path, lang: str) -> tuple[dict, dict, dict]:
    """단일 시점에서 G-SI 산출. (project_health_dict, scoring_dict, ast_summary)."""
    from .metrics import compute_metrics
    from .si import compute_si_static, scoring_to_dict

    if lang == "csharp":
        from .analyzer import analyze as run_csharp
        result = run_csharp(input_path=target)
        ast_data = result.data
    elif lang in ("c", "cpp"):
        from .cpp_analyzer import analyze_cpp
        r = analyze_cpp(input_path=target)
        ast_data = r.data
    else:
        raise ValueError(f"unsupported lang: {lang}")

    metrics = compute_metrics(ast_data)
    scoring = compute_si_static(metrics)
    sd = scoring_to_dict(scoring)
    ph = sd.get("project_health") or {}
    return ph, sd, ast_data.get("summary", {})


# ---------------------------------------------------------------------------
# 직렬화
# ---------------------------------------------------------------------------


def to_dict(r: TimeSeriesResult) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "project": r.project,
        "repo": r.repo,
        "subdir": r.subdir,
        "lang": r.lang,
        "samples": r.samples,
        "since": r.since,
        "until": r.until,
        "points": [asdict(p) for p in r.points],
        "notes": r.notes,
    }


# ---------------------------------------------------------------------------
# HTML (단일 파일 SVG 차트)
# ---------------------------------------------------------------------------


def generate_html(result: TimeSeriesResult, output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_render_html(result), encoding="utf-8")
    return output_path


def _render_html(r: TimeSeriesResult) -> str:
    title = html.escape(r.project or "G-SI Timeseries")
    points = r.points
    return _PAGE.format(
        title=title,
        meta=_render_meta(r),
        line_chart=_render_line_chart(points),
        grade_stack=_render_grade_stack(points),
        bugfix_bar=_render_bugfix_bar(points),
        point_table=_render_point_table(points),
        notes=_render_notes(r),
    )


def _render_meta(r: TimeSeriesResult) -> str:
    rows = [
        ("repo", r.repo),
        ("subdir", r.subdir or "(repo root)"),
        ("lang", r.lang),
        ("samples", str(r.samples)),
        ("date range", f"{r.since or '*'} .. {r.until or '*'}"),
        ("sampled points", str(len(r.points))),
    ]
    body = "\n".join(
        f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>" for k, v in rows
    )
    return f"<table class='meta'>{body}</table>"


def _render_line_chart(points: list[TimeSeriesPoint]) -> str:
    if not points:
        return "<section><h2>Project Health 추이</h2><p>데이터 없음.</p></section>"
    width = 760
    height = 320
    margin = {"left": 50, "right": 24, "top": 30, "bottom": 60}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]
    n = len(points)
    x_step = plot_w / max(1, n - 1)

    def _y(v: float) -> float:
        return margin["top"] + plot_h - (v / 100.0) * plot_h

    def _x(i: int) -> float:
        return margin["left"] + i * x_step

    out = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" class="chart">']
    out.append(
        f'<rect x="{margin["left"]}" y="{margin["top"]}" width="{plot_w}" height="{plot_h}" '
        f'fill="#fafafa" stroke="#ddd"/>'
    )
    for v in (0, 20, 40, 60, 80, 100):
        y = _y(v)
        out.append(
            f'<line x1="{margin["left"]}" y1="{y:.1f}" x2="{margin["left"]+plot_w}" y2="{y:.1f}" stroke="#eee"/>'
        )
        out.append(
            f'<text x="{margin["left"]-6}" y="{y+4:.1f}" text-anchor="end" font-size="11" fill="#666">{v}</text>'
        )

    # health line
    health_path = "M " + " L ".join(
        f"{_x(i):.1f} {_y(p.health_score):.1f}" for i, p in enumerate(points)
    )
    out.append(f'<path d="{health_path}" fill="none" stroke="#2b5d8c" stroke-width="2"/>')
    # avg_si line
    avg_path = "M " + " L ".join(
        f"{_x(i):.1f} {_y(p.avg_si):.1f}" for i, p in enumerate(points)
    )
    out.append(f'<path d="{avg_path}" fill="none" stroke="#c47b30" stroke-width="1.5" stroke-dasharray="4 3"/>')

    for i, p in enumerate(points):
        color = GRADE_COLORS.get(p.health_grade, "#888")
        tip = (
            f"{p.date} {p.short_sha}\\n"
            f"health={p.health_score:.1f} ({p.health_grade})  avg_si={p.avg_si:.1f}\\n"
            f"risk_ratio={p.risk_ratio:.2%}  cycles={p.cycle_count}\\n"
            f"bugfix_since_prev={p.bugfix_commits_since_prev}"
        )
        out.append(
            f'<circle cx="{_x(i):.1f}" cy="{_y(p.health_score):.1f}" r="5" '
            f'fill="{color}" stroke="#222" stroke-width="0.6">'
            f'<title>{html.escape(tip)}</title>'
            f'</circle>'
        )
    # x labels (date) — 매 점마다 표시
    label_step = max(1, n // 8)
    for i, p in enumerate(points):
        if i % label_step != 0 and i != n - 1:
            continue
        out.append(
            f'<text x="{_x(i):.1f}" y="{margin["top"]+plot_h+18}" text-anchor="middle" '
            f'font-size="11" fill="#666" transform="rotate(-30 {_x(i):.1f} {margin["top"]+plot_h+18})">'
            f'{html.escape(p.date)}</text>'
        )
    # legend
    legend_x = margin["left"] + 10
    legend_y = margin["top"] + 14
    out.append(
        f'<g><rect x="{legend_x}" y="{legend_y-8}" width="14" height="3" fill="#2b5d8c"/>'
        f'<text x="{legend_x+20}" y="{legend_y}" font-size="11">Project Health</text></g>'
    )
    out.append(
        f'<g><rect x="{legend_x+130}" y="{legend_y-8}" width="14" height="3" fill="#c47b30"/>'
        f'<text x="{legend_x+150}" y="{legend_y}" font-size="11">avg G-SI</text></g>'
    )
    out.append('</svg>')
    return (
        "<section>"
        "<h2>Project Health 추이</h2>"
        "<p class='hint'>본 그래프는 plan §4.5 의 percentile rank 정의에 따라 산출된 G-SI 와 "
        "프로젝트 단일 종합 점수(Project Health) 의 시간 변화이다. 0=건강, 100=고위험.</p>"
        + "".join(out)
        + "</section>"
    )


def _render_grade_stack(points: list[TimeSeriesPoint]) -> str:
    if not points:
        return ""
    width = 760
    height = 220
    margin = {"left": 50, "right": 24, "top": 28, "bottom": 50}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]
    n = len(points)
    x_step = plot_w / max(1, n - 1)

    out = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" class="chart">']
    out.append(
        f'<rect x="{margin["left"]}" y="{margin["top"]}" width="{plot_w}" height="{plot_h}" fill="#fafafa" stroke="#ddd"/>'
    )
    # 누적 비율을 polyline 으로
    bands = ["A", "B", "C", "D", "E"]
    series: dict[str, list[float]] = {g: [] for g in bands}  # 누적값 (위에서 아래로)
    for p in points:
        total = max(1, sum(p.grade_distribution.values()))
        cumulative = 0.0
        # 위 → 아래 순서로 E,D,C,B,A 가 쌓이도록 — 시각화는 A 가 아래
        # SVG 좌표는 위가 0 — A 가 아래쪽에 보이려면 누적은 A,B,C,D,E 순
        for g in bands:
            cumulative += p.grade_distribution.get(g, 0) / total * 100.0
            series[g].append(cumulative)

    def _x(i: int) -> float:
        return margin["left"] + i * x_step

    def _y(pct: float) -> float:
        return margin["top"] + plot_h - (pct / 100.0) * plot_h

    # 영역: 0~A, A~A+B, ...
    prev_top = [0.0] * n
    for g in bands:
        top = series[g]
        # polygon: prev_top 라인 위 + top 라인 아래로 닫음
        points_xy = [(i, prev_top[i]) for i in range(n)] + [(i, top[i]) for i in range(n - 1, -1, -1)]
        d = "M " + " L ".join(f"{_x(i):.1f} {_y(v):.1f}" for i, v in points_xy) + " Z"
        out.append(f'<path d="{d}" fill="{GRADE_COLORS[g]}" fill-opacity="0.85"/>')
        prev_top = list(top)

    # legend
    legend_x = margin["left"] + 10
    legend_y = margin["top"] + 14
    for k, g in enumerate(bands):
        out.append(
            f'<g><rect x="{legend_x + k*50}" y="{legend_y-8}" width="14" height="10" fill="{GRADE_COLORS[g]}"/>'
            f'<text x="{legend_x + k*50 + 18}" y="{legend_y}" font-size="11">{g}</text></g>'
        )
    label_step = max(1, n // 8)
    for i, p in enumerate(points):
        if i % label_step != 0 and i != n - 1:
            continue
        out.append(
            f'<text x="{_x(i):.1f}" y="{margin["top"]+plot_h+18}" text-anchor="middle" font-size="11" fill="#666" '
            f'transform="rotate(-30 {_x(i):.1f} {margin["top"]+plot_h+18})">{html.escape(p.date)}</text>'
        )
    out.append('</svg>')
    return (
        "<section><h2>등급 분포 시계열</h2>"
        "<p class='hint'>각 색은 A~E 등급의 비율. percentile rank 정의상 안정 분포가 기본이지만, "
        "구조가 단순화/복잡화 되면 분포 자체가 이동할 수 있다.</p>"
        + "".join(out)
        + "</section>"
    )


def _render_bugfix_bar(points: list[TimeSeriesPoint]) -> str:
    if not points:
        return ""
    width = 760
    height = 200
    margin = {"left": 50, "right": 24, "top": 28, "bottom": 50}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]
    n = len(points)
    x_step = plot_w / max(1, n)
    bar_w = max(2.0, x_step * 0.7)

    max_b = max((p.bugfix_commits_since_prev for p in points), default=0)
    if max_b <= 0:
        max_b = 1

    out = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" class="chart">']
    out.append(
        f'<rect x="{margin["left"]}" y="{margin["top"]}" width="{plot_w}" height="{plot_h}" fill="#fafafa" stroke="#ddd"/>'
    )
    # y ticks
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        v = int(max_b * frac)
        y = margin["top"] + plot_h - frac * plot_h
        out.append(f'<line x1="{margin["left"]}" y1="{y:.1f}" x2="{margin["left"]+plot_w}" y2="{y:.1f}" stroke="#eee"/>')
        out.append(f'<text x="{margin["left"]-6}" y="{y+4:.1f}" text-anchor="end" font-size="11" fill="#666">{v}</text>')

    for i, p in enumerate(points):
        h = (p.bugfix_commits_since_prev / max_b) * plot_h
        x = margin["left"] + i * x_step + (x_step - bar_w) / 2
        y = margin["top"] + plot_h - h
        out.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
            f'fill="#7e57c2" fill-opacity="0.85">'
            f'<title>{html.escape(p.date)}: {p.bugfix_commits_since_prev} bug-fix</title>'
            f'</rect>'
        )
    label_step = max(1, n // 8)
    for i, p in enumerate(points):
        if i % label_step != 0 and i != n - 1:
            continue
        cx = margin["left"] + i * x_step + x_step / 2
        out.append(
            f'<text x="{cx:.1f}" y="{margin["top"]+plot_h+18}" text-anchor="middle" font-size="11" fill="#666" '
            f'transform="rotate(-30 {cx:.1f} {margin["top"]+plot_h+18})">{html.escape(p.date)}</text>'
        )
    out.append('</svg>')
    return (
        "<section><h2>bug-fix 활동 (직전 시점 이후 ~ 현재 시점)</h2>"
        "<p class='hint'>각 막대는 이전 sample 시점부터 현재 sample 시점까지의 bug-fix 커밋 수다. "
        "Health 그래프와 함께 보면 활동량이 많은 구간이 G-SI 에 어떻게 반영되는지 시사한다.</p>"
        + "".join(out)
        + "</section>"
    )


def _render_point_table(points: list[TimeSeriesPoint]) -> str:
    if not points:
        return ""
    rows = []
    for p in points:
        color = GRADE_COLORS.get(p.health_grade, "#888")
        rows.append(
            f"<tr>"
            f"<td>{html.escape(p.date)}</td>"
            f"<td><code>{html.escape(p.short_sha)}</code></td>"
            f"<td><span class='badge' style='background:{color}'>{p.health_grade}</span> {p.health_score:.1f}</td>"
            f"<td class='num'>{p.avg_si:.1f}</td>"
            f"<td class='num'>{p.risk_ratio*100:.1f}%</td>"
            f"<td class='num'>{p.cycle_count}</td>"
            f"<td class='num'>{p.classes_total:,}</td>"
            f"<td class='num'>{p.bugfix_commits_since_prev}</td>"
            f"<td class='subj'>{html.escape(p.subject[:60])}</td>"
            f"</tr>"
        )
    return (
        "<section><h2>시점별 측정값</h2>"
        "<table class='points'>"
        "<thead><tr><th>date</th><th>sha</th><th>health</th><th>avg G-SI</th>"
        "<th>risk%</th><th>cycles</th><th>classes</th><th>bugfix Δ</th><th>subject</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></section>"
    )


def _render_notes(r: TimeSeriesResult) -> str:
    if not r.notes:
        return ""
    items = "".join(f"<li>{html.escape(n)}</li>" for n in r.notes)
    return f"<section><h2>비고</h2><ul class='notes'>{items}</ul></section>"


_PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<title>{title} — G-SI 시계열 (Phase D)</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "Noto Sans KR", sans-serif;
          color: #222; background: #fff; margin: 0; padding: 24px; line-height: 1.5; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  h2 {{ font-size: 17px; margin: 28px 0 10px; border-bottom: 1px solid #eee; padding-bottom: 4px; }}
  .hint {{ color: #666; font-size: 12px; margin: 2px 0 8px; max-width: 760px; }}
  table.meta th {{ text-align: left; color: #666; font-weight: 500; padding: 2px 12px 2px 0; width: 150px; }}
  table.meta td {{ padding: 2px 0; font-family: ui-monospace, Consolas, monospace; color: #222; }}
  svg.chart {{ width: 100%; max-width: 800px; height: auto; }}
  table.points {{ border-collapse: collapse; font-size: 12px; }}
  table.points th, table.points td {{ padding: 3px 8px; border-bottom: 1px solid #f0f0f0; text-align: left; }}
  table.points th {{ background: #f7f7f7; font-weight: 500; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.subj {{ color: #666; font-style: italic; }}
  .badge {{ display: inline-block; width: 18px; height: 18px; line-height: 18px;
           text-align: center; color: #fff; font-size: 11px; font-weight: 600;
           border-radius: 3px; margin-right: 4px; vertical-align: middle; }}
  code {{ font-family: ui-monospace, Consolas, monospace; font-size: 11px;
          background: #f6f8fa; padding: 1px 4px; border-radius: 3px; }}
  ul.notes li {{ color: #555; font-size: 12px; }}
  footer {{ margin-top: 40px; color: #888; font-size: 11px; }}
</style>
</head>
<body>
<h1>{title} — G-SI 시계열 (Phase D)</h1>
<p class='hint'>Plan §7.4 Phase D — 균등 간격으로 샘플링한 시점들의 Project Health · avg G-SI · 등급 분포 · bug-fix 활동을 시각화한다.</p>
{meta}
{line_chart}
{grade_stack}
{bugfix_bar}
{point_table}
{notes}
<footer>생성: game-si timeseries · 단일 파일 HTML · CDN 외부 의존성 없음.</footer>
</body></html>
"""
