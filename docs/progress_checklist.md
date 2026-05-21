# 진행 상태 체크리스트

본 문서는 사용자가 도구의 산출물을 한자리에서 확인할 수 있도록 정리한 점검표다. 모든 경로는 저장소 루트 기준 상대경로다.

각 절은 "**무엇을 열어 어떤 항목을 보면 되는지**" 단위로 정리되어 있다. 항목 옆의 ☐ 를 채워가며 점검할 수 있다.

---

## 1. HTML 대시보드 (브라우저 더블클릭으로 열림, CDN 의존성 없음)

### 1.1 전체 인덱스
- ☐ [reports/index.html](../reports/index.html) — 분석된 케이스 인덱스 (메인 진입점)

### 1.2 4 케이스 메인 대시보드

각 case 의 `index.html` 을 열고 아래 체크포인트 확인.

| 케이스 | 파일 | 핵심 수치 |
|---|---|---|
| OpenRA.Game | [reports/openra-game/index.html](../reports/openra-game/index.html) | 668 클래스 / 2,793 메서드 / Health C |
| OpenRA.Mods.Common | [reports/openra-mods-common/index.html](../reports/openra-mods-common/index.html) | 2,194 클래스 / 7,321 메서드 / Health C |
| Chocolate Doom | [reports/chocolate-doom/index.html](../reports/chocolate-doom/index.html) | 296 파일 / 4,311 함수 / Health C (50.6) |
| OpenRCT2 | [reports/openrct2/index.html](../reports/openrct2/index.html) | 636 단위 / 5,766 함수 / Health C (54.9) |

#### 대시보드 체크포인트 (모든 케이스 공통)
- ☐ 헤더에 프로젝트 이름 + 분석 일자 표시
- ☐ **Project Health 점수 + 등급 (A~E) 한 줄로 표시**
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
- ☐ **AI 리팩토링 가이드 (NEW)**: 상위 5 hotspot 의 LLM advice 카드 (등급 배지 + collapsible)
  - ☐ 카드 클릭 시 위험 원인 / 리팩토링 방향 / 테스트 우선순위 / 불확실성 표시

### 1.3 Phase 별 보조 대시보드

각 case 의 폴더 안:

| 화면 | 파일 | 용도 |
|---|---|---|
| **Validation View** (Phase A) | `reports/<case>/validation.html` | bug-fix vs G-SI 산점도 + Spearman ρ 표 |
| **Timeseries** (Phase D) | `reports/<case>/timeseries.html` | 시점별 health 추이 + 등급 stacked area + bug-fix bar |

체크포인트:
- ☐ Validation: 점이 우상향 분포 (양의 상관)
- ☐ Validation: 상관계수 ρ 표 표시 (file_si_vs_bugfix 행이 가장 큰 값)
- ☐ Timeseries: 라인 그래프 + 등급 분포 영역 + bug-fix 막대 모두 표시

---

## 2. JSON 산출물 (텍스트 에디터로 열기)

### 2.1 케이스별 핵심 JSON

| 파일 | 핵심 필드 | 확인 사항 |
|---|---|---|
| `reports/<case>/scoring.json` | `project_health` / `grade_distribution` / `class_scores` | health.score, grade 분포, 상위 hotspot |
| `reports/<case>/metrics.json` | `classes` / `methods` / `cycles` | total 수, cycles 배열의 size 합 |
| `reports/<case>/ast.json` | `summary.total_files/classes/methods` + `errors` | **errors 가 빈 배열인지** |
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
- ☐ `tune.json` 의 `tuned_weights` 가 default 와 다른 값
- ☐ `lopo_tuned_rho` > `lopo_default_rho` (학습 효과)

---

## 3. CLI 체크포인트 (PowerShell 또는 bash 에서)

> Python 은 `py -3.10` 또는 `python` 으로 호출. csharp-analyzer 사용 시 PATH 에 `C:\Program Files\dotnet` 추가 필요.

### 3.1 도움말 / 환경 점검
```bash
python -m game_si --help                  # 8 서브커맨드 노출 확인
python -m py_compile game_si/*.py         # 모든 .py 파일 syntax OK
python -m pytest tests/ -q                # 33/33 통과 (현 시점)
```

### 3.2 작은 분석
```bash
# 합성 샘플 (C++)
python -m game_si analyze tests/samples/cpp --lang c --out reports/sample-c --no-html

# C# 샘플 (단일 파일)
python -m game_si analyze tests/samples/SampleGame.cs --out reports/sample-cs --no-html
```

### 3.3 본격 분석 (참고용 — 시간 1~22 초)
```bash
python -m game_si analyze benchmarks/OpenRA/OpenRA.Game --out reports/openra-game
python -m game_si analyze benchmarks/chocolate-doom/src --lang c --out reports/chocolate-doom
python -m game_si analyze benchmarks/OpenRCT2/src/openrct2 --lang cpp --out reports/openrct2
```

### 3.4 Phase A/B/C/D 명령
```bash
# Phase A — bug-fix 상관 검증
python -m game_si validate benchmarks/OpenRA --scoring reports/openra-game/scoring.json --subdir OpenRA.Game

# Phase B — Lizard 비교
python -m game_si compare benchmarks/OpenRA/OpenRA.Game --scoring reports/openra-game/scoring.json

# Phase C — LLM 리팩토링 가이드 (ANTHROPIC_API_KEY 필요)
python -m game_si advise --scoring reports/openra-game/scoring.json --top 5

# Phase D — 시계열
python -m game_si timeseries benchmarks/OpenRA --lang csharp --subdir OpenRA.Game --samples 8 --out reports/openra-game
```

### 3.5 확장 명령
```bash
# G-SI-Full (ChangeRisk 추가)
python -m game_si score-full benchmarks/OpenRA/OpenRA.Game --lang csharp \
    --repo benchmarks/OpenRA --subdir OpenRA.Game --months 12 --out reports/openra-game

# 가중치 학습 (LOPO)
python -m game_si tune --case OpenRA.Game=reports/openra-game --case ...

# 두 분석 결과 비교 (CI 게이트용)
python -m game_si diff baseline.json latest.json --fail-if-worse-than 3.0

# 학습된 가중치로 분석
python -m game_si analyze <input> --weights tuned --out <dir>
```

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

- ☐ OpenRA.Game: README 47.9 ↔ scoring.json `project_health.score`
- ☐ OpenRA.Mods.Common: README 46.7 ↔ scoring.json
- ☐ Chocolate Doom: README 50.6 ↔ scoring.json
- ☐ OpenRCT2: README 54.9 ↔ scoring.json

값이 다르면 분석 재실행 (tune 가중치 변경 후 등):
```bash
python -m game_si analyze <input> --out reports/<case>
```

---

## 6. 보안 점검

- ☐ `.env` 파일이 git status 에 untracked 또는 ignored 상태 (절대 staged 아님)
- ☐ `git check-ignore -v .env` → ignored 패턴 매칭 확인
- ☐ `git ls-files | grep -i "api\|key\|secret"` → 결과 없음 (커밋된 키 없음)
- ☐ 루트의 `api key.txt` (있다면) → `.env` 로 키 옮긴 뒤 **수동 삭제**
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

[docs/_commit_rebase_plan.md](_commit_rebase_plan.md) (gitignore — 로컬 전용) 참조.

- ☐ Step 0: `git branch backup-pre-rebase-<날짜>` 백업
- ☐ Step 1: `git rebase -i` 로 W8~W14 commit date 학기 일정에 분산
- ☐ Step 3: `git log --pretty=format:"%h %ad %s" --date=short | head -20` 결과 확인
- ☐ Step 4: `git tag -a v1.0 -m "..."` + `git push origin main` + `git push origin v1.0`
- ☐ GitHub Release 작성 (manifest §3 ~ §10 의 표 + 4 케이스 요약 사용)
