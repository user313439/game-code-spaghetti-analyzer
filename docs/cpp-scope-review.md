# C/C++ 추출 범위 보완과 재측정 (2026-10-22)

## 무엇을 고쳤나

C/C++ 기본 분석(tree-sitter)은 파일 맨 바깥에 있는 함수 정의와 전역 변수만 읽었다. 그래서 다음 블록 안에 있는 함수와 변수가 빠졌다.

- `namespace { }` (중첩 namespace 포함)
- `extern "C" { }`
- `template <...>`
- `#if`·`#ifdef`·`#ifndef`·`#elif`·`#else` 분기

이 문제는 최종보고서 v8의 4차 검토에서 드러났다. OpenRCT2는 .cpp 대부분이 최상위 namespace로 감싸져 있어, 544파일 중 328파일의 함수 본문 줄 수(LOC)와 CC가 0으로 잡혔다.

`game_si/cpp_analyzer.py`의 `_file_scope_items`는 이제 위 블록 안도 파일 범위로 읽는다. 클래스 본문과 함수 본문 안으로는 들어가지 않는다. 기본 분석은 전처리기를 실행하지 않으므로 모든 분기를 읽는다. 다만 `#if 0` 분기는 죽은 코드라서 건너뛰고 `#else` 쪽만 읽는다. 분석기 버전은 `cpp-analyzer-0.2`다. 회귀 검사는 `tests/test_cpp_analyzer.py`의 두 검사(`test_functions_inside_namespace_extern_if_and_template`, `test_c_functions_inside_preprocessor_blocks`)다.

C# 분석기와 Clang 정밀 분석은 바뀌지 않았다. 그래서 OpenRA 여섯 사례, DOOM 3 Clang, OpenRCT2 Clang 표본, OpenTyrian 정밀 분석의 결과는 그대로다.

## 고정 실험 재측정

입력 커밋, 파일 집합, bug-fix 집계 기준(종료일 2026-10-03 UTC)은 같다. Chocolate Doom과 OpenRCT2는 `analyze → validate → compare → score-full → timeseries`를 다시 실행했다. 지표 제거와 LOPO는 8사례 전체로 다시 계산했다. 이전 결과는 `reports/archive/pre-cpp-scope-2026-10-22/`에 보관했다.

| 사례 | 함수 | 분석 단위 | LOC가 0인 파일 | G-SI ρ | LOC ρ | CC ρ | top-30 Jaccard |
|---|---:|---:|---:|---:|---:|---:|---:|
| Chocolate Doom (전) | 4,311 | 296 | 33 | 0.5851 | 0.6158 | 0.4676 | 0.3333 |
| Chocolate Doom (후) | 4,544 | 296 | 24 | 0.6011 | 0.6824 | 0.5025 | 0.3333 |
| OpenRCT2 (전) | 5,766 | 636 | 328 | 0.4687 | 0.4062 | 0.3681 | 0.2500 |
| OpenRCT2 (후) | 10,890 | 680 | 12 | 0.4633 | 0.5419 | 0.3119 | 0.2000 |

ρ는 파일 단위 Spearman 상관이다. LOC는 파일 안 함수 본문 줄 수의 합이다(`validate.py`의 `loc_total`). 남은 LOC 0 파일은 대부분 함수 정의가 없는 파일이다(데이터·문자열·아이콘 표, 미리 컴파일된 헤더). 예외는 두 개다. Chocolate Doom `strife/wi_stuff.c`는 파일 전체가 `#if 0` 안에 있다. OpenRCT2 `command_line/RootCommands.cpp`는 매크로 때문에 구문 복구가 일어나 함수가 선언으로 읽혔고, 부분 분석 파일로 표시된다.

이제 네 주요 사례 모두 G-SI가 CC보다 높고 LOC보다 낮다. OpenRCT2에서 G-SI가 LOC보다 높게 나왔던 이전 결과는 추출 누락 때문이었다.

| 지표 제거 조합(세 원본 프로젝트 동일 비중 평균 ρ) | 전 | 후 |
|---|---:|---:|
| 기본 5항목 | 0.5229 | 0.5265 |
| CC 제외 | 0.4371 | 0.4408 |
| Coupling 제외 | 0.4879 | 0.4942 |
| DependencyCycle 제외 | 0.5311 | 0.5491 |
| GlobalState 제외 | 0.4942 | 0.4904 |
| GameLoopCentrality 제외 | 0.5403 | 0.5363 |
| CC+Coupling만 | 0.5262 | 0.5250 |

CC·Coupling·GlobalState를 빼면 평균이 낮아지고, 순환·게임 루프를 빼면 높아지는 구도는 같다. LOPO(후보 2,226개)는 기본 0.5265, tuned hold-out 0.5297, 차이 +0.0032다(전: 0.5229, 0.5269, +0.0040). 기본 가중치를 그대로 쓴다.

Lizard 사례 파일(Chocolate Doom `i_system.c`: G-SI 100·1위, Coupling 156, DependencyCycle 63, GlobalState 22로 평균 이하. `hexen/mn_menu.c`: G-SI 86.49·41위)은 그대로다.

## 규모를 통제한 결과 (`tools/partial_loc.py` → `reports/partial_loc.json`)

| 사례 | 부분 ρ(G-SI \| LOC) [95% 구간] | 부분 ρ(CC \| LOC) | 부분 ρ(G-SI \| 실제 줄 수) | 상위 20% 파일의 bug-fix 비율: G-SI · LOC · CC |
|---|---|---:|---:|---|
| OpenRA.Game | 0.193 [0.057, 0.328] | −0.033 | 0.210 | 55.2% · 54.1% · 45.7% |
| OpenRA.Mods.Common | 0.117 [0.058, 0.173] | 0.045 | 0.102 | 46.0% · 47.7% · 41.9% |
| Chocolate Doom | 0.184 [0.058, 0.309] | −0.092 | 0.433 | 44.3% · 48.7% · 33.4% |
| OpenRCT2 | 0.142 [0.047, 0.240] | −0.274 | 0.119 | 55.6% · 64.9% · 39.7% |

- 같은 파일 집합(validation.json)으로 계산했다. 구간은 파일을 2,000번 다시 뽑은 부트스트랩(seed 20261022)이다.
- 실제 줄 수는 고정 커밋의 `benchmarks/` 체크아웃에서 센 파일의 줄 수다.
- 상위 20% 비율은 순위 경계의 동점 파일을 나누어 센 값이다. 그래서 무작위 20%의 기대값이 정확히 20%다.
- G-SI는 규모를 LOC로 재든 실제 줄 수로 재든, 통제한 뒤에도 네 사례 모두 수정 이력과 양의 관련이 남는다. 상위 20% 비율은 네 사례 모두 CC 순서보다 높고, 세 사례에서는 LOC 순서가 더 높다.

## 웹 입력과 사례의 재측정

보고서에 쓴 C/C++ 웹 입력은 남아 있는 원래 입력으로 다시 분석했다. 명령은 웹이 쓰는 것과 같은 `game_si analyze <입력> --lang <언어>`다. 함수 수는 다음과 같다.

| 입력 | 전 | 후 | 파일 사이 연결 · 가장 큰 순환 고리 |
|---|---:|---:|---|
| Quake 2 (187파일) | 4,434 | 4,489 | 11 · 0 (같음) |
| OpenTTD (566파일) | 10,184 | 10,830 | 7,547 → 7,557 · 176 (같음) |
| SuperTuxKart (858파일) | 7,701 | 13,395 | 7,833 → 8,695 · 371 → 449 |
| Endless Sky (260파일) | 3,727 | 3,946 | 1,994 → 1,995 · 122 (같음) |
| OpenTyrian 기본 분석 (52파일) | 561 | 581 | 333 · 43 (같음) |
| 2048.c | 19 | 19 | — |

- **OpenTyrian 적용 사례:** 원본(해시 대조 105파일 일치)과 수정본의 전체 함수는 581→582다. setupMenu·JE_newEnemy·JE_createNewEventEnemy·find_free_enemy_slot의 CC와 길이, opentyr.c·tyrian2.c의 G-SI 96.15·98.08은 그대로다.
- **Quake 2 적용 사례:** Default_MenuKey는 CC 62→24, 115→78행으로 같다. 엉킴 총량도 99.78로 같다.
