# 최종판 후보 재현성 검증 (2026-10-03)

> 후속 기록(2026-10-22): [C/C++ 추출 범위 보완과 재측정](cpp-scope-review.md). C/C++ 기본 분석이 namespace·extern "C"·template·#if 블록 안의 함수도 읽도록 고친 뒤 Chocolate Doom·OpenRCT2와 지표 제거·LOPO를 다시 측정했다. 그 두 사례와 지표 제거·LOPO의 최신 값은 그 문서를 따른다.
>
> 이 문서는 식별·호출 연결 보완 전의 2단계 검증 기록입니다. 이후 수정된 수치와 최신 판정은 [최종 보완·재검수](refinement-review.md)를 우선합니다. 아래 결과가 보완 후 결과와 다른 것은 분석 결함 수정 때문이며, 과거 기록은 그대로 보존합니다.

## 현재 결론

중간보고서 제출·승인 이후, 기존 구현을 실제로 재검증하고 튜닝 검증의 계산·분리 기준을 보완했다. 새 게임이나 유료 AI 분석은 추가하지 않았다. 현재 패키지 버전은 `1.0.0rc1`이며 v1.0 태그·GitHub Release·학교 제출을 실행한 것은 아니다.

기본 분석 8개 사례의 기존 점수·지표는 모두 재현됐다. 새 `scoring.json`에는 재계산용 반올림 전 `raw_exact` 필드만 추가했다. 본 분석과 튜닝의 기본값도 파일 단위 상관이 일치했다. 단위·회귀·CLI 통합 테스트 49개와 실험 결과 자동 확인 67개가 통과했다. 후자는 세 원본 저장소의 입력 커밋·작업 상태, 계산 일치, 시계열 32시점, 프로젝트별 fold 분리 및 선택한 가중치의 정밀도 일치를 검사한다.

## 1. 실험 기준과 보존

| 항목 | 최종판 기준 |
|---|---|
| 입력 | 기존 3개 게임 저장소, 8개 분석 사례 유지 |
| 통계 제외 | OpenRA.Server: 분석 파일 1개, 최소 5개 기준 미충족 |
| 기타 제외 조건 | bug-fix 상수값 또는 기본 점수의 상관 계산 불가; 유효 원본 프로젝트 2개 미만이면 LOPO 중단 |
| 기본 분석 | 기존 default 가중치 유지, 클래스 단위 G-SI → 파일 최대값 |
| 튜닝 계산 | 클래스 전체 기준 Z-score → 가중합 → 백분위(소수 둘째 자리) → 파일 최대값 |
| 교차 검증 | OpenRA의 모든 모듈을 함께 제외하는 원본 프로젝트 단위 LOPO |
| 평균 | 프로젝트 내 사례 평균을 구한 뒤 3개 프로젝트를 동일 가중 평균 |
| G-SI-Full | UTC 종료일 2026-10-03, 시작일 2025-10-08 (12개월=360일 근사) |
| 시계열 | 과거 실험과 동일한 8개 커밋씩, 현재 분석기로 재측정 |
| AI 안내 | 기존 20개 생성 결과를 과거 실험 예시로 보존, 새 API 호출 없음 |

| 저장소 | 고정 커밋 |
|---|---|
| OpenRA | `8f2138c71106aaffd8a288b56d1c9ef6013700ba` |
| Chocolate Doom | `c62b634f394e64dd51dec7e6f890496f43a56ade` |
| OpenRCT2 | `7a2cddeed1304f284829ffb0c91f31557819c51e` |

재검증 원본은 로컬 `docs/_verification/2026-10-03/`에 남긴다. 현재 공개 결과는 `reports/`에 반영하며 교체 전 결과 JSON은 `reports/archive/pre-final-2026-10-03/`에 보존한다. 승인된 `docs/_midterm_phase/중간보고서_안영진.docx`는 수정하지 않는다.

이전 +0.0130 및 +0.0288은 당시 계산·분리 기준의 실험 기록이다. 새 수치로 과거 기록을 덮어쓰거나 동일 조건에서 성능이 변한 것처럼 비교하지 않는다. 공개용 근거 JSON은 `reports/verification-2026-10-03.json`이며 구현·테스트 소스 SHA-256 및 환경 버전을 포함한다.

화면 표시용 `raw`는 소수 넷째 자리지만, 새 튜닝은 `raw_exact`를 사용한다. 과거 JSON에 해당 필드가 없으면 이전 반올림 지표로 계산하고 `input_precision`에 근사 계산임을 표시한다. 기본·전체 선택·세 fold 가중치의 7개 유효 사례 상관을 원본 AST 계산과 대조했다. 그리드 후보 중 참여 사례 하나라도 상관이 정의되지 않으면 후보를 제외한다. 학습으로 선택한 가중치의 hold-out 모듈 중 하나라도 상관이 정의되지 않으면 오류로 중단하고 비교 불가로 처리한다. 이를 빼고 평균을 높이거나 검증 데이터를 보고 가중치를 다시 선택하지 않는다.

## 2. 기본 분석 및 Phase A

모든 상관은 파일 단위이며, bug-fix는 커밋 메시지 키워드로 만든 대리 지표다. 실제 결함 정답이나 미래 결함 예측 실험이 아니다.

| 주요 사례 | 파일 수 | 클래스/분석 단위 | Health | G-SI ρ | LOC ρ | CC ρ |
|---|---:|---:|---:|---:|---:|---:|
| OpenRA.Game | 226 | 668 | 48.62 | 0.6011 | 0.6988 | 0.5517 |
| OpenRA.Mods.Common | 1,080 | 2,194 | 46.78 | 0.5363 | 0.6129 | 0.5265 |
| Chocolate Doom | 296 | 296 | 50.57 | 0.5851 | 0.6158 | 0.4676 |
| OpenRCT2 | 544 | 636 | 54.84 | 0.4598 | 0.4062 | 0.3681 |

파일 단위와 클래스 단위의 상관은 다르다. 특히 OpenRA.Game의 클래스 단위 상관은 음수이므로 단위를 생략해 보편적인 양의 상관이라고 표현하지 않는다. p-value는 정규근사이며 0 출력은 수치 정밀도 한계다. 사용자 실험, 실제 리팩토링 효과, 인과관계는 검증하지 않았다.

## 3. 튜닝 결과와 권장 해석

전체 자료로 선택한 후보 가중치는 `cc=.35, coupling=.25, dependency_cycle=.05, global_state=.30, game_loop_centrality=.05`이다. 이 가중치는 최종 분석에 선택적으로 사용할 수 있지만 학습에 쓴 자료의 성능은 별도 검증 성능이 아니다.

| 원본 프로젝트 LOPO 평균 | ρ |
|---|---:|
| 기본 가중치 | 0.5194 |
| 각 fold의 학습 가중치로 계산한 hold-out | 0.5251 |
| 차이 | +0.0057 |

| 제외한 프로젝트 | 해당 프로젝트 hold-out 평균 ρ | 나머지 프로젝트에서 학습한 가중치 (CC/Coupling/DC/GS/GLC) |
|---|---:|---|
| OpenRA (유효 모듈 5개 함께 제외) | 0.5106 | .25 / .40 / .05 / .25 / .05 |
| Chocolate Doom | 0.6090 | .40 / .20 / .05 / .30 / .05 |
| OpenRCT2 | 0.4557 | .35 / .20 / .10 / .30 / .05 |

개선폭은 작고, 3개 프로젝트뿐이며, 개선의 통계적 유의성은 검정하지 않았다. OpenRCT2 hold-out은 기본값보다 낮다. 따라서 **default를 기본 동작으로 유지하고 tuned는 선택 기능으로 제공**한다. 새 프로젝트에서 항상 더 좋다는 결론은 내리지 않는다.

## 4. Lizard 비교

| 사례 | 매칭 파일 수 | top-5 Jaccard | top-10 | top-30 | G-SI vs Lizard max CC ρ |
|---|---:|---:|---:|---:|---:|
| OpenRA.Game | 226 | 0.6667 | 0.4286 | 0.3636 | 0.6481 |
| OpenRA.Mods.Common | 1,080 | 0.2500 | 0.6667 | 0.5000 | 0.7926 |
| Chocolate Doom | 291 | 0.1111 | 0.1111 | 0.3333 | 0.7082 |
| OpenRCT2 | 544 | 0.1111 | 0.0526 | 0.2245 | 0.5307 |

G-SI와 CC가 다른 파일을 점검 후보로 제시한다는 근거다. 후보 목록 차이만으로 G-SI가 더 정확한 결함 탐지기라고 주장하지 않는다. 헤더 포함 여부 등 분석 범위도 다르다.

## 5. 시계열과 AI 안내

| 사례 | 새 Health 시계열 (8시점) | 새 순환 의존성 수 |
|---|---|---|
| OpenRA.Game | 38.09, 36.18, 40.39, 40.65, 44.03, 45.97, 47.76, 48.62 | 0, 0, 1, 1, 2, 3, 4, 5 |
| OpenRA.Mods.Common | 46.67, 44.77, 44.72, 46.73, 46.83, 47.01, 47.98, 46.78 | 0, 3, 3, 4, 4, 4, 5, 4 |
| Chocolate Doom | 52.44, 52.51, 52.32, 50.77, 51.75, 50.27, 50.49, 50.57 | 1, 1, 1, 3, 3, 2, 2, 2 |
| OpenRCT2 | 52.19, 52.18, 52.21, 52.18, 52.11, 52.11, 52.11, 54.84 | 1, 1, 1, 1, 1, 1, 1, 2 |

단조 악화나 감소 구간 없음이라는 해석은 하지 않는다. 점수는 각 분석 시점의 내부 분포를 기준으로 하므로 시점 간 절대 위험도 비교에도 한계가 있다. 순환 수·평균 결합도·코드 규모를 함께 확인한다.

AI 결과는 현재 점수·지표와 다른 사례가 있고 `Context`가 현재 `OpenRCT2.Context`로 표기되는 등 이름도 달라졌다. 기존 가이드는 생성 당시의 정성적 사용 예시로 보존한다. JSON 형식 준수는 제안의 정확성·유용성 검증과 다르다. 대시보드에도 생성 당시 지표를 기준으로 한 안내라는 주의문을 표시한다.

## 6. 환경, 검증 범위와 남은 일

Python 3.10, .NET SDK 8.0.421, NetworkX 3.4.2, NumPy 2.2.6, tree-sitter 0.25.2, tree-sitter-c 0.24.2, tree-sitter-cpp 0.23.4, Lizard 1.22.1을 사용했다. 최초 .NET 빌드는 오류 0개였으나 개발용 Roslyn 검사기의 컴파일러 버전 관련 CS9057 경고 2개가 있었다. 최종 증분 빌드는 오류·경고 0개였다. 증분 빌드만으로 최초 경고가 해결됐다고 판단하지 않으며, 의존성 버전을 변경하여 숨기지 않았다. Windows에서는 64비트 `C:\Program Files\dotnet`을 PATH 앞에 두었다.

검증: 단위·회귀·CLI 통합 테스트, 실제 8개 분석·Phase A, 주요 4개 Lizard 비교·Full·32시점 시계열, 결과 JSON 및 프로젝트 fold 분리. 유료 API의 현재 응답·품질, 수동 브라우저 상호작용 전체, 실제 GitHub의 최신 상태·배포는 이번 검증 범위가 아니다.

최종 마무리의 남은 산출물은 검증 결과를 바탕으로 한 별도 Word 최종보고서와 학교 지정 양식의 한 페이지 포스터다. 보고서·포스터의 제출 양식/시각 검수, 사용자의 제출 및 Git 공개 요청은 따로 확인한다. 과거 커밋 날짜를 바꾸지 않고 실제 재검증·보완을 현재 작업으로 기록한다.

## 7. 재현 방법

기존 입력 커밋을 유지하고 새 출력 디렉토리에서 실행한다. 분석 사례별 경로는 `reports/verification-2026-10-03.json` 및 `benchmark-manifest.md`의 고정 커밋에 대응한다.

```powershell
$env:PATH = "C:\Program Files\dotnet;" + $env:PATH
dotnet build csharp-analyzer/csharp-analyzer.csproj
py -3.10 -B -m pytest tests/ -q -p no:cacheprovider
py -3.10 -B -m game_si analyze benchmarks/OpenRA/OpenRA.Game --lang csharp --out docs/_verification/2026-10-03/openra-game
py -3.10 -B -m game_si validate benchmarks/OpenRA --scoring docs/_verification/2026-10-03/openra-game/scoring.json --subdir OpenRA.Game
py -3.10 -B -m game_si compare benchmarks/OpenRA/OpenRA.Game --scoring docs/_verification/2026-10-03/openra-game/scoring.json
py -3.10 -B -m game_si score-full benchmarks/OpenRA/OpenRA.Game --lang csharp --repo benchmarks/OpenRA --subdir OpenRA.Game --months 12 --until 2026-10-03 --out docs/_verification/2026-10-03/openra-game
py -3.10 -B -m game_si timeseries benchmarks/OpenRA --lang csharp --subdir OpenRA.Game --samples 8 --out docs/_verification/2026-10-03/openra-game
```

전체 8개 사례의 scoring·validation을 준비한 후:

```powershell
py -3.10 -B -m game_si tune --case OpenRA.Game=docs/_verification/2026-10-03/openra-game --case OpenRA.Mods.Common=docs/_verification/2026-10-03/openra-mods-common --case OpenRA.Mods.Cnc=docs/_verification/2026-10-03/openra-mods-cnc --case OpenRA.Mods.D2k=docs/_verification/2026-10-03/openra-mods-d2k --case OpenRA.Server=docs/_verification/2026-10-03/openra-server --case OpenRA.Platforms.Default=docs/_verification/2026-10-03/openra-platforms-default --case "Chocolate Doom=docs/_verification/2026-10-03/chocolate-doom" --case OpenRCT2=docs/_verification/2026-10-03/openrct2 --out docs/_verification/2026-10-03
py -3.10 -B docs/_verification/verify_final.py
```

프로젝트 그룹은 validation의 repo_path로 판정한다. 별도 이름이 필요하면 `--project-group NAME=PROJECT`로 지정한다. Full은 종료일을 고정하고, 시작·종료 경계를 UTC로 지정하여 정적 분석과 기간 의존 결과를 구분해 확인한다.
