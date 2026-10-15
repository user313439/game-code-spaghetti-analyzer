import importlib
import importlib.util
import json
import time

import pytest
pytest.importorskip('psutil')


def module():
    assert importlib.util.find_spec('game_si.web.jobs'), 'Job runner is missing'
    return importlib.import_module('game_si.web.jobs')


def prepared(manager, text='int Tick(int x) { if(x) return 1; return 0; }'):
    job = manager.create('새 분석', 'folder')
    path = manager.directory(job['id']) / 'input'
    path.mkdir(exist_ok=True)
    (path / 'game.c').write_text(text, encoding='utf-8')
    manager.ready(job['id'])
    return job['id']


def wait(manager, ident):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        value = manager.get(ident)
        if value['state'] not in {'running', 'importing'}:
            return value
        time.sleep(.05)
    pytest.fail('Analysis did not finish')


def test_actual_cli_result_and_restart_history(tmp_path):
    manager = module().JobManager(tmp_path)
    try:
        ident = prepared(manager)
        manager.start(ident, {'lang': 'c', 'subdir': '.', 'backend': 'tree-sitter'})
        result = wait(manager, ident)
        assert result['state'] == 'complete', result
        assert result['result_url'].endswith('/index.html')
        assert json.loads((manager.directory(ident) / 'result/scoring.json').read_text(encoding='utf-8'))
    finally:
        manager.close()
    reopened = module().JobManager(tmp_path)
    assert reopened.get(ident)['state'] == 'complete'
    assert len(reopened.list()) == 1
    reopened.close()


def test_soft_delete_actual_result_preserves_files_and_restores_after_restart(tmp_path):
    manager = module().JobManager(tmp_path)
    ident = prepared(manager)
    manager.start(ident, {'lang': 'c'})
    assert wait(manager, ident)['state'] == 'complete'
    manager.close()
    manager = module().JobManager(tmp_path)
    source = (manager.directory(ident) / 'input/game.c').read_bytes()
    report = (manager.directory(ident) / 'result/index.html').read_bytes()
    deleted = manager.delete(ident)
    assert deleted['deleted_at'] and deleted['state'] == 'complete'
    assert deleted['result_url'] is None and not deleted['can_delete']
    assert manager.list() == []
    assert manager.list(include_deleted=True)[0]['id'] == ident
    with pytest.raises(KeyError):
        manager.get(ident)
    manager.close()
    reopened = module().JobManager(tmp_path)
    assert reopened.list() == []
    assert reopened.restore(ident)['state'] == 'complete'
    assert reopened.get(ident)['result_url']
    assert (reopened.directory(ident) / 'input/game.c').read_bytes() == source
    assert (reopened.directory(ident) / 'result/index.html').read_bytes() == report
    reopened.close()


@pytest.mark.parametrize('reservation', ['import_workers', 'processes'])
def test_reserved_interrupted_job_cannot_be_deleted(tmp_path, reservation):
    manager = module().JobManager(tmp_path)
    ident = manager.create('import', 'folder')['id']
    with pytest.raises(module().BusyError):
        manager.delete(ident)
    manager.cancel(ident)
    slot = getattr(manager, reservation)
    if isinstance(slot, set):
        slot.add(ident)
    else:
        slot[ident] = object()
    assert not manager.get(ident)['can_delete']
    with pytest.raises(module().BusyError):
        manager.delete(ident)
    slot.clear()
    assert manager.get(ident)['can_delete']
    manager.delete(ident)
    with pytest.raises(KeyError):
        manager.start(ident, {'lang': 'c'})
    with pytest.raises(KeyError):
        manager.cancel(ident)
    manager.close()


def test_source_size_backfill_only_for_imported_records_and_cached(tmp_path, monkeypatch):
    manager = module().JobManager(tmp_path)
    ready = prepared(manager)
    failed = manager.create('bad', 'folder')['id']
    (manager.directory(failed) / 'input/partial.c').write_text('int f();')
    manager.fail(failed, 'import failed')
    manager.records[ready]['scan'].pop('source_bytes', None)
    manager._save(manager.records[ready])
    manager.close()
    reopened = module().JobManager(tmp_path)
    assert reopened.get(ready)['scan']['source_bytes'] > 0
    assert reopened.get(failed)['scan'] is None
    monkeypatch.setattr(module(), 'inspect_source', lambda root: pytest.fail('must not rescan on poll'))
    assert reopened.get(ready)['scan']['source_bytes'] > 0
    assert len(reopened.list()) == 2
    reopened.close()


@pytest.mark.parametrize('state', ['ready', 'failed', 'interrupted', 'partial'])
def test_restore_preserves_terminal_or_ready_state(tmp_path, state):
    manager = module().JobManager(tmp_path)
    ident = prepared(manager)
    manager.update(ident, state=state, error='saved detail', options={'lang': 'c'})
    original = manager.get(ident)
    manager.delete(ident)
    restored = manager.restore(ident)
    for field in ['state', 'scan', 'source', 'error', 'options', 'created_at']:
        assert restored[field] == original[field]
    manager.close()


def test_source_size_is_whole_import_not_selected_analysis_folder(tmp_path):
    manager = module().JobManager(tmp_path)
    ident = manager.create('game', 'folder')['id']
    root = manager.directory(ident) / 'input'
    (root / 'src').mkdir()
    (root / 'src/game.c').write_bytes(b'int f(){return 1;}')
    (root / 'game.h').write_bytes(b'int f();')
    manager.ready(ident)
    before = manager.get(ident)['scan']['source_bytes']
    manager._command(ident, {'lang': 'c', 'subdir': 'src'})
    assert before == len(b'int f(){return 1;}int f();')
    assert manager.get(ident)['scan']['source_bytes'] == before
    manager.close()


def test_unknown_backfill_is_saved_once_even_if_sources_are_missing(tmp_path, monkeypatch):
    manager = module().JobManager(tmp_path)
    ident = prepared(manager)
    manager.records[ident]['scan'].pop('source_bytes')
    manager._save(manager.records[ident])
    manager.close()
    calls = []
    def missing(root):
        calls.append(root)
        raise OSError('source unavailable')
    monkeypatch.setattr(module(), 'inspect_source', missing)
    reopened = module().JobManager(tmp_path)
    assert reopened.get(ident)['scan']['source_bytes'] is None
    reopened.close()
    again = module().JobManager(tmp_path)
    assert again.get(ident)['scan']['source_bytes'] is None
    assert len(calls) == 1
    again.close()


def test_partial_result_is_not_failed(tmp_path):
    manager = module().JobManager(tmp_path)
    try:
        ident = prepared(manager, 'int Tick(){return missing + ;}')
        manager.start(ident, {'lang': 'c'})
        result = wait(manager, ident)
        assert result['state'] == 'partial', result
        assert result['result_url']
    finally:
        manager.close()


def test_failed_and_timed_out_have_no_result(tmp_path):
    manager = module().JobManager(tmp_path, timeout=.001)
    try:
        ident = prepared(manager)
        manager.start(ident, {'lang': 'c'})
        result = wait(manager, ident)
        assert result['state'] == 'interrupted'
        assert result['result_url'] is None
    finally:
        manager.close()


@pytest.mark.parametrize('options', [{'lang': 'python'}, {'subdir': '../'},
                                    {'backend': 'shell'}, {'backend': 'clang'},
                                    {'lang': 'csharp', 'backend': 'clang'}])
def test_bad_settings_do_not_launch(tmp_path, options):
    manager = module().JobManager(tmp_path)
    try:
        ident = prepared(manager)
        with pytest.raises(ValueError):
            manager.start(ident, options)
        assert manager.get(ident)['state'] == 'ready'
    finally:
        manager.close()


def test_id_validation_and_interrupted_recovery(tmp_path):
    manager = module().JobManager(tmp_path)
    job = manager.create('import', 'github')
    with pytest.raises(ValueError):
        manager.directory('../../')
    manager.close()
    reopened = module().JobManager(tmp_path)
    assert reopened.get(job['id'])['state'] == 'interrupted'
    reopened.close()


def test_only_one_running_job_and_cancel(tmp_path):
    manager = module().JobManager(tmp_path)
    try:
        a = prepared(manager)
        b = prepared(manager)
        manager.start(a, {'lang': 'c'})
        with pytest.raises(module().BusyError):
            manager.start(b, {'lang': 'c'})
        manager.cancel(a)
        result = wait(manager, a)
        assert result['state'] == 'interrupted'
        assert result['result_url'] is None
    finally:
        manager.close()


def test_corrupt_record_does_not_break_other_jobs(tmp_path):
    ident = 'a' * 32
    folder = tmp_path / ident
    folder.mkdir()
    (folder / 'job.json').write_text(json.dumps({'id': ident}), encoding='utf-8')
    manager = module().JobManager(tmp_path)
    try:
        assert manager.list() == []
        assert manager.create('new', 'folder')['state'] == 'importing'
    finally:
        manager.close()


def test_inconsistent_scoring_never_published(tmp_path, monkeypatch):
    manager = module().JobManager(tmp_path)
    ident = prepared(manager)
    result = manager.directory(ident) / 'result'
    result.mkdir()
    (result / 'analysis_status.json').write_text('{"state":"complete"}')
    (result / 'scoring.json').write_text('{"analysis_status":{"state":"partial"}}')
    (result / 'index.html').write_text('report')

    class Finished:
        returncode = 0
        def poll(self):
            return 0

    monkeypatch.setattr(module().subprocess, 'Popen', lambda *a, **k: Finished())
    try:
        manager._run(ident, ['dummy'])
        assert manager.get(ident)['state'] == 'failed'
        assert manager.get(ident)['result_url'] is None
    finally:
        manager.close()
