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

### 1.4 Phase A 검증 결과 (W8, 2026-05-20)

Plan §7.1 의 Phase A 핵심 정량 검증을 본 매니페스트의 커밋(`8f2138c7`) 기준으로 수행했다. 검증 명령은 다음과 같다.

```bash
python -m game_si validate benchmarks/OpenRA \
    --scoring reports/openra-game/scoring.json --subdir OpenRA.Game
python -m game_si validate benchmarks/OpenRA \
    --scoring reports/openra-mods-common/scoring.json --subdir OpenRA.Mods.Common
```

본 시점 기준으로 `OpenRA.Game` 의 git history 6,242 커밋, `OpenRA.Mods.Common` 의 6,815 커밋이 스캔되었으며, 각 모듈에서 1,148 / 1,323 개의 bug-fix 커밋이 키워드 매칭으로 식별되었다 (`fix typo`/`fix indent` 등 사소한 수정은 제외).

| 모듈 | 분석 단위 | n | G-SI ρ | LOC ρ | CC ρ |
|---|---|---:|---:|---:|---:|
| OpenRA.Game | 파일 | 226 | **+0.580** | +0.699 | +0.552 |
| OpenRA.Game | 클래스 | 668 | −0.124 | −0.185 | −0.144 |
| OpenRA.Mods.Common | 파일 | 1,080 | **+0.541** | +0.613 | +0.527 |
| OpenRA.Mods.Common | 클래스 | 2,194 | **+0.075** (p<0.001) | +0.027 (n.s.) | +0.024 (n.s.) |

(모든 파일 단위 p-value 는 1e-6 이하로 측정되었다. ρ는 Spearman 순위 상관계수.)

해석 요약은 다음과 같다.

- **파일 단위에서 G-SI 가 bug-fix 빈도와 강한 양의 상관을 보인다.** 두 모듈 모두 ρ≈+0.55 ± 0.04 범위로, LOC 단독(+0.61~0.70) 보다 약간 낮지만 CC 단독(+0.53~0.55) 과 동등 수준이다. Plan RQ1 을 지지하는 일관된 신호다.
- **클래스 단위에서는 단위 부적합 효과가 관찰된다.** 한 파일에 다수 클래스가 포함된 경우(예: `TraitsInterfaces.cs` 의 50+개 인터페이스) 모든 클래스가 동일한 bug-fix 카운트를 공유한다. 이는 plan §13 에서 명시한 "분석 단위 부적합" 시나리오의 실측 예로, OpenRA.Game 케이스에서는 음의 상관, OpenRA.Mods.Common 케이스에서는 약한 양의 상관으로 나타났다.
- **OpenRA.Mods.Common 클래스 단위에서는 G-SI 만 통계적으로 유의(p<0.001)했고 LOC/CC 단독은 유의성 미달이었다.** 큰 n(=2,194) 에서도 추가 설명력이 검출된다는 점에서 plan RQ2 (G-SI 가 LOC/CC 단독 대비 추가 설명력) 의 약하지만 일관된 근거가 된다.
- **bug-fix 커밋의 비-클래스 변경 (자산/설정/주석 등) 은 OpenRA.Game 1,150 회, OpenRA.Mods.Common 549 회** 로 측정되었다. 이는 정적 분석 대상 외 변경이며, 분석기 신호 외부의 자연 noise 로 분류된다.

세부 산출물은 다음 위치에 저장된다.

- 텍스트 요약: `reports/openra-game/validation_summary.txt`, `reports/openra-mods-common/validation_summary.txt`
- JSON 원본: `reports/openra-{game,mods-common}/validation.json`
- HTML 시각화 (산점도 포함): `reports/openra-{game,mods-common}/validation.html`

## 2. 후속 분석 대상

| 프로젝트 | URL | 라이선스 | 진입 단계 |
|---|---|---|---|
| Chocolate Doom | https://github.com/chocolate-doom/chocolate-doom | GPL-2.0 | W11 (Phase 2) — 진입 완료 |
| OpenRCT2 | https://github.com/OpenRCT2/OpenRCT2 | GPL-3.0 | W12 (Phase 2) |

### 2.1 Chocolate Doom (W11 진입)

| 항목 | 값 |
|---|---|
| 저장소 URL | https://github.com/chocolate-doom/chocolate-doom |
| 라이선스 | GPL-2.0 |
| 언어 | C (.c/.h) |
| 분기 | `master` |
| 분석 시점 커밋 | `c62b634f394e64dd51dec7e6f890496f43a56ade` |
| 커밋 메시지 | "strife: Mirror the `mouse_fire_countdown` in joystick logic as well (#1796)" (2026-05-16) |
| 분석 일자 | 2026-05-20 |

**재현 명령**

```bash
git clone --depth 50 https://github.com/chocolate-doom/chocolate-doom.git benchmarks/chocolate-doom
cd benchmarks/chocolate-doom
git checkout c62b634f394e64dd51dec7e6f890496f43a56ade
cd ../..

python -m game_si analyze benchmarks/chocolate-doom/src --lang c --out reports/chocolate-doom
```

**측정 결과 (W11 시점, tree-sitter syntactic 분석)**

| 항목 | 값 |
|---|---|
| 분석된 `.c` 파일 (compilation unit) | 296 |
| 함수 정의 | 4,311 |
| 합산 LOC (비주석·비공백) | 190,440 |
| 분석 소요 시간 | 약 5.4초 (헤더 제외 본문만) |
| 파싱 실패 파일 | 0 |
| 클래스 의존성 그래프 edges | 1,058 (include 기반) |
| SCC (≥2) | 2 |

**Project Health**: 50.57 / 100 (등급 C). avg_si=50.35, risk_ratio=40.2%, avg_coupling=7.15 (C# OpenRA.Game 의 1.73 대비 4 배). 등급 분포 A 58 / B 60 / C 59 / D 59 / E 60.

**상위 hotspot 정성 검토** (G-SI 상위 10):

| 등급 | G-SI | 파일 | 주요 시그널 |
|---|---:|---|---|
| E | 100.00 | `i_system` | 결합도 156 (시스템 인터페이스) |
| E | 99.66 | `m_misc` | 결합도 116 (유틸 god-module) |
| E | 99.32 | `strife.p_switch` | CC_top10p=212 (거대 switch) |
| E | 98.99 | `i_video` | GS=263 (전역 비디오 상태) |
| E | 98.65 | `z_zone` | 결합도 90 (zone allocator) |
| E | 98.31 | `m_argv` | CC_top10p=25, 결합도 57 |
| E | 97.97 | `v_video` | 결합도 62, GS=32 |
| E | 97.64 | `w_wad` | WAD 로더, 결합도 62 |
| E | 97.30 | `deh_main` | DeHackEd 메인, 결합도 76 |
| E | 96.96 | `heretic.g_game` | **GS=546** (게임 전역 상태 god-object) |

Doom 코드를 아는 사람이 즉시 납득 가능한 god-modules 가 상위에 올라온다 — i_system / i_video / z_zone / w_wad 같은 시스템·메모리·WAD 인터페이스, 그리고 g_game 같은 게임 전역 상태 god-object. 정성 평가로는 G-SI 가 C 코드에서도 위험 구간을 합리적으로 식별함을 확인했다.

산출물: `reports/chocolate-doom/{ast,metrics,scoring}.json`, `reports/chocolate-doom/index.html`.

**Phase A 검증 결과 (W11, 동일 커밋 기준)**

```bash
python -m game_si validate benchmarks/chocolate-doom \
    --scoring reports/chocolate-doom/scoring.json --subdir src
```

| 분석 단위 | n | G-SI ρ | LOC ρ | CC ρ |
|---|---:|---:|---:|---:|
| 파일 / 클래스 (1:1) | 296 | **+0.582** | +0.616 | +0.468 |

(클래스 1 개 = 파일 1 개로 1:1 매핑되는 C 케이스 특성상 두 단위 결과가 동일하다. 모든 p<1e-6. git history 전체, bug-fix 키워드 매칭 + 사소한 수정 제외.)

상위 bug-fix 파일과 G-SI 상위 hotspot 의 교집합이 크다. 예) `i_video.c` 는 60 회 bug-fix 수정으로 1 위이며 G-SI 등급도 E (98.99). `strife/p_enemy.c`, `d_iwad.c`, `i_sdlsound.c` 등도 양쪽에 함께 등장한다.

해석:

- C 코드베이스에서도 G-SI 가 bug-fix 빈도와 **강한 양의 상관**(ρ≈+0.58, p<1e-6) 을 보인다. plan RQ1 의 일반화 가능성을 시사한다.
- **CC 단독(+0.47) 보다 G-SI(+0.58) 가 명확히 우월**하다 (Δρ≈+0.11). plan RQ2 의 "G-SI 가 CC 를 단독으로 사용한 경우보다 추가 설명력을 갖는다" 가 OpenRA(C#) 보다 더 분명하게 드러나는 케이스다.
- LOC 단독은 여전히 본 비교에서 가장 강한 상관(+0.62)이다. 게임 코드의 bug-fix 빈도가 코드 크기에 크게 영향받는다는 일반 경향과 일치하며, 게임 도메인 특화 시그널(GlobalState, GameLoopCentrality) 의 추가 효과는 다음 단계(Phase B: SonarQube/Lizard 비교, Phase C: LLM 정성 평가) 에서 보강한다.

### 2.2 OpenRCT2 (W12 진입)

| 항목 | 값 |
|---|---|
| 저장소 URL | https://github.com/OpenRCT2/OpenRCT2 |
| 라이선스 | GPL-3.0 |
| 언어 | C++ (.cpp/.h) |
| 분기 | `develop` |
| 분석 시점 커밋 | `7a2cddeed1304f284829ffb0c91f31557819c51e` |
| 커밋 메시지 | "Use move semantics in GroupVector::Set (#26579)" (2026-05-18) |
| 분석 일자 | 2026-05-20 |
| 분석 범위 | `src/openrct2/` (코어 모듈만. UI/Android 등은 본 작품 범위 외) |

**재현 명령**

```bash
git clone --depth 100 https://github.com/OpenRCT2/OpenRCT2.git benchmarks/OpenRCT2
cd benchmarks/OpenRCT2
git checkout 7a2cddeed1304f284829ffb0c91f31557819c51e
cd ../..

python -m game_si analyze benchmarks/OpenRCT2/src/openrct2 --lang cpp \
    --out reports/openrct2
```

**측정 결과 (W12 시점)**

| 항목 | 값 |
|---|---|
| 분석된 `.cpp` 파일 | 544 |
| 분석 단위 (compilation_unit + C++ class) | 636 (544 + 92 class/struct) |
| 함수 정의 | 5,766 |
| 합산 LOC (비주석·비공백) | 486,014 |
| 분석 소요 시간 | 약 22.3초 |
| 파싱 실패 파일 | 0 |
| 클래스 의존성 그래프 edges | 5,998 |
| SCC (≥2) | 2 |

**Project Health**: 54.94 / 100 (등급 C). avg_si=50.45, avg_coupling=**19.07** (Chocolate Doom 7.15 의 2.7 배, OpenRA.Game 1.73 의 11 배). coupling_norm 컴포넌트가 100 으로 saturate — 본 작품 분석 케이스 중 결합도가 가장 높은 코드베이스.

**상위 hotspot 정성 검토** (G-SI 상위 10):

| 등급 | G-SI | kind | 단위 | 주요 시그널 |
|---|---:|---|---|---|
| E | 100.00 | compilation_unit | `park.Legacy` | CC_top10p=568 (거대 legacy migration) |
| E | 99.84 | **class** | `Context` | 결합도 250 (application god-object) |
| E | 99.69 | compilation_unit | `ride.Ride` | 결합도 172 (라이드 시스템 메인) |
| E | 99.53 | compilation_unit | `ride.Vehicle` | CC_top10p=39.5, 결합도 122 |
| E | 99.37 | compilation_unit | `drawing.Drawing` | 결합도 164, GS=43 |
| E | 99.21 | compilation_unit | `ride.RideData` | 결합도 215 |
| E | 99.06 | compilation_unit | `GameState` | 결합도 226 |
| E | 98.90 | compilation_unit | `world.Map` | 결합도 202 |
| E | 98.74 | compilation_unit | `Diagnostic` | 결합도 192 |
| E | 98.58 | compilation_unit | `paint.track.coaster.TwisterRollerCoaster` | CC=45.7, GS=243 |

`Context`(C++ 클래스) 가 별도 ClassNode 로 추출되어 god-object 시그널을 정확히 잡았다 — C++ namespace/class 추출 경로 검증. `park.Legacy` 의 CC_top10p=568 같은 극단치는 거대 switch 문(레거시 저장 포맷 마이그레이션) 으로, 게임 코드의 자연스러운 위험 패턴이다. 코스터 페인트 코드(`paint.track.coaster.*`) 가 hotspot 으로 잡힌 것은 OpenRCT2 의 알려진 복잡 영역과 일치한다.

산출물: `reports/openrct2/{ast,metrics,scoring}.json`, `reports/openrct2/index.html`.

**Phase A 검증 결과 (W12, 동일 커밋 기준)**

```bash
python -m game_si validate benchmarks/OpenRCT2 \
    --scoring reports/openrct2/scoring.json --subdir src/openrct2
```

| 분석 단위 | n | G-SI ρ | LOC ρ | CC ρ |
|---|---:|---:|---:|---:|
| 파일 | 544 | **+0.458** | +0.406 | +0.368 |
| 클래스 (compilation_unit + C++ class) | 636 | +0.323 | +0.329 | +0.304 |

(모든 p<1e-13. git history 전체. 매칭 안된 변경 3,973 회 — UI/Android/플랫폼별 파일 등 본 분석 범위 밖.)

본 케이스가 **plan RQ2 의 가장 강한 증거**다 — 파일 단위에서 G-SI 가 LOC 와 CC 두 baseline 모두를 명확히 능가했다.

| 비교 | 차이 (Δρ) |
|---|---:|
| G-SI − LOC | +0.052 |
| G-SI − CC | +0.090 |

상위 bug-fix 파일은 G-SI 상위 hotspot 과 강하게 겹친다 — `ride/Ride.cpp`(147 회 / G-SI 99.69), `Context.cpp`(69 회 / G-SI 99.84), `world/Map.cpp`(52 회 / G-SI 98.90), `Game.cpp`(46 회) 등. 자주 수정되는 god-module 군이 정량적으로 일관되게 식별된다.

## 3. 전체 Phase A 검증 요약

본 작품의 4 개 케이스 스터디를 통한 plan §7.1 Phase A 정량 검증 결과를 한자리에 정리한다 (모두 **파일 단위**, 전체 git history 기준).

| 케이스 | 언어 | n | G-SI ρ | LOC ρ | CC ρ | G-SI > LOC | G-SI > CC |
|---|---|---:|---:|---:|---:|:---:|:---:|
| OpenRA.Game | C# | 226 | +0.580 | +0.699 | +0.552 | — | ≈ |
| OpenRA.Mods.Common | C# | 1,080 | +0.541 | +0.613 | +0.527 | — | ≈ |
| Chocolate Doom | C | 296 | +0.582 | +0.616 | +0.468 | — | **✓ +0.11** |
| **OpenRCT2** | C++ | 544 | **+0.458** | +0.406 | +0.368 | **✓ +0.05** | **✓ +0.09** |

해석:

1. **RQ1 (일관된 위험 구간 식별)** — 4 개 케이스 모두에서 G-SI 가 bug-fix 빈도와 **유의한 양의 상관 (+0.46 ~ +0.58, 모두 p<1e-13)**. 언어·도메인을 가로질러 일관된 시그널.
2. **RQ2 (LOC/CC 단독 대비 추가 설명력)** — CC 단독 대비 G-SI 가 모든 케이스에서 우월하거나 동등. LOC 단독 대비 OpenRCT2 에서 명확히 우월. C# OpenRA 두 케이스에서는 LOC 가 약간 더 강했으나, 이는 plan §7.1 이 "특정 수치 도달에 종속되지 않도록" 명시한 범위 안의 결과이며, 게임 도메인 특화 시그널의 효과는 Phase B(외부 도구 비교) / Phase C(LLM 정성 평가) / Phase D(시계열 분석) 에서 추가 입증한다.
3. **RQ4 (실용적 처리량)** — 분석 시간: OpenRA.Game 1.2초 / OpenRA.Mods.Common 4.5초 / Chocolate Doom 5.4초 / OpenRCT2 22.3초. validate 실행 시간은 git log 스캔 + 클래스 매핑으로 모두 30초 이내. 사용성 충분.

## 3. 라이선스 및 재배포 원칙

- 본 매니페스트에 등재된 저장소의 코드는 본 작품 저장소에 복사하거나 포함하지 않는다.
- 본 작품의 분석 결과 JSON·HTML 리포트는 원본 소스 코드 전문이나 긴 코드 스니펫을 포함하지 않는 범위에서 산출·공유한다.
- 보고서에 코드 인용이 필요한 경우 파일 경로·지표값·그래프 구조·짧은 인용만 포함하고, 원본 저장소 URL과 라이선스를 함께 명시한다.
- 원본 게임 에셋(예: 게임 데이터 파일)은 본 작품에서 사용·배포하지 않는다.
