// 분석 결과를 JSON으로 직렬화하기 위한 데이터 모델.
// 스키마 버전은 docs/ast-schema.md 와 동기화한다.

namespace CSharpAnalyzer;

using System.Text.Json.Serialization;

public sealed class AnalysisResult
{
    [JsonPropertyName("schema_version")]
    public string SchemaVersion { get; set; } = "0.2";

    [JsonPropertyName("analyzed_at")]
    public string AnalyzedAt { get; set; } = "";

    [JsonPropertyName("input_path")]
    public string InputPath { get; set; } = "";

    [JsonPropertyName("analyzer_version")]
    public string AnalyzerVersion { get; set; } = "0.2.0";

    [JsonPropertyName("summary")]
    public AnalysisSummary Summary { get; set; } = new();

    [JsonPropertyName("files")]
    public List<FileNode> Files { get; set; } = new();

    [JsonPropertyName("errors")]
    public List<AnalysisError> Errors { get; set; } = new();

    [JsonPropertyName("diagnostics")]
    public List<AnalysisDiagnostic> Diagnostics { get; set; } = new();
}

public sealed class AnalysisDiagnostic
{
    [JsonPropertyName("path")]
    public string Path { get; set; } = "";

    [JsonPropertyName("kind")]
    public string Kind { get; set; } = "syntax";

    [JsonPropertyName("line")]
    public int Line { get; set; }

    [JsonPropertyName("message")]
    public string Message { get; set; } = "";
}

public sealed class AnalysisSummary
{
    [JsonPropertyName("total_files")]
    public int TotalFiles { get; set; }

    [JsonPropertyName("total_classes")]
    public int TotalClasses { get; set; }

    [JsonPropertyName("total_methods")]
    public int TotalMethods { get; set; }

    [JsonPropertyName("total_loc")]
    public int TotalLoc { get; set; }

    [JsonPropertyName("elapsed_ms")]
    public long ElapsedMs { get; set; }
}

public sealed class FileNode
{
    [JsonPropertyName("path")]
    public string Path { get; set; } = "";

    [JsonPropertyName("relative_path")]
    public string RelativePath { get; set; } = "";

    [JsonPropertyName("loc")]
    public int Loc { get; set; }

    [JsonPropertyName("classes")]
    public List<ClassNode> Classes { get; set; } = new();
}

public sealed class ClassNode
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("fully_qualified_name")]
    public string FullyQualifiedName { get; set; } = "";

    [JsonPropertyName("namespace")]
    public string? Namespace { get; set; }

    [JsonPropertyName("kind")]
    public string Kind { get; set; } = "class"; // class | struct | interface | record | enum

    [JsonPropertyName("start_line")]
    public int StartLine { get; set; }

    [JsonPropertyName("end_line")]
    public int EndLine { get; set; }

    [JsonPropertyName("is_static")]
    public bool IsStatic { get; set; }

    [JsonPropertyName("is_partial")]
    public bool IsPartial { get; set; }

    [JsonPropertyName("is_abstract")]
    public bool IsAbstract { get; set; }

    [JsonPropertyName("base_types")]
    public List<string> BaseTypes { get; set; } = new();

    /// <summary>
    /// 클래스 본문에서 syntactic 수준으로 발견된 외부 타입 이름의 집합.
    /// CBO 계산의 기반이 된다. semantic 분석 도입 시 정밀도가 향상된다.
    /// </summary>
    [JsonPropertyName("referenced_types")]
    public List<string> ReferencedTypes { get; set; } = new();

    /// <summary>
    /// 본 클래스 안에서 발견된 static 멤버 접근 표현 (예: "GameManager.CurrentPlayer").
    /// GlobalState 메트릭의 입력.
    /// </summary>
    [JsonPropertyName("static_member_accesses")]
    public List<string> StaticMemberAccesses { get; set; } = new();

    /// <summary>
    /// 본 클래스 안에서 발견된 싱글톤형 인스턴스 접근 (예: "Foo.Instance").
    /// </summary>
    [JsonPropertyName("singleton_accesses")]
    public List<string> SingletonAccesses { get; set; } = new();

    [JsonPropertyName("methods")]
    public List<MethodNode> Methods { get; set; } = new();
}

public sealed class MethodNode
{
    [JsonPropertyName("symbol_id")]
    public string? SymbolId { get; set; }

    [JsonPropertyName("invoked_symbols")]
    public List<string> InvokedSymbols { get; set; } = new();

    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("signature")]
    public string Signature { get; set; } = "";

    [JsonPropertyName("start_line")]
    public int StartLine { get; set; }

    [JsonPropertyName("end_line")]
    public int EndLine { get; set; }

    [JsonPropertyName("parameter_count")]
    public int ParameterCount { get; set; }

    [JsonPropertyName("return_type")]
    public string ReturnType { get; set; } = "";

    [JsonPropertyName("is_static")]
    public bool IsStatic { get; set; }

    [JsonPropertyName("is_async")]
    public bool IsAsync { get; set; }

    [JsonPropertyName("is_override")]
    public bool IsOverride { get; set; }

    [JsonPropertyName("cyclomatic_complexity")]
    public int CyclomaticComplexity { get; set; }

    [JsonPropertyName("loc")]
    public int Loc { get; set; }

    /// <summary>
    /// 메서드 본문에서 호출된 메서드 이름 목록 (syntactic level).
    /// 형태는 "Foo" 또는 "obj.Foo" 등 원본 식별자 그대로이며, semantic 도입 시 정확한 심볼로 해석된다.
    /// 게임 루프 reachability 계산의 입력으로 사용된다.
    /// </summary>
    [JsonPropertyName("invoked_names")]
    public List<string> InvokedNames { get; set; } = new();

    /// <summary>
    /// 본 메서드가 게임 루프 진입점(Tick/Update/Render/Draw/On*) 패턴에 해당하는지 여부.
    /// GameLoopCentrality 계산의 시드(seed).
    /// </summary>
    [JsonPropertyName("is_game_loop_entry")]
    public bool IsGameLoopEntry { get; set; }
}

public sealed class AnalysisError
{
    [JsonPropertyName("path")]
    public string Path { get; set; } = "";

    [JsonPropertyName("message")]
    public string Message { get; set; } = "";
}
