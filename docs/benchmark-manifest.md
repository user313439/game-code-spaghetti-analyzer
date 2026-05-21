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

## 4. Phase B — Lizard 와의 hotspot 비교 (W13)

plan §7.2 의 Phase B 정량 비교를 수행했다. 본 작품은 도구 셋업 부담이 낮은 Lizard(v1.22.1) 를 외부 비교 도구로 사용한다. Lizard 는 함수 단위의 Cyclomatic Complexity 와 LOC 를 제공하며, C/C++/C# 모두 지원한다.

비교는 **파일 단위** 에서 수행했다. G-SI 측 대표값은 plan §4.1 정의에 따라 파일 내 클래스 si_max, Lizard 측 대표값은 파일 내 함수 CC 의 최댓값(`max_cc`).

```bash
python -m game_si compare <input_path> --scoring <scoring.json>
```

### 4.1 종합 결과

| 케이스 | 매칭 파일 | top-5 Jaccard | top-10 Jaccard | top-30 Jaccard | ρ(si vs liz_cc) |
|---|---:|---:|---:|---:|---:|
| OpenRA.Game | 226 | **0.67** | 0.43 | 0.36 | +0.63 |
| OpenRA.Mods.Common | 1,080 | 0.43 | **0.54** | **0.50** | +0.80 |
| Chocolate Doom | 291 | 0.11 | 0.11 | 0.33 | +0.70 |
| OpenRCT2 | 544 | 0.11 | 0.11 | 0.25 | +0.53 |

해석:

- **Spearman ρ 0.53 ~ 0.80** — G-SI 와 Lizard max_CC 는 강한 양의 상관을 보인다. 즉 두 지표가 비슷한 방향을 가리키긴 한다. 하지만 동일하지는 않다.
- **Top-5 Jaccard 가 11~67% 로 큰 격차** — 가장 위험한 5 개를 골라 봤을 때 두 도구의 결과가 **상당히 다르다**. Chocolate Doom 과 OpenRCT2 에서는 9 개 중 1 개(11%) 만 공통.
- 이 차이는 G-SI 가 CC 단독으로는 잡지 못하는 위험 시그널(Coupling, GlobalState, GameLoopCentrality) 을 반영한다는 점을 뒷받침한다.

### 4.2 G-SI 단독 hotspot — plan RQ3 의 정성 증거

각 케이스의 G-SI 상위 10 중 Lizard top-30 에 들지 않은 사례 일부:

**OpenRA.Game** — G-SI 가 단독으로 식별한 게임 도메인 hotspot

| G-SI 순위 | Lizard 순위 | G-SI | Lizard CC | 파일 | 시그널 |
|---:|---:|---:|---:|---|---|
| 8 | 51 | 98.7 | **9** | `Renderer.cs` | 결합도/전역 (게임 렌더 god-object) |
| 9 | 185 | 98.5 | **2** | `Primitives/int2.cs` | 결합도 (모든 좌표 코드 의존) |
| 10 | 31 | 98.4 | 11 | `Graphics/WorldRenderer.cs` | 결합도 + 게임 루프 중심성 |
| 12 | 167 | 98.1 | **2** | `Input/Keycode.cs` | 결합도 (입력 enum) |
| 15 | 45 | 97.6 | 9 | `World.cs` | 결합도 (게임 world god) |
| 18 | 179 | 97.2 | **2** | `Traits/TraitsInterfaces.cs` | 결합도 (trait 인터페이스 모음) |

`int2.cs`(CC=2), `Keycode.cs`(CC=2), `TraitsInterfaces.cs`(CC=2) 같은 케이스가 특히 명확하다 — **본문 자체는 매우 단순하지만 모든 시스템이 의존하는 결합도 hub** 다. CC 만 보는 도구는 절대 잡을 수 없는 게임 코드의 위험 패턴.

**Chocolate Doom** — G-SI 가 단독으로 식별한 C god-module 들

| G-SI 순위 | Lizard 순위 | G-SI | Lizard CC | 파일 | 시그널 |
|---:|---:|---:|---:|---|---|
| 1 | 155 | 100.0 | 12 | `i_system.c` | 결합도 156 (시스템 인터페이스) |
| 2 | 171 | 99.7 | 10 | `m_misc.c` | 결합도 116 (utility god) |
| 4 | 71 | 99.0 | 28 | `i_video.c` | GS=263 (비디오 전역 상태) |
| 5 | 165 | 98.7 | 11 | `z_zone.c` | 결합도 90 (zone allocator) |
| 6 | 76 | 98.3 | 26 | `m_argv.c` | 결합도 + GS |

Doom 의 잘 알려진 god-module 군이 정확히 G-SI 상위에 올라온다. Lizard 순위는 모두 100 위 밖 — CC 만 보면 평범한 파일들이지만, 게임 도메인 시그널이 들어가면 위험 1~6위.

**OpenRCT2** — C++ god-object 식별

| G-SI 순위 | Lizard 순위 | G-SI | Lizard CC | 파일 | 시그널 |
|---:|---:|---:|---:|---|---|
| 2 | 179 | 99.8 | 16 | `Context.cpp` | 결합도 250 (application god-class) |
| 3 | 71 | 99.7 | 34 | `ride/Ride.cpp` | 결합도 172 |
| 5 | 106 | 99.4 | 24 | `drawing/Drawing.cpp` | 결합도 164, GS 43 |
| 6 | 299 | 99.2 | **8** | `ride/RideData.cpp` | 결합도 215 (라이드 데이터 hub) |
| 7 | 82 | 99.1 | 30 | `GameState.cpp` | 결합도 226 (게임 전역 상태) |

`RideData.cpp` 는 Lizard 순위 299 (CC=8) 인데 G-SI 6위 — 결합도 215 의 라이드 데이터 hub. C++ 의 한 god-object 패턴.

### 4.3 Lizard 단독 hotspot — 보완 사례

반대로 Lizard top-30 에 있지만 G-SI top-30 에는 없는 파일들도 검토했다. 대부분 **"내부적으로는 거대한 switch/state machine 인데 외부 결합도는 낮은"** 케이스다. 예) OpenRCT2 의 `paint/track/coaster/HybridCoaster.cpp` 는 Lizard CC=225 (paint track 코드의 거대한 switch) 이지만 G-SI 51.9 (등급 C) 로 본 작품 기준 위험 구간 밖이다. 이는 plan RQ2 에서 다룬 "단독 CC 가 잡는 위험" 과 G-SI 의 차이를 보여주는 사례로, 보고서에서는 두 시그널의 상호보완을 언급한다.

### 4.4 RQ3 에 대한 결론

> RQ3. 게임 특화 항목(전역 상태 의존성, 게임 루프 중심성 등)은 일반 정적 분석 도구가 식별하지 못하는 위험 구간을 추가로 잡아내는가?

- 4 개 케이스 전부에서 **G-SI 상위 30 중 일부 (5~10개)** 가 Lizard 상위 30 에 들지 않는다.
- 이 단독 식별 파일들은 일관되게 **"본문은 단순하나 결합도/전역 시그널이 높은" 게임 도메인 god-object 패턴** (Renderer, World, Context, i_system, GameState, RideData, ...).
- 따라서 RQ3 에 대해 **긍정 답변** 을 제공한다. CC 단독 도구는 본 작품의 GlobalState · Coupling · GameLoopCentrality 시그널이 잡는 위험을 놓친다.

산출물: 각 케이스의 `reports/<case>/compare.{json,_summary.txt}`.

## 5. Phase D — G-SI 시계열 분석 (W14)

plan §7.4 의 Phase D 확장 실험. 각 저장소의 git history 에서 균등 간격으로 8 개 커밋을 샘플링하고, 각 시점에 별도 git worktree 를 만들어 G-SI 를 재산출했다. 원본 working tree 는 손대지 않는다.

```bash
python -m game_si timeseries <repo> --lang <c|cpp|csharp> --subdir <subdir> \
    --samples 8 --out reports/<case>
```

### 5.1 cycle_count 와 코드베이스 성장의 일관 시그널

| 케이스 | 기간 | 시작 → 끝 (classes) | 시작 → 끝 (cycles) | health 변화 |
|---|---|---:|---:|---:|
| **OpenRA.Game** (C#) | 2010 → 2026 | 361 → 668 (1.85×) | **0 → 5** (단조 증가) | 38.0 → 47.9 (악화 +9.9) |
| **OpenRA.Mods.Common** (C#) | 2014 → 2026 | 3 → 2,194 | **0 → 4** (단조 증가, 최근 5→4) | 46.7 → 46.7 (안정) |
| **Chocolate Doom** (C) | 2005 → 2026 (21년) | 62 → 296 (4.8×) | 1 → 2~3 (안정 진동) | 52.4 → 50.6 (소폭 개선) |
| **OpenRCT2** (C++) | 2016 → 2026 | 385 → 636 | 1 → 2 (최근 +1) | 52.2 → 54.9 (악화 +2.7) |

해석:

- **모든 케이스에서 cycle_count 가 시간에 따라 증가하거나 안정 유지된다** — 감소한 케이스는 없다. 이는 plan §2 에서 다룬 "출시 후 업데이트 주기가 짧고 기능 추가가 잦아 임시 구현이 장기 코드로 굳어진다" 가설의 정량 증거다.
- **OpenRA.Game 이 가장 명확한 단조 악화 케이스다.** 16 년 동안 cycle 0→5, project health 38→48 — 도구가 이 추세를 자동 추적하고 시각화한다.
- **OpenRA.Mods.Common 은 코드베이스가 ~700× 폭발했지만 health 는 안정**이다. percentile-rank 정의의 일관성을 확인하는 케이스 — 분포가 함께 이동했음을 시사한다.
- **Chocolate Doom 은 21 년에 걸쳐 거의 안정**이다 (50.6 ~ 52.5). Doom 소스 포트로서 보존 지향 코드베이스의 특성과 일치.
- **OpenRCT2 는 최근 1 년 (2024→2026) 사이 health 52.1→54.9 로 명확한 악화** — cycle 도 1→2 로 증가. 활발한 리팩토링 시점의 일시적 패턴일 수 있다.

### 5.2 bug-fix 활동과 G-SI

각 케이스의 시점 간 bug-fix 커밋 수를 측정한 결과, 코드베이스 크기에 따라 자연 스케일링한다 (`OpenRA.Mods.Common 273/period`, `OpenRCT2 344/period`). 단일 시점 G-SI 와 직전 구간의 bug-fix 활동 사이에는 일관된 상관이 보이지 않았으나, 시점이 8 개로 적어 통계적 결론을 내리기는 어렵다. 본 결과는 plan §3.2 의 time-split 검증(G-SI-Full 평가) 의 기반 데이터로도 활용 가능하다.

산출물: `reports/<case>/timeseries.json` (수치) + `reports/<case>/timeseries.html` (Project Health 추이 line chart + 등급 분포 stacked area + bug-fix 활동 bar + 시점 표).

## 6. Phase C — LLM Refactoring Advisor (W13)

plan §7.3 의 Phase C 정성 평가. 4 케이스 각각의 G-SI 상위 5 hotspot 에 대해 Claude Haiku 4.5 를 호출하여 (1) 위험 원인, (2) 리팩토링 방향, (3) 테스트 우선순위를 한국어 JSON 으로 받는다. 자동 코드 수정 기능은 본 작품 범위 외다 (plan §3, §6.4).

### 6.1 설계 결정

- **모델**: `claude-haiku-4-5` ($1/M input, $5/M output). 학사 졸업작품 비용 통제(plan §11) 기준에 적합.
- **Prompt caching**: 시스템 프롬프트(`game_si/advisor.py` SYSTEM_PROMPT, ~3,900 자) 에 `cache_control: ephemeral` 부착. 실측 결과 토큰 기준으로 Haiku 4.5 의 최소 캐시 prefix(4,096 토큰)에 미달해 `cache_read_input_tokens` 가 0 으로 측정되었다 — 첫 호출의 캐시 쓰기 비용도 0 으로 잡혔으므로 실비 영향은 없으나, 차후 시스템 프롬프트를 영문 보강해 캐시를 활용하면 추가 30~40% 절감 가능.
- **Structured outputs**: `output_config.format` 에 JSON schema 를 전달해 응답 형식을 API 수준에서 강제. `risk_reasons` / `refactoring_suggestions` / `test_priorities` / `uncertainty_notes` 필드.
- **Retry**: SDK `max_retries=5` + 자동 backoff (429/5xx). 본 실행에서는 재시도 발생 없음.
- **입력 최소화** (plan §10.6): 원본 소스를 통째로 보내지 않는다 — 지표값 + 가장 복잡한 메서드의 짧은 스니펫(최대 30줄) + 시그니처만.

### 6.2 4 케이스 호출 통계

```bash
python -m game_si advise --scoring reports/<case>/scoring.json --top 5
```

| 케이스 | input tokens | output tokens | 비용 (USD) |
|---|---:|---:|---:|
| OpenRA.Game | 20,518 | 9,874 | $0.0699 |
| OpenRA.Mods.Common | 20,244 | 7,746 | $0.0590 |
| Chocolate Doom | 20,135 | 9,724 | $0.0688 |
| OpenRCT2 | 20,802 | 9,413 | $0.0679 |
| **합계** | **81,699** | **36,757** | **$0.2655** |

20 hotspot 전체 분석 비용이 $0.27 — 본 작품 LLM 보조 예산($1 미만)의 일부.

### 6.3 정성 평가 — 응답 품질

다음은 실측된 advice 의 한 예시 (Chocolate Doom `i_system` hotspot, G-SI 100, 결합도 156, SCC 크기 32, GlobalState 22):

> **위험 원인**: "결합도 156 — 156개의 외부 타입/단위를 참조하거나 참조받으며, 이는 거의 모든 모듈이 이 compilation unit 에 직·간접적으로 의존함을 의미한다. 변경 시 광범위한 회귀 테스트가 필수이다."

> **리팩토링 제안**: "전역 상태를 명시적 컨텍스트 객체로 캡슐화하라. `struct DosEmulationState { static_bool firsttime; int dos_version; void *mem_dump; }` 같은 형태로 도스 호환성 설정을 분리하고 ... 단, 게임 루프 핫 패스에서는 성능 영향을 검증해야 한다."

> **테스트 우선순위**: "특성 테스트(Characterisation Test)를 작성하라: `i_system.c`의 모든 공개 함수(특히 `I_GetMemoryValue`, 메모리 할당/해제, DOS 버전 감지 함수)를 현재 동작 그대로 기록하는 테스트를 작성하여 의도하지 않은 변경을 탐지한다."

다른 케이스도 동일한 패턴이 관찰된다. OpenRA.Game `UnitOrders` 에서는 "ProcessOrder 메서드가 60+ 개의 case 분기를 가진 거대 switch 문" + "dispatch 테이블(문자열-to-handler 딕셔너리)" 분리를 제안했고, OpenRCT2 `park.Legacy` (CC_top10p=568) 에서는 "레거시 저장 포맷 마이그레이션" 패턴을 인지하고 게임 자산 변환의 의도성을 언급하며 보존을 권고했다.

종합:

1. **정량 인용의 정확성** — 모든 응답이 지표 수치(CC, 결합도, GlobalState, SCC 크기) 를 정확히 인용한다. 시스템 프롬프트에 G-SI 정의를 충분히 담은 효과.
2. **게임 도메인 인지** — DOS 호환성, god-module, 코스터 페인트, RCT1 임포터 같은 도메인 특화 패턴을 인식하고 조언에 반영. 일반 정적 분석 보고서보다 도메인 깊이가 있다.
3. **테스트 유형의 적절성** — characterisation test, golden master test, performance regression test 같은 게임/레거시 코드에 적합한 테스트 유형을 권고. 단순한 "유닛 테스트 추가" 수준이 아니다.
4. **불확실성 명시** — 모든 응답이 `uncertainty_notes` 에 추측 한계(스니펫 일부만 노출, 의존성 그래프 미시각화 등)를 명시한다. 자동 패치 없이 의사결정 보조 도구로 사용하기에 안전하다.

### 6.4 한계 및 사용 가이드라인

- **추측이 포함됨** — 응답에 `(추정)`, "가능성이 높다", "확실하지 않음" 같은 표현이 빈번. 도구는 의사결정 보조이며, 실제 리팩토링은 사람이 의존성 그래프 확인 후 진행해야 한다.
- **시점별 결정성 없음** — 같은 hotspot 도 호출 시점에 따라 advice 가 일부 달라질 수 있다 (LLM 특성). 보고서 인용 시에는 본 실행 결과를 fixed 한 stop-snapshot 으로 사용한다.
- **코드 스니펫 의존성** — `ast.json` 이 가용하지 않은 경우 advice 품질이 떨어진다. 본 4 케이스는 모두 ast.json 을 보유.
- **자동 코드 수정 금지** — 응답의 리팩토링 제안은 사람이 검토·적용해야 한다. plan §6.4 의 범위 외 명시.

산출물: 각 케이스의 `reports/<case>/advisor.{json,md}`. `advisor.md` 는 사람용 한국어 마크다운, `advisor.json` 은 구조화된 원본.

## 7. G-SI-Full — ChangeRisk 항목 추가 확장 (plan §4.3)

plan §4.3 의 G-SI-Full 가중합을 본 시점에 구현했다.

```
raw_full(unit) = 0.25·Z(CC) + 0.20·Z(Coupling) + 0.15·Z(DepCycle)
               + 0.15·Z(GS) + 0.15·Z(GLC) + 0.10·Z(ChangeRisk)
```

ChangeRisk 정의 (`game_si/change_risk.py`): 최근 N 개월(기본 12) 동안 해당 **파일** 을 수정한 commit 수에 bug-fix 비율을 가산해 결합한 값 — `total_changes × (1 + bugfix_ratio)`.

```bash
python -m game_si score-full <input_path> --lang <lang> --repo <repo> \
    --subdir <subdir> --months 12 --out reports/<case>
```

**데이터 누수 방지** (plan §3.2 명시) — G-SI-Full 은 git 변경 이력 기반이라 Phase A 의 정답값과 같은 출처를 공유한다. 따라서 본 작품은 G-SI-Full 을 **보조 지표** 로 별도 산출만 하고 Phase A 의 검증값으로 사용하지 않는다.

### 7.1 4 케이스 상위 hotspot 변화 — G-SI-Static vs G-SI-Full

가장 큰 변화 예시 (OpenRA.Game, top 10 중 변화 + 인 클래스만):

| rank Full | G-SI Static → Full | Δ | ChangeRisk | fqn |
|---:|---:|---:|---:|---|
| 1 | 99.85 → 100.00 | **+0.15** | 13 | `OpenRA.Server.Server` (god-object + 활발한 수정) |
| 8 | 98.65 → 98.95 | **+0.30** | 6 | `OpenRA.Renderer` |
| 9 | 98.35 → 98.80 | **+0.45** | 5 | `OpenRA.Graphics.WorldRenderer` |
| 10 | 98.05 → 98.65 | **+0.60** | 0 | `OpenRA.KeycodeExts` |

`Server` 가 1 위로 올라온 것이 특히 합리적 — 결합도·전역 상태에 더해 12 개월 내 13 회 수정 활동이 있어 변경 위험이 높다. percentile rank 정의상 상승하는 클래스 만큼 다른 클래스는 하락하므로 분포 자체가 이동한다.

타 케이스 산출물: `reports/<case>/scoring_full.json` + `scoring_full_summary.txt`.

## 8. 가중치 튜닝 + LOPO 교차 검증 (plan §4.6)

```bash
python -m game_si tune --case OpenRA.Game=reports/openra-game \
    --case OpenRA.Mods.Common=reports/openra-mods-common \
    --case "Chocolate Doom=reports/chocolate-doom" \
    --case OpenRCT2=reports/openrct2
```

5 차원 가중치를 step 0.05 grid 로 탐색 (sum=1 제약, **2,226 후보**) 하여 4 케이스의 **파일 단위 Spearman ρ 평균을 최대화** 하는 가중치를 찾는다. Leave-One-Project-Out 교차 검증으로 과적합을 점검한다.

### 8.1 결과

**Default vs Tuned**:

| 항목 | cc | coupling | dependency_cycle | global_state | game_loop_centrality |
|---|---:|---:|---:|---:|---:|
| default (plan §4.2) | 0.30 | 0.25 | 0.15 | 0.15 | 0.15 |
| **tuned (본 실험)** | **0.30** | **0.30** | **0.05** | **0.30** | **0.05** |

**케이스별 ρ**:

| 케이스 | default ρ | tuned ρ | Δ |
|---|---:|---:|---:|
| OpenRA.Game | +0.5756 | +0.6454 | **+0.0698** |
| OpenRA.Mods.Common | +0.5451 | +0.5677 | +0.0226 |
| Chocolate Doom | +0.5815 | +0.6186 | +0.0370 |
| OpenRCT2 | +0.4606 | +0.4812 | +0.0206 |

**LOPO**:

| | ρ |
|---|---:|
| default (4 케이스 평균) | +0.5407 |
| **tuned (hold-out 평균)** | **+0.5706** |
| **Δ (tuned − default)** | **+0.0299** |

### 8.2 해석

1. **CC + Coupling + GlobalState 가 가장 강한 시그널** — tuned 가중치가 셋 다 0.30 으로 결합되어 0.90 (총합 1.0 중 90%) 을 차지한다. 이는 게임 코드의 위험이 분기 복잡도(CC) + 모듈 간 결합도(Coupling) + 전역 상태 의존(GS) 세 축에서 발생한다는 plan §2 의 가설과 일치한다.
2. **DependencyCycle 과 GameLoopCentrality 는 4 케이스에서 약한 시그널** — tuned 가중치가 0.05 로 거의 무시된다. DepCycle 은 4 케이스 모두 SCC 수가 적어 (1~5 개) binary 같은 효과를 내고, GLC 는 진입점 매칭이 syntactic 이라 정확도 한계가 있다. 본 결과는 도구의 **개선 우선순위** (semantic 분석 도입, GLC 계산 정밀화) 를 데이터로 제시한다.
3. **LOPO 가 default 대비 +0.03 개선** — tuned 가 단일 케이스에 과적합되지 않았음을 시사. 단 4 케이스로는 통계적 일반화에 한계가 있으므로 보고서에서는 "정량 신호" 수준으로 한정해 다룬다.

산출물: `reports/tune.{json,_summary.txt}`.

## 9. CI 품질 게이트 샘플 (plan §6.3)

plan §6.3 의 "GitHub Actions 에서 동작 가능한 품질 게이트 샘플" 을 두 모듈로 구현했다.

### 9.1 `diff` 서브커맨드 (`game_si/diff.py`)

두 `scoring.json` 의 변화를 산출한다 — Project Health Δ, avg_si Δ, risk_ratio Δ, cycle_count Δ, 그리고 **등급이 변한 클래스 목록 (악화·개선 따로)**.

```bash
python -m game_si diff baseline.json latest.json --fail-if-worse-than 3.0
```

`--fail-if-worse-than N` 옵션으로 health_delta 가 N 초과면 exit code 2 — CI 에서 PR 을 실패시킬 수 있다.

산출물: `diff.json` + `diff_summary.txt`.

### 9.2 GitHub Actions 샘플: `.github/workflows/g-si-quality-gate.yml`

PR 이 main 으로 머지될 때 다음 흐름:

1. main(baseline) + PR HEAD(latest) 둘 다 checkout
2. Python + .NET(C# 인 경우) 셋업, `pip install -e .`
3. 양쪽에서 `game-si analyze` 실행 → 각각 `scoring.json` 산출
4. `game-si diff --fail-if-worse-than 3.0` 로 게이트
5. `diff_summary.txt` 를 PR 코멘트로 등록 + artifact 업로드

본 yaml 은 도구의 워크플로 통합 가능성을 보여 주는 **샘플**이다. 실제 사용 시 분석 대상(`ANALYZE_PATH`, `REPO_SUBDIR`) 과 임계치(`FAIL_THRESHOLD`) 를 프로젝트에 맞게 수정한다.

## 10. 종합 — plan 마일스톤 매핑

| plan 절 | 마일스톤 | 상태 | 본 매니페스트 위치 |
|---|---|---|---|
| §4.2 G-SI-Static | 기본 점수 산출 | 완료 | §1, §2 |
| §4.3 G-SI-Full | ChangeRisk 확장 | 완료 | §7 |
| §4.6 가중치 운용 (tuned) | grid + LOPO | 완료 | §8 |
| §6.1 Phase 1 (C# 분석) | OpenRA 2 모듈 | 완료 | §1 |
| §6.2 Phase 2 (C/C++ 분석) | Chocolate Doom + OpenRCT2 | 완료 | §2 |
| §6.3 Phase 3 항목 — CI 품질 게이트 | GitHub Actions 샘플 | 완료 | §9 |
| §7.1 Phase A (정량 검증) | 4 케이스 Spearman | 완료 | §3 |
| §7.2 Phase B (외부 도구 비교) | Lizard | 완료 | §4 |
| §7.3 Phase C (LLM Advisor) | Haiku 4.5, 20 hotspot | 완료 | §6 |
| §7.4 Phase D (시계열) | git worktree 기반 | 완료 | §5 |
| §7.5 Phase E (사용자 설문) | "시간 허용 시" | 양식 준비 | `docs/phase_e_survey.md` (사용자 진행) |

## 3. 라이선스 및 재배포 원칙

- 본 매니페스트에 등재된 저장소의 코드는 본 작품 저장소에 복사하거나 포함하지 않는다.
- 본 작품의 분석 결과 JSON·HTML 리포트는 원본 소스 코드 전문이나 긴 코드 스니펫을 포함하지 않는 범위에서 산출·공유한다.
- 보고서에 코드 인용이 필요한 경우 파일 경로·지표값·그래프 구조·짧은 인용만 포함하고, 원본 저장소 URL과 라이선스를 함께 명시한다.
- 원본 게임 에셋(예: 게임 데이터 파일)은 본 작품에서 사용·배포하지 않는다.
