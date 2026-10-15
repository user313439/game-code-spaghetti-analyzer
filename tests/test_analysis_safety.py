"""사용자 입력·부분 분석·진단 표시 회귀 및 실제 추출 통합 검사."""
import json
import re
import os
from pathlib import Path

import pytest

from game_si.cli import main
from game_si.cpp_analyzer import analyze_cpp


def source(tmp_path, name='good.c', text='int Tick(void) { return 0; }'):
    path = tmp_path / name
    path.write_text(text, encoding='utf-8')
    return path


@pytest.mark.parametrize('lang', ['auto', 'c', 'cpp', 'csharp'])
def test_unsupported_file_is_rejected_before_outputs(tmp_path, capsys, lang):
    path = source(tmp_path, 'game.py', 'print("hello")')
    out = tmp_path / 'result'
    assert main(['analyze', str(path), '--lang', lang, '--out', str(out)]) == 1
    assert '지원' in capsys.readouterr().err
    assert not out.exists()


def test_empty_directory_is_rejected_before_outputs(tmp_path, capsys):
    folder = tmp_path / 'empty'
    folder.mkdir()
    out = tmp_path / 'result'
    assert main(['analyze', str(folder), '--out', str(out)]) == 1
    assert '소스' in capsys.readouterr().err
    assert not out.exists()


@pytest.mark.parametrize('text', ['', '   \n\n', '/* 주석만 존재 */', '/* first */ /* second */'])
def test_blank_cpp_file_does_not_get_a_score(tmp_path, text):
    path = source(tmp_path, text=text)
    out = tmp_path / 'result'
    assert main(['analyze', str(path), '--lang', 'c', '--out', str(out)]) == 1
    assert not (out / 'scoring.json').exists()
    assert not (out / 'index.html').exists()


def test_cpp_syntax_recovery_is_reported_without_discarding_files(tmp_path):
    source(tmp_path, 'broken.c', 'int Tick(void) { return missing + ; }')
    result = analyze_cpp(tmp_path)
    assert result.data['summary']['total_files'] == 1
    assert result.data.get('diagnostics')
    assert result.data['diagnostics'][0]['kind'] == 'syntax'
    assert result.data['diagnostics'][0]['line'] == 1
    assert result.errors == []


def test_cli_partial_syntax_analysis_marks_json_and_html(tmp_path, capsys):
    path = source(tmp_path, 'broken.c', 'int Tick(void) { return missing + ; }')
    out = tmp_path / 'result'
    assert main(['analyze', str(path), '--lang', 'c', '--out', str(out), '--top', '0']) == 3
    status = json.loads((out / 'analysis_status.json').read_text(encoding='utf-8'))
    assert status['state'] == 'partial'
    assert status['syntax_files'] == 1
    assert json.loads((out / 'scoring.json').read_text(encoding='utf-8'))['analysis_status'] == status
    view = (out / 'index.html').read_text(encoding='utf-8')
    assert '부분 분석' in view and 'broken.c' in view
    assert '부분 분석' in capsys.readouterr().err


def test_file_read_failure_preserves_other_results(tmp_path, monkeypatch, capsys):
    source(tmp_path)
    source(tmp_path, 'blocked.c')
    original = Path.read_bytes
    def read(path):
        if path.name == 'blocked.c':
            raise PermissionError('접근 거부 <script>bad</script>')
        return original(path)
    monkeypatch.setattr(Path, 'read_bytes', read)
    out = tmp_path / 'result'
    assert main(['analyze', str(tmp_path), '--lang', 'c', '--out', str(out), '--top', '0']) == 3
    status = json.loads((out / 'analysis_status.json').read_text(encoding='utf-8'))
    assert status['analyzed_files'] == 1 and status['failed_files'] == 1
    assert 'blocked.c' in capsys.readouterr().err
    view = (out / 'index.html').read_text(encoding='utf-8')
    assert '접근 거부 <script>bad</script>' in status['errors'][0]['message']
    assert '접근·추출 실패 1개' in view
    assert '<script>bad</script>' not in view


def test_all_file_failures_do_not_create_score_or_dashboard(tmp_path, monkeypatch, capsys):
    source(tmp_path)
    def blocked(path):
        raise PermissionError('접근 거부')
    monkeypatch.setattr(Path, 'read_bytes', blocked)
    out = tmp_path / 'result'
    assert main(['analyze', str(tmp_path), '--lang', 'c', '--out', str(out)]) == 1
    assert not (out / 'scoring.json').exists()
    assert not (out / 'index.html').exists()
    assert (out / 'analysis_status.json').exists()
    assert '분석' in capsys.readouterr().err


def test_directory_permission_failure_is_partial_not_silently_ignored(tmp_path, monkeypatch):
    source(tmp_path)
    blocked = tmp_path / 'blocked'
    blocked.mkdir()
    source(blocked)
    original = os.scandir
    def scandir(path):
        if Path(path) == blocked:
            raise PermissionError(13, '접근 거부', str(blocked))
        return original(path)
    monkeypatch.setattr(os, 'scandir', scandir)
    accessor = getattr(Path(), '_accessor', None)
    if accessor is not None:
        monkeypatch.setattr(accessor, 'scandir', scandir)
    out = tmp_path / 'result'
    assert main(['analyze', str(tmp_path), '--lang', 'c', '--out', str(out), '--top', '0']) == 3
    status = json.loads((out / 'analysis_status.json').read_text(encoding='utf-8'))
    assert status['failed_files'] == 1
    assert status['errors'][0]['path'] == 'blocked'


@pytest.mark.parametrize('text, expected', [('int Tick(void) { return 0; }', 0),
                                          ('int Tick(void) { return missing + ; }', 3)])
def test_full_analysis_preserves_diagnostics(tmp_path, monkeypatch, text, expected):
    monkeypatch.setattr('game_si.change_risk.compute_change_risk', lambda **kwargs: {})
    path = source(tmp_path, text=text)
    out = tmp_path / 'result'
    assert main(['score-full', str(path), '--lang', 'c', '--repo', str(tmp_path), '--out', str(out)]) == expected
    assert (out / 'analysis_status_full.json').exists()
    status = json.loads((out / 'analysis_status_full.json').read_text(encoding='utf-8'))
    assert status['state'] == ('partial' if expected == 3 else 'complete')
    assert json.loads((out / 'scoring_full.json').read_text(encoding='utf-8'))['analysis_status'] == status


def test_normal_analysis_has_explicit_limits_and_collapsed_help(tmp_path):
    path = source(tmp_path)
    out = tmp_path / 'result'
    assert main(['analyze', str(path), '--lang', 'c', '--out', str(out), '--top', '0']) == 0
    assert (out / 'analysis_status.json').exists()
    status = json.loads((out / 'analysis_status.json').read_text(encoding='utf-8'))
    assert status['state'] == 'complete' and status['limitations']
    view = (out / 'index.html').read_text(encoding='utf-8')
    assert '<summary>대시보드 읽는 법</summary>' in view
    assert '<details class="help" open>' not in view
    assert '분석 범위와 한계' in view


def test_output_path_failure_is_explained_without_traceback(tmp_path, capsys):
    path = source(tmp_path)
    out = source(tmp_path, 'output.txt', '사용자 파일')
    assert main(['analyze', str(path), '--lang', 'c', '--out', str(out)]) == 1
    assert '[error]' in capsys.readouterr().err
    assert out.read_text(encoding='utf-8') == '사용자 파일'


def test_output_failure_does_not_leave_a_complete_status(tmp_path, monkeypatch, capsys):
    path = source(tmp_path)
    original = Path.write_text
    def write(target, *args, **kwargs):
        if target.name == 'scoring.json':
            raise OSError('결과 저장 실패')
        return original(target, *args, **kwargs)
    monkeypatch.setattr(Path, 'write_text', write)
    out = tmp_path / 'result'
    assert main(['analyze', str(path), '--lang', 'c', '--out', str(out)]) == 1
    status = json.loads((out / 'analysis_status.json').read_text(encoding='utf-8'))
    assert status['state'] == 'failed'
    assert '결과 저장 실패' in capsys.readouterr().err


def test_full_analysis_rejects_unsupported_input_before_git_history(tmp_path, capsys):
    path = source(tmp_path, 'game.py', 'print("hello")')
    out = tmp_path / 'result'
    assert main(['score-full', str(path), '--repo', str(tmp_path), '--out', str(out)]) == 1
    assert '지원' in capsys.readouterr().err
    assert not out.exists()


def test_dashboard_save_failure_also_marks_saved_scoring_failed(tmp_path, monkeypatch):
    path = source(tmp_path)
    original = Path.write_text
    def write(target, *args, **kwargs):
        if target.name == 'index.html':
            raise OSError('대시보드 저장 실패')
        return original(target, *args, **kwargs)
    monkeypatch.setattr(Path, 'write_text', write)
    out = tmp_path / 'result'
    assert main(['analyze', str(path), '--lang', 'c', '--out', str(out)]) == 1
    saved = json.loads((out / 'scoring.json').read_text(encoding='utf-8'))
    assert saved['analysis_status']['state'] == 'failed'


def test_process_failure_marks_old_output_as_not_latest(tmp_path, monkeypatch, capsys):
    from game_si.analyzer import AnalyzerExecutionError
    path = source(tmp_path)
    out = tmp_path / 'result'
    assert main(['analyze', str(path), '--lang', 'c', '--out', str(out)]) == 0
    def fail(*args):
        raise AnalyzerExecutionError('추출 프로세스 실행 실패')
    monkeypatch.setattr('game_si.cli._run_cpp', fail)
    assert main(['analyze', str(path), '--lang', 'c', '--out', str(out)]) == 1
    status = json.loads((out / 'analysis_status.json').read_text(encoding='utf-8'))
    assert status['state'] == 'failed'
    view = (out / 'index.html').read_text(encoding='utf-8')
    assert '이전 결과' in view and '최신 실행' in view
    assert '기존 결과' in capsys.readouterr().err


def test_csharp_syntax_recovery_is_reported(tmp_path):
    from game_si.analyzer import analyze
    path = source(tmp_path, 'broken.cs', 'class Broken { int Tick() { return missing + ; } }')
    result = analyze(path)
    assert result.files
    assert result.data.get('diagnostics')
    assert result.data['diagnostics'][0]['kind'] == 'syntax'
    assert result.data['diagnostics'][0]['line'] == 1


def test_csharp_missing_external_reference_is_not_mislabeled_as_syntax_error(tmp_path):
    from game_si.analyzer import analyze
    path = source(tmp_path, 'external.cs', 'class Game : Engine.MissingBase { void Tick() { Engine.Api.Update(); } }')
    result = analyze(path)
    assert result.files and not result.errors
    assert not result.data.get('diagnostics')


def test_csharp_code_after_inline_license_comment_is_not_empty(tmp_path):
    path = source(tmp_path, 'valid.cs', '/* license */ class Loop { void Tick() {} }')
    out = tmp_path / 'result'
    assert main(['analyze', str(path), '--lang', 'csharp', '--out', str(out)]) == 0
    assert (out / 'scoring.json').exists()


def test_landing_intro_is_structured_without_raw_development_links():
    root = Path(__file__).resolve().parents[1]
    view = (root / 'reports/index.html').read_text(encoding='utf-8')
    header_css = re.search(r'header\s*\{([^}]+)', view).group(1)
    assert 'text-align: center' in header_css
    intro = view.split('<main>', 1)[1].split('</section>', 1)[0]
    assert '프로젝트 소개' in intro
    assert '.md' not in intro and '.json' not in intro
    assert '본 도구를' not in intro
