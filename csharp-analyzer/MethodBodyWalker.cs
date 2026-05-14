// 메서드 본문을 순회하여 다음 시그널을 수집한다.
//
// - 호출된 메서드 이름 (InvocationExpression)
// - 객체 생성 (ObjectCreationExpression)으로 참조된 타입 이름
// - static mutable 멤버 접근 (heuristic)
// - 싱글톤형 인스턴스 접근 (예: Foo.Instance)
//
// 본 walker는 syntactic 분석만 수행하므로 정확도가 제한적이다.
// 후속 단계에서 semantic 분석(MSBuildWorkspace) 도입 시 정밀도가 향상된다.

namespace CSharpAnalyzer;

using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

public sealed class MethodBodyWalker : CSharpSyntaxWalker
{
    public HashSet<string> InvokedNames { get; } = new(StringComparer.Ordinal);
    public HashSet<string> CreatedTypes { get; } = new(StringComparer.Ordinal);
    public HashSet<string> StaticAccesses { get; } = new(StringComparer.Ordinal);
    public HashSet<string> SingletonAccesses { get; } = new(StringComparer.Ordinal);

    public override void VisitInvocationExpression(InvocationExpressionSyntax node)
    {
        string callee = node.Expression switch
        {
            IdentifierNameSyntax id => id.Identifier.Text,
            MemberAccessExpressionSyntax ma => $"{ma.Expression}.{ma.Name.Identifier.Text}",
            GenericNameSyntax gn => gn.Identifier.Text,
            _ => node.Expression.ToString(),
        };
        if (!string.IsNullOrWhiteSpace(callee)) InvokedNames.Add(callee);

        base.VisitInvocationExpression(node);
    }

    public override void VisitObjectCreationExpression(ObjectCreationExpressionSyntax node)
    {
        var typeName = node.Type.ToString();
        if (!string.IsNullOrWhiteSpace(typeName)) CreatedTypes.Add(typeName);
        base.VisitObjectCreationExpression(node);
    }

    public override void VisitMemberAccessExpression(MemberAccessExpressionSyntax node)
    {
        // 다음 두 가지 휴리스틱을 적용한다.
        //
        // (1) `Type.MEMBER` 형태이고 Type이 대문자로 시작하면 static 접근 후보로 본다.
        //     (semantic 분석이 없으면 인스턴스 vs 정적 구분은 정확히 알 수 없으므로 보수적 추정.)
        // (2) `Foo.Instance` 처럼 마지막 멤버 이름이 일반적인 싱글톤 시그니처면
        //     싱글톤 접근으로 분류한다.
        var memberName = node.Name.Identifier.Text;
        var leftExpr = node.Expression.ToString();

        if (IsLikelyType(leftExpr))
        {
            StaticAccesses.Add($"{leftExpr}.{memberName}");
        }

        if (IsSingletonAccessor(memberName))
        {
            SingletonAccesses.Add($"{leftExpr}.{memberName}");
        }

        base.VisitMemberAccessExpression(node);
    }

    private static bool IsLikelyType(string expression)
    {
        // 좌측 표현이 단일 식별자이고 PascalCase로 시작하면 타입으로 추정한다.
        if (string.IsNullOrEmpty(expression)) return false;
        if (!char.IsUpper(expression[0])) return false;
        // 단순 식별자이거나 점으로만 구성된 경로 (Foo, Foo.Bar)면 타입성으로 본다.
        foreach (var ch in expression)
        {
            if (!(char.IsLetterOrDigit(ch) || ch == '_' || ch == '.')) return false;
        }
        return true;
    }

    private static bool IsSingletonAccessor(string memberName)
    {
        // 보편적으로 사용되는 싱글톤 접근자 이름.
        return memberName is "Instance" or "Current" or "Singleton" or "Shared"
            or "Default" or "Main" or "Active";
    }
}
