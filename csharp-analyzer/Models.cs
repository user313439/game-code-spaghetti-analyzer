// 분석 결과를 JSON으로 직렬화하기 위한 데이터 모델.
// 스키마 버전은 docs/ast-schema.md 와 동기화한다.

namespace CSharpAnalyzer;

using System.Text.Json.Serialization;

public sealed class AnalysisResult
{
    [JsonPropertyName("schema_version")]
    public string SchemaVersion { get; set; } = "0.1";

    [JsonPropertyName("analyzed_at")]
    public string AnalyzedAt { get; set; } = "";

    [JsonPropertyName("input_path")]
    public string InputPath { get; set; } = "";

    [JsonPropertyName("analyzer_version")]
    public string AnalyzerVersion { get; set; } = "0.1.0";

    [JsonPropertyName("summary")]
    public AnalysisSummary Summary { get; set; } = new();

    [JsonPropertyName("files")]
    public List<FileNode> Files { get; set; } = new();

    [JsonPropertyName("errors")]
    public List<AnalysisError> Errors { get; set; } = new();
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

    [JsonPropertyName("methods")]
    public List<MethodNode> Methods { get; set; } = new();
}

public sealed class MethodNode
{
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
}

public sealed class AnalysisError
{
    [JsonPropertyName("path")]
    public string Path { get; set; } = "";

    [JsonPropertyName("message")]
    public string Message { get; set; } = "";
}
