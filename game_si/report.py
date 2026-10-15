"""HTML 대시보드 생성.

단일 파일(single-file) 형태의 HTML을 생성한다. CDN 또는 외부 리소스에 의존하지 않으며,
CSS·SVG·Vanilla JavaScript만 사용한다. 파일 더블클릭으로 어디서든 열린다.

W6에서 다음 섹션을 제공한다.
    - Summary: 총 클래스/메서드 수, 등급 분포, 가중치 표
    - Hotspot Table: G-SI 상위 클래스
    - Module Table: 모듈 단위 집계

W7에서 다음 섹션이 추가될 예정이다.
    - Dependency Graph (Cytoscape.js)
    - Cycle Explorer
"""

from __future__ import annotations

import datetime as _dt
import html
import json
import math
from pathlib import Path
from typing import Any

from .metrics import MetricsResult
from .si import ScoringResult, scoring_to_dict


# 등급별 색상 (CSS, 대시보드 도넛/배지 공통)
GRADE_COLORS = {
    "A": "#3b8e5a",   # 진한 녹색
    "B": "#7fb95a",   # 연두
    "C": "#e3b341",   # 노랑
    "D": "#ef7d3c",   # 주황
    "E": "#d24343",   # 빨강
}


def generate_dashboard(
    project_name: str,
    scoring: ScoringResult,
    metrics: MetricsResult,
    output_path: Path,
    top_n: int = 30,
    advisor_data: dict | None = None,
    analysis_status: dict | None = None,
    project_subtitle: str | None = None,
) -> Path:
    """대시보드 HTML을 생성하고 경로를 반환한다.

    `advisor_data` 가 주어지면 LLM Refactoring Guide 섹션을 대시보드에 통합한다
    (plan §10.3). `reports/<case>/advisor.json` 의 구조를 그대로 받는다.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    html_doc = _render_html(project_name, scoring, metrics, top_n, advisor_data, analysis_status,
                            project_subtitle)
    output_path.write_text(html_doc, encoding="utf-8")
    return output_path


# ---------------------------------------------------------------------------
# 렌더링
# ---------------------------------------------------------------------------


def _render_html(
    project_name: str,
    scoring: ScoringResult,
    metrics: MetricsResult,
    top_n: int,
    advisor_data: dict | None = None,
    analysis_status: dict | None = None,
    project_subtitle: str | None = None,
) -> str:
    analyzed_at = _dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    hotspots = sorted(scoring.class_scores, key=lambda c: -c.si)[:top_n]
    module_rows = sorted(scoring.module_scores, key=lambda m: -m.si_max)
    si_by_fqn = {cs.fqn: cs for cs in scoring.class_scores}

    # 임베드용 데이터 — JS가 Hotspot Table 동적 렌더링, 그래프 검색 등에 사용한다.
    embedded = {
        "project": project_name,
        "analyzed_at": analyzed_at,
        "hotspot_top_n": top_n,
        "grade_colors": GRADE_COLORS,
        "all_classes": json.loads(_hotspot_data_payload(scoring)),
        "cycle_count": len(metrics.sccs),
    }
    embedded_json = json.dumps(embedded, ensure_ascii=False, indent=None, default=_json_default)

    file_units = bool(analysis_status and analysis_status.get('backend') == 'clang')
    return _unit_wording(_HTML_TEMPLATE, file_units).format(
        project_name=html.escape(project_name),
        project_subtitle=_render_project_subtitle(project_subtitle, analysis_status),
        analyzed_at=analyzed_at,
        help_box=_render_help_box(file_units),
        analysis_status=_render_analysis_status(analysis_status),
        health_hero=_render_health_hero(scoring, metrics, file_units),
        summary_cards=_render_summary_cards(scoring, metrics, file_units),
        grade_donut=_render_grade_donut(scoring.grade_distribution),
        weights_table=_render_weights_table(scoring.weights, file_units),
        hotspot_table=_render_hotspot_table(hotspots, top_n, file_units),
        module_table=_render_module_table(module_rows, file_units),
        dependency_graph=_render_dependency_graph(scoring, metrics, top_n=50, file_units=file_units),
        cycle_explorer=_render_cycle_explorer(metrics, si_by_fqn, file_units),
        refactoring_guide=_render_refactoring_guide(advisor_data),
        embedded_json=embedded_json,
    )


def _unit_wording(text: str, file_units: bool) -> str:
    """Adapt static template wording before interpolating any project/source data."""
    if not file_units:
        return text
    return (text.replace('클래스', '구현 파일').replace('메서드', '함수')
            .replace('추출된 타입 및 C/C++ 함수 묶음의 총 개수', '선택한 구현 파일 단위의 총 개수')
            .replace('분석된 모든 함수와 생성자(.ctor)의 합. enum 항목, 자동 속성은 카운트하지 않습니다.',
                     '선택한 구현 파일에 정의된 함수·생성자·소멸자의 합. 선언과 헤더 본문은 제외합니다.')
            .replace('.cs 파일과 구현 파일(struct, interface, record 포함)의 개수', '선택한 구현 파일의 개수')
            .replace('.cs 파일', 'C/C++ 구현 파일'))


def _render_refactoring_guide(advisor_data: dict | None) -> str:
    """plan §10.3 의 'Refactoring Guide' 화면 — LLM Advisor 출력을 통합.

    advisor_data 가 None 이면 빈 placeholder 만 반환 (advise 미실행 안내).
    """
    if advisor_data is None:
        return (
            '<section id="refactoring-guide-empty" class="hidden-section"></section>'
        )
    rows = advisor_data.get("rows", [])
    if not rows:
        return '<section id="refactoring-guide-empty" class="hidden-section"></section>'

    model = html.escape(str(advisor_data.get("model", "claude-haiku-4-5")))

    cards = []
    for idx, row in enumerate(rows, 1):
        fqn = html.escape(str(row.get("fqn", "")))
        grade = str(row.get("grade", "?"))
        si = float(row.get("si", 0.0))
        file_path = html.escape(str(row.get("file_path", "")))
        method = row.get("snippet_method")
        method_label = (
            f' · 메서드 <code>{html.escape(str(method))}</code>'
            if method else ""
        )
        color = GRADE_COLORS.get(grade, "#888")

        advice = row.get("advice", {}) or {}
        rs = advice.get("risk_reasons", []) or []
        sg = advice.get("refactoring_suggestions", []) or []
        tp = advice.get("test_priorities", []) or []
        unc = advice.get("uncertainty_notes", "") or ""

        def _ul(items: list) -> str:
            return "<ul>" + "".join(f"<li>{html.escape(str(x))}</li>" for x in items) + "</ul>"

        cards.append(
            f'<details class="advice-card" data-grade="{grade}"{" open" if idx == 1 else ""}>'
            f'<summary>'
            f'<span class="advice-rank">#{idx}</span>'
            f'<span class="grade-badge" style="background:{color}">{grade}</span>'
            f'<span class="advice-si">G-SI {si:.1f}</span>'
            f'<code class="advice-fqn">{fqn}</code>'
            f'<span class="advice-path">{file_path}{method_label}</span>'
            f'</summary>'
            f'<div class="advice-body">'
            f'<div class="advice-block"><h4>위험 원인</h4>{_ul(rs)}</div>'
            f'<div class="advice-block"><h4>리팩토링 방향</h4>{_ul(sg)}</div>'
            f'<div class="advice-block"><h4>테스트 우선순위</h4>{_ul(tp)}</div>'
            + (f'<div class="advice-uncertainty"><strong>불확실성</strong>: {html.escape(unc)}</div>'
               if unc else "")
            + '</div></details>'
        )

    return (
        '<section>'
        '<div class="sec-head">'
        '<h2>AI 리팩토링 가이드</h2>'
        '<button class="sec-info" data-target="help-advise" aria-expanded="false">ⓘ 이 섹션이 뭔가요?</button>'
        f'<span class="advice-meta">model=<code>{model}</code></span>'
        '</div>'
        '<p class="advice-provenance">각 안내의 점수와 설명은 <strong>생성 당시의 지표</strong>를 기준으로 하며 '
        '현재 분석 결과와 다를 수 있습니다. 이전 실험 예시를 재사용할 때는 최신 점수·이름·의존성을 별도로 확인하세요.</p>'
        '<div class="sec-explain" id="help-advise" hidden>'
        '<p>각 카드는 <strong>G-SI 상위 hotspot 한 개</strong>에 대한 LLM 의 정성 분석입니다. '
        '카드를 클릭하면 펼쳐집니다. 각 카드는 다음 네 섹션으로 구성됩니다.</p>'
        '<ul>'
        '<li><strong>위험 원인</strong> — 왜 이 코드가 위험한지. 지표 수치(CC, 결합도, SCC 크기, GlobalState)를 직접 인용합니다.</li>'
        '<li><strong>리팩토링 방향</strong> — 게임 도메인 맥락(게임 루프 핫 패스, god-object, 거대 switch 등)을 반영한 구체적 제안. <em>코드를 직접 만들지는 않습니다</em> (plan §6.4).</li>'
        '<li><strong>테스트 우선순위</strong> — 안전한 변경을 위해 먼저 작성·강화할 테스트. characterisation test / golden master / performance regression 같은 게임·레거시 코드 적합한 유형을 권고합니다.</li>'
        '<li><strong>불확실성</strong> — 모델이 명시한 추측 한계. 의존성 그래프 일부만 봤다거나 스니펫이 짧다거나 등.</li>'
        '</ul>'
        '<p>본 가이드는 <em>의사결정 보조용</em> 입니다. 실제 리팩토링은 사람이 의존성 그래프와 영향 범위를 직접 확인한 뒤 진행해야 합니다.</p>'
        '</div>'
        + "".join(cards)
        + '</section>'
    )


def _render_analysis_status(status: dict | None) -> str:
    if status is not None and status.get('backend') == 'clang':
        return _render_clang_status(status)
    if status is None:
        return _status_card('unknown', [_status_metric('추출 미확인',
            '이 결과에는 파일별 분석 상태 기록이 연결되지 않았습니다. 성공 여부와 진단 수를 확인할 수 없습니다.')],
            '상태 기록이 없어 성공 여부를 확인할 수 없습니다.',
            ['원본 소스와 결과 생성 기록을 함께 확인하세요.'], None)
    unit = '클래스 단위' if status.get('language') == 'csharp' else '클래스·함수 묶음 단위'
    counts = [
        _status_metric(unit, '점수는 추출한 클래스 또는 C/C++ 함수 묶음별로 계산합니다. 파일 수와 점수 단위 수는 다를 수 있습니다.'),
        _status_metric('등록 해당 없음', '기본 분석은 별도의 컴파일 설정 등록 목록을 사용하지 않습니다.'),
        _status_metric(f"추출 {status['analyzed_files']:,}개", '분석 결과에 포함된 소스 파일 수입니다. 완전한 분석을 뜻하지 않으며 구문 복구나 외부 참조로 정보가 빠질 수 있습니다.'),
        _status_metric('미등록 해당 없음', '기본 분석에는 컴파일 설정 미등록 항목이 없습니다. 선택 언어와 제외 설정에 따른 분석 범위는 별도로 적용됩니다.'),
        _status_metric(f"접근·추출 실패 {status['failed_files']:,}개", '읽기 또는 추출에 실패한 항목 수입니다. 0개여도 코드 전체가 정확하게 해석됐다는 보증은 아닙니다.'),
        _status_metric('컴파일 오류 해당 없음', '이 방식에서는 컴파일러 진단을 수집하지 않습니다. 게임의 실제 버그 개수나 컴파일 오류가 0개라는 뜻이 아닙니다.'),
        _status_metric('컴파일 경고 해당 없음', '이 방식에서는 컴파일러 경고를 수집하지 않습니다. 경고가 없음을 검증한 결과는 아닙니다.'),
        _status_metric(f"구문 복구 {status['syntax_files']:,}개 파일", '파서가 읽기 어려운 구문을 건너뛰거나 복구한 파일 수입니다. 관련 함수나 연결 정보가 불완전할 수 있습니다.'),
    ]
    return _status_card(status['state'], counts, _status_note(status),
                        _diagnostic_reasons(status), status)


def _render_clang_status(status: dict) -> str:
    error_reasons = _diagnostic_reasons(status)
    warning_reasons = _diagnostic_reasons(status, warnings=True)
    error_hint = ' · '.join(_diagnostic_reasons(status, concise=True)[:2])
    warning_hint = ' · '.join(_diagnostic_reasons(status, warnings=True, concise=True)[:2])
    counts = [
        _status_metric('구현 파일 단위', '선택한 C/C++ 구현 파일별로 점수를 계산합니다. 헤더는 해석에 참고하지만 헤더 안의 함수 본문은 점수 대상에서 제외합니다.'),
        _status_metric(f"등록 {status['registered_files']:,}개", '이번 분석 범위와 컴파일 설정에 함께 포함된 파일 수입니다. 같은 파일의 여러 설정 중 첫 설정만 사용합니다.'),
        _status_metric(f"추출 {status['analyzed_files']:,}개", '분석 결과를 받아 저장한 파일 수입니다. 오류가 있는 파일도 읽을 수 있는 부분은 포함하므로, 모든 함수와 연결 정보의 완전한 분석을 뜻하지는 않습니다.'),
        _status_metric(f"미등록 {status['unregistered_files']:,}개", '선택한 입력 범위에 있지만 컴파일 설정에 등록되지 않아 분석 대상에서 제외한 구현 파일 수입니다.'),
        _status_metric(f"접근·추출 실패 {status['failed_files']:,}개", '파일 읽기 실패, 분석 작업 중단 또는 시간 초과 등으로 파일 결과를 받지 못한 항목 수입니다. 컴파일러 오류와는 별도로 집계합니다.'),
        _status_metric(f"컴파일 오류 {status['compiler_error_files']:,}개 파일/{status['compiler_error_count']:,}건",
            '코드를 정상적으로 해석하지 못한 진단입니다. 게임의 실제 버그 개수는 아닙니다.'
            + (f'\n이번 진단: {error_hint}.' if status['compiler_error_count'] else ' 수집된 오류 진단은 없습니다.')),
        _status_metric(f"컴파일 경고 {status['compiler_warning_files']:,}개 파일/{status['compiler_warning_count']:,}건",
            '분석은 계속할 수 있지만 확인이 필요한 진단입니다. 경고만으로 실패나 실제 버그를 뜻하지 않습니다.'
            + (f'\n이번 진단: {warning_hint}.' if status['compiler_warning_count'] else ' 수집된 경고 진단은 없습니다.')),
    ]
    reasons = error_reasons if status['state'] != 'complete' else []
    if status['compiler_warning_count']:
        reasons = [*reasons, *warning_reasons]
    return _status_card(status['state'], counts, _status_note(status), reasons, status)


def _status_metric(label: str, explanation: str) -> str:
    return (f'<span class="status-metric" tabindex="0" '
            f'data-tooltip="{html.escape(explanation, quote=True)}" '
            f'aria-label="{html.escape(label + "。 " + explanation, quote=True)}">'
            f'{html.escape(label)}</span>')


def _diagnostic_reasons(status: dict, warnings: bool = False, concise: bool = False) -> list[str]:
    """Describe observed diagnostic categories, never infer a game-specific cause."""
    severities = {'warning'} if warnings else {'error', 'fatal'}
    messages = ' '.join(str(d.get('message', '')).lower()
                        for d in status.get('compiler_diagnostics', [])
                        if d.get('severity') in severities)
    # Match compiler wording, not project names or paths.
    reasons = []
    def add(label: str, explanation: str) -> None:
        reasons.append(label if concise else explanation)

    if 'forbids macroizing' in messages:
        add('키워드 매크로 충돌', '코드가 private·protected 같은 언어 키워드를 매크로로 바꾸어, 현재 표준 라이브러리의 보호 규칙과 충돌한 진단이 있습니다.')
    if 'cast from member pointer' in messages:
        add('멤버 함수 포인터 변환', '서로 다른 멤버 함수 포인터 사이의 변환을 현재 컴파일러가 허용하지 않은 진단이 있습니다. 관련 호출 정보가 불완전할 수 있습니다.')
    if 'file not found' in messages:
        add('누락된 헤더', '필요한 헤더를 찾지 못한 진단이 있습니다. 해당 파일의 존재와 include 설정을 확인해야 합니다.')
    if 'unknown type name' in messages or 'undeclared identifier' in messages:
        add('타입·이름 해석 문제', '일부 타입이나 이름을 해석하지 못했습니다. 헤더·매크로·설정 문제 또는 앞선 오류의 영향일 수 있어 원인을 별도로 확인해야 합니다.')
    if 'string literal' in messages and ('conversion' in messages or 'convert' in messages):
        add('문자열 상수 변환', '문자열 상수를 수정 가능한 문자 포인터처럼 다루는 코드에 대한 진단이 있습니다. 실제로 문자열을 변경하는지 확인할 필요가 있습니다.')
    if 'equality comparison with extraneous parentheses' in messages:
        add('비교 표현식 확인', '괄호로 둘러싼 비교 표현식에 대한 진단이 있습니다. 비교와 대입 중 의도한 표현이 맞는지 확인할 필요가 있습니다.')
    if "'static' can only be specified" in messages:
        add('static 선언 위치', 'static을 적은 위치에 대한 진단이 있습니다. 선언과 정의가 현재 언어 규칙에 맞는지 확인할 필요가 있습니다.')
    if 'memcpy' in messages and 'non-trivially copyable' in messages:
        add('객체 바이트 복사', '단순 바이트 복사가 안전하다고 보장되지 않는 타입에 memcpy를 사용한 진단이 있습니다. 객체 복사 방식이 적절한지 확인할 필요가 있습니다.')
    if messages and not reasons:
        add('원인 추가 확인 필요', '현재 진단만으로 원인을 확정하지 않습니다. 분석 설정과 원본 코드를 함께 확인해야 합니다.')
    if not warnings:
        errors = status.get('errors', [])
        if errors:
            worker_messages = ' '.join(str(e.get('message', '')).lower() for e in errors)
            if 'timeout' in worker_messages:
                add('분석 시간 초과', '분석 작업이 제한 시간 안에 끝나지 않은 항목이 있습니다. 해당 항목의 결과는 받지 못했습니다.')
            else:
                add('접근·설정·작업 실패 확인', '파일 접근·분석 작업·설정 또는 저장 단계의 실패가 기록됐습니다. 실패한 항목과 오류 안내를 확인해야 합니다.')
        if status.get('syntax_files', 0):
            add('구문 복구 발생', '읽기 어려운 구문을 복구하거나 건너뛴 파일이 있습니다. 관련 함수와 연결 정보가 빠질 수 있습니다.')
        if not reasons and (status.get('compiler_error_count', 0) or status['state'] != 'complete'):
            add('원인 추가 확인 필요', '현재 상태 요약만으로 원인을 확정할 수 없습니다. 입력·설정·추출·저장 단계의 원본 진단을 확인해야 합니다.')
    elif not reasons and status.get('compiler_warning_count', 0):
        add('원본 경고 확인 필요', '주의가 필요한 컴파일러 진단이 기록됐습니다. 경고의 실제 의미는 원본 진단과 코드를 함께 확인해야 합니다.')
    return reasons


def _status_note(status: dict) -> str:
    if status['state'] == 'failed':
        return '최신 실행은 실패했습니다. 남아 있는 결과를 최신 성공 결과로 사용하지 마세요.'
    if status['state'] == 'partial':
        return '결과는 얻었지만 일부 정보가 불완전할 수 있어 부분 분석으로 표시합니다.'
    return '선택한 범위의 분석을 완료했습니다.'


def _render_file_coverage(status: dict | None) -> str:
    """Count selected inputs with returned results and no error/fatal; not accuracy."""
    if not status or status.get('backend') != 'clang' or status.get('state') != 'partial':
        return ''
    counts = [status.get(key) for key in
              ('registered_files', 'analyzed_files', 'failed_files', 'compiler_error_files')]
    if any(type(value) is not int for value in counts):
        return ''
    registered, analyzed, failed, error_files = counts
    if not (registered > 0 and failed >= 0 and 0 <= error_files <= analyzed <= registered
            and analyzed + failed == registered):
        return ''
    clean = analyzed - error_files
    percentage = 100 * clean / registered
    explanation = ('선택한 등록 입력 중 결과를 얻었고 컴파일 오류가 없던 파일의 비율입니다. '
                   '경고 파일은 포함하고 추출 실패 파일은 분자에서 제외합니다. 미등록 파일은 계산 대상 밖입니다. '
                   '정확도나 전체 게임의 분석률을 뜻하지 않습니다.')
    return ('<div class="status-coverage"><span tabindex="0" '
            f'data-tooltip="{html.escape(explanation, quote=True)}">컴파일 오류 없는 파일 비율 '
            f'<strong>{percentage:.1f}%</strong> · {clean:,}/{registered:,}개</span></div>')


def _status_card(state: str, counts: list[str], note: str, reasons: list[str],
                 status: dict | None) -> str:
    labels = {'complete': '분석 완료', 'partial': '부분 분석', 'failed': '분석 실패',
              'unknown': '분석 상태 미확인'}
    summary = {'complete': '분석 상태 설명', 'partial': '왜 부분 분석인가요?',
               'failed': '왜 분석에 실패했나요?', 'unknown': '분석 상태 설명'}[state]
    native = bool(status and status.get('backend') == 'clang')
    scope = (f"선택한 구현 파일 {status['registered_files']:,}개 대상" if native else
             '선택한 소스 범위 대상' if status else '분석 범위 미확인')
    limitations = ''.join(f'<li>{html.escape(str(item))}</li>'
                          for item in (status or {}).get('limitations', []))
    reason_body = ''.join(f'<li>{html.escape(reason)}</li>' for reason in reasons)
    if not reason_body:
        reason_body = '<li>선택한 범위에 대한 결과입니다. 완료 표시는 전체 게임의 완전한 해석이나 빌드 성공을 보증하지 않습니다.</li>'
    warning_body = ''
    if state == 'complete' and status and status.get('compiler_warning_count', 0):
        warnings = ''.join(f'<li>{html.escape(item)}</li>'
                           for item in _diagnostic_reasons(status, warnings=True))
        warning_body = f'<h3>기록된 경고 참고</h3><ul>{warnings}</ul>'
    details = ('' if state == 'complete' else
               f'<details class="analysis-info"><summary>{summary}</summary><ul>{reason_body}</ul></details>')
    details += ('<details class="analysis-info"><summary>분석 범위와 한계</summary>'
                f'<ul>{limitations}</ul>{warning_body}'
                '<p>전체 설정과 진단은 원본 분석 데이터에 보존되어 있습니다.</p></details>')
    heading = labels[state]
    if state == 'complete':
        completion_tip = ('선택한 분석 대상 기준의 완료 표시입니다. '
                          '정확도나 전체 게임의 분석률, 빌드 성공률을 뜻하지 않습니다. ')
        completion_tip += ('등록된 선택 입력 기준이며 미등록 파일은 제외합니다. 경고가 남을 수 있습니다.'
                           if native else
                           '기본 분석은 컴파일러 진단을 수집하지 않으므로 컴파일 오류가 없다는 뜻은 아닙니다.')
        heading += (' · <span class="status-completion" tabindex="0" '
                    f'data-tooltip="{html.escape(completion_tip, quote=True)}">100%</span>')
    return (f'<aside class="analysis-status{" partial" if state != "complete" else ""}" aria-label="분석 상태">'
            f'<div class="status-heading"><strong>{heading}</strong><span>{html.escape(scope)}</span></div>'
            f'{_render_file_coverage(status)}'
            f'<div class="status-counts">{" · ".join(counts)}</div>'
            f'<p class="status-note">{html.escape(note)}</p>'
            f'{details}</aside>')


def _render_project_subtitle(subtitle: str | None, status: dict | None) -> str:
    if subtitle is None:
        subtitle = ('선택한 구현 파일 · 컴파일 설정 기반 분석' if status and status.get('backend') == 'clang'
                    else '선택한 소스 코드 · 기본 정적 분석')
    return f'<p class="report-subtitle">{html.escape(subtitle)}</p>' if subtitle else ''


def _render_help_box(file_units: bool = False, analysis_status: dict | None = None) -> str:
    """대시보드 상단에 두는 \"이 대시보드 읽는 법\" 도움말 박스.

    각 섹션의 상세 설명은 섹션 헤더 옆 ⓘ 토글로 분리되어 있으므로,
    이 박스는 점수 의미·등급 색상과 화면 사용법을 담는다.
    """
    help_box = _unit_wording('''<details class="help">
    <summary>대시보드 읽는 법</summary>
    <div class="help-body">
        <p><strong>Game Spaghetti Index (G-SI)</strong>는 분석한 클래스 집합 내부의 <strong>상대적인 검토 우선순위</strong>입니다. 절대 품질·결함 확률이나 프로젝트 간 우열을 뜻하지 않습니다.</p>
        <p>동점은 상단 백분위로 계산합니다. 모두 동점이면 100/E여도 심각한 결함의 증거가 아니며, 순위로 후보를 구분할 수 없습니다. 원시 지표와 실제 소스를 함께 확인하세요.</p>
        <p class="help-grade">
            등급 의미 →
            <span class="grade-badge" style="background:#3b8e5a">A</span> 0~20 미만 ·
            <span class="grade-badge" style="background:#7fb95a">B</span> 20~40 미만 ·
            <span class="grade-badge" style="background:#e3b341">C</span> 40~60 미만 ·
            <span class="grade-badge" style="background:#ef7d3c">D</span> 60~80 미만 ·
            <span class="grade-badge" style="background:#d24343">E</span> 80~100
        </p>
        <p class="help-tip">💡 각 섹션 제목 옆의 <strong>「ⓘ 이 섹션이 뭔가요?」</strong> 버튼을 누르면 그 섹션이 무엇을 보여주는지 자세한 설명이 나옵니다. 화면 곳곳의 항목에 마우스를 올리면 그 자리에서 짧은 설명이 풍선으로 표시됩니다.</p>
    </div>
</details>''', file_units)
    return help_box


def _render_health_hero(scoring: ScoringResult, metrics: MetricsResult, file_units: bool = False) -> str:
    """프로젝트 종합 점수(Project Health)를 큰 히어로 카드로 표시."""
    ph = scoring.project_health
    if ph is None:
        return ""
    color = GRADE_COLORS[ph.grade]
    unit = '구현 파일' if file_units else '클래스'
    desc = _health_description(ph)
    if len({c.raw_score for c in scoring.class_scores}) <= 1:
        desc += " 현재 가중합이 모두 동점이므로 순위는 후보 구분에 유효하지 않습니다."
    return f'''<div class="health-hero">
        <div class="health-circle" style="border-color:{color}">
            <div class="health-grade" style="color:{color}">{ph.grade}</div>
            <div class="health-score">{ph.score:.0f}</div>
            <div class="health-unit">/ 100</div>
        </div>
        <div class="health-info">
            <div class="health-title">구조 요약 (보조 Health)</div>
            <div class="health-desc">{desc}</div>
            <div class="health-stats">
                <div data-tooltip="프로젝트 내 모든 {unit}의 G-SI 점수 평균. 종합 점수에 45% 기여">
                    <span class="hs-label">평균 G-SI</span><span class="hs-value">{ph.avg_si:.1f}</span></div>
                <div data-tooltip="G-SI 60 이상(D·E 등급)인 {unit}의 비율. 종합 점수에 25% 기여">
                    <span class="hs-label">상대 D+E 비율</span><span class="hs-value">{ph.risk_ratio * 100:.1f}%</span></div>
                <div data-tooltip="순환 참조에 빠진 {unit} 묶음의 수(크기 ≥ 2). 종합 점수에 15% 기여">
                    <span class="hs-label">순환 의존성</span><span class="hs-value">{ph.cycle_count}</span></div>
                <div data-tooltip="{unit} 한 개당 평균적으로 몇 개의 다른 {unit}와 연결되는지(fan-in + fan-out 평균). 종합 점수에 15% 기여">
                    <span class="hs-label">평균 결합도</span><span class="hs-value">{ph.avg_coupling:.2f}</span></div>
            </div>
        </div>
    </div>'''


def _health_description(ph) -> str:
    return "상대 순위·순환·결합도를 합친 검증되지 않은 보조 수치입니다. 절대 품질이나 프로젝트 간 비교에는 사용하지 마세요."


def _json_default(obj: Any) -> Any:
    if isinstance(obj, set):
        return sorted(obj)
    return str(obj)


# ---------------------------------------------------------------------------
# 섹션 빌더
# ---------------------------------------------------------------------------


def _render_summary_cards(scoring: ScoringResult, metrics: MetricsResult, file_units: bool = False) -> str:
    si_values = [c.si for c in scoring.class_scores]
    avg_si = sum(si_values) / len(si_values) if si_values else 0.0
    max_si = max(si_values) if si_values else 0.0
    risk_count = sum(1 for c in scoring.class_scores if c.grade in ("D", "E"))

    cards = [
        ("분석 클래스", f"{scoring.total_classes:,}",
         "분석기가 추출한 타입 또는 C/C++ 함수 묶음의 합계"),
        ("분석 메서드", f"{scoring.total_methods:,}",
         "분석된 모든 메서드와 생성자의 합계"),
        ("의존성 순환(SCC ≥ 2)", f"{len(metrics.sccs):,}",
         "A→B→C→A처럼 서로 참조해서 빙빙 도는 클래스 묶음의 개수. 적을수록 좋음"),
        ("평균 G-SI", f"{avg_si:.1f}",
         "클래스 상대 백분위 평균. 절대 품질 비교에는 사용하지 않음"),
        ("최대 G-SI", f"{max_si:.1f}",
         "최대 상대 백분위. 비어 있지 않은 분석은 공식상 항상 100"),
        ("상대 D/E 클래스", f"{risk_count:,}",
         "상대 백분위 60 이상인 클래스 수. 실제 결함 여부는 별도 검토"),
    ]
    if file_units:
        cards = [(_unit_wording(label, True), value, _unit_wording(tip, True))
                 for label, value, tip in cards]
        cards[0] = (cards[0][0], cards[0][1], '선택한 구현 파일 단위의 합계')
        cards[1] = (cards[1][0], cards[1][1], '선택한 구현 파일에 정의된 함수·생성자·소멸자의 합계')
    return "".join(
        f'<div class="card" data-tooltip="{html.escape(tip)}">'
        f'<div class="card-label">{html.escape(label)}</div>'
        f'<div class="card-value">{html.escape(value)}</div></div>'
        for label, value, tip in cards
    )


def _render_grade_donut(distribution: dict[str, int]) -> str:
    """등급 분포를 SVG 도넛 차트로 렌더링."""
    total = sum(distribution.values()) or 1
    cx, cy, r, stroke = 90, 90, 70, 28
    circumference = 2 * math.pi * r

    segments = []
    offset = 0.0
    legend_items = []
    for grade in "ABCDE":
        count = distribution.get(grade, 0)
        if total <= 0:
            pct = 0.0
        else:
            pct = count / total
        length = pct * circumference
        color = GRADE_COLORS[grade]
        if length > 0:
            segments.append(
                f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
                f'stroke="{color}" stroke-width="{stroke}" '
                f'stroke-dasharray="{length:.3f} {circumference:.3f}" '
                f'stroke-dashoffset="{-offset:.3f}" transform="rotate(-90 {cx} {cy})"/>'
            )
        offset += length
        legend_items.append(
            f'<div class="legend-item">'
            f'<span class="swatch" style="background:{color}"></span>'
            f'<span>{grade}</span>'
            f'<span class="count">{count:,} ({pct * 100:.1f}%)</span>'
            f'</div>'
        )

    return f'''<div class="donut-container">
        <svg viewBox="0 0 180 180" width="180" height="180" class="donut">
            <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#1f2937" stroke-width="{stroke}"/>
            {''.join(segments)}
            <text x="{cx}" y="{cy}" text-anchor="middle" dominant-baseline="central"
                  fill="#cbd5e1" font-size="20" font-weight="600">{total:,}</text>
        </svg>
        <div class="legend">{''.join(legend_items)}</div>
    </div>'''


def _render_weights_table(weights: dict[str, float], file_units: bool = False) -> str:
    tooltips = {
        "cc": "Cyclomatic Complexity — 메서드 안의 if/for/case 등 분기 수",
        "coupling": "Coupling — 다른 클래스와 얼마나 연결되어 있는지 (fan-in + fan-out)",
        "dependency_cycle": "DependencyCycle — 순환 참조에 빠졌는지, 묶음의 크기는 얼마인지",
        "global_state": "GlobalState — 전역/static 변수와 싱글톤 인스턴스에 얼마나 의존하는지",
        "game_loop_centrality": "GameLoopCentrality — Tick/Update/Render 등 게임 루프 진입점에서 얼마나 가까운지",
    }
    rows = "".join(
        f'<tr><td data-tooltip="{html.escape(_unit_wording(tooltips.get(k, ""), file_units))}">{html.escape(k)}</td>'
        f'<td class="num">{v:.3f}</td></tr>'
        for k, v in weights.items()
    )
    return f'''<table class="kv-table">
        <thead><tr><th>항목</th><th class="num">가중치</th></tr></thead>
        <tbody>{rows}</tbody>
    </table>'''


def _render_hotspot_table(hotspots, top_n: int, file_units: bool = False) -> str:
    """표 골격만 렌더링. 본문은 클라이언트 측에서 등급 필터에 따라 동적으로 그린다."""
    unit = '구현 파일' if file_units else '클래스'
    notice = (
        f'<div class="table-notice">'
        f'기본은 전체 {unit} 중 <strong>G-SI 상위 {top_n}개</strong>를 표시합니다. '
        f'특정 등급(A~E)을 선택하면 <strong>그 등급 안에서</strong> 상위 {top_n}개를 다시 보여줍니다. '
        f'전체 등급 분포는 위 등급 분포 차트에서 확인하세요.'
        f'</div>'
    )

    def th(label: str, sort: str | None = None, tip: str | None = None, num: bool = False) -> str:
        label = _unit_wording(label, file_units)
        tip = _unit_wording(tip, file_units) if tip else tip
        parts = ['<th']
        classes: list[str] = []
        if sort:
            classes.append("sortable")
            parts.append(' data-sort="' + sort + '"')
        if num:
            classes.append("num")
        if classes:
            parts.append(' class="' + " ".join(classes) + '"')
        if tip:
            parts.append(' data-tooltip="' + html.escape(tip) + '"')
        parts.append('>')
        parts.append(label)
        parts.append('</th>')
        return ''.join(parts)

    return f'''{notice}
    <div class="table-controls">
        <input type="text" id="hotspot-filter" placeholder="텍스트 검색: FQN 또는 파일 경로 부분 일치">
        <select id="grade-filter">
            <option value="">전체 등급에서 상위 {top_n}</option>
            <option value="E">E 등급만 (상대 80~100)</option>
            <option value="D">D 등급만 (리팩토링 후보)</option>
            <option value="C">C 등급만 (보통)</option>
            <option value="B">B 등급만 (일반)</option>
            <option value="A">A 등급만 (상대 0~20 미만)</option>
        </select>
        <span id="hotspot-count" class="hotspot-count"></span>
    </div>
    <table class="hotspot-table" id="hotspot-table">
        <thead><tr>
            <th class="num" data-tooltip="G-SI 점수 기준 등수">#</th>
            <th data-tooltip="A~E는 상대 백분위 구간이며 동점 때문에 균등하지 않을 수 있음">등급</th>
            {th("G-SI", sort="num", num=True, tip="0~100. 분석 집합 내부 상대 백분위. 절대 품질 아님")}
            {th("클래스 FQN", sort="str", tip="네임스페이스를 포함한 정규 이름")}
            {th("CC", sort="num", num=True, tip="Cyclomatic Complexity. 메서드 안의 if/for/case 등 분기 수. 클래스 단위는 상위 10% 평균")}
            {th("Coupling", sort="num", num=True, tip="다른 클래스를 참조하는 수(fan-out) + 참조받는 수(fan-in)")}
            {th("GlobalState", sort="num", num=True, tip="전역(static) 변수와 싱글톤 인스턴스에 접근한 횟수")}
            {th("CycleSize", sort="num", num=True, tip="순환 참조에 빠진 묶음의 크기. 0이면 순환에 포함되지 않음")}
            {th("GameLoop", sort="num", num=True, tip="Tick/Update/Render 같은 진입점으로부터의 가까움. 1.0이면 진입점 그 자체")}
            <th data-tooltip="이 {unit}가 위험으로 분류된 가장 큰 두 항목">주요 원인</th>
            <th data-tooltip="파일 경로 : 시작 라인">위치</th>
        </tr></thead>
        <tbody id="hotspot-tbody"></tbody>
    </table>'''


def _hotspot_data_payload(scoring) -> str:
    """모든 클래스 점수를 JS가 다룰 수 있는 가벼운 dict 배열로 직렬화."""
    payload = []
    for cs in scoring.class_scores:
        payload.append({
            "fqn": cs.fqn,
            "file_path": cs.file_path,
            "start_line": cs.start_line,
            "grade": cs.grade,
            "si": round(cs.si, 1),
            "cc": round(cs.raw.get("cc", 0), 1),
            "coupling": int(cs.raw.get("coupling", 0)),
            "global_state": int(cs.raw.get("global_state", 0)),
            "dependency_cycle": int(cs.raw.get("dependency_cycle", 0)),
            "game_loop_centrality": round(cs.raw.get("game_loop_centrality", 0), 2),
            "top_reasons": cs.top_reasons,
        })
    return json.dumps(payload, ensure_ascii=False)


def _render_dependency_graph(
    scoring: ScoringResult,
    metrics: MetricsResult,
    top_n: int = 50,
    file_units: bool = False,
) -> str:
    """상위 hotspot 클래스와 그 인접 노드를 SVG force-directed 그래프로 렌더링한다.

    좌표는 NetworkX spring_layout으로 Python에서 미리 계산해 SVG에 박아둔다.
    외부 JavaScript 라이브러리(Cytoscape.js 등)에 의존하지 않으면서도
    한눈에 의존성 구조를 파악할 수 있다.
    """
    import networkx as nx
    unit = '구현 파일' if file_units else '클래스'

    g = metrics.class_graph
    if g.number_of_nodes() == 0:
        return '<div class="empty">의존성 그래프를 그릴 노드가 없습니다.</div>'

    # 상위 hotspot 중심으로 부분 그래프 추출.
    #
    # 큰 코드베이스(예: OpenRA.Mods.Common)에서는 top_n + 1-홉 이웃이 수백 개로 폭발해
    # 화면이 점들로 덮여 인터랙션이 어렵다. 보기 좋은 범위로 노드 수를 제한한다.
    MAX_NODES = 150
    hotspot_fqns = [cs.fqn for cs in sorted(scoring.class_scores, key=lambda c: -c.si)[:top_n]]
    seed = [fqn for fqn in hotspot_fqns if fqn in g]
    expanded: list[str] = list(seed)  # 순서 보존을 위해 list 사용
    seen = set(seed)

    # seed 각각의 1-홉 이웃을 G-SI 점수가 높은 순서로 우선 채운다.
    si_rank = {cs.fqn: i for i, cs in enumerate(sorted(scoring.class_scores, key=lambda c: -c.si))}
    neighbor_candidates: list[str] = []
    for fqn in seed:
        for nb in list(g.predecessors(fqn)) + list(g.successors(fqn)):
            if nb not in seen:
                neighbor_candidates.append(nb)
                seen.add(nb)
    neighbor_candidates.sort(key=lambda n: si_rank.get(n, 10**9))
    for nb in neighbor_candidates:
        if len(expanded) >= MAX_NODES:
            break
        expanded.append(nb)

    subgraph = g.subgraph(expanded).copy()

    if subgraph.number_of_nodes() == 0:
        return '<div class="empty">선택된 hotspot에 의존성 엣지가 없습니다.</div>'

    # spring_layout으로 좌표 계산. seed 고정으로 결과를 결정적으로 만든다.
    pos = nx.spring_layout(
        subgraph,
        k=1.5 / max(1, subgraph.number_of_nodes() ** 0.5),
        iterations=80,
        seed=42,
    )

    width, height, margin = 1400, 720, 50
    si_lookup = {cs.fqn: cs for cs in scoring.class_scores}

    # 좌표 정규화
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    if not xs or not ys or (max(xs) == min(xs)) or (max(ys) == min(ys)):
        return '<div class="empty">레이아웃 좌표를 계산할 수 없습니다.</div>'
    x_range = max(xs) - min(xs)
    y_range = max(ys) - min(ys)

    def project(p):
        x = (p[0] - min(xs)) / x_range * (width - 2 * margin) + margin
        y = (p[1] - min(ys)) / y_range * (height - 2 * margin) + margin
        return x, y

    # 각 노드의 정수 인덱스를 부여 (DOM 셀렉터 단순화)
    fqn_to_idx = {fqn: i for i, fqn in enumerate(subgraph.nodes())}

    # 엣지
    edges_svg = []
    for u, v in subgraph.edges():
        x1, y1 = project(pos[u])
        x2, y2 = project(pos[v])
        edges_svg.append(
            f'<line class="edge" data-src="{fqn_to_idx[u]}" data-dst="{fqn_to_idx[v]}" '
            f'x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="#334155" stroke-width="0.8" stroke-opacity="0.6" marker-end="url(#arrow)"/>'
        )

    # 노드 + 인접 정보 (info panel용)
    node_info_payload: dict[str, dict] = {}
    nodes_svg = []
    for fqn, i in fqn_to_idx.items():
        x, y = project(pos[fqn])
        cs = si_lookup.get(fqn)
        if cs is not None:
            color = GRADE_COLORS[cs.grade]
            radius = 6 + min(14, cs.raw.get("coupling", 0) * 0.3)
            si_text = f"{cs.si:.0f}"
            label = cs.name
            payload = {
                "fqn": cs.fqn,
                "grade": cs.grade,
                "si": cs.si,
                "raw": cs.raw,
                "top_reasons": cs.top_reasons,
                "file_path": cs.file_path,
                "start_line": cs.start_line,
            }
        else:
            color = "#475569"
            radius = 4
            si_text = "?"
            label = fqn.rsplit(".", 1)[-1] if "." in fqn else fqn
            payload = {"fqn": fqn, "grade": "?", "si": None}

        # 인접 정보
        in_neighbors = list(subgraph.predecessors(fqn))
        out_neighbors = list(subgraph.successors(fqn))
        payload["fan_in"] = len(in_neighbors)
        payload["fan_out"] = len(out_neighbors)
        payload["neighbor_idxs"] = [fqn_to_idx[n] for n in in_neighbors + out_neighbors]
        payload["sample_neighbors"] = {
            "in": [n.rsplit(".", 1)[-1] for n in in_neighbors[:5]],
            "out": [n.rsplit(".", 1)[-1] for n in out_neighbors[:5]],
        }
        node_info_payload[str(i)] = payload

        nodes_svg.append(
            f'<g class="node" data-idx="{i}" data-fqn="{html.escape(fqn)}">'
            f'<title>{html.escape(fqn)} (G-SI={si_text})</title>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" '
            f'fill="{color}" stroke="#0f172a" stroke-width="1.2"/>'
            f'<text x="{x:.1f}" y="{y - radius - 3:.1f}" text-anchor="middle" '
            f'fill="#cbd5e1" font-size="10">{html.escape(label)}</text>'
            f'</g>'
        )

    info_json = json.dumps(node_info_payload, ensure_ascii=False)

    return f'''<div class="graph-meta">
        표시 노드 {subgraph.number_of_nodes()} · 엣지 {subgraph.number_of_edges()} ·
        (G-SI 상위 {top_n}개 hotspot + 1-홉 이웃) ·
        <em>마우스를 노드에 올리면 우측에 상세 정보가 나타납니다.</em>
    </div>
    <div class="graph-controls">
        <input type="text" id="graph-search" placeholder="그래프 안 {unit} 검색 (이름의 일부 입력)">
        <div class="grade-toggle" id="graph-grade-toggle">
            <span class="gt-label">등급 강조:</span>
            <button data-grade="" class="gt-btn gt-active">전체</button>
            <button data-grade="A" class="gt-btn">A</button>
            <button data-grade="B" class="gt-btn">B</button>
            <button data-grade="C" class="gt-btn">C</button>
            <button data-grade="D" class="gt-btn">D</button>
            <button data-grade="E" class="gt-btn">E</button>
        </div>
        <span class="graph-match-count" id="graph-match-count"></span>
        <div class="graph-zoom" id="graph-zoom">
            <button id="zoom-in" data-tooltip="확대 (또는 마우스 휠 위)">＋</button>
            <button id="zoom-out" data-tooltip="축소 (또는 마우스 휠 아래)">−</button>
            <button id="zoom-reset" data-tooltip="원래 크기로 복귀">리셋</button>
        </div>
    </div>
    <div class="graph-tip">💡 <strong>그래프 사용법</strong> — 마우스 휠로 확대/축소, 드래그로 이동, 노드 위에 마우스를 올리면 우측에 상세 정보가 표시됩니다.</div>
    <div class="graph-wrap">
        <svg viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" class="depgraph" id="depgraph">
            <defs>
                <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                    <path d="M0,0 L8,4 L0,8 z" fill="#64748b"/>
                </marker>
            </defs>
            <g class="edges">{''.join(edges_svg)}</g>
            <g class="nodes">{''.join(nodes_svg)}</g>
        </svg>
        <aside class="graph-info" id="graph-info">
            <div class="info-empty">노드 위에 마우스를 올리면<br>여기에 상세 정보가 나타납니다.<br><br>
            아래 검색창에 {unit} 이름을 입력하거나 등급 버튼을 누르면<br>해당 노드가 강조됩니다.</div>
        </aside>
    </div>
    <script id="graph-node-info" type="application/json">{info_json}</script>'''


def _render_cycle_explorer(metrics: MetricsResult, si_lookup: dict, file_units: bool = False) -> str:
    """크기 ≥ 2 인 SCC 목록을 표시한다. 각 cycle의 멤버 클래스와 평균 G-SI를 보여준다."""
    # 섹션 상단의 ⓘ 토글이 설명을 대체하므로 내부 intro는 비워둔다.
    intro = ""
    unit = '구현 파일' if file_units else '클래스'

    total = len(metrics.sccs)
    if total == 0:
        count_card = (
            '<div class="cycle-count cycle-count-zero" '
            'data-tooltip="크기가 2 이상인 순환 의존성이 하나도 발견되지 않았습니다. 좋은 신호입니다.">'
            '<div class="cc-number">0</div>'
            '<div class="cc-label">발견된 순환 묶음 (전체)</div>'
            f'<div class="cc-hint">✅ 좋은 신호 — {unit}들이 한 방향으로 흐름</div>'
            '</div>'
        )
        return intro + count_card

    # 카운트 카드 — 이 숫자가 "전체"임을 명확히
    sccs_sorted = sorted(metrics.sccs, key=len, reverse=True)
    largest = len(sccs_sorted[0])
    count_card = (
        f'<div class="cycle-count" '
        f'data-tooltip="이 프로젝트 전체에서 발견된 순환 의존성 묶음의 수입니다. 상위 N개가 아니라 전부 표시됩니다.">'
        f'<div class="cc-number">{total}</div>'
        f'<div class="cc-label">발견된 순환 묶음 (전체)</div>'
        f'<div class="cc-hint">가장 큰 묶음의 크기: <strong>{largest}개 {unit}</strong></div>'
        f'</div>'
    )

    rows = [intro, count_card]
    for idx, scc in enumerate(sccs_sorted, 1):
        members = sorted(scc)
        si_values = [si_lookup[fqn].si for fqn in members if fqn in si_lookup]
        avg_si = sum(si_values) / len(si_values) if si_values else 0.0
        max_si = max(si_values) if si_values else 0.0
        grade = _grade(max_si)
        member_html = "".join(
            f'<li><code title="G-SI={si_lookup[m].si:.1f}" '
            f'class="cycle-member grade-{si_lookup[m].grade}">{html.escape(m)}</code></li>'
            if m in si_lookup else
            f'<li><code class="cycle-member">{html.escape(m)}</code></li>'
            for m in members[:20]
        )
        more = f" ... 외 {len(members) - 20}개" if len(members) > 20 else ""
        tip = (
            f"이 묶음 안의 {len(scc)}개 {unit}는 서로 참조 사슬을 이루고 있어 "
            f"한 {unit}를 수정하면 나머지에도 영향이 갈 수 있습니다."
        )
        rows.append(
            f'<details class="cycle-entry" data-tooltip="{html.escape(tip)}"><summary>'
            f'<span class="cycle-rank">#{idx}</span>'
            f'<span class="grade-badge" style="background:{GRADE_COLORS[grade]}">{grade}</span>'
            f'<span class="cycle-stat">크기 <strong>{len(scc)}</strong></span>'
            f'<span class="cycle-stat">평균 G-SI <strong>{avg_si:.1f}</strong></span>'
            f'<span class="cycle-stat">최대 <strong>{max_si:.1f}</strong></span>'
            f'</summary><ul>{member_html}</ul>{more}</details>'
        )
    return f'{rows[0]}{rows[1]}<div class="cycle-list">{"".join(rows[2:])}</div>'


def _grade(score: float) -> str:
    """등급 분류 — `_render_grade_donut`과 분리되어 있어 별도 함수로 둔다."""
    if score < 20: return "A"
    if score < 40: return "B"
    if score < 60: return "C"
    if score < 80: return "D"
    return "E"


def _render_module_table(modules, file_units: bool = False) -> str:
    # 섹션 상단의 ⓘ 토글이 설명을 대체하므로 내부 intro는 더 이상 그리지 않는다.
    intro = ""
    unit = '구현 파일' if file_units else '클래스'
    source_label = 'C/C++ 구현 파일' if file_units else '.cs 파일'
    count_tip = '선택한 구현 파일의 합' if file_units else '클래스 · 구조체 · 인터페이스 · 레코드의 합'
    rows = []
    for ms in modules:
        rows.append(
            f'<tr>'
            f'<td>{html.escape(ms.module)}</td>'
            f'<td><span class="grade-badge" style="background:{GRADE_COLORS[ms.grade]}">{ms.grade}</span></td>'
            f'<td class="num">{ms.si_mean:.1f}</td>'
            f'<td class="num">{ms.si_max:.1f}</td>'
            f'<td class="num">{ms.file_count:,}</td>'
            f'<td class="num">{ms.class_count:,}</td>'
            f'</tr>'
        )
    body = "".join(rows) if rows else '<tr><td colspan="6" class="empty">집계할 모듈이 없습니다.</td></tr>'
    return f'''{intro}
    <table class="module-table">
        <thead><tr>
            <th data-tooltip="분석 입력 폴더 바로 아래의 1단계 폴더 이름. (root)는 폴더에 들어있지 않고 분석 폴더 바로 아래에 놓인 {source_label}들">모듈</th>
            <th data-tooltip="모듈 내 파일별 최대 G-SI의 평균을 기준으로 한 구간">등급</th>
            <th class="num" data-tooltip="모듈 내 파일별 최대 G-SI를 파일 동일 비중으로 평균">평균 G-SI</th>
            <th class="num" data-tooltip="모듈에서 가장 위험한 {unit} 하나의 G-SI">최대 G-SI</th>
            <th class="num" data-tooltip="모듈에 속한 {source_label} 수">파일 수</th>
            <th class="num" data-tooltip="모듈에 속한 {count_tip}">{unit} 수</th>
        </tr></thead>
        <tbody>{body}</tbody>
    </table>'''


# ---------------------------------------------------------------------------
# HTML 템플릿
# ---------------------------------------------------------------------------


_HTML_TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{project_name} — Game Spaghetti Index Report</title>
<style>
  :root {{
    --bg: #0f172a; --panel: #111827; --panel2: #1f2937;
    --fg: #e5e7eb; --muted: #94a3b8; --accent: #60a5fa; --border: #1f2937;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--fg);
    font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
    line-height: 1.5; font-size: 14px;
  }}
  header {{ padding: 24px 32px; background: var(--panel); border-bottom: 1px solid var(--border); }}
  header h1 {{ margin: 0 0 4px 0; font-size: 22px; }}
  header .report-subtitle {{ margin: 4px 0; color: #cbd5e1; font-size: 14px; }}
  header .report-kind {{ color: var(--muted); font-size: 12px; margin-bottom: 8px; }}
  header .meta {{ color: var(--muted); font-size: 13px; }}
  main {{ padding: 24px 32px; max-width: 1400px; margin: 0 auto; }}
  section {{ margin-bottom: 32px; }}
  section h2 {{ font-size: 17px; margin: 0; color: #cbd5e1; }}
  .sec-head {{ display: flex; gap: 12px; align-items: baseline; margin-bottom: 12px;
               padding-bottom: 6px; border-bottom: 1px solid var(--border); }}
  .sec-info {{ background: transparent; color: var(--accent); border: 1px solid var(--border);
               padding: 2px 10px; border-radius: 999px; font-size: 11px; cursor: pointer;
               white-space: nowrap; transition: all 0.1s; }}
  .sec-info:hover {{ background: rgba(96,165,250,0.1); border-color: var(--accent); }}
  .sec-info[aria-expanded="true"] {{ background: var(--accent); color: #0b1322; border-color: var(--accent); }}
  .hidden-section {{ display: none; }}
  .advice-meta {{ color: var(--muted); font-size: 12px; margin-left: auto; }}
  .advice-meta code {{ background: rgba(255,255,255,0.08); padding: 1px 6px; border-radius: 3px; }}
  .advice-card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
                  margin-bottom: 10px; }}
  .advice-card[data-grade="E"] {{ border-left: 4px solid #d24343; }}
  .advice-card[data-grade="D"] {{ border-left: 4px solid #ef7d3c; }}
  .advice-card[data-grade="C"] {{ border-left: 4px solid #e3b341; }}
  .advice-card[data-grade="B"] {{ border-left: 4px solid #7fb95a; }}
  .advice-card[data-grade="A"] {{ border-left: 4px solid #3b8e5a; }}
  .advice-card summary {{ cursor: pointer; padding: 12px 16px; display: flex; align-items: center;
                          gap: 12px; font-size: 13px; user-select: none; }}
  .advice-card summary:hover {{ background: rgba(255,255,255,0.02); }}
  .advice-card summary::-webkit-details-marker {{ display: none; }}
  .advice-rank {{ color: var(--muted); font-variant-numeric: tabular-nums; min-width: 28px; }}
  .advice-si {{ color: var(--muted); font-variant-numeric: tabular-nums; min-width: 80px; }}
  .advice-fqn {{ font-family: ui-monospace, "Cascadia Code", monospace; font-size: 12px;
                 background: rgba(255,255,255,0.05); padding: 2px 8px; border-radius: 4px; }}
  .advice-path {{ color: var(--muted); font-size: 12px; margin-left: auto; }}
  .advice-path code {{ background: rgba(255,255,255,0.06); padding: 0 4px; border-radius: 3px; }}
  .advice-body {{ padding: 0 18px 14px 18px; border-top: 1px solid var(--border); }}
  .advice-block {{ margin-top: 14px; }}
  .advice-block h4 {{ margin: 0 0 6px 0; font-size: 13px; color: var(--accent); }}
  .advice-block ul {{ margin: 0; padding-left: 22px; }}
  .advice-block li {{ margin-bottom: 6px; color: #d1d5db; line-height: 1.55; }}
  .advice-uncertainty {{ margin-top: 14px; padding: 10px 12px; background: rgba(96,165,250,0.06);
                          border-left: 3px solid var(--accent); border-radius: 0 6px 6px 0;
                          color: var(--muted); font-size: 12.5px; line-height: 1.6; }}
  .advice-uncertainty strong {{ color: var(--accent); }}
  .sec-explain {{ background: rgba(96,165,250,0.06); border-left: 3px solid var(--accent);
                  padding: 14px 18px; margin-bottom: 12px; font-size: 13px; line-height: 1.7;
                  color: #cbd5e1; border-radius: 0 6px 6px 0; }}
  .sec-explain strong {{ color: #e5e7eb; }}
  .sec-explain em {{ color: var(--accent); font-style: normal; }}
  .sec-explain code {{ background: rgba(255,255,255,0.08); padding: 1px 6px;
                        border-radius: 3px; font-size: 12px; }}
  .sec-explain p {{ margin: 0 0 10px 0; }}
  .sec-explain p:last-child {{ margin-bottom: 0; }}
  .sec-explain ul {{ margin: 6px 0 10px 0; padding-left: 22px; }}
  .sec-explain li {{ margin-bottom: 4px; }}
  .card-row {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; }}
  .card {{ background: var(--panel); padding: 14px 16px; border-radius: 8px; border: 1px solid var(--border); }}
  .card-label {{ color: var(--muted); font-size: 12px; }}
  .card-value {{ font-size: 22px; font-weight: 600; margin-top: 4px; }}
  .grid-2 {{ display: grid; grid-template-columns: 320px 1fr; gap: 24px; align-items: start; }}
  .panel {{ background: var(--panel); padding: 16px; border-radius: 8px; border: 1px solid var(--border); }}
  .donut-container {{ display: flex; align-items: center; gap: 16px; }}
  .donut {{ flex-shrink: 0; }}
  .legend {{ display: flex; flex-direction: column; gap: 6px; }}
  .legend-item {{ display: flex; align-items: center; gap: 8px; font-size: 13px; }}
  .legend-item .count {{ color: var(--muted); margin-left: auto; }}
  .swatch {{ width: 14px; height: 14px; border-radius: 3px; display: inline-block; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }}
  th {{ background: var(--panel2); color: #cbd5e1; font-weight: 600; position: sticky; top: 0; }}
  th.sortable {{ cursor: pointer; user-select: none; }}
  th.sortable::before {{ content: " ↕"; color: var(--muted); font-size: 11px; }}
  th.num, td.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
  td.rank {{ color: var(--muted); }}
  td.fqn {{ font-family: ui-monospace, "Cascadia Code", monospace; font-size: 12px; }}
  td.path code {{ font-size: 11px; color: var(--muted); }}
  td.empty {{ text-align: center; color: var(--muted); padding: 20px; }}
  tr[data-grade="E"] {{ background: rgba(210,67,67,0.07); }}
  tr[data-grade="D"] {{ background: rgba(239,125,60,0.05); }}
  .grade-badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px;
                  color: #fff; font-weight: 600; font-size: 12px; min-width: 22px; text-align: center; }}
  .kv-table th, .kv-table td {{ padding: 6px 10px; }}
  .table-controls {{ display: flex; gap: 8px; margin-bottom: 8px; }}
  .table-controls input, .table-controls select {{
    background: var(--panel2); color: var(--fg); border: 1px solid var(--border);
    padding: 6px 10px; border-radius: 6px; font-size: 13px;
  }}
  .table-controls input {{ flex: 1; }}
  .graph-panel {{ overflow: hidden; }}
  .graph-meta {{ color: var(--muted); font-size: 12px; margin-bottom: 8px; }}
  .graph-meta em {{ color: var(--accent); font-style: normal; }}
  .graph-wrap {{ display: grid; grid-template-columns: 1fr 280px; gap: 12px; align-items: stretch; }}
  .depgraph {{ display: block; background: #0b1322; border-radius: 6px; width: 100%; height: 620px; }}
  .depgraph .node {{ cursor: pointer; transition: opacity 0.15s; }}
  .depgraph .node text {{ pointer-events: none; opacity: 0.7; }}
  .depgraph .node:hover circle {{ stroke: var(--accent); stroke-width: 3; }}
  .depgraph .node:hover text {{ opacity: 1; font-weight: 600; font-size: 12px; }}
  .depgraph.has-hover .node:not(.hl):not(.hl-neighbor) {{ opacity: 0.18; }}
  .depgraph.has-hover .edge:not(.hl-edge) {{ stroke-opacity: 0.08; }}
  .depgraph .edge.hl-edge {{ stroke: var(--accent); stroke-width: 1.6; stroke-opacity: 1; }}
  .graph-info {{ background: #0b1322; border-radius: 6px; padding: 14px; min-height: 620px;
                 font-size: 13px; overflow-y: auto; }}
  .graph-info .info-empty {{ color: var(--muted); text-align: center; padding-top: 60px; line-height: 1.6; }}
  .graph-info .info-fqn {{ font-family: ui-monospace, monospace; font-size: 12px;
                            word-break: break-all; color: #e2e8f0; margin-bottom: 8px; }}
  .graph-info .info-grade {{ display: inline-block; padding: 4px 12px; border-radius: 999px;
                              color: #fff; font-weight: 700; font-size: 13px; }}
  .graph-info .info-si {{ font-size: 28px; font-weight: 700; margin-left: 8px; }}
  .graph-info dl {{ display: grid; grid-template-columns: max-content 1fr; gap: 4px 12px;
                    margin: 12px 0; font-size: 12px; }}
  .graph-info dt {{ color: var(--muted); }}
  .graph-info dd {{ margin: 0; text-align: right; font-variant-numeric: tabular-nums; }}
  .graph-info .info-section {{ margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border); }}
  .graph-info .info-section h4 {{ font-size: 11px; color: var(--muted); margin: 0 0 4px 0;
                                    text-transform: uppercase; letter-spacing: 0.04em; }}
  .graph-info code.neighbor {{ display: inline-block; background: rgba(255,255,255,0.06);
                                padding: 1px 6px; border-radius: 4px; font-size: 11px;
                                margin: 2px 4px 2px 0; }}

  /* Project Health hero card */
  .health-hero {{ display: flex; gap: 24px; align-items: center; background: var(--panel);
                  padding: 24px; border-radius: 10px; border: 1px solid var(--border); }}
  .health-circle {{ width: 140px; height: 140px; border-radius: 50%; border: 6px solid;
                    display: flex; flex-direction: column; align-items: center; justify-content: center;
                    flex-shrink: 0; background: var(--panel2); }}
  .health-grade {{ font-size: 36px; font-weight: 800; line-height: 1; }}
  .health-score {{ font-size: 28px; font-weight: 600; margin-top: 4px; color: var(--fg); }}
  .health-unit {{ color: var(--muted); font-size: 12px; }}
  .health-info {{ flex: 1; }}
  .health-title {{ font-size: 13px; color: var(--muted); text-transform: uppercase;
                   letter-spacing: 0.05em; margin-bottom: 4px; }}
  .health-desc {{ font-size: 15px; margin-bottom: 14px; line-height: 1.5; }}
  .health-stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }}
  .health-stats > div {{ background: var(--panel2); padding: 10px 12px; border-radius: 6px;
                          display: flex; flex-direction: column; }}
  .hs-label {{ color: var(--muted); font-size: 12px; }}
  .hs-value {{ font-size: 18px; font-weight: 600; margin-top: 2px; }}

  /* Help box */
  .help {{ background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
           padding: 12px 16px; margin-bottom: 24px; }}
  .help > summary {{ cursor: pointer; color: var(--accent); font-weight: 600; user-select: none; }}
  .help-body {{ margin-top: 12px; font-size: 13px; line-height: 1.6; color: #cbd5e1; }}
  .help-body ul {{ padding-left: 22px; }}
  .help-body li {{ margin-bottom: 6px; }}
  .help-body .help-grade {{ margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border); font-size: 12px; }}
  .help-body .help-grade .grade-badge {{ margin: 0 4px; }}

  /* Hotspot notice / count */
  .table-notice {{ background: rgba(96, 165, 250, 0.07); border: 1px solid rgba(96, 165, 250, 0.25);
                   border-radius: 6px; padding: 10px 14px; margin-bottom: 12px; font-size: 13px;
                   color: #cbd5e1; }}
  .table-notice strong {{ color: var(--accent); }}
  .hotspot-count {{ color: var(--muted); font-size: 12px; align-self: center; }}

  /* 섹션 소개 문구 */
  .section-intro {{ background: rgba(96, 165, 250, 0.05); border-left: 3px solid var(--accent);
                    padding: 10px 14px; margin-bottom: 12px; font-size: 13px; color: #cbd5e1;
                    border-radius: 0 6px 6px 0; }}
  .section-intro strong {{ color: #e5e7eb; }}
  .section-intro code {{ background: rgba(255,255,255,0.08); padding: 1px 6px;
                          border-radius: 3px; font-size: 12px; }}

  /* Custom tooltip — [data-tooltip] 속성이 있는 요소 hover 시 표시 */
  [data-tooltip] {{ position: relative; cursor: help; }}
  [data-tooltip]::after {{
    content: attr(data-tooltip);
    position: absolute; left: 50%; bottom: calc(100% + 6px);
    transform: translateX(-50%);
    background: #020617; color: #f1f5f9; padding: 8px 10px; border-radius: 6px;
    font-size: 12px; line-height: 1.4; font-weight: 400;
    white-space: normal; width: max-content; max-width: 260px;
    text-align: left; pointer-events: none; opacity: 0;
    transition: opacity 0.12s; z-index: 100;
    border: 1px solid #334155;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  }}
  [data-tooltip]:hover::after, [data-tooltip]:focus::after {{ opacity: 1; }}
  th[data-tooltip] {{ cursor: help; }}

  /* Graph controls — 검색 + 등급 토글 */
  .graph-controls {{ display: flex; gap: 12px; align-items: center; margin-bottom: 10px;
                     flex-wrap: wrap; }}
  .graph-controls input {{
    background: var(--panel2); color: var(--fg); border: 1px solid var(--border);
    padding: 6px 10px; border-radius: 6px; font-size: 13px; flex: 1; min-width: 280px;
  }}
  .grade-toggle {{ display: flex; gap: 4px; align-items: center; }}
  .gt-label {{ color: var(--muted); font-size: 12px; margin-right: 4px; }}
  .gt-btn {{ background: var(--panel2); color: var(--muted); border: 1px solid var(--border);
             padding: 4px 12px; border-radius: 6px; font-size: 12px; font-weight: 600;
             cursor: pointer; transition: all 0.1s; }}
  .gt-btn:hover {{ color: var(--fg); border-color: #475569; }}
  .gt-btn.gt-active {{ color: #fff; }}
  .gt-btn[data-grade="A"].gt-active {{ background: #3b8e5a; border-color: #3b8e5a; }}
  .gt-btn[data-grade="B"].gt-active {{ background: #7fb95a; border-color: #7fb95a; }}
  .gt-btn[data-grade="C"].gt-active {{ background: #e3b341; border-color: #e3b341; color: #111; }}
  .gt-btn[data-grade="D"].gt-active {{ background: #ef7d3c; border-color: #ef7d3c; }}
  .gt-btn[data-grade="E"].gt-active {{ background: #d24343; border-color: #d24343; }}
  .gt-btn[data-grade=""].gt-active {{ background: var(--accent); border-color: var(--accent); }}
  .graph-match-count {{ color: var(--muted); font-size: 12px; }}
  .graph-match-count.warn {{ color: #fbbf24; }}
  .graph-zoom {{ display: flex; gap: 4px; }}
  .graph-zoom button {{ background: var(--panel2); color: var(--fg); border: 1px solid var(--border);
                         padding: 4px 12px; border-radius: 6px; font-size: 13px; cursor: pointer;
                         font-weight: 600; min-width: 38px; }}
  .graph-zoom button:hover {{ background: #1f2a3a; border-color: var(--accent); }}
  .graph-tip {{ background: rgba(96,165,250,0.06); border-radius: 4px;
                padding: 8px 12px; margin-bottom: 10px; font-size: 12px; color: #cbd5e1; }}
  .graph-tip strong {{ color: var(--accent); }}
  .depgraph {{ cursor: grab; }}
  .depgraph.dragging {{ cursor: grabbing; }}

  /* 검색 매치 강조 */
  .depgraph .node.search-match circle {{
    stroke: #fff; stroke-width: 2.5;
    filter: drop-shadow(0 0 6px rgba(96, 165, 250, 0.9));
  }}
  .depgraph .node.search-match text {{ opacity: 1; font-weight: 700; font-size: 11px; fill: #fff; }}
  .depgraph.has-search .node:not(.search-match):not(.hl):not(.hl-neighbor) {{ opacity: 0.25; }}

  .help-body .help-tip {{ margin-top: 10px; padding: 8px 12px; background: rgba(96,165,250,0.06);
                           border-radius: 4px; font-size: 12px; }}
  .cycle-count {{ background: var(--panel2); border-radius: 8px; padding: 16px 20px;
                  display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px;
                  border-left: 4px solid #d24343; max-width: 480px; }}
  .cycle-count-zero {{ border-left-color: #3b8e5a; }}
  .cc-number {{ font-size: 36px; font-weight: 800; line-height: 1; color: #f1f5f9;
                font-variant-numeric: tabular-nums; }}
  .cc-label {{ color: var(--muted); font-size: 13px; }}
  .cc-hint {{ color: #cbd5e1; font-size: 12px; margin-top: 4px; }}
  .cycle-list details {{ background: var(--panel2); padding: 10px 12px; border-radius: 6px; margin-bottom: 6px; }}
  .cycle-list summary {{ cursor: pointer; display: flex; gap: 12px; align-items: center; }}
  .cycle-stat {{ color: #cbd5e1; font-size: 13px; }}
  .cycle-stat strong {{ color: #f1f5f9; font-variant-numeric: tabular-nums; }}
  .cycle-rank {{ color: var(--muted); font-variant-numeric: tabular-nums; }}
  .cycle-list ul {{ margin: 10px 0 0 24px; padding: 0; }}
  .cycle-list li {{ margin-bottom: 2px; }}
  .cycle-member {{ font-family: ui-monospace, monospace; font-size: 12px; padding: 1px 6px;
                   border-radius: 4px; background: rgba(255,255,255,0.05); }}
  .cycle-member.grade-D, .cycle-member.grade-E {{ background: rgba(210,67,67,0.15); }}
  .empty {{ color: var(--muted); padding: 12px; text-align: center; }}
  .analysis-status, .analysis-info {{ padding: 14px 18px; border: 1px solid var(--border); border-radius: 8px; margin-bottom: 20px; color: var(--muted); font-size: 13px; }}
  .analysis-status > strong {{ color: var(--fg); margin-right: 16px; }}
  .analysis-status > span {{ display: inline-block; }}
  .analysis-status.partial {{ border-left: 3px solid #e3b341; }}
  .analysis-status.partial > strong {{ color: #e3b341; }}
  .status-heading {{ display: flex; flex-wrap: wrap; gap: 6px 16px; align-items: baseline; margin-bottom: 12px; }}
  .status-heading strong {{ color: var(--fg); font-size: 18px; }}
  .analysis-status.partial .status-heading strong {{ color: #e3b341; }}
  .status-counts {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline; color: #cbd5e1; line-height: 1.8; }}
  .status-metric {{ display: inline-block; border-bottom: 1px dotted #64748b; }}
  .status-metric:focus {{ outline: 2px solid var(--accent); outline-offset: 3px; }}
  .status-metric::after {{ left: 0; transform: none; width: 320px; max-width: min(320px, 80vw); bottom: auto; top: calc(100% + 8px); }}
  .status-note {{ margin: 12px 0; line-height: 1.7; }}
  .status-metric::after {{ white-space: pre-line; }}
  .status-coverage {{ margin: 0 0 12px; color: #cbd5e1; font-size: 14px; }}
  .status-coverage strong {{ color: var(--fg); font-size: 18px; margin: 0 3px; }}
  .analysis-status .analysis-info {{ padding: 0; border: 0; margin: 10px 0 0; }}
  .analysis-info > summary {{ cursor: pointer; color: var(--accent); }}
  .analysis-info h3 {{ font-size: 13px; color: var(--fg); }}
  .analysis-issues {{ max-height: 240px; overflow: auto; overflow-wrap: anywhere; }}
  .analysis-info ul {{ padding-left: 20px; }}
  footer {{ padding: 20px 32px; color: var(--muted); font-size: 12px; text-align: center; border-top: 1px solid var(--border); }}
</style>
</head>
<body>
<header>
  <h1>{project_name}</h1>
  {project_subtitle}
  <div class="report-kind">Game Spaghetti Index Report</div>
  <div class="meta">분석 시각: {analyzed_at}</div>
</header>
<main>

{help_box}

{analysis_status}

<section>
  <div class="sec-head">
    <h2>구조 요약 (보조 Health)</h2>
    <button class="sec-info" data-target="help-health" aria-expanded="false">ⓘ 이 섹션이 뭔가요?</button>
  </div>
  <div class="sec-explain" id="help-health" hidden>
    <p><strong>검증되지 않은 보조 구조 요약</strong>입니다. 상대 순위 기반 항목을 포함하므로 절대 코드 품질이나 프로젝트 간 우열을 판정하지 않습니다.</p>
    <p>다음 네 가지 신호를 가중 평균합니다.</p>
    <ul>
      <li><strong>평균 G-SI (45%)</strong> — 프로젝트 안 모든 클래스의 G-SI 점수를 단순 평균. 가장 큰 비중.</li>
      <li><strong>상대 D+E 비율 (25%)</strong> — G-SI 60 이상인 클래스 비율. 결함 비율이 아닙니다.</li>
      <li><strong>순환 의존성 수 (15%)</strong> — A→B→C→A 처럼 서로 참조해서 빙빙 도는 묶음의 개수. 로그 스케일 적용(0 → 0점, 1 → 30점, 5 → 70점, 20 이상 → 100점).</li>
      <li><strong>평균 결합도 (15%)</strong> — 클래스 한 개당 평균적으로 몇 개의 다른 클래스와 연결되는지(fan-in+fan-out 평균). 평균 10 이상이면 100점으로 saturate.</li>
    </ul>
    <p>A~E는 수치 구간만 표시합니다. 평균 G-SI와 D/E 비율은 백분위 공식과 동점에 영향을 받으므로, 이 수치를 전체 품질의 증거로 발표하지 마세요.</p>
  </div>
  {health_hero}
</section>

<section>
  <div class="sec-head">
    <h2>Summary</h2>
    <button class="sec-info" data-target="help-summary" aria-expanded="false">ⓘ 이 섹션이 뭔가요?</button>
  </div>
  <div class="sec-explain" id="help-summary" hidden>
    <p>분석 규모와 위험 신호를 6개 숫자로 압축한 카드 묶음입니다.</p>
    <ul>
      <li><strong>분석 클래스</strong> — 추출된 타입 및 C/C++ 함수 묶음의 총 개수.</li>
      <li><strong>분석 메서드</strong> — 분석된 모든 메서드와 생성자(.ctor)의 합. enum 항목, 자동 속성은 카운트하지 않습니다.</li>
      <li><strong>의존성 순환(SCC ≥ 2)</strong> — 크기가 2 이상인 강한 연결 요소(Strongly Connected Component). 적을수록 좋고, 0이면 의존성이 한 방향으로 흐른다는 좋은 신호입니다.</li>
      <li><strong>평균 G-SI</strong> — 클래스 단위 G-SI 점수의 단순 평균. Project Health의 가장 큰 입력입니다.</li>
      <li><strong>최대 G-SI</strong> — 최대 상대 백분위. 비어 있지 않은 분석 집합에서는 항상 100이므로 품질 비교 정보가 없습니다.</li>
      <li><strong>상대 D/E 클래스</strong> — G-SI 60 이상인 클래스 수. 실제 결함이나 리팩토링 필요성은 소스 검토로 확인합니다.</li>
    </ul>
    <p>각 카드에 마우스를 올리면 동일한 설명이 풍선으로 표시됩니다.</p>
  </div>
  <div class="card-row">{summary_cards}</div>
</section>

<section>
  <div class="sec-head">
    <h2>등급 분포 및 가중치</h2>
    <button class="sec-info" data-target="help-dist" aria-expanded="false">ⓘ 이 섹션이 뭔가요?</button>
  </div>
  <div class="sec-explain" id="help-dist" hidden>
    <p><strong>왼쪽 등급 분포</strong>는 분석 집합 내부의 상대 백분위 구간입니다. 동점이 많으면 분포가 불균등하며 모두 동점이면 전부 E가 됩니다.</p>
    <p>평균·최대 G-SI를 보더라도 다른 프로젝트와 절대 품질을 비교할 수 없습니다. 원시 메트릭과 실제 소스를 함께 확인하세요.</p>
    <p><strong>오른쪽 표</strong>는 고정 기본 가중치입니다. 튜닝 옵션도 구현되어 있지만, 가중치 탐색과 지표 제거 실험은 탐색적 결과이며 산식의 신뢰성을 자동으로 입증하지 않습니다.</p>
  </div>
  <div class="grid-2">
    <div class="panel">{grade_donut}</div>
    <div class="panel">{weights_table}</div>
  </div>
</section>

<section>
  <div class="sec-head">
    <h2>Hotspot Table (G-SI 상위)</h2>
    <button class="sec-info" data-target="help-hotspot" aria-expanded="false">ⓘ 이 섹션이 뭔가요?</button>
  </div>
  <div class="sec-explain" id="help-hotspot" hidden>
    <p><strong>위험한 순서로 정렬된 클래스 목록</strong>입니다. 기본은 전체 클래스 중 G-SI 상위 N개를 보여주며, 두 가지 방법으로 표를 좁힐 수 있습니다.</p>
    <ul>
      <li><strong>등급 필터</strong> — A~E 중 하나를 선택하면 <em>그 등급 안에서 다시 상위 N개</em>를 골라 표를 새로 그립니다. "B 등급 안에서 가장 위험한 30개"처럼 봅니다.</li>
      <li><strong>텍스트 검색</strong> — 클래스의 정규 이름(FQN)이나 파일 경로 일부를 입력하면 일치하는 클래스만 남깁니다. 등급 필터와 동시 적용 가능합니다.</li>
    </ul>
    <p><strong>컬럼별 의미</strong> — 헤더에 마우스를 올리면 각 컬럼이 무엇을 측정하는지 설명이 표시됩니다. 컬럼 헤더를 클릭하면 그 항목 기준으로 정렬됩니다(다시 누르면 역순). 우측 카운터는 "현재 보이는 행 수 / 조건을 만족하는 전체 / 프로젝트 전체"를 보여줍니다.</p>
    <p><strong>주요 원인</strong> 컬럼은 G-SI 점수에 가장 크게 기여한 두 항목을 알려 줍니다. 예를 들어 "cc, global_state" 는 그 클래스가 분기가 많고 전역 상태에 강하게 의존한다는 뜻입니다.</p>
  </div>
  {hotspot_table}
</section>

<section>
  <div class="sec-head">
    <h2>Dependency Graph (G-SI 상위 hotspot 중심)</h2>
    <button class="sec-info" data-target="help-graph" aria-expanded="false">ⓘ 이 섹션이 뭔가요?</button>
  </div>
  <div class="sec-explain" id="help-graph" hidden>
    <p><strong>위험 클래스 주변의 참조 관계</strong>를 점과 선으로 그린 그래프입니다.</p>
    <ul>
      <li><strong>점(노드) = 클래스</strong>. 색은 등급(A 녹색 ~ E 빨강), 크기는 결합도(다른 클래스와 연결된 정도)에 비례합니다.</li>
      <li><strong>선(엣지) = 한 클래스가 다른 클래스를 참조하는 의존성</strong>. 화살표 방향은 "이 클래스를 사용한다"의 방향입니다.</li>
      <li><strong>표시 범위</strong> — G-SI 상위 hotspot 부터 채우고 그 인접 클래스까지 포함하되, 노드 수가 최대 150개를 넘지 않도록 제한합니다. 그래서 작은 프로젝트는 그래프 전체가, 큰 프로젝트는 가장 위험한 영역만 표시됩니다.</li>
      <li><strong>A · B 등급 노드가 보이지 않는 이유</strong> — 그래프 자체가 위험 클래스 중심으로 그려지기 때문에 표시 범위 안에는 거의 D · E 등급(과 일부 C)만 포함됩니다. A · B 클래스는 위 등급 분포 차트와 Hotspot Table 등급 필터에서 확인하세요.</li>
    </ul>
    <p><strong>사용법</strong></p>
    <ul>
      <li><strong>마우스 휠</strong> — 커서 위치를 중심으로 확대 / 축소.</li>
      <li><strong>드래그</strong> — 보이는 영역 이동(pan).</li>
      <li><strong>＋ / − / 리셋 버튼</strong> — 중앙 기준 확대 / 축소 / 처음 배율로 복귀.</li>
      <li><strong>노드 hover</strong> — 그 클래스가 진해지고 인접 노드 / 엣지만 강조, 나머지는 흐려짐. 우측 패널에 FQN · G-SI · 등급 · 메트릭 · fan-in/out · 인접 클래스 샘플이 표시됩니다.</li>
      <li><strong>검색</strong> — 이름의 일부를 입력하면 매칭 노드가 흰 후광으로 강조됩니다. 매칭 안 된 노드는 흐려지지만 hover로 인접 관계는 그대로 볼 수 있습니다.</li>
      <li><strong>등급 강조 버튼</strong> — A~E 중 하나를 누르면 그 등급 노드만 강조. 검색과 동시 적용 가능합니다.</li>
    </ul>
  </div>
  <div class="panel graph-panel">{dependency_graph}</div>
</section>

<section>
  <div class="sec-head">
    <h2>Cycle Explorer (Strongly Connected Components)</h2>
    <button class="sec-info" data-target="help-cycle" aria-expanded="false">ⓘ 이 섹션이 뭔가요?</button>
  </div>
  <div class="sec-explain" id="help-cycle" hidden>
    <p><strong>A → B → C → A 처럼 서로 참조해서 빙빙 도는 클래스 묶음</strong>(Strongly Connected Component, SCC)을 모은 섹션입니다.</p>
    <p>일반적으로 의존성은 한 방향으로 흘러야 합니다(예: UI → 로직 → 데이터). 그런데 두 클래스가 서로를 참조하기 시작하면, 한쪽을 수정할 때 반드시 다른 쪽도 함께 신경 써야 합니다. 이런 묶음이 3개, 4개로 커지면 영향 범위 추적이 사실상 불가능에 가까워집니다. 그래서 SCC는 리팩토링 1순위 후보입니다.</p>
    <p>본 섹션의 <strong>카운트 카드 숫자가 곧 프로젝트 안의 모든 SCC 수</strong>입니다. 상위 N개를 보여주는 것이 아니라 전부 나열합니다. 프로젝트마다 수치가 다른데, 예를 들어 OpenRA.Game 모듈은 5개, OpenRA.Mods.Common 모듈은 4개의 묶음이 있습니다.</p>
    <p>각 항목을 클릭하면 그 묶음에 속한 클래스 FQN 목록이 펼쳐집니다. 묶음 안의 모든 클래스가 동일한 SCC에 있다는 사실 자체가 이미 위험 신호이므로, 점수가 낮은 클래스라도 함께 정리 대상이 됩니다.</p>
  </div>
  <div class="panel">{cycle_explorer}</div>
</section>

<section>
  <div class="sec-head">
    <h2>Module Summary</h2>
    <button class="sec-info" data-target="help-module" aria-expanded="false">ⓘ 이 섹션이 뭔가요?</button>
  </div>
  <div class="sec-explain" id="help-module" hidden>
    <p>클래스 G-SI의 파일별 최대값을 <strong>최상위 폴더(모듈) 단위로 집계</strong>한 표입니다. 상대 순위 요약이며 절대 품질이 아닙니다.</p>
    <p><strong>컬럼 의미</strong></p>
    <ul>
      <li><strong>모듈</strong> — 분석 입력 폴더 바로 아래의 1단계 폴더 이름. 예를 들어 OpenRA.Game을 분석하면 Network, Server, Map 등이 모듈로 잡힙니다. <code>(root)</code>는 폴더 안에 들어있지 않고 분석 폴더 바로 밑에 놓인 .cs 파일들을 한 모듈로 묶은 것입니다.</li>
      <li><strong>등급</strong> — 모듈 내 파일 최대 G-SI의 평균을 기준으로 한 A~E 구간.</li>
      <li><strong>평균 G-SI</strong> — 각 파일의 si_max를 구한 뒤 파일별 동일 비중으로 평균. 클래스 전체 평균과 다릅니다.</li>
      <li><strong>최대 G-SI</strong> — 모듈에서 가장 위험한 클래스 하나의 G-SI. 평균은 낮은데 최대만 높다면 그 모듈에 핀포인트 hotspot이 있다는 신호입니다.</li>
      <li><strong>파일 수 · 클래스 수</strong> — 모듈에 속한 .cs 파일과 클래스(struct, interface, record 포함)의 개수.</li>
    </ul>
    <p>모듈 단위로 보면 어느 컴포넌트가 통째로 정리 대상인지, 아니면 특정 클래스만 문제인지 빠르게 판단할 수 있습니다.</p>
  </div>
  {module_table}
</section>

{refactoring_guide}

</main>
<footer>
  Generated by <code>game-si</code> · static-only metrics (G-SI-Static) · CDN-free single-file report
</footer>

<script>
(function() {{
  const dataRoot = {embedded_json};
  window.__GAME_SI__ = dataRoot;
  const GRADE_COLORS = dataRoot.grade_colors;
  const TOP_N = dataRoot.hotspot_top_n || 30;
  const ALL_CLASSES = dataRoot.all_classes || [];

  // ----- Hotspot Table 동적 렌더링 -----
  const textInput = document.getElementById('hotspot-filter');
  const gradeSelect = document.getElementById('grade-filter');
  const tbody = document.getElementById('hotspot-tbody');
  const countSpan = document.getElementById('hotspot-count');

  function escapeHtml(s) {{
    return String(s).replace(/[&<>"']/g, c => ({{
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }})[c]);
  }}

  let sortKey = 'si';
  let sortAsc = false;

  function renderHotspots() {{
    if (!tbody) return;
    const needle = (textInput.value || '').toLowerCase();
    const grade = gradeSelect.value;

    // 1) 등급/텍스트 필터로 후보 추출
    let candidates = ALL_CLASSES.filter(c => {{
      if (grade && c.grade !== grade) return false;
      if (needle) {{
        const text = (c.fqn + ' ' + c.file_path).toLowerCase();
        if (!text.includes(needle)) return false;
      }}
      return true;
    }});

    // 2) 정렬
    candidates.sort((a, b) => {{
      const av = a[sortKey];
      const bv = b[sortKey];
      const cmp = (typeof av === 'number') ? (av - bv) : String(av).localeCompare(String(bv));
      return cmp * (sortAsc ? 1 : -1);
    }});

    const totalMatched = candidates.length;
    const shown = candidates.slice(0, TOP_N);

    // 3) DOM 렌더링
    if (shown.length === 0) {{
      tbody.innerHTML = '<tr><td colspan="11" class="empty">조건에 맞는 클래스가 없습니다.</td></tr>';
    }} else {{
      tbody.innerHTML = shown.map((c, i) => {{
        const reasons = (c.top_reasons && c.top_reasons.length) ? c.top_reasons.join(', ') : '—';
        const color = GRADE_COLORS[c.grade] || '#475569';
        return `<tr data-grade="${{c.grade}}">
          <td class="num rank">${{i + 1}}</td>
          <td><span class="grade-badge" style="background:${{color}}">${{c.grade}}</span></td>
          <td class="num">${{c.si.toFixed(1)}}</td>
          <td class="fqn" title="${{escapeHtml(c.fqn)}}">${{escapeHtml(c.fqn)}}</td>
          <td class="num">${{c.cc.toFixed(1)}}</td>
          <td class="num">${{c.coupling}}</td>
          <td class="num">${{c.global_state}}</td>
          <td class="num">${{c.dependency_cycle}}</td>
          <td class="num">${{c.game_loop_centrality.toFixed(2)}}</td>
          <td class="reasons">${{escapeHtml(reasons)}}</td>
          <td class="path"><code>${{escapeHtml(c.file_path)}}:${{c.start_line}}</code></td>
        </tr>`;
      }}).join('');
    }}

    if (countSpan) {{
      if (grade || needle) {{
        countSpan.textContent = `${{shown.length}} / ${{totalMatched}} 개 표시 (전체 ${{ALL_CLASSES.length}})`;
      }} else {{
        countSpan.textContent = `${{shown.length}} / ${{ALL_CLASSES.length}} 개 표시`;
      }}
    }}
  }}

  if (textInput) textInput.addEventListener('input', renderHotspots);
  if (gradeSelect) gradeSelect.addEventListener('change', renderHotspots);

  // 컬럼 정렬: 헤더 클릭으로 sortKey 변경
  const sortableHeaders = {{
    2: 'si', 3: 'fqn', 4: 'cc', 5: 'coupling',
    6: 'global_state', 7: 'dependency_cycle', 8: 'game_loop_centrality'
  }};
  const table = document.getElementById('hotspot-table');
  if (table) {{
    table.querySelectorAll('th.sortable').forEach(th => {{
      th.addEventListener('click', () => {{
        const colIdx = Array.from(th.parentNode.children).indexOf(th);
        const key = sortableHeaders[colIdx];
        if (!key) return;
        if (sortKey === key) {{
          sortAsc = !sortAsc;
        }} else {{
          sortKey = key;
          sortAsc = (key === 'fqn');  // 이름은 오름차순 디폴트, 수치는 내림차순
        }}
        renderHotspots();
      }});
    }});
  }}

  renderHotspots();

  // ----- Dependency Graph 인터랙션 -----
  // GRADE_COLORS는 이미 위에서 dataRoot.grade_colors로 선언되어 있다 (중복 선언 금지).
  const graphSvg = document.getElementById('depgraph');
  const graphInfo = document.getElementById('graph-info');
  const nodeInfoScript = document.getElementById('graph-node-info');
  if (graphSvg && graphInfo && nodeInfoScript) {{
    const nodeInfo = JSON.parse(nodeInfoScript.textContent);
    const allNodes = graphSvg.querySelectorAll('.node');
    const allEdges = graphSvg.querySelectorAll('.edge');

    function clearHl() {{
      graphSvg.classList.remove('has-hover');
      allNodes.forEach(n => n.classList.remove('hl', 'hl-neighbor'));
      allEdges.forEach(e => e.classList.remove('hl-edge'));
    }}

    function renderInfo(idx) {{
      const info = nodeInfo[idx];
      if (!info) return;
      const color = GRADE_COLORS[info.grade] || '#475569';
      const reasons = (info.top_reasons && info.top_reasons.length)
        ? info.top_reasons.join(', ') : '—';
      const raw = info.raw || {{}};
      const inList = (info.sample_neighbors && info.sample_neighbors.in.length)
        ? info.sample_neighbors.in.map(n => `<code class="neighbor">${{n}}</code>`).join('')
        : '<span style="color: var(--muted); font-size: 11px;">없음</span>';
      const outList = (info.sample_neighbors && info.sample_neighbors.out.length)
        ? info.sample_neighbors.out.map(n => `<code class="neighbor">${{n}}</code>`).join('')
        : '<span style="color: var(--muted); font-size: 11px;">없음</span>';
      graphInfo.innerHTML = `
        <div class="info-fqn">${{info.fqn}}</div>
        <div>
          <span class="info-grade" style="background:${{color}}">${{info.grade}}</span>
          <span class="info-si">${{info.si !== null ? info.si.toFixed(0) : '?'}}</span>
          <span style="color: var(--muted); font-size: 13px;">/ 100</span>
        </div>
        <dl>
          <dt>Cyclomatic Complexity</dt><dd>${{(raw.cc || 0).toFixed(1)}}</dd>
          <dt>Coupling</dt><dd>${{Math.round(raw.coupling || 0)}}</dd>
          <dt>Global State</dt><dd>${{Math.round(raw.global_state || 0)}}</dd>
          <dt>Cycle Size</dt><dd>${{Math.round(raw.dependency_cycle || 0)}}</dd>
          <dt>Game Loop Centrality</dt><dd>${{(raw.game_loop_centrality || 0).toFixed(2)}}</dd>
          <dt>Fan-in / Fan-out</dt><dd>${{info.fan_in || 0}} / ${{info.fan_out || 0}}</dd>
        </dl>
        <div class="info-section">
          <h4>주요 위험 원인</h4>
          <div style="font-size: 12px;">${{reasons}}</div>
        </div>
        <div class="info-section">
          <h4>이 클래스를 참조하는 클래스 (샘플)</h4>
          <div>${{inList}}</div>
        </div>
        <div class="info-section">
          <h4>이 클래스가 참조하는 클래스 (샘플)</h4>
          <div>${{outList}}</div>
        </div>
      `;
    }}

    function highlight(node) {{
      clearHl();
      graphSvg.classList.add('has-hover');
      node.classList.add('hl');
      const idx = node.getAttribute('data-idx');
      const info = nodeInfo[idx];
      const neighborIdxs = new Set((info && info.neighbor_idxs) || []);
      allNodes.forEach(n => {{
        const ni = n.getAttribute('data-idx');
        if (neighborIdxs.has(parseInt(ni, 10))) n.classList.add('hl-neighbor');
      }});
      allEdges.forEach(e => {{
        const src = parseInt(e.getAttribute('data-src'), 10);
        const dst = parseInt(e.getAttribute('data-dst'), 10);
        if (src === parseInt(idx, 10) || dst === parseInt(idx, 10)) {{
          e.classList.add('hl-edge');
        }}
      }});
      renderInfo(idx);
    }}

    allNodes.forEach(node => {{
      node.addEventListener('mouseenter', () => highlight(node));
    }});

    // ----- Dependency Graph 검색 & 등급 토글 -----
    const graphSearch = document.getElementById('graph-search');
    const gradeToggle = document.getElementById('graph-grade-toggle');
    const matchCount = document.getElementById('graph-match-count');

    function getNodeGrade(nodeEl) {{
      const idx = nodeEl.getAttribute('data-idx');
      const info = nodeInfo[idx];
      return info ? info.grade : null;
    }}

    function applyGraphSearch() {{
      const needle = (graphSearch ? graphSearch.value : '').trim().toLowerCase();
      const activeGradeBtn = gradeToggle ? gradeToggle.querySelector('.gt-active') : null;
      const gradeFilter = activeGradeBtn ? activeGradeBtn.getAttribute('data-grade') : '';
      const hasFilter = !!(needle || gradeFilter);

      let matched = 0;
      allNodes.forEach(node => {{
        const fqn = (node.getAttribute('data-fqn') || '').toLowerCase();
        const grade = getNodeGrade(node);
        const textOk = !needle || fqn.includes(needle);
        const gradeOk = !gradeFilter || grade === gradeFilter;
        if (hasFilter && textOk && gradeOk) {{
          node.classList.add('search-match');
          matched++;
        }} else {{
          node.classList.remove('search-match');
        }}
      }});
      graphSvg.classList.toggle('has-search', hasFilter);

      if (matchCount) {{
        if (hasFilter) {{
          if (matched === 0) {{
            const reason = gradeFilter
              ? `이 그래프에는 ${{gradeFilter}} 등급 노드가 없습니다 (그래프는 위험 클래스 중심 표시)`
              : `검색어와 일치하는 노드가 없습니다`;
            matchCount.textContent = reason;
            matchCount.classList.add('warn');
          }} else {{
            matchCount.textContent = `${{matched}}개 노드 강조됨`;
            matchCount.classList.remove('warn');
          }}
        }} else {{
          matchCount.textContent = '';
          matchCount.classList.remove('warn');
        }}
      }}
    }}

    if (graphSearch) graphSearch.addEventListener('input', applyGraphSearch);
    if (gradeToggle) {{
      gradeToggle.querySelectorAll('.gt-btn').forEach(btn => {{
        btn.addEventListener('click', () => {{
          gradeToggle.querySelectorAll('.gt-btn').forEach(b => b.classList.remove('gt-active'));
          btn.classList.add('gt-active');
          applyGraphSearch();
        }});
      }});
    }}

    graphSvg.addEventListener('mouseleave', () => {{
      clearHl();
      graphInfo.innerHTML = '<div class="info-empty">노드 위에 마우스를 올리면<br>여기에 상세 정보가 나타납니다.<br><br>아래 검색창에 클래스 이름을 입력하거나 등급 버튼을 누르면<br>해당 노드가 강조됩니다.</div>';
    }});

    // ----- Dependency Graph zoom / pan -----
    const initialVB = graphSvg.getAttribute('viewBox').split(' ').map(Number);
    let vb = {{ x: initialVB[0], y: initialVB[1], w: initialVB[2], h: initialVB[3] }};

    function applyVB() {{
      graphSvg.setAttribute('viewBox', `${{vb.x}} ${{vb.y}} ${{vb.w}} ${{vb.h}}`);
    }}

    function zoomAt(factor, focusX, focusY) {{
      // focusX/Y in viewBox coords
      const newW = vb.w / factor;
      const newH = vb.h / factor;
      // 최소·최대 줌 제한
      if (newW < initialVB[2] * 0.1 || newW > initialVB[2] * 4) return;
      vb.x = focusX - (focusX - vb.x) / factor;
      vb.y = focusY - (focusY - vb.y) / factor;
      vb.w = newW;
      vb.h = newH;
      applyVB();
    }}

    graphSvg.addEventListener('wheel', (e) => {{
      e.preventDefault();
      const pt = graphSvg.createSVGPoint();
      pt.x = e.clientX; pt.y = e.clientY;
      const sp = pt.matrixTransform(graphSvg.getScreenCTM().inverse());
      const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      zoomAt(factor, sp.x, sp.y);
    }}, {{ passive: false }});

    let dragging = false, dragStart = null;
    graphSvg.addEventListener('mousedown', (e) => {{
      if (e.target.closest('.node')) return; // 노드 위에서는 hover 동작 우선
      dragging = true;
      dragStart = {{ x: e.clientX, y: e.clientY, vbX: vb.x, vbY: vb.y }};
      graphSvg.classList.add('dragging');
    }});
    window.addEventListener('mousemove', (e) => {{
      if (!dragging) return;
      const rect = graphSvg.getBoundingClientRect();
      const scaleX = vb.w / rect.width;
      const scaleY = vb.h / rect.height;
      vb.x = dragStart.vbX - (e.clientX - dragStart.x) * scaleX;
      vb.y = dragStart.vbY - (e.clientY - dragStart.y) * scaleY;
      applyVB();
    }});
    window.addEventListener('mouseup', () => {{
      dragging = false;
      graphSvg.classList.remove('dragging');
    }});

    const zoomIn = document.getElementById('zoom-in');
    const zoomOut = document.getElementById('zoom-out');
    const zoomReset = document.getElementById('zoom-reset');
    if (zoomIn) zoomIn.addEventListener('click', () => zoomAt(1.25, vb.x + vb.w / 2, vb.y + vb.h / 2));
    if (zoomOut) zoomOut.addEventListener('click', () => zoomAt(1 / 1.25, vb.x + vb.w / 2, vb.y + vb.h / 2));
    if (zoomReset) zoomReset.addEventListener('click', () => {{
      vb = {{ x: initialVB[0], y: initialVB[1], w: initialVB[2], h: initialVB[3] }};
      applyVB();
    }});
  }}

  // ----- 섹션 헤더 ⓘ 설명 토글 -----
  document.querySelectorAll('.sec-info').forEach(btn => {{
    btn.addEventListener('click', () => {{
      const targetId = btn.getAttribute('data-target');
      const target = document.getElementById(targetId);
      if (!target) return;
      const isHidden = target.hasAttribute('hidden');
      if (isHidden) {{
        target.removeAttribute('hidden');
        btn.setAttribute('aria-expanded', 'true');
        btn.textContent = '✕ 설명 닫기';
      }} else {{
        target.setAttribute('hidden', '');
        btn.setAttribute('aria-expanded', 'false');
        btn.textContent = 'ⓘ 이 섹션이 뭔가요?';
      }}
    }});
  }});
}})();
</script>
</body>
</html>
"""
