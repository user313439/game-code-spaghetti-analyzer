# 로컬 웹 사용성 보완 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 승인된 가독성·복구 가능한 기록 삭제·정렬·게임별 예시 소개를 기존 로컬 웹 흐름에 추가한다.

**Architecture:** 기존 JobManager JSON 메타데이터에 삭제 시각과 가져온 소스 크기를 보존한다. FastAPI는 삭제된 작업과 결과를 기본 접근에서 제외하고 복원을 지원한다. 기존 순수 JS·CSS 화면은 정렬, 삭제 확인, 되돌리기와 접힌 삭제 목록, 프로젝트별 소개로 확장한다.

**Tech Stack:** Python 3.10, FastAPI, 기존 HTML/CSS/JavaScript, pytest와 Node 테스트. 의존성 추가 없음.

**작업 방식:** 사용자가 현재 공유 작업공간에서 계속 수정하도록 승인했으며 기존 미커밋 구현을 유지한다. 새 worktree·브랜치·커밋·push를 만들지 않는다.

**상태:** 2026-10-12 구현·검수 완료. 전체 407개 테스트 통과(건너뜀 없음), 독립 명세·품질 검토 완료. 사용자 직접 시연 피드백을 기다린다. 최신 검수 화면은 `http://127.0.0.1:8766/`이다.

---

### Task 1: 사용성 보완 구현 (단일 통합 변경)

**Files:** game_si/web/inputs.py, jobs.py, app.py, static/index.html, app.css, app.js; tests/test_web_inputs.py, test_web_jobs.py, test_web_app.py, test_web_ui.py.

- [x] 크기 계산·삭제·복원 테스트를 먼저 작성하고 실패를 확인한다.

```python
ident = prepared(manager)
before = (manager.directory(ident) / 'input/game.c').read_bytes()
manager.delete(ident)
assert manager.list() == []
with pytest.raises(KeyError):
    manager.get(ident)
manager.restore(ident)
assert (manager.directory(ident) / 'input/game.c').read_bytes() == before
assert manager.get(ident)['can_delete']
```

등록 상태가 importing/running이거나 import_workers/processes에 남아 있으면 BusyError, 잘못된 ID는 거부한다. 삭제는 재시작 후 유지하고 restore는 기존 상태·결과·입력을 보존한다. scan.source_bytes는 제외 폴더 밖 소스·헤더만 합산하고 성공하지 않은 가져오기는 미확인이다. 과거 완료 기록의 누락 값은 시작 시 계산·저장하되 매 조회마다 계산하지 않는다.

- [x] API 테스트를 먼저 작성하고 실패를 확인한다.

```python
assert client.post(f'/api/jobs/{ident}/delete').status_code == 403
assert client.post(f'/api/jobs/{ident}/delete', headers=headers(client)).status_code == 200
assert client.get(f'/api/jobs/{ident}').status_code == 404
assert client.get(f'/results/{ident}/index.html').status_code == 404
assert client.get('/api/jobs').json() == []
assert client.get('/api/jobs?include_deleted=true').json()[0]['deleted_at']
assert client.post(f'/api/jobs/{ident}/restore', headers=headers(client)).status_code == 200
```

메타데이터 API 계약: get/list 기본은 삭제 제외, list(include_deleted=True)는 전체 기록, deleted_at은 시각 또는 null, can_delete는 현재 안전성에 따른 bool, 결과 URL은 삭제 시 null. start/cancel도 삭제된 ID를 받지 않는다. 예시 API는 기존 name/url에 project/genre/language/description/scope/focus/auxiliary를 추가해 정적 결과 링크를 유지한다.

- [x] 순수 UI 함수와 화면 계약 테스트를 먼저 작성하고 실패를 확인한다.

```javascript
const jobs = [{id:'old',name:'B',created_at:1,scan:{source_bytes:10}},
              {id:'new',name:'A',created_at:2,scan:{source_bytes:20}},
              {id:'unknown',name:'C',created_at:3,scan:null}];
assert.deepEqual(ui.sortJobs(jobs,'latest').map(j=>j.id), ['unknown','new','old']);
assert.deepEqual(ui.sortJobs(jobs,'name').map(j=>j.id), ['new','old','unknown']);
assert.deepEqual(ui.sortJobs(jobs,'size').map(j=>j.id), ['new','old','unknown']);
assert.equal(ui.formatSourceSize(null), '미확인');
```

정렬은 비파괴 복사본에서 수행하고 같은 값은 최신순이다. 작은 쓰레기통은 accessible name·안전 상태 disabled를 제공한다. 삭제는 확인 후 숨기고 되돌리기 알림과 기본 접힌 삭제 목록에서 복원을 지원한다. 정렬 변경·새로고침·삭제/복원 중 오래된 응답이 새 목록을 덮지 않도록 한다. 로컬 분석 설명은 키보드와 마우스로 확인한다. 고급 설정 및 하단 문구를 약 2px 확대·진하게 하고 모바일에서도 유지한다.

- [x] 위 테스트를 통과하는 최소 구현 후 웹 회귀 테스트를 실행한다.

Run: `py -3.10 -m pytest tests/test_web_inputs.py tests/test_web_jobs.py tests/test_web_app.py tests/test_web_ui.py tests/test_web_integration.py -q --tb=short`

게임별 예시는 OpenRA(엔진·공통 로직 링크), Chocolate Doom(src), OpenRCT2(기존 선택 범위), DOOM 3(게임플레이 Clang 부분 분석) 소개 카드로 표시한다. OpenRA 보조 4모듈은 별도 접힌 그룹이며 기존 reports 파일은 수정하지 않는다. DOM 삽입은 textContent를 유지한다.

- [x] 명세 독립 검토 후 코드 품질 독립 검토를 통과한다. 리뷰 문제는 재현 테스트부터 수정한다.

검토에서 상세 기록 응답 역전과 가져오기 생성·예약 사이의 경쟁 조건을 발견했다. 실제 버튼 핸들러/생성 직후 취소·삭제 회귀 검사에서 6개 실패를 확인한 뒤 최소 수정했고, 관련 7개 검사가 통과했다. 명세 재검토와 품질 검토에서 완료를 막는 문제는 없었다. 복원 후 키보드 초점 개선은 경미한 후속 항목이다.

### Task 2: 전체 검증·실제 브라우저·안내

**Files:** docs/local-web-guide.md, reports/verification-web-feedback-2026-10-12.json, 이 계획.

- [x] 사용 안내에 삭제는 캐시 보존·복원 가능, 크기는 가져온 소스·헤더 기준, 예시와 새 분석 구분을 적는다. 2048.c와 Chocolate Doom 입력·범위·영상 흐름을 안내한다.
- [x] 기존 정적 reports 보존 해시를 비교한다. Python 전체 tests를 .NET 및 호환 libclang 조건에서 실행하고 JS 문법 검사한다.
- [x] 기존 서버의 주소·작업 상태를 확인한다. 재시작 요청이 실행 정책에 차단되어 기존 서버를 강제 종료하지 않고 최신 버전을 8766 포트로 실행했다. 실제 사용은 새 주소에서만 한다.
- [x] 실제 브라우저에서 글씨·설명·정렬·삭제 확인 취소·삭제·되돌리기·재접속 후 복원·예시 펼치기·결과 링크를 확인한다. 검수용 새 기록만 삭제/복원하고 기존 사용자 기록은 건드리지 않는다.
- [x] 검증 근거와 제한을 저장하고 localhost 화면을 사용자에게 열어둔다. Git 작업은 하지 않는다.
