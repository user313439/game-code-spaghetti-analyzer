"""Finding Claude Code (PATH first, then the copy inside the Claude desktop app) and its login state."""
import subprocess

from game_si.web import assistant


def test_bundled_claude_code_is_found_newest_first(tmp_path, monkeypatch):
    for version in ['2.1.9', '2.1.10', 'not-a-version']:
        folder = tmp_path / 'Claude' / 'claude-code' / version / 'abc'
        folder.mkdir(parents=True)
        (folder / 'claude.exe').write_bytes(b'')
    monkeypatch.setenv('APPDATA', str(tmp_path))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('USERPROFILE', str(tmp_path / 'home'))
    monkeypatch.setattr(assistant.shutil, 'which', lambda name: None)
    assert assistant.executable('claude') == [str(tmp_path / 'Claude/claude-code/2.1.10/abc/claude.exe')]
    # The Store app's real location (works from any terminal) wins over the in-app view of the same version.
    store = tmp_path / 'local/Packages/AnthropicPBC.Claude_x/LocalCache/Roaming/Claude/claude-code/2.1.10/abc'
    store.mkdir(parents=True)
    (store / 'claude.exe').write_bytes(b'')
    assert assistant.executable('claude') == [str(store / 'claude.exe')]
    assert assistant.executable('codex') == []
    monkeypatch.setattr(assistant.shutil, 'which', lambda name: str(tmp_path / f'{name}.exe'))
    assert assistant.executable('claude') == [str(tmp_path / 'claude.exe')]   # an installed CLI wins


def test_login_state_comes_from_auth_status_without_an_ai_request(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, '{"loggedIn": true, "authMethod": "claude.ai"}', '')
    monkeypatch.setattr(assistant.subprocess, 'run', fake_run)
    assistant._LOGIN.clear()
    assert assistant.claude_logged_in(['claude.exe']) is True
    assert assistant.claude_logged_in(['claude.exe']) is True   # cached
    assert calls == [['claude.exe', 'auth', 'status']]
    monkeypatch.setattr(assistant.subprocess, 'run', lambda command, **kwargs: (_ for _ in ()).throw(OSError()))
    assistant._LOGIN.clear()
    assert assistant.claude_logged_in(['other.exe']) is None


def test_codex_inside_the_desktop_app_is_found_newest_first(tmp_path, monkeypatch):
    import os
    app = tmp_path / 'local/OpenAI/Codex/bin'
    for folder, stamp in [('', 100), ('old', 200), ('new', 300)]:
        (app / folder).mkdir(parents=True, exist_ok=True)
        (app / folder / 'codex.exe').write_bytes(b'')
        os.utime(app / folder / 'codex.exe', (stamp, stamp))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('USERPROFILE', str(tmp_path / 'home'))
    monkeypatch.setattr(assistant.shutil, 'which', lambda name: None)
    assert assistant.executable('codex') == [str(app / 'new/codex.exe')]
    extension = tmp_path / 'home/.vscode/extensions/openai.chatgpt-1.0/bin/windows-x86_64'
    extension.mkdir(parents=True)
    (extension / 'codex.exe').write_bytes(b'')
    os.utime(extension / 'codex.exe', (400, 400))
    assert assistant.executable('codex') == [str(extension / 'codex.exe')]
    monkeypatch.setattr(assistant.shutil, 'which', lambda name: str(tmp_path / f'{name}.exe'))
    assert assistant.executable('codex') == [str(tmp_path / 'codex.exe')]   # an installed CLI wins


def test_codex_login_comes_from_login_status_without_an_ai_request(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0 if command[0] == 'codex.exe' else 1, 'Logged in using ChatGPT', '')
    monkeypatch.setattr(assistant.subprocess, 'run', fake_run)
    monkeypatch.setattr(assistant, 'executable', lambda service: ['codex.exe'] if service == 'codex' else [])
    assistant._LOGIN.clear()
    row = {r['id']: r for r in assistant.capabilities()}['codex']
    assert row['installed'] and row['logged_in'] is True and row['login_command'] == 'codex.exe login'
    assert calls == [['codex.exe', 'login', 'status']]
    assert assistant.codex_logged_in(['other.exe']) is False


# ---------------------------------------------------------------- any other AI (OpenAI-compatible address)
import http.server
import json
import threading

import pytest


def test_address_rules_keep_the_key_on_https_or_this_pc():
    ok = assistant.check_base_url
    assert ok('https://api.openai.com/v1/') == 'https://api.openai.com/v1'
    assert ok('http://localhost:11434/v1') == 'http://localhost:11434/v1'
    assert ok('http://127.0.0.1:1234/v1') == 'http://127.0.0.1:1234/v1'
    for bad in ['', 'ftp://x/v1', 'http://example.com/v1', 'https://user:pw@example.com/v1', 'https://x.com/v1?key=1', 'javascript:alert(1)']:
        with pytest.raises(ValueError):
            ok(bad)


def test_connection_rules_for_every_kind():
    check = assistant.validate_connection
    check({'service': 'claude', 'mode': 'cli'})
    check({'service': 'compatible', 'mode': 'api', 'base_url': 'http://localhost:11434/v1', 'model': 'llama3.1:8b'})
    check({'service': 'compatible', 'mode': 'api', 'base_url': 'https://openrouter.ai/api/v1', 'model': 'anthropic/claude-3.5-sonnet', 'api_key': 'k'})
    for bad in [{'service': 'other', 'mode': 'cli'}, {'service': 'codex', 'mode': 'api', 'api_key': 'k'},
                {'service': 'compatible', 'mode': 'api', 'base_url': 'http://localhost:11434/v1'},
                {'service': 'compatible', 'mode': 'api', 'base_url': 'http://evil.example/v1', 'model': 'm'},
                {'service': 'claude', 'mode': 'cli', 'model': 'bad model;'}]:
        with pytest.raises(ValueError):
            check(bad)


def test_capabilities_offer_any_ai_without_an_install_flag(monkeypatch):
    monkeypatch.setattr(assistant, 'executable', lambda service: [])
    rows = {r['id']: r for r in assistant.capabilities()}
    assert set(rows) == {'codex', 'claude', 'compatible'}   # Gemini: an address under the other AIs
    assert any(p['url'] == 'http://localhost:11434/v1' and p.get('local') for p in rows['compatible']['presets'])


class FakeAI(http.server.BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *args):
        pass

    def _send(self, code, body):
        data = json.dumps(body).encode('utf8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        FakeAI.seen.append(('GET', self.path, self.headers.get('Authorization')))
        self._send(200, {'data': [{'id': 'llama3.1:8b'}, {'id': 'qwen2.5-coder:7b'}, {'id': 'bad name;'}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        FakeAI.seen.append(('POST', self.path, body))
        if 'response_format' in body:   # an old server that does not know JSON mode
            self._send(400, {'error': 'unknown field response_format'})
            return
        text = '<think>먼저 구조를 본다</think>답입니다:\n```json\n{"ok": true, "model": "%s"}\n```' % body['model']
        self._send(200, {'choices': [{'message': {'role': 'assistant', 'content': text}}]})


@pytest.fixture
def fake_ai():
    FakeAI.seen = []
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), FakeAI)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_address[1]}/v1'
    server.shutdown()


def test_any_ai_is_called_with_the_chat_api_and_its_reply_is_read(fake_ai):
    reply = assistant.call_provider('compatible', 'api', '프롬프트', 'llama3.1:8b', '', base_url=fake_ai + '/',
                                    schema={'type': 'object'}, guidance='지침', validate=lambda d: d)
    assert reply == {'ok': True, 'model': 'llama3.1:8b'}
    posts = [s for s in FakeAI.seen if s[0] == 'POST']
    assert [p[1] for p in posts] == ['/v1/chat/completions'] * 2        # retried without JSON mode
    assert posts[0][2]['response_format'] == {'type': 'json_object'} and 'response_format' not in posts[1][2]
    messages = posts[1][2]['messages']
    assert messages[0]['role'] == 'system' and '지침' in messages[0]['content'] and messages[1]['content'] == '프롬프트'


def test_model_list_asks_for_nothing_to_be_generated(fake_ai):
    assert assistant.list_models(fake_ai, 'secret') == ['llama3.1:8b', 'qwen2.5-coder:7b']
    assert FakeAI.seen == [('GET', '/v1/models', 'Bearer secret')]


def test_unreachable_address_gives_a_plain_message():
    with pytest.raises(ValueError, match='연결하지 못했습니다'):
        assistant.list_models('http://127.0.0.1:9/v1')


def test_web_api_lists_models_and_checks_the_connection(fake_ai, tmp_path):
    from fastapi.testclient import TestClient
    from game_si.web.app import create_app
    with TestClient(create_app(tmp_path), base_url='http://127.0.0.1:8765') as client:
        h = {'X-Game-SI-Token': client.get('/api/session').json()['token']}
        assert client.post('/api/assistant/models', headers=h, json={'base_url': fake_ai}).json() == {'models': ['llama3.1:8b', 'qwen2.5-coder:7b']}
        r = client.post('/api/assistant/models', headers=h, json={'base_url': 'http://example.com/v1'})
        assert r.status_code == 400 and 'https' in r.json()['detail']
        assert client.post('/api/assistant/models', json={'base_url': fake_ai}).status_code == 403   # token required


def test_each_program_lists_the_models_it_accepts(tmp_path, monkeypatch):
    monkeypatch.setattr(assistant.Path, 'home', lambda: tmp_path)
    assert assistant.codex_models() == []   # no cache: nothing named
    (tmp_path / '.codex').mkdir()
    (tmp_path / '.codex' / 'models_cache.json').write_text(json.dumps({'models': [
        {'slug': 'gpt-6-luna', 'visibility': 'list', 'priority': 5}, {'slug': 'gpt-6.1-sol', 'visibility': 'list', 'priority': 1},
        {'slug': 'hidden-model', 'visibility': 'hide', 'priority': 0}, {'slug': 'bad name;', 'visibility': 'list', 'priority': 2}]}), encoding='utf8')
    assert assistant.codex_models() == ['gpt-6.1-sol', 'gpt-6-luna']
    assert assistant.CLI_MODELS['claude']() == ['opus', 'sonnet', 'haiku'] and set(assistant.CLI_MODELS) == {'claude', 'codex'}
