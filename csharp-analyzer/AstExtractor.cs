// 단일 C# 파일의 SyntaxTree로부터 클래스·메서드 노드를 추출한다.
//
// 본 추출기는 W1 단계에서는 syntactic 분석만 수행한다.
// MSBuildWorkspace를 사용한 semantic 분석(타입 해석, 호출 그래프)은 W2 이후에 별도 모듈로 추가한다.

namespace CSharpAnalyzer;

using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

public static class AstExtractor
{
    public static FileNode ExtractFromFile(string absolutePath, string? relativePath = null)
    {
        var source = File.ReadAllText(absolutePath);
        var tree = CSharpSyntaxTree.ParseText(source, path: absolutePath);
        var root = (CompilationUnitSyntax)tree.GetRoot();

        var fileNode = new FileNode
        {
            Path = absolutePath,
            RelativePath = relativePath ?? absolutePath,
            Loc = CountLoc(source),
        };

        foreach (var typeDecl in root.DescendantNodes().OfType<BaseTypeDeclarationSyntax>())
        {
            var classNode = ExtractTypeDeclaration(typeDecl);
            if (classNode != null)
            {
                fileNode.Classes.Add(classNode);
            }
        }

        return fileNode;
    }

    private static ClassNode? ExtractTypeDeclaration(BaseTypeDeclarationSyntax typeDecl)
    {
        var lineSpan = typeDecl.GetLocation().GetLineSpan();
        var modifiers = typeDecl.Modifiers.Select(m => m.Text).ToHashSet();

        var classNode = new ClassNode
        {
            Name = typeDecl.Identifier.Text,
            FullyQualifiedName = BuildFullyQualifiedName(typeDecl),
            Namespace = GetEnclosingNamespace(typeDecl),
            Kind = DetermineKind(typeDecl),
            StartLine = lineSpan.StartLinePosition.Line + 1,
            EndLine = lineSpan.EndLinePosition.Line + 1,
            IsStatic = modifiers.Contains("static"),
            IsPartial = modifiers.Contains("partial"),
            IsAbstract = modifiers.Contains("abstract"),
        };

        // base types
        if (typeDecl.BaseList != null)
        {
            foreach (var bt in typeDecl.BaseList.Types)
            {
                classNode.BaseTypes.Add(bt.Type.ToString());
            }
        }

        // 클래스 본문 전체를 순회하여 참조 타입 / 정적 접근 / 싱글톤 접근을 수집한다.
        var classWalker = new MethodBodyWalker();
        classWalker.Visit(typeDecl);
        classNode.ReferencedTypes.AddRange(classWalker.CreatedTypes.OrderBy(s => s));
        classNode.StaticMemberAccesses.AddRange(classWalker.StaticAccesses.OrderBy(s => s));
        classNode.SingletonAccesses.AddRange(classWalker.SingletonAccesses.OrderBy(s => s));

        // methods — 중첩 타입의 메서드는 그 타입에 귀속되므로 직접 자식만 본다.
        if (typeDecl is TypeDeclarationSyntax tds)
        {
            foreach (var memberDecl in tds.Members)
            {
                if (memberDecl is MethodDeclarationSyntax method)
                {
                    classNode.Methods.Add(ExtractMethod(method));
                }
                else if (memberDecl is ConstructorDeclarationSyntax ctor)
                {
                    classNode.Methods.Add(ExtractConstructor(ctor));
                }
            }
        }

        return classNode;
    }

    private static MethodNode ExtractMethod(MethodDeclarationSyntax method)
    {
        var lineSpan = method.GetLocation().GetLineSpan();
        var modifiers = method.Modifiers.Select(m => m.Text).ToHashSet();

        var ccWalker = new CyclomaticComplexityWalker();
        var bodyWalker = new MethodBodyWalker();
        if (method.Body != null)
        {
            ccWalker.Visit(method.Body);
            bodyWalker.Visit(method.Body);
        }
        else if (method.ExpressionBody != null)
        {
            ccWalker.Visit(method.ExpressionBody);
            bodyWalker.Visit(method.ExpressionBody);
        }

        var node = new MethodNode
        {
            Name = method.Identifier.Text,
            Signature = BuildSignature(method),
            StartLine = lineSpan.StartLinePosition.Line + 1,
            EndLine = lineSpan.EndLinePosition.Line + 1,
            ParameterCount = method.ParameterList.Parameters.Count,
            ReturnType = method.ReturnType.ToString(),
            IsStatic = modifiers.Contains("static"),
            IsAsync = modifiers.Contains("async"),
            IsOverride = modifiers.Contains("override"),
            CyclomaticComplexity = ccWalker.Complexity,
            Loc = lineSpan.EndLinePosition.Line - lineSpan.StartLinePosition.Line + 1,
            IsGameLoopEntry = IsGameLoopEntryName(method.Identifier.Text),
        };

        // 호출된 메서드 이름을 결정적인 순서로 저장한다.
        node.InvokedNames.AddRange(bodyWalker.InvokedNames.OrderBy(s => s));
        return node;
    }

    /// <summary>
    /// 메서드 이름이 게임 루프 진입점 패턴에 해당하는지 판정한다.
    /// 본 작품은 OpenRA 및 일반 C# 게임 코드를 우선 대상으로 하며,
    /// Unity 전용(예: Awake, FixedUpdate)은 §6.1 확장 detector에서 추가한다.
    /// </summary>
    private static bool IsGameLoopEntryName(string name)
    {
        if (string.IsNullOrEmpty(name)) return false;

        // 정확히 일치하는 진입점 이름.
        if (name is "Tick" or "Update" or "LateUpdate" or "FixedUpdate"
            or "Render" or "Draw" or "Awake" or "Start"
            or "MainLoop" or "GameLoop")
            return true;

        // 패턴: "On*" (이벤트/콜백 핸들러), "*Tick", "*Frame"
        if (name.StartsWith("On", StringComparison.Ordinal) && name.Length > 2 && char.IsUpper(name[2]))
            return true;
        if (name.EndsWith("Tick", StringComparison.Ordinal) && name.Length > 4)
            return true;
        if (name.EndsWith("Frame", StringComparison.Ordinal) && name.Length > 5)
            return true;

        return false;
    }

    private static MethodNode ExtractConstructor(ConstructorDeclarationSyntax ctor)
    {
        var lineSpan = ctor.GetLocation().GetLineSpan();
        var modifiers = ctor.Modifiers.Select(m => m.Text).ToHashSet();

        var ccWalker = new CyclomaticComplexityWalker();
        var bodyWalker = new MethodBodyWalker();
        if (ctor.Body != null)
        {
            ccWalker.Visit(ctor.Body);
            bodyWalker.Visit(ctor.Body);
        }
        else if (ctor.ExpressionBody != null)
        {
            ccWalker.Visit(ctor.ExpressionBody);
            bodyWalker.Visit(ctor.ExpressionBody);
        }

        var node = new MethodNode
        {
            Name = ".ctor",
            Signature = $"{ctor.Identifier.Text}({string.Join(", ", ctor.ParameterList.Parameters.Select(p => p.Type?.ToString() ?? "?"))})",
            StartLine = lineSpan.StartLinePosition.Line + 1,
            EndLine = lineSpan.EndLinePosition.Line + 1,
            ParameterCount = ctor.ParameterList.Parameters.Count,
            ReturnType = "void",
            IsStatic = modifiers.Contains("static"),
            IsAsync = false,
            IsOverride = false,
            CyclomaticComplexity = ccWalker.Complexity,
            Loc = lineSpan.EndLinePosition.Line - lineSpan.StartLinePosition.Line + 1,
            IsGameLoopEntry = false,
        };
        node.InvokedNames.AddRange(bodyWalker.InvokedNames.OrderBy(s => s));
        return node;
    }

    private static string BuildSignature(MethodDeclarationSyntax method)
    {
        var parameters = string.Join(", ", method.ParameterList.Parameters.Select(p => $"{p.Type?.ToString() ?? "?"} {p.Identifier.Text}"));
        return $"{method.ReturnType} {method.Identifier.Text}({parameters})";
    }

    private static string BuildFullyQualifiedName(BaseTypeDeclarationSyntax typeDecl)
    {
        var ns = GetEnclosingNamespace(typeDecl);
        var typeName = typeDecl.Identifier.Text;

        // 중첩 타입의 경우 부모 타입 이름도 포함
        var enclosingTypes = new List<string>();
        SyntaxNode? parent = typeDecl.Parent;
        while (parent != null)
        {
            if (parent is BaseTypeDeclarationSyntax parentType)
            {
                enclosingTypes.Insert(0, parentType.Identifier.Text);
            }
            parent = parent.Parent;
        }

        var nestedPath = enclosingTypes.Count > 0 ? string.Join(".", enclosingTypes) + "." : "";
        return string.IsNullOrEmpty(ns) ? $"{nestedPath}{typeName}" : $"{ns}.{nestedPath}{typeName}";
    }

    private static string? GetEnclosingNamespace(SyntaxNode node)
    {
        SyntaxNode? parent = node.Parent;
        while (parent != null)
        {
            if (parent is NamespaceDeclarationSyntax nsDecl)
                return nsDecl.Name.ToString();
            if (parent is FileScopedNamespaceDeclarationSyntax fsNs)
                return fsNs.Name.ToString();
            parent = parent.Parent;
        }
        return null;
    }

    private static string DetermineKind(BaseTypeDeclarationSyntax typeDecl) => typeDecl switch
    {
        ClassDeclarationSyntax => "class",
        StructDeclarationSyntax => "struct",
        InterfaceDeclarationSyntax => "interface",
        RecordDeclarationSyntax r => r.ClassOrStructKeyword.Text == "struct" ? "record struct" : "record",
        EnumDeclarationSyntax => "enum",
        _ => "type",
    };

    private static int CountLoc(string source)
    {
        // 비어있지 않고 주석만으로 구성되지 않은 줄을 LOC로 본다.
        var lines = source.Split('\n');
        var loc = 0;
        var inBlockComment = false;
        foreach (var raw in lines)
        {
            var line = raw.Trim();
            if (string.IsNullOrEmpty(line)) continue;

            if (inBlockComment)
            {
                if (line.Contains("*/")) inBlockComment = false;
                continue;
            }
            if (line.StartsWith("/*"))
            {
                if (!line.Contains("*/")) inBlockComment = true;
                continue;
            }
            if (line.StartsWith("//")) continue;

            loc++;
        }
        return loc;
    }
}
