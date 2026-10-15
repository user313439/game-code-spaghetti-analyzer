// SemanticModel 기반 AST 추출 (W14 후속 개선 1-A).
//
// 같은 Compilation 안의 type/method symbol 은 SemanticModel 로 정확한 FQN 을
// 해석한다. 외부 dll 의 type 은 SymbolInfo 가 null 이거나 partial 일 수 있어
// 그 경우엔 syntactic 텍스트로 fallback 한다.

namespace CSharpAnalyzer;

using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

public static class AstExtractor
{
    public static FileNode ExtractFromTree(
        string absolutePath,
        string relativePath,
        SyntaxTree tree,
        SemanticModel model)
    {
        var source = tree.GetText().ToString();
        var root = (CompilationUnitSyntax)tree.GetRoot();

        var fileNode = new FileNode
        {
            Path = absolutePath,
            RelativePath = relativePath ?? absolutePath,
            Loc = CountLoc(source),
        };

        foreach (var typeDecl in root.DescendantNodes().OfType<BaseTypeDeclarationSyntax>())
        {
            var classNode = ExtractTypeDeclaration(typeDecl, model);
            if (classNode != null)
            {
                fileNode.Classes.Add(classNode);
            }
        }

        return fileNode;
    }

    // 후방 호환: 단일 파일을 독립적으로 파싱하는 옛 진입점. semantic 없이 syntactic 으로만 분석.
    public static FileNode ExtractFromFile(string absolutePath, string? relativePath = null)
    {
        var source = File.ReadAllText(absolutePath);
        var tree = CSharpSyntaxTree.ParseText(source, path: absolutePath);
        var compilation = CSharpCompilation.Create(
            "Standalone",
            new[] { tree },
            new[] { MetadataReference.CreateFromFile(typeof(object).Assembly.Location) });
        var model = compilation.GetSemanticModel(tree, ignoreAccessibility: true);
        return ExtractFromTree(absolutePath, relativePath ?? absolutePath, tree, model);
    }

    private static ClassNode? ExtractTypeDeclaration(BaseTypeDeclarationSyntax typeDecl, SemanticModel model)
    {
        var lineSpan = typeDecl.GetLocation().GetLineSpan();
        var modifiers = typeDecl.Modifiers.Select(m => m.Text).ToHashSet();

        // semantic 으로 type symbol 을 받아 정확한 FQN 을 구성
        var typeSymbol = model.GetDeclaredSymbol(typeDecl) as INamedTypeSymbol;
        var fqn = typeSymbol != null
            ? FormatFqn(typeSymbol)
            : BuildFullyQualifiedNameSyntactic(typeDecl);
        var ns = typeSymbol?.ContainingNamespace?.IsGlobalNamespace == false
            ? typeSymbol.ContainingNamespace.ToDisplayString()
            : GetEnclosingNamespaceSyntactic(typeDecl);

        var classNode = new ClassNode
        {
            Name = typeDecl.Identifier.Text,
            FullyQualifiedName = fqn,
            Namespace = string.IsNullOrEmpty(ns) ? null : ns,
            Kind = DetermineKind(typeDecl),
            StartLine = lineSpan.StartLinePosition.Line + 1,
            EndLine = lineSpan.EndLinePosition.Line + 1,
            IsStatic = modifiers.Contains("static"),
            IsPartial = modifiers.Contains("partial"),
            IsAbstract = modifiers.Contains("abstract"),
        };

        // base types — semantic 으로 base + interfaces 를 FQN 으로 추출
        if (typeSymbol != null)
        {
            if (typeSymbol.BaseType != null && typeSymbol.BaseType.SpecialType != SpecialType.System_Object)
            {
                classNode.BaseTypes.Add(FormatFqn(typeSymbol.BaseType));
            }
            foreach (var iface in typeSymbol.Interfaces)
            {
                classNode.BaseTypes.Add(FormatFqn(iface));
            }
        }
        else if (typeDecl.BaseList != null)
        {
            foreach (var bt in typeDecl.BaseList.Types)
            {
                classNode.BaseTypes.Add(bt.Type.ToString());
            }
        }

        // 클래스 본문 전체를 순회하여 참조 타입 / 정적 접근 / 싱글톤 접근을 수집
        var classWalker = new MethodBodyWalker(model);
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
                    classNode.Methods.Add(ExtractMethod(method, model));
                }
                else if (memberDecl is ConstructorDeclarationSyntax ctor)
                {
                    classNode.Methods.Add(ExtractConstructor(ctor, model));
                }
            }
        }

        return classNode;
    }

    private static MethodNode ExtractMethod(MethodDeclarationSyntax method, SemanticModel model)
    {
        var lineSpan = method.GetLocation().GetLineSpan();
        var modifiers = method.Modifiers.Select(m => m.Text).ToHashSet();

        var ccWalker = new CyclomaticComplexityWalker();
        var bodyWalker = new MethodBodyWalker(model);
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
            SymbolId = (model.GetDeclaredSymbol(method) as IMethodSymbol)?.OriginalDefinition.GetDocumentationCommentId(),
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

        node.InvokedNames.AddRange(bodyWalker.InvokedNames.OrderBy(s => s));
        node.InvokedSymbols.AddRange(bodyWalker.InvokedSymbols.OrderBy(s => s));
        return node;
    }

    private static bool IsGameLoopEntryName(string name)
    {
        if (string.IsNullOrEmpty(name)) return false;

        if (name is "Tick" or "Update" or "LateUpdate" or "FixedUpdate"
            or "Render" or "Draw" or "Awake" or "Start"
            or "MainLoop" or "GameLoop")
            return true;

        if (name.StartsWith("On", StringComparison.Ordinal) && name.Length > 2 && char.IsUpper(name[2]))
            return true;
        if (name.EndsWith("Tick", StringComparison.Ordinal) && name.Length > 4)
            return true;
        if (name.EndsWith("Frame", StringComparison.Ordinal) && name.Length > 5)
            return true;

        return false;
    }

    private static MethodNode ExtractConstructor(ConstructorDeclarationSyntax ctor, SemanticModel model)
    {
        var lineSpan = ctor.GetLocation().GetLineSpan();
        var modifiers = ctor.Modifiers.Select(m => m.Text).ToHashSet();

        var ccWalker = new CyclomaticComplexityWalker();
        var bodyWalker = new MethodBodyWalker(model);
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
            SymbolId = (model.GetDeclaredSymbol(ctor) as IMethodSymbol)?.OriginalDefinition.GetDocumentationCommentId(),
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
        node.InvokedSymbols.AddRange(bodyWalker.InvokedSymbols.OrderBy(s => s));
        return node;
    }

    private static string BuildSignature(MethodDeclarationSyntax method)
    {
        var parameters = string.Join(", ", method.ParameterList.Parameters.Select(p => $"{p.Type?.ToString() ?? "?"} {p.Identifier.Text}"));
        return $"{method.ReturnType} {method.Identifier.Text}({parameters})";
    }

    /// <summary>
    /// INamedTypeSymbol 의 FQN 을 "Namespace.OuterType.TypeName" 형식으로 구성.
    /// global namespace 는 빈 문자열로 처리하고 제네릭 원형의 타입 매개변수를 보존한다.
    /// </summary>
    public static string FormatFqn(INamedTypeSymbol symbol)
    {
        var format = new SymbolDisplayFormat(
            globalNamespaceStyle: SymbolDisplayGlobalNamespaceStyle.Omitted,
            typeQualificationStyle: SymbolDisplayTypeQualificationStyle.NameAndContainingTypesAndNamespaces,
            genericsOptions: SymbolDisplayGenericsOptions.IncludeTypeParameters,
            miscellaneousOptions: SymbolDisplayMiscellaneousOptions.UseSpecialTypes);
        return symbol.OriginalDefinition.ToDisplayString(format);
    }

    private static string BuildFullyQualifiedNameSyntactic(BaseTypeDeclarationSyntax typeDecl)
    {
        var ns = GetEnclosingNamespaceSyntactic(typeDecl);
        var typeName = typeDecl.Identifier.Text;

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

    private static string? GetEnclosingNamespaceSyntactic(SyntaxNode node)
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
