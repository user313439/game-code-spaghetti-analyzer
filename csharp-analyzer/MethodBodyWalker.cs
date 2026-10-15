// SemanticModel 기반 walker (W14 후속 개선 1-A).
//
// 본 walker 는 다음을 수집한다.
//   InvokedNames     — 호출된 메서드의 정확한 ContainingType FQN + 메서드 이름
//                      (예: "OpenRA.Network.Server.AcceptConnection"). semantic 실패 시
//                      syntactic 텍스트로 fallback.
//   CreatedTypes     — ObjectCreation 의 정확한 type FQN. semantic 실패 시 텍스트.
//   StaticAccesses   — semantic 으로 IsStatic 확인된 멤버 접근. syntactic 휴리스틱은
//                      fallback.
//   SingletonAccesses — 이름 휴리스틱 그대로 (Instance / Current 등).

namespace CSharpAnalyzer;

using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

public sealed class MethodBodyWalker : CSharpSyntaxWalker
{
    private readonly SemanticModel _model;

    public MethodBodyWalker(SemanticModel model)
    {
        _model = model;
    }

    public HashSet<string> InvokedNames { get; } = new(StringComparer.Ordinal);
    public HashSet<string> InvokedSymbols { get; } = new(StringComparer.Ordinal);
    public HashSet<string> CreatedTypes { get; } = new(StringComparer.Ordinal);
    public HashSet<string> StaticAccesses { get; } = new(StringComparer.Ordinal);
    public HashSet<string> SingletonAccesses { get; } = new(StringComparer.Ordinal);

    public override void VisitInvocationExpression(InvocationExpressionSyntax node)
    {
        // semantic 으로 호출 대상 method symbol 을 해석. 성공하면 ContainingType
        // 의 정확한 FQN 을 prefix 로 붙여 같은 프로젝트 내 클래스 그래프 매칭에
        // 활용된다 (예: "Foo.Bar.Method" 형태). 실패 시 syntactic 텍스트.
        var info = _model.GetSymbolInfo(node);
        ISymbol? sym = info.Symbol;
        string callee;
        if (sym is IMethodSymbol method && method.ContainingType != null)
        {
            // 별도 노드로 추출하지 않는 로컬 함수를 동명 클래스 메서드로 연결하지 않는다.
            if (method.MethodKind == MethodKind.LocalFunction)
            {
                base.VisitInvocationExpression(node);
                return;
            }
            var symbolId = (method.ReducedFrom ?? method).OriginalDefinition.GetDocumentationCommentId();
            if (symbolId != null) InvokedSymbols.Add(symbolId);
            var typeFqn = AstExtractor.FormatFqn(method.ContainingType);
            callee = string.IsNullOrEmpty(typeFqn) ? method.Name : $"{typeFqn}.{method.Name}";
        }
        else
        {
            callee = node.Expression switch
            {
                IdentifierNameSyntax id => id.Identifier.Text,
                MemberAccessExpressionSyntax ma => $"{ma.Expression}.{ma.Name.Identifier.Text}",
                GenericNameSyntax gn => gn.Identifier.Text,
                _ => node.Expression.ToString(),
            };
        }
        if (!string.IsNullOrWhiteSpace(callee)) InvokedNames.Add(callee);

        base.VisitInvocationExpression(node);
    }

    public override void VisitObjectCreationExpression(ObjectCreationExpressionSyntax node)
    {
        // semantic 으로 type symbol 해석. 성공하면 FQN, 실패 시 텍스트.
        var typeInfo = _model.GetTypeInfo(node.Type);
        if (typeInfo.Type is INamedTypeSymbol named)
        {
            CreatedTypes.Add(AstExtractor.FormatFqn(named));
        }
        else
        {
            var typeName = node.Type.ToString();
            if (!string.IsNullOrWhiteSpace(typeName)) CreatedTypes.Add(typeName);
        }
        base.VisitObjectCreationExpression(node);
    }

    public override void VisitMemberAccessExpression(MemberAccessExpressionSyntax node)
    {
        var memberName = node.Name.Identifier.Text;
        var leftExpr = node.Expression.ToString();

        // semantic 으로 static 멤버 접근을 정확히 판정.
        var symbolInfo = _model.GetSymbolInfo(node);
        ISymbol? sym = symbolInfo.Symbol ?? symbolInfo.CandidateSymbols.FirstOrDefault();
        bool isStaticAccess = sym switch
        {
            IFieldSymbol f => f.IsStatic && !f.IsConst && !f.IsReadOnly,
            IPropertySymbol p => p.IsStatic,
            IMethodSymbol m => m.IsStatic,
            null => IsLikelyType(leftExpr),  // semantic 실패 시 휴리스틱
            _ => false,
        };
        if (isStaticAccess)
        {
            // semantic 으로 containing type FQN 까지 얻을 수 있으면 그것을 prefix 로
            string prefix = leftExpr;
            if (sym?.ContainingType is INamedTypeSymbol containing)
            {
                prefix = AstExtractor.FormatFqn(containing);
            }
            StaticAccesses.Add($"{prefix}.{memberName}");
        }

        if (IsSingletonAccessor(memberName))
        {
            SingletonAccesses.Add($"{leftExpr}.{memberName}");
        }

        base.VisitMemberAccessExpression(node);
    }

    private static bool IsLikelyType(string expression)
    {
        if (string.IsNullOrEmpty(expression)) return false;
        if (!char.IsUpper(expression[0])) return false;
        foreach (var ch in expression)
        {
            if (!(char.IsLetterOrDigit(ch) || ch == '_' || ch == '.')) return false;
        }
        return true;
    }

    private static bool IsSingletonAccessor(string memberName)
    {
        return memberName is "Instance" or "Current" or "Singleton" or "Shared"
            or "Default" or "Main" or "Active";
    }
}
