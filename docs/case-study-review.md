# 양방향 후보 소스 검토 (2026-10-04)

후보 “정리”는 순위표를 예쁘게 만드는 일이 아니라 **왜 올라왔는지 실제 소스로 확인하고, 점검할 항목과 과도한 해석을 구분하는 일**이다. 아래는 실제 결함 발견이나 수정 효과의 실험이 아닌 수작업 정성 검토다. 소스와 외부 게임은 변경하지 않았다.

공통 기준: 최신 default 점수, 같은 파일 집합에서 G-SI/Lizard top-30 비교, 동점은 파일 경로순. CC 수치는 G-SI 입력(클래스의 상위 10% 평균)과 Lizard 최대 함수 CC가 서로 다를 수 있다.

## 1. Doom `i_system.c`: 낮은 함수 복잡도지만 구조 연결이 많은 후보

- 고정 소스: Chocolate Doom `c62b634f394e64dd51dec7e6f890496f43a56ade`, `benchmarks/chocolate-doom/src/i_system.c`.
- G-SI 100, 파일 순위 1 / Lizard 최대 CC 12, 순위 159. 원시 Coupling 156, DependencyCycle 63(SCC 크기+내부 연결), GlobalState 22, GameLoopCentrality 1/3.
- 소스 확인: 57~77행의 종료 콜백 연결 리스트와 `exit_funcs`, 251~268행의 `I_Quit` 콜백 순회, 276~300행의 `I_Error` 재귀 종료 방지 상태. 385행 이후에는 DOS 메모리 읽기 호환용 상태도 있다.
- 해석: 여러 모듈이 쓰는 시스템/종료 경계이므로 변경 영향과 상태 관리 검토에 적합하다. “함수가 복잡하지 않으면 모든 구조 위험도 낮다”는 결론을 보완하는 사례다. 다만 기반 시스템 허브가 널리 참조되는 것 자체는 자연스러워 결함 또는 설계 실패의 증거가 아니다.
- 권장 점검: 정상 종료와 오류 종료의 콜백 순서·중복 실행, 재진입 오류 종료, DOS 메모리 읽기 크기·범위의 기존 동작을 고정하는 테스트. 실제 테스트 구현이나 리팩토링 효능 측정은 이번 사례 검토에 포함하지 않았다.

## 2. Doom `hexen/mn_menu.c`: G-SI 목록만 보면 밀릴 수 있는 복잡한 동작

- 같은 Doom SHA, `benchmarks/chocolate-doom/src/hexen/mn_menu.c`.
- G-SI 86.49, 순위 41 / Lizard 최대 CC 144, 순위 4. G-SI 원시 대표 CC 42, Coupling 8, DependencyCycle 0, GlobalState 275, GameLoopCentrality 0.
- 소스 확인: 1183행 시작 `MN_Responder`에서 입력·메뉴 상태를 처리하고, 1382행 이후 확인 질문 분기, 1786행 이후 문자열 편집/삭제/취소/확정 분기가 이어진다.
- 해석: top-30에 없다고 중요하지 않은 파일이 아니다. G-SI 파일 순위는 여러 구조 항목과 대표 CC를 혼합하고, Lizard는 가장 복잡한 함수 하나를 강조한다. 메뉴는 본래 상태 머신 성격이 있어 큰 CC가 모두 불필요한 복잡도라는 뜻도 아니다.
- 권장 점검: 메뉴 열림/닫힘, 확인 질문 종류, 저장 이름 입력·삭제·취소·확정의 상태 전이와 버튼/키 조합을 표 기반으로 검사한다. Lizard 상위 후보도 함께 점검해야 한다는 **역방향 사례**다.

## 3. OpenRA `Primitives/int2.cs`: 높은 상대 순위의 반례·주의 사례

- 고정 소스: OpenRA `8f2138c71106aaffd8a288b56d1c9ef6013700ba`, `benchmarks/OpenRA/OpenRA.Game/Primitives/int2.cs`.
- G-SI 98.50, 파일 순위 9 / Lizard 최대 CC 2, 순위 178. 원시 CC 2, Coupling 15, DependencyCycle 4, GlobalState 5, GameLoopCentrality 1/3.
- 소스 확인: 19행의 `readonly struct int2`, readonly 좌표 필드와 작은 산술·동등성·변환 메서드, `Sign`/`Abs`/`Max`/`Min`의 `Math` 호출. 다수의 연산자도 있으나 현재 C# MethodNode는 일반 메서드·생성자만 수집한다.
- 해석: 널리 쓰이는 좌표 값 타입이라 연결 수가 높은 것은 자연스러울 수 있다. static `Math` 호출이 GlobalState에 포함되는 구현 한계도 보인다. **높은 G-SI를 “리팩토링해야 할 나쁜 구조”로 해석하지 않는 구체적 반례**로 제시한다.
- 권장 점검: 값을 변경할 일이 생기면 산술·동등성·해시·변환·경계값의 호환성 테스트를 우선한다. 이 파일을 분리하거나 점수를 낮추는 것을 목표로 삼지 않는다.

## 결론

G-SI 후보와 Lizard 후보를 함께 보고, 공통 후보 → 각 도구 단독 후보 → 원시 지표 → 실제 역할/소스의 순서로 검토하는 것이 적절하다. 한 도구의 top-N 밖이라는 이유로 다른 후보를 버리지 않는다. 위 세 사례는 새 성능 지표나 사용자 만족도 측정이 아니라 보고서의 해석·한계·테스트 우선순위를 설명하는 근거다.

수치 출처: `reports/chocolate-doom/scoring.json`, `reports/chocolate-doom/compare.json`, `reports/openra-game/scoring.json`, `reports/openra-game/compare.json`. 입력 해시와 실행 검증은 [최종 보완·재검수](refinement-review.md)에 연결했다.
