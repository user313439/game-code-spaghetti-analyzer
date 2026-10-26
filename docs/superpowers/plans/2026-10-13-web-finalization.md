# 라이트 블루 확정 및 1~3단계 마무리 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 사용자가 확정한 라이트 블루를 로컬 웹의 기본 화면에 적용하고 실제 사용 검수·최신 문서 정리까지 완료한다.

**Architecture:** 기존 CSS 팔레트와 안전한 결과 링크를 재사용한다. theme 생략/미지원 값은 blue, 명시한 light/dark는 비교용으로 유지한다. 보고서 CSS는 HTTP 응답에만 적용하며 원본 HTML/JSON과 기존 사용자 기록은 보존한다. Git·최종보고서·AI 연결·추가 엔진 기능은 이번 범위 밖이다.

**Tech Stack:** 기존 FastAPI, HTML/CSS/JS, Python 3.10 pytest, Node, 실제 브라우저. 의존성 변경 없음.

### Task 1: 기본 테마

Files: game_si/web/static/app.js, index.html; game_si/web/app.py; tests/test_web_ui.py, test_web_app.py.

- [x] 기본/미지원 query가 blue이며 light/dark 명시 설정과 결과 링크를 유지하는 검사를 작성한다. API 기본 HTML blue, 명시 dark 원본, JSON/디스크 파일/CSP/삭제 접근 보존도 검사한다.
- [x] `py -3.10 -m pytest tests/test_web_ui.py tests/test_web_app.py -q -k 'theme or preview' --tb=short`에서 변경 전 실패를 확인한다.
- [x] JS는 `const requestedTheme = new URLSearchParams(location.search).get("theme"); const previewTheme = ["light", "dark", "blue"].includes(requestedTheme) ? requestedTheme : "blue";`로 선택한다. light는 루트 속성을 제거한다. 안전한 결과 링크에 dark도 명시하여 서버 기본 blue와 섞이지 않게 한다.
- [x] HTML 루트에 blue 속성과 blue theme-color를 넣는다. 보고서 응답은 `theme = theme if theme in {'light','dark','blue'} else 'blue'`로 선택하고 기존 FileResponse/CSS 경로를 유지한다.
- [x] 관련 검사와 `node --check game_si/web/static/app.js`를 통과시킨다.

### Task 2: 실제 사용 검수

- [x] 현재 서버 작업 목록을 확인한다. 진행 중인 작업이 없을 때만 소유한 실행 세션을 정상 재시작한다.
- [x] 기본 주소 → GitHub 주소 Enter → 가져오기 → 언어/범위 → 실제 새 분석 → 기본 블루 결과 → 표/그래프/도움말 → 기록을 확인한다. OpenRA 전체 C#은 기존 대표 시연 후보이며 오늘 실행과 기존 예시를 구분한다.
- [x] ZIP 입력으로 작은 실제 게임 소스를 분석한다. 폴더/드래그 입력은 가능한 브라우저 조작과 자동 검사 범위를 구분해 기록한다.
- [x] 이번 검수에서 만든 기록 하나만 삭제/되돌리기하여 다른 사용자 기록을 보존한다. 실제 실패 입력 안내도 확인한다.
- [x] 검색 결과가 없을 때 표 설명창 경계를 조사한다. 재현되는 문제만 최소 수정하고 회귀 검사한다. 지원하지 않는 hover 조작을 했다고 기록하지 않는다.
- [x] 화면 캡처와 새 검수 근거를 저장한다. 사용자 직접 체험·녹화는 미완료로 남긴다.

### Task 3: 검수·문서

Files: README.md, START_HERE.md, docs/README.md, docs/local-web-guide.md, docs/progress_checklist.md; 새 docs/web-final-review.md 및 reports/verification-web-finalization-2026-10-13.json.

- [x] 전체 검사 `py -3.10 -m pytest tests -q --tb=short`를 .NET 및 호환 libclang 조건으로 실행한다. 기존 보고서 226개·인덱스 해시를 확인한다.
- [x] README의 오래된 명령 개수·기능 범위·웹 기본 테마·검수 링크를 실제 코드와 맞춘다. 과거 실험 수치는 조건 없이 최신 값으로 덮어쓰지 않는다.
- [x] 진행 체크리스트는 최신 확인 기준으로 정리한다. '양의 상관이어야 통과' 같은 부적절한 통과 조건과 오래된 숫자는 제거하고 실제 증거/미확인/제출 대기를 나눈다.
- [x] 로컬 사용 안내에 기본 테마, 현재 주소/재시작 방법, 실제 시연 후보, AI와 정적 분석의 구분, 새 결과와 고정 예시의 구분을 명시한다. 전체 게임 정확도나 사용자 설문 완료를 주장하지 않는다.
- [x] 파일 검토와 독립 코드 검토에서 필요한 보완을 처리하고 사용자에게 결과/남은 직접 체험/다음 Git 단계만 안내한다. 커밋/push/버전 태그는 하지 않는다.

최종 근거: 전체 425 passed (72.00초), 후속 웹/상태 표시 161 passed (16.81초), 독립 검토 제안 반영 후 웹/API 55 passed (7.98초). 원본 보고서 226개와 인덱스 해시 일치. 사용자 직접 체험/탐색기 드래그/외부 브라우저는 완료 주장 없이 별도 대기. Git 작업 없이 현재 작업공간과 확인용 서버 유지.
