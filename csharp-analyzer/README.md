# csharp-analyzer

Roslyn 기반 C# 정적 분석 콘솔. `game-si` 도구의 분석 엔진으로 사용된다.

## 빌드

`.NET 8 SDK` 가 필요하다.

```bash
cd csharp-analyzer
dotnet build
```

## 직접 실행

```bash
# 단일 파일
dotnet run -- --input ../tests/samples/SampleGame.cs

# 디렉토리 (재귀)
dotnet run -- --input ../benchmarks/OpenRA/OpenRA.Game --output ../reports/openra-game/ast.json

# bin/Debug 의 dll을 직접 실행
dotnet bin/Debug/net8.0/csharp-analyzer.dll --input <path> [--output <json>] [--exclude <dirname>]
```

## 출력 형식

JSON 출력 스키마는 [`../docs/ast-schema.md`](../docs/ast-schema.md)에 정의되어 있다.

## 추출 항목 (W1 단계)

- 파일 단위: 경로, LOC
- 타입 단위: 이름, 정규 이름, 네임스페이스, kind(class/struct/interface/record/enum), base types, modifiers
- 메서드 단위: 이름, 시그니처, 파라미터 수, 반환 타입, modifiers, Cyclomatic Complexity, LOC

## 후속 단계 예정 기능

- W2: 솔루션(.sln) 입력 지원 (MSBuildWorkspace), semantic 분석
- W3: 호출 그래프 / 참조 그래프 출력
- W4: 게임 특화 패턴 detector (게임 루프, 정적 상태, 이벤트 핸들러)
