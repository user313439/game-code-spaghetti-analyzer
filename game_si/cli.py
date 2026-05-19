"""game-si 명령줄 인터페이스.

W1 단계에서는 `analyze` 서브커맨드만 실제 동작하며,
나머지 서브커맨드(`diff`, `validate`, `compare`)는 후속 주차에 구현된다.

Examples
--------
    # 단일 프로젝트 분석
    python -m game_si analyze ./benchmarks/OpenRA/OpenRA.Game --lang csharp \\
        --out ./reports/openra-game/

    # 상위 N개 hotspot만 콘솔에 출력
    python -m game_si analyze ./benchmarks/OpenRA/OpenRA.Game --top 10
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

from . import __version__
from .analyzer import (
    AnalyzerExecutionError,
    AnalyzerNotFoundError,
    analyze as run_analyzer,
)


def _force_utf8_streams() -> None:
    """Windows 콘솔(cp949)에서 한글 출력이 깨지지 않도록 stdout/stderr을 UTF-8로 강제한다."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
                continue
            except Exception:
                pass
        # 폴백: 버퍼를 새 TextIOWrapper로 감싼다.
        buffer = getattr(stream, "buffer", None)
        if buffer is not None:
            setattr(
                sys,
                stream_name,
                io.TextIOWrapper(buffer, encoding="utf-8", errors="replace", line_buffering=True),
            )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="game-si",
        description="Game Spaghetti Index 측정 및 시각화 도구",
    )
    parser.add_argument("--version", action="version", version=f"game-si {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    # analyze
    p_analyze = sub.add_parser("analyze", help="단일 프로젝트 정적 분석을 수행한다.")
    p_analyze.add_argument("input", help="분석할 디렉토리, .cs 파일, 또는 .sln 경로")
    p_analyze.add_argument(
        "--lang",
        choices=["csharp", "c", "cpp", "auto"],
        default="auto",
        help="분석 대상 언어. `auto` 는 디렉토리 내 확장자 분포로 자동 선택한다.",
    )
    p_analyze.add_argument(
        "--out",
        type=Path,
        help="결과 디렉토리. JSON과 (후속 단계에서 추가될) HTML이 저장된다.",
    )
    p_analyze.add_argument(
        "--top",
        type=int,
        default=0,
        help="콘솔에 출력할 상위 hotspot 수 (0이면 출력 안 함)",
    )
    p_analyze.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="추가로 제외할 디렉토리 이름 (반복 가능)",
    )
    p_analyze.add_argument(
        "--no-score",
        action="store_true",
        help="G-SI 산출과 대시보드 생성을 건너뛰고 AST JSON만 출력한다.",
    )
    p_analyze.add_argument(
        "--no-html",
        action="store_true",
        help="HTML 대시보드를 생성하지 않는다 (JSON만 저장).",
    )
    p_analyze.add_argument(
        "--project-name",
        default=None,
        help="대시보드 헤더에 표시할 프로젝트 이름. 기본값은 입력 디렉토리 이름.",
    )
    p_analyze.add_argument(
        "--dashboard-top",
        type=int,
        default=30,
        help="대시보드 Hotspot Table에 표시할 클래스 수 (기본 30).",
    )

    # 후속 주차에서 구현될 명령들 — W1에서는 stub
    p_diff = sub.add_parser("diff", help="(W12+) 두 분석 결과의 G-SI 변화 비교")
    p_diff.add_argument("baseline_json")
    p_diff.add_argument("latest_json")

    p_validate = sub.add_parser(
        "validate",
        help="Phase A: bug-fix 커밋 빈도와 G-SI의 Spearman 상관을 측정한다.",
    )
    p_validate.add_argument("repo", help="대상 git working tree 경로 (예: ./benchmarks/OpenRA)")
    p_validate.add_argument(
        "--scoring",
        type=Path,
        required=True,
        help="이미 산출된 scoring.json 경로 (analyze 의 출력)",
    )
    p_validate.add_argument(
        "--subdir",
        default=None,
        help="저장소 루트로부터 분석 대상 서브 디렉토리 (예: OpenRA.Game). "
             "지정하면 git log 가 해당 경로로 제한되고, scoring.json 의 상대 경로와 매핑된다.",
    )
    p_validate.add_argument("--since", help="시작일 (YYYY-MM-DD)")
    p_validate.add_argument("--until", help="종료일 (YYYY-MM-DD)")
    p_validate.add_argument(
        "--out",
        type=Path,
        default=None,
        help="validation.json/validation_summary.txt 출력 디렉토리. 기본은 scoring.json 디렉토리.",
    )
    p_validate.add_argument(
        "--max-commits",
        type=int,
        default=0,
        help="안전 상한 (0=무제한). git log 가 너무 클 때 사용.",
    )
    p_validate.add_argument(
        "--no-html",
        action="store_true",
        help="validation.html 생성을 건너뛰고 JSON/summary 만 출력한다.",
    )
    p_validate.add_argument(
        "--project-name",
        default=None,
        help="validation.html 헤더에 표시할 프로젝트 이름. 기본값은 --subdir 또는 scoring.json 디렉토리 이름.",
    )

    p_advise = sub.add_parser(
        "advise",
        help="Phase C: 상위 hotspot 에 대해 Claude Haiku 로 리팩토링 가이드를 받는다.",
    )
    p_advise.add_argument("--scoring", type=Path, required=True, help="analyze 가 산출한 scoring.json")
    p_advise.add_argument(
        "--ast", type=Path, default=None,
        help="코드 스니펫 추출에 사용할 ast.json. 기본은 scoring.json 옆의 ast.json.",
    )
    p_advise.add_argument("--top", type=int, default=5, help="조언을 받을 상위 hotspot 수 (기본 5, 권장 5~10)")
    p_advise.add_argument(
        "--out", type=Path, default=None,
        help="advisor.{json,md} 출력 디렉토리. 기본은 scoring.json 디렉토리.",
    )
    p_advise.add_argument("--project-name", default=None, help="리포트 헤더 표시용 이름")
    p_advise.add_argument(
        "--model", default="claude-haiku-4-5",
        help="Anthropic 모델 ID (기본: claude-haiku-4-5).",
    )

    p_compare = sub.add_parser(
        "compare",
        help="Phase B: 외부 도구(Lizard) hotspot 과 G-SI hotspot 을 비교한다.",
    )
    p_compare.add_argument("input", help="분석 대상 디렉토리 (analyze 와 동일한 경로)")
    p_compare.add_argument("--scoring", type=Path, required=True, help="analyze 가 산출한 scoring.json")
    p_compare.add_argument(
        "--out", type=Path, default=None,
        help="compare.{json,html,_summary.txt} 출력 디렉토리. 기본은 scoring.json 디렉토리.",
    )
    p_compare.add_argument(
        "--top-ns", default="5,10,30",
        help="Jaccard 비교에 사용할 top-N 값들 (콤마 구분, 기본: 5,10,30).",
    )
    p_compare.add_argument(
        "--project-name", default=None,
        help="요약/HTML 헤더 표시용 프로젝트 이름.",
    )

    return parser


def _cmd_analyze(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[error] 입력 경로가 존재하지 않습니다: {input_path}", file=sys.stderr)
        return 1

    out_dir = args.out
    output_json: Path | None = None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        output_json = out_dir / "ast.json"

    lang = _resolve_language(args.lang, input_path)
    print(f"[ast] language: {lang}")

    # 1) 언어별 analyzer 실행 → AST JSON
    try:
        if lang == "csharp":
            result_data, result_errors = _run_csharp(input_path, output_json, args.exclude)
        else:
            result_data, result_errors = _run_cpp(input_path, output_json, args.exclude)
    except (AnalyzerNotFoundError, AnalyzerExecutionError, RuntimeError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    summary = result_data.get("summary", {})
    print(
        f"[ast] files={summary.get('total_files')} "
        f"classes={summary.get('total_classes')} "
        f"methods={summary.get('total_methods')} "
        f"loc={summary.get('total_loc')} "
        f"elapsed={summary.get('elapsed_ms')}ms"
    )
    if result_errors:
        print(f"[warn] {len(result_errors)} files failed to parse", file=sys.stderr)
    if output_json is not None:
        print(f"[ast] wrote {output_json}")

    if args.no_score:
        if args.top and args.top > 0:
            _print_top_methods(result_data, args.top)
        return 0

    # 후속 단계가 사용하는 shim — 기존 코드 호환 (result.data 형태)
    class _ResultShim:
        data = result_data
    result = _ResultShim()

    # 2) Metric Engine
    from .metrics import compute_metrics, metrics_to_dict
    metrics = compute_metrics(result.data)
    print(
        f"[metrics] classes={len(metrics.classes)} methods={len(metrics.methods)} "
        f"sccs(size>=2)={len(metrics.sccs)} "
        f"class_edges={metrics.class_graph.number_of_edges()}"
    )

    # 3) G-SI 산출
    from .si import compute_si_static, scoring_to_dict
    scoring = compute_si_static(metrics)
    print(
        "[si] grade distribution: "
        + " ".join(f"{g}={scoring.grade_distribution[g]}" for g in "ABCDE")
    )

    # 4) 결과 저장 (out 디렉토리가 지정된 경우)
    if out_dir is not None:
        (out_dir / "metrics.json").write_text(
            json.dumps(metrics_to_dict(metrics), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[metrics] wrote {out_dir / 'metrics.json'}")
        (out_dir / "scoring.json").write_text(
            json.dumps(scoring_to_dict(scoring), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[si] wrote {out_dir / 'scoring.json'}")

        if not args.no_html:
            from .report import generate_dashboard
            project_name = args.project_name or _default_project_name(input_path)
            html_path = generate_dashboard(
                project_name=project_name,
                scoring=scoring,
                metrics=metrics,
                output_path=out_dir / "index.html",
                top_n=args.dashboard_top,
            )
            print(f"[dashboard] wrote {html_path}")

    if args.top and args.top > 0:
        _print_top_classes(scoring, args.top)

    return 0


def _resolve_language(lang_arg: str, input_path: Path) -> str:
    """`--lang auto` 일 때 디렉토리 내 확장자 분포로 csharp / c / cpp 를 결정한다.

    뒤섞인 경우 (.c 와 .cpp 가 함께 존재) cpp 가 더 일반적이므로 cpp 로 본다.
    .cs 가 1 개 이상이면 csharp 우선.
    """
    if lang_arg != "auto":
        return lang_arg
    counts = {"csharp": 0, "c": 0, "cpp": 0}
    from .cpp_analyzer import C_EXTENSIONS, CPP_EXTENSIONS
    if input_path.is_file():
        suf = input_path.suffix.lower()
        if suf == ".cs":
            return "csharp"
        if suf in CPP_EXTENSIONS:
            return "cpp"
        if suf in C_EXTENSIONS:
            return "c"
        # 기본
        return "csharp"
    for p in input_path.rglob("*"):
        if not p.is_file():
            continue
        suf = p.suffix.lower()
        if suf == ".cs":
            counts["csharp"] += 1
        elif suf in CPP_EXTENSIONS:
            counts["cpp"] += 1
        elif suf in C_EXTENSIONS:
            counts["c"] += 1
    if counts["csharp"] > 0 and counts["csharp"] >= counts["cpp"] + counts["c"]:
        return "csharp"
    if counts["cpp"] > 0:
        return "cpp"
    if counts["c"] > 0:
        return "c"
    # 폴백 (확장자가 하나도 안 잡혔을 때)
    return "csharp"


def _run_csharp(
    input_path: Path,
    output_json: Path | None,
    excludes: list[str],
) -> tuple[dict, list[dict]]:
    result = run_analyzer(input_path=input_path, output_path=output_json, excludes=excludes)
    return result.data, result.errors


def _run_cpp(
    input_path: Path,
    output_json: Path | None,
    excludes: list[str],
) -> tuple[dict, list[dict]]:
    from .cpp_analyzer import analyze_cpp
    r = analyze_cpp(input_path=input_path, excludes=excludes, output_path=output_json)
    return r.data, r.errors


def _default_project_name(input_path: Path) -> str:
    """입력 경로에서 합리적인 프로젝트 이름을 추출한다."""
    p = input_path.resolve()
    if p.is_file():
        return p.parent.name
    return p.name


def _print_top_classes(scoring, top_n: int) -> None:
    rows = sorted(scoring.class_scores, key=lambda c: -c.si)[:top_n]
    print()
    print(f"=== Top {len(rows)} classes by G-SI-Static ===")
    for i, cs in enumerate(rows, 1):
        reasons = ", ".join(cs.top_reasons) if cs.top_reasons else "—"
        print(
            f"  {i:>2}. [{cs.grade}] G-SI={cs.si:6.2f}  CC={cs.raw['cc']:.1f}  "
            f"CP={int(cs.raw['coupling']):>3}  GS={int(cs.raw['global_state']):>3}  "
            f"CL={int(cs.raw['dependency_cycle']):>2}  GLC={cs.raw['game_loop_centrality']:.2f}  "
            f"{cs.fqn}"
        )
        print(f"        reasons: {reasons}")


def _print_top_methods(data: dict, top_n: int) -> None:
    """W1에서는 CC만 기준으로 상위 N개를 출력한다.

    후속 주차에서 G-SI 점수로 정렬되도록 확장한다.
    """
    rows = []
    for f in data.get("files", []):
        for c in f.get("classes", []):
            for m in c.get("methods", []):
                rows.append({
                    "cc": m["cyclomatic_complexity"],
                    "loc": m["loc"],
                    "name": f"{c['fully_qualified_name']}.{m['name']}",
                    "path": f["relative_path"],
                    "line": m["start_line"],
                })
    rows.sort(key=lambda r: -r["cc"])

    print()
    print(f"=== Top {min(top_n, len(rows))} methods by Cyclomatic Complexity ===")
    for r in rows[:top_n]:
        print(f"  CC={r['cc']:>3}  LOC={r['loc']:>4}  {r['name']}")
        print(f"        {r['path']}:{r['line']}")


def _cmd_validate(args: argparse.Namespace) -> int:
    """W8 Phase A — bug-fix 커밋 빈도와 G-SI 점수의 Spearman 상관 측정.

    필수 입력:
      * ``repo``       — 대상 저장소 working tree (git CLI 가 해석 가능해야 함)
      * ``--scoring``  — analyze 가 산출한 scoring.json
    선택 입력:
      * ``--subdir``   — 저장소 루트로부터 분석 대상 서브 디렉토리
      * ``--since``    — 검증 기간 시작일 (YYYY-MM-DD)
      * ``--until``    — 검증 기간 종료일
      * ``--out``      — 결과 출력 디렉토리 (기본: scoring.json 디렉토리)
    """
    from .gitlog import collect_bugfix_commits
    from .validate import (
        format_text_summary,
        load_scoring,
        run_validation,
        to_dict,
    )

    repo_path = Path(args.repo)
    if not repo_path.exists():
        print(f"[error] repo 경로가 존재하지 않습니다: {repo_path}", file=sys.stderr)
        return 1
    if not (repo_path / ".git").exists():
        print(f"[warn] {repo_path}/.git 가 없습니다. git working tree 가 맞는지 확인하라.", file=sys.stderr)

    scoring_path: Path = args.scoring
    if not scoring_path.exists():
        print(f"[error] scoring.json 이 존재하지 않습니다: {scoring_path}", file=sys.stderr)
        return 1

    out_dir: Path = args.out if args.out is not None else scoring_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[validate] repo={repo_path}")
    print(f"[validate] scoring={scoring_path}")
    if args.subdir:
        print(f"[validate] subdir={args.subdir}")
    if args.since or args.until:
        print(f"[validate] date range: {args.since or '*'} .. {args.until or '*'}")

    try:
        gitlog = collect_bugfix_commits(
            repo_path=repo_path,
            since=args.since,
            until=args.until,
            path_filter=args.subdir,
            max_commits=(args.max_commits or None),
        )
    except RuntimeError as exc:
        print(f"[error] git log 실패: {exc}", file=sys.stderr)
        return 1

    print(
        f"[validate] commits scanned: {gitlog.total_commits}, "
        f"bug-fix commits: {len(gitlog.bugfix_commits)}, "
        f"unique touched paths: {len(gitlog.file_touch_counts)}"
    )

    scoring = load_scoring(scoring_path)
    result = run_validation(scoring=scoring, gitlog=gitlog, subdir=args.subdir)

    json_path = out_dir / "validation.json"
    summary_path = out_dir / "validation_summary.txt"
    json_path.write_text(
        json.dumps(to_dict(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary_text = format_text_summary(result)
    summary_path.write_text(summary_text + "\n", encoding="utf-8")

    print()
    print(summary_text)
    print()
    print(f"[validate] wrote {json_path}")
    print(f"[validate] wrote {summary_path}")

    if not args.no_html:
        from .validate_report import generate_validation_html
        html_name = args.project_name or args.subdir or out_dir.name
        html_path = generate_validation_html(
            result=result,
            output_path=out_dir / "validation.html",
            project_name=html_name,
        )
        print(f"[validate] wrote {html_path}")
    return 0


def _cmd_advise(args: argparse.Namespace) -> int:
    """W13 Phase C — 상위 hotspot 에 대해 LLM 리팩토링 가이드 수집."""
    from .advisor import Advisor, format_markdown, to_dict

    scoring_path: Path = args.scoring
    if not scoring_path.exists():
        print(f"[error] scoring.json 이 존재하지 않습니다: {scoring_path}", file=sys.stderr)
        return 1

    ast_path: Path | None = args.ast or (scoring_path.parent / "ast.json")
    ast_data: dict | None = None
    if ast_path is not None and ast_path.exists():
        with open(ast_path, "r", encoding="utf-8") as f:
            ast_data = json.load(f)
    else:
        print(f"[warn] ast.json 가용하지 않음 — 지표만으로 답변. ({ast_path})", file=sys.stderr)

    out_dir: Path = args.out if args.out is not None else scoring_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    project_name = args.project_name or scoring_path.parent.name
    print(f"[advise] project={project_name}  model={args.model}  top={args.top}")

    try:
        advisor = Advisor(model=args.model)
    except RuntimeError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    with open(scoring_path, "r", encoding="utf-8") as f:
        scoring = json.load(f)

    try:
        result = advisor.advise_top_n(
            scoring=scoring,
            ast_data=ast_data,
            project=project_name,
            top_n=args.top,
            progress=True,
        )
    except Exception as exc:
        print(f"[error] Advisor 호출 실패: {exc}", file=sys.stderr)
        return 1

    json_path = out_dir / "advisor.json"
    md_path = out_dir / "advisor.md"
    json_path.write_text(
        json.dumps(to_dict(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(format_markdown(result), encoding="utf-8")

    print()
    print(
        f"[advise] tokens: input={result.total_usage['input_tokens']:,} "
        f"output={result.total_usage['output_tokens']:,} "
        f"cache_write={result.total_usage['cache_creation_input_tokens']:,} "
        f"cache_read={result.total_usage['cache_read_input_tokens']:,}"
    )
    print(f"[advise] 예상 비용: ${result.estimated_cost_usd:.4f} USD")
    print(f"[advise] wrote {json_path}")
    print(f"[advise] wrote {md_path}")
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    """W13 Phase B — Lizard hotspot 과 G-SI hotspot 의 Jaccard / Spearman 비교."""
    from .compare import run_lizard, run_comparison, to_dict, format_text_summary

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[error] 입력 경로가 존재하지 않습니다: {input_path}", file=sys.stderr)
        return 1
    scoring_path: Path = args.scoring
    if not scoring_path.exists():
        print(f"[error] scoring.json 이 존재하지 않습니다: {scoring_path}", file=sys.stderr)
        return 1
    out_dir: Path = args.out if args.out is not None else scoring_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    top_ns_raw = [s.strip() for s in (args.top_ns or "").split(",") if s.strip()]
    try:
        top_ns = tuple(int(s) for s in top_ns_raw) or (5, 10, 30)
    except ValueError:
        print(f"[error] --top-ns 파싱 실패: {args.top_ns}", file=sys.stderr)
        return 1

    project_name = args.project_name or _default_project_name(input_path)
    print(f"[compare] project={project_name}")
    print(f"[compare] running lizard on {input_path}")

    lizard_stats = run_lizard(input_path)
    print(f"[compare] lizard analyzed {len(lizard_stats)} files")

    with open(scoring_path, "r", encoding="utf-8") as f:
        scoring = json.load(f)

    result = run_comparison(
        scoring=scoring,
        lizard_stats=lizard_stats,
        project=project_name,
        scoring_path=str(scoring_path),
        analyzed_path=str(input_path),
        top_ns=top_ns,
    )

    json_path = out_dir / "compare.json"
    summary_path = out_dir / "compare_summary.txt"
    json_path.write_text(
        json.dumps(to_dict(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary_text = format_text_summary(result)
    summary_path.write_text(summary_text + "\n", encoding="utf-8")

    print()
    print(summary_text)
    print()
    print(f"[compare] wrote {json_path}")
    print(f"[compare] wrote {summary_path}")
    return 0


def _cmd_stub(name: str) -> int:
    print(
        f"[info] '{name}' 명령은 후속 주차에서 구현될 예정입니다.\n"
        f"       W1 단계에서는 'analyze'만 동작합니다.",
        file=sys.stderr,
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    _force_utf8_streams()
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "analyze":
        return _cmd_analyze(args)
    if args.command == "validate":
        return _cmd_validate(args)
    if args.command == "compare":
        return _cmd_compare(args)
    if args.command == "advise":
        return _cmd_advise(args)
    if args.command in {"diff"}:
        return _cmd_stub(args.command)

    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
