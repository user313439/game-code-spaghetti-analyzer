# game-code-spaghetti-analyzer

> 게임 엔진 기반 프로젝트의 유지보수성 향상을 위한 **Game Spaghetti Index (G-SI)** 측정·시각화 도구

[![grade: v1.0](https://img.shields.io/badge/release-v1.0-3b8e5a)]() [![tests](https://img.shields.io/badge/tests-17%2F17-3b8e5a)]() [![cases](https://img.shields.io/badge/case_studies-4-2b5d8c)]() [![langs](https://img.shields.io/badge/langs-C%23%20%C2%B7%20C%20%C2%B7%20C%2B%2B-2b5d8c)]()

게임 코드는 매 프레임 도는 게임 루프, 잦은 업데이트, 깊은 결합으로 인해 일반 정적 분석 지표(CC, LOC) 가 잡지 못하는 위험 패턴이 누적된다. 본 작품은 다섯 가지 메트릭(CC · Coupling · DependencyCycle · GlobalState · GameLoopCentrality) 을 가중합한 **G-SI** 점수를 프로젝트 내부 percentile rank 로 변환하여 0~100 점으로 표현하고, 단일 파일 HTML 대시보드로 시각화한다.

## 핵심 결과 (3 게임 프로젝트 / 4 본격 케이스 검증)

본 작품은 **OpenRA, Chocolate Doom, OpenRCT2** 를 대상으로 G-SI 를 적용했다. OpenRA 는 여러 내부 모듈로 나누어 분석했으며, C 기반 Chocolate Doom 과 C/C++ 기반 OpenRCT2 를 추가해 **언어와 구조가 다른 게임에서도 동일 지표가 동작함을 확인**했다. 검증에 사용한 분석 단위는 총 8 개 (OpenRA 6 모듈 + Doom 1 + RCT2 1) 이며, 그 중 OpenRA.Server (분석 가능 파일 1 개) 는 통계적 검증 단위로는 표본 부족이라 별도 표시한다 (§Limitations 참고).

**4 본격 케이스 — 파일 단위 Spearman ρ (vs bug-fix touch count)**:

| 케이스 | 언어 | 규모 | Project Health | G-SI ρ | LOC ρ | CC ρ |
|---|---|---|---:|---:|---:|---:|
| [OpenRA.Game](reports/openra-game/index.html) | C# | 668 클래스 / 2.8K 메서드 / 32K LOC | C (48.6) | **+0.580** | +0.699 | +0.552 |
| [OpenRA.Mods.Common](reports/openra-mods-common/index.html) | C# | 2,194 클래스 / 7.3K 메서드 / 117K LOC | C (46.8) | **+0.541** | +0.613 | +0.527 |
| [Chocolate Doom](reports/chocolate-doom/index.html) | C | 296 파일 / 4.3K 함수 / 190K LOC | C (50.6) | **+0.582** | +0.616 | +0.468 |
| [OpenRCT2](reports/openrct2/index.html) | C++ | 636 단위 / 5.8K 함수 / 486K LOC | C (54.8) | **+0.458** | +0.406 | +0.368 |

(모든 ρ 는 **파일 단위** Spearman 순위 상관계수, p<1e-6. 자세한 내용은 [docs/benchmark-manifest.md](docs/benchmark-manifest.md) §3.)

**검증 요약**:

- **RQ1 (위험 구간 식별의 일관성)** — 4/4 케이스에서 G-SI 가 bug-fix 빈도와 의미 있는 양의 상관 (파일 단위 ρ=+0.46 ~ +0.58, 모두 p<1e-13).
- **RQ2 (LOC/CC 와의 관계 — 보완 지표 관점)** — 케이스에 따라 G-SI 가 LOC/CC 보다 우월하기도 (OpenRCT2: G-SI +0.458 > LOC +0.406 > CC +0.368) 하고, LOC 가 더 강한 신호를 보이기도 (OpenRA.Game: LOC +0.699 > G-SI +0.580) 한다. **본 작품의 입장은 "G-SI 가 LOC/CC 를 대체"하는 것이 아니라 "기존 지표가 설명하지 못하는 게임 코드 특화 위험(게임 루프 결합, 전역 상태, 의존성 순환) 을 함께 설명하는 보완 지표" 라는 것이다**.
- **RQ3 (게임 특화 시그널의 추가 식별력)** — Phase B (Lizard 비교, plan §7.2) 에서 G-SI top-N 과 Lizard CC top-N 의 Jaccard 가 0.11~0.67 으로 격차 있음. **G-SI 만 식별하는 god-object 패턴** 다수 (예: OpenRA `Renderer.cs` CC=9 인데 결합도 100+, Chocolate Doom `i_system.c` CC=12 인데 결합도 156).
- **RQ4 (실용적 처리량)** — 최대 케이스(OpenRCT2 486K LOC) 도 22 초 분석, 검증·비교·시계열 모두 30 초 이내.

**클래스 단위 vs 파일 단위**: 같은 케이스도 분석 단위에 따라 결과가 달라진다. 예) OpenRA.Game 에서 **파일 단위 ρ=+0.58** 이지만 **클래스 단위 ρ=-0.12** — `TraitsInterfaces.cs` 같은 한 파일에 인터페이스 50 개가 들어있어 한 bug-fix 카운트를 공유하는 효과. 모든 ρ 인용 시 단위를 함께 표기한다 ([docs/benchmark-manifest.md §3](docs/benchmark-manifest.md) 표 참고).

추가 차원:
- **시계열 (Phase D)** — 4/4 케이스에서 시간 흐름에 따라 `cycle_count` 가 증가하거나 안정 유지 (감소 케이스 없음). OpenRA.Game 은 16 년 동안 cycles 0→5, project health 38→48 단조 악화.
- **LLM 가이드 (Phase C)** — Claude Haiku 4.5 로 20 hotspot 정성 분석. 모든 응답이 JSON schema 통과, 게임 도메인 패턴 (DOS 호환성, god-module, 거대 switch, 레거시 마이그레이션) 인지. 자동 코드 수정은 본 작품 범위 외(plan §6.4).

## CLI

설치 후 다섯 가지 서브커맨드가 노출된다.

```bash
# 1. 단일 프로젝트 정적 분석 → ast.json / metrics.json / scoring.json / index.html
python -m game_si analyze <repo_subdir> --lang {csharp,c,cpp,auto} \
    --out reports/<project>

# 2. Phase A — bug-fix 커밋 빈도와 G-SI 의 Spearman 상관 측정
python -m game_si validate <git_repo> --scoring reports/<project>/scoring.json \
    --subdir <subdir>

# 3. Phase B — 외부 도구(Lizard) hotspot 과의 비교
python -m game_si compare <repo_subdir> --scoring reports/<project>/scoring.json

# 4. Phase C — 상위 hotspot 에 대해 Claude Haiku 로 리팩토링 가이드
python -m game_si advise --scoring reports/<project>/scoring.json --top 5
# (ANTHROPIC_API_KEY 필요. .env 파일 또는 환경변수)

# 5. Phase D — 균등 간격 N 시점에서 G-SI 시계열 측정
python -m game_si timeseries <git_repo> --lang c --subdir src --samples 12 \
    --out reports/<project>
```

각 명령은 `reports/<project>/` 디렉토리에 결과 파일과 단일 파일 HTML 시각화를 함께 산출한다. HTML 은 CDN 의존성 없이 더블클릭으로 열린다.

## 기능 범위 — 현재 가능 / 향후

| 기능 | 상태 |
|---|:---:|
| C# 정적 분석 (Roslyn + SemanticModel) | ✅ v1.0 |
| C/C++ 정적 분석 (tree-sitter) | ✅ v1.0 |
| G-SI-Static 산출 + 등급 + Project Health | ✅ v1.0 |
| G-SI-Full (ChangeRisk 항목 추가) | ✅ v1.0 |
| 단일 파일 HTML 대시보드 (Refactoring Guide 통합) | ✅ v1.0 |
| Phase A 검증: bug-fix 상관 (`validate`) | ✅ v1.0 |
| Phase B 비교: Lizard hotspot (`compare`) | ✅ v1.0 |
| Phase C: LLM Refactoring Advisor (`advise`, Claude Haiku) | ✅ v1.0 |
| Phase D: 시계열 G-SI (`timeseries`) | ✅ v1.0 |
| 가중치 학습 + LOPO (`tune`) + `analyze --weights tuned` | ✅ v1.0 |
| `diff` (두 commit 간 G-SI 변화 + CI 게이트) | ✅ v1.0 |
| GitHub Actions 품질 게이트 샘플 | ✅ v1.0 |
| Phase E 사용자 설문 (양식 준비) | 🔶 사용자 진행 |
| Roslyn MSBuildWorkspace (csproj 자동 로드 + 외부 dll references) | ⏳ 향후 (plan §13 위험 분리) |
| SonarQube 비교 통합 | ⏳ 향후 (보고서 "비교 대상" 으로 언급) |
| Unity 샘플 분석 (plan §8.4 선택 후보) | ⏳ 향후 |
| 메서드 단위 G-SI (현재 클래스 단위) | ⏳ 향후 |
| 자동 코드 수정 패치 생성 | ❌ 범위 외 (plan §6.4) |

## 시작하기

### 요구 사항
- **Python 3.10 이상**
- **.NET 8 SDK** (C# 분석 시 — `C:\Program Files\dotnet` 권장)
- (선택) **Anthropic API 키** (Phase C LLM Advisor — `.env` 또는 환경변수)

### 설치 및 빌드

```bash
# Python 패키지 + 의존성 설치
pip install -e .

# C# 분석기 빌드 (한 번만)
cd csharp-analyzer && dotnet build && cd ..
```

### .NET 8 SDK PATH 등록 (필요 시)

`dotnet --info` 가 5.0 만 잡거나 안 잡히면:

```powershell
# 영구 (사용자 환경변수)
[Environment]::SetEnvironmentVariable("PATH",
    "C:\Program Files\dotnet;" + $env:PATH, "User")

# 또는 현재 세션만
$env:PATH = "C:\Program Files\dotnet;" + $env:PATH
```

설치 안 됐으면 [dotnet.microsoft.com/download/dotnet/8.0](https://dotnet.microsoft.com/download/dotnet/8.0) 참고.

### 환경 점검

```bash
python -m game_si --help           # 8 서브커맨드 노출
python -m py_compile game_si/*.py  # syntax OK
python -m pytest tests/ -q         # 33/33 통과
```

### 간단한 사용 예

```bash
# OpenRA.Game 분석 (C#)
python -m game_si analyze benchmarks/OpenRA/OpenRA.Game --out reports/openra-game
# → reports/openra-game/index.html 을 브라우저에서 열기

# Chocolate Doom 분석 (C)
python -m game_si analyze benchmarks/chocolate-doom/src --lang c --out reports/chocolate-doom

# Phase A 검증 (bug-fix 상관)
python -m game_si validate benchmarks/chocolate-doom \
    --scoring reports/chocolate-doom/scoring.json --subdir src
```

자세한 재현 명령은 [docs/benchmark-manifest.md](docs/benchmark-manifest.md) 의 각 케이스 절에 정리되어 있다.

## 결과 확인하기 (초보자도 OK — 브라우저 더블클릭)

| 보고 싶은 것 | 파일 |
|---|---|
| **전체 결과 한눈에 (한국어 마크다운)** | [docs/benchmark-manifest.md](docs/benchmark-manifest.md) §3~§10 |
| 전체 결과 대시보드 | [reports/index.html](reports/index.html) |
| OpenRA.Game 분석 (엔진 코어) | [reports/openra-game/index.html](reports/openra-game/index.html) |
| OpenRA.Mods.Common (게임 모드 공용) | [reports/openra-mods-common/index.html](reports/openra-mods-common/index.html) |
| Chocolate Doom 분석 (C 소스 포트) | [reports/chocolate-doom/index.html](reports/chocolate-doom/index.html) |
| OpenRCT2 분석 (C/C++ 재구현) | [reports/openrct2/index.html](reports/openrct2/index.html) |
| G-SI ↔ bug-fix 상관 그래프 (Phase A) | `reports/<case>/validation.html` |
| Lizard 와의 비교 결과 (Phase B) | `reports/<case>/compare_summary.txt` |
| LLM 리팩토링 제안 (Phase C) | `reports/<case>/advisor.md` 또는 각 대시보드 하단 |
| G-SI 시간 흐름 변화 (Phase D) | `reports/<case>/timeseries.html` |
| 단계별 진행 점검표 | [docs/progress_checklist.md](docs/progress_checklist.md) |

## 산출물 위치

| 위치 | 내용 |
|---|---|
| [reports/openra-game/](reports/openra-game/) | OpenRA.Game (C# 엔진 코어) 분석 + Phase A/B/C/D |
| [reports/openra-mods-common/](reports/openra-mods-common/) | OpenRA.Mods.Common (C# 게임 모듈) 분석 + Phase A/B/C/D |
| [reports/chocolate-doom/](reports/chocolate-doom/) | Chocolate Doom (C, Doom 소스 포트) |
| [reports/openrct2/](reports/openrct2/) | OpenRCT2 (C++, RollerCoaster Tycoon 재구현) |

각 케이스 디렉토리에는 다음이 포함된다 (개당 수 MB ast.json/metrics.json 은 `.gitignore`):
- `scoring.json` — 클래스별 G-SI · raw 메트릭 · 등급
- `index.html` — 메인 대시보드 (hotspot 표 · 의존성 그래프 · 등급 분포)
- `validation.{json,html,_summary.txt}` — Phase A 검증
- `compare.{json,_summary.txt}` — Phase B Lizard 비교
- `advisor.{json,md}` — Phase C LLM 가이드 (한국어)
- `timeseries.{json,html}` — Phase D 시계열

## 디렉토리 구성

```text
csharp-analyzer/   Roslyn 기반 C# 정적 분석 콘솔 (.NET 8)
game_si/           Python CLI 및 분석 파이프라인
  ├── analyzer.py        C# 분석기 호출 어댑터
  ├── cpp_analyzer.py    tree-sitter 기반 C/C++ AST 추출
  ├── metrics.py         그래프·메트릭 계산 (NetworkX)
  ├── si.py              G-SI 산출 + Project Health
  ├── report.py          메인 대시보드 HTML 생성
  ├── gitlog.py          git log 기반 bug-fix 커밋 추출
  ├── validate.py        Phase A — Spearman 상관
  ├── validate_report.py Phase A — 산점도 HTML
  ├── compare.py         Phase B — Lizard 비교
  ├── advisor.py         Phase C — Claude Haiku 호출
  └── timeseries.py      Phase D — git worktree 기반 시계열
tests/             pytest 단위 테스트 (17/17 통과)
docs/              ast-schema.md, benchmark-manifest.md
reports/           4 케이스 분석 산출물
benchmarks/        외부 분석 대상 (git 추적 제외, 재현은 manifest 의 커밋 해시로)
```

## 문서

- [docs/progress_checklist.md](docs/progress_checklist.md) — 산출물 확인 체크리스트 (대시보드 / JSON / CLI / 보안 점검)
- [docs/si-formula.md](docs/si-formula.md) — G-SI 공식 상세 + 가중치 운용(default/tuned/custom) + 등급표 + 검증 데이터 요약
- [docs/benchmark-manifest.md](docs/benchmark-manifest.md) — 분석 대상 메타정보 + Phase A/B/C/D 측정 결과 종합
- [docs/ast-schema.md](docs/ast-schema.md) — AST JSON 스키마 v0.2 (csharp-analyzer · cpp_analyzer 공통)
- [docs/phase_e_survey.md](docs/phase_e_survey.md) — Phase E 사용자 피드백 설문 가이드 + 양식 (선택)

## 한계 (Limitations) — 보강 / 향후 / 현실적 어려움

본 작품의 한계를 정직하게 분류한다.

### 현재 구현에서 보완된 부분
- **표본 부족 케이스 명시 처리** — OpenRA.Server 처럼 분석 가능 파일 수 < 5 인 케이스는 `tune` 결과에서 `excluded: insufficient samples` 로 표시되며 LOPO 평균에서 명시적으로 제외된다.
- **NaN/평가 불가 자동 경고** — `validate`, `tune` 명령이 n 부족 시 NaN 대신 사람이 읽을 수 있는 사유 문자열을 출력한다.
- **파일/클래스 단위 결과 분리** — 모든 ρ 값을 파일 단위와 클래스 단위로 함께 보고 (매니페스트 §3, §8). 단위에 따라 결과가 바뀌는 케이스(OpenRA.Game) 도 솔직히 표시.
- **unmatched change count** — validate 결과에 bug-fix 변경 중 분석 단위와 매칭 안 된 파일 수와 비율을 함께 보고.
- **결과 확인용 HTML/MD/summary** — 위 "결과 확인하기" 절에 정리.

### 향후 개발 가능한 부분
- **더 많은 게임 프로젝트 추가** — Unity 샘플(plan §8.4 선택 후보), Godot, MonoGame 등.
- **C/C++ semantic 분석 고도화** — 현재 tree-sitter syntactic 기반. `compile_commands.json` + clang tooling 도입 시 매크로·템플릿 정밀 분석.
- **bug-fix 커밋 → 원인 파일 매칭 정확도** — 현재는 변경된 모든 파일을 균등 가중. blame 기반 정밀 매칭 가능.
- **리팩토링 제안 적용 전후 G-SI 변화 비교** — Phase D 의 시계열 + Phase C 의 advice 를 결합한 후속 실험.
- **시간 단위 G-SI 추세와 실제 issue tracker 데이터 결합** — bug 리포트의 라벨/심각도까지 활용한 다층 검증.

### 현실적으로 어려운 부분
- **SonarQube 수준의 범용 정적 분석기 완성도** — 본 작품은 게임 도메인 특화 도구로 포지셔닝. 범용 분석기는 별도 영역.
- **모든 언어·게임 구조 완벽 분석** — 동적 dispatch (event handler, reflection), 매크로 metaprogramming 등은 정적 분석의 본질적 한계.
- **bug-fix 커밋 → 원인 코드 100% 정확 매칭** — 커밋 메시지 휴리스틱 의 한계는 본질적이며, 어떤 도구도 완벽 매칭은 불가.
- **정적 분석으로 런타임 버그·실제 플레이 안정성 증명** — 본 작품 범위 외. 정적 분석은 위험 신호 식별이며 실제 안정성은 동적·QA 검증이 별도 필요.

## 라이선스 / 표절 방지

- 분석 대상(OpenRA, Chocolate Doom, OpenRCT2) 의 원본 소스는 본 저장소에 **포함되지 않는다** (`benchmarks/` 는 `.gitignore`). 재현은 manifest 에 기록된 commit hash 로.
- 본 작품의 분석 코드 · 메트릭 · 시각화 · LLM 통합은 모두 직접 작성.
- LLM 입력에 원본 소스 전체를 보내지 않는다 — 지표값, 메서드 시그니처, 최대 30 줄 짧은 스니펫만.

## 메타 정보

| 항목 | 내용 |
|---|---|
| 분야 | 보안 / SW 공학 |
| 유형 | 작품 (개인) |
| 학기 | 2026학년도 1학기 |
| 소속 | 성균관대학교 소프트웨어학과 |
| 진행 | W1 → W14 (개발 트랙), v1.0 |
