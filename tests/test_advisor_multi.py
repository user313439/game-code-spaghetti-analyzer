"""Bounded multi-file approval and truthful progress without live AI requests."""
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from game_si.web.app import create_app
from game_si.web import assistant


@pytest.fixture
def workbench(tmp_path):
    app = create_app(tmp_path)
    manager = app.state.manager
    ident = manager.create('Multi-file verification', 'folder')['id']
    folder = manager.directory(ident)
    for i in range(6):
        (folder / 'input' / f'u{i}.c').write_text(f'int Tick{i}(void) {{ return {i}; }}\n', encoding='utf8')
    result = folder / 'result'
    result.mkdir()
    (result / 'index.html').write_text('<html><head></head><body>Verification only</body></html>')
    rows = [dict(fqn=f'unit{i}', file_path=f'u{i}.c', si=100-i, raw={'cc': 1}) for i in range(6)]
    rows.append(dict(rows[0], fqn='same_file_class'))
    (result / 'scoring.json').write_text(json.dumps({'class_scores': rows}))
    methods=[dict(file_path=f'u{i}.c',name=f'Tick{i}',fqn=f'unit{i}.Tick{i}',start_line=1,end_line=1,cc=1,loc=1) for i in range(6)]
    (result / 'metrics.json').write_text(json.dumps({'methods':methods}))
    manager.update(ident, state='complete', options={'lang': 'c', 'subdir': '.'})
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        headers = {'X-Game-SI-Token': client.get('/api/session').json()['token']}
        yield client, f'/api/jobs/{ident}/assistant', headers, folder, app.state.assistant


def wait(client, endpoint):
    for _ in range(200):
        state = client.get(endpoint).json()
        if state['state'] != 'running':
            return state
        time.sleep(.04)
    pytest.fail('Worker did not finish')


def body(action='advice', selected=None):
    return dict(action=action, service='codex', mode='cli', candidates=selected or ['unit0', 'unit1'])


def reply(edits=None, paths=None):
    paths = paths or ['u0.c', 'u1.c']
    changed = {item['path'] for item in edits or []}
    return dict(reasons=['코드 근거'], suggestions=['변경 방향'], tests=['확인할 동작'],
                uncertainty='검사 응답이며 실제 AI 결과가 아닙니다.', edits=edits or [], relationships=[],
                file_reviews=[dict(path=path, role='파일 역할입니다.', finding='구조를 확인합니다.',
                    reason='코드 근거를 검토합니다.', change='작은 변경을 제안합니다.',
                    expected_effect='검증할 기대 효과입니다.', impact='호출부를 확인합니다.',
                    decision='refactor' if path in changed else 'keep', targets=['Tick'+path[1:-2]] if path in changed else [], evidence=['Tick 함수'],
                    checks=['입출력 비교']) for path in paths])


def test_combined_request_progress_and_copy_only_apply(workbench, monkeypatch):
    client, endpoint, headers, folder, _ = workbench
    entered, release = threading.Event(), threading.Event()
    prompts = []

    def provider(service, mode, prompt, model='', api_key=''):
        prompts.append(json.loads(prompt))
        entered.set()
        assert release.wait(5)
        return reply([dict(path=f'u{i}.c', old=f'return {i};', new=f'return {i+10};') for i in range(2)]
                     if '변경안 단계' in prompt else [])

    monkeypatch.setattr(assistant, 'call_provider', provider)
    response = client.post(endpoint, headers=headers, json=body())
    assert response.status_code == 202, response.text
    assert entered.wait(3)
    running = client.get(endpoint).json()
    assert running['progress']['stage'] == 'ai'
    assert running['progress']['indeterminate'] is True
    assert running.get('estimated_seconds') is None
    release.set()
    state = wait(client, endpoint)
    assert state['state'] == 'complete', state
    assert len(prompts) == 1
    assert {s['path'] for s in prompts[0]['sources']} == {'u0.c', 'u1.c'}
    assert set(state['source_hashes']) == {'u0.c', 'u1.c'}
    assert state['progress']['step'] == state['progress']['total']
    response = client.post(endpoint, headers=headers, json=body('preview'))
    assert response.status_code == 202, response.text
    preview = wait(client, endpoint)
    assert preview['state'] == 'complete', preview
    assert len(preview['preview']['files']) == 2
    response = client.post(endpoint+'/apply', headers=headers, json={'preview_id': preview['preview_id']})
    assert response.status_code == 202
    applied = wait(client, endpoint)
    assert applied['state'] == 'complete', applied
    assert applied['progress']['stage'] == 'complete'
    assert len(applied['comparison']['before']) == 3  # two classes share the first file
    for i in range(2):
        assert f'return {i};' in (folder/'input'/f'u{i}.c').read_text()
        assert f'return {i+10};' in (folder/'revisions'/applied['revision']/'source'/f'u{i}.c').read_text()


@pytest.mark.parametrize('selection', [['unit0']*2, ['unit0', 'same_file_class'], ['missing'], [f'unit{i}' for i in range(6)]])
def test_selection_bounds_before_ai(workbench, monkeypatch, selection):
    client, endpoint, headers, _, _ = workbench
    calls = []
    monkeypatch.setattr(assistant, 'call_provider', lambda *args: calls.append(args))
    assert client.post(endpoint, headers=headers, json=body(selected=selection)).status_code in {400, 422}
    assert not calls


def test_preview_requires_same_selection_and_every_hash(workbench, monkeypatch):
    client, endpoint, headers, folder, _ = workbench
    monkeypatch.setattr(assistant, 'call_provider', lambda *args: reply())
    assert client.post(endpoint, headers=headers, json=body()).status_code == 202
    assert wait(client, endpoint)['state'] == 'complete'
    assert client.post(endpoint, headers=headers, json=body('preview', ['unit0'])).status_code == 400
    (folder/'input/u1.c').write_text('int Tick1(void) { return 99; }')
    assert client.post(endpoint, headers=headers, json=body('preview')).status_code == 400


def test_outside_edits_never_become_approvable(workbench, monkeypatch):
    client, endpoint, headers, _, _ = workbench
    monkeypatch.setattr(assistant, 'call_provider', lambda *args: reply([dict(path='u2.c', old='return 2;', new='return 42;')]))
    assert client.post(endpoint, headers=headers, json=body()).status_code == 202
    wait(client, endpoint)
    assert client.post(endpoint, headers=headers, json=body('preview')).status_code == 202
    state = wait(client, endpoint)
    assert state['state'] == 'failed'
    assert not state.get('preview_id')
    assert not state.get('revision_url')


def test_apply_checks_unchanged_context_files_too(workbench, monkeypatch):
    client, endpoint, headers, folder, _ = workbench
    monkeypatch.setattr(assistant, 'call_provider', lambda *args: reply([dict(path='u0.c', old='return 0;', new='return (0);')]))
    for action in ['advice', 'preview']:
        assert client.post(endpoint, headers=headers, json=body(action)).status_code == 202
        state = wait(client, endpoint)
        assert state['state'] == 'complete'
    assert len(state['preview']['files']) == 1
    (folder/'input/u1.c').write_text('int Changed(void) { return 9; }')
    response = client.post(endpoint+'/apply', headers=headers, json={'preview_id': state['preview_id']})
    assert response.status_code == 400
    assert not (folder/'revisions').exists()


def test_apply_compares_selected_unchanged_files_too(workbench, monkeypatch):
    client, endpoint, headers, _, _ = workbench
    monkeypatch.setattr(assistant, 'call_provider', lambda *args: reply([dict(path='u0.c', old='return 0;', new='return (0);')]))
    for action in ['advice','preview']:
        assert client.post(endpoint, headers=headers, json=body(action)).status_code == 202
        state=wait(client,endpoint)
        assert state['state']=='complete',state
    assert client.post(endpoint+'/apply',headers=headers,json={'preview_id':state['preview_id']}).status_code==202
    state=wait(client,endpoint)
    assert state['state']=='complete',state
    assert {row['file_path'] for row in state['comparison']['before']}=={'u0.c','u1.c'}
    assert {row['file_path'] for row in state['comparison']['after']}=={'u0.c','u1.c'}


def test_apply_rejects_selected_keep_file_changed_during_copy(workbench,monkeypatch):
    client,endpoint,headers,folder,_=workbench
    monkeypatch.setattr(assistant,'call_provider',lambda *args:reply([dict(path='u0.c',old='return 0;',new='return (0);')]))
    for action in ['advice','preview']:
        assert client.post(endpoint,headers=headers,json=body(action)).status_code==202
        state=wait(client,endpoint)
        assert state['state']=='complete',state
    copy2=assistant.shutil.copy2
    keep=folder/'input/u1.c'
    def racing_copy(source,target):
        if str(source)==str(keep):keep.write_text('int Tick1(void) { return 99; }\n',encoding='utf8')
        return copy2(source,target)
    monkeypatch.setattr(assistant.shutil,'copy2',racing_copy)
    assert client.post(endpoint+'/apply',headers=headers,json={'preview_id':state['preview_id']}).status_code==202
    state=wait(client,endpoint)
    assert state['state']=='failed',state
    assert '사본' in state['error'] and '변경' in state['error']
    assert not state.get('revision_url') and not state.get('download_url')


def test_combined_input_size_is_bounded_before_provider(workbench, monkeypatch):
    client, endpoint, headers, folder, _ = workbench
    for i in range(3):
        (folder/'input'/f'u{i}.c').write_text('/*'+'x'*129996+'*/')
    calls = []
    def provider(service, mode, prompt, *args):
        calls.append(prompt)
        return reply(paths=['u0.c','u1.c','u2.c'])
    monkeypatch.setattr(assistant, 'call_provider', provider)
    response = client.post(endpoint, headers=headers, json=body(selected=['unit0','unit1','unit2']))
    assert response.status_code == 202
    state = wait(client, endpoint)
    assert state['state'] == 'complete', state
    assert state['context']['mode'] == 'focused'
    assert len(calls) == 1 and len(calls[0].encode('utf8')) <= 360000


def test_timing_estimate_requires_matching_history_and_new_advice_has_no_old_context(workbench, monkeypatch):
    client, endpoint, headers, _, _ = workbench
    prompts = []
    def provider(service, mode, prompt, *args):
        prompts.append(json.loads(prompt))
        return reply()
    monkeypatch.setattr(assistant, 'call_provider', provider)
    for i in range(2):
        assert client.post(endpoint, headers=headers, json=body()).status_code == 202
        state = wait(client, endpoint)
        assert state['estimate_samples'] == i
    assert state['estimated_seconds'] is not None
    assert prompts[1]['previous_advice'] is None
    different_model = dict(body(), model='other-model')
    assert client.post(endpoint, headers=headers, json=different_model).status_code == 202
    state = wait(client, endpoint)
    assert state['estimated_seconds'] is None
