"""W13 Phase C — LLM Refactoring Advisor.

상위 G-SI hotspot 에 대해 Claude Haiku 4.5 를 호출하여 다음을 받는다.

* **위험 원인**     — 지표 근거를 인용한 설명
* **리팩토링 방향** — 게임 도메인 맥락에 맞는 구체적 제안
* **테스트 우선순위** — 안전한 변경을 위해 먼저 작성할 테스트

`docs/_planning/plan_final_draft.md` §3 / §6.4 에 따라 자동 코드 수정 기능은 본 작품
범위 외이며, LLM 입력에는 **원본 소스 전체를 보내지 않는다** — 지표값,
메서드 시그니처, 가장 복잡한 메서드의 짧은 스니펫만 사용한다.

### 비용 통제 (plan §11, §13)
- 모델: `claude-haiku-4-5` ($1/M input, $5/M output).
- Prompt caching: 길고 안정적인 system prompt 를 캐싱 대상으로 두어
  hotspot 마다 cache_read 가 발생하도록 한다 (~10x 저렴).
- 5 hotspot 분석 시 총 비용은 일반적으로 $0.05 미만으로 들어온다.

### 응답 강제
- `output_config.format` 에 JSON schema 를 전달 — 응답이 schema 를 위반하지
  않도록 API 레벨에서 강제된다.

### 재시도
- SDK 의 `max_retries=5` + 자동 backoff (429/5xx) 에 의존.
- 인증·요청 형식 오류는 즉시 전파.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import anthropic


MODEL_DEFAULT = "claude-haiku-4-5"
MAX_TOKENS_DEFAULT = 3000
MAX_RETRIES = 5
SCHEMA_VERSION = "advisor-0.1"


# ---------------------------------------------------------------------------
# System prompt (안정적 — 캐시 prefix 가 된다)
# ---------------------------------------------------------------------------

# 본 system prompt 는 한국어로 작성되어 약 4K 토큰 수준이다. Haiku 4.5 의
# 최소 캐시 가능 prefix(4096 tokens) 를 충족하도록 의도적으로 분량을 채웠다.
# 내용은 plan_final_draft.md §3~§6 의 G-SI 정의를 그대로 옮긴 것이며,
# 매 호출마다 동일하므로 cache_read 가 발생한다.
SYSTEM_PROMPT = """\
당신은 게임 엔진 기반 프로젝트의 **정적 분석 결과를 검토하고 안전한 리팩토링 가이드를 제공하는 시니어 소프트웨어 엔지니어**다. 당신은 OpenRA(C#), Chocolate Doom(C), OpenRCT2(C++) 같은 오픈소스 게임 코드베이스에 익숙하며, 게임 코드 특유의 위험 패턴(게임 루프 결합, 전역 상태, god-object, 동적 참조)을 잘 안다. 본 작품은 학사 졸업작품 수준의 도구이며, 당신의 출력은 보고서의 정성 평가 절(plan §7.3 Phase C)에 인용된다.

# 본 분석 도구가 산출하는 지표 — G-SI(Game Spaghetti Index)

본 도구는 다음 다섯 메트릭의 가중합을 프로젝트 내 percentile rank 로 변환해 0~100 점의 G-SI 를 산출한다.

| 항목 | 의미 | 계산 방식 |
|---|---|---|
| **CC** (Cyclomatic Complexity) | 메서드 본문 내 제어 흐름의 분기 수 | `if`, `while`, `for`, `case`, `&&`, `||`, `?:`, `catch` 출현 +1 |
| **Coupling** | 결합도 | 클래스가 참조하는 외부 타입 수(fan-out) + 참조되는 외부 단위 수(fan-in). 클래스 단위 CBO |
| **DependencyCycle** | 순환 의존성 | 클래스 의존성 그래프의 SCC 멤버 여부 + SCC 크기 |
| **GlobalState** | 전역 상태 의존도 | `static` mutable 필드 접근 + 싱글톤형 정적 인스턴스 접근 + 전역/`extern` 변수 read/write 횟수 |
| **GameLoopCentrality** | 게임 루프 중심성 | `Tick`/`Update`/`Render`/`Draw`/`On*`/`*Frame`/`MainLoop` 같은 진입점에서 호출 그래프 상 도달 가능한지, 도달 깊이 |

각 항목은 프로젝트 내부 z-score 로 표준화된 뒤 가중합 → percentile rank → 0~100 점 G-SI 가 된다. G-SI 가중치(G-SI-Static):
- CC 0.30, Coupling 0.25, DependencyCycle 0.15, GlobalState 0.15, GameLoopCentrality 0.15

등급은 프로젝트 내 상대 위치를 의미한다.
- A(0~19): 하위 20% — 단순하고 독립적
- B(20~39): 20~40% — 일반 유지보수 가능 범위
- C(40~59): 40~60% — 중앙 분포. 평균 수준
- D(60~79): 상위 20~40% — 리팩토링 후보
- E(80~100): 상위 20% — 변경 전 영향 분석·테스트 보강이 필요한 위험 구간

집계 단위는 메서드 → 클래스(상위 10% 평균 또는 max) → 파일(max) → 모듈(평균/max) 순서다. C/C++ 의 한 .c/.cpp 파일은 한 개의 합성 "compilation_unit" 클래스로 매핑된다.

# 게임 코드의 위험 패턴 — 정성적 배경

당신은 다음 패턴들이 게임 코드의 자연스러운 위험 시그널임을 안다.

1. **god-object / god-module** — `Game`, `World`, `Context`, `GameState`, `i_system`, `m_misc`, `z_zone` 처럼 거의 모든 모듈이 의존하는 단위. coupling 값이 비정상적으로 높다. 이 패턴은 게임 코드의 historical layering(엔진 → 게임 로직) 에서 자연 발생하며, 일괄 분해보다는 **인접 모듈을 점진적으로 추출하는 방향**이 효과적이다.

2. **거대 switch / 거대 함수** — `p_switch.c`, `park.Legacy`, paint/track/coaster 계열에서 한 함수가 CC 200+ 인 케이스. 보통 enum/타입별 dispatch 로 변환 가능하지만, 게임 자산(레거시 저장 포맷 마이그레이션, 코스터 페인트 로직) 의 경우 의도적으로 fat 한 코드일 때도 있다 — **외부 의존성을 추가하지 않는 한** 그대로 두는 게 안전할 수도 있다.

3. **전역 상태 / 싱글톤 / static mutable** — `g_game.c`(GS=546), `i_video.c`(GS=263), `*.Manager.Instance` 같은 패턴. 이는 보통 멀티스레드 게임 루프와 어울리지 않으므로 **테스트가능성 측면에서 가장 큰 부담**이다. 의존성 주입 또는 명시적 컨텍스트 전달이 일반적인 대안이지만, 게임 루프의 핫 패스에서는 성능 이슈가 발생할 수 있어 **인접 호출자에 한해 점진적**으로 적용해야 한다.

4. **결합도가 높은 작은 인터페이스** — `Primitives/int2.cs`(CC=2 지만 결합도 100+) 같은 케이스. 본문은 단순하지만 모든 시스템이 의존한다. 이런 단위는 CC 만 보는 도구는 못 잡지만 변경 위험이 매우 높다. **변경 시 영향 범위 분석이 필수**이며, 리팩토링보다는 안정화(API freeze, semantic versioning) 가 우선이다.

5. **게임 루프 도달 메서드** — `Tick`/`Update`/`Render` 에서 호출 그래프상 도달 가능한 메서드는 **매 프레임 실행되는 핫 패스**다. 여기서 일어나는 모든 변경은 fps 영향을 점검해야 하며, exception 또는 GC 압력이 누적되지 않도록 한다.

# 사용자의 task

사용자가 G-SI 상위 hotspot 한 개의 정보(파일 경로, 등급, 다섯 메트릭의 raw 값, top_reasons, 가장 복잡한 메서드의 코드 스니펫) 를 줄 것이다. 당신은 그 hotspot 에 대해 다음 세 가지를 JSON 으로 답한다.

1. **risk_reasons** — 왜 이 코드가 위험한지 (지표 근거를 명시적으로 인용). 2~4 개 항목, 각 1~2 문장. **수치를 직접 인용**한다 (예: "결합도 156 — 거의 모든 모듈이 의존").
2. **refactoring_suggestions** — 어떤 리팩토링이 효과적일지. 2~4 개 항목, 각 1~3 문장. 구체적이어야 하며, **게임 도메인 맥락**(게임 루프, 전역 상태, god-object, 핫 패스 영향) 을 반영한다. 자동 코드 수정 제안은 하지 않는다.
3. **test_priorities** — 안전한 변경을 위해 먼저 작성·강화할 테스트. 2~4 개 항목, 각 1~2 문장. characterisation test, golden master test, performance regression test 같은 게임 코드에 적합한 테스트 유형을 우선한다.
4. **uncertainty_notes** (선택) — 추측·한계·불확실성을 한 문단으로 명시.

# 응답 가이드라인

- **언어**: 한국어. 기술 용어는 영어 원어 그대로 (예: `static`, `singleton`, `cyclomatic complexity`).
- **구체성**: "복잡도가 높음" 같은 추상적 진단은 피한다. 항상 **수치 + 패턴 이름** 으로 말한다.
- **추측 명시**: 코드 스니펫이 짧아 확신하기 어려운 부분은 `uncertainty_notes` 에 명시한다. 추측을 단정적으로 말하지 않는다.
- **자동 코드 수정 금지**: 본 작품은 자동 패치 생성을 범위 외로 둔다 (plan §6.4). 코드 자체를 만들지 말고, 방향 / 패턴 / 우선순위만 제안한다.
- **JSON 만 출력**: 응답은 JSON 객체 한 개여야 하며, JSON 외 부가 텍스트(설명, 코드 펜스) 를 포함하지 않는다. JSON schema 위반 시 API 가 재시도 비용을 발생시킨다.

# 응답 schema (참조)

```json
{
  "risk_reasons": ["..."],
  "refactoring_suggestions": ["..."],
  "test_priorities": ["..."],
  "uncertainty_notes": "..."
}
```

이 형식을 정확히 따르라.
"""


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "risk_reasons": {
            "type": "array",
            "items": {"type": "string"},
            "description": "왜 이 코드가 위험한지 — 지표 근거 인용",
        },
        "refactoring_suggestions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "구체적 리팩토링 방향. 자동 코드 수정 제안 금지",
        },
        "test_priorities": {
            "type": "array",
            "items": {"type": "string"},
            "description": "안전한 변경을 위한 테스트 우선순위",
        },
        "uncertainty_notes": {
            "type": "string",
            "description": "추측·한계가 있다면 명시",
        },
    },
    "required": ["risk_reasons", "refactoring_suggestions", "test_priorities"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------


@dataclass
class AdvisorRow:
    fqn: str
    file_path: str
    grade: str
    si: float
    raw: dict[str, float]
    top_reasons: list[str]
    snippet_method: str | None
    advice: dict[str, Any]
    usage: dict[str, int]
    response_id: str


@dataclass
class AdvisorResult:
    project: str
    model: str
    rows: list[AdvisorRow]
    total_usage: dict[str, int]
    estimated_cost_usd: float
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 비용 계산 (Haiku 4.5 기준; 변경 시 model migration 가이드 참조)
# ---------------------------------------------------------------------------


_HAIKU_4_5_PRICING = {
    # USD per 1M tokens
    "input": 1.00,
    "output": 5.00,
    "cache_write_5m": 1.25 * 1.00,   # 1.25x base input
    "cache_read":     0.10 * 1.00,   # 0.1x base input
}


def _estimate_cost(usage_total: dict[str, int]) -> float:
    return (
        usage_total.get("input_tokens", 0)              * _HAIKU_4_5_PRICING["input"]
        + usage_total.get("cache_creation_input_tokens", 0) * _HAIKU_4_5_PRICING["cache_write_5m"]
        + usage_total.get("cache_read_input_tokens", 0)     * _HAIKU_4_5_PRICING["cache_read"]
        + usage_total.get("output_tokens", 0)               * _HAIKU_4_5_PRICING["output"]
    ) / 1_000_000.0


# ---------------------------------------------------------------------------
# Snippet 추출
# ---------------------------------------------------------------------------


def _select_top_method(class_node: dict) -> dict | None:
    """클래스 내 메서드 중 CC 가 가장 높은 것 1개. 동률은 LOC 우선."""
    methods = [method for method in class_node.get("methods", [])
               if not method.get("is_macro_generated", False)]
    if not methods:
        return None
    return max(
        methods,
        key=lambda m: (m.get("cyclomatic_complexity", 0), m.get("loc", 0)),
    )


def _build_snippet(
    ast_data: dict,
    fqn: str,
    max_lines: int = 30,
) -> tuple[str, str | None]:
    """fqn 에 해당하는 클래스에서 가장 복잡한 메서드 본문을 max_lines 까지 추출.

    Returns
    -------
    (snippet, method_name) — 실패 시 ("", None).

    원본 소스가 가용한 경우(file.path 가 실재 파일이면) 라인 단위로 잘라낸다.
    스니펫은 전체 함수의 처음 max_lines 줄 + 말미 "... (truncated)" 표시.
    plan §10.6 의 "원본 코드 전체 전송 금지" 원칙에 부합한다.
    """
    target_class = None
    target_file = None
    for f in ast_data.get("files", []):
        for c in f.get("classes", []):
            if c.get("fully_qualified_name") == fqn:
                target_class = c
                target_file = f
                break
        if target_class is not None:
            break
    if target_class is None or target_file is None:
        return "", None

    method = _select_top_method(target_class)
    if method is None:
        return "", None

    src_path = Path(target_file.get("path", ""))
    if not src_path.is_file():
        return "", method.get("name")

    start = max(1, int(method.get("start_line", 1)))
    end = int(method.get("end_line", start))
    end_capped = min(end, start + max_lines - 1)
    try:
        with open(src_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return "", method.get("name")
    snippet_lines = lines[start - 1: end_capped]
    snippet = "".join(snippet_lines).rstrip()
    if end_capped < end:
        snippet += f"\n... (truncated; full method spans lines {start}-{end})"
    return snippet, method.get("name")


# ---------------------------------------------------------------------------
# Prompt 조립
# ---------------------------------------------------------------------------


def _build_user_prompt(
    hotspot: dict,
    snippet: str,
    snippet_method: str | None,
    in_neighbors: list[str] | None = None,
    out_neighbors: list[str] | None = None,
) -> str:
    raw = hotspot.get("raw", {})
    lines: list[str] = []
    lines.append("# Hotspot 정보")
    lines.append(f"- fully_qualified_name: `{hotspot.get('fqn')}`")
    lines.append(f"- file_path: `{hotspot.get('file_path')}`")
    lines.append(f"- kind: {hotspot.get('kind')}")
    lines.append(f"- grade: **{hotspot.get('grade')}** ({hotspot.get('si')} / 100)")
    lines.append(f"- 클래스 LOC: {hotspot.get('loc', '?')}")
    lines.append("")
    lines.append("## raw 메트릭")
    lines.append(f"- CC (top-10% mean): {raw.get('cc')}")
    lines.append(f"- Coupling (fan-in + fan-out): {int(raw.get('coupling', 0))}")
    lines.append(f"- DependencyCycle (SCC size, 0=non-member): {int(raw.get('dependency_cycle', 0))}")
    lines.append(f"- GlobalState (static + singleton accesses): {int(raw.get('global_state', 0))}")
    lines.append(f"- GameLoopCentrality (1=entry point, 0=unreachable): {raw.get('game_loop_centrality')}")
    if hotspot.get("top_reasons"):
        lines.append(f"- top_reasons: {', '.join(hotspot['top_reasons'])}")
    lines.append("")

    # 의존성 그래프 컨텍스트 — 모델이 "의존성 그래프 미시각화" 우려를 일부 해소할 수
    # 있도록 직접 in/out 이웃 FQN 을 prompt 에 포함시킨다.
    if in_neighbors is not None or out_neighbors is not None:
        lines.append("## 의존성 그래프 (클래스 단위 in/out 이웃)")
        in_n = in_neighbors or []
        out_n = out_neighbors or []
        if in_n:
            shown = in_n[:10]
            extra = f" (외 {len(in_n) - 10} 개 더)" if len(in_n) > 10 else ""
            lines.append(f"- **이 클래스를 참조하는 클래스** ({len(in_n)}개): "
                         + ", ".join(f"`{n}`" for n in shown) + extra)
        else:
            lines.append("- 이 클래스를 참조하는 클래스: 없음 (또는 매핑 안된 외부)")
        if out_n:
            shown = out_n[:10]
            extra = f" (외 {len(out_n) - 10} 개 더)" if len(out_n) > 10 else ""
            lines.append(f"- **이 클래스가 참조하는 클래스** ({len(out_n)}개): "
                         + ", ".join(f"`{n}`" for n in shown) + extra)
        else:
            lines.append("- 이 클래스가 참조하는 클래스: 없음 (또는 매핑 안된 외부)")
        lines.append("")

    if snippet:
        method_label = f"`{snippet_method}`" if snippet_method else "(메서드)"
        lines.append(f"## 가장 복잡한 메서드 {method_label} (일부)")
        lines.append("```")
        lines.append(snippet)
        lines.append("```")
    else:
        lines.append("(코드 스니펫 가용하지 않음 — 지표만으로 판단)")
    lines.append("")
    lines.append("위 정보(지표 + 의존성 이웃 + 코드 스니펫)를 모두 활용해 JSON schema 에 맞춰 응답하라.")
    return "\n".join(lines)


def _load_metrics_neighbors(metrics_path: Path) -> dict[str, tuple[list[str], list[str]]]:
    """metrics.json 에서 fqn → (in_neighbors, out_neighbors) 매핑 추출.

    metrics-0.2 이상 스키마에서 동작. 0.1 이라면 빈 dict 반환.
    """
    try:
        with open(metrics_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError:
        return {}
    out: dict[str, tuple[list[str], list[str]]] = {}
    for c in data.get("classes", []):
        in_n = c.get("in_neighbors")
        out_n = c.get("out_neighbors")
        if in_n is None and out_n is None:
            continue
        out[c["fqn"]] = (in_n or [], out_n or [])
    return out


# ---------------------------------------------------------------------------
# 핵심 클래스
# ---------------------------------------------------------------------------


def _load_dotenv(path: Path | None = None) -> None:
    """프로젝트 루트의 .env 를 ``os.environ`` 으로 머지한다 (이미 설정된 값은 보존).

    python-dotenv 의존성 없이 간단히 처리. 형식: ``KEY=value`` 또는 ``KEY="value"``.
    """
    if path is None:
        # advisor.py 기준으로 repo root 추정 (game_si/ 의 부모)
        repo_root = Path(__file__).resolve().parent.parent
        path = repo_root / ".env"
    if not path.is_file():
        return
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            # 이미 truthy 한 값으로 설정된 환경변수는 보존. 빈 문자열이거나
            # 미설정 상태면 .env 의 값으로 덮어쓴다.
            if key and not os.environ.get(key):
                os.environ[key] = value
    except OSError:
        pass


class Advisor:
    """Anthropic Claude Haiku 를 호출해 hotspot 조언을 받는다."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = MODEL_DEFAULT,
        max_tokens: int = MAX_TOKENS_DEFAULT,
    ) -> None:
        _load_dotenv()
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.\n"
                "다음 중 한 가지 방법으로 설정하세요:\n"
                "  1) 프로젝트 루트에 `.env` 파일을 만들고: ANTHROPIC_API_KEY=sk-ant-...\n"
                "     (.env 는 .gitignore 에 의해 추적 제외됨)\n"
                "  2) PowerShell 임시: $env:ANTHROPIC_API_KEY = '<key>'\n"
                "  3) PowerShell 영구: [Environment]::SetEnvironmentVariable('ANTHROPIC_API_KEY', '<key>', 'User')"
            )
        self.client = anthropic.Anthropic(api_key=key, max_retries=MAX_RETRIES)
        self.model = model
        self.max_tokens = max_tokens

    def advise_one(
        self,
        hotspot: dict,
        snippet: str,
        snippet_method: str | None,
        in_neighbors: list[str] | None = None,
        out_neighbors: list[str] | None = None,
    ) -> AdvisorRow:
        user_text = _build_user_prompt(
            hotspot, snippet, snippet_method,
            in_neighbors=in_neighbors, out_neighbors=out_neighbors,
        )
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_text}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": _OUTPUT_SCHEMA,
                }
            },
        )
        text = next(b.text for b in response.content if b.type == "text")
        advice = json.loads(text)
        usage = response.usage
        return AdvisorRow(
            fqn=hotspot["fqn"],
            file_path=hotspot["file_path"],
            grade=hotspot["grade"],
            si=float(hotspot["si"]),
            raw=hotspot.get("raw", {}),
            top_reasons=list(hotspot.get("top_reasons", [])),
            snippet_method=snippet_method,
            advice=advice,
            usage={
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
                "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
            },
            response_id=response.id,
        )

    def advise_top_n(
        self,
        scoring: dict,
        ast_data: dict | None,
        project: str,
        top_n: int = 5,
        progress: bool = True,
        neighbors_by_fqn: dict[str, tuple[list[str], list[str]]] | None = None,
    ) -> AdvisorResult:
        hotspots = sorted(
            scoring.get("class_scores", []),
            key=lambda c: -float(c.get("si", 0.0)),
        )[:top_n]
        if not hotspots:
            raise ValueError("scoring.json 에 class_scores 가 비어 있다.")

        rows: list[AdvisorRow] = []
        notes: list[str] = []
        for idx, hotspot in enumerate(hotspots, 1):
            snippet, method_name = ("", None)
            if ast_data is not None:
                snippet, method_name = _build_snippet(ast_data, hotspot["fqn"])
            if not snippet:
                notes.append(
                    f"hotspot #{idx} ({hotspot['fqn']}): 코드 스니펫 가용하지 않음 — 지표만으로 답변."
                )
            if progress:
                print(
                    f"[advise] {idx}/{len(hotspots)} {hotspot['grade']} G-SI={hotspot['si']:>6.2f}  {hotspot['fqn']}",
                    flush=True,
                )
            in_n, out_n = (None, None)
            if neighbors_by_fqn and hotspot["fqn"] in neighbors_by_fqn:
                in_n, out_n = neighbors_by_fqn[hotspot["fqn"]]
            row = self.advise_one(hotspot, snippet, method_name, in_neighbors=in_n, out_neighbors=out_n)
            rows.append(row)

        total = {
            "input_tokens": sum(r.usage["input_tokens"] for r in rows),
            "output_tokens": sum(r.usage["output_tokens"] for r in rows),
            "cache_creation_input_tokens": sum(
                r.usage["cache_creation_input_tokens"] for r in rows
            ),
            "cache_read_input_tokens": sum(
                r.usage["cache_read_input_tokens"] for r in rows
            ),
        }
        cost = _estimate_cost(total)
        return AdvisorResult(
            project=project,
            model=self.model,
            rows=rows,
            total_usage=total,
            estimated_cost_usd=cost,
            notes=notes,
        )


# ---------------------------------------------------------------------------
# 직렬화 / 요약
# ---------------------------------------------------------------------------


def to_dict(r: AdvisorResult) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "project": r.project,
        "model": r.model,
        "total_usage": r.total_usage,
        "estimated_cost_usd": round(r.estimated_cost_usd, 6),
        "rows": [asdict(row) for row in r.rows],
        "notes": r.notes,
    }


def format_markdown(r: AdvisorResult) -> str:
    """사람이 보기 좋은 마크다운 요약."""
    out: list[str] = []
    out.append(f"# {r.project} — LLM 리팩토링 가이드 (Phase C)\n")
    out.append(f"- 모델: `{r.model}`")
    cache_read = r.total_usage.get("cache_read_input_tokens", 0)
    cache_total = cache_read + r.total_usage.get("cache_creation_input_tokens", 0)
    hit_rate = (cache_read / cache_total * 100.0) if cache_total else 0.0
    out.append(
        f"- 토큰 사용: input={r.total_usage['input_tokens']:,} "
        f"output={r.total_usage['output_tokens']:,} "
        f"cache_write={r.total_usage['cache_creation_input_tokens']:,} "
        f"cache_read={r.total_usage['cache_read_input_tokens']:,} "
        f"(cache hit ≈ {hit_rate:.1f}%)"
    )
    out.append(f"- 예상 비용: **${r.estimated_cost_usd:.4f}** USD\n")
    for idx, row in enumerate(r.rows, 1):
        out.append(f"## {idx}. [{row.grade}] G-SI {row.si:.1f} — `{row.fqn}`")
        out.append(f"`{row.file_path}` · CC={row.raw.get('cc')}  CP={int(row.raw.get('coupling', 0))}  "
                   f"GS={int(row.raw.get('global_state', 0))}  GLC={row.raw.get('game_loop_centrality')}")
        adv = row.advice
        out.append("\n**위험 원인**")
        for r_ in adv.get("risk_reasons", []):
            out.append(f"- {r_}")
        out.append("\n**리팩토링 제안**")
        for s in adv.get("refactoring_suggestions", []):
            out.append(f"- {s}")
        out.append("\n**테스트 우선순위**")
        for t in adv.get("test_priorities", []):
            out.append(f"- {t}")
        if adv.get("uncertainty_notes"):
            out.append(f"\n_불확실성: {adv['uncertainty_notes']}_")
        out.append("")
    if r.notes:
        out.append("### 비고")
        for n in r.notes:
            out.append(f"- {n}")
    return "\n".join(out)
