"""Phase A 검증 결과를 단일 HTML 파일로 시각화한다.

본 모듈은 `validate.py` 의 산출물(`ValidationResult` 또는 `validation.json`)을
받아 산점도(SVG)와 상관계수 표를 포함한 단일 페이지를 생성한다. CDN 의존성
없이 동작하며, `report.py` 의 메인 대시보드와 분리되어 있어 후속 수정의
표면적을 줄인다.

생성되는 파일은 ``validation.html`` 한 개이다 — `analyze` 의 ``index.html``
옆에 두는 것을 기본 배치로 한다.
"""

from __future__ import annotations

import html
import json
import math
from pathlib import Path
from typing import Any

from .validate import ValidationResult


# 등급별 색상 (report.py 와 동일)
GRADE_COLORS = {
    "A": "#3b8e5a",
    "B": "#7fb95a",
    "C": "#e3b341",
    "D": "#ef7d3c",
    "E": "#d24343",
}


def generate_validation_html(
    result: ValidationResult,
    output_path: Path,
    project_name: str | None = None,
) -> Path:
    """검증 리포트 HTML을 작성하고 경로를 반환한다."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_render_html(result, project_name), encoding="utf-8")
    return output_path


# ---------------------------------------------------------------------------
# 렌더링
# ---------------------------------------------------------------------------


def _render_html(r: ValidationResult, project_name: str | None) -> str:
    title = project_name or (r.subdir or "G-SI Validation")
    return _PAGE.format(
        title=html.escape(title),
        meta=_render_meta(r),
        correlations=_render_correlation_section(r),
        scatter=_render_scatter_section(r),
        top_files=_render_top_files_table(r),
        notes=_render_notes(r),
    )


def _render_meta(r: ValidationResult) -> str:
    rows = [
        ("repo", r.repo_path),
        ("subdir", r.subdir or "(repo root)"),
        ("date range", f"{r.since or '*'} .. {r.until or '*'}"),
        ("commits scanned", f"{r.total_commits:,}"),
        ("bug-fix commits", f"{r.bugfix_commits:,}"),
        (
            "classes / files",
            f"{r.classes_total:,} classes ({r.classes_with_bugfix:,} touched) · "
            f"{r.files_total:,} files ({r.files_with_bugfix:,} touched)",
        ),
        ("unmatched changes", f"{r.unmatched_change_count:,} (non-class assets/configs)"),
        ("keywords", ", ".join(r.keywords)),
    ]
    body = "\n".join(
        f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>"
        for k, v in rows
    )
    return f"<table class='meta'>{body}</table>"


def _render_correlation_section(r: ValidationResult) -> str:
    def _table(title: str, hint: str, stats) -> str:
        rows = []
        for s in stats:
            rho = "—" if math.isnan(s.spearman_rho) else f"{s.spearman_rho:+.4f}"
            p = "—" if s.p_value is None else (f"{s.p_value:.4g}" if s.p_value > 0 else "<1e-6")
            cls = _rho_class(s.spearman_rho)
            rows.append(
                f"<tr class='{cls}'>"
                f"<td>{html.escape(s.name)}</td>"
                f"<td class='num'>{s.n:,}</td>"
                f"<td class='num rho'>{rho}</td>"
                f"<td class='num p'>{p}</td>"
                f"</tr>"
            )
        return (
            f"<div class='corr-block'>"
            f"<h3>{html.escape(title)}</h3>"
            f"<p class='hint'>{html.escape(hint)}</p>"
            f"<table class='corr'>"
            f"<thead><tr><th>지표</th><th>n</th><th>Spearman ρ</th><th>p-value</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            f"</table>"
            f"</div>"
        )

    return (
        "<section>"
        "<h2>Spearman 순위 상관계수</h2>"
        + _table(
            "파일 단위",
            "Git 변경의 자연 단위가 파일이므로 1차 해석 지표로 사용한다. "
            "정렬 기준은 plan §4.1: 파일 si_max, loc 합, cc_max.",
            r.file_correlations,
        )
        + _table(
            "클래스 단위",
            "한 파일에 다수 클래스가 있을 경우 동일 bug-fix 카운트를 공유한다. "
            "결과 해석 시 plan §13 \"분석 단위 부적합\" 항을 참고한다.",
            r.class_correlations,
        )
        + "</section>"
    )


def _rho_class(rho: float) -> str:
    if math.isnan(rho):
        return "rho-na"
    if rho >= 0.3:
        return "rho-pos-strong"
    if rho > 0:
        return "rho-pos"
    if rho <= -0.3:
        return "rho-neg-strong"
    return "rho-neg"


def _render_scatter_section(r: ValidationResult) -> str:
    """파일 단위 산점도(G-SI vs bug-fix)를 SVG로 그린다.

    축은 G-SI 0~100, bug-fix 0~max. log scale 은 사용하지 않는다 (해석 용이성).
    bug-fix 0 인 파일도 함께 그린다 (회색 점).
    """
    rows = r.file_rows
    if not rows:
        return "<section><h2>산점도</h2><p>데이터 없음.</p></section>"

    width = 720
    height = 420
    margin = {"left": 60, "right": 24, "top": 30, "bottom": 50}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]

    max_bug = max((fr.bugfix_count for fr in rows), default=0)
    if max_bug <= 0:
        max_bug = 1
    # x: G-SI 0~100, y: bug-fix 0~max
    def _x(si: float) -> float:
        return margin["left"] + (si / 100.0) * plot_w

    def _y(b: float) -> float:
        return margin["top"] + plot_h - (b / max_bug) * plot_h

    # 그리드 + 축
    x_ticks = [0, 20, 40, 60, 80, 100]
    # y ticks: 5단계
    y_step = max(1, math.ceil(max_bug / 5))
    y_ticks = list(range(0, max_bug + 1, y_step))
    if y_ticks[-1] < max_bug:
        y_ticks.append(max_bug)

    parts: list[str] = []
    parts.append(f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" class="scatter">')
    # 축 영역 배경
    parts.append(
        f'<rect x="{margin["left"]}" y="{margin["top"]}" '
        f'width="{plot_w}" height="{plot_h}" fill="#fafafa" stroke="#ddd"/>'
    )
    # 그리드 + tick
    for xt in x_ticks:
        x = _x(xt)
        parts.append(f'<line x1="{x:.1f}" y1="{margin["top"]}" x2="{x:.1f}" y2="{margin["top"]+plot_h}" stroke="#eee"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{margin["top"]+plot_h+18}" '
            f'text-anchor="middle" font-size="11" fill="#666">{xt}</text>'
        )
    for yt in y_ticks:
        y = _y(yt)
        parts.append(f'<line x1="{margin["left"]}" y1="{y:.1f}" x2="{margin["left"]+plot_w}" y2="{y:.1f}" stroke="#eee"/>')
        parts.append(
            f'<text x="{margin["left"]-6}" y="{y+4:.1f}" '
            f'text-anchor="end" font-size="11" fill="#666">{yt}</text>'
        )
    # 축 라벨
    parts.append(
        f'<text x="{margin["left"]+plot_w/2:.1f}" y="{height-12}" '
        f'text-anchor="middle" font-size="12" fill="#333">파일 G-SI (max within file, 0~100)</text>'
    )
    parts.append(
        f'<text x="14" y="{margin["top"]+plot_h/2:.1f}" '
        f'text-anchor="middle" font-size="12" fill="#333" '
        f'transform="rotate(-90 14 {margin["top"]+plot_h/2:.1f})">bug-fix commit touch count</text>'
    )
    # 점
    for fr in sorted(rows, key=lambda r: r.bugfix_count):
        cx = _x(fr.si_max)
        cy = _y(fr.bugfix_count)
        # 등급으로 색 선택 (파일 si_max 기준 등급)
        grade = _grade(fr.si_max)
        color = GRADE_COLORS.get(grade, "#888")
        opacity = 0.85 if fr.bugfix_count > 0 else 0.35
        r_px = 3.5 if fr.bugfix_count == 0 else 4.5
        tooltip = (
            f"{fr.file_path}\\nG-SI(max)={fr.si_max:.1f}  classes={fr.class_count}  "
            f"LOC={fr.loc_total}  bug-fix={fr.bugfix_count}"
        )
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r_px}" '
            f'fill="{color}" fill-opacity="{opacity}" stroke="#333" stroke-width="0.4">'
            f'<title>{html.escape(tooltip)}</title>'
            f'</circle>'
        )
    parts.append('</svg>')

    return (
        "<section>"
        "<h2>산점도: 파일 G-SI(max) vs bug-fix 빈도</h2>"
        "<p class='hint'>각 점은 분석된 한 개의 .cs 파일이다. 색상은 파일 si_max 의 등급(A~E)이며, "
        "회색조 점(왼쪽 아래) 은 bug-fix 가 없는 파일이다. 점에 마우스를 올리면 파일 경로가 표시된다.</p>"
        + "".join(parts)
        + "</section>"
    )


def _render_top_files_table(r: ValidationResult) -> str:
    if not r.top_bugfix_files:
        return ""
    file_by_path = {fr.file_path: fr for fr in r.file_rows}
    rows = []
    for path, count in r.top_bugfix_files[:15]:
        fr = file_by_path.get(path)
        si_max = f"{fr.si_max:.1f}" if fr else "—"
        loc = f"{fr.loc_total:,}" if fr else "—"
        grade = _grade(fr.si_max) if fr else "?"
        color = GRADE_COLORS.get(grade, "#888")
        rows.append(
            f"<tr>"
            f"<td class='num'>{count}</td>"
            f"<td><span class='badge' style='background:{color}'>{grade}</span> "
            f"<code>{html.escape(path)}</code></td>"
            f"<td class='num'>{si_max}</td>"
            f"<td class='num'>{loc}</td>"
            f"</tr>"
        )
    return (
        "<section>"
        "<h2>가장 자주 bug-fix 된 분석 파일 (상위 15)</h2>"
        "<table class='top'>"
        "<thead><tr><th>fix #</th><th>파일</th><th>G-SI (max)</th><th>LOC</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        "</section>"
    )


def _render_notes(r: ValidationResult) -> str:
    if not r.notes:
        return ""
    items = "".join(f"<li>{html.escape(n)}</li>" for n in r.notes)
    return f"<section><h2>진단 메모</h2><ul class='notes'>{items}</ul></section>"


def _grade(si: float) -> str:
    if si < 20: return "A"
    if si < 40: return "B"
    if si < 60: return "C"
    if si < 80: return "D"
    return "E"


# ---------------------------------------------------------------------------
# 페이지 템플릿 (단일 파일, CDN 의존성 없음)
# ---------------------------------------------------------------------------


_PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<title>{title} — G-SI Validation (Phase A)</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "Noto Sans KR", sans-serif;
          color: #222; background: #fff; margin: 0; padding: 24px; line-height: 1.5; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  h2 {{ font-size: 17px; margin: 28px 0 10px; border-bottom: 1px solid #eee; padding-bottom: 4px; }}
  h3 {{ font-size: 14px; margin: 14px 0 6px; color: #555; }}
  table {{ border-collapse: collapse; font-size: 13px; }}
  .meta {{ margin: 6px 0 0; }}
  .meta th {{ text-align: left; color: #666; font-weight: 500; padding: 2px 12px 2px 0; width: 150px; }}
  .meta td {{ padding: 2px 0; font-family: ui-monospace, Consolas, monospace; color: #222; }}
  table.corr {{ margin: 4px 0 6px; min-width: 460px; }}
  table.corr th, table.corr td {{ padding: 4px 10px; border-bottom: 1px solid #f0f0f0; }}
  table.corr th {{ background: #f7f7f7; font-weight: 500; text-align: left; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.rho {{ font-weight: 600; }}
  tr.rho-pos-strong td.rho {{ color: #1f7a3a; }}
  tr.rho-pos td.rho {{ color: #5a9d4a; }}
  tr.rho-neg td.rho {{ color: #c47b30; }}
  tr.rho-neg-strong td.rho {{ color: #b53a3a; }}
  .corr-block {{ display: inline-block; vertical-align: top; margin-right: 24px; }}
  .hint {{ color: #666; font-size: 12px; margin: 2px 0 6px; max-width: 700px; }}
  .scatter {{ width: 100%; max-width: 760px; height: auto; }}
  table.top {{ min-width: 600px; }}
  table.top th, table.top td {{ padding: 4px 10px; border-bottom: 1px solid #f0f0f0; }}
  table.top th {{ background: #f7f7f7; font-weight: 500; text-align: left; }}
  .badge {{ display: inline-block; width: 18px; height: 18px; line-height: 18px;
            text-align: center; color: #fff; font-size: 11px; font-weight: 600;
            border-radius: 3px; margin-right: 6px; vertical-align: middle; }}
  code {{ font-family: ui-monospace, Consolas, monospace; font-size: 12px; background: #f6f8fa; padding: 1px 4px; border-radius: 3px; }}
  ul.notes li {{ color: #555; }}
  footer {{ margin-top: 40px; color: #888; font-size: 11px; }}
</style>
</head>
<body>
<h1>{title} — G-SI Validation (Phase A)</h1>
<p class="hint">Plan §7.1 Phase A — Git bug-fix 커밋 빈도와 G-SI / LOC / CC 간의 Spearman 순위 상관 검증.</p>
{meta}
{correlations}
{scatter}
{top_files}
{notes}
<footer>생성: game-si validate · 본 페이지는 단일 파일 HTML이며 CDN 등 외부 리소스에 의존하지 않는다.</footer>
</body>
</html>
"""
