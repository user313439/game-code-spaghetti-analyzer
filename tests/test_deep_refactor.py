"""One click, several files in depth: one AI call per file (several at once), checked per file,
merged into one change; a rejected file can be redone and added to the same change."""
import json
import threading
import time

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('tree_sitter_c')
from fastapi.testclient import TestClient

from game_si.web import assistant, assistant_context
from game_si.web.app import create_app

BODY = {
    'a.c': 'static int total;\n\nint Alpha(int x)\n{\n\tif (x > 0) {\n\t\ttotal += x;\n\t}\n\tif (x > 10) {\n\t\ttotal += 1;\n\t}\n\treturn total;\n}\n',
    'b.c': 'static int count;\n\nint Beta(int y)\n{\n\tif (y < 0) {\n\t\tcount -= y;\n\t}\n\tif (y < -10) {\n\t\tcount -= 1;\n\t}\n\treturn count;\n}\n',
}
NAMES = {'a.c': ('Alpha', 'x', 'total', 'add_alpha'), 'b.c': ('Beta', 'y', 'count', 'add_beta')}


def reply(path, outside=False):
    function, arg, var, helper = NAMES[path]
    text = BODY[path]
    start = text.index('\tif (')
    block = text[start:text.index('\treturn')]
    helper_code = f'static void {helper}(int {arg})\n{{\n' + block + '}\n\n'
    review = dict(path=path, role='역할입니다.', finding='두 조건 블록이 함수에 몰려 있습니다.', reason='조건 처리를 나눕니다.',
                  change=f'조건 블록을 정적 보조 함수 {helper}로 옮깁니다.', expected_effect='함수가 짧아집니다.', impact='없습니다.',
                  decision='refactor', change_type='functions', targets=[function], evidence=[f'새 정적 보조 함수 {helper}'],
                  checks=['반환값이 같은지 확인합니다.'])
    edits = [dict(path='a.c' if outside else path, old=block, new=f'\t{helper}({arg});\n'),
             dict(path=path, old=f'int {function}(int {arg})\n{{', new=helper_code + f'int {function}(int {arg})\n{{')]
    return dict(overview=dict(title='정리합니다.', problem=f'{path}의 문제입니다.', reason='이유입니다.', change='바꿉니다.', expected_effect='좋아집니다.'),
                reasons=['근거입니다.'], suggestions=['방향입니다.'], tests=['확인합니다.'], uncertainty='', relationships=[f'{path} 관계입니다.'],
                file_reviews=[review], companions=[], creates=[], edits=edits)


def make_job(tmp_path):
    app = create_app(tmp_path)
    manager = app.state.manager
    ident = manager.create('깊게 정리', 'folder')['id']
    for name, text in BODY.items():
        (manager.directory(ident) / 'input' / name).write_text(text, encoding='utf8')
    result = manager.directory(ident) / 'result'
    result.mkdir()
    raw = {'cc': 3, 'coupling': 0, 'dependency_cycle': 0, 'global_state': 2, 'game_loop_centrality': 0}
    units = [{'fqn': n[0], 'name': n[0], 'file_path': f'{n[0]}.c', 'si': 100 - i, 'grade': 'E', 'loc': 13, 'raw': raw}
             for i, n in enumerate(['a', 'b'])]
    (result / 'scoring.json').write_text(json.dumps({'class_scores': units, 'analysis_status': {'state': 'complete', 'language': 'c'}}), encoding='utf8')
    (result / 'metrics.json').write_text(json.dumps({
        'classes': [{'fqn': u['fqn'], 'name': u['name'], 'file_path': u['file_path'], 'out_neighbors': [], 'in_neighbors': []} for u in units],
        'methods': [dict(file_path=f'{c}.c', class_fqn=c, name=NAMES[f'{c}.c'][0], fqn=f'{c}.{NAMES[f"{c}.c"][0]}', start_line=3, end_line=13, cc=12, loc=11)
                    for c in ['a', 'b']]}), encoding='utf8')
    manager.update(ident, state='complete', options={'lang': 'c', 'subdir': '.'})
    return app, ident


def wait(client, url):
    for _ in range(600):
        state = client.get(url).json()
        if state['state'] != 'running':
            return state
        time.sleep(0.05)
    raise AssertionError('task did not finish')


def test_files_are_done_at_once_each_alone_and_merged_into_one_change(tmp_path, monkeypatch):
    seen, both = [], threading.Barrier(2, timeout=10)

    def provider(service, mode, prompt, model='', api_key='', **kw):
        payload = json.loads(prompt)
        seen.append((payload['mode'], payload['editable_paths'], kw.get('timeout'), '[깊게 정리 모드]' in kw.get('guidance', '')))
        both.wait()   # both files are with the AI at the same time
        return reply(payload['editable_paths'][0])
    monkeypatch.setattr(assistant, 'call_provider', provider)
    app, ident = make_job(tmp_path)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        h = {'X-Game-SI-Token': client.get('/api/session').json()['token']}
        url = f'/api/jobs/{ident}/assistant'
        started = client.post(url, headers=h, json=dict(action='preview', strategy='deep', service='claude', mode='cli', candidates=['a', 'b'], direct=True))
        assert started.status_code == 202 and [w['state'] for w in started.json()['workers']] == ['waiting', 'waiting']
        state = wait(client, url)
        assert state['state'] == 'complete', state.get('error')
        assert sorted(s[1][0] for s in seen) == ['a.c', 'b.c']
        assert all(mode == 'deep' and timeout == assistant.DEEP_TIMEOUT and deep for mode, _, timeout, deep in seen)
        assert sorted(f['path'] for f in state['preview']['files']) == ['a.c', 'b.c']
        assert {w['state'] for w in state['workers']} == {'done'} and state['preview_failures'] == []
        assert all(w['mode'] == 'full' and w['targets'] and w['helpers'] for w in state['workers'])
        lines = state['change_advice']['overview']['problem'].split('\n')
        assert lines == ['[a.c] a.c의 문제입니다.', '[b.c] b.c의 문제입니다.']
        assert [r['path'] for r in state['change_advice']['file_reviews']] == ['a.c', 'b.c']
        assert client.post(url + '/apply', headers=h, json={'preview_id': state['preview_id']}).status_code == 202
        applied = wait(client, url)
        assert applied['state'] == 'complete', applied.get('error')
        copy = app.state.manager.directory(ident) / 'revisions' / applied['revision'] / 'source'
        assert 'add_alpha(x);' in (copy / 'a.c').read_text('utf8') and 'add_beta(y);' in (copy / 'b.c').read_text('utf8')
        # The result page shows each changed function's code before and after.
        changes = client.get(f'/api/jobs/{ident}/rounds/1/changes').json()['functions']
        by = {(c['file'], c['name']): c for c in changes}
        assert set(by) == {('a.c', 'Alpha'), ('a.c', 'add_alpha'), ('b.c', 'Beta'), ('b.c', 'add_beta')}
        alpha = by[('a.c', 'Alpha')]
        assert not alpha['created'] and '-\tif (x > 0) {' in alpha['diff'] and '+\tadd_alpha(x);' in alpha['diff']
        assert by[('a.c', 'add_alpha')]['created'] and by[('a.c', 'add_alpha')]['diff'].count('\n+') >= 5
        assert [c['created'] for c in changes] == [False, False, True, True]   # changed functions first, new ones after
        assert client.get(f'/api/jobs/{ident}/rounds/9/changes').status_code == 404


def test_a_rejected_file_leaves_the_others_and_can_be_redone_into_the_same_change(tmp_path, monkeypatch):
    bad = {'b.c'}

    def provider(service, mode, prompt, model='', api_key='', **kw):
        path = json.loads(prompt)['editable_paths'][0]
        return reply(path, outside=path in bad)   # b.c's first reply also edits a.c: rejected
    monkeypatch.setattr(assistant, 'call_provider', provider)
    app, ident = make_job(tmp_path)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        h = {'X-Game-SI-Token': client.get('/api/session').json()['token']}
        url = f'/api/jobs/{ident}/assistant'
        body = dict(action='preview', strategy='deep', service='claude', mode='cli', candidates=['a', 'b'], direct=True)
        assert client.post(url, headers=h, json=body).status_code == 202
        state = wait(client, url)
        assert state['state'] == 'complete' and [f['path'] for f in state['preview']['files']] == ['a.c']
        failed = {w['path']: w for w in state['workers']}['b.c']
        assert failed['state'] == 'failed' and '밖의' in failed['error']
        assert [f['path'] for f in state['preview_failures']] == ['b.c']
        assert (app.state.manager.directory(ident) / 'assistant-rejected-b.c.json').is_file()
        # Redo only b.c and add it to the same change.
        bad.clear()
        retry = dict(body, candidates=['b'], retry_of=state['preview_id'])
        assert client.post(url, headers=h, json=retry).status_code == 202
        redone = wait(client, url)
        assert redone['state'] == 'complete', redone.get('error')
        assert sorted(f['path'] for f in redone['preview']['files']) == ['a.c', 'b.c'] and redone['preview_id'] != state['preview_id']
        assert {w['path']: w['state'] for w in redone['workers']} == {'a.c': 'done', 'b.c': 'done'} and redone['preview_failures'] == []
        again = {w['path']: w for w in redone['workers']}['b.c']
        assert again['attempt'] == 2 and '밖의' in again['last_error']   # the try count and last reason carry over
        assert redone['change_advice']['overview']['problem'].split('\n') == ['[a.c] a.c의 문제입니다.', '[b.c] b.c의 문제입니다.']
        assert state['change_advice']['overview']['title'].startswith('1개 파일') and redone['change_advice']['overview']['title'].startswith('2개 파일')
        assert redone['candidates'] == ['a', 'b'] and set(redone['source_hashes']) == {'a.c', 'b.c'}
        # A stale preview id cannot be redone.
        assert client.post(url, headers=h, json=dict(retry, retry_of=state['preview_id'])).status_code == 400


def test_a_retry_is_refused_when_a_kept_file_changed_since(tmp_path, monkeypatch):
    monkeypatch.setattr(assistant, 'call_provider', lambda s, m, prompt, *a, **kw: reply(json.loads(prompt)['editable_paths'][0],
                                                                                         outside=json.loads(prompt)['editable_paths'][0] == 'b.c'))
    app, ident = make_job(tmp_path)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        h = {'X-Game-SI-Token': client.get('/api/session').json()['token']}
        url = f'/api/jobs/{ident}/assistant'
        body = dict(action='preview', strategy='deep', service='claude', mode='cli', candidates=['a', 'b'], direct=True)
        client.post(url, headers=h, json=body)
        state = wait(client, url)
        assert [f['path'] for f in state['preview']['files']] == ['a.c']
        (app.state.manager.directory(ident) / 'input' / 'a.c').write_text(BODY['a.c'] + '\n/* edited */\n', encoding='utf8')
        refused = client.post(url, headers=h, json=dict(body, candidates=['b'], retry_of=state['preview_id']))
        assert refused.status_code == 400 and '원본 코드가 바뀌어' in refused.json()['detail']


def test_every_file_rejected_is_a_failure_with_each_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(assistant, 'call_provider', lambda *a, **kw: (_ for _ in ()).throw(ValueError('AI 요청이 완료되지 않았습니다.')))
    app, ident = make_job(tmp_path)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        h = {'X-Game-SI-Token': client.get('/api/session').json()['token']}
        url = f'/api/jobs/{ident}/assistant'
        assert client.post(url, headers=h, json=dict(action='preview', strategy='deep', service='claude', mode='cli',
                                                     candidates=['a', 'b'], direct=True)).status_code == 202
        state = wait(client, url)
        assert state['state'] == 'failed' and 'a.c: AI 요청이 완료되지 않았습니다.' in state['error'] and 'b.c' in state['error']
        assert 'preview' not in state


def test_a_timeout_says_what_to_do_and_a_reply_failing_its_check_is_kept(tmp_path, monkeypatch):
    import subprocess

    def provider(service, mode, prompt, *a, **kw):
        path = json.loads(prompt)['editable_paths'][0]
        if path == 'a.c':
            raise ValueError('AI 응답 제한 시간을 초과했습니다.') from subprocess.TimeoutExpired('claude', 900)
        error = ValueError('AI 변경 요약을 확인하지 못했습니다.')
        error.reply = reply(path)
        raise error
    monkeypatch.setattr(assistant, 'call_provider', provider)
    app, ident = make_job(tmp_path)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        h = {'X-Game-SI-Token': client.get('/api/session').json()['token']}
        url = f'/api/jobs/{ident}/assistant'
        client.post(url, headers=h, json=dict(action='preview', strategy='deep', service='claude', mode='cli', candidates=['a', 'b'], direct=True))
        workers = {w['path']: w for w in wait(client, url)['workers']}
    assert '분 안에 답하지 못했습니다' in workers['a.c']['error'] and '원본은 그대로' in workers['a.c']['error']
    saved = json.loads((app.state.manager.directory(ident) / 'assistant-rejected-b.c.json').read_text('utf8'))
    assert saved['error'] == 'AI 변경 요약을 확인하지 못했습니다.' and saved['reply']['edits']


def pass_reply(block, helper, other_path=None):
    """A reply moving one `if` block of Alpha into a new helper (as a later pass would)."""
    data = reply('a.c')
    data['file_reviews'][0].update(change=f'남은 조건 블록을 정적 보조 함수 {helper}로 옮깁니다.', evidence=[f'새 정적 보조 함수 {helper}'])
    data['edits'] = [dict(path=other_path or 'a.c', old=block, new=f'\t{helper}(x);\n'),
                     dict(path='a.c', old='int Alpha(int x)\n{', new=f'static void {helper}(int x)\n{{\n{block}}}\n\nint Alpha(int x)\n{{')]
    return data


def run_passes(tmp_path, monkeypatch, second, passes=2):
    from game_si.web import assistant_jobs
    monkeypatch.setattr(assistant_jobs, 'DEEP_PASSES', passes)
    monkeypatch.setattr(assistant_jobs, 'DEEP_CONTINUE_CC', 1)
    monkeypatch.setattr(assistant_jobs, 'DEEP_MIN_GAIN', 0)
    asked = []

    def provider(service, mode, prompt, *a, **kw):
        payload = json.loads(prompt)
        asked.append((payload.get('continuation'), kw.get('max_output')))
        if payload.get('continuation'):
            assert 'add_first(x);' in payload['sources'][0]['content']   # the text the first pass left
            return second
        return pass_reply('\tif (x > 0) {\n\t\ttotal += x;\n\t}\n', 'add_first')
    monkeypatch.setattr(assistant, 'call_provider', provider)
    app, ident = make_job(tmp_path)
    client = TestClient(app, base_url='http://127.0.0.1:8765')
    h = {'X-Game-SI-Token': client.get('/api/session').json()['token']}
    url = f'/api/jobs/{ident}/assistant'
    client.post(url, headers=h, json=dict(action='preview', strategy='deep', service='claude', mode='cli', candidates=['a'], direct=True))
    return app, ident, client, h, url, wait(client, url), asked


def test_a_file_is_handed_on_for_a_second_pass_and_checked_as_one_change(tmp_path, monkeypatch):
    second = pass_reply('\tif (x > 10) {\n\t\ttotal += 1;\n\t}\n', 'add_second')
    app, ident, client, h, url, state, asked = run_passes(tmp_path, monkeypatch, second)
    with client:
        assert state['state'] == 'complete', state.get('error')
        assert [c['pass'] if c else 1 for c, _ in asked] == [1, 2] and asked[1][0]['helpers'] == ['add_first']
        assert all(cap == assistant.DEEP_OUTPUT_TOKENS for _, cap in asked)
        worker = state['workers'][0]
        assert worker['state'] == 'done' and worker['steps_done'] == 2 and '2번' in worker['note']
        assert worker['helpers'] == ['add_first', 'add_second']
        after = state['preview']['files'][0]['after'].replace('\r\n', '\n')
        assert '\tadd_first(x);\n\tadd_second(x);\n\treturn total;' in after and after.count('if (x >') == 2   # each block once, in its helper
        assert client.post(url + '/apply', headers=h, json={'preview_id': state['preview_id']}).status_code == 202
        assert wait(client, url)['state'] == 'complete'


def test_a_pass_that_took_little_away_ends_the_passes(tmp_path, monkeypatch):
    # The gain that decides another pass is the last pass's own, not the total since the original.
    from game_si.web import assistant_jobs
    second = pass_reply('\tif (x > 10) {\n\t\ttotal += 1;\n\t}\n', 'add_second')
    real = assistant_jobs.measure_functions
    monkeypatch.setattr(assistant_jobs, 'measure_functions', lambda path, text: [
        dict(m, cc=100 if 'add_first' not in text else 80) for m in real(path, text)])   # pass 1: 100 -> 80, pass 2: 80 -> 80
    app, ident, client, h, url, state, asked = run_passes(tmp_path, monkeypatch, second, passes=3)
    with client:
        assert state['state'] == 'complete' and state['workers'][0]['steps_done'] == 2
        assert len(asked) == 2   # no third request after a pass that gained nothing


def test_a_rejected_later_pass_keeps_the_first_pass(tmp_path, monkeypatch):
    second = pass_reply('\tif (x > 10) {\n\t\ttotal += 1;\n\t}\n', 'add_second', other_path='b.c')   # edits another file
    app, ident, client, h, url, state, asked = run_passes(tmp_path, monkeypatch, second)
    with client:
        worker = state['workers'][0]
        assert state['state'] == 'complete' and worker['state'] == 'done' and worker['steps_done'] == 1
        assert '2단계' in worker['note'] and '밖의' in worker['note_detail'] and worker['helpers'] == ['add_first']
        after = state['preview']['files'][0]['after']
        assert 'add_first(x);' in after and 'add_second' not in after
        assert (app.state.manager.directory(ident) / 'assistant-rejected-a.c-pass2.json').is_file()


def test_a_helper_put_after_another_function_is_not_taken_for_a_change_to_it(tmp_path):
    # Real case (rehearsal 2026-10-26): the diff lined the new helper's '}' and blank line up with the
    # previous function's, so the insertion looked like a change inside that function.
    # The target's lines before the moved block are what the diff prefers to line up.
    body = ('int Alpha(int x)\n{\n\tint a = 1;\n\tint b = 2;\n\tint c = 3;\n\ttotal += a + b + c;\n'
            '\tif (x > 0) {\n\t\ttotal += x;\n\t}\n\tif (x > 10) {\n\t\ttotal += 1;\n\t}\n\treturn total;\n}\n')
    (tmp_path / 'a.c').write_text('static int total;\n\nint Prev(void)\n{\n\treturn total;\n}\n\n' + body, encoding='utf8', newline='')
    block = body[body.index('\tif ('):body.index('\treturn')]
    data = reply('a.c')
    data['edits'] = [dict(path='a.c', old=block, new='\tadd_alpha(x);\n'),
                     dict(path='a.c', old='int Alpha(int x)\n{', new='static void add_alpha(int x)\n{\n' + block + '}\n\nint Alpha(int x)\n{')]
    methods = [dict(file_path='a.c', name='Prev', fqn='a.Prev', start_line=3, end_line=6, cc=1, loc=4),
               dict(file_path='a.c', name='Alpha', fqn='a.Alpha', start_line=8, end_line=21, cc=3, loc=14)]
    preview = assistant.preview_changes(tmp_path, data['edits'])
    assistant_context.validate_preview_targets(data, methods, preview)
    assert preview['files'][0]['added_helpers'] == ['add_alpha']
    data['file_reviews'][0]['targets'] = ['Prev']   # a change really inside another function is still refused
    with pytest.raises(ValueError):
        assistant_context.validate_preview_targets(data, methods, assistant.preview_changes(tmp_path, data['edits']))


def test_a_helper_put_after_an_earlier_passes_helper_is_lined_up_whole(tmp_path):
    # Real case (rehearsal 2026-10-26, tyrian2.c pass 3): the function before the insertion was a helper of
    # an earlier pass, so it has no measured lines, and the diff took its closing '}' lines into the insertion.
    # The target's long unchanged head is what the diff lines up first.
    head = ''.join(f'\tint v{n} = {n};\n' for n in range(12))
    body = (f'int Alpha(int x)\n{{\n{head}\tif (x > 0) {{\n\t\tif (x > 5) {{\n\t\t\ttotal += x;\n\t\t}}\n\t}}\n'
            '\treturn total;\n}\n')
    prev = 'static void add_first(int x)\n{\n\tif (x > 1) {\n\t\tif (x > 2) {\n\t\t\ttotal += 2;\n\t\t}\n\t}\n}\n\n'
    (tmp_path / 'a.c').write_text('static int total;\n\n' + prev + body, encoding='utf8', newline='')
    block = body[body.index('\tif ('):body.index('\treturn')]
    data = reply('a.c')
    data['edits'] = [dict(path='a.c', old=block, new='\tadd_alpha(x);\n'),
                     dict(path='a.c', old='int Alpha(int x)\n{', new='static void add_alpha(int x)\n{\n' + block + '}\n\nint Alpha(int x)\n{')]
    methods = [dict(file_path='a.c', name='Alpha', fqn='a.Alpha', start_line=12, end_line=32, cc=3, loc=21)]
    preview = assistant.preview_changes(tmp_path, data['edits'])
    assistant_context.validate_preview_targets(data, methods, preview)
    assert preview['files'][0]['added_helpers'] == ['add_alpha']


def test_a_helper_called_through_another_new_helper_is_accepted(tmp_path):
    # Real case (rehearsal 2026-10-26, pass 3): a later pass moved the call of an earlier pass's helper
    # into a new helper, so the target reaches it only through that helper.
    (tmp_path / 'a.c').write_text(BODY['a.c'], encoding='utf8', newline='')
    text = BODY['a.c']
    block = text[text.index('\tif ('):text.index('\treturn')]
    first, second = block[:block.index('\tif (x > 10)')], block[block.index('\tif (x > 10)'):]
    helpers = (f'static void add_inner(int x)\n{{\n{first}}}\n\n'
               f'static void add_alpha(int x)\n{{\n\tadd_inner(x);\n{second}}}\n\n')
    data = reply('a.c')
    data['file_reviews'][0].update(change='조건 블록을 add_alpha로 옮기고 첫 블록은 add_inner로 나눕니다.')
    data['edits'] = [dict(path='a.c', old=block, new='\tadd_alpha(x);\n'),
                     dict(path='a.c', old='int Alpha(int x)\n{', new=helpers + 'int Alpha(int x)\n{')]
    methods = [dict(file_path='a.c', name='Alpha', fqn='a.Alpha', start_line=3, end_line=13, cc=3, loc=11)]
    preview = assistant.preview_changes(tmp_path, data['edits'])
    assistant_context.validate_preview_targets(data, methods, preview)
    assert sorted(preview['files'][0]['added_helpers']) == ['add_alpha', 'add_inner']
    data['edits'][1]['new'] = helpers + 'static void unused_helper(int x)\n{\n\ttotal = x;\n}\n\nint Alpha(int x)\n{'
    data['file_reviews'][0]['change'] += ' unused_helper도 둡니다.'
    with pytest.raises(ValueError):   # a helper nothing reaches is still refused
        assistant_context.validate_preview_targets(data, methods, assistant.preview_changes(tmp_path, data['edits']))


def test_a_helper_with_an_if_split_by_preprocessor_lines_is_accepted(tmp_path):
    # Real case (rehearsal 2026-10-26, tyrian2.c): '#ifdef NDEBUG / if (a) / #else / if (b) / #endif {'
    # is valid C that tree-sitter cannot read, so the moved block looked broken.
    block = '#ifdef NDEBUG\n\tif (x > 0 || total)\n#else\n\tif (x > 0)\n#endif\n\t{\n\t\ttotal += x;\n\t}\n'
    (tmp_path / 'a.c').write_text(f'static int total;\n\nint Alpha(int x)\n{{\n{block}\treturn total;\n}}\n', encoding='utf8', newline='')
    data = reply('a.c')
    data['edits'] = [dict(path='a.c', old=block, new='\tadd_alpha(x);\n'),
                     dict(path='a.c', old='int Alpha(int x)\n{', new=f'static void add_alpha(int x)\n{{\n{block}}}\n\nint Alpha(int x)\n{{')]
    methods = [dict(file_path='a.c', name='Alpha', fqn='a.Alpha', start_line=3, end_line=14, cc=3, loc=12)]
    preview = assistant.preview_changes(tmp_path, data['edits'])
    assistant_context.validate_preview_targets(data, methods, preview)
    assert preview['files'][0]['added_helpers'] == ['add_alpha']
    helper = data['edits'][1]['new'].split('\n\nint Alpha')[0]
    assert assistant_context._readable('a.c', helper) is not None
    assert assistant_context._readable('a.c', helper.replace('total += x;', 'total += x')) is None   # really broken
    assert assistant_context._readable('a.c', helper.replace('#endif\n', '')) is None   # unpaired #ifdef
    # only #if/#else/#endif lines are left out: a broken or new #include / #define outside is still refused
    assert assistant_context._inserted_helpers('a.c', '#include <\n' + helper) == []
    assert assistant_context._inserted_helpers('a.c', '#define LIMIT 3\n' + helper) == []
    assert assistant_context._inserted_helpers('a.c', '#ifdef NET\n' + helper + '\n#endif\n') == ['add_alpha']


def test_explanation_lists_are_tidied_not_rejected():
    data = reply('a.c')
    data.update(reasons=['근거입니다.'] * 12, suggestions=['', '  '], tests=[])
    assistant.validate_advice(data)
    assert len(data['reasons']) == 8
    assert data['suggestions'] == ['조건 블록을 정적 보조 함수 add_alpha로 옮깁니다.']   # filled from the file review
    assert data['tests'] == ['반환값이 같은지 확인합니다.']
    with pytest.raises(ValueError):
        assistant.validate_advice(dict(reply('a.c'), file_reviews=[], tests=[]))   # nothing to fill from
    with pytest.raises(ValueError):
        assistant.validate_advice(dict(reply('a.c'), file_reviews=123, tests=[]))


def test_a_rejected_reply_is_kept_as_it_arrived_on_every_connection(monkeypatch):
    sent = dict(reply('a.c'), reasons=['근거입니다.'] * 12, overview='잘못된 요약')
    import contextlib
    import io
    body = json.dumps({'content': [{'type': 'text', 'text': json.dumps(sent)}]}).encode('utf8')
    monkeypatch.setattr(assistant.urllib.request, 'urlopen', lambda *a, **kw: contextlib.nullcontext(io.BytesIO(body)))
    with pytest.raises(ValueError) as caught:
        assistant.call_provider('claude', 'api', '{}', 'claude-sonnet-5-5', 'key')
    assert caught.value.reply == sent and len(caught.value.reply['reasons']) == 12   # not the tidied copy


def test_a_task_cancelled_during_an_api_request_sends_no_retry(monkeypatch):
    import io
    sent = []

    def refused(request, timeout=None):
        sent.append(request.full_url)
        assistant.CANCELLED.add('task-x')   # cancelled while the first request ran; the model then answers 400
        raise assistant.urllib.error.HTTPError(request.full_url, 400, 'too large', {}, io.BytesIO(b'{}'))
    monkeypatch.setattr(assistant.urllib.request, 'urlopen', refused)
    assistant._TASK.key = 'task-x'
    try:
        with pytest.raises(ValueError, match='취소'):
            assistant.call_provider('claude', 'api', '{}', 'claude-sonnet-5-5', 'key')
        with pytest.raises(ValueError, match='취소'):
            assistant._compatible('{}', 'm', 'key', 'http://127.0.0.1:9', {}, '', lambda d: d)
    finally:
        assistant._TASK.key = None
        assistant.CANCELLED.discard('task-x')
    assert len(sent) == 2   # one request each, no retry after the cancel


def test_helper_inserted_before_its_block_is_moved_still_applies(tmp_path):
    (tmp_path / 'a.c').write_text(BODY['a.c'], encoding='utf8')
    edits = list(reversed(reply('a.c')['edits']))   # helper first: the moved block now appears twice
    files = assistant.preview_changes(tmp_path, edits)['files']
    after = files[0]['after']
    assert after.count('\tif (x > 0) {') == 1 and '\tadd_alpha(x);' in after and after.index('static void add_alpha') < after.index('int Alpha')


def test_cancel_stops_every_file(tmp_path, monkeypatch):
    release = threading.Event()

    def provider(*args, **kw):
        release.wait(10)
        return reply('a.c')
    monkeypatch.setattr(assistant, 'call_provider', provider)
    app, ident = make_job(tmp_path)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        h = {'X-Game-SI-Token': client.get('/api/session').json()['token']}
        url = f'/api/jobs/{ident}/assistant'
        client.post(url, headers=h, json=dict(action='preview', strategy='deep', service='claude', mode='cli', candidates=['a', 'b'], direct=True))
        for _ in range(100):
            if any(w['state'] == 'running' for w in client.get(url).json()['workers']):
                break
            time.sleep(0.05)
        cancelled = client.post(url + '/cancel', headers=h, json={}).json()
        assert cancelled['state'] == 'cancelled' and {w['state'] for w in cancelled['workers']} == {'cancelled'}
        release.set()
        time.sleep(0.5)
        later = client.get(url).json()
        assert later['state'] == 'cancelled' and 'preview' not in later   # late replies are dropped


def test_a_large_file_sends_its_target_functions_whole_never_cut(monkeypatch):
    filler = ''.join(f'int filler{i}(void)\n{{\n\treturn {i};\n}}\n\n' for i in range(400))
    target = 'int Big(int x)\n{\n' + ''.join(f'\tif (x == {i}) x += {i};\n' for i in range(300)) + '\treturn x;\n}\n'
    text = '#include "big.h"\n\n' + filler + target
    lines = text.splitlines()
    start = lines.index('int Big(int x)') + 1
    methods = [dict(file_path='big.c', name='Big', fqn='big.Big', start_line=start, end_line=len(lines), cc=301, loc=303)]
    methods += [dict(file_path='big.c', name=f'filler{i}', fqn=f'big.filler{i}', start_line=3 + 5 * i, end_line=6 + 5 * i, cc=1, loc=4) for i in range(400)]
    sources = {'big.c': text.encode('utf8'), 'big.h': b'int Big(int x);\n'}
    monkeypatch.setattr(assistant_context, 'DEEP_FULL_LIMIT', 5_000)
    monkeypatch.setattr(assistant_context, 'DEEP_PROMPT_LIMIT', 60_000)
    prompt, context = assistant_context.build_deep_prompt({'fqn': 'big', 'file_path': 'big.c'}, 'big.c', sources, methods)
    payload = json.loads(prompt)
    main = next(s for s in payload['sources'] if s['path'] == 'big.c')
    assert context['mode'] == 'focused' and context['targets'] == ['Big'] and context['skipped_targets'] == []
    assert target in main['content'] and all(not r['partial'] for r in main['ranges'])
    assert payload['focus_functions'][0]['name'] == 'Big' and payload['editable_paths'] == ['big.c']
    assert len(prompt.encode('utf8')) <= 60_000
    # Too small to hold the target whole: it is reported as skipped, not cut.
    monkeypatch.setattr(assistant_context, 'DEEP_PROMPT_LIMIT', 20_000)
    _, context = assistant_context.build_deep_prompt({'fqn': 'big', 'file_path': 'big.c'}, 'big.c', sources, methods)
    assert context['targets'] == [] and context['skipped_targets'] == ['Big']


def test_other_functions_give_way_before_a_target_is_dropped(monkeypatch):
    # The target fits the raw budget but JSON escaping makes the prompt too large with the extras:
    # the extra functions are dropped first, the target stays whole.
    big = 'int Big(int x)\n{\n' + ''.join(f'\tif (x == {i}) {{ x += "{i}"[0]; }}\n' for i in range(900)) + '\treturn x;\n}\n'
    small = ''.join(f'int s{i}(void)\n{{\n\treturn "{i}"[0];\n}}\n' for i in range(200))
    text = small + big
    lines = text.split('\n')
    start = lines.index('int Big(int x)') + 1
    methods = [dict(file_path='big.c', name='Big', fqn='big.Big', start_line=start, end_line=len(lines) - 1, cc=901, loc=903)]
    methods += [dict(file_path='big.c', name=f's{i}', fqn=f'big.s{i}', start_line=1 + 4 * i, end_line=4 + 4 * i, cc=1, loc=4) for i in range(200)]
    monkeypatch.setattr(assistant_context, 'DEEP_FULL_LIMIT', 5_000)
    monkeypatch.setattr(assistant_context, 'DEEP_PROMPT_LIMIT', len(big) + 30_000)
    prompt, context = assistant_context.build_deep_prompt({'fqn': 'big', 'file_path': 'big.c'}, 'big.c', {'big.c': text.encode('utf8')}, methods)
    assert context['targets'] == ['Big'] and big.rstrip('\n') in json.loads(prompt)['sources'][0]['content']


def test_a_form_feed_does_not_shift_lines_and_cut_the_target():
    # The analyzer numbers lines on '\n' only; a form feed in a comment must not move the target's end.
    filler = ''.join(f'int f{i}(void)\n{{\n\treturn {i};\n}}\n' for i in range(50))
    text = '/* page\fbreak */\n' + filler + 'int Big(int x)\n{\n\tif (x) x++;\n\treturn x;\n}\n'
    lines = text.split('\n')
    start = lines.index('int Big(int x)') + 1
    methods = [dict(file_path='big.c', name='Big', fqn='big.Big', start_line=start, end_line=start + 4, cc=12, loc=5)]
    original = (assistant_context.DEEP_FULL_LIMIT, assistant_context.DEEP_PROMPT_LIMIT)
    try:
        assistant_context.DEEP_FULL_LIMIT = 100
        prompt, context = assistant_context.build_deep_prompt({'fqn': 'big', 'file_path': 'big.c'}, 'big.c', {'big.c': text.encode('utf8')}, methods)
    finally:
        assistant_context.DEEP_FULL_LIMIT, assistant_context.DEEP_PROMPT_LIMIT = original
    content = json.loads(prompt)['sources'][0]['content']
    assert context['targets'] == ['Big'] and 'int Big(int x)\n{\n\tif (x) x++;\n\treturn x;\n}' in content


def test_a_cancelled_task_sends_no_request(monkeypatch):
    monkeypatch.setattr(assistant.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('a request was sent'))
    key = ('assistant', 'job', 'cancelled-run')
    assistant.CANCELLED.add(key)
    with assistant.owned_by(key):
        with pytest.raises(ValueError, match='취소'):
            assistant.call_provider('claude', 'api', '{}', 'model', 'key')


def test_round_changes_keep_overloads_apart_and_measure_each_file(tmp_path):
    app = create_app(tmp_path)
    manager = app.state.manager
    ident = manager.create('함수 비교', 'folder')['id']
    folder = manager.directory(ident)
    before = {'a.cpp': 'int foo(int x) { return 1; }\nint foo(double x) { return 2; }\nint shared(void) { return 3; }\n',
              'b.cpp': 'int shared(void) { return 4; }\n'}
    after = {'a.cpp': 'int foo(int x) { return 9; }\nint foo(double x) { return 2; }\nint shared(void) { return 5; }\n',
             'b.cpp': 'int shared(void) { return 6; }\n'}
    revision = 'f' * 32
    for root, files in [(folder / 'input', before), (folder / 'revisions' / revision / 'source', after)]:
        root.mkdir(parents=True, exist_ok=True)
        for name, text in files.items():
            (root / name).write_text(text, encoding='utf8')

    def metrics(path, rows):
        path.mkdir(parents=True, exist_ok=True)
        (path / 'metrics.json').write_text(json.dumps({'methods': [dict(file_path=f, name=n, start_line=s, cc=c, loc=1) for f, n, s, c in rows]}), encoding='utf8')
        (path / 'scoring.json').write_text(json.dumps({'class_scores': [], 'analysis_status': {'state': 'complete'}}), encoding='utf8')
    metrics(folder / 'result', [('a.cpp', 'foo', 1, 1), ('a.cpp', 'foo', 2, 1), ('a.cpp', 'shared', 3, 10), ('b.cpp', 'shared', 1, 20)])
    metrics(folder / 'revisions' / revision / 'result', [('a.cpp', 'foo', 1, 1), ('a.cpp', 'foo', 2, 1), ('a.cpp', 'shared', 3, 2), ('b.cpp', 'shared', 1, 3)])
    (folder / 'rounds.json').write_text(json.dumps({'rounds': [{'round': 1, 'revision': revision, 'base': None, 'files': ['a.cpp', 'b.cpp'],
                                                               'checks': {}}], 'current': 1}), encoding='utf8')
    manager.update(ident, state='complete', options={'lang': 'cpp', 'subdir': '.'})
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        rows = client.get(f'/api/jobs/{ident}/rounds/1/changes').json()['functions']
    found = {(r['file'], r['name']): r for r in rows}
    assert sorted(found) == [('a.cpp', 'foo'), ('a.cpp', 'shared'), ('b.cpp', 'shared')]   # foo(double) did not change
    assert '+int foo(int x) { return 9; }' in found[('a.cpp', 'foo')]['diff']   # a one-line change keeps its new line
    assert found[('a.cpp', 'shared')]['before']['cc'] == 10 and found[('a.cpp', 'shared')]['after']['cc'] == 2
    assert found[('b.cpp', 'shared')]['before']['cc'] == 20 and found[('b.cpp', 'shared')]['after']['cc'] == 3


def test_prescribed_functions_come_first():
    methods = [dict(file_path='a.c', name=n, fqn=f'a.{n}', start_line=i * 10 + 1, end_line=i * 10 + 9, cc=cc, loc=9)
               for i, (n, cc) in enumerate([('Huge', 90), ('Mid', 40), ('Small', 12), ('Tiny', 2)])]
    # Two at most: one reply has to fit the time limit, and a huge function alone fills it.
    assert [m['name'] for m in assistant_context.deep_targets('a.c', methods, ['Small'])] == ['Small', 'Huge']
    assert [m['name'] for m in assistant_context.deep_targets('a.c', methods)] == ['Huge', 'Mid']


def test_a_state_file_swap_refused_for_a_moment_is_tried_again(tmp_path, monkeypatch):
    # Windows refuses the swap while a page is reading the file; one refusal used to fail the whole task.
    from pathlib import Path
    from game_si.web.jobs import write_json
    real, refused = Path.replace, []

    def flaky(self, target):
        if len(refused) < 2:
            refused.append(target)
            raise PermissionError(13, 'in use')
        return real(self, target)
    monkeypatch.setattr(Path, 'replace', flaky)
    write_json(tmp_path / 'state.json', {'state': 'done'})
    assert len(refused) == 2 and json.loads((tmp_path / 'state.json').read_text('utf8')) == {'state': 'done'}
    assert [p.name for p in tmp_path.iterdir()] == ['state.json']   # no temporary file left behind
