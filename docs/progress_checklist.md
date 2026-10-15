# 진행 상태 체크리스트

현재 마무리 기준은 [웹 최종 검수](web-final-review.md)이며 실행은 [로컬 웹 사용 안내](local-web-guide.md)를 따른다. 고정 8사례의 통계 수치 기준은 [refinement-review.md](refinement-review.md)다. 과거 테스트 수는 해당 날짜의 기록이며 현재 소스 검증을 대신하지 않는다.

## 현재 마무리 순서

- [x] 사용자 선택: 라이트 블루 디자인 확정.
- [x] 기본 주소와 새 결과·기록·예시에 같은 테마 연결. 비교용 light/dark 유지.
- [x] 새 공개 GitHub 입력으로 OpenRA 전체 C# 1,517개 파일을 실제 분석하고 결과 확인.
- [x] ZIP 선택 및 폴더 선택의 실제 입력·분석 흐름 점검.
- [x] 빈 검색에서도 정렬 화살표와 설명이 충돌하지 않도록 표시 보완.
- [x] 기록 정렬 및 이번 검수 기록의 삭제·되돌리기 확인. 기존 기록 유지.
- [x] 전체 425개 자동 검사 및 기존 보고서 226개·인덱스 보존 확인. 근거는 web-final-review.md 참조.
- [ ] 사용자 직접 체험: 주소 입력 → 범위 확인 → 분석 → 결과 확인. 에이전트 점검을 사용자 체험/설문으로 대체하지 않는다.
- [ ] 사용자 직접 드래그 입력 및 본인이 사용할 외부 브라우저 환경 확인.
- [ ] Git 반영 승인 후 공개 파일 선별·비밀/개인/임시 파일 점검·커밋·push.
- [ ] 승인된 중간보고서와 최종 양식을 참고해 별도 Word 최종보고서 작성·시각 검수.
- [ ] 학교 지정 한 페이지 포스터 작성·시각 검수.
- [ ] 실제 실행으로 발표 영상 녹화 및 학교 제출.

아래는 고정 실험 산출물을 추가 확인할 때의 체크포인트다. 모든 케이스·상호작용을 오늘 다시 검증한 것으로 표시하지 않는다. 새 웹 결과는 `.cache/web/jobs/`에 있으며 기존 `reports/` 예시와 다를 수 있다.

본 문서는 사용자가 도구의 산출물을 한자리에서 확인할 수 있도록 정리한 점검표다. 모든 경로는 저장소 루트 기준 상대경로다.

각 절은 "**무엇을 열어 어떤 항목을 보면 되는지**" 단위로 정리되어 있다. 항목 옆의 ☐ 를 채워가며 점검할 수 있다.

---

## 1. HTML 대시보드 (브라우저 더블클릭으로 열림, CDN 의존성 없음)

### 1.1 전체 인덱스
- ☐ [reports/index.html](../reports/index.html) — 분석된 케이스 인덱스 (메인 진입점)

### 1.2 고정 실험 주요 4사례와 별도 Clang 사례

각 case 의 `index.html` 을 열고 아래 체크포인트 확인.

| 케이스 | 파일 | 핵심 수치 |
|---|---|---|
| OpenRA.Game | [reports/openra-game/index.html](../reports/openra-game/index.html) | 668 클래스 / 2,793 메서드 / Health C |
| OpenRA.Mods.Common | [reports/openra-mods-common/index.html](../reports/openra-mods-common/index.html) | 2,194 클래스 / 7,321 메서드 / Health C |
| Chocolate Doom | [reports/chocolate-doom/index.html](../reports/chocolate-doom/index.html) | 296 파일 / 4,311 함수 / 보조 Health C; 구문 복구에 따른 부분 분석 |
| OpenRCT2 | [reports/openrct2/index.html](../reports/openrct2/index.html) | 544 파일 / 636 단위 / 5,766 함수 / 보조 Health C; 부분 분석 |
| DOOM 3 (별도 Clang 사례) | [reports/doom3-gameplay-clang/index.html](../reports/doom3-gameplay-clang/index.html) | 선택 구현 파일 69개 / 4,375 함수 / 부분 분석. 기존 통계 8사례와 별도 |

#### 대시보드 체크포인트 (모든 케이스 공통)
- ☐ 헤더에 프로젝트 이름 + 분석 일자 표시
- ☐ **보조 Health와 상대 등급 표시**. 절대 품질·버그 개수로 읽히지 않는지 확인
- ☐ 카드 행: 총 클래스 수, 총 메서드 수, 등급 분포 등
- ☐ 도넛 차트: 등급(A~E) 분포 시각화
- ☐ **Hotspot Table**: G-SI 상위 30 클래스 (정렬·검색·필터 동작)
  - ☐ 검색창에서 클래스 이름 일부 입력 시 행 필터링
  - ☐ 등급 드롭다운에서 E 만 선택 시 E 등급 행만 표시
  - ☐ 컬럼 헤더 클릭 시 정렬 방향 토글
- ☐ **Dependency Graph (SVG)**: 노드/엣지 표시 + 줌·팬 동작
  - ☐ 노드 hover 시 클래스 정보 툴팁
  - ☐ 노드 클릭 시 (구현돼있다면) 강조 표시
- ☐ **Cycle Explorer**: SCC(>=2) 목록 + 각 cycle 클릭 시 멤버 펼침
- ☐ **이전 AI 안내 예시 (있는 결과만)**: 생성 당시 데이터임을 구분. 새 웹 분석에서 자동 생성되지 않음
  - ☐ 카드 클릭 시 위험 원인 / 리팩토링 방향 / 테스트 우선순위 / 불확실성 표시

### 1.3 Phase 별 보조 대시보드

각 case 의 폴더 안:

| 화면 | 파일 | 용도 |
|---|---|---|
| **Validation View** (Phase A) | `reports/<case>/validation.html` | bug-fix vs G-SI 산점도 + Spearman ρ 표 |
| **Timeseries** (Phase D) | `reports/<case>/timeseries.html` | 시점별 health 추이 + 등급 stacked area + bug-fix bar |

체크포인트:
- ☐ Validation: 산점도가 실제 입력 JSON과 일치하고 분석 단위·표본·대리 지표를 설명
- ☐ Validation: 상관계수 ρ 표·계산 불가 사유 표시. 양의 상관이나 특정 지표 우위는 통과 조건이 아님
- ☐ Timeseries: 라인 그래프 + 등급 분포 영역 + bug-fix 막대 모두 표시

---

## 2. JSON 산출물 (텍스트 에디터로 열기)

### 2.1 케이스별 핵심 JSON

| 파일 | 핵심 필드 | 확인 사항 |
|---|---|---|
| `reports/<case>/scoring.json` | `project_health` / `grade_distribution` / `class_scores` | health.score, grade 분포, 상위 hotspot |
| `reports/<case>/metrics.json` | `classes` / `methods` / `cycles` | total 수, cycles 배열의 size 합 |
| `reports/<case>/ast.json` | `summary.total_files/classes/methods` + `errors` | 추출·진단과 analysis_status.json의 정상/부분/실패 집계가 일치하는지 |
| `reports/<case>/validation.json` | `class_correlations` / `file_correlations` | Spearman ρ 값 |
| `reports/<case>/compare.json` | `jaccard_topN` / `gsi_only_topN` | G-SI 단독 hotspot 목록 |
| `reports/<case>/advisor.json` | `rows[].advice` | 각 hotspot 의 4 절 (위험/리팩토링/테스트/불확실성) |
| `reports/<case>/timeseries.json` | `points[]` | 시점별 health_score 추이 |
| `reports/<case>/scoring_full.json` | (G-SI-Full) | ChangeRisk 포함 점수 |

> `ast.json` 과 `metrics.json` 은 용량이 커서 (.gitignore) git push 대상이 아님. 로컬에서만 확인.

### 2.2 케이스 간 통합 JSON

| 파일 | 내용 |
|---|---|
| `reports/tune.json` | 8-케이스 가중치 튜닝 + LOPO 결과 |
| `reports/tune_summary.txt` | 같은 내용의 사람용 텍스트 |

확인:
- ☐ `tune.json`의 선택 가중치·기본값·fold별 입력/출력이 실제 계산과 일치 (다른 값이어야 한다는 조건은 없음)
- ☐ 실제 분석과 튜닝의 기본값 상관 일치, 동일 원본 프로젝트의 train/hold-out 분리 확인
- ☐ 개선 여부와 무관하게 default·hold-out 결과 및 차이를 그대로 기록 (양의 개선폭 자체는 통과 조건이 아님)

---

## 3. CLI 체크포인트 (PowerShell 또는 bash 에서)

> Python 은 `py -3.10` 또는 `python` 으로 호출. csharp-analyzer 사용 시 PATH 에 `C:\Program Files\dotnet` 추가 필요.

### 3.1 도움말 / 환경 점검
```bash
python -m game_si --help                  # 9 서브커맨드 노출 확인
python -m py_compile game_si/*.py         # 모든 .py 파일 syntax OK
python -m pytest tests/ -q                # 현재 개수·환경은 web-final-review.md의 근거 참조
```

### 3.2 작은 분석
```bash
# 합성 C 샘플 (같은 폴더의 C++ 파일은 언어 선택으로 제외)
python -m game_si analyze tests/samples/cpp --lang c --out reports/sample-c --no-html

# C# 샘플 (단일 파일)
python -m game_si analyze tests/samples/SampleGame.cs --out reports/sample-cs --no-html
```

### 3.3 고정 벤치마크를 새 출력 폴더에서 분석 (시간은 환경·범위에 따라 달라짐)
```bash
python -m game_si analyze benchmarks/OpenRA/OpenRA.Game --out .cache/manual-check/openra-game
python -m game_si analyze benchmarks/chocolate-doom/src --lang c --out .cache/manual-check/chocolate-doom
python -m game_si analyze benchmarks/OpenRCT2/src/openrct2 --lang cpp --out .cache/manual-check/openrct2
```

### 3.4 Phase A/B/C/D 명령
```bash
# Phase A — bug-fix 상관 검증
python -m game_si validate benchmarks/OpenRA --scoring reports/openra-game/scoring.json --subdir OpenRA.Game --out .cache/manual-check/openra-game

# Phase B — Lizard 비교
python -m game_si compare benchmarks/OpenRA/OpenRA.Game --scoring reports/openra-game/scoring.json --out .cache/manual-check/openra-game

# Phase C — LLM 리팩토링 가이드 (ANTHROPIC_API_KEY 필요)
python -m game_si advise --scoring reports/openra-game/scoring.json --top 5 --out .cache/manual-check/advice

# Phase D — 시계열
python -m game_si timeseries benchmarks/OpenRA --lang csharp --subdir OpenRA.Game --samples 8 --out .cache/manual-check/openra-game
```

### 3.5 확장 명령
```bash
# G-SI-Full (ChangeRisk 추가)
python -m game_si score-full benchmarks/OpenRA/OpenRA.Game --lang csharp \
    --repo benchmarks/OpenRA --subdir OpenRA.Game --months 12 --out .cache/manual-check/openra-game

# 가중치 학습 (LOPO)
python -m game_si tune --help

# 두 분석 결과 비교 (CI 게이트용)
python -m game_si diff baseline.json latest.json --fail-if-worse-than 3.0

# 학습된 가중치로 분석
python -m game_si analyze <input> --weights tuned --out <dir>
```

전체 8사례 튜닝·지표 제거 실험의 실제 명령은 [refinement-review.md](refinement-review.md)를 따른다. 선택한 후보와 hold-out 결과를 구분한다. `advise`는 별도 유료 API 호출이며 사용자 동의·키 준비 없이 실행하지 않는다.

---

## 4. 환경 설정 (.NET 8 SDK)

C# 분석을 실행하려면 .NET 8 SDK 필요. 현재 PC 에서 점검:

```powershell
# 1) 설치 확인
dotnet --info       # 또는 "C:\Program Files\dotnet\dotnet.exe" --info

# 2) 빌드 (한 번만 필요)
"C:\Program Files\dotnet\dotnet.exe" build csharp-analyzer/csharp-analyzer.csproj -c Debug

# 3) PATH 등록 (영구)
[Environment]::SetEnvironmentVariable("PATH",
    "C:\Program Files\dotnet;" + $env:PATH, "User")
```

또는 한 세션만:
```powershell
$env:PATH = "C:\Program Files\dotnet;" + $env:PATH
```

설치 안 됐다면 [dotnet.microsoft.com/download/dotnet/8.0](https://dotnet.microsoft.com/download/dotnet/8.0) 에서 SDK 다운.

---

## 5. README 와의 일치 확인

`README.md` 의 표 (4 케이스 핵심 결과) 가 실제 `reports/<case>/scoring.json` 의 `project_health.score` 값과 일치하는지:

- ☐ OpenRA.Game: README 48.2와 scoring.json의 반올림 표시 일치
- ☐ OpenRA.Mods.Common: README 46.7과 scoring.json의 반올림 표시 일치
- ☐ Chocolate Doom: README 50.6 ↔ scoring.json
- ☐ OpenRCT2: README 54.9와 scoring.json의 반올림 표시 일치

값이 다르면 먼저 분석 버전·입력 커밋·가중치·기간·반올림 차이를 확인한다. 과거 값과 현재 값은 무조건 통일하지 않는다. 새 실행은 별도 결과 폴더에 저장한다:
```bash
python -m game_si analyze <input> --out .cache/manual-check/<new-case>
```

---

## 6. 보안 점검

- ☐ `.env` 파일이 git status 에 untracked 또는 ignored 상태 (절대 staged 아님)
- ☐ `git check-ignore -v .env` → ignored 패턴 매칭 확인
- ☐ 공개 대상 파일의 내용과 경로를 검사해 실제 비밀이 포함되지 않았는지 확인 (파일명 검색만으로 비밀 부재를 보증하지 않음)
- ☐ `docs/_private/api key.txt` (있다면) → `.env` 로 키 옮긴 뒤 **수동 삭제**
- ☐ `.gitignore` 의 §"Environment & Secrets" 절에 다음 패턴 모두 포함:
  - `.env`, `.env.local`, `.env.*.local`
  - `*.pem`, `*.key`, `secrets.json`
  - `api*key*.txt`, `api key.txt`, `api_key.json`
  - `.secret*`, `*.secret`, `*.secret.txt`

---

## 7. 문서 일치 확인

- ☐ [README.md](../README.md) 의 "핵심 결과 4 케이스 표" 가 manifest §3 과 일치
- ☐ [docs/si-formula.md](si-formula.md) 의 가중치 표가 `reports/tune.json` 의 `tuned_weights` 와 일치
- ☐ [docs/benchmark-manifest.md](benchmark-manifest.md) 각 케이스의 commit hash 가 `benchmarks/<repo>/.git` 의 현재 HEAD 와 일치 (또는 명시된 checkout 시점)

---

## 8. Phase E 진행 (선택)

[docs/phase_e_survey.md](phase_e_survey.md) 의 시연 시나리오 + 양식 사용. plan §7.5 "시간 허용 시" 영역.

- ☐ 대상자 3~5 명 (동료 학생 / SW 분야 경험자) 섭외
- ☐ 시연 환경 사전 준비 (`reports/` 4 케이스 미리 빌드)
- ☐ 30 분 세션 진행 + 응답 양식 수집
- ☐ 결과 정성 분석 → 보고서 §7.5 절 1~2 페이지

---

## 9. v1.0 release 운영

현재 실제 수행한 재검증·수정·문서화를 현재 날짜의 새 커밋으로 기록한다. 과거 커밋 날짜 변경은 하지 않는다. 커밋·태그·push는 사용자 명시 요청 후 실행한다.

- ☐ Step 0: 기존 결과·제출본 보존, 현재 변경사항 및 검증 근거 확인
- ☐ Step 1: 재검증·보완을 실제 수행 날짜로 기록
- ☐ Step 3: 과거 이력 그대로 유지, 비밀·임시 파일 제외 확인
- ☐ Step 4: `git tag -a v1.0 -m "..."` + `git push origin main` + `git push origin v1.0`
- ☐ GitHub Release 작성 (manifest §3 ~ §10 의 표 + 4 케이스 요약 사용)
