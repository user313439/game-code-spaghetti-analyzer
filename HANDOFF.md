# HANDOFF — 지금 상태 (150줄 이하, 일이 끝날 때마다 덮어쓴다)

마지막 갱신: 2026-10-26 저녁 / 작성: Claude Opus 5.5

## 목표와 현재 단계

- **최종 목표:** 졸업작품 'G-SI 게임 코드 스파게티 분석기'를 완성해 제출한다. 제출물은 소스 ZIP, 최종보고서(학교 양식), 교내 발표 PPT이고, 제출 뒤 시연 영상과 포스터를 만든다.
- **지금 단계:** 코드 마무리. 10/25~26 변경을 커밋 `d9e90aa`로 main에 fast-forward 병합하고 push했다(origin/main과 같음). 전체 테스트 600 passed, 4 skipped.
  - 메인 폴더의 중복 변경은 정리했다(커밋 안 된 건 `시연_리허설_순서표.md`·`최종 프롬프트.txt`뿐, 의도적으로 제외).
  - 보고서는 코드를 동결한 뒤 최종판 한 번만 만든다(사용자 결정).
- **기준 커밋:** `d9e90aa`(origin/main과 같음).

## 이번에 한 일 (10/26 저녁) — 새 코드로 실제 AI 재검증

**실측 (OpenTyrian 작업 `e1ba503f…`, 5개 파일, '한 번에 깊게', Claude Code `sonnet`)**
- 5개 파일 모두 통과, **7분 48초**. AI 호출 13번(파일 5 + 이어서 정리 8), 입력 약 160만(캐시 생성 125만·캐시 읽기 35만)·출력 약 30만 토큰(`message.id` 중복 제거).
- 5시간 한도 **10% → 46%**(+36%p, 이 대화 몫 약간 포함). Pro에서 한 번 돌리면 한도의 1/3 이상을 쓴다 → 시연에서는 미리 만든 변경안을 쓰는 편이 안전.
- 이어서 정리: mainint·opentyr 3단계 모두 반영, game_menu·tyrian2는 3단계가 거절돼 2단계까지, video_scale_hqNx는 1단계(아래 측정 한계).
- 복잡도(재분석, Clang): JE_itemScreen 371→178(−52%), JE_playerMovement 274→119(−57%), JE_playerCollide 80→24, setupMenu 122→63, JE_main 375→261, JE_eventSystem 255→207, JE_menuFunction 98→86. 새 보조 함수 52개, 바뀐 함수 전체 합은 2,021→2,064(+2%, 옮긴 만큼 그대로).
- 적용(8단계) 정상: 원본 보존·변경안 일치·52개 파일 재분석 구문 오류 0. 결과 화면(9단계) 정상. 2라운드로 기록됨(`revisions/0393bc74…`).
- **컴파일:** 바뀐 5개 파일 libclang(작업 폴더 `compile_commands.json` 플래그) 오류 0·경고 0, 일부러 넣은 오류는 잡힘.
- **Codex 동작 검토:** 5개 모두 동작 변경 없음, 이대로 적용 가능, **9/10**. 감점: game_menu 조이스틱 설정에서 같은 테두리를 두 번 그림(화면 결과 같음, 낮음).

**고친 것 (실제 AI 결과에서 나온 검사 오판 3종 + Codex 검토 4건)**
1. 3단계 거절 2건은 모두 **검사 오판**이었다(저장된 답을 같은 검사에 다시 넣어 확인, 고친 뒤 둘 다 통과).
   - 앞 단계 보조 함수의 호출이 새 보조 함수 안으로 옮겨짐 → 대상 함수에서 새 보조 함수를 거쳐 닿으면 허용(`_new_ast_helpers`).
   - `#ifdef / if (a) / #else / if (b) / #endif {`(올바른 C)를 tree-sitter가 오류로 읽음 → 짝이 맞는 `#if…#endif` 줄만 비우고 다시 읽기(`_readable`). `#include`·`#define`은 비우지 않음.
   - 삽입 직전 함수가 앞 단계 보조 함수(측정 범위 없음)라 difflib가 그 닫는 `}`를 삽입에 붙임 → 함수 밖 삽입도 함수 단위로 읽힐 때까지 밀기(`validate_preview_targets`).
2. Codex 커밋 전 검토(5건 중 4건 수정, 테스트 추가):
   - 이어서 정리의 '효과가 작으면 멈춤'이 늘 원본과 비교하던 것 → 직전 단계 대비로(`_continue_deep`).
   - 다시 만들기의 시도 횟수·지난 거절 이유가 늘 초기화되던 것 → 상태를 지우기 전에 읽음.
   - 취소한 뒤 API 400 재시도를 보내던 것 → 재시도 전 취소 확인(`_stop_if_cancelled`, API·주소 연결 둘 다).
   - 연결 방법을 'API 키'로 바꿔도 CLI 별칭 `sonnet`이 남던 것 → 방법별로 모델을 기억·추천(`prescription.js`).
3. 800×600에서 변경안 비교 창이 창보다 커지던 것 → 화면 높이에 맞춤(300~620px).
4. 화면 확인: 범위 확인 단계에서 소개 배너가 숨고 '이 범위 분석하기'가 800×600 첫 화면에 보임.
5. `docs/ai-refactoring-guide.md`에 이어서 정리·모델 안내·실측 반영, RUNBOOK 1줄 추가.
6. (사용자 피드백) 가져오기 화면: ZIP·폴더를 고르면 놓기 칸이 사라지고 '선택 지우기'만 남음(한 번에 소스 하나). 범위 확인의 첫 분석 방식을 '정밀 분석 (Clang · 자동 인식된 빌드 설정)'으로 사실대로 바꾸고 설명·오류 문구·순서표·웹 안내를 맞춤.

**측정 한계(고치지 않음):** video_scale_hqNx는 매크로가 많아 tree-sitter가 `hq4x_32`를 함수로 못 읽어(복잡도 0으로 봄) 이어서 정리를 멈췄다. 안전한 쪽으로 멈추는 것이라 그대로 둠.

## 다음에 할 일 (우선순위 순) — 괄호 안은 추천 노력 수준

1. ~~push·main 병합~~ 10/26 완료.
2. **사용자 직접 리허설 (사용자)** — `시연_리허설_순서표.md` 1~11단계, 게임 빌드·플레이 포함. 피드백을 받으면 고친다(medium). 추가 채점자 리허설은 하지 않기로 함.
3. 커밋 뒤 테스트 XML을 `docs/_verification/<날짜>-final/`에(low).
4. **소스 ZIP (medium)**, 5. **보고서 v11 (high)**, 6. **교내 발표 PPT (high)** — 6차 검토 `docs/_final_report_phase/_work_v10/review_6_v10.md`, v10 34쪽에서 시작. 이번 실측(7분 48초, 5개 통과, Codex 9/10, 컴파일 0)을 반영.
7. **사용자만 할 수 있는 것:** 소감 수정, 지도교수 서명, 포털 제출, 제출 뒤 시연 영상·포스터.

## 열려 있는 문제·결정 대기

- 검사 구멍(기존): tree-sitter가 아예 함수로 못 읽을 만큼 깨진 새 함수는 '새 보조 함수'로 잡히지 않아 이 검사를 빠져나갈 수 있다. 적용 뒤 재분석(Clang)의 구문 오류 수로는 드러난다. 시간이 있으면 '수정본의 구문 오류 노드가 원본보다 늘면 거절'을 검토.
- Codex 지적 1건(낮음)은 AI 결과물의 중복 그리기라 앱 수정 대상 아님.
- Fable(planner)은 이 계정에서 크레딧 부족으로 실패한다. 두 번째 의견은 Codex(`~/Desktop/AI_WORKFLOW/tools/codex.sh review|ask`).

## 참고

- **사용자 규칙:** 설명은 한국어. 결과 판단은 Claude에게 맡기되 우려는 보고. 커밋·push는 요청 시에만. 실제 AI 요청 전 허락(사용량이 Pro 한도와 같이 쓰임). 단계마다 추천 노력 수준·새 세션 여부를 한 줄로.
- **중요 파일:** 서버 `game_si/web/assistant_jobs.py`(`_generate_deep`·`_continue_deep`·`merge_deep_passes`), `assistant_context.py`(`build_deep_prompt`·`measure_functions`·`validate_preview_targets`·`_new_ast_helpers`·`_readable`), `assistant.py`(`DEEP_GUIDANCE`·`call_provider`·`_stop_if_cancelled`), `jobs.py`(`write_json`). 화면 `static/app/prescription.js`(`stepAdvice`·`stepModel`·`connectionPicker`)·`page-refactor.js`·`page-import.js`.
- **리허설 서버:** 8767, 메인 폴더 코드. 서버 쪽 .py를 바꾸면 재시작(8767 프로세스를 끄고 `py -3.10 -m game_si.web --port 8767`을 메인 폴더에서 숨겨 켬, 로그는 `docs/_demo_phase_v3/server.log`). 정적 JS는 새로 고침으로 반영(캐시 때문에 `fetch(...,{cache:'reload'})` 뒤 새로 고침).
- **실측 도구(이번 세션 스크래치, 필요하면 다시 만들 것):** 토큰 집계(`~/.claude/projects/*game-si-advice*/*.jsonl`을 시작 시각 이후만, `message.id` 중복 제거), 거절 답 재검사(`assistant-rejected-*-pass3.json`의 `reply`를 직전 단계 `after`에 `preview_changes`로 적용 → `validate_preview_targets`), libclang 컴파일 검사(`revisions/<id>/compile_commands.json`의 arguments에서 `-c`·`-o` 빼고 `index.parse`).
- **채점자 리허설 요령:** 내장 브라우저는 다른 로컬 포트(8791) 접속을 막아 ZIP 선택을 못 함 → 2단계는 앱 API(`/api/import/files`, 파이썬으로 multipart; Git Bash curl은 한글 경로 파일을 못 읽음)로 가져온 뒤 3단계부터.
- **테스트:** PowerShell에서 `$env:PATH="C:\Program Files\dotnet;"+$env:PATH`, `$env:GAME_SI_TEST_CLANG_LIBRARY="<저장소>\docs\_verification\2026-10-05-cpp-feasibility\clang20\Library\bin\libclang-13.dll"` 뒤 `py -3.10 -m pytest tests -q`(약 2분). 워크트리에서는 `csharp-analyzer`를 먼저 `dotnet build`, `docs/_demo_phase_v2`·`docs/_verification`은 메인으로 연결(junction)해 둠.
- **함정:** `RUNBOOK.md`.
