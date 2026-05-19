# game-code-spaghetti-analyzer

> 게임 엔진 기반 프로젝트의 유지보수성 향상을 위한 **스파게티 지수(Spaghetti Index, SI)** 측정 및 시각화 도구

## 개요

대규모 게임 코드베이스(LoL과 같은)는 잦은 업데이트 과정에서 복잡한 의존성으로 인해 예기치 못한 회귀 버그(Regression Bug)가 빈번히 발생한다. 본 작품은 게임 코드의 "엉킴 정도"를 정량적으로 측정·시각화하고, AI 기반 리팩토링 가이드를 제공하여 게임 엔진 기반 프로젝트의 유지보수성을 향상시키는 것을 목표로 한다.

## 연구 목적

- **대규모 게임 코드의 복잡성 해결**: 코드 간의 복잡한 의존성으로 인한 회귀 버그를 사전에 식별
- **객관적 지표의 부재 해소**: '스파게티 코드'에 대한 직관적이고 정량적인 지표 제공
- **품질 관리 자동화**: 실시간으로 코드의 엉킴 정도를 파악하고 리팩토링 가이드를 제공

## 진행 계획

1. **지표 정의 및 공식 수립**
   - 순환 복잡도(Cyclomatic Complexity, CC), 결합도(Coupling), 전역 변수 의존성을 결합한 스파게티 지수(SI) 산출 공식 정의
2. **정적 분석 엔진 구현**
   - C++ / C# 소스코드를 파싱하여 함수 및 클래스 간의 참조 관계를 추출하는 핵심 모듈 개발
3. **데이터 시각화 모듈**
   - 추출된 의존성 데이터를 그래프 형태로 시각화하여 코드의 '위험 구간'을 직관적으로 노출
4. **AI 기반 리팩토링 가이드**
   - 분석된 문제 코드에 대해 LLM API를 연동하여 구체적인 수정 방안 및 개선 코드를 제안
5. **실험 및 검증**
   - GitHub 내 오픈소스 게임 엔진 기반 프로젝트(소규모 Unity 게임, C++ 기반 아케이드 게임 등)를 대상으로 지수를 측정하고 유효성 검증

## 기대 효과

- **개발 생산성 증대**: 코드 수정 전 영향 범위를 사전에 파악하여 디버깅 및 테스트 시간 단축
- **기술 부채 감소**: 프로젝트 초기 단계부터 스파게티 지수를 관리하여 장기적인 유지보수 비용 절감
- **교육적 도구 활용**: 초보 개발자가 본인의 코드 스타일을 객관적으로 점검하고 학습할 수 있는 가이드 역할 수행

## 메타 정보

| 항목 | 내용 |
|---|---|
| 분야 | 보안 / SW 공학 |
| 유형 | 작품 (개인) |
| 학기 | 2026학년도 1학기 |
| 소속 | 성균관대학교 소프트웨어학과 |

## 분석 사례 (라이브 데모)

본 도구를 오픈소스 게임 엔진 [OpenRA](https://github.com/OpenRA/OpenRA) (Command & Conquer · Red Alert · Dune 2000의 오픈소스 재구현)에 적용한 결과를 다음 위치에서 바로 확인할 수 있다.

- 분석 사례 인덱스: [`reports/index.html`](reports/index.html)
- OpenRA.Game 모듈 (엔진 코어): [`reports/openra-game/index.html`](reports/openra-game/index.html) — 668 클래스 / 2,793 메서드, Project Health **C 등급 (47.9점)**
- OpenRA.Mods.Common 모듈 (공용 게임 부품): [`reports/openra-mods-common/index.html`](reports/openra-mods-common/index.html) — 2,194 클래스 / 7,321 메서드, Project Health **C 등급 (46.7점)**

각 HTML 파일은 외부 라이브러리 의존성 없이 단일 파일로 동작한다. 저장소를 clone한 뒤 위 경로의 파일을 브라우저로 열면 결과 대시보드가 그대로 표시된다. GitHub Pages가 활성화되어 있다면 같은 페이지를 URL로도 열 수 있다.

분석 시점의 OpenRA 커밋과 재현 명령은 [`docs/benchmark-manifest.md`](docs/benchmark-manifest.md)에 정리되어 있다.

## 사용 방법

### 요구 사항
- .NET 8 SDK
- Python 3.10 이상

### 빌드

```bash
# C# 분석 엔진 빌드
cd csharp-analyzer
dotnet build
cd ..
```

### 분석 실행

```bash
# 디렉토리 분석
python -m game_si analyze <대상_경로> --out reports/<프로젝트명>

# 상위 hotspot 콘솔 출력
python -m game_si analyze <대상_경로> --top 10
```

분석 결과 JSON 스키마는 [`docs/ast-schema.md`](docs/ast-schema.md), 분석 대상의 재현 정보는 [`docs/benchmark-manifest.md`](docs/benchmark-manifest.md)에 정리되어 있다.

## 디렉토리 구성

```text
csharp-analyzer/   Roslyn 기반 C# 정적 분석 콘솔 (.NET 8)
game_si/           Python CLI · 분석 어댑터 · 메트릭 엔진 · G-SI 산출 · HTML 대시보드 생성
tests/samples/     테스트용 샘플 C# 코드
docs/              ast-schema.md, benchmark-manifest.md (공개용 기술 문서)
reports/           분석 산출물 — index.html · openra-game/ · openra-mods-common/
benchmarks/        외부 분석 대상 (git 추적 제외)
```
