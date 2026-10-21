"""Regression tests for the independent review of the web redesign (2026-10-20)."""
import copy
import json
import threading
import time

import pytest

from game_si.web import assistant, prescription
from game_si.web.change_rules import companion_ok, declaration_moves, logical_lines

pytest.importorskip('tree_sitter_c')
import test_refactor_links as T  # noqa: E402  (shared fixtures of the link-refactor tests)
from game_si.web.assistant_context import validate_preview_targets  # noqa: E402


def make_root(tmp_path, files=None):
    for name, text in (files or {'a.h': T.A_H, 'a.c': T.A_C, 'b.c': T.B_C, 'c.c': T.C_C}).items():
        (tmp_path / name).write_text(text, encoding='utf8', newline='')
    return tmp_path


def check(root, data, methods=T.METHODS, companions=frozenset({'b.c', 'c.c'})):
    assistant.validate_scope(data, ['a.c', 'a.h'], preview=True, companions=set(companions))
    result = assistant.preview_changes(root, data['edits'], data['creates'])
    validate_preview_targets(data, methods, result, companions=set(companions))
    return result


def functions_target_with_companion():
    d = T.advice()
    d['file_reviews'][0] = T.review('a.c', 'refactor', 'functions', ['setupMenu'])
    d['file_reviews'][1] = T.review('a.h', 'keep', 'declarations')
    d['creates'] = []
    d['companions'] = [{'path': 'b.c', 'reason': '이유입니다.'}]
    d['edits'] = [{'path': 'a.c', 'old': '\tJE_byte x = 1;', 'new': '\tJE_byte x = 2;'},
                  {'path': 'b.c', 'old': '#include <stdio.h>\n', 'new': '#include <string.h>\n'}]
    return d


# --- change rules ----------------------------------------------------------------------------

def test_companion_is_recognised_whatever_the_edit_order(tmp_path):
    root = make_root(tmp_path)
    d = functions_target_with_companion()
    roles = {f['path']: f['role'] for f in check(root, d)['files']}
    d['edits'].reverse()
    assert roles == {f['path']: f['role'] for f in check(root, d)['files']} == {'a.c': 'target', 'b.c': 'companion'}


def test_declarations_compare_every_definition_even_with_the_same_signature(tmp_path):
    header = ('#ifndef A_H\n#define A_H\ntypedef unsigned char JE_byte;\n'
              '#ifdef _WIN32\nstatic inline int plat(void) { return 1; }\n#else\nstatic inline int plat(void) { return 2; }\n#endif\n#endif\n')
    root = make_root(tmp_path, {'a.h': header, 'a.c': T.A_C, 'b.c': T.B_C, 'c.c': T.C_C})
    d = T.advice()
    d['creates'], d['companions'] = [], []
    d['edits'] = [{'path': 'a.h', 'old': '{ return 1; }', 'new': '{ system("calc"); return 1; }'}]
    with pytest.raises(ValueError, match='함수 본문'):
        check(root, d)


def test_control_characters_that_join_lines_are_rejected(tmp_path):
    source = '#include "a.h"\n// keep stdio for printf\n#include <stdio.h>\n\nint b_value(void)\n{\n\treturn MIN(1, 2);\n}\n'
    root = make_root(tmp_path, {'a.h': T.A_H, 'a.c': T.A_C, 'b.c': source, 'c.c': T.C_C})
    d = T.advice()
    d['creates'] = []
    d['companions'] = [{'path': 'b.c', 'reason': '이유입니다.'}]
    d['edits'] = [{'path': 'b.c', 'old': '// keep stdio for printf\n#include <stdio.h>', 'new': '// keep stdio for printf\x0c#include <stdio.h>'}]
    with pytest.raises(ValueError, match='제어 문자'):
        assistant.preview_changes(root, d['edits'], [])
    assert companion_ok('#include <a.h>\n', '#include <a.h>\n#include <b.h>\n')
    assert not companion_ok('// x\n#include <a.h>\n', '// x \\\n#include <a.h>\n')   # continuation joins the include into the comment


@pytest.mark.parametrize('content', [
    T.TYPES.replace('#endif', '#define MIN(a, b) ((a) > (b) ? (a) : (b))\n#endif'),   # behaviour-changing macro
    T.TYPES.replace('#endif', '#define return exit(0); return\n#endif'),
    T.TYPES.replace('#endif', 'static int lives = 99;\n#endif'),
])
def test_new_headers_may_only_hold_moved_declarations(tmp_path, content):
    root = make_root(tmp_path)
    d = T.advice()
    d['creates'][0]['content'] = content
    with pytest.raises(ValueError, match='옮기기만'):
        check(root, d)


def test_lambda_initializer_in_new_cpp_header_is_rejected(tmp_path):
    root = make_root(tmp_path)
    d = T.advice()
    d['creates'][0] = {'path': 'types.hpp', 'reason': '공용 선언입니다.',
                       'content': '#pragma once\ntypedef unsigned char JE_byte;\n#define MIN(a, b) ((a) < (b) ? (a) : (b))\n'
                                  'static int boot = [](){ system("calc"); return 0; }();\n'}
    for edit in d['edits']:
        edit['new'] = edit['new'].replace('types.h', 'types.hpp')
    with pytest.raises(ValueError):
        check(root, d)


def test_declarations_in_a_source_file_cannot_change_initializers(tmp_path):
    source = '#include "a.h"\n\nstatic int lives = 3;\n\nvoid setupMenu(void)\n{\n\tJE_byte x = lives;\n\t(void)x;\n}\n'
    root = make_root(tmp_path, {'a.h': T.A_H, 'a.c': source, 'b.c': T.B_C, 'c.c': T.C_C})
    d = T.advice()
    d['creates'], d['companions'] = [], []
    d['file_reviews'][0] = T.review('a.c', 'refactor', 'declarations')
    d['file_reviews'][1] = T.review('a.h', 'keep', 'declarations')
    d['edits'] = [{'path': 'a.c', 'old': 'static int lives = 3;', 'new': 'static int lives = 99;'}]
    with pytest.raises(ValueError, match='옮기기만'):
        check(root, d, methods=[dict(T.METHODS[0], start_line=5, end_line=9)])


def test_dropped_declarations_must_reappear_elsewhere(tmp_path):
    root = make_root(tmp_path)
    d = T.advice()
    d['creates'][0]['content'] = T.TYPES.replace('#define MIN(a, b) ((a) < (b) ? (a) : (b))\n', '')
    with pytest.raises(ValueError, match='옮겨지지 않은'):
        check(root, d)


def test_unchanged_paired_header_may_be_left_out_of_the_reviews(tmp_path):
    root = make_root(tmp_path)
    d = functions_target_with_companion()
    d['file_reviews'] = [d['file_reviews'][0]]           # only a.c explained; a.h (sent as context) unchanged
    check(root, d)
    assert [r['path'] for r in d['file_reviews']] == ['a.c', 'a.h'] and d['file_reviews'][1]['decision'] == 'keep'
    d = T.advice()
    d['file_reviews'] = [d['file_reviews'][0]]           # a.h is edited, so its explanation is required
    with pytest.raises(ValueError, match='바뀌는 파일은 모두'):
        check(root, d)


def test_removing_a_duplicate_kept_in_the_shared_header_is_allowed():
    keys = '#define K_TAB 9\n#define K_ENTER 13\nvoid Key_Event(int key);\n'
    menu = '#define K_TAB 9\n#define K_ENTER 13\nvoid Menu_Draw(void);\n'   # copied constants, as in Quake 2
    shared = '#ifndef KEYCODES_H\n#define KEYCODES_H\n#define K_TAB 9\n#define K_ENTER 13\n#endif\n'
    items = [('keys.h', keys, '#include "keycodes.h"\nvoid Key_Event(int key);\n', False),
             ('qmenu.h', menu, '#include "keycodes.h"\nvoid Menu_Draw(void);\n', False),
             ('keycodes.h', '', shared, True)]
    assert declaration_moves(items) is None
    items[2] = ('keycodes.h', '', shared.replace('#define K_ENTER 13\n', ''), True)   # K_ENTER now defined nowhere
    assert '옮겨지지 않은' in declaration_moves(items)


def test_moved_declarations_may_be_re_spaced(tmp_path):
    root = make_root(tmp_path)
    d = T.advice()
    d['creates'][0]['content'] = T.TYPES.replace('typedef unsigned char JE_byte;', 'typedef  unsigned char\tJE_byte;   /* bytes */')
    assert {f['path'] for f in check(root, d)['files']} >= {'types.h', 'a.h'}


def test_include_inside_a_comment_does_not_count(tmp_path):
    root = make_root(tmp_path)
    d = T.advice()
    d['companions'] = []
    d['edits'] = [{'path': 'a.h', 'old': T.advice()['edits'][0]['old'], 'new': '/* #include "types.h" */\n'}]
    with pytest.raises(ValueError, match='#include로 사용하는 변경이 없습니다'):
        check(root, d)


def test_new_header_cannot_shadow_an_existing_include(tmp_path):
    source = '#include "a.h"\n#include "SDL.h"\n\nint b_value(void)\n{\n\treturn 1;\n}\n'
    root = make_root(tmp_path, {'a.h': T.A_H, 'a.c': T.A_C, 'b.c': source, 'c.c': T.C_C})
    with pytest.raises(ValueError, match='겹칩니다'):
        assistant.preview_changes(root, [{'path': 'c.c', 'old': '#include "a.h"\n', 'new': '#include "a.h"\n#include "SDL.h"\n'}],
                                  [{'path': 'SDL.h', 'content': '#pragma once\ntypedef int SDL_bool;\n', 'reason': '공용 선언입니다.'}])
    # A path that only shares the base name with a system header is fine: <sys/types.h> is not "types.h".
    (root / 'c.c').write_text('#include <sys/types.h>\n' + T.C_C, encoding='utf8')
    assert check(root, T.advice())


def test_case_variant_new_files_and_csharp_aliases_are_rejected(tmp_path):
    root = make_root(tmp_path)
    twice = [{'path': 'types.h', 'content': T.TYPES, 'reason': '이유입니다.'}, {'path': 'TYPES.h', 'content': T.TYPES, 'reason': '이유입니다.'}]
    with pytest.raises(ValueError, match='한 번만'):
        assistant.preview_changes(root, T.advice()['edits'], twice)
    assert not assistant.INCLUDE_LINE.match('using Console = OpenRA.Evil;')
    assert assistant.INCLUDE_LINE.match('using OpenRA.Traits;')


def test_logical_lines_follow_the_compiler():
    text = 'a; // c \\\nhidden;\n/* x\n y */ b;\nchar *s = "/* not a comment */";\n'
    assert logical_lines(text) == ['a;', 'b;', 'char *s = "/* not a comment */";']
    assert declaration_moves([('x.cs', 'a', 'b', False)]).startswith('x.cs')


# --- prescription ------------------------------------------------------------------------------

@pytest.mark.parametrize('text', ['모두 다 바뀝니다.', '그러다 보면 고리가 줄어듭니다.', '바다 같은 함수입니다.',
                                  'opentyr.h를 나눕니다.', '3.5배 줄어듭니다.', '정리합니다 (예: types.h).', '두 문장입니다. 둘째도 그렇습니다'])
def test_polite_sentences_are_accepted(text):
    prescription._polite('reason', text, 300)


@pytest.mark.parametrize('text', ['좋아요. 그래서 정리합니다.', '좋다.그래서 정리합니다.', '좋음. 정리합니다.', '정리한다.'])
def test_every_sentence_must_be_polite(text):
    with pytest.raises(ValueError):
        prescription._polite('reason', text, 300)


def test_removing_a_cycle_member_is_not_counted_as_untangling():
    names = 'abcd'
    graph = {'nodes': [{'id': n} for n in names], 'edges': [[a, b] for a in names for b in names if a != b]}
    eff = prescription.effects([{'name': 'a', 'kind': 'link'}], graph)
    assert (eff['base'], eff['steps'][0]['after'], eff['steps'][0]['reduced']) == (4, 3, False)
    assert prescription.headline([{'name': 'a', 'kind': 'link'}], eff, '파일', False) == '1개 파일의 연결을 정리합니다.'


def test_validate_rejects_unhashable_names():
    data = {'done': False, 'why_not_top': '', 'benefit': '좋아집니다.',
            'files': [{'name': ['a'], 'kind': 'link', 'reason': '이유입니다.', 'change_idea': '나눕니다.', 'expected': '줄어듭니다.'}]}
    with pytest.raises(ValueError):
        prescription.validate(data, {'a'})


def test_prescription_shares_the_job_lock_and_retries_non_json(tmp_path, monkeypatch):
    from test_prescription import FakeJobs, good, wait
    jobs = FakeJobs(tmp_path)
    service = prescription.Prescriptions(jobs)
    assert service.lock is jobs.lock
    replies = [json.JSONDecodeError('Expecting value', '', 0), good()]

    def fake(*args, **kwargs):
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply
    monkeypatch.setattr(prescription.assistant, 'call_provider', fake)
    service.start('c' * 32, {'service': 'claude', 'mode': 'cli'})
    state = wait(service, 'c' * 32)
    assert state['state'] == 'complete' and not replies


def test_context_tells_what_earlier_rounds_changed():
    from test_prescription import diag
    text, _ = prescription.build_context(diag(), None, [{'round': 1, 'files': ['a.h']}], {'links': 5})
    payload = json.loads(text)
    assert payload['already_changed'] == [{'round': 1, 'files': ['a.h']}] and payload['tangle'] == {'links': 5}
    assert payload['largest_cycle']


# --- rounds ------------------------------------------------------------------------------------

def make_job(tmp_path):
    from game_si.web.app import create_app
    app = create_app(tmp_path)
    manager = app.state.manager
    ident = manager.create('라운드 게임', 'folder')['id']
    (manager.directory(ident) / 'input' / 'main.c').write_text('int Tick(void) { return 0; }\n', encoding='utf8')
    result = manager.directory(ident) / 'result'
    result.mkdir()
    (result / 'scoring.json').write_text(json.dumps({'class_scores': [{'fqn': 'main', 'name': 'main', 'file_path': 'main.c', 'si': 100,
        'grade': 'E', 'loc': 1, 'raw': {'cc': 1, 'coupling': 0, 'dependency_cycle': 0, 'global_state': 0, 'game_loop_centrality': 0}}],
        'analysis_status': {'state': 'complete', 'language': 'c'}}), encoding='utf8')
    (result / 'metrics.json').write_text(json.dumps({'classes': [{'fqn': 'main', 'name': 'main', 'file_path': 'main.c', 'out_neighbors': [], 'in_neighbors': []}],
        'methods': [dict(file_path='main.c', class_fqn='main', name='Tick', fqn='main.Tick', start_line=1, end_line=1, cc=1, loc=1)]}), encoding='utf8')
    manager.update(ident, state='complete', options={'lang': 'c', 'subdir': '.'})
    return app, ident


def test_old_job_keeps_its_applied_revision_as_round_one(tmp_path):
    app, ident = make_job(tmp_path)
    folder = app.state.manager.directory(ident)
    revision = 'e' * 32
    (folder / 'revisions' / revision / 'source').mkdir(parents=True)
    (folder / 'revisions' / revision / 'source' / 'main.c').write_text('int Tick(void) { return 1; }\n', encoding='utf8')
    (folder / 'revisions' / revision / 'result').mkdir()
    for name in ['scoring.json', 'metrics.json']:
        (folder / 'revisions' / revision / 'result' / name).write_text((folder / 'result' / name).read_text('utf8'), encoding='utf8')
    (folder / 'revisions' / revision / 'modified-source.zip').write_bytes(b'zip')
    (folder / 'assistant.json').write_text(json.dumps({'state': 'complete', 'action': 'advice'}), encoding='utf8')   # revision key lost
    jobs = app.state.assistant
    data = jobs.rounds(ident)
    assert data['current'] == 1 and data['rounds'][0]['revision'] == revision and data['rounds'][0]['files'] == ['main.c']
    assert (folder / 'rounds.json').is_file() and (folder / 'revisions' / revision / 'manifest.json').is_file()
    jobs.verify_revision(ident, revision)
    (folder / 'revisions' / revision / 'source' / 'main.c').write_text('int Tick(void) { return 9; }\n', encoding='utf8')
    with pytest.raises(ValueError, match='수정본 소스가 바뀌어'):
        jobs.verify_revision(ident, revision)


def test_preview_from_an_undone_round_cannot_be_applied(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import re
    from test_rounds import provider as base, wait as wait_job

    def provider(service, mode, prompt, *args, **kwargs):   # each round: return n; -> return n+1;
        n = int(re.search(r'return (\d+);', prompt).group(1))
        reply = base(service, mode, 'return 1;', *args, **kwargs)
        reply['edits'] = [dict(path='main.c', old=f'return {n};', new=f'return {n + 1};')]
        return reply
    monkeypatch.setattr(assistant, 'call_provider', provider)
    app, ident = make_job(tmp_path)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        h = {'X-Game-SI-Token': client.get('/api/session').json()['token']}
        url = f'/api/jobs/{ident}/assistant'

        def preview():
            assert client.post(url, headers=h, json=dict(action='preview', service='codex', mode='cli', candidates=['main'], direct=True)).status_code == 202
            state = wait_job(client, url)
            assert state['state'] == 'complete', state.get('error')
            return state

        def apply(state):
            return client.post(url + '/apply', headers=h, json={'preview_id': state['preview_id']})
        first = preview()
        assert apply(first).status_code == 202 and wait_job(client, url)['state'] == 'complete'
        second = preview()
        assert apply(second).status_code == 202 and wait_job(client, url)['state'] == 'complete'
        pending = preview()                       # reviewed on round 2, never applied
        client.post(f'/api/jobs/{ident}/rounds/undo', headers=h)
        assert 'preview_id' not in client.get(url).json()
        assert apply(pending).status_code == 400
        third = preview()
        assert apply(third).status_code == 202 and wait_job(client, url)['state'] == 'complete'
        rounds = client.get(f'/api/jobs/{ident}/rounds').json()
        assert rounds['current'] == 2 and [r['round'] for r in rounds['discarded']] == [2]   # undone round stays on record


def test_incomplete_analysis_answers_409_everywhere(tmp_path):
    from fastapi.testclient import TestClient
    from game_si.web.app import create_app
    app = create_app(tmp_path)
    ident = app.state.manager.create('진행 중', 'folder')['id']
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        for path in ['/diagnosis', '/tangle', '/rounds', '/prescription', '/assistant']:
            assert client.get(f'/api/jobs/{ident}{path}').status_code == 409, path
        assert client.get(f'/workspace/{ident}', follow_redirects=False).status_code == 307


def test_casual_demo_retries_recognition_after_a_failed_check(tmp_path):
    from game_si.web.casual_demo import CasualDemo
    (tmp_path / '01_original/source/src').mkdir(parents=True)
    (tmp_path / '01_original/source/src/opentyr.c').write_text('int main(void){return 0;}\n')
    source = tmp_path / 'job'
    source.mkdir()
    (source / 'opentyr.c').write_text('int main(void){return 0;}\n')

    class Assistant:
        ready = False
        def get(self, ident): return {'state': 'idle'}
        def source(self, ident):
            if not self.ready:
                raise ValueError('정적 분석을 먼저 완료해 주세요.')
            return source
    helper = Assistant()
    demo = CasualDemo(helper, tmp_path)
    assert not demo.registered('job')
    helper.ready = True
    assert demo.registered('job')


def test_one_lock_means_no_deadlock_between_refactor_and_prescription(tmp_path):
    app, ident = make_job(tmp_path)
    jobs, prescriptions = app.state.assistant, app.state.prescriptions
    assert prescriptions.lock is jobs.lock
    done = []
    workers = [threading.Thread(target=lambda: done.append(prescriptions.busy(ident))),
               threading.Thread(target=lambda: done.append(jobs.get(ident)['state']))]
    with jobs.lock:   # holding the shared lock in another thread must not block forever once released
        for w in workers:
            w.start()
        time.sleep(0.05)
    for w in workers:
        w.join(timeout=5)
    assert len(done) == 2
