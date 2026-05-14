// 메서드 본문을 순회하며 Cyclomatic Complexity(CC)를 계산한다.
//
// CC = 1 + (분기 노드 수)
// 분기 노드:
//   - if, while, for, foreach, do, case label (default 제외)
//   - catch clause
//   - 삼항 연산자 ?:
//   - 논리 연산자 &&, ||
//   - null 병합 연산자 ??
//   - switch expression arm
//
// (반환문, 단순 대입, 산술 연산은 분기로 보지 않는다.)

namespace CSharpAnalyzer;

using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

public sealed class CyclomaticComplexityWalker : CSharpSyntaxWalker
{
    public int Complexity { get; private set; } = 1;

    public override void VisitIfStatement(IfStatementSyntax node)
    {
        Complexity++;
        base.VisitIfStatement(node);
    }

    public override void VisitWhileStatement(WhileStatementSyntax node)
    {
        Complexity++;
        base.VisitWhileStatement(node);
    }

    public override void VisitForStatement(ForStatementSyntax node)
    {
        Complexity++;
        base.VisitForStatement(node);
    }

    public override void VisitForEachStatement(ForEachStatementSyntax node)
    {
        Complexity++;
        base.VisitForEachStatement(node);
    }

    public override void VisitDoStatement(DoStatementSyntax node)
    {
        Complexity++;
        base.VisitDoStatement(node);
    }

    public override void VisitCaseSwitchLabel(CaseSwitchLabelSyntax node)
    {
        // 각 case는 분기를 추가한다. default는 제외.
        Complexity++;
        base.VisitCaseSwitchLabel(node);
    }

    public override void VisitCasePatternSwitchLabel(CasePatternSwitchLabelSyntax node)
    {
        Complexity++;
        base.VisitCasePatternSwitchLabel(node);
    }

    public override void VisitSwitchExpressionArm(SwitchExpressionArmSyntax node)
    {
        Complexity++;
        base.VisitSwitchExpressionArm(node);
    }

    public override void VisitCatchClause(CatchClauseSyntax node)
    {
        Complexity++;
        base.VisitCatchClause(node);
    }

    public override void VisitConditionalExpression(ConditionalExpressionSyntax node)
    {
        // 삼항 연산자 cond ? a : b
        Complexity++;
        base.VisitConditionalExpression(node);
    }

    public override void VisitBinaryExpression(BinaryExpressionSyntax node)
    {
        // &&, ||, ?? 는 단락 평가(short-circuit)로 분기를 만든다.
        var kind = node.OperatorToken.Kind();
        if (kind == SyntaxKind.AmpersandAmpersandToken ||
            kind == SyntaxKind.BarBarToken ||
            kind == SyntaxKind.QuestionQuestionToken)
        {
            Complexity++;
        }
        base.VisitBinaryExpression(node);
    }
}
