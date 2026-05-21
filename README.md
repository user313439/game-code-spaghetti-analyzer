# game-code-spaghetti-analyzer

> 게임 엔진 기반 프로젝트의 유지보수성 향상을 위한 **Game Spaghetti Index (G-SI)** 측정·시각화 도구

[![grade: v1.0](https://img.shields.io/badge/release-v1.0-3b8e5a)]() [![tests](https://img.shields.io/badge/tests-17%2F17-3b8e5a)]() [![cases](https://img.shields.io/badge/case_studies-4-2b5d8c)]() [![langs](https://img.shields.io/badge/langs-C%23%20%C2%B7%20C%20%C2%B7%20C%2B%2B-2b5d8c)]()

게임 코드는 매 프레임 도는 게임 루프, 잦은 업데이트, 깊은 결합으로 인해 일반 정적 분석 지표(CC, LOC) 가 잡지 못하는 위험 패턴이 누적된다. 본 작품은 다섯 가지 메트릭(CC · Coupling · DependencyCycle · GlobalState · GameLoopCentrality) 을 가중합한 **G-SI** 점수를 프로젝트 내부 percentile rank 로 변환하여 0~100 점으로 표현하고, 단일 파일 HTML 대시보드로 시각화한다.

## 핵심 결과 (4 케이스 검증)

| 케이스 | 언어 | 규모 | Project Health | Phase A G-SI ρ (vs bug-fix) |
|---|---|---|---:|---:|
| [OpenRA.Game](reports/openra-game/index.html) | C# | 668 클래스 / 2.8K 메서드 / 32K LOC | C (47.9) | **+0.580** (p<1e-6) |
| [OpenRA.Mods.Common](reports/openra-mods-common/index.html) | C# | 2,194 클래스 / 7.3K 메서드 / 117K LOC | C (46.7) | **+0.541** (p<1e-6) |
| [Chocolate Doom](reports/chocolate-doom/index.html) | C | 296 파일 / 4.3K 함수 / 190K LOC | C (50.6) | **+0.582** (p<1e-6) |
| [OpenRCT2](reports/openrct2/index.html) | C++ | 636 단위 / 5.8K 함수 / 486K LOC | C (54.9) | **+0.458** (p<1e-13) |

**검증 요약** (자세한 내용은 [docs/benchmark-manifest.md](docs/benchmark-manifest.md) §3~§6):

- **RQ1 (위험 구간 식별의 일관성)** — 4/4 케이스에서 G-SI 가 bug-fix 빈도와 유의한 양의 상관, ρ=+0.46 ~ +0.58 (모두 p<1e-13).
- **RQ2 (LOC/CC 단독 대비 추가 설명력)** — OpenRCT2 에서 G-SI(+0.458) > LOC(+0.406) > CC(+0.368) 로 G-SI 가 두 baseline 모두 능가. Chocolate Doom 에서 CC 단독 대비 Δρ +0.11.
- **RQ3 (게임 특화 시그널의 추가 식별력)** — Lizard 와 hotspot top-5 Jaccard 가 0.11~0.67. G-SI 만 식별하는 god-object 패턴 (예: OpenRA `Renderer.cs`(CC=9), Chocolate Doom `i_system.c`(CC=12)) 다수.
- **RQ4 (실용적 처리량)** — 최대 케이스(OpenRCT2 486K LOC) 도 22 초 분석, 검증·비교·시계열 모두 30 초 이내.

추가 차원:
- **시계열 (Phase D)** — 4/4 케이스에서 시간 흐름에 따라 `cycle_count` 가 증가하거나 안정 유지 (감소 케이스 없음). OpenRA.Game 은 16 년 동안 cycles 0→5, project health 38→48 단조 악화.
- **LLM 가이드 (Phase C)** — Claude Haiku 4.5 로 20 hotspot 정성 분석. 총 비용 $0.27, 모든 응답이 JSON schema 통과, 게임 도메인 패턴 (DOS 호환성, god-module, 거대 switch, 레거시 마이그레이션) 인지.

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

## 시작하기

### 요구 사항
- Python 3.10 이상
- .NET 8 SDK (C# 분석 시)
- (선택) Anthropic API 키 (Phase C LLM Advisor)

### 설치 및 빌드

```bash
# Python 패키지 설치
pip install -e .

# C# 분석기 빌드
cd csharp-analyzer && dotnet build && cd ..
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

- [docs/si-formula.md](docs/si-formula.md) — G-SI 공식 상세 + 가중치 운용(default/tuned/custom) + 등급표 + 검증 데이터 요약
- [docs/benchmark-manifest.md](docs/benchmark-manifest.md) — 분석 대상 메타정보 + Phase A/B/C/D 측정 결과 종합
- [docs/ast-schema.md](docs/ast-schema.md) — AST JSON 스키마 v0.2 (csharp-analyzer · cpp_analyzer 공통)

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
