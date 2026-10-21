"""Cancelling an AI request stops only that request's AI program, and a late worker never overwrites."""
import sys
import threading
import time

import pytest

pytest.importorskip('fastapi')
from fastapi.testclient import TestClient

from game_si.web import assistant, prescription


def test_cancel_owner_stops_only_its_own_process(tmp_path):
    results = {}

    def run(key):
        with assistant.owned_by(key):
            started = time.time()
            result = assistant.run_cli([sys.executable, '-c', 'import time; time.sleep(30)'], '', tmp_path)
            results[key] = (result.returncode, time.time() - started)
    mine, other = threading.Thread(target=run, args=(('assistant', 'a', '1'),)), threading.Thread(target=run, args=(('assistant', 'b', '2'),))
    mine.start(); other.start()
    for _ in range(100):
        with assistant.PROCESS_LOCK:
            if len(assistant.OWNERS) >= 2:
                break
        time.sleep(0.05)
    assert assistant.cancel_owner(('assistant', 'a', '1')) == 1
    mine.join(timeout=10)
    assert not mine.is_alive() and results[('assistant', 'a', '1')][0] != 0 and results[('assistant', 'a', '1')][1] < 15
    assert other.is_alive()   # the other task's program keeps running
    assert assistant.cancel_owner(('assistant', 'b', '2')) == 1
    other.join(timeout=10)
    assert not assistant.OWNERS


def test_preview_and_prescription_can_be_cancelled(tmp_path, monkeypatch):
    from test_review_fixes import make_job
    release = threading.Event()
    calls = []

    def slow(service, mode, prompt, *args, **kwargs):   # stands in for an AI program that takes long
        calls.append(service)
        release.wait(10)
        raise ValueError('AI 요청이 완료되지 않았습니다.')
    monkeypatch.setattr(assistant, 'call_provider', slow)
    monkeypatch.setattr(prescription.assistant, 'call_provider', slow)
    app, ident = make_job(tmp_path)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        h = {'X-Game-SI-Token': client.get('/api/session').json()['token']}
        url = f'/api/jobs/{ident}/assistant'
        assert client.post(url + '/cancel', headers=h).status_code == 400          # nothing to cancel
        assert client.post(url, headers=h, json=dict(action='preview', service='codex', mode='cli', candidates=['main'], direct=True)).status_code == 202
        assert client.post(url + '/cancel').status_code == 403                     # token required
        state = client.post(url + '/cancel', headers=h).json()
        assert state['state'] == 'cancelled' and state['progress']['stage'] == 'cancelled'
        release.set()
        time.sleep(0.3)
        assert client.get(url).json()['state'] == 'cancelled'                      # late failure does not overwrite
        release.clear()

        purl = f'/api/jobs/{ident}/prescription'
        assert client.post(purl, headers=h, json={'service': 'claude', 'mode': 'cli'}).status_code == 202
        assert client.post(purl + '/cancel', headers=h).json()['state'] == 'cancelled'
        release.set()
        time.sleep(0.3)
        assert client.get(purl).json()['state'] == 'cancelled'
        # A new request after cancelling starts normally.
        release.clear()
        assert client.post(url, headers=h, json=dict(action='preview', service='codex', mode='cli', candidates=['main'], direct=True)).status_code == 202
        assert client.get(url).json()['state'] == 'running'
        client.post(url + '/cancel', headers=h)
        release.set()
    assert len(calls) == 3
