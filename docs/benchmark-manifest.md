# 분석 대상(벤치마크) 매니페스트

본 작품은 오픈소스 게임 코드를 **분석 대상 데이터셋**으로만 사용한다. 본 작품 코드에 포함하거나 기능으로 사용하지 않으며, 외부 저장소의 코드는 본 저장소에 커밋되지 않는다(`benchmarks/` 디렉토리는 `.gitignore`에 의해 추적 제외).

재현을 위해서는 본 파일에 기록된 URL과 커밋 해시를 사용하여 분석 시점의 코드 상태를 동일하게 재구성한다.

## 1. OpenRA (1차 분석 대상)

| 항목 | 값 |
|---|---|
| 저장소 URL | https://github.com/OpenRA/OpenRA |
| 라이선스 | GPL-3.0-or-later |
| 언어 | C# (.NET 8) |
| 분기 | `bleed` |
| 분석 시점 커밋 | `8f2138c71106aaffd8a288b56d1c9ef6013700ba` |
| 커밋 메시지 | "Fix crush logic" (2026-04-10) |
| 분석 일자 | 2026-05-14 |

### 1.1 재현 명령

```bash
# 저장소 clone (커밋 고정)
git clone https://github.com/OpenRA/OpenRA.git benchmarks/OpenRA
cd benchmarks/OpenRA
git checkout 8f2138c71106aaffd8a288b56d1c9ef6013700ba
cd ../..

# 분석 실행 (OpenRA.Game 모듈)
python -m game_si analyze benchmarks/OpenRA/OpenRA.Game --out reports/openra-game
```

### 1.2 분석 범위

W1 단계에서는 `OpenRA.Game` 모듈을 1차 대상으로 한다. 후속 단계에서 `OpenRA.Mods.Common`, `OpenRA.Server`, `OpenRA.Platforms.Default` 등을 순차적으로 추가한다.

### 1.3 측정 결과 (W1 시점, syntactic 분석)

| 항목 | 값 |
|---|---|
| 분석된 `.cs` 파일 | 226 |
| 클래스/구조체/인터페이스/레코드 | 668 |
| 메서드 및 생성자 | 2,793 |
| 합산 LOC (비주석·비공백) | 32,577 |
| 분석 소요 시간 | 약 4.6초 |
| 파싱 실패 파일 | 0 |

CC 분포는 일반적인 코드베이스 분포에 부합한다 (CC=1이 58.4%, CC≥21이 0.8%).

## 2. 후속 분석 대상

| 프로젝트 | URL | 라이선스 | 진입 단계 |
|---|---|---|---|
| Chocolate Doom | https://github.com/chocolate-doom/chocolate-doom | GPL-2.0 | W11 (Phase 2) |
| OpenRCT2 | https://github.com/OpenRCT2/OpenRCT2 | GPL-3.0 | W12 (Phase 2) |

각 대상의 분석 시점 커밋과 명령은 해당 단계 진입 시 본 문서에 추가한다.

## 3. 라이선스 및 재배포 원칙

- 본 매니페스트에 등재된 저장소의 코드는 본 작품 저장소에 복사하거나 포함하지 않는다.
- 본 작품의 분석 결과 JSON·HTML 리포트는 원본 소스 코드 전문이나 긴 코드 스니펫을 포함하지 않는 범위에서 산출·공유한다.
- 보고서에 코드 인용이 필요한 경우 파일 경로·지표값·그래프 구조·짧은 인용만 포함하고, 원본 저장소 URL과 라이선스를 함께 명시한다.
- 원본 게임 에셋(예: 게임 데이터 파일)은 본 작품에서 사용·배포하지 않는다.
