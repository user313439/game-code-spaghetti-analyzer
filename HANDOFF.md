# HANDOFF — 지금 상태 (150줄 이하, 일이 끝날 때마다 덮어쓴다)

마지막 갱신: 2026-10-29 오후 / 작성: Claude Opus 5.5

## 목표와 현재 단계

- **최종 목표:** 졸업작품 'G-SI 게임 코드 스파게티 분석기'를 완성해 제출한다. 제출물은 소스 ZIP, 최종보고서(학교 양식), 교내 발표 PPT이고, 제출 뒤 시연 영상과 포스터를 만든다.
- **지금 단계:** 코드 마무리 — 사용자 리허설 피드백 반영. 10/29 피드백: ① AI 리팩토링 거절이 잦다(Codex로 여러 게임 시험해 원인 찾고 고치기) ② 결과 화면이 밋밋하다(시연 아이디어, Codex와 의견 교환).
- **커밋 위치:** 워크트리 브랜치 `claude/rehearsal-feedback-analysis-624049`(이 폴더).
  - 10/29 커밋: `a930ad7`(코드·테스트·`tools/deep_probe.py`) + 이 HANDOFF·RUNBOOK 커밋. 그 앞은 `4ebce48`(10/27 피드백 3건).
  - 메인 폴더(`main`, 8767 서버 코드)에는 이 브랜치 코드를 **복사만** 했고 8767 재시작 완료(10/29 오후). main 로컬은 `9110c02`, origin/main은 `2be4f6f`(그 뒤 push 안 함).
  - main에 합칠 때: 메인의 같은 파일을 `git restore`·새 파일(`tools/deep_probe.py`) 삭제 → `git merge --ff-only <브랜치>` → push(사용자 확인 뒤).
  - 커밋하지 않는 것: `시연_리허설_순서표.md`, `최종 프롬프트.txt`, `docs/_*`, `.env`, `.claude/`, `tmp/`, 메인 폴더의 `image-*.png`.
- **테스트:** 635 passed, 4 skipped(10/29).
- 보고서는 코드를 동결한 뒤 최종판 한 번만 만든다(사용자 결정).

## 10/29에 한 일 — AI 리팩토링 거절 원인 시험(Codex만 사용)

**도구:** `tools/deep_probe.py` — 분석된 작업을 스크래치에 복사해 웹과 같은 '한 번에 깊게' 흐름(직접 모드, G-SI 상위 파일)을 돌리고, AI 원본 답·토큰·거절 이유를 남긴다. 원본 작업은 건드리지 않음.
`py -3.10 tools/deep_probe.py --jobs <메인>/.cache/web/jobs --job <id> --out <스크래치> --model gpt-6.1-sol --files 5 --passes 1`

**결과(모두 한 단계, 이어서 정리 없음):**
| 조건 | 결과 |
|---|---|
| OpenTyrian 4개, Luna, 옛 스키마 | 2개만 완료(약 50줄씩), 5번 중 3번 '설명만 하고 edits 빈 배열' → "수정 판단과 실제 변경 파일이 일치하지 않습니다" |
| 같은 4개, Sol, 옛 스키마 | 4개 모두 첫 답 통과, 88~150줄 이동(JE_main 388→337 등), 토큰 21.6만(Luna 32.9만) |
| 같은 4개, Luna, 새 스키마 | 빈 edits 거절은 사라졌지만 2개는 "안전 확인 불가"로 안 고침 → Luna는 이 작업에 부적합 |
| Chocolate Doom 3·OpenRA(C#) 5·OpenRCT2(C++) 5, Sol, 새 스키마 | 13개 중 12개 첫 답 통과. 실패 1개(WindowManager.cpp)는 검사 오판 → 고침 |

**고친 것:**
1. 깊게 정리 응답 스키마 `DEEP_SCHEMA`: edits를 맨 앞에(코드 먼저, 설명은 그 뒤). 지침에 "edits부터, 설명만 하고 비우지 말 것".
2. refactor인데 edits가 비면 거절 이유 "AI가 고친다고 설명했지만 실제 코드 편집(edits)을 보내지 않았습니다"(재시도 때 AI에게도 그대로 전달). 화면 쉬운 문구 추가(`core.js` PLAIN_REASONS).
3. 처방 화면의 Codex 변경안 모델 안내: 예전엔 Luna로 바꾸는 버튼이 떴음(오늘 Luna를 쓰게 된 경로) → gpt-6.1-sol 권장, Luna는 권하지 않는다고 안내(`prescription.js` stepAdvice).
4. **함수 단위 재확인 `_check_by_tree`**: 줄 검사(`_check_by_lines`, difflib)가 거절할 때만 함수 단위로 다시 본다. 함수 밖 코드·기존 주석·함수 순서와 자리(클래스·접근 구역·#if 갈래)는 그대로, 바뀐 함수는 선언 대상뿐이고 머리(반환형·이름·매개변수·한정자)는 그대로, 새 함수는 대상과 같은 자리의 보조 함수. 원문에서 직접 잘라 비교(#if 줄을 비워 읽은 경우 대비). 통과 못 하면 줄 검사의 거절 이유를 그대로 냄.
   - Codex 검수(Sol high)에서 첫 구현의 구멍 5개 지적 → 모두 반영하고 테스트로 고정(`test_whole_functions_refuse_what_the_review_found` 등).
5. 매크로로 이름이 다른 대상(`#define main SDL_main`)을 줄 범위로도 인식(`_new_ast_helpers`). 저장된 실제 거절 opentyr.c(03bd9a9f)가 이제 통과.
6. (기존 결함) C# 보조 메서드는 **자기 클래스의** 바뀐 대상이 불러야 함.
- 저장된 실제 거절 답 재검사: 오판이던 opentyr.c·WindowManager.cpp 2건은 통과, 정당한 거절(mainint.c 대상 하나 미변경 — 지금은 살리기가 처리, video_scale 매크로)은 그대로 거절.

**AI 진단(처방) 비교:** 저장된 처방 4개(Codex 1, Claude 3)는 고른 파일·대상 함수가 사실상 같음. Claude가 수치(CC 375 등)를 더 넣는 정도 → 처방도 Codex로 충분.

**Codex 사용량:** 5시간 창 2% → 54%(Luna·Sol 시험 약 145만 토큰 + 의견·검수). 20:08 초기화. 주간 8%.

## 결과 화면·시연 아이디어 — Claude·Codex(Astra) 두 차례 의견 교환 결론

- 핵심 시연: **같은 작은 기능을 원본과 정리본에 각각 추가**해 수정 위치·고친 함수 크기·빌드·플레이를 나란히 비교. "버그를 고친 게 아니라 다음 변경의 출발점을 분명하게 만들었다". 리팩토링은 동작을 바꾸지 않으므로 '정리했더니 버그가 사라졌다'는 논리는 쓰지 않는다.
- 기능 후보(OpenTyrian): ① 방어구 경고 2단계(1~2 CRITICAL, 3~5 WARNING; tyrian2.c JE_main 경고 블록 ≈1872행, 정리 때 실제로 updateArmorWarning류 보조 함수로 빠짐) ② 음량 숫자·MUTE 표시(game_menu.c JE_itemScreen ≈663행, 예비안) ③ 무적 시간 막대(mainint.c ≈3930행, 후순위).
- 결과 화면 개편 우선순위: ① 맨 위 "N개 파일의 큰 함수 M개를 나눴습니다 · 보조 함수 K개 · 복잡도 늘어난 함수 L개" + 검사/빌드/플레이 상태 ② 원래 함수 → 보조 함수 → "이 기능(예: 방어구 경고)을 고칠 땐 여기부터"(책임·위치·CC·줄 수) ③ 고친 파일만 묶은 전후 비교를 위에, 게임 전체(99.96)는 아래 보조 지표로.
- 버린 것: 위험 등급 막대(고친 네 함수가 정리 뒤에도 CC>50이라 안 움직임), CC를 "최소 시험 횟수"로 번역(부정확 — '분기 복잡도'로), 과거 버전 버그 예측 실험·모델 반복 성공률 벤치마크(남은 기간에 검증 부담 큼).
- **아직 사용자 선택 전**: 화면은 목업 2~3안을 보여 주고 고른 뒤 만든다(키트 규칙).

## 다음에 할 일 (우선순위 순) — 괄호 안은 추천 노력 수준

1. **사용자 결정 2가지:** (a) 시연 흐름 그대로(OpenTyrian 4개, Sol, 이어서 정리 3단계) Codex로 다시 돌려 단계 중 거절 확인 — Codex 5시간 한도 약 25~30% 사용 예상, 20:08 초기화 뒤 권장(medium) (b) 결과 화면 개편 — 목업 2~3안부터(high).
2. 리허설에서 처방 화면 모델이 Luna로 남아 있으면 'gpt-6.1-sol로 바꾸기' 누를 것(사용자).
3. 동일 기능 추가 시연 준비(방어구 경고 2단계): 원본·정리본 각각 구현, 빌드·플레이 비교(high).
4. 사용자 직접 리허설 계속 → push·main 병합(사용자 확인 뒤) → 테스트 XML `docs/_verification/<날짜>-final/` → 소스 ZIP → 보고서 v11(high) → 교내 발표 PPT(high). 6차 검토 `docs/_final_report_phase/_work_v10/review_6_v10.md`, v10 34쪽에서 시작.
5. **사용자만 할 수 있는 것:** 소감 수정, 지도교수 서명, 포털 제출, 제출 뒤 시연 영상·포스터.

## 보고서에 반영할 것 (코드 동결 뒤)

- 분석 범위: C#은 Roslyn으로 완전 분석. C/C++ 기본 분석은 매크로 많은 파일이 '부분 분석'(Chocolate Doom 296개 중 37개, OpenRCT2 679개 중 46개). 정밀 분석(Clang)은 `compile_commands.json` 필요, OpenTyrian은 자동 인식.
- AI 리팩토링: 10/26 Claude Sonnet 실측(5개 파일, 7분 48초, 한도 10→46%), 10/29 Codex 시험(위 표: 4개 게임·3개 언어 17개 파일, Sol 첫 답 통과 16/17), 모델 선택 근거(Luna 부적합), 거절 자동 처리(살리기·1회 재시도), 검사 두 겹(줄 단위 + 함수 단위 재확인).

## 열려 있는 문제

- 이어서 정리(2·3단계)는 10/29 수정 뒤 실제 AI로 아직 안 봄(위 1-a).
- video_scale_hqNx는 매크로 때문에 tree-sitter가 `hq4x_32`를 못 읽어 이어서 정리를 멈춘다(안전한 쪽).
- tree-sitter가 함수로 못 읽을 만큼 깨진 새 함수는 '새 보조 함수'로 잡히지 않는다(재분석 구문 오류 수로 드러남).
- C++ 클래스 안에 넣은 static 보조 멤버는 공개 구역이어도 받아들인다(.cpp 안 클래스라 다른 파일에서 안 보임; RideConstruction·WindowManager가 이 형태).

## 참고

- **사용자 규칙:** 설명은 한국어. 결과 판단은 Claude에게 맡기되 우려는 보고. 커밋·push는 요청 시에만. 실제 AI 요청·한도를 많이 쓰는 작업 전 허락(Codex 한도 포함). 단계마다 추천 노력 수준·새 세션 여부를 한 줄로.
- **리허설 서버:** 8767, 메인 폴더 코드. 재시작은 진행 중인 AI·분석 작업이 없을 때만: `cd "C:/Users/dudwl/Desktop/Projects/졸업작품" && py -3.10 tmp/restart_server.py --restart`. 정적 파일은 `/ui/…`로 서빙, 브라우저 Ctrl+F5.
- **Codex 한도 확인:** 작은 `codex exec`(비-ephemeral) 한 번 뒤 `~/.codex/sessions/<날짜>/*.jsonl`의 `rate_limits`(primary=5시간, secondary=주간). 앱의 Codex 호출은 `--ephemeral`이라 기록이 안 남음.
- **거절 답 재검사:** 실제 거절 답은 작업 폴더의 `assistant-rejected-*.json`. 옛 작업은 `job.json`의 `options.subdir` 기준 경로(예: `OpenTyrian/src`).
- **처음 보는 게임 넣어 보기:** 앱 API `/api/import/files`(파이썬 multipart) → `/api/jobs/<id>/start`. 분석된 확인용 작업: check-chocolate-doom `0b91aa01…`, check-openra-game `0568a73e…`, check-openrct2 `ae845e06…`, OpenTyrian 최신 `5137ba22…`.
- **테스트:** PowerShell에서 `$env:PATH="C:\Program Files\dotnet;"+$env:PATH`, `$env:GAME_SI_TEST_CLANG_LIBRARY="<메인>\docs\_verification\2026-10-05-cpp-feasibility\clang20\Library\bin\libclang-13.dll"` 뒤 `py -3.10 -m pytest tests -q -p no:cacheprovider`(약 2분).
- **함정:** `RUNBOOK.md`(10/29: Luna 빈 edits, difflib 오판 4번째 → 함수 단위 재확인, 매크로 이름, Codex '보안 위험' 오인 거절).
