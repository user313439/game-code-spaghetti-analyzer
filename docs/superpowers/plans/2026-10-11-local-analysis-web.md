# Local Analysis Web Implementation Plan

> **For agentic workers:** Use subagent-driven-development for the independent frontend task and requesting-code-review for spec/quality checkpoints. The primary agent integrates dependent backend tasks. User instructions override automatic Git commits/worktree creation: preserve this dirty checkout, do not commit, branch, push, or change existing analysis outputs.

**Goal:** 로컬 브라우저에서 공개 GitHub, ZIP, 폴더 소스를 가져와 실제 기존 분석기를 실행하고 결과를 확인한다.

**Architecture:** FastAPI는 입력·작업 상태·허용된 결과만 제공한다. 작업별 소스와 결과는 `.cache/web/jobs/<uuid>/`에 분리하며 CLI는 별도 프로세스로 실행한다. CDN 없는 HTML/CSS/JavaScript는 두 입력 탭과 대상 확인·분석 상태·결과 링크를 제공한다.

**Tech Stack:** Python 3.10+, FastAPI, Uvicorn, python-multipart, psutil, pytest/httpx, 기존 game_si CLI, 순수 JavaScript.

## 작업 목록과 검증

### 1. 입력과 GitHub 가져오기

Create `game_si/web/inputs.py`, test `tests/test_web_inputs.py`.

- [x] Import가 아니라 누락 동작을 확인하는 실패 테스트 작성. 예: `assert importlib.util.find_spec('game_si.web') is not None`로 새 패키지 부재를 확인하고 이후 아래 기능을 테스트한다.
- [x] `safe_relative(name)`은 `../`, 절대/드라이브/UNC, Windows 장치/ADS, 심볼릭 링크 및 중복 대상 접근을 거부한다.
- [x] ZIP의 메타데이터뿐 아니라 실제 수신/해제 바이트를 검사한다. 100 MiB 입력, 1 GiB 해제, 20,000개 상한. 선택형 폴더 업로드는 1 GiB 총량과 20,000개 상한.
- [x] `parse_repository(url)`은 정확히 `https://github.com/<owner>/<repo>`만 받고 `.git` 접미사는 허용한다. 포트·인증정보·query·fragment·추가 경로는 거부한다.
- [x] `fetch_repository(url, destination)`은 공식 API에서 기본 브랜치 커밋을 가져오고 커밋 ZIP을 제한된 공식 호스트로 내려받는다. 오류는 사용자 안내용 ValueError로 변환한다.
- [x] `inspect_source(root)`는 분석 대상별 언어 수와 안전한 소스 하위 폴더를 반환한다. `.git`, 빌드/의존성 폴더는 제외하며 비지원 단독 입력을 거부한다.
- [x] 실행: `py -3.10 -m pytest tests/test_web_inputs.py -q`; 경로 탈출·잘못된 URL·손상 ZIP·상한 초과·정상 디렉터리 테스트 통과.

### 2. 작업과 CLI 실행

Create `game_si/web/jobs.py`, test `tests/test_web_jobs.py`.

- [x] `JobManager(root)` / `create(name, kind)` / `get(id)` / `list()` / `start(id, options)` / `close()` 계약을 테스트부터 고정한다.
- [x] JSON 메타데이터는 원자적 replace로 기록하고 ID를 검증한다. 서버 재시작 시 준비/실행 작업은 중단으로 복구한다.
- [x] `start()`는 언어·backend enum, 대상 상대 폴더·Clang 고급 로컬 경로를 검증하고 한 번에 한 실행만 허용한다.
- [x] CLI 인자 예: `[sys.executable, '-u', '-m', 'game_si', 'analyze', str(input_path), '--lang', lang, '--out', str(job_dir / 'result'), '--project-name', name]`.
- [x] 로그는 파일로 받고 제한된 최근 내용만 상태 API로 제공한다. 로그의 관측된 stage와 경과 시간만 보고한다.
- [x] 종료 0/3 + 이번 index.html/scoring.json/analysis_status.json 및 상태 일치가 확인된 경우에만 완료/부분 링크를 준다.
- [x] 실행 30분 제한, 서버 종료·취소 시 추적된 프로세스 트리만 종료한다. 중복 분석은 409로 매핑한다.
- [x] 실행: `py -3.10 -m pytest tests/test_web_jobs.py -q`; 실제 작은 C 소스를 CLI로 분석하고 결과/실패/재시작 검사.

### 3. HTTP 서버와 패키징

Create `game_si/web/app.py`, `__init__.py`, `__main__.py`; modify optional web dependencies/package-data in `pyproject.toml`; test `tests/test_web_app.py`.

- [x] GET `/api/session` returns `{token, limits}`; GET `/api/jobs` returns list; GET `/api/jobs/{id}` returns job metadata with stage/log/result_url.
- [x] POST `/api/import/github` JSON `{url, name}` returns prepared job. POST `/api/import/files` multipart has `files[]` and JSON `paths` (same order), `name`; single `.zip` is archive mode, otherwise relative-path folder mode.
- [x] POST `/api/jobs/{id}/start` JSON `{lang, subdir, backend, local_path, compile_commands, clang_library}` starts nonblocking analysis. POST `/api/jobs/{id}/cancel` requests termination.
- [x] GET `/api/examples` returns allowlisted existing report links. GET `/results/{id}/{filename}` only exposes result `index.html`, `scoring.json`, `analysis_status.json`; examples only approved report HTML. Never mount source directories or repo root.
- [x] Host exact loopback; mutation Origin must match host/port plus `X-Game-SI-Token`; deny broad CORS. Limit incoming body before multipart spooling. Serve token only same-origin, no-cache responses.
- [x] `python -m game_si.web --port 8765` runs loopback-only server with clear missing extra/port conflict messages; clean lifecycle closes jobs. No build script execution.
- [x] 실행: `py -3.10 -m pytest tests/test_web_app.py -q`; HTTP auth/path/upload/job/result tests plus optional package-resource check.

### 4. 간결한 화면

Create `game_si/web/static/index.html`, `app.css`, `app.js`; test `tests/test_web_ui.py`.

- [x] 테스트 우선: 두 입력 탭, ZIP/폴더 선택(`webkitdirectory`)과 drop zone, 접힌 advanced, CSP에 맞는 외부 정적 JS/CSS, aria-live 상태와 accessible labels 확인.
- [x] 위 HTTP 계약을 사용하는 `fetch` wrapper와 토큰, import → 확인 → start → polling → result 흐름 구현.
- [x] folder drop는 `webkitGetAsEntry`로 모든 readEntries 배치를 반복 수집한다. 폴더 선택은 `webkitRelativePath`를 보존한다. 파일 개수·총량·제외/지원 확장자를 사전 확인하고 서버에서도 검증한다.
- [x] 드래그 실패/미지원 브라우저는 폴더 선택으로 안내한다. 업로드 중·실행 중 중복 버튼을 잠근다. 결과 이름/로그는 textContent로 출력한다.
- [x] 화면은 독자적인 중립 밝은 배경과 청록 포인트, 작은 구조 분석 브랜드, 중앙 입력 카드. 그림/브랜드/문구 복제 없음. 사례/이력은 보조 메뉴.
- [x] 실행: `py -3.10 -m pytest tests/test_web_ui.py -q`; 가능한 실제 브라우저에서 사용자 입력/탭/결과를 검증한다.

### 5. 통합 및 사용 안내

Create `docs/local-web-guide.md`; add small README start section, keep old evidence unchanged.

- [x] ZIP·폴더는 같은 C 소스로 분석하여 CLI와 scoring/metrics 동등성 검사. 실제 공개 C/C++ 저장소를 가져오는 읽기 작업도 검사한다.
- [x] C#은 준비된 .NET으로 실제 샘플 분석; Clang은 기존 DOOM 환경의 호환 libclang과 별도 C++ fixture로 고급 local mode 실행을 검증한다. DOOM 전체 분석은 이번 UI 검증에서 재실행하지 않는다. 새 분석은 `.cache`만 사용한다.
- [x] 전체 회귀: `$env:PATH = 'C:\Program Files\dotnet;' + $env:PATH; py -3.10 -m pytest tests -q`.
- [x] wheel/정적 자원 포함과 실행 도움말 검사. 기록에는 실행 결과·실제 검증 범위·브라우저 제한을 정직하게 남긴다.
- [x] 사용자에게 로컬 링크와 실행 안내를 제공한다. 피드백 전에는 GitHub에 반영하지 않는다.

## 계약 자체 검토

GitHub와 폴더를 ZIP 업로드로 위장하지 않고 각각 실제 가져오기와 상대 경로 업로드를 구현한다. 모든 새 분석은 CLI를 실행한다. 기존 결과 단순 재표시는 분석 예시만 사용한다. 진행 상태는 관측값이며 결과 정확도 보증이나 서버 보안 샌드박스 주장을 하지 않는다.
