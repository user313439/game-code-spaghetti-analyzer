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
