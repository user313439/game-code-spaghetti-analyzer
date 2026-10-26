# 전체 화이트 미리보기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 밝은 메인 디자인을 분석 결과창까지 연결하는 화이트 비교 버전을 제공하고, 기본 결과 및 다크 미리보기는 보존한다.

**Architecture:** `?theme=light` 링크로 미리보기를 선택한다. 메인 JS는 안전한 결과 경로에만 이 옵션을 붙인다. 결과 라우트는 허용된 HTML을 읽고 고정된 로컬 화이트 CSS를 응답에만 추가한다. 파일을 재생성하거나 점수·데이터·원본 HTML을 변경하지 않는다. 기존 CSP와 삭제된 결과 접근 제한을 유지한다.

**Tech Stack:** 기존 FastAPI, HTML/CSS/JS, Python 3.10 pytest와 Node. 새 의존성 없음.

**실행 범위:** 현재 공유 작업공간에서 사용자 요청한 미리보기를 만든다. Git 브랜치·커밋·push는 하지 않는다. 테스트 입력은 임시 폴더만 사용한다.

### Task 1: 안전한 화이트 결과 링크

Files: game_si/web/static/app.js, app.css; tests/test_web_ui.py.

- [x] 먼저 `previewResultUrl('/examples/openra-game/index.html','light')`가 해당 경로 뒤에 `?theme=light`를 붙이고, 외부/잘못된 경로는 null이며 기본/다크 옵션은 원래 경로임을 테스트한다. 실제 DOM 핸들러의 예시 링크와 결과 링크도 확인한다.
- [x] `py -3.10 -m pytest tests/test_web_ui.py -q -k white`로 기능 부재 실패를 확인한다.
- [x] 기존 safeResultUrl을 재사용해 최소 헬퍼를 구현한다. 결과 링크에는 light/blue만 추가하고 기본/다크 경로는 유지한다. 메인/기록/주 예시/보조 예시 링크에 일관되게 적용한다. 기존 밝은 기본 규칙과 다크 규칙은 보존한다.

### Task 2: 보고서 응답의 화이트 스타일

Files: game_si/web/app.py, game_si/web/static/report-light.css; tests/test_web_app.py.

- [x] 저장된 HTML과 JSON을 이용해 기본/다크 응답의 내용 불변, light HTML의 고정 CSS 삽입, 저장 파일 불변, JSON 불변, 알 수 없는 theme 미반영, 삭제된 결과의 light 접근도 404임을 검사한다. 기존 예시 라우트에도 같은 스타일과 CSP가 적용되는지 검사한다.
- [x] `py -3.10 -m pytest tests/test_web_app.py -q -k white`로 CSS 미적용 실패를 확인한다.
- [x] 허용된 결과 파일 조회가 끝난 뒤 공통 응답 헬퍼를 호출한다. theme가 light/blue이고 HTML head가 있을 때만 고정 CSS를 `</head>` 앞에 추가하는 HTMLResponse를 반환한다. 다른 경우는 기존 FileResponse를 유지한다.
- [x] 배경/패널/본문/보조문구/청록 강조색을 화이트 메인과 맞춘다. 하드코딩된 밝은 글씨, 표, 그래프 배경·라벨·선, 도넛 중앙값, 툴팁, 상태 경고, 등급 배지의 글씨를 함께 조정한다. 등급 배경색·데이터·그래프 노드·배치는 바꾸지 않는다.

### Task 3: 검수와 사용자 비교

- [x] 웹 테스트와 JS 문법 검사를 실행한다. 전체 테스트도 .NET 및 호환 libclang 조건으로 확인한다.
- [x] 실행 중인 작업이 없는지 확인하고, 현재 관리하는 로컬 실행 세션만 정상 종료/재실행해 최신 라우트를 적용한다.
- [x] 실제 브라우저에서 화이트 메인→기록/예시→완료/부분 결과를 연다. 표 검색·정렬·도움말·그래프 검색·확대·키보드 상태 툴팁을 점검한다. 캡처를 저장해 열어 보고 흰 화면에 남은 어두운 면이나 옅은 글씨를 보완한다. 표 헤더의 실제 마우스 hover 경계 검수는 도구 제한으로 미확인임을 기록한다.
- [x] 기존 정적 보고서 보존 해시를 확인하고 검수 기록을 저장한다. 화이트와 다크 링크를 함께 제공하고 기본 테마 확정은 사용자 피드백 후 진행한다.

### Task 4: 2026-10-13 사용자 요청 추가 — 세 번째 라이트 블루

Files: game_si/web/static/app.css, app.js, report-blue.css; game_si/web/app.py; tests/test_web_app.py, test_web_ui.py.

- [x] `?theme=blue`에만 블루그레이·옅은 하늘색 팔레트를 적용한다. 다크/화이트/기본은 유지한다. 새 CSS는 저장된 HTML 대신 응답에서만 적용한다.
- [x] 먼저 블루 선택·안전한 링크·네 DOM 링크 경로·API 팔레트·다른 버전 보존 검사를 작성하고 실패를 확인한다. 허용된 light/blue 이외 값은 파일명이나 HTML 삽입에 사용하지 않는다.
- [x] 기본 화이트 결과 스타일에 고정된 블루 팔레트를 더하는 방식으로 재사용한다. 메인에도 같은 배경/글씨/강조색을 적용하고 카드·입력·설명·기록·예시 색상을 조정한다.
- [x] 실제 브라우저와 자동 검사에서 세 버전·표 검색·그래프·부분 분석 경고를 확인하고 세 비교 링크를 제공한다. 최종 테마는 아직 확정하지 않는다.

검수 결과 (2026-10-13): 전체 검사 419 passed, 80.31초, Node 문법 검사 exit 0. 기존 보고서 226개 해시 일치 및 reports/index.html 보존. 독립 코드 검토에서 Critical/Important 없음. Git 작업 없이 현재 작업공간에 미리보기 유지.
