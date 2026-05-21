# OpenRA.Game — LLM 리팩토링 가이드 (Phase C)

- 모델: `claude-haiku-4-5`
- 토큰 사용: input=21,507 output=9,560 cache_write=0 cache_read=0 (cache hit ≈ 0.0%)
- 예상 비용: **$0.0693** USD

## 1. [E] G-SI 100.0 — `OpenRA.Network.UnitOrders`
`Network/UnitOrders.cs` · CC=93.0  CP=5  GS=47  GLC=0.3333

**위험 원인**
- 매우 높은 순환 복잡도(CC 93.0)로 인해 메서드 내 제어 흐름이 극도로 복잡함. ProcessOrder 메서드는 거대 switch 구조로 40개 이상의 order 타입을 다루며, 각 case 내에서 다중 조건문과 중첩 루프를 포함하고 있어 테스트 경로 수가 2^93 에 가까워 완전 커버리지가 불가능함.
- 전역 상태 접근(GlobalState 47)이 매우 높음. TextNotificationsManager, OrderManager, World 같은 싱글톤형 static 인스턴스를 직접 참조하고 있으며, 이들은 순수 함수 테스트를 불가능하게 만들고 게임 루프 내 상태 추적을 어렵게 함.
- 게임 루프 중심성(GameLoopCentrality 0.3333)이 상당함. ProcessOrder는 network message 처리 핫 패스에서 매 프레임 호출될 수 있으며, 여기서 발생하는 예외나 지연은 네트워크 응답 지연으로 직결되어 게임 플레이 경험에 즉시 영향을 미침.
- 소규모 fan-out(5개)이지만 각 의존 클래스(Order, MiniYaml, FluentMessage 등)는 네트워크 메시지 파싱 및 게임 상태 동기화의 핵심이므로, 이 메서드의 변경은 멀티플레이어 동작 전체에 영향을 미칠 수 있음.

**리팩토링 제안**
- giant switch 를 Strategy/Command 패턴으로 분해. 각 order 타입별로 별도 handler 클래스를 도입하되, handler 자체는 현재 큰 switch 문을 소유하지 말고 OrderType → Handler mapping 딕셔너리로 관리. 이렇게 하면 CC를 메서드당 10~15 로 낮출 수 있고, 새 order 타입 추가 시 기존 switch 문을 수정하지 않아도 됨.
- Global state 의존성을 제거하기 위해 OrderProcessor 를 생성자 주입 가능한 service 로 변환. TextNotificationsManager, OrderManager 의 참조를 static 호출 대신 생성자 파라미터로 받도록 시그니처를 변경. 게임 루프 초기화 시 한 번만 의존성을 설정하므로 성능 오버헤드 없음.
- ProcessOrder 내에서 order 검증 / 파싱 / 상태 적용 을 three-phase 로 분리. validation phase 에서 미리 잘못된 order 를 reject 하고, parsing phase 에서는 pure function 으로 order → domain object 변환, application phase 만 side-effect 수행. 각 phase 를 별도 메서드로 추출하면 unit test 와 integration test 를 명확히 분리할 수 있음.
- 고위험 case 그룹(Player action orders: Move, Attack, Build 등)을 별도 클래스로 먼저 추출해 점진적 리팩토링 시작. 반드시 필요한 handler 만 먼저 분리하고, 시스템 메시지(Message, FluentMessage) 같은 낮은 변경 빈도 case 는 당분간 switch 에 남겨두어 리팩토링 범위를 한정.

**테스트 우선순위**
- ProcessOrder 의 각 order 타입별 characterisation test (golden master) 작성. 현재 코드 행동을 .yaml/.json snapshot 으로 기록하고, 리팩토링 후 동일한 네트워크 패킷 입력에 대해 같은 결과를 내는지 regression 검증. 멀티플레이어 시나리오(join, leave, unit order, resource transfer 등) 를 20~30 개 케이스로 정의.
- Pure function 테스트 (validation + parsing phase). order 문자열을 입력으로 받아 정상/에러 상태를 돌려주는 메서드를 별도로 만들고, mocking 없이 즉시 테스트 가능하게 함. 특히 malformed order(missing field, invalid value, boundary cases) 에 대해 30+ 케이스 검증.
- Performance regression test. ProcessOrder 를 10,000 회 호출하는 benchmark 를 작성하고, 리팩토링 전후 평균 응답 시간 및 GC allocation 을 측정. 게임 루프 핫 패스이므로 1% 이상의 성능 저하도 허용 불가.
- Integration test (OrderManager + World + TextNotificationsManager 통합). network message 를 받아 order 가 올바르게 world state 에 반영되고 UI notification 이 발생하는지 검증. 멀티플레이어 상황(2~4 player) 에서 메시지 순서 섞임, 지연 등 edge case 포함.

_불확실성: 코드 스니펫이 일부만 제공되었으므로, 전체 40+ case 의 정확한 분포(데이터 처리 case vs 상태 변경 case vs UI-only case)를 확인할 수 없음. ProcessOrder 메서드의 총 라인수가 368 라인(48~415)인데, 한 메서드가 이렇게 크다는 것 자체가 극도로 높은 CC 를 뒷받침함. 또한 global state 접근 47 건이 주로 ProcessOrder 메서드에 집중된 것인지, 클래스 내 다른 static initializer 나 helper method 에 분산된 것인지 불명확함. 게임 루프 중심성 0.3333 은 상당히 높지만, 이것이 network thread 에서 호출되는지 main game thread 에서 호출되는지 확인 필요. 만약 background thread 라면 static state 접근에 concurrent modification risk 가 있을 수 있음._

## 2. [E] G-SI 99.8 — `OpenRA.Server.Server`
`Server/Server.cs` · CC=33.25  CP=23  GS=176  GLC=1.0

**위험 원인**
- GlobalState 176 — 싱글톤, static mutable, 전역 변수 접근이 매우 많아서 테스트 고립이 거의 불가능하며, 동시성 문제의 원인이 될 수 있다. 서버 상태 초기화 및 정리 검증이 어렵다.
- CC 33.25 (상위 10% 평균) — ValidateClient 메서드 스니펫만 봐도 다층 조건 분기(State 체크, 비밀번호 검증, IP 주소 파싱, Location 조회 등)가 중첩되어 있으며, 전체 메서드는 465~706줄에 걸쳐 있다. 한 메서드에서 인증, 세션 생성, 플레이어 등록, 메시지 전송이 모두 처리된다.
- Coupling 23 + GameLoopCentrality 1.0 — 22개의 외부 클래스 의존(OrderBuffer, PlayerMessageTracker, Session, GameSave, ReplayRecorder, GeoIP 등)과 game loop entry point 역할을 동시에 하므로, 이 클래스의 변경이 전체 멀티플레이 시스템의 회귀를 야기할 가능성이 크다.
- 단일 책임 위반 — 핸드셰이크 검증, 플레이어 세션 관리, 주문 송수신 완충, IP 지오로케이션, 리플레이 기록, 비밀번호 인증 등이 한 클래스에서 처리된다. god-object 패턴의 전형적인 사례다.

**리팩토링 제안**
- **인증 및 검증 로직 분리**: ValidateClient 메서드에서 HandshakeResponse 역직렬화, 비밀번호 검증, IP 화이트리스트 체크 등을 별도 `ClientAuthenticator` 또는 `ServerAuthenticationPolicy` 인터페이스로 추출한다. 이렇게 하면 테스트 시 mock authenticator 를 주입 가능하고, GlobalState 의존성을 감소시킬 수 있다. 단, game loop 핫 패스(connection accept)에서 호출되므로 성능 회귀를 피하기 위해 인접 호출자에만 먼저 적용한다.
- **세션 관리 / 플레이어 추적을 Strategy 패턴으로 분리**: `PlayerMessageTracker`, `OrderBuffer` 등 관련 클래스들이 이미 분리되어 있으나, Server 클래스에서 이들을 직접 생성/소유하고 있다. 세션 라이프사이클(생성→활성→종료)을 `ISessionManager` 인터페이스로 추상화하고, dependency injection 으로 주입받도록 변경하면 coupling 을 낮출 수 있다. 특히 테스트에서 mock SessionManager 로 교체 가능해진다.
- **전역 상태 의존성을 명시적 컨텍스트 인자로 치환**: GeoIP, Settings 같은 정적 접근을 추적하고, 가능한 한 Server 생성자 또는 메서드 인자로 주입받도록 점진적으로 변경한다. 예를 들어 `GeoIP.LookupCountry(ipAddress)` 호출을 `this.geoipService.LookupCountry(ipAddress)` 로 변경한다. 이는 GlobalState 176 을 단계적으로 낮추며, 테스트 환경에서 mock GeoIP 사용을 가능하게 한다.
- **ValidateClient 의 거대 메서드 분해**: 현재 240줄 이상의 메서드를 5~6개의 작은 유효성 검사 단계로 분해한다 (예: `ValidateGameState()`, `ValidateCredentials()`, `ValidatePlayerInfo()`, `ValidateSlots()`, `CreateAndRegisterSession()`). 각 단계마다 조기 반환(early exit)을 사용하면 CC 를 단계별로 낮출 수 있고, 테스트도 단위별로 가능해진다. 이미 `DropClient()`, `SendOrderTo()` 헬퍼가 있으므로 패턴 일관성도 유지된다.

**테스트 우선순위**
- **Characterisation Test (현재 동작 스냅샷)**: Server 클래스의 현재 정상 동작을 golden master 로 기록한다. 성공적인 클라이언트 연결 시나리오(올바른 핸드셰이크 → 세션 생성 → 플레이어 등록 → 게임 시작), 인증 실패 시나리오(틀린 비밀번호 → 에러 메시지 송신 → 연결 종료), 게임 시작 후 지연 접속(거부) 등을 각각 기록한다. 리팩토링 전후 동작이 동일함을 보장한다.
- **Dependency Injection 마이그레이션 테스트**: Server 생성자가 현재 전역 상태(GeoIP, Settings, Log)를 직접 참조하는 부분을 mock 로 주입받도록 변경할 때, mock GeoIP(고정 국가 코드 반환), mock Settings(임의의 비밀번호 설정) 를 사용한 단위 테스트를 먼저 작성한다. 이를 통해 GlobalState 의존성 제거 효과를 검증하고, 리팩토링 과정에서 회귀를 조기에 감지한다.
- **멀티스레드 동시성 테스트**: Server 가 여러 스레드에서 동시에 여러 클라이언트 연결을 받을 때 race condition(세션 ID 중복, 플레이어 리스트 손상)이 없는지 확인한다. 현재 GlobalState 가 높으므로 lock/atomic 정확성이 중요하다. concurrent connection accept, order dispatch, player state update 시나리오를 stress test 한다.
- **Performance Regression (게임 루프 핫 패스)**: ValidateClient 메서드는 game loop entry point 에서 호출되므로, 리팩토링 후 클라이언트 핸드셰이크 처리 시간(지연 시간, GC 할당)이 증가하지 않았는지 검증한다. 서버 fps(프레임 반영 로직)에 영향이 없는지 벤치마크한다.

_불확실성: ValidateClient 메서드의 전체 길이(465~706줄)를 확인할 수 없어, 정확한 CC 와 분기점 분포를 추정했다. 또한 Server 클래스의 GlobalState 176 이 구체적으로 어떤 정적 멤버(GeoIP, Settings, Log 등)를 몇 번 호출하는지 명시되지 않았으므로, 상대적 영향도만 판단했다. 의존성 그래프에서 '22개'로 표시되었으나 구체적 사용 패턴(읽기만 vs. 읽기+쓰기, 핫 패스 vs. 초기화 시점)이 알려지지 않았다. 따라서 리팩토링 제안은 일반적 게임 엔진 패턴(god-object 분해, DI 도입)에 기초했으며, 실제 적용 시 성능 영향(GC, 락 경합)을 마이크로벤치마크로 재검증해야 한다._

## 3. [E] G-SI 99.7 — `OpenRA.Game`
`Game.cs` · CC=16.25  CP=27  GS=152  GLC=1.0

**위험 원인**
- 게임 루프 진입점(GameLoopCentrality=1.0)으로서 매 프레임 핫 패스 내 모든 변경은 fps 및 렌더링 성능에 직접 영향을 미친다. Loop() 메서드의 타이밍 로직(nextLogic, now, deltaTime 관리)이 프레임 드롭 또는 동기화 오류를 유발할 수 있어 극도의 신중함이 필요하다.
- 전역 상태 접근(GlobalState=152)이 매우 높으며, Settings, ModData, WorldRenderer, Sound 등 27개 외부 모듈에 의존한다(Coupling=27). 이들 대부분이 static/singleton 인스턴스를 통해 접근되므로 테스트 격리가 어렵고, 한 지점의 전역 상태 변경이 연쇄 부작용을 초래할 수 있다.
- 코드 스니펫에서 보이는 Loop() 메서드는 타이밍 동기화 로직을 포함하고 있으며, 시간 계산 오류(예: nextLogic 잘못된 업데이트)는 게임 속도 저하 또는 프레임 누락으로 이어진다. CC=16.25(상위 10% 평균)는 분기가 많음을 시사하며, 분기별 부작용 추적이 어렵다.

**리팩토링 제안**
- 타이밍 로직을 전담하는 별도 FrameScheduler 또는 GameTimer 클래스로 추출하되, Loop() 내 직접 호출에만 한정하여 외부 의존성을 추가하지 말 것. 이를 통해 타이밍 계산을 unit test 가능하게 격리하고, Loop() 자체의 책임을 단순화할 수 있다.
- 현재 27개 의존성 중 Settings, GraphicsSettings, ModData 같은 구성 정보 접근을 Dependency Injection 패턴으로 변환할 단계적 계획을 수립하되, 게임 루프 중간에 주입을 시도하지 말고 Game 생성자 단계에서만 주입할 것. 이는 런타임 성능 영향을 최소화하면서 테스트 시 mock 주입을 가능케 한다.
- Loop() 메서드 내 static mutable 필드(예: Settings.Game.Timestep 등) 읽기를 최소화하기 위해 루프 초입에 한 번만 읽고 지역변수로 캐싱하는 패턴을 도입할 것. 이는 GC 압력 감소 및 성능 안정성을 높인다.
- 현재 Loop() 메서드가 888 LOC 클래스 내에서 139 줄(추정)을 차지하므로, 렌더링 루틴(rendering skip logic, buffer swap)과 로직 업데이트 루틴을 분리된 protected 메서드로 추출하되, Loop() 자체는 orchestrator 역할만 수행하게 할 것. 이는 각 루틴의 테스트 및 변경 영향 분석을 단순화한다.

**테스트 우선순위**
- Characterisation Test: 현재 Loop() 동작을 기준으로 프레임 타이밍(nextLogic, deltaTime 진행, 렌더링 skip 조건)의 golden output 을 기록할 것. 미래 변경 시 타이밍 회귀를 감지하기 위한 기준점이 된다.
- Performance Regression Test: Loop() 메서드 한 사이클(예: 100회 반복)의 실행 시간 및 GC 할당 량을 측정하는 벤치마크를 구성할 것. 타이밍 로직 리팩토링 전후 fps 변화를 정량적으로 검증해야 한다.
- Mock Static Injection Test: Settings, ModData 등 주요 static/singleton 의존성을 test double 로 대체할 수 있는 test hook 을 Game 클래스에 추가하고, Loop() 호출 시 각각 다른 값(Timestep 변경, MaxFramerate 변경)을 주입해 타이밍 로직의 correctness 를 검증할 것.
- Integration Regression Test: 게임이 실제로 로드되고 몇 프레임 실행되는 end-to-end 흐름에서 crash 나 deadlock 이 발생하지 않는지, 그리고 기대 fps 범위 내에 머물러 있는지 확인할 것.

_불확실성: 코드 스니펫이 부분(truncated)이어서 Loop() 메서드 전체 구조, 내부 while/for 루프 개수, 예외 처리 범위를 정확히 파악하기 어렵다. 또한 27개 의존성 중 어느 클래스가 실제로 static 또는 singleton 패턴인지 확인할 수 없으므로, GlobalState=152 의 정확한 구성(static 필드 읽기 vs 싱글톤 인스턴스 접근)을 재검토해야 한다. Loop() 메서드 외 Game 클래스의 나머지 787 LOC 에 대한 메트릭 분해도 필요하며, 생명주기 메서드(Initialize, LoadContent, Dispose 등)의 복잡도 분포를 보면 리팩토링 우선순위가 바뀔 수 있다._

## 4. [E] G-SI 99.5 — `OpenRA.MiniYaml`
`MiniYaml.cs` · CC=32.5  CP=23  GS=10  GLC=0.25

**위험 원인**
- 결합도 23 (fan-out 3개, fan-in 20개) — OpenRA 거의 모든 설정 파서가 이 클래스를 의존하므로, 이 클래스의 변경이 전체 시스템에 cascade effect를 일으킬 수 있다. 특히 ValueActorInit, ActorReference, Map, MapPlayers, Network 계층 등 핵심 구조가 직접 의존한다.
- CC 평균 32.5 (top-10% 메서드) — 가장 복잡한 FromLines 메서드는 YAML 파싱의 인덴테이션, 문자열 풀링, 주석 처리, 예외 흐름을 한 곳에서 담당하는 거대 파서다. 이 메서드는 메모리 효율성을 위해 의도적으로 낮은 추상화 레벨을 유지하고 있어 리팩토링 난도가 높다.
- DependencyCycle = 2 (SCC 멤버) — MiniYaml이 속한 순환 의존성 컴포넌트 크기 2는 self-loop 또는 양방향 의존성을 암시하며, 이는 정적 분석이나 의존성 주입 개선을 어렵게 한다.
- GameLoopCentrality 0.25 — 이 클래스는 직접 게임 루프 진입점이 아니지만, Map/ActorReference/Network 계층을 통해 Tick/Load/Save 경로에 도달 가능하므로, 게임 시작/저장/로드 시 핫 패스의 일부다. 파싱 성능 저하는 로딩 시간 증가로 직결된다.

**리팩토링 제안**
- FromLines 메서드의 문자열 풀링 및 인덴테이션 파싱 로직을 별도의 내부 헬퍼 클래스(StringPoolingBuffer, IndentationParser 등)로 추출하되, 메서드 시그니처는 유지해 외부 호출처에 영향을 주지 않는다. 이렇게 하면 메서드 CC를 낮추고 각 관심사별 단위 테스트가 가능해진다.
- MiniYaml의 public 인터페이스를 의도적으로 축소하여, 외부에서는 FromLines/Save/Merge 같은 핵심 3~4개 메서드만 직접 호출하도록 강제한다. 내부 parsing state와 validation 로직은 private 로 격리해 변경 영향 범위를 제한한다. 이는 결합도 23을 실질적으로 낮출 수 없지만, API 契約을 명확히 해 향후 리팩토링 여지를 만든다.
- GlobalState 접근(10회) 및 exception throw 패턴을 추적하여, YamlException 생성 시점에서 파싱 컨텍스트(파일명, 라인번호, 스택)를 캡슐화한 전용 구조체를 도입한다. 이렇게 하면 error reporting이 일관되고, 향후 로깅/모니터링 추가 시 변경 점 하나만 수정하면 된다.
- FromLines 메서드의 성능 특성(string pooling, memory allocation)을 벤치마크하고 로드 시간 회귀 테스트를 추가하여, 향후 리팩토링 시 fps 또는 로딩 시간 저하가 없음을 자동 검증한다. 게임 루프상의 Map 로딩은 1회성이지만 에디터나 멀티플레이 세션에서 빈번하므로 성능 보장이 중요하다.

**테스트 우선순위**
- Characterisation test (현재 FromLines 동작의 golden master) — 다양한 YAML 포맷(중첩 depth, 특수 문자, 주석 위치, 빈 줄, 문자열 풀 충돌)에 대해 현재 파서의 출력을 전부 기록해두고, 향후 리팩토링 후에도 동일한 결과를 내는지 검증한다. 이는 파서의 의도하지 않은 동작 변화를 즉시 탐지한다.
- Performance regression test — Map/GameSave 로딩 시간을 마이크로벤치마크하여 리팩토링 전후 성능 차이(CPU, GC pressure, memory peak)를 측정한다. FromLines의 string pooling이 의도적 최적화이므로, 이를 손상시키지 않는 것을 자동 검증한다.
- Integration test with fan-in clients — ValueActorInit, ActorReference, MapPlayers 등 20개 의존 클래스 각각과 함께 MiniYaml 파싱 결과를 검증하는 엔드-투-엔드 테스트. 이는 MiniYaml 변경이 상위 계층에서 실제로 정상 작동함을 보장한다.
- Error handling edge case test — YamlException 스로우 경로(깨진 인덴테이션, 잘못된 형식, 순환 참조)를 명시적으로 테스트하여, 파싱 실패 시 사용자 메시지 품질과 복구 가능성을 검증한다. 게임 로딩 중 파싱 오류는 사용 경험을 크게 해치므로 우선순위가 높다.

_불확실성: 코드 스니펫은 FromLines 메서드의 초반부만 제공되어, 전체 제어 흐름(특히 후반부 예외 처리, 문자열 풀 업데이트 빈도, tail recursion 또는 반복)을 확인할 수 없다. CC 32.5는 top-10% 메서드 평균이므로, 실제 FromLines 의 개별 CC는 이보다 훨씬 높을 가능성이 있다. 또한 DependencyCycle = 2 (SCC 크기)만으로는 MiniYaml이 어느 다른 클래스와 순환 의존하는지, 그 사이클이 런타임(싱글톤) 초기화인지 컴파일타임(using/import)인지 판단하기 어렵다. 의존성 그래프의 fan-in 20개가 모두 강한 의존(필수 parsing)인지, 약한 의존(선택적 serialization)인지도 코드 점검 없이 추정 어렵다._

## 5. [E] G-SI 99.4 — `OpenRA.Support.VariableExpression.Token`
`Support/VariableExpression.cs` · CC=35.0  CP=5  GS=31  GLC=0.0

**위험 원인**
- Cyclomatic Complexity 35.0 — `GetNextType` 메서드가 switch/if 분기 30개 이상을 포함하는 거대 함수로, 제어 흐름 경로가 2^35 에 가까워 모든 분기 조합을 테스트하기 실질적으로 불가능하다. 이로 인해 엣지 케이스(예: 연속된 연산자, 잘못된 문자열 경계) 에서 버그 발생 확률이 높다.
- Dependency Cycle 크기 3 — `Token`, `VariableToken`, `NumberToken` 이 순환 참조를 형성하고 있어, 한 클래스의 변경이 다른 클래스의 컴파일/동작에 예측 불가능한 영향을 미친다. 특히 토큰 타입 정의나 파싱 로직 변경 시 회귀 버그 가능성이 높다.
- Global State 접근 31회 — 메서드 본체 내 `static` 필드나 싱글톤 인스턴스 접근이 빈번해, 동기화 문제나 테스트 격리가 어렵고, 문자열 파싱 중 외부 상태에 의존적인 부작용이 누적될 수 있다.

**리팩토링 제안**
- **switch 문을 상태 머신 또는 룩업 테이블로 분해**: `GetNextType` 의 switch 블록을 character-to-token-type 매핑 테이블(`Dictionary<char, (Action, TokenType)>`) 로 변환하거나, 각 연산자 타입별 nested enum 핸들러로 분리해 CC 를 15 이하로 감소시킨다. 이는 문자 분석 로직과 다음 문자 확인 로직을 명확히 분리하므로 엣지 케이스 테스트도 용이해진다.
- **순환 의존성 해소 — interface/enum 추출**: `TokenType` 이 공통 인터페이스 또는 enum 으로 이미 정의되어 있다면, `Token` 의 추상화 수준을 높여 `VariableToken`/`NumberToken` 이 구체 구현체가 되도록 재구성한다. 이렇게 하면 `Token` → 추상화, 구체 토큰들은 느슨한 결합으로 변경된다.
- **Global State 의존성을 매개변수 또는 컨텍스트 객체로 전환**: `GetNextType` 을 순수 함수로 만들기 위해, 필요한 모든 설정(문자 규칙, 연산자 정의 등) 을 `TokenParsingContext` 같은 불변 레코드로 전달한다. 이를 통해 문자열 파싱 로직을 테스트 및 성능 분석이 쉬워진다.
- **메인 파싱 루프 추출**: 현재 `ref int i` 포인터 조작이 `GetNextType` 내부에 산재해 있다면, 자동 상태 진행(i 증분)을 담당하는 `IEnumerable<Token> Parse(string expression)` 래퍼로 감싼다. 이는 호출자 쪽 복잡도를 낮추고, 파싱 상태 추적을 명확히 한다.

**테스트 우선순위**
- **Characterisation test for GetNextType edge cases**: 각 연산자(`!`, `!=`, `<`, `<=`, `>`, `>=`, `==`, `||`, `&&` 등) 와 올바른/잘못된 경계(문자열 끝, 중복 연산자, 숫자-연산자 시퀀스) 에 대해 예상 반환 값과 `i` 증분을 명시적으로 검증하는 행렬식 테스트를 작성한다. 이를 통해 현재 동작을 baseline 으로 고정한 뒤 리팩토링 후 회귀를 조기에 감지한다.
- **Circular dependency isolation test**: `Token`, `VariableToken`, `NumberToken` 을 각각 독립적으로 인스턴스화하고, 메서드 호출 경로를 추적해 순환 의존성이 실제로 runtime 에 문제를 일으키는지 확인한다. 순환 구조를 깨는 리팩토링 후, 이 테스트는 회귀 방지 역할을 한다.
- **Integration test for full expression parsing**: 실제 게임 변수 표현식(예: `hp > 50 && armor <= 100 || is_hero`) 을 파싱해 토큰 시퀀스와 평가 결과가 의도와 일치하는지 검증한다. GetNextType 의 분해 후에도 전체 파이프라인이 동작함을 보증하는 golden master test 역할을 한다.

_불확실성: 코드 스니펫이 `GetNextType` 의 일부만 제시되어 전체 switch 구조와 모든 분기를 확인할 수 없었으므로, CC 35.0 의 정확한 분포(단일 메서드인지 여러 메서드 합인지) 를 단정하기 어렵다. 또한 GlobalState 31 의 구성(static 필드 vs 싱글톤 접근 vs 전역 변수)이 명시되지 않아, 리팩토링 우선순위(매개변수 주입 vs 컨텍스트 객체 vs 불변화) 를 세부 조정하기 위해서는 전체 클래스 본체와 호출 그래프 상세 검사가 필요하다. `GameLoopCentrality 0.0` 은 이 토큰 파서가 매 프레임 루프의 핫 패스 밖에 있다는 뜻으로, 성능 회귀 테스트보다는 정확성과 유지보수성을 우선하는 리팩토링이 적절하다._
