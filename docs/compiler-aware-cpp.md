# 선택형 컴파일 설정 기반 C/C++ 분석

2026-10-09 추가 화면 수정: 완료 제목에 선택한 분석 대상 기준의 `100%`를 표시하고, 완료 카드에도 접힌 `분석 범위와 한계`를 복원했다. 도움말은 기존 점수·등급·사용법 구성으로 되돌렸으며 완료 상태의 경고 설명은 한계 영역에 보존했다. 부분 Clang의 컴파일 오류 없는 파일 비율은 그대로 유지한다. OpenRCT2 3파일 결과는 게임 전체 평가가 아닌 `Clang 기능 검증용` 표본임을 부제에 명시한다. 기존 본격 OpenRCT2 결과는 별도로 544개 구현 파일을 분석했으며 36개 구문 복구 파일로 부분 분석 상태다. 새 전체 범위 Clang 분석은 이번 화면 수정에 포함하지 않는다. [추가 화면 검수 기록](../reports/verification-dashboard-complete-scope-2026-10-09.json).

2026-10-09 화면 정리: 모든 분석 방식의 상태 카드를 공통 배치로 맞췄다. 항목별 툴팁과 접힌 원인 설명을 추가하고, 프로젝트 이름과 부제를 분리했다. Clang의 오류·경고는 실제 진단 수를 표시하며 기본 분석에서는 `해당 없음`으로 표시한다. 이번 변경은 표시 부분만 갱신하며 기존 분석 JSON·점수·분석 시각을 변경하지 않는다. 실제 로컬 파일 클릭 점검은 브라우저 보안 정책상 여전히 미확인이다. [화면 갱신 검수 기록](../reports/verification-dashboard-status-2026-10-09.json)을 별도로 남긴다.

같은 날 후속 표시 개선: `이번 진단:`은 툴팁의 새 줄로 분리하고, 완료 카드의 중복 설명은 접힌 도움말로 옮겼다. 부분 분석에서 집계가 일치하는 Clang 입력에만 `컴파일 오류 없는 파일 비율`을 표시한다. DOOM 3의 43/69 = 62.3%는 선택한 등록 입력 중 결과를 얻었고 error/fatal이 없던 파일의 비율이다. 경고 파일은 포함하고 추출 실패 파일은 분자에서 제외한다. 정확도·전체 게임 분석률·파일별 정보의 완전성 지표가 아니며, 집계가 없거나 불일치하면 비율을 표시하지 않는다. [후속 화면 검수 기록](../reports/verification-dashboard-coverage-2026-10-09.json)을 별도로 남긴다.

상태: 2026-10-07 구현 및 아래 범위의 로컬 검수 완료. DOOM 3 결과는 부분 분석이며, OpenRCT2 완료 결과는 선택한 3개 입력에 한정한다.

2026-10-08 최종 확인: 독립 요구사항·품질 검토를 통과했고, 선택형 native 라이브러리를 포함한 전체 테스트 257개를 다시 실행해 통과했다(56.36초). 현재 제품 소스·새 결과·기존 47산출물·벤치마크 소스와 리비전이 앞선 실험 기록과 일치한다. [마무리 확인 기록](../reports/verification-clang-final-2026-10-08.json)은 10월 7일의 실험 기록을 수정하지 않고 별도로 남겼다. 승인한 분석기 보완 범위는 완료했으며, 실제 화면 클릭 시연·최종보고서·발표 자료 작성은 다음 단계로 남는다.

## 쉽게 설명하면

기본 분석은 소스에 적힌 문법을 읽는다. 추가한 Clang 방식은 “이 프로젝트가 어떤 헤더와 매크로 정의를 사용하는가”라는 컴파일 문맥을 함께 읽어, 활성화된 함수 본문과 함수 소속·직접 호출의 심볼을 추출한다. 게임 이름에 맞춰 특정 매크로를 지우거나 바꾸는 기능이 아니다. 같은 입력 형식으로 다른 C/C++ 프로젝트에도 사용할 수 있지만, 호환되는 컴파일 설정과 라이브러리를 준비해야 한다.

이 단계의 점수 단위는 **선택한 구현 파일**이다. C++ 클래스가 여러 파일·헤더에 걸쳐 있을 때 클래스 전체를 완전히 집계한 점수는 아니다. 실제 클래스·네임스페이스·함수 심볼은 AST JSON에 보존하고, 화면에서는 파일 단위의 검토 우선순위를 제공한다.

## 기본 방식은 그대로 유지

```powershell
python -m game_si analyze <소스폴더> --lang cpp --out reports/basic-example
```

기본값은 tree-sitter이며 추가 라이브러리 없이 기존처럼 실행된다. 새 방식은 기존 결과와 **다른 출력 폴더**에 저장한다. 기본 분석과 Clang 분석은 활성화된 본문·추출 단위·연결 정보가 다를 수 있으므로 점수 차이를 “품질이 개선됐다” 또는 “정확도가 몇 % 높아졌다”로 해석하지 않는다. 과거 통계·튜닝·시계열 결과와도 자동으로 섞지 않는다.

## 필요한 준비

1. 선택 의존성인 Clang Python 바인딩과, 호환되는 native libclang을 준비한다. 이번 검수 조합은 바인딩 20.1.5 / native Clang 20.1.8이다. Windows DLL 파일명이 `libclang-13.dll`이어도 실제 라이브러리 버전은 별도로 확인한다.
2. 프로젝트의 컴파일 데이터베이스를 준비한다. 첫 버전은 아래처럼 `arguments` 배열이 있는 JSON을 받는다. `command` 문자열만 있는 항목은 지원하지 않는다. 공식 형식에는 두 표현이 모두 있지만, 이 도구는 셸 문자열 해석을 하지 않는 부분집합만 지원한다. [Clang 공식 형식 설명](https://clang.llvm.org/docs/JSONCompilationDatabase.html)
3. `directory`, 소스 파일, include 경로, 매크로 정의, 표준과 타깃을 원본 프로젝트 설정에 맞춰 확인한다. 프로그램이 빌드 설정을 자동으로 생성하거나 누락된 외부 라이브러리를 설치하지는 않는다.

설치 예:

```powershell
pip install -e ".[clang]"
```

이 명령은 Python 바인딩용이다. 호환되는 native 라이브러리와 그 의존 DLL은 별도로 필요하다. 검수용 도구 폴더를 제품 코드에 하드코딩하지 않는다.

데이터베이스 예:

```json
[
  {
    "directory": "C:/example/game",
    "file": "src/Player.cpp",
    "arguments": ["clang++", "-std=c++17", "-Iinclude", "-DGAME_FEATURE=1",
                  "-c", "src/Player.cpp", "-o", "unused.obj"]
  }
]
```

`directory`는 컴파일 문맥의 기준 경로다. 상대 include 경로와 소스 경로는 이를 기준으로 해석한다. 출력·빌드·링크 동작 옵션은 분석에 사용하지 않으며, 입력의 컴파일러 명령을 실행하지 않는다. 셸·래퍼·응답 파일·플러그인과 허용하지 않은 옵션은 명시적으로 거부한다. 출력 경로는 `-o 파일`처럼 분리된 형태만 지원하고 `-o파일`은 거부한다. 따라서 어떤 프로젝트의 빌드 데이터베이스든 수정 없이 모두 지원하는 것은 아니다.

실행 예:

```powershell
python -m game_si analyze C:/example/game/src --lang cpp `
  --cpp-backend clang --compile-commands C:/example/game/compile_commands.json `
  --clang-library C:/tools/clang/libclang.dll --out reports/clang-example
```

제목에는 `--project-name "게임 이름"`, 작은 부제에는 `--project-subtitle "선택한 분석 범위"`를 사용한다. 부제를 생략하면 분석 방식에 맞는 일반 설명을 자동으로 표시한다. 게임 이름에 따른 특별 처리 없이 다른 프로젝트에도 같은 상태 안내와 툴팁이 적용된다. 원인 설명은 지원하는 진단 문구에서 확인한 범주만 요약하며, 모든 오류의 근본 원인을 자동 진단하는 기능은 아니다.

`--clang-timeout`은 파일 하나를 분석하는 제한 시간(초)이다. 기본은 60초이며, 유한한 양수를 지정한다. C 파일도 `--lang c`와 해당 파일의 C 컴파일 설정으로 사용할 수 있다. C# 분석에는 이 옵션을 적용하지 않는다.

## 어디까지 분석하는가

- 입력 범위와 데이터베이스에 동시에 포함된 `.c/.cpp/.cxx/.cc`만 점수 대상이다. 등록되지 않은 구현 파일은 별도 목록으로 남기고, 헤더·SDK 본문은 중복 점수 대상에 넣지 않는다.
- 같은 파일의 구성이 여러 개면 첫 구성을 선택한다. 선택된 항목과 대안 수를 기록하지만 모든 플랫폼·조건부 구성을 분석한 것은 아니다.
- 매크로가 생성한 함수의 심볼·소속·호출 위치를 표시한다. 원본 한 줄짜리 매크로 호출을 완전한 함수 본문으로 AI에 넘기지 않는다.
- CC는 활성화된 본문의 분기 수에 기반한다. 기존 C/C++ 규칙처럼 `default`도 +1하고 range-for는 분기 항목에서 제외한다. 새 방식은 함수 기본 인자와 중첩 lambda 본문을 해당 함수의 CC에 섞지 않는다. Lizard의 기본 규칙과 차이가 있을 수 있다. 조건부 컴파일과 매크로 확장으로 기본 분석의 수치와 달라질 수 있다.
- 직접 호출은 해석된 심볼을 사용한다. 함수 포인터·가상 호출의 실제 런타임 대상, 이벤트·스크립트의 동적 연결을 완전히 추적하지 않는다.
- 파일 관계는 선택된 함수 정의·타입 소속을 선택 파일로 매핑한 근사다. 헤더에 선언된 하나의 타입이 여러 구현 파일에 걸친 경우 연결 범위가 넓어질 수 있다. 완전한 클래스 의존 그래프라는 의미가 아니다.
- 전역·정적 상태 참조는 정적 코드에서 읽은 것이다. 실제 실행 중 공유 상태의 변경·빈도·스레드 안전성을 입증하지 않는다.

## 오류가 나면

| 상태 | 의미 | 종료 코드 |
|---|---|---:|
| 완료 | 선택 범위에서 유효한 정의를 추출했으며 오류/fatal 진단이나 파일 실패가 없음. 경고가 남을 수 있고 정확성 보증은 아님 | 0 |
| 부분 분석 | 컴파일러 오류/fatal, 읽기·프로세스 실패 또는 제한 시간 초과가 있지만 유효한 추출 결과가 있음 | 3 |
| 실패 | 설정·라이브러리 문제, 선택 교집합 없음, 유효한 정의 없음 또는 결과 저장 실패 | 1 |

파일마다 별도 프로세스에서 파싱하므로 한 입력의 네이티브 충돌·시간 초과가 다른 입력의 결과를 지우지 않는다. 라이브러리가 없다고 자동으로 기본 방식으로 바꿔 성공이라고 표시하지 않는다. 프로세스 격리는 운영체제 보안 샌드박스를 의미하지 않는다.

상태와 선택 범위는 `analysis_status.json`, `scoring.json`, HTML에 표시한다. 원시 함수 정보·구성은 `ast.json`에서 확인한다. 컴파일러 오류 입력 수와 기본 분석의 문법 복구 파일 수는 다른 항목이다. 헤더에서 발생한 진단도 해당 입력의 분석 문맥과 연결된다.

실패한 실행 뒤 이전 결과가 남아 있을 수 있다. 실패 안내가 표시된 결과를 최신 성공 결과로 제출하지 않는다. 출력 저장 자체가 막힌 경우 상태 파일도 갱신할 수 없어 콘솔 안내를 확인해야 한다.

## 검수용 실제 사례의 경계

DOOM 3는 원본 `game.vcxproj`에 등록된 gameplay 구현 입력 69개를 사용한다. `_Common.props`, `_Game.props`, `_Debug.props`의 매크로 정의를 반영하고, 현재 Windows SDK를 읽기 위해 C++17 / `i686-pc-windows-msvc`를 지정했다. 이는 현대 Clang을 위한 **분석 설정**이며, 2000년대 MSVC로 게임을 그대로 빌드한 재현 실험은 아니다. 기존 기본 분석의 gameplay 입력은 71개였지만 `EndLevel.cpp`, `gamesys/Callbacks.cpp`는 이 프로젝트 구성에 등록되지 않아 이번 점수에서 제외된다. 호환성 오류를 게임별 예외로 숨기거나 버전 보호 매크로를 해제하지 않는다.

OpenRCT2는 `Guard.cpp`, `Path.cpp`, `String.cpp` 3개의 대표 입력만 사용한다. 원본 CMake의 `NOMINMAX`, `-fno-char8_t`, thirdparty include를 근거로 C++20 / `x86_64-pc-windows-msvc` 분석 문맥을 준비했다. 선택한 core 폴더의 나머지 28개 구현 파일은 데이터베이스에 등록하지 않았다. 이 3개가 처리되어도 core 전체나 OpenRCT2 전체가 지원된다는 뜻은 아니다.

정식 `analyze` 명령으로 각 범위를 두 번 실행한 결과는 다음과 같다. 함수·메서드 수와 LOC는 선택 파일에서 추출한 정의를 집계한 값이며 저장소 전체 크기가 아니다.

| 사례 | 선택 파일 / 점수 단위 | 추출 함수·메서드 | 추출 LOC | 상태 / 종료 코드 | 두 실행 관측 시간 |
|---|---:|---:|---:|---|---|
| DOOM 3 gameplay | 69 / 69 파일 | 4,375 | 71,964 | 부분 분석 / 3 | 205.906초 / 201.281초 |
| OpenRCT2 대표 core 입력 | 3 / 3 파일 | 71 | 954 | 선택한 표본 완료 / 0 | 9.781초 / 9.391초 |

두 실행의 `ast.json`, `metrics.json`, `scoring.json`, `analysis_status.json`은 분석 시각과 소요 시간만 제외하고 일치했다. 위 시간은 현재 컴퓨터에서 관측한 값이며 표준화된 성능 벤치마크는 아니다.

DOOM 3는 작업 프로세스 실패가 0개였지만 26개 입력에서 error/fatal 진단, 69개 입력에서 경고가 나왔다. 총 3,845개의 error/fatal 진단(오류 3,844 + fatal 1)과 경고 1,120개가 있어 **부분 분석**으로 남는다. `TypeInfo.cpp` 분석 문맥에 오류/fatal 3,467개가 집중됐으며, 원본의 `private`/`protected` 키워드 매크로와 현대 MSVC 표준 라이브러리 보호 검사 사이의 충돌·후속 오류가 포함된다. 이벤트 등록에서도 옛 MSVC 관용의 멤버 함수 포인터 변환을 현재 Clang이 거부했다. 헤더 진단과 연쇄 오류를 포함하는 이 수치를 “게임 버그 3,845개”로 해석하지 않는다. OpenRCT2의 선택한 3개 입력에서는 오류·경고·작업 실패가 없었다.

결과는 [DOOM 3 HTML](../reports/doom3-gameplay-clang/index.html), [OpenRCT2 표본 HTML](../reports/openrct2-clang-sample/index.html), [별도 검수 근거 JSON](../reports/verification-clang-integration-2026-10-07.json)으로 분리했다. 실제 브라우저 조작, 게임 빌드·실행, 유료 AI의 새 조언 생성은 이번 검수에 포함하지 않는다. HTML 검수는 내장 JSON, JavaScript 문법과 범위·단위 표시, 도움말의 기본 접힘 상태를 확인하는 정적 검사다.

선택형 native 런타임을 활성화한 전체 테스트는 **257개 통과**했다. 기본 분석 8사례를 현재 코드로 다시 실행해 기존 지표·점수·상태와 일치함을 확인했고, 기존 결과 파일 47개도 해시가 유지됐다. 기본 지표·점수 산식과 C# 분석 소스, 승인된 통합 변경을 제외한 기존 소스, 두 벤치마크의 소스·Git 리비전 보존을 함께 확인했다. 검수 기준 자료를 준비한 날짜는 10월 5일이며, 실게임 실행·검수 기록 생성은 10월 7일, 최종 독립 품질 검토와 전체 테스트 재확인은 10월 8일에 완료했다. 로컬 검증 스크립트의 최초 import 경로 오류와 보완 후 전체 재검증도 실험 근거 JSON에 기록했다.

### 대표 정의와 호출의 원본 대조

| 원본 파일과 행 | 추출한 소속·정의 | 원본에서 확인한 직접 호출 |
|---|---|---|
| `Player.cpp` 4326–4565행 | `idPlayer::UpdateFocus` | 4365행 등의 `ClearFocus()` → `idPlayer::ClearFocus` |
| `script/Script_Interpreter.cpp` 936–1835행 | `idInterpreter::Execute` | 964행 등의 `Error(...)` → `idInterpreter::Error` |
| `Game_local.cpp` 2157–2358행 | `idGameLocal::RunFrame` | 2172행의 `GetLocalPlayer()` → `idGameLocal::GetLocalPlayer` |

DOOM 3의 추출 정의 4,375개 중 매크로가 생성한 정의는 284개다. `physics/Physics_Player.cpp` 34행의 `CLASS_DECLARATION( idPhysics_Actor, idPhysics_Player )`에서는 생성된 `CreateInstance`, `GetType` 정의의 소속이 `idPhysics_Player`이고 매크로 호출 위치가 34행임을 대조했다. 검수 근거에는 심볼 식별자와 호출의 실제 소스 행도 남긴다. 대표 항목의 대조가 모든 함수나 모든 호출의 정확성을 입증하는 것은 아니다.

### 대표 함수의 CC가 달라지는 이유

| 함수 | 기본 분석 | Clang 활성 본문 | Lizard |
|---|---:|---:|---:|
| `idPlayer::UpdateFocus` | 55 | 55 | 55 |
| `idInterpreter::Execute` | 193 | 194 | 192 |
| `idGameLocal::RunFrame` | 37 | 38 | 39 |

원본과 native 분기 노드를 대조했다. `Execute`의 989행과 `RunFrame`의 2168행에서는 활성화된 `assert` 매크로가 내부 `if` 분기로 확장되어 Clang 값이 기본 분석보다 1 높다. `Execute`의 `default` 분기는 본 도구에서는 +1하지만 Lizard에서는 세지 않는다. `RunFrame` 안의 2166·2191행 `#ifdef`는 Lizard가 각각 +1한다. 원본 파일을 바꾸지 않고 메모리에서만 두 지시문을 제외했을 때 Lizard가 39에서 37로 바뀌는 것도 확인했다. 따라서 서로 다른 숫자를 임의로 맞추거나 평균내지 않고, 구성과 계산 규칙을 함께 기록한다.

### 현재 컴퓨터에서 다시 실행하기

프로젝트 루트에서 아래 명령을 실행한다. 준비한 바인딩·DLL·분석 설정은 로컬 검수 폴더에 있으며 Git에는 포함되지 않는다. 다른 컴퓨터에서는 앞의 준비 절차에 따라 라이브러리와 해당 컴퓨터의 SDK 경로를 갖는 데이터베이스를 따로 준비해야 한다. 아래 실행은 게임을 빌드하거나 실행하지 않으며, 별도의 새 결과 폴더를 갱신한다.

```powershell
$env:PYTHONPATH = (Resolve-Path 'docs/_verification/2026-10-05-cpp-feasibility/bindings20').Path
$demoClangLibrary = (Resolve-Path 'docs/_verification/2026-10-05-cpp-feasibility/clang20/Library/bin/libclang-13.dll').Path

py -3.10 -B -m game_si analyze benchmarks/DOOM-3/neo/game --lang cpp `
  --cpp-backend clang `
  --compile-commands docs/_verification/2026-10-05-clang-integration/doom3-analysis-compile-commands.json `
  --clang-library $demoClangLibrary --out reports/doom3-gameplay-clang

py -3.10 -B -m game_si analyze benchmarks/OpenRCT2/src/openrct2/core --lang cpp `
  --cpp-backend clang `
  --compile-commands docs/_verification/2026-10-05-clang-integration/openrct2-sample-analysis-compile-commands.json `
  --project-name "OpenRCT2" --project-subtitle "Clang 기능 검증용 · 선택한 3개 구현 파일" `
  --clang-library $demoClangLibrary --out reports/openrct2-clang-sample
```

종료 코드 3은 유효한 결과가 남은 부분 분석이다. DOOM 3 사례를 재실행할 때 이 상태를 정상 완료로 바꾸어 설명하지 않는다. HTML은 각 결과 폴더의 `index.html`이다. AI 조언을 새로 요청하는 `advise`는 위 명령에 포함하지 않았으며 별도의 유료 API 설정·사용 동의가 필요하다.

## 발표에서 표현할 핵심

“이 도구는 게임 코드를 정적 분석해, 복잡도와 연결 관계 등 다섯 지표로 먼저 검토할 파일이나 클래스를 제시합니다. 기본 구문 분석에 더해 C/C++ 프로젝트의 헤더·매크로 설정을 사용하는 선택형 분석도 추가했습니다. 분석 결과는 절대적인 결함 판정이 아니라 검토 우선순위입니다. 선택적으로 AI가 지표와 소스 일부를 읽고 개선 방향을 제안할 수 있지만, 실제 수정과 검증은 사람이 수행합니다.”

현재 지원 한계를 넘는 자동 수정·전체 엔진 해석·모든 게임 적용은 향후 과제다. 다음 확장은 여러 구성 비교, 헤더 inline·템플릿 집계, 동적 호출 표현, 실제 수정 전후 테스트와 비용·효과 평가 순으로 검토할 수 있다.
