# OpenRCT2 — LLM 리팩토링 가이드 (Phase C)

- 모델: `claude-haiku-4-5`
- 토큰 사용: input=22,202 output=10,426 cache_write=0 cache_read=0 (cache hit ≈ 0.0%)
- 예상 비용: **$0.0743** USD

## 1. [E] G-SI 100.0 — `park.Legacy`
`park/Legacy.cpp` · CC=568.0  CP=24  GS=7  GLC=0.0

**위험 원인**
- Cyclomatic Complexity 568.0 — 단일 compilation_unit 내 제어 흐름이 극도로 복잡. 제시된 TrackTypeMustBeMadeInvisible 메서드만 해도 수십 개의 if/else 와 switch case 가 중첩되어 있으며, 파일 전체 CC 평균은 게임 코드 일반 수준의 10배 이상. 코드 이해 및 변경 시 버그 유입 위험이 매우 높다.
- DependencyCycle 275 — 순환 의존성 그래프 멤버이면서 SCC 크기가 275개로 매우 큼. park.Legacy 는 ObjectRepository, ParkFileImporter, S4Importer 등 12개 클래스에 의존되고 동시에 ride.Ride, object.ObjectList, rct1/rct2 모듈 등 12개를 참조하며, 이 모두가 상호 순환 구조를 형성. 레거시 파일 포맷 마이그레이션 코드의 중심이 되어 있어 변경 영향 추적이 거의 불가능.
- 게임 자산 호환성 레이어로 설계된 god-module — 로그 플룸, 기가 코스터, 기타 탈것 타입별 legacy track element 변환 로직이 모두 이 파일에 집중. 정적 지형, 트랙 엘리먼트, 탈것 타입 등 도메인 전역 개념에 대한 암묵적 계약(contract)이 하드코딩되어 있어, 새 탈것 타입 추가 시마다 이 파일을 수정해야 한다.

**리팩토링 제안**
- TrackTypeMustBeMadeInvisible 를 ride 타입별 lookup table (map/dictionary) 로 변환. 현재 중첩 if/switch 구조 대신 (rideType, parkFileVersion) → {trackType 컬렉션} 형태의 데이터 테이블을 외부 configuration 또는 상수로 정의하고, loop 기반 조회로 단순화. 이렇게 하면 CC 를 수십 단계 낮출 수 있고, 새 탈것 타입 추가 시 코드 수정 대신 데이터만 확장하면 된다.
- park.Legacy 내 대규모 메서드들을 ride 타입 또는 마이그레이션 시대(version era) 단위로 분해한 작은 객체(converter 클래스)들로 추출. 예: LegacyLogFlumeConverter, LegacyGigaCoasterConverter 같은 전용 클래스를 만들고 각각이 구체적 버전 범위와 타입 매핑만 담당하도록 분리. 이는 순환 의존성을 끊고 각 converter 를 독립적으로 테스트 가능하게 만든다.
- ObjectRepository, ParkFileImporter, S4Importer 등 의존자(fan-in)와의 인터페이스를 명시적 adapter 계층으로 추상화. 현재 모든 클래스가 park.Legacy 의 구체적 함수들을 직접 호출하므로, 변환 인터페이스(ILegacyTrackConverter, ILegacyPeepConverter) 를 선언하고 구현을 분리하면 fan-in 을 줄이고 SCC 크기를 감소시킬 수 있다.
- 게임 루프 영향 평가: GameLoopCentrality 0.0 이므로 이 모듈은 런타임 Tick/Update/Render 호출 체인 밖이고, 파일 로드/저장 초기 단계에만 사용된다. 따라서 리팩토링은 frameRate 성능에는 거의 영향을 주지 않으나, 게임 시작(park load) 지연 및 메모리 할당 패턴을 모니터링해야 한다.

**테스트 우선순위**
- Golden master / characterisation test for legacy format migration: rct1, rct2, s4 포맷의 알려진 공개 파크 파일 여러 개를 로드 → 변환 → 저장 후, 결과 속성(탑승인원, 트랙 요소 위치, 조경 객체)이 변경 전후 동일함을 비교하는 회귀 테스트를 우선 작성. 이는 park.Legacy 변경의 모든 버그를 catch 할 수 있는 가장 저렴한 수단.
- Ride type 별 track element conversion table 의 exhaustiveness test: 모든 ride 타입 × 모든 track type × 모든 지원 버전의 조합에 대해 TrackTypeMustBeMadeInvisible 및 유사 함수들의 출력이 정의되어 있는지 확인. Coverage 빈틈이 있으면 사용자가 레거시 파크 로드 시 assertion 또는 silent data loss 를 경험할 수 있다.
- Integration test for dependency cycle 상의 인접 호출자들(ObjectRepository, S4Importer): 각 importer 가 park.Legacy 의 변환 함수를 호출하고 결과를 ObjectManager 에 삽입할 때, object 생성 순서 및 FK 참조 무결성이 보장되는지 테스트. 순환 의존성 때문에 변경 영향이 쉽게 멀리까지 전파되므로, 각 importer 별로 작은 파크 데이터셋을 고정해 놓고 매번 검증해야 한다.

_불확실성: 제시된 스니펫은 TrackTypeMustBeMadeInvisible 일부만 보여주므로, 파일 내 다른 메서드들의 구체적 CC 분포와 각 메서드가 얼마나 많은 track type / ride type 조합을 다루는지 정확히 파악하기 어렵다. 또한 DependencyCycle 275 는 매우 큰 숫자인데, 이것이 park.Legacy 자신이 직접 순환 참조를 만드는지, 아니면 외부 모듈(ride, object, rct1/rct2)의 거대 순환 구조에 park.Legacy 가 포함된 건지 명확하지 않다. 전자라면 park.Legacy 내부 리팩토링만으로 SCC 크기를 줄일 수 있으나, 후자라면 더 광범위한 모듈 간 의존성 재설계가 필요할 수 있다. 상세한 의존성 그래프 또는 SCC 멤버 리스트가 있으면 더 정확한 우선순위를 정할 수 있을 것으로 예상된다._

## 2. [E] G-SI 99.8 — `Context`
`Context.cpp` · CC=13.6667  CP=250  GS=0  GLC=1.0

**위험 원인**
- 결합도 250 — 202개 클래스가 이 Context를 직접 참조하며, 거의 모든 게임 액션(action.*)과 엔티티 시스템이 의존하는 god-object 구조다. 이는 OpenRCT2의 역사적 아키텍처(중앙 집중식 상태 관리)에서 비롯되었으나, 변경 시 전체 게임 시스템의 회귀 테스트가 필수적이다.
- 게임 루프 중심성 1.0 — LoadParkFromStream, Update, Tick 같은 주요 진입점에서 직접 호출되므로, 이 클래스의 수정은 매 프레임 실행되는 핫 패스에 영향을 준다. 특히 메모리 할당, 파일 I/O 폴백 로직, 예외 처리가 포함된 복잡한 메서드들이 게임 루프 경로상에 있다.
- 순환 의존성 275 — 이 클래스가 속한 SCC(Strongly Connected Component) 규모가 275다. 이는 Context와 그 의존 클래스들(ParkImporter, ObjectManager, RCT2, TrackDesignRepository 등)이 서로를 참조하는 순환 고리를 형성함을 의미한다. 이로 인해 단위 테스트 격리가 어렵고, 모의 객체(mock) 생성도 복잡해진다.
- 메서드 복잡도 고평균 (CC 13.67) — 코드 스니펫의 LoadParkFromStream 메서드는 조건분기(if/else if), 파일 타입 분류, 여러 IParkImporter 전략 선택, 예외 처리를 다루고 있으며, 보이지 않은 부분(lines 788-999)까지 포함하면 200+ 라인의 거대 함수로 추정된다. 이는 파크 로드 성공/실패 경로가 교착되어 있음을 시사한다.

**리팩토링 제안**
- 파크 파일 분류 및 로드 전략을 Strategy 패턴으로 분리하라. TryClassifyFile 과정을 독립적인 FileTypeResolver 클래스로 추출하고, FileType별 IParkImporter 팩토리를 별도 팩토리 클래스로 구성하면, LoadParkFromStream의 분기 로직을 감소시키고 테스트 용이성을 높일 수 있다. 이 변경은 Context의 다른 부분(게임 루프 업데이트)에 영향을 주지 않는다.
- 202개 의존 클래스를 다루는 god-object 구조를 점진적으로 분해하기 위해, 먼저 'action 시스템'과 '게임 상태'를 분리한 GameState 인터페이스를 도입하라. 현재 Context는 액션 처리, 맵 관리, 엔티티 참조를 모두 담당하는데, 이들을 각각 ActionDispatcher, MapManager, EntityRepository로 위임하면, 개별 액션 클래스는 이들 작은 인터페이스를 참조하게 된다. 변경은 action 계층부터 시작하되, 게임 루프 핫 패스(Update/Tick)는 후순위로 미룬다.
- 순환 의존성을 끊기 위해 Context → RCT2 → ObjectManager 같은 의존성 체인에서 중간 계층(adapters)을 삽입하라. 예를 들어 RCT2 레거시 형식 파싱을 LegacyFormatHandler 어댑터로 래핑하면, Context와 RCT2 간 직접 순환 참조를 제거할 수 있다. 다만 이 변경은 파크 로드(게임 시작 시점)에만 영향을 주므로, 런타임 성능 우려는 낮다.

**테스트 우선순위**
- 특성화 테스트(Characterisation Test) — 현재 LoadParkFromStream의 모든 분기(park file, S4 save, S6 save, invalid type, 예외 경로)를 입력 파일별로 수집하여 golden master로 기록하라. 리팩토링 후 동일 입력에 대해 동일 출력(또는 메모리 구조)을 재현하는지 검증하면, 세부 구현 변경을 안전하게 격리할 수 있다.
- Context 의존 클래스들(주요 action 10~20개)에 대한 통합 테스트 강화 — LoadParkFromStream 후 특정 action(FootpathPlaceAction, MapChangeSizeAction 등)이 올바르게 작동하는지 확인하라. 이는 god-object 구조에서 의존성 주입이나 팩토리 변경 후 암묵적 회귀를 잡는 데 효과적이다.
- 게임 루프 성능 회귀 테스트 — LoadParkFromStream 이후 10프레임간 Update/Render 호출 시간을 측정하여 기준선(baseline)을 설정하라. 리팩토링(특히 ParkImporter 전략 분리, adapters 추가)이 호출 체인 길이나 메모리 할당을 변경할 수 있으므로, fps 저하 감시가 필수다.
- 순환 의존성 감지 테스트 — 리팩토링 후 의존성 그래프에서 Context-to-RCT2-to-ObjectManager 같은 주요 순환 경로가 제거되었는지 정적 분석으로 재검증하라. 또한 Context 생성 시 모의 객체(mocks)만으로 초기화 가능한지 테스트하면, 실제 격리 개선을 신속히 확인할 수 있다.

_불확실성: 코드 스니펫이 truncated 되어 LoadParkFromStream의 전체 제어흐름(특히 788-999 범위)을 파악할 수 없다. CC 13.67은 top-10% 평균값이므로 개별 메서드가 훨씬 더 복잡할 수 있으며, 예외 처리 깊이나 중첩된 try-catch, 파일 I/O 재시도 로직 등이 추가되면 실제 CC는 40~60에 달할 수도 있다. 또한 DependencyCycle 275는 SCC 크기로 해석했으나, 이것이 Context를 포함한 전체 SCC 규모인지 Context 관련 부분집합인지 명확하지 않다. 순환 의존성 끊기의 우선순위는 전체 의존성 그래프 시각화 후 재검토가 필요하다. 마지막으로 OpenRCT2의 실제 게임 루프 구조(멀티스레드 여부, 비동기 로드 지원)가 알려지지 않아, 성능 영향 범위의 예측 신뢰도가 중간 수준이다._

## 3. [E] G-SI 99.7 — `ride.Ride`
`ride/Ride.cpp` · CC=18.7778  CP=172  GS=9  GLC=1.0

**위험 원인**
- 결합도 172 — 129개 클래스가 이 compilation unit을 직접 참조하며, 43개의 외부 클래스에 의존하는 god-object 패턴. 모든 ride 관련 액션(RideCreateAction, RideDemolishAction, RideSetAppearanceAction 등)이 이 단위에 의존하므로, 인터페이스 또는 필드 변경이 프로젝트 전체에 파급된다.
- 게임 루프 중심성 1.0 — Ride::Tick/Update 메서드가 game loop entry point이며, 매 프레임마다 실행되는 핫 패스. 여기서의 성능 저하나 예외는 fps에 직접 영향을 미친다.
- 순환 의존성 SCC 크기 275 — 이 단위가 포함된 strongly connected component이 275개 노드로 매우 크다. ride 도메인 전체가 순환 결합되어 있음을 의미하며, 리팩토링 시 변경 영향 범위를 정확히 파악하기 어렵다.
- Cyclomatic Complexity 평균 18.78 (상위 10%) — updateMaxVehicles 코드 스니펫에서 보이는 다중 if-else, for 루프, ternary 연산 등이 복합적으로 얽혀 있다. 4964 LOC 규모의 파일에서 메서드 복잡도가 높으면 로직 변경 시 회귀 위험이 커진다.

**리팩토링 제안**
- Ride 클래스를 역할별 파사드로 분해하되, 게임 루프 의존성을 먼저 분리한다. 예: RidePhysicsCalculator(updateMaxVehicles 같은 공학 계산), RideStateManager(상태 전이), RideAudioVisuals(음향/시각 효과) 등으로 추출하되, 초기에는 Ride 내 delegate로 두어 호출 경로는 변경하지 않는 방식으로 진행한다. 이를 통해 game loop entry point는 유지하면서 내부 결합을 낮춘다.
- 외부에서 Ride를 참조하는 129개 클래스들이 ride의 어느 필드/메서드에 접근하는지 매핑하고, 공통 쿼리 인터페이스(읽기 전용: getRideStats, getRidePassengerInfo, getRideStatus 등)로 추상화한다. 이를 통해 액션 클래스들이 Ride의 내부 구현이 아닌 계약에 의존하도록 전환한다.
- 전역 상태 접근(GlobalState=9) 중 static reference의 출처를 추적한다. ObjectManager, RideManager, Scenario 같은 singleton/static 참조가 정말 필요한지, 아니면 생성자 또는 메서드 인자로 명시적 전달이 가능한지 검토한다. 특히 게임 루프 핫 패스에 있는 메서드(Tick/Update)에서는 불필요한 singleton lookup을 제거하면 성능상 이득이 있을 수 있다.
- updateMaxVehicles 같은 복합 계산 로직을 순수 함수로 추출한다(입력: rideEntry, stationNumTiles, 기존 파라미터들 → 출력: newNumCarsPerTrain, maxNumCarsPerTrain). 이렇게 하면 로직을 독립적으로 테스트·검증할 수 있고, 나중에 SIMD 최적화나 병렬 계산으로 확장할 때도 도움이 된다.

**테스트 우선순위**
- Characterisation test: 현재 Ride 클래스의 주요 public 메서드(updateMaxVehicles, tick, setName 등)에 대해 다양한 입력(다른 ride 타입, 역(station) 길이 조건, 객체 미존재 등)에서의 output을 golden snapshot으로 기록한다. 이후 리팩토링 중 이 snapshot과의 차이를 점검하여 의도하지 않은 로직 변경을 조기 탐지한다.
- Performance regression test: 게임 루프 entry point인 Ride::Tick을 100프레임 이상 반복 실행하고, 실행 시간 및 메모리 할당(GC pressure)을 측정한다. 리팩토링(특히 delegate pattern 도입, 인터페이스 추상화) 후에도 같은 성능 기준을 만족하는지 확인한다.
- Dependency injection feasibility test: 현재 코드에서 ObjectManager, RideManager 등 singleton 참조를 constructor parameter로 주입받도록 한 임시 오버로드를 작성하고, 이것이 game loop 호출 경로에서 성능 저하를 일으키는지 측정한다. 불가피한 경우 lazy initialization이나 thread-local caching 같은 대안을 시범한다.
- Circular dependency resolution test: SCC size 275인 순환 참조를 단계적으로 끊으면서, 각 단계마다 컴파일·링크 시간과 runtime behavior가 변하지 않음을 확인한다. 예: ride.Vehicle 의존성을 분리할 때, Vehicle이 여전히 Ride를 역참조하는지, 아니면 추상 인터페이스로 대체 가능한지 먼저 조사한다.

_불확실성: 코드 스니펫이 updateMaxVehicles의 일부만 제공되어, 전체 메서드의 모든 분기와 exit point를 파악하기 어렵다. 특히 for 루프와 그 내부 조건들이 정확히 몇 개의 경로를 만드는지 불명확하다. 또한 4964 LOC 파일 전체의 메서드 분포(최대 CC, 평균 CC, 메서드 개수)를 알 수 없어, updateMaxVehicles가 대표적 복잡 메서드인지 아니면 예외인지 판단할 수 없다. 의존성 그래프의 129개 fan-in 클래스 중 몇 개가 실제로 game loop 중에 Ride를 호출하는지, 즉 몇 개가 'hot path' 에 있는지도 불명확하며, 이에 따라 리팩토링 우선순위(인터페이스 분리 vs. 상태 추출 vs. 성능 보정)가 달라질 수 있다._

## 4. [E] G-SI 99.5 — `ride.Vehicle`
`ride/Vehicle.cpp` · CC=39.5  CP=122  GS=8  GLC=1.0

**위험 원인**
- 결합도 122 (fan-out 35개, fan-in 87개) — 게임 내 대부분의 엔티티, 액션, 윈도우 시스템이 Vehicle 을 직접 의존하는 핵심 god-object 패턴. 이 클래스 변경은 수십 개 모듈에 ripple effect 를 발생시킨다.
- GameLoopCentrality 1.0 — UpdateMeasurements, Update 등 메서드들이 매 프레임 게임 루프에서 직접 호출되는 핫 패스. 이 코드는 밀리초당 누적되므로, 성능 회귀나 GC 압력 증가가 즉시 fps 에 반영된다.
- 순환 의존성 (DependencyCycle 275, SCC 멤버) — Ride, RideData, GameState, World 등 상호 참조 구조에서 Vehicle 은 중심에 있어, 호출 흐름을 추적하거나 테스트 고립이 극도로 어렵다. 변경 영향을 정적 분석으로 추적 불가능한 구간이 존재할 수 있다.
- CC 39.5 (상위 10% 평균) — UpdateMeasurements 메서드 스니펫만 보아도 다중 조건부(status, station 검증, timeout 로직), 플래그 조작, 윈도우 매니저 호출 등이 얽혀 있어, 한 번의 논리 변경이 여러 분기를 동시에 영향한다.

**리팩토링 제안**
- Vehicle 의존성을 단계별로 계층화하기 — 현재 87 개 클래스가 Vehicle 을 직접 참조하는데, 이 중 '엔티티 속성 읽기'(LightListEntry, ItemPref 등)와 '게임 로직 변경'(CheatSetAction, Editor 등) 을 분리하는 read-only facade 또는 event-driven interface 를 도입. 급격한 변경 대신, 인접한 5~10 개 호출처부터 interface 로 전환하여 점진적으로 결합도를 낮춘다.
- UpdateMeasurements 의 상태 머신 단계를 명시적 enum / visitor pattern 으로 분해 — 현재 메서드는 travellingBoat, testInProgress, averageSpeedTestTimeout 등 여러 상태 전이를 한곳에서 관리. status, flags 값별로 상태별 핸들러를 분리하고, 매 상태 전이에서 윈도우 갱신·플래그 변경을 독립적 콜백으로 옮기면 각 분기의 부작용(side effect)이 명확해진다.
- 전역 state 접근(Ui::GetWindowManager(), GetRide() 등) 을 Vehicle 생성 시점에 주입받는 컨텍스트로 변경 — 현재 UpdateMeasurements 는 매 호출마다 전역 윈도우 매니저를 조회. 이는 핫 패스에서 성능 이슈 + 테스트 고립 불가. Vehicle 을 구성할 때 RideRef, WindowManager 를 DI 패턴으로 전달하되, 핫 패스 성능(캐시 미스, 가상 호출 오버헤드) 은 benchmarking 하여 실제 fps 영향을 측정한 뒤 적용.
- UpdateMeasurements 의 통계 누적 로직(averageSpeedTestTimeout 등) 을 별도 'RideTestState' 혹은 'MeasurementAccumulator' 객체로 추출 — 현재 Ride 와 Vehicle 모두 테스트 상태를 관리하는 중복 책임. 이 로직을 3rd 클래스로 옮기고 Ride 와 Vehicle 이 이를 query 하는 구조로 바꾸면, 테스트 시나리오를 독립적으로 구성할 수 있다.

**테스트 우선순위**
- Vehicle 모듈 내 상태 전이 characterisation test — 현재 게임 코드는 UpdateMeasurements 의 정확한 사이드 이펙트(어떤 조건에서 어떤 플래그가 변하고, 윈도우가 언제 갱신되는지)를 명시적으로 문서화한 테스트가 부족할 가능성 높음. 상태별(travellingBoat, testInProgress 등) 입력 케이스를 만들고, 출력 플래그/윈도우 갱신 호출을 golden master 로 기록해 회귀 방지.
- Vehicle 변경이 87 개 의존 클래스에 미치는 영향 범위 분석 테스트 — 리팩토링 전, Vehicle API 의 구간별 변경(예: GetRide() 반환 타입 변경, status 필드 접근 제한 등)에 대해 compile-time 과 runtime 양쪽에서 어느 모듈이 영향받는지 매핑. 의존성 그래프의 cut-edge 를 식별해 우선 리팩토링 대상 결정.
- UpdateMeasurements 성능 회귀 테스트 (fps / memory) — 매 프레임 호출되는 메서드이므로, 리팩토링 전후 프로파일 데이터(cpu time, allocation count, GC pause) 를 측정하는 benchmark 구성. 특히 DI 패턴 도입 시 가상 호출 오버헤드가 누적되지 않는지 확인.
- Vehicle 의 전역 상태 접근(GetWindowManager, GetRide 등) 을 격리하는 stub/mock test — 현재 8 개의 전역 접근 지점이 있는데, 각각을 mock 으로 대체했을 때 UpdateMeasurements 의 논리가 동일하게 작동하는지 검증. 이를 통해 향후 DI 전환 시 동치성 보장.

_불확실성: 코드 스니펫이 일부(line 455~766 중 처음 몇십 줄)이므로, UpdateMeasurements 의 전체 분기 수(actual CC)와 누락된 side effect 를 완전히 파악하기 어렵다. 또한 Vehicle 이 vehicle.cpp 단일 파일 내에만 있는지, 여러 헤더 파일의 Vehicle 클래스/함수가 더 있는지 불명. DependencyCycle 275 는 매우 큰 SCC 크기를 시사하는데, 순환 의존성의 실제 경로(Vehicle ← Ride ← World ← Entity ← ...)를 그려보지 않아 어느 단계에서 끊을 수 있을지 확실하지 않다. 성능 핫 패스 여부도 UpdateMeasurements 호출 빈도(매 프레임인지, 특정 상태에서만인지)에 따라 달라질 수 있으므로 profiling 정보가 필요하다._

## 5. [E] G-SI 99.4 — `drawing.Drawing`
`drawing/Drawing.cpp` · CC=15.5  CP=164  GS=43  GLC=0.5

**위험 원인**
- 결합도 164(팬인 153 + 팬아웃 11) — 거의 모든 액션/UI 모듈이 이 드로잉 단위에 의존하므로, 여기서의 변경이 수백 개 호출처에 파급된다. 순환 의존성 SCC 크기 275는 끊어낼 수 없는 강한 결합을 의미한다.
- 게임 루프 중심성 0.5(매우 높음) — UpdatePaletteEffects 등 메서드가 Render/Draw 진입점에서 호출되는 핫 패스 상에 있으므로, 매 프레임 성능 영향을 점검해야 한다. 팔레트 업데이트, 메모리 순회(gGamePalette 배열 루프)가 누적되면 fps 저하가 발생할 수 있다.
- 전역 상태 접근 43회 — gGamePalette, Weather::gLightningFlash, gLightningDirection 같은 정적 변수를 직접 읽고 수정한다. 이로 인해 테스트 고립이 어렵고 부작용이 예측 불가능해진다.
- CC 15.5(상위 10% 평균) — UpdatePaletteEffects 메서드 본체에만 다중 조건 분기(weather check, null check, palette type dispatch)가 중첩되어 있어, 장기 유지보수 시 새로운 기상 또는 팔레트 모드 추가 시 복잡도가 급증할 위험이 있다.

**리팩토링 제안**
- **전역 팔레트 상태를 컨텍스트 객체로 감싸기** — gGamePalette, gLightningFlash, gLightningDirection을 GamePaletteState 같은 명시적 객체로 캡슐화하고, Drawing 생성 시 주입받도록 변경. 이렇게 하면 테스트에서 팔레트 상태를 mock 할 수 있고, 향후 멀티플레이어/리플레이 기능에도 대응 가능해진다. 핫 패스(Render) 성능은 포인터 역참조 1~2 단계 추가로 무시할 수준이다.
- **기상 효과 업데이트를 전략 패턴으로 분리** — Weather::gLightningFlash, gRainLevel 같은 기상 상태별 팔레트 변환 로직을 WeatherPaletteStrategy 인터페이스로 추출. UpdatePaletteEffects를 호출할 때 현재 날씨에 맞는 전략만 실행하도록. 이렇게 하면 메서드 복잡도를 낮추고, 향후 새로운 기상 모드 추가 시 기존 코드 수정 대신 새 전략만 구현하면 된다.
- **팬인 모듈의 의존성을 간접화** — 현재 153개 모듈(모든 액션 클래스)이 Drawing을 직접 import 한다. 이들이 실제로 필요한 것은 DrawText, DrawRect 같은 구체적 함수 몇 개뿐이다. 이를 IDrawingContext 인터페이스로 추상화하고, 각 액션은 인터페이스만 의존하도록 변경하면, Drawing 내부 리팩토링이 액션 코드에 영향을 주지 않는다.
- **팔레트 업데이트 루프의 성능 프로파일링** — UpdatePaletteEffects 내 gGamePalette 배열 순회(for i in 0..numColours)가 매 프레임 실행되므로, 팬인 크기 변경 전에 성능 회귀 테스트를 작성해 frame time 증가를 감시한다. 필요시 팔레트 업데이트 빈도를 낮추거나, 더티 플래그 방식으로 변경된 색상만 업데이트하는 최적화를 고려할 수 있다.

**테스트 우선순위**
- **기상 효과 팔레트 변환 characterisation test** — 번개/폭우 상태별로 gGamePalette 배열의 RGB 값이 예상 공식(예: blue = -((0xFF - g1Entry.blue) / 2) - 1)에 따라 변환되는지 확인하는 golden master 테스트. 기존 동작을 '정답'으로 기록해 두고, 리팩토링 후에도 동일한 팔레트 값이 나오는지 검증한다.
- **의존성 주입 + 모킹 통합 테스트** — Drawing 생성 시 mock GamePaletteState, mock WeatherContext를 주입해, 전역 상태 없이 UpdatePaletteEffects가 올바르게 호출되는지 테스트. 이를 통해 리팩토링 후 153개 호출처의 동작이 보장됨을 증명한다.
- **프레임 시간 회귀 테스트** — UpdatePaletteEffects를 1000회 반복 호출했을 때 소요 시간을 측정하는 성능 테스트. 리팩토링(전략 패턴 분리, 컨텍스트 주입) 전후 프레임 시간이 ±5% 이내임을 확인해, 최적화 후보(더티 플래그, 배열 크기 축소)를 검증한다.
- **팬인 호출 연쇄 테스트** — 액션 클래스 몇 개(CheatSetAction, RideDemolishAction)에서 Drawing::DrawText/DrawRect를 호출하는 시나리오를 자동화. 인터페이스 추상화 후에도 기존 액션 코드가 컴파일되고 실행되는지 확인한다.

_불확실성: 코드 스니펫이 부분 발췌이므로, UpdatePaletteEffects 메서드의 전체 라인 수(747~899)와 정확한 CC 값을 확인할 수 없다. 또한 Weather::gLightningFlash 같은 외부 정적 변수의 수정 빈도와 크기를 알 수 없어, 전역 상태 43회 중 몇 개가 쓰기인지 추정만 가능하다. Drawing이 어떤 렌더링 백엔드(GDI, Direct3D, OpenGL)를 사용하는지에 따라 팔레트 업데이트의 성능 특성이 달라질 수 있으므로, 플랫폼별 회귀 테스트가 필요할 수 있다. 또한 순환 의존성 SCC 275가 Drawing 클래스 자체의 순환 참조인지, 아니면 Drawing을 포함한 상위 모듈 수준의 순환인지 불명확하여, 리팩토링의 실효성 판단에 불확실성이 남아 있다._
