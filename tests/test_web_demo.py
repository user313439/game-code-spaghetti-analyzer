import json
import pytest


def test_demo_runs_only_registered_job_and_verified_revision(tmp_path):
    from game_si.web.demo import DemoGame
    class Assistant:
        def get(self, ident): return {'state': 'complete', 'revision': 'a' * 32}
    demo = DemoGame(Assistant(), tmp_path)
    assert demo.get('other') == {'available': False}
    with pytest.raises(ValueError):
        demo.prepare('other')
    (tmp_path / 'demo_job.json').write_text(json.dumps({'id': 'registered'}))
    assert demo.get('registered')['available']
    with pytest.raises(ValueError):
        demo.launch('registered', 'modified')
    with pytest.raises(ValueError):
        demo.launch('registered', '../outside')


def test_casual_demo_has_distinct_metadata_and_requires_matching_source(tmp_path):
    from game_si.web.casual_demo import CasualDemo
    class Assistant:
        def get(self,ident):return {'state':'complete','revision':'b'*32}
    demo=CasualDemo(Assistant(),tmp_path)
    assert demo.get('other')=={'available':False}
    (tmp_path/'demo_job.json').write_text(json.dumps({'id':'casual'}))
    data=demo.get('casual')
    assert data['available']
    assert 'OpenTyrian' in data['name']
    assert data['game_title'] == 'OpenTyrian'
    assert data['description'] and 'Space' not in data['description']
    assert 'Space' in data['controls']
    with pytest.raises(ValueError):demo.launch('casual','modified')


@pytest.mark.parametrize('scope, prefix', [('OpenTyrian/src', ''), ('OpenTyrian', 'src/'), ('.', 'OpenTyrian/src/')])
def test_casual_demo_finds_the_original_under_any_folder_choice(tmp_path, scope, prefix):
    # The scope screen starts on the whole import; the game can still be built from it.
    from game_si.web.casual_demo import CasualDemo
    original = tmp_path / 'demo' / '01_original' / 'source' / 'src'
    original.mkdir(parents=True)
    (original / 'tyrian2.c').write_text('int main(void) { return 0; }\n', encoding='utf8')
    imported = tmp_path / 'input' / 'OpenTyrian' / 'src'
    imported.mkdir(parents=True)
    (imported / 'tyrian2.c').write_text('int main(void) { return 0; }\n', encoding='utf8')
    (tmp_path / 'input' / 'OpenTyrian' / 'README.txt').write_text('not source', encoding='utf8')

    class Assistant:
        def source(self, ident): return tmp_path / 'input' / scope
    demo = CasualDemo(Assistant(), tmp_path / 'demo')
    assert demo._prefix('job') == prefix and demo.registered('job')
    (imported / 'tyrian2.c').write_text('int main(void) { return 1; }\n', encoding='utf8')
    assert CasualDemo(Assistant(), tmp_path / 'demo')._prefix('job') is None   # a different source is not the demo


def test_casual_demo_never_reuses_an_old_revision_verification(tmp_path):
    from game_si.web.casual_demo import CasualDemo
    class Assistant:
        revision = 'b'*32
        def get(self, ident): return {'state':'complete','revision':self.revision}
    assistant = Assistant()
    demo = CasualDemo(assistant, tmp_path)
    (tmp_path/'demo_job.json').write_text(json.dumps({'id':'casual'}))
    demo._save({'state':'complete','revision':'a'*32})
    evidence = tmp_path/'02_modified'/('a'*32)
    evidence.mkdir(parents=True)
    (evidence/'verification.json').write_text(json.dumps({'summary':'OLD VERIFIED CLAIM'}))
    stale = demo.get('casual')
    assert 'OLD VERIFIED CLAIM' not in stale['verification_summary'] and not stale.get('behavior_checked')
    assistant.revision = 'a'*32
    current = demo.get('casual')
    assert current['verification_summary'] == 'OLD VERIFIED CLAIM' and current['behavior_checked'] is True
    (evidence/'verification.json').unlink()
    assert demo.get('casual')['behavior_checked'] is False


def test_demo_prepare_returns_saved_progress_before_worker_runs(tmp_path, monkeypatch):
    from game_si.web import demo as module
    class Assistant:
        def get(self, ident): return {'state': 'complete', 'revision': 'a' * 32}
    class DeferredThread:
        def __init__(self, **kwargs): pass
        def start(self): pass
        def is_alive(self): return True
    monkeypatch.setattr(module.threading, 'Thread', DeferredThread)
    (tmp_path / 'demo_job.json').write_text(json.dumps({'id': 'registered'}))
    demo = module.DemoGame(Assistant(), tmp_path)
    state = demo.prepare('registered')
    assert state['state'] == 'running'
    assert state['started_at']
    assert state['progress'] == {
        'stage': 'copy', 'label': '시연 원본을 복사하고 있습니다.',
        'step': 0, 'total': 4, 'indeterminate': True,
    }
    assert demo.get('registered')['started_at'] == state['started_at']


@pytest.mark.parametrize('recipe', ['doom', 'casual'])
def test_demo_build_reports_real_stages_without_running_build_tools(tmp_path, monkeypatch, recipe):
    from game_si.web import casual_demo, demo as module
    revision = 'a' * 32
    relative = 'doom/m_menu.c' if recipe == 'doom' else 'main.c'
    baseline = tmp_path / '01_original/source/src' / relative
    baseline.parent.mkdir(parents=True)
    baseline.write_bytes(b'before')
    job = tmp_path / 'job'
    revised = job / 'revisions' / revision / 'source' / relative
    revised.parent.mkdir(parents=True)
    revised.write_bytes(b'after')
    for result in [job / 'result', job / 'revisions' / revision / 'result']:
        result.mkdir(parents=True)
        (result / 'index.html').write_text('fixture')
    state = {'state': 'complete', 'revision': revision, 'preview': {'files': [{
        'path': relative, 'sha256': module.digest(b'before'), 'bom': False,
        'after': 'after', 'diff': 'fixture diff',
    }]}}
    analysed = job / 'input' / relative
    analysed.parent.mkdir(parents=True)
    analysed.write_bytes(b'before')

    class Assistant:
        def get(self, ident): return state
        def folder(self, ident): return job
        def source(self, ident): return job / 'input'   # the analysed original source
    demo = (module.DemoGame if recipe == 'doom' else casual_demo.CasualDemo)(Assistant(), tmp_path)
    observed = []
    save = demo._save
    def record(value):
        result = save(value)
        observed.append(json.loads((tmp_path / 'demo_status.json').read_text('utf8')))
        return result
    monkeypatch.setattr(demo, '_save', record)
    build = tmp_path / '02_modified' / revision / 'build'
    if recipe == 'doom':
        original_exe = tmp_path / '01_original/build/src/Release/chocolate-doom.exe'
        original_exe.parent.mkdir(parents=True)
        original_exe.write_bytes(b'original executable')
        def fake_run(command, folder, log):
            if '--build' in command:
                exe = build / 'src/Release/chocolate-doom.exe'
                exe.parent.mkdir(parents=True)
                exe.write_bytes(b'fixture executable')
        monkeypatch.setattr(demo, '_run', fake_run)
    else:
        library = tmp_path / 'dependencies/SDL2-2.32.10/lib/x64/SDL2.dll'
        library.parent.mkdir(parents=True)
        library.write_bytes(b'fixture library')
        class FakeBuild:
            returncode = 0
            def __init__(self, *args, **kwargs):
                (build / 'opentyrian.exe').write_bytes(b'fixture executable')
            def wait(self, timeout): return 0
        monkeypatch.setattr(casual_demo.subprocess, 'Popen', FakeBuild)
    demo._build('registered', state)
    assert observed[-1]['state'] == 'complete', observed[-1]
    stages = [item['progress']['stage'] for item in observed]
    assert stages[0] == 'copy'
    assert stages[-1] == 'complete'
    assert list(dict.fromkeys(stages)) == ['copy', 'validate', 'build', 'package', 'complete']
    assert all(item['started_at'] == observed[0]['started_at'] for item in observed)
    assert observed[-1]['progress']['step'] == observed[-1]['progress']['total'] == 4
    assert observed[-1]['progress']['indeterminate'] is False


def test_demo_failed_validation_preserves_time_and_completed_stage(tmp_path):
    from game_si.web.demo import DemoGame
    demo = DemoGame(None, tmp_path)
    demo._build('registered', {'revision': 'a' * 32})
    state = json.loads((tmp_path / 'demo_status.json').read_text('utf8'))
    assert state['state'] == 'failed'
    assert state['started_at']
    assert state['progress']['stage'] == 'failed'
    assert state['progress']['indeterminate'] is False


def test_demo_progress_preserves_one_run_time_but_resets_for_retry(tmp_path, monkeypatch):
    from game_si.web import demo as module
    times = iter(['first-run', 'retry-run'])
    class Clock:
        @staticmethod
        def now(zone):
            class Time:
                def isoformat(self): return next(times)
            return Time()
    monkeypatch.setattr(module, 'datetime', Clock)
    demo = module.DemoGame(None, tmp_path)
    revision = 'a' * 32
    demo._save({'state': 'running', 'revision': revision,
                'progress': demo._progress('validate', '원본 확인 중', 1)})
    failed = demo._save({'state': 'failed', 'revision': revision, 'error': 'fixture error'})
    assert failed['started_at'] == 'first-run'
    assert failed['progress']['stage'] == 'failed'
    assert failed['progress']['step'] == 1
    retry = demo._save({'state': 'running', 'revision': revision,
                       'progress': demo._progress('copy', '원본 복사 중', 0)})
    assert retry['started_at'] == 'retry-run'


def test_interrupted_demo_stops_indeterminate_progress_without_rewriting_status(tmp_path):
    from game_si.web.demo import DemoGame
    class Assistant:
        def get(self, ident): return {'state': 'complete', 'revision': 'a' * 32}
    (tmp_path / 'demo_job.json').write_text(json.dumps({'id': 'registered'}))
    demo = DemoGame(Assistant(), tmp_path)
    saved = demo._save({'state': 'running', 'revision': 'a' * 32,
                        'progress': demo._progress('build', '빌드 중', 2)})
    state = demo.get('registered')
    assert state['state'] == 'interrupted'
    assert state['started_at'] == saved['started_at']
    assert state['progress']['stage'] == 'interrupted'
    assert state['progress']['indeterminate'] is False
    assert json.loads((tmp_path / 'demo_status.json').read_text('utf8')) == saved
