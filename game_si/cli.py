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
import json
import sys
from pathlib import Path

from . import __version__
from .analyzer import (
    AnalyzerExecutionError,
    AnalyzerNotFoundError,
    analyze as run_analyzer,
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
        choices=["csharp"],
        default="csharp",
        help="분석 대상 언어 (W1 단계에서는 csharp만 지원)",
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

    # 후속 주차에서 구현될 명령들 — W1에서는 stub
    p_diff = sub.add_parser("diff", help="(W12+) 두 분석 결과의 G-SI 변화 비교")
    p_diff.add_argument("baseline_json")
    p_diff.add_argument("latest_json")

    p_validate = sub.add_parser("validate", help="(W13+) Git 변경 이력으로 G-SI 검증")
    p_validate.add_argument("repo")
    p_validate.add_argument("--since", help="검증에 사용할 시점 (YYYY-MM-DD)")

    p_compare = sub.add_parser("compare", help="(W16+) 외부 도구 결과와 G-SI 비교")
    p_compare.add_argument("our_json")
    p_compare.add_argument("other_json")

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

    try:
        result = run_analyzer(input_path=input_path, output_path=output_json, excludes=args.exclude)
    except (AnalyzerNotFoundError, AnalyzerExecutionError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    summary = result.summary
    print(
        f"[ok] files={summary.get('total_files')} "
        f"classes={summary.get('total_classes')} "
        f"methods={summary.get('total_methods')} "
        f"loc={summary.get('total_loc')} "
        f"elapsed={summary.get('elapsed_ms')}ms"
    )
    if result.errors:
        print(f"[warn] {len(result.errors)} files failed to parse", file=sys.stderr)

    if output_json is not None:
        print(f"[ok] wrote {output_json}")

    if args.top and args.top > 0:
        _print_top_methods(result.data, args.top)

    return 0


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


def _cmd_stub(name: str) -> int:
    print(
        f"[info] '{name}' 명령은 후속 주차에서 구현될 예정입니다.\n"
        f"       W1 단계에서는 'analyze'만 동작합니다.",
        file=sys.stderr,
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "analyze":
        return _cmd_analyze(args)
    if args.command in {"diff", "validate", "compare"}:
        return _cmd_stub(args.command)

    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
