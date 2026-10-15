// csharp-analyzer
//
// 입력: 단일 .cs 파일, .cs 파일이 포함된 디렉토리, 또는 .sln 솔루션 경로
// 출력: AST·메트릭 결과를 담은 JSON (stdout 또는 --output 으로 지정된 파일)
//
// 분석 방식: 모든 .cs 파일을 한 CSharpCompilation 으로 묶어 SemanticModel 을
// 활용한다 (W14 후속 개선 1-A). MSBuildWorkspace 와 csproj references 없이
// 같은 프로젝트 내 type/method symbol 의 정확한 FQN 을 해석한다. 외부 dll
// 의 reference 는 syntactic fallback 으로 처리.

namespace CSharpAnalyzer;

using System.Diagnostics;
using System.Text.Json;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;

internal sealed class Program
{
    private static int Main(string[] args)
    {
        try
        {
            var options = CliOptions.Parse(args);
            if (options == null)
            {
                PrintUsage();
                return 2;
            }

            if (!File.Exists(options.InputPath) && !Directory.Exists(options.InputPath))
            {
                Console.Error.WriteLine($"[error] input path not found: {options.InputPath}");
                return 1;
            }

            var stopwatch = Stopwatch.StartNew();
            var result = new AnalysisResult
            {
                AnalyzedAt = DateTime.UtcNow.ToString("o"),
                InputPath = Path.GetFullPath(options.InputPath),
            };

            var files = CollectCSharpFiles(options.InputPath, options.ExcludePatterns, result.Errors);
            if (files.Count == 0)
            {
                Console.Error.WriteLine($"[warn] no .cs files found under: {options.InputPath}");
            }

            var rootForRelative = Directory.Exists(options.InputPath)
                ? Path.GetFullPath(options.InputPath)
                : Path.GetDirectoryName(Path.GetFullPath(options.InputPath)) ?? options.InputPath;

            // 1) 모든 파일을 SyntaxTree 로 파싱.
            var trees = new List<(string AbsPath, string Relative, SyntaxTree Tree)>();
            foreach (var file in files)
            {
                try
                {
                    var source = File.ReadAllText(file);
                    var tree = CSharpSyntaxTree.ParseText(source, path: file);
                    var syntaxError = tree.GetDiagnostics().FirstOrDefault(d => d.Severity == DiagnosticSeverity.Error);
                    if (syntaxError != null)
                    {
                        result.Diagnostics.Add(new AnalysisDiagnostic
                        {
                            Path = file,
                            Line = syntaxError.Location.GetLineSpan().StartLinePosition.Line + 1,
                            Message = $"{syntaxError.Id}: {syntaxError.GetMessage()} — 복구 가능한 부분을 추출했으므로 결과가 불완전할 수 있습니다.",
                        });
                    }
                    var relative = Path.GetRelativePath(rootForRelative, file).Replace('\\', '/');
                    trees.Add((file, relative, tree));
                }
                catch (Exception ex)
                {
                    result.Errors.Add(new AnalysisError { Path = file, Message = ex.Message });
                }
            }

            // 2) 모든 SyntaxTree 를 한 Compilation 으로 묶기. 시스템 기본 reference 만
            //    추가 — 외부 dll 은 syntactic fallback 으로 처리. csproj 자동 로드는
            //    plan §5.1 의 MSBuildWorkspace 도입 시 보강된다.
            var compilation = CSharpCompilation.Create(
                assemblyName: "CSharpAnalyzerCompilation",
                syntaxTrees: trees.Select(t => t.Tree),
                references: new[] {
                    MetadataReference.CreateFromFile(typeof(object).Assembly.Location),
                },
                options: new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary));

            // 3) 각 파일에 대해 SemanticModel 을 받아 추출.
            foreach (var (absPath, relative, tree) in trees)
            {
                try
                {
                    var model = compilation.GetSemanticModel(tree, ignoreAccessibility: true);
                    var node = AstExtractor.ExtractFromTree(absPath, relative, tree, model);
                    result.Files.Add(node);
                }
                catch (Exception ex)
                {
                    result.Errors.Add(new AnalysisError { Path = absPath, Message = ex.Message });
                }
            }

            // summary
            result.Summary.TotalFiles = result.Files.Count;
            result.Summary.TotalClasses = result.Files.Sum(f => f.Classes.Count);
            result.Summary.TotalMethods = result.Files.Sum(f => f.Classes.Sum(c => c.Methods.Count));
            result.Summary.TotalLoc = result.Files.Sum(f => f.Loc);
            stopwatch.Stop();
            result.Summary.ElapsedMs = stopwatch.ElapsedMilliseconds;

            // serialize
            var jsonOptions = new JsonSerializerOptions
            {
                WriteIndented = true,
                DefaultIgnoreCondition = System.Text.Json.Serialization.JsonIgnoreCondition.WhenWritingNull,
            };
            var json = JsonSerializer.Serialize(result, jsonOptions);

            if (string.IsNullOrEmpty(options.OutputPath))
            {
                Console.Out.WriteLine(json);
            }
            else
            {
                var outDir = Path.GetDirectoryName(Path.GetFullPath(options.OutputPath));
                if (!string.IsNullOrEmpty(outDir) && !Directory.Exists(outDir))
                    Directory.CreateDirectory(outDir);
                File.WriteAllText(options.OutputPath, json);
                Console.Error.WriteLine($"[ok] wrote {options.OutputPath} (files={result.Summary.TotalFiles}, classes={result.Summary.TotalClasses}, methods={result.Summary.TotalMethods}, errors={result.Errors.Count}, elapsed={result.Summary.ElapsedMs}ms)");
            }

            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[fatal] {ex.GetType().Name}: {ex.Message}");
            Console.Error.WriteLine(ex.StackTrace);
            return 1;
        }
    }

    private static List<string> CollectCSharpFiles(string inputPath, IReadOnlyList<string> excludePatterns, List<AnalysisError> errors)
    {
        var collected = new List<string>();

        if (File.Exists(inputPath))
        {
            if (inputPath.EndsWith(".cs", StringComparison.OrdinalIgnoreCase))
                collected.Add(Path.GetFullPath(inputPath));
            return collected;
        }

        // 디렉토리 처리
        var defaultExclude = new[] { "bin", "obj", ".git", ".vs", "packages", "node_modules", "TestResults" };
        var allExcludes = defaultExclude.Concat(excludePatterns).ToHashSet(StringComparer.OrdinalIgnoreCase);

        foreach (var file in EnumerateCSharpFiles(inputPath, allExcludes, errors))
        {
            collected.Add(file);
        }
        return collected;
    }

    private static IEnumerable<string> EnumerateCSharpFiles(string dir, HashSet<string> excludes, List<AnalysisError> errors)
    {
        IEnumerable<string> subdirs;
        try { subdirs = Directory.GetDirectories(dir); }
        catch (Exception ex) { errors.Add(new AnalysisError { Path = dir, Message = ex.Message }); yield break; }

        foreach (var sub in subdirs)
        {
            var name = Path.GetFileName(sub);
            if (excludes.Contains(name)) continue;
            foreach (var f in EnumerateCSharpFiles(sub, excludes, errors)) yield return f;
        }

        IEnumerable<string> files;
        try { files = Directory.GetFiles(dir, "*.cs"); }
        catch (Exception ex) { errors.Add(new AnalysisError { Path = dir, Message = ex.Message }); yield break; }

        foreach (var f in files) yield return Path.GetFullPath(f);
    }

    private static void PrintUsage()
    {
        Console.Error.WriteLine("Usage: csharp-analyzer --input <path> [--output <path>] [--exclude <dirname> ...]");
        Console.Error.WriteLine("");
        Console.Error.WriteLine("  --input    Path to a .cs file, a directory, or a .sln file (W2+).");
        Console.Error.WriteLine("  --output   Output JSON path. If omitted, writes JSON to stdout.");
        Console.Error.WriteLine("  --exclude  Additional directory names to exclude (repeatable).");
        Console.Error.WriteLine("             Defaults: bin obj .git .vs packages node_modules TestResults");
    }
}

internal sealed class CliOptions
{
    public string InputPath { get; set; } = "";
    public string OutputPath { get; set; } = "";
    public List<string> ExcludePatterns { get; } = new();

    public static CliOptions? Parse(string[] args)
    {
        if (args.Length == 0) return null;

        var opts = new CliOptions();
        for (int i = 0; i < args.Length; i++)
        {
            var arg = args[i];
            switch (arg)
            {
                case "--input":
                case "-i":
                    if (++i >= args.Length) return null;
                    opts.InputPath = args[i];
                    break;
                case "--output":
                case "-o":
                    if (++i >= args.Length) return null;
                    opts.OutputPath = args[i];
                    break;
                case "--exclude":
                case "-x":
                    if (++i >= args.Length) return null;
                    opts.ExcludePatterns.Add(args[i]);
                    break;
                case "--help":
                case "-h":
                    return null;
                default:
                    // 명시적 옵션이 없으면 첫 위치 인자를 input으로 본다.
                    if (string.IsNullOrEmpty(opts.InputPath)) opts.InputPath = arg;
                    else if (string.IsNullOrEmpty(opts.OutputPath)) opts.OutputPath = arg;
                    break;
            }
        }

        return string.IsNullOrEmpty(opts.InputPath) ? null : opts;
    }
}
