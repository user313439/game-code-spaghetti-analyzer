# 웹 재설계 진행 상황 (2026-10-20, Claude Code)

설계: `docs/superpowers/specs/2026-10-19-web-redesign-design.md` (끝의 '구현과 다른 점' 포함) · 시안: `docs/superpowers/mockups/2026-10-19-web-redesign/`

## 완료
1. 데이터 계층: `tangle.py`(엉킴 총량), `diagnosis.py`(진단·레버리지·문장·캐시), API `/diagnosis`(기본 = 현재 라운드), `/tangle`
2. 새 화면 `game_si/web/static/app/*` (CSP 준수, 외부 라이브러리·글꼴 없음): 가져오기·기록·예시·진단(진단서↔지도)·리팩토링·결과
3. AI 처방: `prescription.py` + `/prescription` + 패널
4. 리팩토링 확장: `change_type`(functions/declarations), companions(#include/using), creates(선언 전용 헤더), 검사 규칙은 `change_rules.py`
5. 라운드: `rounds.json`, `/rounds`, `/rounds/undo`, `/rounds/{n}/play`, 시연 빌드는 현재 라운드 수정본 전체 반영
6. 정리: 옛 화면·전용 테스트를 `docs/_archive/legacy-web-ui-2026-10-19/`로 이동, 문서 갱신
7. **독립 검토 반영 (10/20)** — 화면·서버 각각 검토 후 수정
   - 화면: 이동 후 늦게 끝난 요청이 새 화면을 덮어쓰지 않게 함, 적용 실패 표시, 빌드 전 플레이 기록 잠금, 게임 감시 중복 제거, 오래된 처방은 '다시 받기'만, 진행 표시를 제자리 갱신(로그·포커스 유지), 비교 화면 `---` 줄 해석, C# 클래스 표 키, 접근성(aria-pressed·라벨·live 영역), 180KB 초과·같은 파일 클래스 선택 차단, 이전 라운드 변경안 안내
   - 서버: 함께 수정 파일 판정 버그(변수 덮어쓰기), 선언 정리 '옮기기만' 허용(같은 이름 함수 모두 비교, 새 매크로·초기값 거절), 새 헤더의 기존 include 이름 가리기 차단, 주석 속 include 무시, 제어 문자·삼중 문자 거절, `using` 별칭 거절, 과거 작업의 수정본을 1라운드로 저장, 두 잠금 교착 제거(한 잠금 공유), 되돌린 라운드의 변경안 적용 차단·되돌린 라운드 기록 보존(`discarded`), 존댓말 검사 문장 단위로, 고리 '줄어듦' 계산에서 자기 자신 제외, 처방 입력에 이전 라운드·엉킴 총량·고리 목록 추가, JSON 아닌 응답 1회 재요청, 시연 인식 실패를 캐시하지 않음, 수정본 지문(`manifest.json`) 기록·빌드 전 확인, Chocolate Doom 시연도 전체 수정본 비교, 분석 미완료는 모두 409
   - 회귀 테스트: `tests/test_review_fixes.py` (34개)
8. **전체 프로젝트 점검 (AI 호출 없음)**: 분석 결과 11개 + OpenTyrian에서 진단·총량·처방 입력·처방 검증/효과·함수 수정 검사·선언 이동 검사·함께 수정 후보를 실행. 부분 분석 파일(Chocolate Doom m_misc.c, Doom 3, OpenRCT2 Context.cpp, OpenTyrian tyrian2.c) 포함 모두 통과. 스크립트: scratchpad `dryrun_all.py`, `e2e_partial.py`
9. **취소 버튼 (10/20)**: 변경안·처방 생성 중 '요청 취소'. 그 요청의 AI 프로그램만 종료, 늦은 작업은 덮어쓰지 않음, 취소 뒤 고른 파일 유지. 테스트 `tests/test_cancel.py`
10. **처음 분석하는 게임 점검**: MonoGame Platformer2D(C#)로 업로드→분석→진단→처방 입력→변경안→적용·재분석까지 브라우저와 같은 API로 통과(가짜 AI 응답). 스크립트: scratchpad `e2e_new_game.py`
11. **AI 연결**: 데스크톱 앱에 포함된 Claude Code 자동 탐색, 로그인 여부·로그인 명령 표시(`auth status`, AI 요청 없음), 내 계정 방식에서도 모델 지정. 테스트 `tests/test_ai_connection.py`
12. **측정 기록**: OpenTyrian Clang 분석 = 전체 분석(52파일, 컴파일 오류 0, 63초). 기본 분석과 연결 구조가 다름(순환 고리 43 → 2파일, 연결 333 → 224). Quake 2(GitHub 가져오기) 기본 분석 = 부분(187파일 중 33), 연결 11개(헤더 이름이 .c와 달라 연결 추정이 약함). 작업은 scratchpad `realcheck/jobs`에 보관
13. **첫 실제 AI 점검 (Quake 2, Claude Code·Opus)**: 처방 26초(구체적·정확). 변경안 첫 시도는 짝 헤더 설명 누락으로 거절 → 고침(AI에 `review_paths` 명시, 바뀌지 않은 문맥 파일 설명은 '유지'로 채움, 바뀐 파일은 설명 필수). 중복 정의 제거는 같은 줄이 남아 있으면 허용. AI 응답 제한 240→600초. 거절된 응답은 작업 폴더 `assistant-rejected-reply.json`에 보관. 재시도 성공(약 3분): Default_MenuKey CC 62→24, 엉킴 총량 99.78. 보고서용 초안 `docs/_final_report_phase/추가_전체분석_한계와_업계비교_초안.md`
14. **GitHub 가져오기 개선**: 100MB 제한은 우리 쪽 제한이었음 → tar.gz를 받으며 바로 풀어 소스만 저장(묶음 2 GiB·15분, 소스 1 GiB·2만 개). 테스트 `tests/test_github_stream.py`
15. **최신 게임 시험(AI 없음)**: OpenTTD(566 cpp, 부분 126, 24초), osu!(4,890 cs, 6,927 클래스, 전체, 69초), SuperTuxKart(858, 부분 190, 동봉 라이브러리가 상위 차지 → 범위 선택 필요, 32초), Endless Sky(391MB 저장소, 가져오기 17초, 부분 45, 26초)
16. **B: 시연 게임 정밀 분석(Clang)**: `clang_presets.py`(원본과 같은 소스일 때만 Visual Studio 프로젝트와 같은 옵션으로 compile_commands 생성), 범위 화면 '분석 방식' 선택(기본값 정밀), `clang-auto`, 수정본 Clang 재분석(경로 이동), 진단 '정밀 분석' 표시, 지도·칩 짧은 이름. API 끝까지 확인: 분석 40초·오류 0, 재분석 41초. 테스트 `tests/test_clang_presets.py`, Clang 테스트 80개 포함 554개 통과(`GAME_SI_TEST_CLANG_LIBRARY` 지정 시)

17. **커밋·push (10/21, 사용자 요청)**: c64d31c(웹 재설계 코드·테스트), 23ddbf2(사용 설명·검증 문서·이 설계 문서), 706dcdc(change_rules.py의 유니코드 줄 구분 문자를 이스케이프로). origin/main과 같음. 제외: 다른 superpowers 내부 문서·시안·이 진행 기록, `최종 프롬프트.txt`, `.claude/`, `docs/_*`(보고서·검증 원본), HWP·PDF·.env
18. **최종보고서 v4 (10/21, 로컬 전용)**: `docs/_final_report_phase/최종보고서_안영진_v4.docx`·`_v4_검토용.pdf`, 38쪽(본문 32쪽). 웹 4단계 흐름·변경안 규칙(표 9)·OpenTyrian 기본/정밀 비교(표 18)·Quake 2 실제 AI·최신 게임 5개·554 테스트 반영. Clang은 한계로, 상용 도구는 참고 한 문장[20][21]으로만, 시연은 자세히 쓰지 않음. 자동 검사 96/96, 양식 재검수는 `학교양식_요구사항_검수.md` 5절. 만드는 스크립트 `_work_v4/build_v4.py`, 검사 `_work_v4/verify_v4.py`, 근거 `docs/_verification/2026-10-21-final/`

19. **최종보고서 v5 (10/21, 로컬 전용, 현재 제출 후보)**: 사용자 요청으로 장별 쪽수를 양식과 똑같이 맞춤 — 서론 6·관련연구 7·제안 7·결과 7·결론 및 소감 2·참고문헌 1 = 30쪽(+표지·요약·부록 2쪽 = 34쪽, 쪽번호 1~33). 표 4개·그림 6 제거(핵심 수치는 본문에 유지), 부록 코드 6→4개(원천코드 부록은 양식 필수), 소감·후속 과제를 이어지는 문장으로 다시 씀. 자동 검사 109/109, 양식 재검수는 `학교양식_요구사항_검수.md` 6절. 스크립트 `_work_v5/build_v5.py`·`verify_v5.py`

20. **최종보고서 v6·v7 (10/21, 로컬)**: 지도교수 관점 서브 에이전트 채점 80 → 87(v6) → 88(v7). 반영 기록 `_work_v6/review_1.md`, `_work_v7/review_2.md`, 3차 검토 전문 `_work_v7/review_3_v7.md`(도움 안 되는 문장 70곳, LOC 통제 부분 상관 제안 등 20개 수정 목록)
21. **웹 개선 (10/22, 커밋 6f616f7, push 완료)**: 아무 AI나 연결(‘다른 AI’ = OpenAI 호환 주소, 모델 목록 확인, 설치 안 된 프로그램은 API 키로 자동 전환, ‘설치 필요’ 표시 삭제), 처방 파일 클릭 → 진단서 카드/지도 노드로 이동, 작업 막대(코드 이름 + 4단계)와 보기 전환 위치 정리, 변경안의 ‘그대로 둔 파일’ 묶음과 이유 표시, 결과 카드 비교 기준 안내. 전체 테스트 562개 통과(Clang 포함)
22. **Quake 2 수정본 확인 (10/22)**: 원본·수정본 quake2.exe 모두 MSVC 2022 x86으로 C 48개 오류 0 빌드, Default_MenuKey 5,120가지 입력(메뉴 상태 5 × 키 1,024) 동작 동일. 기록·스크립트·입력 `docs/_verification/2026-10-22-quake2`(build.py → menukey_check.py 순서로 재실행 가능)
23. **엉킴 총량 실험 (10/22, 실제 Claude Code)**: Clang 정밀 3라운드 100 → 99.89(정밀 분석은 실제 호출로 연결을 세어 선언 이동으로는 고리·연결이 줄지 않음), 기본 분석 공용 헤더 집중 1라운드 98.42. 기록 `docs/_verification/2026-10-22-tangle`
24. **효과 지표 예비 계산 (10/22)**: `docs/_verification/2026-10-22-effect/effect_check.py` — 상위 20% 파일이 과거 bug-fix 흔적의 44~55%(무작위 20%의 2.2~2.7배, LOC 순서와 비슷), LOC 통제 부분 상관 G-SI 0.12~0.26(4/4 양수, CC는 0 근처·음수). 주의: 이 스크립트는 LOC 0 파일을 빼서 n이 validation.json과 조금 다름 — 보고서용은 validate.py와 같은 파일 집합으로 다시 계산
25. **로컬 웹 실행**: `.claude/launch.json`의 `game-si-web-chrome`(포트 8766, `tmp/serve_web_8766.py`, 64비트 .NET을 PATH 앞에 둠). 크롬에서 http://127.0.0.1:8766
26. **효과 지표 결정과 최종보고서 v8 (10/22, 로컬)**: 사용자가 추천안을 골랐다 — 엉킴 총량은 보조, ① 찾는 힘 ② 고친 곳의 변화 ③ AI 변경 안전 구조를 앞세움. 근거 `reports/partial_loc.json`(스크립트 `docs/_verification/2026-10-22-effect/partial_loc.py`, validate.py와 같은 파일 집합: 부분 상관 G-SI 0.193·0.117·0.236·0.288, CC −0.193~0.045, 상위 20% 44~55%·무작위의 2.2~2.8배, LOC 47~54%), 테스트 562개 XML `docs/_verification/2026-10-22-final/tests-6f616f7.xml`. 보고서 `docs/_final_report_phase/최종보고서_안영진_v8.docx`·`_v8_검토용.pdf` 34쪽(장별 6·7·7·7·2·1), 3차 검토 반드시 1~5·권장 6~11·13~15 반영(12 커밋 라벨 수동 검토는 사람이 읽어야 해서 제외), [26] El Emam 외 2001 추가. 자동 검사 175/175 `_work_v8/verify_v8.py`, 양식 재검수 `학교양식_요구사항_검수.md` 7절, 4차 재채점 `_work_v8/review_4_v8.md`
27. **결과 화면을 '고친 곳의 변화' 중심으로 (10/22, 커밋 e607dc6)**: `page-result.js` 순서 = 제목·첫 카드(가장 크게 줄어든 함수의 CC·길이 전후 막대와 감소율, 함께 바뀐 함수 목록, 새 함수까지 합친 합계, 연결·순환 고리 변화) → 안전 확인 배지 줄(검사 규칙·원본 보존·승인 동일·다시 분석·빌드·동작 비교·직접 플레이, 자세히는 펼침, 플레이 기록 버튼) → 파일 점수 표(좁은 화면은 표 안에서 가로 스크롤) → '게임 전체 기준 보조 지표'(엉킴 총량·라운드 막대·네 값, 작게) → 버튼. 순수 계산은 `core.js`(`functionChanges`·`resultHeadline`·`safetyBadges`·`changeText`). `casual_demo.py`에 `behavior_checked`(그 수정본의 verification.json이 있을 때만 '동작 비교' 완료) 추가. 옛 라운드(`migrated`)는 '기록 없음'. 테스트 5개 추가(Node DOM 대역으로 화면 순서까지 확인), 전체 567개 통과. 검사 서버 `result-check`(8771, 실제 라운드 사본, AI 호출 없음)를 `.claude/launch.json`에 추가

28. **C/C++ 추출 범위 보완과 재측정 (10/22, 커밋 997a311, push 완료)**: 4차 재채점(92점)이 찾은 문제 — 기본 분석이 namespace·extern "C"·template·#if 블록 안의 함수·전역 변수를 읽지 않음(OpenRCT2 328/544파일 LOC·CC 0). `cpp_analyzer._file_scope_items`(#if 0 제외, cpp-analyzer-0.2) + 테스트 2개. Chocolate Doom·OpenRCT2 고정 실험과 8사례 지표 제거·LOPO 재측정(`docs/_verification/2026-10-22-cpp-scope/rerun.py`·`publish.py`, 이전 결과 `reports/archive/pre-cpp-scope-2026-10-22`). 새 값: G-SI ρ Doom 0.6011·RCT2 0.4633, LOC가 네 사례 모두 G-SI보다 높음, G-SI > CC 4/4, 기본 0.5265, LOPO 0.5265→0.5297(+0.0032). `tools/partial_loc.py` → `reports/partial_loc.json`: LOC 통제 G-SI 0.12~0.19, 실제 줄 수 통제 0.10~0.43(모두 양수), 상위 20% G-SI 44~56%·LOC 48~65%·CC 33~46%. 웹 입력 재분석(같은 명령, 3회 중앙값, `remeasure_web.json`): Quake 2 4,489·OpenTTD 10,830·STK 13,395·Endless Sky 3,946·OpenTyrian 기본 581 함수, Default_MenuKey·엉킴 99.78·OpenTyrian 사례 값은 그대로. 문서 `docs/cpp-scope-review.md`, README 수치 갱신. 최종 커밋 e607dc6 테스트 569개(`docs/_verification/2026-10-22-final/tests-e607dc6.xml`)
29. **최종보고서 v9 (10/22, 로컬)**: v8 + 재측정 수치 + 4차 검토 반드시·권장(LOC 정의, LOC·CC와의 비교, 실제 줄 수 통제, 처방 계산값은 상한(43→22 대 실제 43→40), Quake 2 문장 범위, 거절 경로 회귀 검사 25개, 결과 화면 설명) + 참고문헌 링크 색 통일. 34쪽(6·7·7·7·2·1), 자동 검사 159/159(`_work_v9/verify_v9.py`), 양식 재검수 8절, 5차 재채점 `_work_v9/review_5_v9.md`
30. **v9 5차 재채점과 최종보고서 v10 (10/23, 로컬)**: 5차 재채점 93점(`_work_v9/review_5_v9.md`, 상세설계 28→29). v10 = v9 + 5차 반드시(요약·서론·결론에 '게임 루프·순환', 서론 상위 20%의 LOC 비교, 24쪽 첫 문장) + 권장(처방 계산값 '줄어드는 최대치', C/C++ 범위 문장 둘로, 순환 제외 이득은 OpenRCT2 0.4633→0.5186, 표 16 출처 입력 이름) + 선택(줄머리 가운뎃점 0·'G-SI'/'그림 1' 끊김 0, 그림 6 점 크기를 재측정 G-SI로 `_work_v10/fig6_map.png`). 표지 날짜 10/23. 온라인 자료 확인일은 10/21 유지(10/23 재확인에서 SciTools만 403). 34쪽 6·7·7·7·2·1, 자동 검사 167/167(`_work_v10/verify_v10.py`), 양식 재검수 9절, 6차 재채점 `_work_v10/review_6_v10.md`
31. **'한 번에 깊게'와 리허설 피드백 반영 (10/25, 커밋 전)**
   - **배경**: 리허설에서 처방 5개를 한 번에 고르자 283KB가 되어 한도 240KB를 넘었고, 큰 파일 두 개가 발췌만 전달됐다. 사용자는 라운드를 나누지 않고 한 번에 큰 결과를 원했다.
   - **설계**: `docs/superpowers/specs/2026-10-25-deep-refactor-design.md`. Codex Astra의 읽기 전용 설계 검토를 반영해 파일별 함수 정리로 범위를 좁혔고, link는 선택 방식으로 남겼다. planner(Fable)는 사용량 한도로 검토하지 못했다.
   - **한 번에 깊게(`strategy: 'deep'`)**
     - 파일마다 AI를 따로 부르고 3개씩 동시에 처리한다.
     - 파일과 헤더가 300KB 이하면 통째로 보낸다. 넘으면 대상 함수 본문 전체를 보내고, 잘라서 보내지 않는다(보내지 못하면 '보류'로 표시).
     - 자기 파일의 함수만 바꿀 수 있다. 파일마다 검사한 뒤 합친다.
     - 부분 성공을 허용하고, 거절된 파일만 다시 만들 수 있다(`retry_of`). 전체 마감은 25분이고, 자동 재시도는 없다.
     - 취소는 각 작업 스레드에 전달하고 `CANCELLED`로 늦게 뜬 프로그램도 멈춘다.
     - 파일 하나의 제한 시간은 900초다. API 출력 한도는 32,000이며, 400이면 8,000으로 다시 보낸다. `MAX_FILE_BYTES`는 1MB로 올렸다.
   - **처방**: 대상 함수(`targets`)를 받고, 정밀 분석에서는 함수 분리를 우선하도록 안내한다.
   - **화면**
     - Codex 앱 안의 `codex.exe` 인식과 `codex login status` 확인.
     - 'AI 처방 주변'은 처방 전에 비활성화.
     - 카드 막대에 '상위 N%', 펼치면 'N위 · 52개 중 · 상위 N%'(공동 순위 포함).
     - 변경안 요약은 2×2로 바꾸고, 문장마다 줄을 나누고 첫 문장은 굵게, 코드 이름은 칩으로 보여 준다. 파일 관계 넘침도 고쳤다.
     - 변경 방식 선택, 파일별 진행 줄, 거절 파일 상자.
     - 결과 화면에 '코드가 이렇게 바뀌었습니다'(`GET /rounds/{n}/changes`).
   - **테스트**: `tests/test_deep_refactor.py`(6개)와 UI·연결·진단 테스트를 더했다.
   - **검사 서버**: 가짜 AI `deep-check`(8772).
   - **함정**
     - app.css의 전역 `.ok` 클래스가 상태 표시용 `ok` 클래스와 겹친다. 상태 클래스는 `is-`·`t-` 접두사를 쓴다(두 번 겪음).
     - Bash heredoc·`python -c`로 코드를 바꾸면 역슬래시가 깨진다. 스크립트는 Write 도구로 파일에 쓴다.

## 남은 일
- **소스 ZIP 구성 확인**: 참고문헌 [18]은 "제출 소스 압축 파일의 docs/_demo_phase_v3·docs/_verification 기록"을 가리킨다. 아래 ZIP 계획(docs/_* 제외)과 맞추려면 이 두 폴더(.env·API 키 없음 확인 후)는 넣어야 한다
- 교내 발표 PPT(지정 양식 `(양식)_교내발표용_PPT.pptx`)
- 작품 업로드용 소스 ZIP(.env·docs/_private·docs/_* 제외)
- 소감 문단은 작성자가 직접 읽고 고치기, 지도교수 서명, 실제 포털 제출(사용자)
- 시연 영상(제출 약 2주 뒤): 녹화 전 10~15분 리허설 권장. Claude Code 로그인 확인 → OpenTyrian 새 작업(ZIP: docs/_demo_phase_v3/OpenTyrian-source.zip, src 범위, 분석 방식 정밀) → 처방 → 1라운드 → 빌드·직접 플레이 → (선택) 2라운드. 실제 AI 요청 전 사용자 확인 필수

## 검사 환경
- 실서버: `.claude/launch.json` game-si-web (8767). 검사 전용: ui-check (8768, scratchpad 사본, 가짜 처방·라운드 포함 — 실제 기록 아님), realcheck (8769, scratchpad 실제 점검 작업)
- 테스트: `py -3.10 -m pytest tests` (C#은 `C:\Program Files\dotnet` PATH 필요, Clang 환경 없으면 80개 skip)
- 커밋은 사용자 요청 시에만
