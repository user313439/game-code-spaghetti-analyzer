"""User-facing report status: truthful counts, concise reasons and shared layout."""

import copy
from html.parser import HTMLParser

import networkx as nx
import pytest

from game_si.cli import _build_parser, main
from game_si.metrics import MetricsResult
from game_si.report import _render_analysis_status, _render_html, _render_help_box
from game_si.si import compute_si_static


class StatusReader(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.metrics = []
        self.completions = []
        self.details = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('class') == 'status-metric':
            self.metrics.append(attrs)
        if attrs.get('class') == 'status-completion':
            self.completions.append(attrs)
        if tag == 'details':
            self.details.append(attrs)


def native_status(state='partial'):
    return dict(state=state, backend='clang', analysis_unit='implementation_file',
                registered_files=69, analyzed_files=69, unregistered_files=2,
                failed_files=0, compiler_error_files=26, compiler_error_count=3845,
                compiler_warning_files=69, compiler_warning_count=1120,
                runtime={'library': 'C:/private/path/lib.dll', 'native_version': '20.1.8'},
                configuration={'path': 'C:/private/config.json', 'sha256': 'SECRET_HASH',
                               'entries': [{'entry_index': 4, 'arguments': ['-Iprivate']} ]},
                errors=[], compiler_diagnostics=[], limitations=['범위 제한 <한계>'])


@pytest.mark.parametrize('state,label', [('complete', '분석 완료'),
                                        ('partial', '부분 분석'), ('failed', '분석 실패')])
def test_native_states_have_same_focusable_tooltip_layout(state, label):
    status = native_status(state)
    if state == 'complete':
        status.update(compiler_error_files=0, compiler_error_count=0)
    original = copy.deepcopy(status)
    view = _render_analysis_status(status)
    reader = StatusReader(view)
    assert label in view
    assert len(reader.metrics) == 7
    assert all(m.get('tabindex') == '0' and m.get('data-tooltip') for m in reader.metrics)
    assert '추출 69개' in view and '미등록 2개' in view
    assert '컴파일 경고 69개 파일/1,120건' in view
    assert '완전한 분석' in view and '게임의 실제 버그 개수' in view
    assert all('open' not in d for d in reader.details)
    assert len(reader.details) == (1 if state == 'complete' else 2)
    assert status == original
    assert '&lt;한계&gt;' in view and '<한계>' not in view
    for technical in ('C:/private', 'SECRET_HASH', 'entry_index', 'arguments='):
        assert technical not in view


def test_native_zero_diagnostics_and_partial_reason_are_truthful():
    status = native_status('complete')
    status.update(compiler_error_files=0, compiler_error_count=0,
                  compiler_warning_files=0, compiler_warning_count=0)
    view = _render_analysis_status(status)
    assert '컴파일 오류 0개 파일/0건' in view
    assert '컴파일 경고 0개 파일/0건' in view
    assert '왜 부분 분석인가요?' not in view
    assert '선택한 범위' in view
    status['state'] = 'partial'
    status['failed_files'] = 1
    status['errors'] = [{'kind': 'worker', 'message': 'timeout <unsafe>', 'path': '/private/file'}]
    view = _render_analysis_status(status)
    assert '왜 부분 분석인가요?' in view
    assert '시간 초과' in view and '/private/file' not in view


@pytest.mark.parametrize('language', ['csharp', 'c', 'cpp'])
@pytest.mark.parametrize('state', ['complete', 'partial', 'failed'])
def test_basic_backends_share_layout_without_fabricated_compiler_counts(language, state):
    status = dict(state=state, language=language, analyzed_files=7, failed_files=1,
                  syntax_files=2, errors=[], diagnostics=[], limitations=['지원 범위'])
    view = _render_analysis_status(status)
    assert len(StatusReader(view).metrics) == 8
    for label in ('등록', '미등록', '컴파일 오류', '컴파일 경고'):
        assert f'{label} 해당 없음' in view
    assert '컴파일 오류 0개' not in view
    assert '구문 복구 2개 파일' in view
    assert '추출 7개' in view
    assert '분석 범위와 한계' in view


def test_unknown_status_does_not_claim_completion_or_zero_diagnostics():
    view = _render_analysis_status(None)
    assert '분석 상태 미확인' in view
    assert '추출 미확인' in view
    assert '분석 완료' not in view and '컴파일 오류 0' not in view


@pytest.mark.parametrize('message,expected', [
    ('The C++ Standard Library forbids macroizing the keyword "private".', '매크로'),
    ("cannot C-style cast from member pointer type 'A' to 'B'", '멤버 함수 포인터'),
    ("'missing.hpp' file not found", '헤더'),
    ("unknown type name 'EMIT'", '타입이나 이름'),
    ('unrecognized compiler issue <unsafe>', '원인을 확정'),
])
def test_native_reason_is_derived_from_diagnostics_not_game_name(message, expected):
    status = native_status()
    status['compiler_diagnostics'] = [{'severity': 'error', 'message': message,
                                       'path': 'C:/private/header.hpp'}]
    view = _render_analysis_status(status)
    assert expected in view
    assert '<unsafe>' not in view and 'C:/private' not in view


def test_warning_explanation_uses_actual_category_and_does_not_invent_errors():
    status = native_status('complete')
    status.update(compiler_error_files=0, compiler_error_count=0)
    status['compiler_diagnostics'] = [{'severity': 'warning', 'message':
        "ISO C++11 does not allow conversion from string literal to 'char *'"}]
    view = _render_analysis_status(status)
    assert '문자열' in view and '수정 가능한' in view
    assert '기록된 경고 참고' in view
    assert '기록된 경고 참고' not in _render_help_box(True, status)
    assert '왜 부분 분석인가요?' not in view


@pytest.mark.parametrize('message,expected', [
    ('The C++ Standard Library forbids macroizing the keyword "private".', '키워드 매크로 충돌'),
    ("'missing.hpp' file not found", '누락된 헤더'),
    ('unexpected diagnostic', '원인 추가 확인 필요'),
])
def test_compiler_tooltips_are_short_and_contextual_while_details_remain(message, expected):
    status = native_status()
    status['compiler_diagnostics'] = [
        {'severity': 'error', 'message': message},
        {'severity': 'warning', 'message': "conversion from string literal to 'char *'"},
    ]
    view = _render_analysis_status(status)
    metrics = StatusReader(view).metrics
    error_tip, warning_tip = [m['data-tooltip'] for m in metrics[-2:]]
    assert len(error_tip) <= 150 and len(warning_tip) <= 150
    assert expected in error_tip and '문자열 상수 변환' in warning_tip
    assert '게임의 실제 버그 개수' in error_tip
    assert '실제로 문자열을 변경하는지 확인' in view


def test_zero_compiler_diagnostics_have_short_noninvented_tooltips():
    status = native_status('complete')
    status.update(compiler_error_files=0, compiler_error_count=0,
                  compiler_warning_files=0, compiler_warning_count=0)
    metrics = StatusReader(_render_analysis_status(status)).metrics
    for metric in metrics[-2:]:
        assert len(metric['data-tooltip']) <= 150
        assert '이번 진단:' not in metric['data-tooltip']


def test_separate_title_and_optional_subtitle_are_escaped():
    metrics = MetricsResult('test', 'test', [], [], nx.DiGraph(), [])
    scoring = compute_si_static(metrics)
    view = _render_html('Example <game>', scoring, metrics, 30,
                        analysis_status=native_status(), project_subtitle='선택 범위 <3파일>')
    assert '<h1>Example &lt;game&gt;</h1>' in view
    assert '<p class="report-subtitle">선택 범위 &lt;3파일&gt;</p>' in view
    assert '<unsafe>' not in view
    assert '[data-tooltip]:focus::after' in view


def test_subtitle_is_available_through_canonical_analyze_command():
    args = _build_parser().parse_args(['analyze', 'input', '--project-subtitle', '선택 범위'])
    assert args.project_subtitle == '선택 범위'


def test_canonical_analyze_forwards_subtitle_and_uses_common_status(tmp_path):
    source = tmp_path / 'example.c'
    source.write_text('int f(void) { return 1; }', encoding='utf-8')
    out = tmp_path / 'report'
    assert main(['analyze', str(source), '--lang', 'c', '--out', str(out), '--top', '0',
                 '--project-name', 'Example <game>', '--project-subtitle', '선택한 <파일>']) == 0
    view = (out / 'index.html').read_text(encoding='utf-8')
    assert '<h1>Example &lt;game&gt;</h1>' in view
    assert '<p class="report-subtitle">선택한 &lt;파일&gt;</p>' in view
    assert '컴파일 오류 해당 없음' in view


def test_diagnostic_label_starts_a_new_tooltip_line():
    status = native_status()
    status['compiler_diagnostics'] = [
        {'severity': 'error', 'message': "'missing.hpp' file not found"},
        {'severity': 'warning', 'message': "conversion from string literal to 'char *'"},
    ]
    tips = StatusReader(_render_analysis_status(status)).metrics[-2:]
    assert all('\n이번 진단:' in tip['data-tooltip'] for tip in tips)
    metrics = MetricsResult('test', 'test', [], [], nx.DiGraph(), [])
    doc = _render_html('Example', compute_si_static(metrics), metrics, 30, analysis_status=status)
    assert 'white-space: pre-line' in doc


def test_partial_ratio_is_selected_file_metric_not_accuracy():
    status = native_status()
    original = copy.deepcopy(status)
    view = _render_analysis_status(status)
    assert '컴파일 오류 없는 파일' in view and '62.3%' in view and '43/69개' in view
    assert '정확도나 전체 게임의 분석률' in view
    assert '분석률 62.3%' not in view and '분석 성공률' not in view
    assert status == original


def test_partial_ratio_excludes_worker_failures_without_double_subtraction():
    status = native_status()
    status.update(registered_files=4, analyzed_files=3, failed_files=1,
                  compiler_error_files=1, compiler_error_count=2)
    view = _render_analysis_status(status)
    assert '50.0%' in view and '2/4개' in view


@pytest.mark.parametrize('change', [
    {'registered_files': 0}, {'registered_files': 70}, {'analyzed_files': 70},
    {'compiler_error_files': 70}, {'compiler_error_files': -1},
    {'registered_files': None}, {'registered_files': True}, {'analyzed_files': 69.5},
    {'state': 'complete'}, {'state': 'failed'},
])
def test_ineligible_states_or_counts_do_not_fabricate_percentage(change):
    status = native_status()
    status.update(change)
    # None is unavailable in the ratio helper; keep the count renderer's normal integer contract.
    from game_si.report import _render_file_coverage
    assert _render_file_coverage(status) == ''


def test_basic_partial_does_not_fabricate_compiler_ratio():
    from game_si.report import _render_file_coverage
    status = dict(state='partial', language='cpp', analyzed_files=10, failed_files=0, syntax_files=2)
    assert _render_file_coverage(status) == ''
    assert _render_file_coverage(None) == ''


@pytest.mark.parametrize('backend', ['clang', 'basic'])
def test_complete_card_preserves_scope_and_help_returns_to_original_content(backend):
    status = native_status('complete') if backend == 'clang' else dict(
        state='complete', language='csharp', analyzed_files=7, failed_files=0,
        syntax_files=0, limitations=['외부 참조 <한계>'])
    view = _render_analysis_status(status)
    assert '분석 상태 설명' not in view and '분석 범위와 한계' in view
    assert len(StatusReader(view).details) == 1
    assert all('open' not in d for d in StatusReader(view).details)
    assert '선택한 범위의 분석을 완료했습니다.' in view
    help_box = _render_help_box(backend == 'clang', status)
    assert '분석 방법과 지원 범위' not in help_box
    assert '&lt;한계&gt;' in view and '&lt;한계&gt;' not in help_box
    assert '<details class="help">' in help_box
    assert '상대적인 검토 우선순위' in help_box and '등급 의미' in help_box


@pytest.mark.parametrize('backend', ['clang', 'basic'])
def test_complete_percentage_is_selected_scope_not_whole_game_or_accuracy(backend):
    status = native_status('complete') if backend == 'clang' else dict(
        state='complete', language='csharp', analyzed_files=7, failed_files=0,
        syntax_files=0, limitations=['지원 범위'])
    if backend == 'clang':
        status.update(registered_files=3, analyzed_files=3, unregistered_files=28,
                      compiler_error_files=0, compiler_error_count=0)
    original = copy.deepcopy(status)
    view = _render_analysis_status(status)
    assert '분석 완료 · ' in view and '>100%</span>' in view
    assert '선택한 분석 대상 기준' in view and '정확도나 전체 게임의 분석률' in view
    completion = StatusReader(view).completions
    assert len(completion) == 1 and completion[0]['tabindex'] == '0'
    assert completion[0]['data-tooltip']
    if backend == 'clang':
        assert '미등록 파일은 제외' in completion[0]['data-tooltip']
        assert '선택한 구현 파일 3개 대상' in view and '미등록 28개' in view
    else:
        assert '컴파일러 진단을 수집하지' in completion[0]['data-tooltip']
        assert '컴파일 오류 해당 없음' in view
    assert status == original


@pytest.mark.parametrize('state', ['partial', 'failed', 'unknown'])
def test_noncomplete_states_do_not_show_complete_percentage(state):
    status = None if state == 'unknown' else native_status(state)
    assert 'status-completion' not in _render_analysis_status(status)
