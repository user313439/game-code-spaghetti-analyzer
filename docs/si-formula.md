# G-SI 공식 상세 (Game Spaghetti Index)

본 문서는 `docs/_planning/plan_final_draft.md` §4 의 G-SI 공식을 구현 시점의 실제 정의·운용 방식으로 옮긴 것이다. 측정 결과 데이터는 `docs/benchmark-manifest.md` 의 §3 ~ §8 을 참조한다.

## 1. 정의

게임 엔진 기반 프로젝트의 C# 및 C/C++ 코드를 정적으로 분석하여, **함수 → 클래스 → 파일 → 모듈** 단위로 산출되는 **0 ~ 100 점**의 위험 지수.

점수는 분석 집합 내부 **percentile rank**로 표현되는 상대 검토 우선순위다. 절대 품질·결함 확률이 아니다. 80 이상은 백분위 구간이며 동점 때문에 실제 클래스 수의 정확한 상위 20%와 다를 수 있다. 최신 보완 결과는 [refinement-review.md](refinement-review.md), 아래 이전 수치 표는 보완 전 검증 기록이다.

## 2. 분석 단위와 집계 규칙

| 단위 | 산출 방식 |
|---|---|
| **메서드/함수** | CC·LOC·게임 루프 관련 신호를 추출. 독립적인 5항목 G-SI는 직접 산출하지 않음 |
| **클래스** | CC 대표값은 메서드 CC의 **상위 10% 평균**. 결합도·순환·전역 상태·루프 신호와 함께 클래스 기준 표준화 후 G-SI 계산 |
| **파일** | 소속 클래스 점수의 (평균, 최대값) 보고. 대표값은 **최대값** |
| **모듈** | 소속 파일 점수의 평균과 최대값 보고. 대표값은 **평균** |

> 메서드 수가 적어 상위 10% 가 1 개 미만이 되는 클래스는 최대값을 대표값으로 사용한다(예: 메서드 수 ≤ 5 인 경우).

## 3. G-SI-Static 공식

본 작품의 **핵심 검증(Phase A)에 사용**하는 정적 분석만 기반의 지표.

```text
raw_static(unit) = 0.30 · Z(CC)
                 + 0.25 · Z(Coupling)
                 + 0.15 · Z(DependencyCycle)
                 + 0.15 · Z(GlobalState)
                 + 0.15 · Z(GameLoopCentrality)

G-SI-Static(class) = percentile_rank(raw_static, within = analyzed case)
```

가중치는 `game_si/si.py` 의 `DEFAULT_WEIGHTS_STATIC` 에 정의되며, `analyze --weights tuned` 옵션으로 `game_si/tune.py` 의 학습 결과를 사용할 수 있다 (§7 참고).

## 4. G-SI-Full 공식 (확장, 보조 지표)

Git 변경 이력 기반 `ChangeRisk` 항목이 추가된 확장 지표. **데이터 누수 방지를 위해 Phase A 의 검증값으로 직접 사용하지 않으며**, 보조 지표로 별도 산출한다.

```text
raw_full(unit) = 0.25 · Z(CC)
               + 0.20 · Z(Coupling)
               + 0.15 · Z(DependencyCycle)
               + 0.15 · Z(GlobalState)
               + 0.15 · Z(GameLoopCentrality)
               + 0.10 · Z(ChangeRisk)

G-SI-Full(class) = percentile_rank(raw_full, within = analyzed case)
```

`python -m game_si score-full <input> --repo <repo> --subdir <subdir> --months 12 --until 2026-10-03 --out <dir>`로 산출한다. 종료일은 UTC로 고정하고 결과 JSON에 기간을 저장한다. 이 예의 시작일은 2025-10-08이다 (12개월을 360일로 근사).

## 5. 각 항목 정의 및 측정 방법

### 5.1 CC (Cyclomatic Complexity)

제어 흐름의 분기 수. 시작값 1, 다음 노드를 만날 때마다 +1.

- `if`, `while`, `for`, `foreach`, `do` 문
- C# `switch`의 각 `case` 라벨 (`default` 제외). C/C++ 파서의 근사 규칙과 언어별 차이는 고려해야 함.
- `switch` 식의 각 arm
- `catch` 절
- 삼항 연산자 `?:`
- 단락 평가 이항 연산자 `&&`, `||`, `??`

`return`, 단순 대입, 산술 연산, `throw` 는 분기로 보지 않는다.

클래스 단위 CC 는 소속 메서드의 평균·최대·상위 10% 평균으로 집계되며, 본 작품은 상위 10% 평균을 대표값으로 사용한다.

### 5.2 Coupling

결합도. 해당 단위가 참조하는 외부 타입 수(fan-out) + 해당 단위를 참조하는 외부 단위 수(fan-in). 클래스 단위에서는 CBO(Coupling Between Objects) 와 동일.

C# 의 경우 Roslyn `SemanticModel` 이 `INamedTypeSymbol` 의 정확한 FQN 을 해석하므로 동명 클래스 다수 케이스도 정확히 매칭된다 (`csharp-analyzer/MethodBodyWalker.cs`). C/C++ 의 경우 tree-sitter 의 `#include` stem + 본문 type identifier 의 simple-name 매칭으로 근사한다 (`game_si/cpp_analyzer.py`).

### 5.3 DependencyCycle

순환 의존성. **본 작품은 W14 후속 개선으로 두 시그널을 결합한다**.

```text
DependencyCycle(class) = cycle_size + cycle_edges,  if class ∈ SCC(size ≥ 2)
                       = 0,                          otherwise
```

- `cycle_size` — 해당 클래스가 속한 SCC 의 크기 (NetworkX strongly_connected_components)
- `cycle_edges` — 해당 클래스가 관여한 SCC 내부 edge 수 (in + out, induced subgraph)

이로써 같은 SCC 안의 hub god-class 와 peripheral 클래스가 차별화된다 (예: 5-node SCC 의 hub `Token` 은 `cycle_edges` 6, peripheral 은 2~4).

### 5.4 GlobalState

전역 상태 의존도. `game_si/metrics.py` 의 `_compute_global_state` 에서 집계.

```text
GlobalState(class) = |static_member_accesses| + |singleton_accesses|
```

- **C#**: mutable static 필드와 static 속성뿐 아니라 static 메서드 접근도 현재 포함한다. 따라서 실제 전역 상태 변경 횟수가 아니라 **정적/싱글톤 접근의 구조 대리 지표**다. 싱글톤형 식별자는 이름 휴리스틱이다. 타입 전체 walker는 중첩 타입의 접근도 부모에 포함할 수 있어 과대 계상 가능성이 있다. C#은 unique 접근 문자열 수이며 C/C++ 반복 접근 횟수와 동일한 측정 단위가 아니다.
- **C/C++**: 파일 최상위 `static` / `extern` / 전역 변수 식별자가 함수 본문에서 사용된 횟수 (중복 허용).

### 5.5 GameLoopCentrality

게임 루프 진입점으로부터 호출 그래프 상 도달 가능성 + 도달 깊이.

```text
GameLoopCentrality(method) = 1 / (1 + depth),  if reachable from entry
                           = 0.0,              otherwise
```

진입점 패턴:

- **C#**: `Tick`, `Update`, `LateUpdate`, `FixedUpdate`, `Render`, `Draw`, `Awake`, `Start`, `MainLoop`, `GameLoop`, `On*`, `*Tick`, `*Frame`
- **C/C++**: `MainLoop`, `D_DoomLoop`, `*Tick`, `*Frame`, `Render`, `Render*`, `*Draw`, `Update`, `*Update`, `On*`

클래스 단위 GameLoopCentrality 는 소속 메서드 중 최댓값.

C#은 Roslyn 문서 심볼 ID로 오버로드·제네릭 원형을 연결한다. local function은 독립 메서드 노드로 추출하지 않으며 동명 클래스 메서드로 연결하지 않는다. 옛 AST는 정확한 전체 호출명을 먼저 확인하고, 수식되지 않은 단순 이름만 유일한 후보일 때 연결한다. 외부·모호한 수식 이름은 임의 연결하지 않는다. 이는 정적 근사이며 런타임 실행 빈도, virtual/delegate/event dispatch를 완전하게 추적하지 않는다.

동명 타입 선언은 소스 파일·위치로 구분해 덮어쓰기를 방지한다. partial 선언을 완전한 하나의 의미 타입으로 병합하지 않으며, 모호한 참조는 보수적으로 제외하므로 결합도를 과소 추정할 수 있다. 위치 기반 식별자는 커밋 간 동일 객체 추적의 한계가 있다.

### 5.6 ChangeRisk (G-SI-Full 전용)

최근 N 개월(기본 12) 동안의 파일 단위 변경 활동.

```text
ChangeRisk(file) = total_changes_in_window · (1 + bugfix_ratio)
```

- `total_changes_in_window` — git log 가 해당 파일을 수정한 commit 수
- `bugfix_ratio` — 그 중 bug-fix 키워드(`fix`, `bug`, `crash`, `regression`, `hotfix`, `patch` 등) 매칭 비율. 사소한 수정(`fix typo`, `fix indent` 등)은 제외.

`game_si/change_risk.py` 에 구현.

## 6. 정규화 — Z-score 와 percentile rank

각 항목 입력값은 단위·스케일이 다르므로 가중합 이전에 표준화한다.

```text
Z(x) = (x − mean) / stdev,  단 stdev=0 이면 1 로 둠

mean, stdev 는 동일 프로젝트 내 모든 분석 단위의 평균과 표준편차
```

가중합 결과를 다시 프로젝트 내 분포의 percentile rank 로 변환:

```text
percentile_rank(x, within = project) = (해당 프로젝트 내에서 x 이하인 단위의 비율) · 100
```

본 정의로 G-SI 는 **0 이상 100 이하** 의 단조 양의 척도이며, 등급 해석이 프로젝트 내부 분포에서의 상대적 위치로 일관된다.

동점은 `≤` 공식상 상단 백분위를 공유한다. 모두 같은 가중합이면 모두 100/E지만 후보를 구분할 정보가 없다. 비어 있지 않은 집합의 최대값은 항상 100이다. `ranking_info`에 순위의 유효성, 고유 가중합 수, 최대 동점 집단 비율 및 해석 경고를 저장한다. 분석 집합이 달라지면 점수도 바뀌므로 diff/CI와 시계열 차이는 절대 품질 변화의 증거가 아니다.

## 7. 가중치 운용 모드 (plan §4.6)

세 가지 모드를 모두 지원한다 — `analyze --weights {default,tuned,custom}`.

### 7.1 default

`game_si/si.py` 의 `DEFAULT_WEIGHTS_STATIC` 에 명시된 plan §4.2 의 고정 값.

| 항목 | cc | coupling | dependency_cycle | global_state | game_loop_centrality |
|---|---:|---:|---:|---:|---:|
| default | 0.30 | 0.25 | 0.15 | 0.15 | 0.15 |

### 7.2 tuned

`game_si/tune.py`는 5차원 가중치 grid (step 0.05, sum=1, 2,226 후보)를 탐색한다. 클래스 전체 기준 Z-score → 가중합 → 백분위(소수 둘째 자리) → 파일 최대값을 사용하여 본 분석과 계산 순서를 맞춘다. 같은 원본 프로젝트의 모듈은 함께 hold-out한다. 목적함수와 최종 평균은 프로젝트별 평균 상관의 동일 가중 평균이다. 세 프로젝트의 사례 연구로, 보편적인 일반화 성능을 입증하지 않는다.

재계산에는 `scoring.json`의 반올림 전 `raw_exact`를 사용한다. 과거 JSON의 `raw`만 있는 경우는 근사 계산으로 표시한다. 최소 5파일 및 기본 상관 계산 가능 조건을 만족하는 원본 프로젝트가 2개 이상이어야 한다. 상수 bug-fix 값 등 제외 사유를 사례별로 기록한다. 후보나 hold-out에서 비교 대상 일부를 버려 평균을 높이지 않으며, 검증 모듈의 상관이 정의되지 않으면 비교 불가 오류로 처리한다.

```bash
python -m game_si tune --case OpenRA.Game=reports/openra-game --case ...
# → reports/tune.json + reports/tune_summary.txt
```

2026-10-03 재검증: 8개 사례 중 Server 제외, 원본 프로젝트 3개. 전체 자료로 선택한 배포용 후보 가중치 (학습 결과이며 fold 가중치와 다름):

| 항목 | cc | coupling | dependency_cycle | global_state | game_loop_centrality |
|---|---:|---:|---:|---:|---:|
| **tuned (본 작품)** | **0.35** | **0.25** | **0.05** | **0.30** | **0.05** |

`analyze --weights tuned` 가 `reports/tune.json` 의 `tuned_weights` 를 자동 로드해 적용한다.

### 7.3 custom

사용자가 지정한 가중치 JSON 파일을 사용한다.

```bash
python -m game_si analyze <input> --weights custom --weights-file my_weights.json
```

JSON 형식:

```json
{
  "cc": 0.35,
  "coupling": 0.25,
  "dependency_cycle": 0.10,
  "global_state": 0.20,
  "game_loop_centrality": 0.10
}
```

합이 1 이 아니어도 내부적으로 정규화된다 (`_normalize_weights`). 알려진 지표 키·유한한 0 이상 숫자·양수 합이어야 한다. 음수, 불리언, null/배열, 비유한 값 및 표현 범위를 넘는 수는 오류로 처리한다.

## 8. 등급표

| 점수 | 등급 | 의미 (프로젝트 내 상대 위치) | 해석 |
|---|---|---|---|
| 0 이상 20 미만 | **A** | 낮은 상대 순위 구간 | 안전함을 보증하지 않음 |
| 20 이상 40 미만 | **B** | 상대 순위 구간 | 절대 품질 판정 아님 |
| 40 이상 60 미만 | **C** | 상대 순위 구간 | 평균적인 품질이라는 뜻이 아님 |
| 60 이상 80 미만 | **D** | 높은 상대 순위 구간 | 실제 소스 점검 후보 |
| 80–100 | **E** | 높은 상대 순위 구간 | 실제 소스 점검 후보, 결함의 증거 아님 |

`game_si/si.py` 의 `_grade(score)` 에서 구현.

## 9. Project Health — 프로젝트 단일 종합 점수

여러 메트릭의 가중 평균으로 보조 구조 요약(0~100)을 산출한다. 상대 백분위 평균과 D/E 비율이 포함되어 공식·동점에 강하게 영향받는다. 별도로 타당성을 검증한 절대 품질 척도가 아니며 프로젝트 간 우열 판정에 사용하지 않는다. 호환성을 위해 수식과 JSON 필드명은 유지한다.

```text
Project Health = 0.45 · avg_si
               + 0.25 · risk_score
               + 0.15 · cycle_score
               + 0.15 · coupling_norm
```

각 항목 정의:

- `avg_si` — 클래스 평균 G-SI (그대로)
- `risk_score` — D/E 등급 클래스 비율 × 100
- `cycle_score` — `min(100, 30 · log2(cycle_count + 1))` (SCC ≥ 2 의 수)
- `coupling_norm` — `min(100, avg_coupling · 10)` (클래스 평균 결합도, 10+ 에서 saturate)

`game_si/si.py` 의 `_compute_project_health` 에서 산출.

## 10. 검증 데이터 — 4 케이스 Phase A 결과 요약

`docs/benchmark-manifest.md` §3 의 4-케이스 종합 표 (파일 단위 Spearman ρ vs bug-fix count):

| 케이스 | 언어 | n | G-SI ρ | LOC ρ | CC ρ |
|---|---|---:|---:|---:|---:|
| OpenRA.Game | C# | 226 | **+0.601** | +0.699 | +0.552 |
| OpenRA.Mods.Common | C# | 1,080 | **+0.536** | +0.613 | +0.527 |
| Chocolate Doom | C | 296 | **+0.585** | +0.616 | +0.468 |
| OpenRCT2 | C++ | 544 | **+0.460** | +0.406 | +0.368 |

과거 bug-fix 커밋 빈도와의 양의 상관이다. p-value는 정규근사이며 JSON의 반올림·수치 정밀도로 0이 출력될 수 있다. 실제 위험의 정답 또는 미래 결함 예측 성능으로 해석하지 않는다.

추가로 2026-10-03 원본 프로젝트 단위 LOPO 평균 ρ (`reports/tune.json`, 계산 방식 tune-0.3):

| | default ρ | tuned ρ | Δ |
|---|---:|---:|---:|
| 3프로젝트 LOPO 평균 | +0.5194 | **+0.5251** | **+0.0057** |

평균 차이는 +0.0057로 작고, 개선의 통계적 유의성은 검정하지 않았다. 기본 가중치를 기본 동작으로 유지한다. 이전 +0.0288은 파일 지표 우선 집계 및 모듈 단위 분리의 과거 결과로 보존하며 새 수치와 동일 실험으로 비교하지 않는다.

## 11. 한계 및 향후 작업

- **C# semantic 분석**: 본 작품은 `CSharpCompilation` + `SemanticModel` 의 간단한 부분을 구현 (`csharp-analyzer/Program.cs`, plan §5.1). `MSBuildWorkspace` + csproj + 외부 dll references 까지 가는 완전한 semantic 분석은 위험도 높음(plan §13) 이유로 의도적 분리 — 향후 작업.
- **C/C++ semantic**: `compile_commands.json` 기반 clang tooling 은 plan §6.4 의 범위 외.
- **GameLoopCentrality 의 약한 시그널**: 8-케이스 tuned 에서 가중치 0.05 로 잡힘. C# 의 semantic 정확도 향상이 일부 회복시키지만, 완전 해결은 동적 호출 dispatch (event handler, delegate) 의 정밀 분석이 필요.
- **표본 수**: 8 케이스 (OpenRA 6 모듈 + Chocolate Doom + OpenRCT2) 는 통계적 일반화에 한계가 있다. 정량 결과는 "정량 신호" 수준으로 보고하며, 더 많은 케이스 추가 시 (Unity 샘플 등) 본 도구의 일반화 검증이 강화될 수 있다.

## 12. 참고

- 4-케이스 분석 결과 메타: `docs/benchmark-manifest.md` §1 ~ §6
- Phase A ~ D 실험 결과: `docs/benchmark-manifest.md` §3 ~ §5
- Phase B (Lizard 비교) + RQ3 정성 증거: `docs/benchmark-manifest.md` §4
- W14 후속 개선 작업 (1-A semantic, 2-A DepCycle, 3-A LLM advisor, 4 C++ namespace, 5-A OpenRA 추가 모듈): `docs/benchmark-manifest.md` §6.5, §8, §10b, §10c
