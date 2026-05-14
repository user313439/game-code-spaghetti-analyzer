# AST JSON 스키마 (v0.1)

`csharp-analyzer`가 출력하는 JSON 파일의 형식을 정의한다. 본 스키마는 후속 단계의 Python Metric Engine 입력 형식이며, 모든 단위는 이 문서를 기준으로 직렬화·역직렬화된다.

## 1. 최상위 객체

| 필드 | 타입 | 설명 |
|---|---|---|
| `schema_version` | string | 본 스키마의 버전. 본 문서는 `"0.1"`. |
| `analyzed_at` | string | 분석 수행 시각. ISO-8601 형식 (UTC). |
| `input_path` | string | 분석 대상의 절대 경로. |
| `analyzer_version` | string | csharp-analyzer 빌드 버전. |
| `summary` | object | 분석 요약(파일·클래스·메서드 수, LOC, 경과 시간). |
| `files` | array of `FileNode` | 분석된 각 `.cs` 파일의 결과. |
| `errors` | array of `AnalysisError` | 파싱이 실패한 파일 목록 (정상 시 빈 배열). |

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
| `methods` | array of `MethodNode` | 타입의 직접 멤버 메서드와 생성자. |

## 5. `MethodNode`

| 필드 | 타입 | 설명 |
|---|---|---|
| `name` | string | 메서드 이름. 생성자의 경우 `.ctor`. |
| `signature` | string | 반환 타입과 매개변수를 포함한 시그니처 문자열. |
| `start_line`, `end_line` | integer | 메서드 선언의 시작·종료 라인. |
| `parameter_count` | integer | 매개변수 개수. |
| `return_type` | string | 반환 타입 (생성자는 `void`). |
| `is_static`, `is_async`, `is_override` | boolean | 수정자 여부. |
| `cyclomatic_complexity` | integer | 본 문서 §7 정의에 따른 CC 값. |
| `loc` | integer | 메서드의 라인 수 (선언부터 닫는 중괄호까지). |

## 6. `AnalysisError`

| 필드 | 타입 | 설명 |
|---|---|---|
| `path` | string | 파싱이 실패한 파일 경로. |
| `message` | string | 예외 메시지. |

## 7. Cyclomatic Complexity 정의

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
- (예정) `0.2` — semantic 분석 결과로 호출 그래프 노드 추가.
