import importlib
import importlib.util
import hashlib
from pathlib import Path

import pytest
import json
import time
import subprocess
import sys
from fastapi.testclient import TestClient


def module():
    assert importlib.util.find_spec('game_si.web.assistant'), 'AI workbench backend is missing'
    return importlib.import_module('game_si.web.assistant')


def test_preview_rejects_traversal_and_ambiguous_edits(tmp_path):
    ai = module()
    (tmp_path / 'main.c').write_text('int x;\nint x;\n', encoding='utf8')
    for edit in [dict(path='../outside.c', old='x', new='y'),
                 dict(path='main.c', old='int x;', new='int y;')]:
        with pytest.raises(ValueError):
            ai.preview_changes(tmp_path, [edit])


def test_apply_creates_copy_and_rejects_stale_source(tmp_path):
    ai = module()
    source = tmp_path / 'original'
    source.mkdir()
    file = source / 'main.c'
    original = b'int main(void) { return 0; }\r\n'
    file.write_bytes(original)
    preview = ai.preview_changes(source, [dict(path='main.c', old='return 0;', new='return 1;')])
    target = tmp_path / 'revision'
    ai.apply_changes(source, target, preview)
    assert file.read_bytes() == original
    assert (target / 'main.c').read_bytes() == original.replace(b'return 0;', b'return 1;')
    assert preview['files'][0]['sha256'] == hashlib.sha256(original).hexdigest()
    file.write_text('changed independently', encoding='utf8')
    with pytest.raises(ValueError, match='변경'):
        ai.apply_changes(source, tmp_path / 'stale', preview)
    assert not (tmp_path / 'stale').exists()


def test_api_requires_explicit_key_and_cli_never_inherits_api_keys(monkeypatch):
    ai = module()
    monkeypatch.setenv('OPENAI_API_KEY', 'do-not-use')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'do-not-use')
    assert 'OPENAI_API_KEY' not in ai.cli_environment()
    assert 'ANTHROPIC_API_KEY' not in ai.cli_environment()
    with pytest.raises(ValueError, match='키'):
        ai.call_provider('openai', 'api', 'test', '', '')


def test_advice_validation_rejects_unbounded_or_empty_reply():
    ai = module()
    for data in [{}, {'reasons': [], 'suggestions': [], 'tests': []}]:
        with pytest.raises(ValueError):
            ai.validate_advice(data)
    good = dict(reasons=['CC=10'], suggestions=['분기 분리'], tests=['기존 입력 결과 비교'], uncertainty='정적 근사')
    assert ai.validate_advice(good) == good


def test_patch_size_and_nested_destination_are_bounded(tmp_path):
    ai = module()
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'main.c').write_text('int x;', encoding='utf8')
    with pytest.raises(ValueError):
        ai.preview_changes(source, [dict(path='main.c', old='int x;', new='x' * 200_000)])
    preview = ai.preview_changes(source, [dict(path='main.c', old='int x;', new='int y;')])
    with pytest.raises(ValueError):
        ai.apply_changes(source, source / 'nested', preview)
    assert not (source / 'nested').exists()


@pytest.mark.parametrize('service', ['codex', 'claude', 'gemini'])
def test_explicit_api_key_transport_without_live_call(monkeypatch, service):
    ai = module()
    reply = dict(reasons=['구조'], suggestions=['분리'], tests=['비교'], uncertainty='정적 검토', edits=[])
    payload = json.dumps(reply, ensure_ascii=False)
    envelopes = {'codex': {'output': [{'content': [{'type': 'output_text', 'text': payload}]}]},
                 'claude': {'content': [{'type': 'text', 'text': payload}]},
                 'gemini': {'candidates': [{'content': {'parts': [{'text': payload}]}}]}}
    captured = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size): return json.dumps(envelopes[service]).encode()
    def transport(request, timeout):
        captured.append(request)
        return Response()
    monkeypatch.setattr(ai.urllib.request, 'urlopen', transport)
    assert ai.call_provider(service, 'api', 'selected public source', 'test-model', 'unit-test-key') == reply
    request = captured[0]
    assert 'unit-test-key' not in request.full_url
    assert 'unit-test-key' not in request.data.decode()
    assert any('unit-test-key' in value for _, value in request.header_items())


def test_cli_timeout_stops_child_processes(tmp_path, monkeypatch):
    import psutil
    ai = module()
    monkeypatch.setattr(ai, 'CLI_TIMEOUT', 1)
    child_pid = tmp_path / 'child.pid'
    script = "import subprocess,sys,time,pathlib; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); pathlib.Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(30)"
    with pytest.raises(subprocess.TimeoutExpired):
        ai.run_cli([sys.executable, '-c', script, str(child_pid)], '', tmp_path)
    assert child_pid.exists()
    assert not psutil.pid_exists(int(child_pid.read_text()))
    assert not ai.PROCESSES


def test_official_npm_codex_installation_is_detected(tmp_path, monkeypatch):
    ai = module()
    folder = tmp_path / 'node_modules/@openai/codex'
    (folder / 'bin').mkdir(parents=True)
    (folder / 'package.json').write_text('{"bin":{"codex":"bin/codex.js"}}')
    (folder / 'bin/codex.js').write_text('// official package entrypoint fixture')
    monkeypatch.setattr(ai.shutil, 'which', lambda name: str(tmp_path / ('node.exe' if name=='node' else 'codex.cmd')))
    assert ai.executable('codex') == [str(tmp_path/'node.exe'),str(folder/'bin/codex.js')]


def test_web_advice_preview_apply_and_original_preservation(tmp_path, monkeypatch):
    ai = module()
    from game_si.web.app import create_app
    app = create_app(tmp_path)
    manager = app.state.manager
    job = manager.create('검토 게임', 'folder')
    ident = job['id']
    source = manager.directory(ident) / 'input' / 'main.c'
    source.write_text('int Tick(void) { return 0; }\n', encoding='utf8')
    result = manager.directory(ident) / 'result'
    result.mkdir()
    saved = b'<html><body>Original static report</body></html>'
    (result / 'index.html').write_bytes(saved)
    (result / 'scoring.json').write_text(json.dumps({'class_scores': [
        {'fqn': 'main.c', 'file_path': 'main.c', 'si': 100, 'raw': {'cc': 1}}]}), encoding='utf8')
    (result / 'metrics.json').write_text(json.dumps({'methods':[dict(file_path='main.c',name='Tick',fqn='main.Tick',start_line=1,end_line=1,cc=1,loc=1)]}), encoding='utf8')
    manager.update(ident, state='complete', options={'lang': 'c', 'subdir': '.'})
    def provider(service, mode, prompt, model='', api_key=''):
        return dict(reasons=['확인된 구조'], suggestions=['반환값 예시 변경'], tests=['테스트'],
                    uncertainty='기능 동등성은 별도 확인',
                    relationships=[], file_reviews=[dict(path='main.c',role='Tick 예시입니다.',
                        finding='반환값을 확인합니다.',reason='검사 응답입니다.',change='반환값 변경 예시입니다.',
                        expected_effect='실제 개선 실험이 아닙니다.',impact='호출 동작을 확인합니다.',
                        decision='refactor' if '변경안 단계' in prompt else 'keep',targets=['Tick'] if '변경안 단계' in prompt else [],
                        evidence=['Tick 함수'],checks=['반환값 확인'])],
                    edits=([dict(path='main.c', old='return 1;', new='return 2;')] if 'return 1;' in prompt
                           else [dict(path='main.c', old='return 0;', new='return 1;')]) if '변경안 단계' in prompt else [])
    monkeypatch.setattr(ai, 'call_provider', provider)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        headers = {'X-Game-SI-Token': client.get('/api/session').json()['token']}
        endpoint = f'/api/jobs/{ident}/assistant'
        old_link = client.get(f'/workspace/{ident}', follow_redirects=False)
        assert old_link.status_code == 307 and old_link.headers['location'] == f'/#/job/{ident}/diagnosis'
        assert client.post(endpoint, json={}).status_code == 403
        def run(action, candidate='main.c', **extra):
            response = client.post(endpoint, headers=headers, json=dict(action=action, service='codex', mode='cli', candidate=candidate, **extra))
            assert response.status_code == 202, response.text
            for _ in range(100):
                state = client.get(endpoint).json()
                if state['state'] != 'running':
                    break
                time.sleep(.05)
            assert state['state'] == 'complete', state
            return state
        assert run('advice')['advice']['suggestions']
        preview = run('preview')
        assert '-int Tick' in preview['preview']['files'][0]['diff']
        response = client.post(endpoint + '/apply', headers=headers, json={'preview_id': preview['preview_id']})
        assert response.status_code == 202, response.text
        for _ in range(200):
            state = client.get(endpoint).json()
            if state['state'] != 'running':
                break
            time.sleep(.05)
        assert state['state'] == 'complete', state
        assert state['revision_url']
        assert client.get(state['revision_url']).status_code == 200
        assert 'sandbox' in client.get(state['revision_url']).headers['content-security-policy']
        assert client.get(state['download_url']).status_code == 200
        assert source.read_text() == 'int Tick(void) { return 0; }\n'
        assert (result / 'index.html').read_bytes() == saved
        assert client.post(endpoint + '/apply', headers=headers, json={'preview_id': 'stale'}).status_code == 400
        revision_url = state['revision_url']
        # The next change builds on round 1: candidates now come from the re-analysed revision.
        current = client.get(endpoint + '/candidates').json()[0]['fqn']
        assert client.get(f'/api/jobs/{ident}/rounds').json()['current'] == 1
        again = run('preview', current, direct=True)
        assert not any(key in again for key in ['revision', 'revision_url', 'comparison', 'message'])
        # A failing new advice request must leave static analysis accessible and keep keys off disk.
        def failing_provider(*args, **kwargs): raise ValueError('테스트 연결 오류')
        monkeypatch.setattr(ai, 'call_provider', failing_provider)
        response = client.post(endpoint, headers=headers, json=dict(action='advice', service='codex',
            mode='api', model='test-model', api_key='test-secret-never-persist', candidate=current))
        assert response.status_code == 202
        for _ in range(100):
            state = client.get(endpoint).json()
            if state['state'] != 'running': break
            time.sleep(.02)
        assert state['state'] == 'failed'
        assert client.get(f'/results/{ident}/index.html').status_code == 200
        assert 'test-secret-never-persist' not in (manager.directory(ident) / 'assistant.json').read_text('utf8')
        manager.delete(ident)
        assert client.get(endpoint).status_code == 404
        assert client.get(revision_url).status_code == 404
