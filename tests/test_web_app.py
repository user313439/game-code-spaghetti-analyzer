import importlib
import importlib.util
import io
import json
import time
import zipfile

import pytest
pytest.importorskip('fastapi')
pytest.importorskip('httpx2')
from fastapi.testclient import TestClient


def app_module():
    assert importlib.util.find_spec('game_si.web.app'), 'HTTP app is missing'
    return importlib.import_module('game_si.web.app')


def test_http_feature_exists():
    assert importlib.util.find_spec('game_si.web.app'), 'HTTP app is missing'


def test_soft_delete_api_is_token_protected_and_hides_results(client):
    job = upload(client).json()
    ident = job['id']
    manager = client.app.state.manager
    result = manager.directory(ident) / 'result'
    result.mkdir()
    (result / 'index.html').write_text('saved report')
    manager.update(ident, state='partial')
    for action in ['delete', 'restore']:
        assert client.post(f'/api/jobs/{ident}/{action}').status_code == 403
    assert client.post(f'/api/jobs/{ident}/delete', headers=headers(client)).status_code == 200
    assert client.get('/api/jobs').json() == []
    assert client.get('/api/jobs?include_deleted=true').json()[0]['deleted_at']
    assert client.get(f'/api/jobs/{ident}').status_code == 404
    assert client.get(f'/results/{ident}/index.html').status_code == 404
    for action in ['start', 'cancel']:
        assert client.post(f'/api/jobs/{ident}/{action}', headers=headers(client), json={}).status_code == 404
    assert client.post(f'/api/jobs/{ident}/restore', headers=headers(client)).status_code == 200
    assert client.get(f'/results/{ident}/index.html').text == 'saved report'
    for action in ['delete', 'restore']:
        assert client.post(f'/api/jobs/bad/{action}', headers=headers(client)).status_code == 400
        assert client.post(f'/api/jobs/{"f" * 32}/{action}', headers=headers(client)).status_code == 404


def test_examples_have_four_projects_and_four_auxiliary_modules(client):
    examples = client.get('/api/examples').json()
    required = {'name', 'url', 'project', 'genre', 'language', 'description', 'scope', 'focus', 'auxiliary'}
    assert all(required <= item.keys() for item in examples)
    assert {item['project'] for item in examples if not item['auxiliary']} == {'OpenRA', 'Chocolate Doom', 'OpenRCT2', 'DOOM 3'}
    assert len([item for item in examples if item['auxiliary']]) == 4
    rct = next(item for item in examples if item['project'] == 'OpenRCT2')
    assert 'src/openrct2' in rct['scope'] and '부분' in rct['scope']


def test_white_preview_preserves_saved_reports_data_and_access_rules(client):
    ident = upload(client).json()['id']
    manager = client.app.state.manager
    result = manager.directory(ident) / 'result'
    result.mkdir()
    original = '<!doctype html><html><head><title>QA</title></head><body>Original<script>const data={score:42};</script></body></html>'
    page = result / 'index.html'
    page.write_text(original, encoding='utf-8')
    (result / 'scoring.json').write_text('{"score":42}', encoding='utf-8')
    manager.update(ident, state='complete')
    path = f'/results/{ident}/index.html'
    for query in ['?theme=dark']:
        assert client.get(path + query).text == original
    for query in ['', '?theme=invalid', '?theme=blue']:
        blue = client.get(path + query)
        assert 'id="report-blue-preview"' in blue.text
        assert 'const data={score:42};' in blue.text
    response = client.get(path + '?theme=light')
    assert response.status_code == 200
    assert 'id="report-light-preview"' in response.text
    assert 'const data={score:42};' in response.text
    rendered = response.text.replace(response.text[response.text.index('<style id="report-light-preview">'):response.text.index('</style>') + len('</style>')], '')
    injected = '<script id="report-layout-preview">' + (app_module().STATIC / 'report-embed.js').read_text('utf8') + '</script>'
    assert rendered.replace(injected, '') == original
    assert page.read_text(encoding='utf-8') == original
    assert client.get(f'/results/{ident}/scoring.json?theme=light').json() == {'score': 42}
    assert client.get(f'/results/{ident}/scoring.json').json() == {'score': 42}
    assert 'sandbox allow-scripts allow-downloads' in response.headers['content-security-policy']
    client.post(f'/api/jobs/{ident}/delete', headers=headers(client))
    assert client.get(path + '?theme=light').status_code == 404


def test_white_preview_also_applies_to_existing_examples_without_replacing_them(client):
    path = '/examples/openra-game/index.html'
    page = app_module().REPO_ROOT / 'reports' / 'openra-game' / 'index.html'
    original = page.read_bytes()
    assert client.get(path + '?theme=dark').content == original
    white = client.get(path + '?theme=light')
    assert white.status_code == 200
    assert 'id="report-light-preview"' in white.text
    assert '--bg:#f7f8f6' in white.text
    assert '#hotspot-table{display:table;width:100%;max-width:none}' in white.text
    assert '.report-table-scroll{width:100%;max-width:100%;min-height:160px;overflow-x:auto}' in white.text
    assert 'id="report-layout-preview"' in white.text
    assert '#hotspot-table th.sortable[data-tooltip]::after{content:attr(data-tooltip)}' in white.text
    assert '[data-tooltip]::after{display:none;' in white.text
    assert '.gt-btn[data-grade="D"].gt-active{color:#061108}' in white.text
    assert page.read_bytes() == original
    assert client.get(path + '?theme=dark').content == original
    assert client.get('/examples/not-allowed/index.html?theme=light').status_code == 404


def test_blue_preview_has_its_own_palette_and_preserves_the_other_versions(client):
    path = '/examples/openra-game/index.html'
    original = client.get(path + '?theme=dark').content
    white = client.get(path + '?theme=light').content
    response = client.get(path + '?theme=blue')
    assert response.status_code == 200
    assert 'id="report-blue-preview"' in response.text
    assert '--bg:#eaf2f9' in response.text and '--accent:#356d9b' in response.text
    assert client.get(path).content == response.content
    assert client.get(path + '?theme=dark').content == original
    assert client.get(path + '?theme=light').content == white
    assert 'sandbox allow-scripts allow-downloads' in response.headers['content-security-policy']


def test_default_page_is_the_redesigned_app_with_theme_before_styles(client):
    response = client.get('/')
    text = response.text
    assert response.status_code == 200 and '<main id="view"' in text
    assert text.index('/ui/theme-init.js') < text.index('/ui/app.css') < text.index('/ui/main.js')
    assert "script-src 'self'" in response.headers['content-security-policy']
    assert '<script>' not in text and 'style=' not in text   # CSP forbids inline script/style


def test_ui_assets_are_whitelisted_with_correct_types(client):
    js = client.get('/ui/main.js')
    assert js.status_code == 200 and js.headers['content-type'].startswith('text/javascript')
    assert client.get('/ui/app.css').headers['content-type'].startswith('text/css')
    for bad in ['/ui/index.html', '/ui/..%2Fapp.py', '/ui/Main.js', '/ui/missing.js', '/ui/app.css.map']:
        assert client.get(bad).status_code == 404, bad
    assert client.get('/legacy').status_code == 404 and client.get('/static/app.js').status_code == 404


@pytest.fixture
def client(tmp_path):
    app = app_module().create_app(tmp_path)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        yield client


def headers(client):
    return {'X-Game-SI-Token': client.get('/api/session').json()['token'],
            'Origin': 'http://127.0.0.1:8765'}


def upload(client, path='game/main.c', text='int Tick(){return 1;}'):
    return client.post('/api/import/files', headers=headers(client),
                       files=[('files', ('main.c', text.encode(), 'application/octet-stream'))],
                       data={'paths': json.dumps([path]), 'name': '내 게임'})


def test_api_rejects_external_host_origin_and_missing_token(client):
    assert client.get('/api/session', headers={'Host': 'evil.example'}).status_code == 403
    assert client.post('/api/import/github', json={'url': 'x'}).status_code == 403
    h = headers(client)
    h['Origin'] = 'https://evil.example'
    assert client.post('/api/import/github', headers=h, json={'url': 'x'}).status_code == 403
    assert client.get('/api/session', headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403


def test_folder_upload_start_and_result_are_real(client):
    response = upload(client)
    assert response.status_code == 201, response.text
    job = response.json()
    assert job['state'] == 'ready'
    ident = job['id']
    assert client.get(f'/results/{ident}/index.html').status_code == 404
    start = client.post(f'/api/jobs/{ident}/start', headers=headers(client), json={'lang': 'c'})
    assert start.status_code == 202, start.text
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        result = client.get(f'/api/jobs/{ident}').json()
        if result['state'] != 'running':
            break
        time.sleep(.05)
    assert result['state'] == 'complete', result
    page = client.get(result['result_url'])
    assert page.status_code == 200
    assert '내 게임' in page.text
    assert client.get(f'/results/{ident}/ast.json').status_code == 404
    assert len(client.get('/api/jobs').json()) == 1


@pytest.mark.parametrize('path', ['../escape.c', 'C:/escape.c', 'game/CON.c'])
def test_upload_path_validation(client, path):
    assert upload(client, path).status_code == 400


def test_zip_upload_and_unsupported_file(client):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, 'w') as z:
        z.writestr('repo/game.c', 'int Update(){return 0;}')
    response = client.post('/api/import/files', headers=headers(client),
                           files={'files': ('game.zip', raw.getvalue())}, data={'paths': '["game.zip"]'})
    assert response.status_code == 201
    assert response.json()['scan']['languages']['c'] == 1
    assert upload(client, 'game.exe').status_code == 400


def test_unknown_job_and_invalid_repository_are_clear(client):
    assert client.get('/api/jobs/' + 'f' * 32).status_code == 404
    assert client.post('/api/import/github', headers=headers(client), json={'url': 'http://localhost/x'}).status_code == 400
    assert client.get('/results/../../.env').status_code == 404


def test_existing_examples_are_separate_and_restricted(client):
    examples = client.get('/api/examples').json()
    assert any('DOOM 3' in e['name'] for e in examples)
    assert client.get(examples[0]['url']).status_code == 200
    assert client.get('/examples/../../.env').status_code == 404


def test_ui_resources_are_same_origin(client):
    response = client.get('/')
    assert response.status_code == 200
    assert "script-src 'self'" in response.headers['content-security-policy']
    assert client.get('/ui/main.js').status_code == 200


def test_cancelled_import_blocks_next_until_worker_exits(client, monkeypatch):
    import threading
    entered, release = threading.Event(), threading.Event()
    def blocked_fetch(*args, **kwargs):
        entered.set()
        release.wait(3)
        raise ValueError('중단되었습니다.')
    monkeypatch.setattr(app_module().inputs, 'fetch_repository', blocked_fetch)
    try:
        job = client.post('/api/import/github', headers=headers(client), json={'url': 'https://github.com/a/b'}).json()
        assert entered.wait(2)
        client.post('/api/jobs/' + job['id'] + '/cancel', headers=headers(client))
        assert not client.get('/api/jobs/' + job['id']).json()['can_delete']
        assert client.post('/api/jobs/' + job['id'] + '/delete', headers=headers(client)).status_code == 409
        assert client.post('/api/import/github', headers=headers(client), json={'url': 'https://github.com/a/c'}).status_code == 409
    finally:
        release.set()


@pytest.mark.parametrize('kind', ['github', 'files'])
def test_import_is_reserved_before_created_job_can_be_cancelled_and_deleted(client, monkeypatch, kind):
    manager = client.app.state.manager
    original = manager.create
    observed = {}
    def cancel_after_create(*args, **kwargs):
        job = original(*args, **kwargs)
        ident = job['id']
        observed['id'] = ident
        observed['reserved'] = ident in manager.import_workers
        manager.cancel(ident)
        try:
            manager.delete(ident)
        except app_module().BusyError:
            observed['delete_blocked'] = True
        else:
            observed['delete_blocked'] = False
        return job
    def cancelled_fetch(*args, **kwargs):
        assert kwargs['cancelled']()
        raise ValueError('소스 가져오기가 중단되었습니다.')
    monkeypatch.setattr(manager, 'create', cancel_after_create)
    monkeypatch.setattr(app_module().inputs, 'fetch_repository', cancelled_fetch)
    if kind == 'github':
        client.post('/api/import/github', headers=headers(client), json={'url':'https://github.com/a/b'})
    else:
        upload(client)
    for worker in manager.threads:
        worker.join(3)
        assert not worker.is_alive()
    ident = observed['id']
    assert observed['reserved'], 'Import reservation must be active when creation returns'
    assert observed['delete_blocked'], 'Cancellation must not allow deletion before the importer exits'
    assert ident not in manager.import_workers
    assert manager.get(ident)['state'] == 'interrupted'
    assert list((manager.directory(ident) / 'input').iterdir()) == []
    assert manager.delete(ident)['deleted_at']


def test_folder_copy_cancel_holds_import_slot(client, monkeypatch):
    import threading
    entered, release = threading.Event(), threading.Event()
    original = app_module().inputs.is_source
    def delayed_source(name):
        entered.set()
        release.wait(3)
        return original(name)
    monkeypatch.setattr(app_module().inputs, 'is_source', delayed_source)
    task = threading.Thread(target=lambda: upload(client))
    task.start()
    try:
        assert entered.wait(2)
        job = client.get('/api/jobs').json()[0]
        client.post('/api/jobs/' + job['id'] + '/cancel', headers=headers(client))
        assert client.post('/api/import/github', headers=headers(client), json={'url': 'https://github.com/a/b'}).status_code == 409
    finally:
        release.set()
        task.join(4)


def test_path_metadata_over_one_mib_reaches_path_validation(client):
    response = client.post('/api/import/files', headers=headers(client),
        files={'files': ('main.c', b'int Tick(){return 1;}')},
        data={'paths': json.dumps(['x' * (1024 * 1024 + 1)])})
    assert response.status_code == 400
    assert '안전하지 않은 파일 경로' in response.json()['detail']


def test_zip_extraction_does_not_block_status_requests(client, monkeypatch):
    import threading
    entered = threading.Event()
    original = app_module().inputs.extract_zip
    def delayed(*args, **kwargs):
        entered.set()
        time.sleep(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(app_module().inputs, 'extract_zip', delayed)
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, 'w') as z:
        z.writestr('game.c', 'int Tick(){return 0;}')
    auth = headers(client)
    task = threading.Thread(target=lambda: client.post('/api/import/files', headers=auth,
        files={'files': ('game.zip', raw.getvalue())}, data={'paths':'["game.zip"]'}))
    task.start()
    try:
        assert entered.wait(2)
        started = time.monotonic()
        assert client.get('/api/session').status_code == 200
        assert time.monotonic() - started < .5
    finally:
        task.join(3)


def test_folder_copy_does_not_block_status_requests(client, monkeypatch):
    import threading
    entered = threading.Event()
    original = app_module().inputs.is_source
    def delayed(name):
        entered.set()
        time.sleep(1)
        return original(name)
    monkeypatch.setattr(app_module().inputs, 'is_source', delayed)
    task = threading.Thread(target=lambda: upload(client))
    task.start()
    try:
        assert entered.wait(2)
        started = time.monotonic()
        assert client.get('/api/session').status_code == 200
        assert time.monotonic() - started < .5
    finally:
        task.join(3)
