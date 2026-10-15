# game-code-spaghetti-analyzer

> 게임 엔진 기반 프로젝트의 유지보수성 향상을 위한 **Game Spaghetti Index (G-SI)** 측정·시각화 도구

[![candidate](https://img.shields.io/badge/candidate-1.0.0rc1-3b8e5a)]() [![tests](https://img.shields.io/badge/tests-verified-3b8e5a)]() [![cases](https://img.shields.io/badge/case_studies-4-2b5d8c)]() [![langs](https://img.shields.io/badge/langs-C%23%20%C2%B7%20C%20%C2%B7%20C%2B%2B-2b5d8c)]()

현재 사용자 진입점은 **로컬 웹 분석 프로그램**입니다. 공개 GitHub 저장소 또는 ZIP·소스 폴더를 가져와 분석 범위를 선택하고, 새 결과와 분석 기록을 확인합니다. 기본 디자인은 라이트 블루입니다. 고정된 기존 실험 결과와 새 입력 실행 결과는 구분합니다. 현재 제품·검수 범위와 남은 제출 작업은 [웹 최종 검수](docs/web-final-review.md), 실행 방법은 [로컬 웹 사용 안내](docs/local-web-guide.md)를 먼저 확인하세요.

2026-10-04 최종 보완: 호출·타입 식별 오류를 수정하고 기본 분석 8사례, 과거 32시점, 튜닝을 재실행했다. 지표 제거 실험 7조합과 양방향 소스 사례 검토를 추가했다. 테스트 79개와 결과 확인 235개를 통과했다. 현재 버전은 릴리스 후보이며 태그·Release·제출은 별도다. 최신 수치와 한계는 [최종 보완·재검수](docs/refinement-review.md), 이전 단계 기록은 [재현성 검증](docs/final-verification.md)을 참조한다.

2026-10-05 후속 보완: 미지원·빈 입력, 파일/폴더 접근 실패, 문법 복구, 결과 저장 실패의 안내를 추가했다. 대시보드는 정상/부분 분석과 정적 근사의 한계를 표시한다. 첫 화면 소개를 정리하고 도움말은 기본 접힘으로 바꿨다. 테스트 105개와 후속 검사 74개를 통과했다. 현재 정적 분석 8사례의 점수·메트릭은 보완 전과 동일하며, C/C++ 파서 복구는 기존에 없던 진단 표시로 드러낸다. 상세 검수는 [오류 안내·화면 보완](docs/safety-ui-review.md)을 참조한다.

선택형 C/C++ 분석: `analyze --cpp-backend clang`은 컴파일 데이터베이스의 헤더·매크로 설정과 심볼을 사용한다. 기본 분석은 그대로 유지하며, 새 방식은 구현 파일 단위의 상대 검토 순위를 제공한다. 준비 조건·실게임 검수·지원 한계는 [컴파일 설정 기반 분석 안내](docs/compiler-aware-cpp.md)를 참조한다. 전체 엔진·모든 클래스·모든 빌드 구성의 완전한 분석을 의미하지 않는다.

본 작품은 다섯 구조 지표(CC · Coupling · DependencyCycle · GlobalState · GameLoopCentrality)를 혼합한 **G-SI**를 분석 집합 내부 백분위(0~100)로 표현하고 단일 파일 HTML로 시각화한다. 코드 검토 후보를 제시하는 도구이며 절대 품질·결함 확률의 판정기가 아니다. 모든 값이 동점이면 전부 100/E가 될 수 있어 원시 지표와 소스를 함께 확인한다. GlobalState와 게임 루프 연결은 정적 근사다.

## 핵심 결과 (3 게임 프로젝트 / 4 본격 케이스 검증)

본 작품은 **OpenRA, Chocolate Doom, OpenRCT2** 를 대상으로 G-SI 를 적용했다. OpenRA 는 여러 내부 모듈로 나누어 분석했으며, C 기반 Chocolate Doom 과 C/C++ 기반 OpenRCT2 를 추가해 **언어와 구조가 다른 게임에서도 동일 지표가 동작함을 확인**했다. 검증에 사용한 분석 단위는 총 8 개 (OpenRA 6 모듈 + Doom 1 + RCT2 1) 이며, 그 중 OpenRA.Server (분석 가능 파일 1 개) 는 통계적 검증 단위로는 표본 부족이라 별도 표시한다 (§Limitations 참고).

**4 본격 케이스 — 파일 단위 Spearman ρ (vs bug-fix touch count)**:

| 케이스 | 언어 | 규모 | 보조 Health | G-SI ρ | LOC ρ | CC ρ |
|---|---|---|---:|---:|---:|---:|
| [OpenRA.Game](reports/openra-game/index.html) | C# | 668 클래스 / 2.8K 메서드 / 32K LOC | C (48.2) | **+0.605** | +0.699 | +0.552 |
| [OpenRA.Mods.Common](reports/openra-mods-common/index.html) | C# | 2,194 클래스 / 7.3K 메서드 / 117K LOC | C (46.7) | **+0.535** | +0.613 | +0.527 |
| [Chocolate Doom](reports/chocolate-doom/index.html) | C | 296 파일 / 4.3K 함수 / 190K LOC | C (50.6) | **+0.585** | +0.616 | +0.468 |
| [OpenRCT2](reports/openrct2/index.html) | C++ | 636 단위 / 5.8K 함수 / 486K LOC | C (54.9) | **+0.469** | +0.406 | +0.368 |

(모든 ρ는 **파일 단위** Spearman 상관이다. Health는 검증되지 않은 보조 구조 요약이며 프로젝트 간 우열을 판정하지 않는다. 최신 근거는 [재검수 문서](docs/refinement-review.md).)

**검증 요약**:

- **RQ1 (후보와 과거 이력의 관련성)** — 4/4 주요 사례에서 과거 bug-fix 빈도와 양의 상관(파일 단위 ρ=+0.469~+0.605). 미래 결함 예측이나 실제 유지보수 비용 감소의 증거는 아니다. p-value는 정규근사이며 0 출력은 수치 정밀도 한계다.
- **RQ2 (기존 지표와의 관계)** — OpenRCT2에서는 G-SI 상관이 LOC/CC보다 높지만, 다른 주요 사례에서는 LOC가 더 높다. 지표 제거 실험에서는 기본 5항목 평균 ρ=0.5229, 게임 루프 제외 0.5403, CC+Coupling만 0.5262였다. **게임 특화 항목이 항상 성능을 높인다는 근거는 없다.** 기본값을 유지하고 다른 구조 관점의 설명 도구로 제시한다.
- **RQ3 (추가 점검 후보)** — Phase B에서 top-5 Jaccard는 0.11~0.67이다. G-SI가 CC와 다른 파일을 점검 후보로 제시한다 (예: Chocolate Doom `i_system.c`, Lizard CC=12, 결합도=156). 목록 차이만으로 실제 결함 탐지의 우수성이나 게임 전용 지표의 효과를 입증하지는 않는다.
- **RQ4 (처리량)** — 실행 시간은 근거 JSON의 사례별 `ast_elapsed_ms`에 남겼다. 병렬 작업 환경의 관측값이며 표준화된 성능 벤치마크가 아니다. 시계열은 분석을 반복하므로 더 오래 걸린다.

**클래스 단위 vs 파일 단위**: 같은 케이스도 분석 단위에 따라 결과가 달라진다. 예) OpenRA.Game 에서 **파일 단위 ρ=+0.60** 이지만 **클래스 단위 ρ=-0.12** — `TraitsInterfaces.cs` 같은 한 파일에 인터페이스 50 개가 들어있어 한 bug-fix 카운트를 공유하는 효과. 모든 ρ 인용 시 단위를 함께 표기한다 ([docs/benchmark-manifest.md §3](docs/benchmark-manifest.md) 표 참고).

추가 차원:
- **시계열 (Phase D)** — 4개 사례의 과거 8시점씩을 동일한 현재 분석기로 다시 측정한다. 장기 변화와 구간별 증감을 구분하며, 모든 구간에서 단조 악화한다고 해석하지 않는다. 각 시점 점수는 해당 시점 내부의 상대 순위이므로 절대 품질 추세의 입증에는 한계가 있다.
- **LLM 가이드 (Phase C)** — 기존 20개 hotspot 안내는 생성 당시 지표를 사용한 **이전 실험 예시**로 보존한다. 현재 점수·클래스명과 다른 항목이 있어 최신 검증으로 취급하지 않는다. 이번 재검증은 유료 API 호출을 하지 않았으며, 자동 코드 수정은 범위 외다.
- **튜닝** — 기본 가중치를 기본 동작으로 유지한다. 프로젝트 단위 LOPO 평균은 default +0.5229, tuned hold-out +0.5269 (차이 +0.0040)이다. 프로젝트는 3개뿐이며 개선의 통계적 유의성은 검정하지 않았다. 전체 자료로 선택한 가중치의 학습 성능과 hold-out 성능을 구분한다.

## 로컬 웹에서 새 소스 분석

`py -3.10 -m pip install -e ".[web]"` 설치 후 `py -3.10 -m game_si.web`를 실행하고 `http://127.0.0.1:8765`에 접속합니다. 이번 PC의 확인용 서버는 `--port 8766`으로 실행합니다. 공개 GitHub 주소 또는 ZIP·폴더 선택/끌어놓기로 소스를 가져와 범위를 확인하고 실제 분석을 실행합니다. 주소 입력 후 Enter는 **소스 가져오기**이며, 범위·언어 확인 후 **이 범위 분석하기**를 별도로 누릅니다.

메인·기록에서 연 결과창은 라이트 블루로 연결됩니다. `?theme=dark`와 `?theme=light`는 이전 디자인 비교용입니다. 스타일은 웹 응답에 적용하므로 저장된 단일 HTML을 직접 열면 원본 디자인을 유지합니다. 새 기록은 최신순·이름순·소스 크기순으로 정렬하고 삭제·복원할 수 있습니다. 원래 실험 결과를 덮어쓰지 않습니다. C#/.NET, Clang 준비 조건과 입력 제한은 [로컬 웹 사용 안내](docs/local-web-guide.md)를 참조하세요.

웹의 새 분석은 **정적 분석·시각화**입니다. CLI의 선택형 `advise`는 별도 AI 안내 기능이며, 현재 웹에는 새 AI 안내 생성·자동 코드 수정을 연결하지 않았습니다. 기존 AI 예시는 생성 당시 자료입니다. 전체 게임의 버그 탐지나 정확도 100%를 의미하지 않습니다.

## CLI

설치 후 9가지 서브커맨드가 노출된다 (`analyze`, `diff`, `validate`, `tune`, `ablate`, `score-full`, `timeseries`, `advise`, `compare`).

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

### 다른 소스 코드 분석과 오류 안내

`analyze`에 다른 C#/C/C++ 소스 폴더 또는 지원 소스 파일을 입력하면 새 결과를 생성한다. 게임 실행 파일·미지원 언어·프로젝트/솔루션 파일은 직접 분석하지 않는다. C/C++ 헤더 본문 분석도 범위 밖이다. 언어가 섞인 저장소는 분석 대상 폴더와 언어를 나누어 실행한다.

- 정상 추출: 종료 코드 `0`. 선택한 언어·범위의 정적 근사이며 외부 참조나 동적 동작을 완전히 해석했다는 뜻은 아니다.
- 부분 분석: 종료 코드 `3`. 읽기/추출 실패 파일·폴더는 건너뛰고, 문법 복구 구문은 가능한 추출 결과를 보존한다. 콘솔, `analysis_status.json`, 점수 JSON, HTML에서 범위와 진단을 확인한다.
- 실패: 종료 코드 `1`. 지원 파일이 없거나 유효한 결과가 없으면 점수를 만들지 않는다. 출력 저장 실패도 실패로 안내한다. 기존 결과는 삭제하지 않으므로 이번 실행의 성공 결과로 사용하지 않는다.

`score-full`도 같은 구분을 적용하고 `analysis_status_full.json`을 별도로 기록한다. 문법 복구 표시는 원본 게임 코드에 반드시 오류가 있다는 뜻이 아니다. 매크로·템플릿 등 파서 지원 한계도 원인일 수 있다. 이 보완은 현재 정적 분석과 Full 실행 범위이며, 과거 시계열 32시점의 파일별 진단을 다시 검사한 것은 아니다.

## 기능 범위 — 현재 가능 / 향후

아래 v1.0은 기능 목표 범위이며 정식 릴리스 발행을 뜻하지 않는다. 현재 패키지 버전은 1.0.0rc1이다. 지표 제거 실험은 `python -m game_si ablate --case OpenRA.Game=reports/openra-game --case Doom=reports/chocolate-doom --case RCT2=reports/openrct2 --out reports/ablation-example`처럼 실행한다. 본 검수의 전체 8사례 결과와는 입력 사례 수가 다른 실행 예다.

| 기능 | 상태 |
|---|:---:|
| C# 정적 분석 (Roslyn + SemanticModel) | ✅ v1.0 |
| C/C++ 정적 분석 (tree-sitter) | ✅ v1.0 |
| 선택형 C/C++ 컴파일 설정 기반 분석 (Clang, 구현 파일 단위) | ✅ 릴리스 후보; 부분 분석·준비 조건 명시 |
| 로컬 웹: 공개 GitHub / ZIP / 폴더 입력, 실제 분석, 기록 정렬·삭제·복원 | ✅ 릴리스 후보 |
| G-SI-Static 산출 + 등급 + Project Health | ✅ v1.0 |
| G-SI-Full (ChangeRisk 항목 추가) | ✅ v1.0 |
| 단일 파일 HTML 대시보드 (Refactoring Guide 통합) | ✅ v1.0 |
| Phase A 검증: bug-fix 상관 (`validate`) | ✅ v1.0 |
| Phase B 비교: Lizard hotspot (`compare`) | ✅ v1.0 |
| Phase C: LLM Refactoring Advisor (`advise`, Claude Haiku) | ✅ v1.0 |
| Phase D: 시계열 G-SI (`timeseries`) | ✅ v1.0 |
| 가중치 학습 + LOPO (`tune`) + `analyze --weights tuned` | ✅ v1.0 |
| 사전 고정 7조합의 지표 제거 실험 (`ablate`) | ✅ 릴리스 후보 |
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
python -m game_si --help           # 9 서브커맨드 노출
python -m py_compile game_si/*.py  # syntax OK
python -m pytest tests/ -q         # 현재 검수 수·환경은 docs/web-final-review.md 참조
```

### 간단한 사용 예

```bash
# OpenRA.Game 분석 (C#)
python -m game_si analyze benchmarks/OpenRA/OpenRA.Game --out .cache/manual-check/openra-game
# → .cache/manual-check/openra-game/index.html 을 브라우저에서 열기

# Chocolate Doom 분석 (C)
python -m game_si analyze benchmarks/chocolate-doom/src --lang c --out .cache/manual-check/chocolate-doom

# Phase A 검증 (bug-fix 상관)
python -m game_si validate benchmarks/chocolate-doom \
    --scoring .cache/manual-check/chocolate-doom/scoring.json --subdir src --out .cache/manual-check/chocolate-doom
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
csharp-analyzer/         C# 분석기 (.NET 8, Roslyn + SemanticModel)
game_si/                 Python 메인 패키지 — CLI · 분석 · 시각화 · 검증
  ├── cli.py                  9 서브커맨드 (analyze/validate/compare/advise/
  │                           timeseries/score-full/tune/ablate/diff)
  ├── web/                    로컬 웹: 입력 · 작업 상태 · 기록 · 예시 · 결과 응답
  ├── clang_analyzer.py        선택형 컴파일 설정 기반 C/C++ 추출
  ├── analyzer.py             C# csharp-analyzer 외부 콘솔 호출 어댑터
  ├── cpp_analyzer.py         tree-sitter 기반 C/C++ AST 추출
  ├── metrics.py              NetworkX 기반 그래프·메트릭 산출
  ├── si.py                   G-SI-Static + G-SI-Full 산출
  ├── report.py               메인 HTML 대시보드 생성 (단일 파일, CDN-free)
  ├── gitlog.py               git log 에서 bug-fix 커밋 추출
  ├── validate.py             Phase A — bug-fix ↔ G-SI Spearman 상관
  ├── compare.py              Phase B — Lizard hotspot 비교
  ├── advisor.py              Phase C — Claude Haiku LLM 가이드
  ├── timeseries.py           Phase D — git worktree 기반 시계열
  ├── change_risk.py          G-SI-Full 의 ChangeRisk 항목
  ├── tune.py                 plan §4.6 — 가중치 grid + LOPO 교차검증
  └── diff.py                 두 scoring.json 비교 (CI 품질 게이트용)
tests/                   pytest 단위·회귀·통합 테스트
docs/                    공개 문서 (ast-schema · benchmark-manifest ·
                                  si-formula · progress_checklist · phase_e_survey)
reports/                 고정 실험: 3 프로젝트 / 8 분석 사례 + 별도 Clang 검수:
  ├── index.html              전체 인덱스
  ├── openra-game/            OpenRA.Game (C# 엔진 코어) — 본격 케이스
  ├── openra-mods-common/     OpenRA.Mods.Common — 본격 케이스
  ├── openra-mods-cnc/        OpenRA.Mods.Cnc — Phase A 보조
  ├── openra-mods-d2k/        OpenRA.Mods.D2k — 보조
  ├── openra-server/          OpenRA.Server — 표본 부족 사례 (n=1)
  ├── openra-platforms-default/  Platforms.Default — 보조
  ├── chocolate-doom/         Chocolate Doom (C) — 본격 케이스
  ├── openrct2/               OpenRCT2 (C/C++) — 본격 케이스
  ├── doom3-gameplay-clang/    DOOM 3 게임플레이 — 부분 분석, 통계 실험과 별도
  └── openrct2-clang-sample/   Clang 기능 검증 3파일 표본, 전체 평가 아님
.cache/web/jobs/         새 웹 입력·로그·결과·분석 기록 (Git 제외)
benchmarks/              외부 분석 대상 (.gitignore — 재현은 manifest 의 commit hash)
.github/workflows/       g-si-quality-gate.yml — PR 마다 G-SI 변화 게이트 (sample)
```

## 문서

- [docs/progress_checklist.md](docs/progress_checklist.md) — 산출물 확인 체크리스트 (대시보드 / JSON / CLI / 보안 점검)
- [docs/si-formula.md](docs/si-formula.md) — G-SI 공식 상세 + 가중치 운용(default/tuned/custom) + 등급표 + 검증 데이터 요약
- [docs/benchmark-manifest.md](docs/benchmark-manifest.md) — 분석 대상 메타정보 + Phase A/B/C/D 측정 결과 종합
- [docs/ast-schema.md](docs/ast-schema.md) — AST JSON 스키마 v0.2 (csharp-analyzer · cpp_analyzer 공통)
- [docs/phase_e_survey.md](docs/phase_e_survey.md) — Phase E 사용자 피드백 설문 가이드 + 양식 (선택)
- [docs/local-web-guide.md](docs/local-web-guide.md) — 실행·입력·기록·시연 순서
- [docs/web-final-review.md](docs/web-final-review.md) — 웹 기본 디자인 확정 후 검수와 제출 전 남은 항목

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
- **C/C++ 분석 고도화** — 기본 tree-sitter와 선택형 Clang을 지원한다. 향후에는 다양한 컴파일 설정 자동 준비·헤더/클래스 집계·여러 빌드 구성과 동적 호출의 해석 범위를 확대한다. 현재 Clang도 완전한 엔진 분석은 아니다.
- **bug-fix 커밋 → 원인 파일 매칭 정확도** — 현재는 변경된 모든 파일을 균등 가중. blame 기반 정밀 매칭 가능.
- **리팩토링 제안 적용 전후 G-SI 변화 비교** — Phase D 의 시계열 + Phase C 의 advice 를 결합한 후속 실험.
- **시간 단위 G-SI 추세와 실제 issue tracker 데이터 결합** — bug 리포트의 라벨/심각도까지 활용한 다층 검증.

### 현실적으로 어려운 부분
- **SonarQube 수준의 범용 정적 분석기 완성도** — 본 작품은 게임 도메인 특화 도구로 포지셔닝. 범용 분석기는 별도 영역.
- **모든 언어·게임 구조 완벽 분석** — 동적 dispatch (event handler, reflection), 매크로 metaprogramming 등은 정적 분석의 본질적 한계.
- **bug-fix 커밋 → 원인 코드 100% 정확 매칭** — 커밋 메시지 휴리스틱 의 한계는 본질적이며, 어떤 도구도 완벽 매칭은 불가.
- **정적 분석으로 런타임 버그·실제 플레이 안정성 증명** — 본 작품 범위 외. 정적 분석은 위험 신호 식별이며 실제 안정성은 동적·QA 검증이 별도 필요.

## 라이선스 / 표절 방지

- 분석 대상(OpenRA, Chocolate Doom, OpenRCT2, DOOM 3)의 원본 소스는 본 저장소에 **포함되지 않는다** (`benchmarks/`와 웹 입력 캐시는 `.gitignore`). 고정 실험은 manifest의 commit hash로 재현한다. 새 GitHub 실행은 기록에 남긴 별도 커밋 기준이다.
- 본 작품의 분석 코드 · 메트릭 · 시각화 · LLM 통합은 모두 직접 작성.
- LLM 입력에 원본 소스 전체를 보내지 않는다 — 지표값, 메서드 시그니처, 최대 30 줄 짧은 스니펫만.

## 메타 정보

| 항목 | 내용 |
|---|---|
| 분야 | 보안 / SW 공학 |
| 유형 | 작품 (개인) |
| 소속 | 성균관대학교 소프트웨어학과 |
| 진행 | 중간보고서 승인 후 보완·검수, 릴리스 후보 1.0.0rc1 (제출·정식 릴리스 별도) |
