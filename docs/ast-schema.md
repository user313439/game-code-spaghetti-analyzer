# AST JSON 스키마 (v0.2)

`csharp-analyzer`가 출력하는 JSON 파일의 형식을 정의한다. 본 스키마는 후속 단계의 Python Metric Engine 입력 형식이며, 모든 단위는 이 문서를 기준으로 직렬화·역직렬화된다.

## 1. 최상위 객체

| 필드 | 타입 | 설명 |
|---|---|---|
| `schema_version` | string | 본 스키마의 버전. 본 문서는 `"0.2"`. |
| `analyzed_at` | string | 분석 수행 시각. ISO-8601 형식 (UTC). |
| `input_path` | string | 분석 대상의 절대 경로. |
| `analyzer_version` | string | csharp-analyzer 빌드 버전. |
| `summary` | object | 분석 요약(파일·클래스·메서드 수, LOC, 경과 시간). |
| `files` | array of `FileNode` | 분석된 각 `.cs` 파일의 결과. |
| `errors` | array of `AnalysisError` | 파싱이 실패한 파일 목록 (정상 시 빈 배열). |
| `diagnostics` | array (선택) | 문법 오류 또는 파서 복구가 발생한 파일의 진단. 가능한 추출 결과는 `files`에 보존한다. `path`, `kind="syntax"`, `line`(1-based), `message`를 포함한다. 기존 AST에서는 없어도 됨. |

## 2. `summary` 객체

| 필드 | 타입 | 설명 |
|---|---|---|
| `total_files` | integer | 분석된 `.cs` 파일 수. |
| `total_classes` | integer | 클래스/구조체/인터페이스/레코드/열거형 합계. |
| `total_methods` | integer | 메서드 및 생성자 합계. |
| `total_loc` | integer | 비주석·비공백 줄 합계. |
| `elapsed_ms` | integer | 분석 경과 시간(밀리초). |

## 3. `FileNode`

| 필드 | 타입 | 설명 |
|---|---|---|
| `path` | string | 파일의 절대 경로. |
| `relative_path` | string | 입력 루트로부터의 상대 경로. 슬래시는 `/`로 정규화한다. |
| `loc` | integer | 비주석·비공백 줄 수. |
| `classes` | array of `ClassNode` | 파일 내 타입 선언 목록. |
| `has_code` | boolean (C/C++ 선택 필드) | 구문 트리에 주석 이외의 노드가 존재하는지. 빈/주석 입력 판정에 사용하며 LOC 근사값과 구분한다. |

## 4. `ClassNode`

| 필드 | 타입 | 설명 |
|---|---|---|
| `name` | string | 단순 이름(예: `Actor`). |
| `fully_qualified_name` | string | 네임스페이스와 중첩 타입을 포함한 정규 이름. |
| `namespace` | string \| null | 소속 네임스페이스 (없으면 null). |
| `kind` | string | `class`, `struct`, `interface`, `record`, `record struct`, `enum`, `type` 중 하나. |
| `start_line`, `end_line` | integer | 타입 선언의 시작·종료 라인 (1-based). |
| `is_static`, `is_partial`, `is_abstract` | boolean | 수정자(modifier) 여부. |
| `base_types` | array of string | 상속·구현하는 타입 이름 목록 (구문 그대로). |
| `referenced_types` | array of string | 클래스 본문에서 `new T(...)` 형태로 등장한 타입 이름. CBO(Coupling) 계산의 입력. |
| `static_member_accesses` | array of string | `Type.Member` 형태의 정적 멤버 접근 (예: `"GameManager.CurrentPlayer"`). GlobalState 메트릭의 입력. |
| `singleton_accesses` | array of string | `*.Instance`, `*.Current`, `*.Singleton` 등 싱글톤형 접근자 사용 목록. |
| `methods` | array of `MethodNode` | 타입의 직접 멤버 메서드와 생성자. |

## 5. `MethodNode`

| 필드 | 타입 | 설명 |
|---|---|---|
| `name` | string | 메서드 이름. 생성자의 경우 `.ctor`. |
| `signature` | string | 반환 타입과 매개변수를 포함한 시그니처 문자열. |
| `symbol_id` | string 또는 null (선택) | C# Roslyn 원형 메서드의 문서 ID. 오버로드·제네릭 구분에 사용. 기존 AST/C/C++에서는 없어도 됨. |
| `invoked_symbols` | array of string (선택) | C#에서 정확히 해석된 호출 대상 원형 문서 ID. local function은 독립 노드 범위 밖이므로 제외. |
| `start_line`, `end_line` | integer | 메서드 선언의 시작·종료 라인. |
| `parameter_count` | integer | 매개변수 개수. |
| `return_type` | string | 반환 타입 (생성자는 `void`). |
| `is_static`, `is_async`, `is_override` | boolean | 수정자 여부. |
| `cyclomatic_complexity` | integer | 본 문서 §7 정의에 따른 CC 값. |
| `loc` | integer | 메서드의 라인 수 (선언부터 닫는 중괄호까지). |
| `invoked_names` | array of string | 본문에서 호출된 메서드 이름 (syntactic, 정렬된 unique 집합). 예: `"Foo"`, `"obj.Bar"`. GameLoopCentrality reachability의 입력. |
| `is_game_loop_entry` | boolean | 메서드 이름이 게임 루프 진입점 패턴(`Tick`, `Update`, `Render`, `Draw`, `On*`, `*Tick`, `*Frame` 등)에 해당하는지 여부. |

## 6. `AnalysisError`

| 필드 | 타입 | 설명 |
|---|---|---|
| `path` | string | 파싱이 실패한 파일 경로. |
| `message` | string | 예외 메시지. |

## 7. Cyclomatic Complexity 정의

2026-10-05 보완: `errors`에는 읽기·추출 실패 및 폴더 접근 실패가 기록될 수 있다. `diagnostics`는 실패로 제외된 파일과 달리 복구 추출된 구문의 불완전성을 나타낸다. C/C++ 진단은 원본 소스의 결함을 확정하지 않으며 매크로 등 파서가 지원하지 못한 구문도 포함한다.

명령줄 `analyze`는 `analysis_status.json`과 `scoring.json.analysis_status`에 `state`(`complete`, `partial`, `failed`), `language`, `analyzed_files`, `failed_files`(폴더 접근 실패도 포함한 항목 수), `syntax_files`, `errors`, `diagnostics`, `limitations`를 기록한다. `score-full`은 별도 `analysis_status_full.json`과 `scoring_full.json.analysis_status`를 사용한다. 저장/실행 실패 기록에는 `failure_reason`이 추가될 수 있다. 완료는 정적 추출의 상태이지 분석 정확성 보증이 아니다.

지원 소스가 없는 입력은 결과 생성 전에 거부한다. 추출 후 유효 결과가 없으면 진단만 보존하고 점수는 생성하지 않는다. 실행 실패 시 이전 결과를 삭제하지 않으며, 쓸 수 있는 상태/점수 JSON을 실패로 표시하고 기존 대시보드에는 최신 실행 실패 안내를 붙인다. 디스크·권한 문제로 이 기록조차 저장할 수 없으면 콘솔 오류 및 비정상 종료가 기준이다.

CC는 다음 규칙으로 계산한다. 시작값은 1이며 다음 노드를 만날 때마다 1씩 증가한다.

- `if`, `while`, `for`, `foreach`, `do` 문
- `switch` 문의 각 `case` 라벨 (패턴 매칭 case 포함, `default`는 제외)
- `switch` 식의 각 arm
- `catch` 절
- 삼항 연산자 `?:`
- 단락 평가 이항 연산자: `&&`, `||`, `??`

`return`, 단순 대입, 산술 연산, throw는 분기로 보지 않는다.

본 정의는 일반적인 McCabe Cyclomatic Complexity의 변형이며, 메서드 단위로 계산한다. 후속 단계에서는 클래스 단위 CC를 소속 메서드의 평균·최대·상위 10% 평균으로 집계한다.

## 8. 변경 이력

- `0.1` (W1) — 초기 정의. syntactic 분석 기반.
- `0.2` (W2) — 호출 관계(`invoked_names`), 참조 타입(`referenced_types`), 정적 접근(`static_member_accesses`), 싱글톤 접근(`singleton_accesses`), 게임 루프 진입점 플래그(`is_game_loop_entry`)를 추가.
- `0.2` 호환 선택 필드 보완(2026-10-03~04) — C# `symbol_id`, `invoked_symbols` 추가. 타입 FQN에는 원형 제네릭 매개변수를 보존. 심볼 정보가 없는 옛 AST도 보수적 이름 매칭으로 처리. MSBuildWorkspace는 아직 미구현.
- `0.2` 호환 진단 필드 보완(2026-10-05) — `diagnostics` 추가. 정적 분석·Full 실행에서 정상/부분/실패 상태를 구분하며 점수 공식은 유지.
