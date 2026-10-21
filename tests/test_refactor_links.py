"""Link-type refactors: declaration-only target edits, include-only companion edits, declaration-only new headers."""
import copy
import json

import pytest

pytest.importorskip('tree_sitter_c')
from game_si.web import assistant
from game_si.web.assistant_context import build_prompt, validate_edit_context, validate_preview_targets

A_H = '#ifndef A_H\n#define A_H\n\ntypedef unsigned char JE_byte;\n#define MIN(a, b) ((a) < (b) ? (a) : (b))\n\nvoid setupMenu(void);\n\n#endif\n'
A_C = '#include "a.h"\n\nvoid setupMenu(void)\n{\n\tJE_byte x = 1;\n\t(void)x;\n}\n'
B_C = '#include "a.h"\n#include <stdio.h>\n\nint b_value(void)\n{\n\tJE_byte y = MIN(1, 2);\n\treturn y;\n}\n'
C_C = '#include "a.h"\n\nint c_value(void)\n{\n\treturn MIN(3, 4);\n}\n'
TYPES = '#ifndef TYPES_H\n#define TYPES_H\n\ntypedef unsigned char JE_byte;\n#define MIN(a, b) ((a) < (b) ? (a) : (b))\n\n#endif\n'
METHODS = [{'fqn': 'a.setupMenu', 'class_fqn': 'a', 'name': 'setupMenu', 'file_path': 'a.c', 'start_line': 3, 'end_line': 7, 'cc': 1, 'loc': 5}]


@pytest.fixture
def root(tmp_path):
    for name, text in {'a.h': A_H, 'a.c': A_C, 'b.c': B_C, 'c.c': C_C}.items():
        (tmp_path / name).write_text(text, encoding='utf8')
    return tmp_path


def review(path, decision, change_type, targets=()):
    return {'path': path, 'role': '역할입니다.', 'finding': '문제입니다.', 'reason': '이유입니다.', 'change': '공용 자료형을 types.h로 옮깁니다.',
            'expected_effect': '연결이 줄어듭니다.', 'impact': '영향입니다.', 'decision': decision, 'change_type': change_type,
            'targets': list(targets), 'evidence': ['근거입니다.'], 'checks': ['빌드를 확인합니다.']}


def advice():
    return {'overview': {k: '요약입니다.' for k in ['title', 'problem', 'reason', 'change', 'expected_effect']},
            'reasons': ['근거입니다.'], 'suggestions': ['방향입니다.'], 'tests': ['빌드합니다.'], 'uncertainty': '',
            'relationships': [],
            'file_reviews': [review('a.c', 'keep', 'functions'), review('a.h', 'refactor', 'declarations')],
            'companions': [{'path': 'b.c', 'reason': '자료형만 씁니다.'}, {'path': 'c.c', 'reason': '매크로만 씁니다.'}],
            'creates': [{'path': 'types.h', 'content': TYPES, 'reason': '공용 자료형 헤더입니다.'}],
            'edits': [
                {'path': 'a.h', 'old': 'typedef unsigned char JE_byte;\n#define MIN(a, b) ((a) < (b) ? (a) : (b))\n', 'new': '#include "types.h"\n'},
                {'path': 'b.c', 'old': '#include "a.h"\n', 'new': '#include "types.h"\n'},
                {'path': 'c.c', 'old': '#include "a.h"\n', 'new': '#include "types.h"\n'}]}


def companions(root):
    return assistant.companion_excerpts(root, ['b.c', 'c.c'])


def preview(root, data):
    assistant.validate_scope(data, ['a.c', 'a.h'], preview=True, companions={'b.c', 'c.c'})
    result = assistant.preview_changes(root, data['edits'], data['creates'])
    validate_preview_targets(data, METHODS, result, companions={'b.c', 'c.c'})
    return result


def test_link_refactor_is_accepted_and_applied(root, tmp_path_factory):
    result = preview(root, advice())
    by = {f['path']: f for f in result['files']}
    assert by['types.h']['created'] is True and by['types.h']['before'] == ''
    assert by['b.c']['role'] == 'companion' and by['a.h']['role'] == 'target'
    out = tmp_path_factory.mktemp('copy') / 'src'
    assistant.apply_changes(root, out, result, {})
    assert (out / 'types.h').read_text('utf8') == TYPES and '#include "types.h"' in (out / 'b.c').read_text('utf8')
    assert (root / 'b.c').read_text('utf8') == B_C and not (root / 'types.h').exists()


def test_prompt_offers_companion_include_excerpts_and_checks_context(root):
    excerpts = companions(root)
    assert excerpts['b.c']['content'].replace('\r\n', '\n') == '#include "a.h"\n#include <stdio.h>\n'
    assert excerpts['b.c']['ranges'][0] == {'start_line': 1, 'end_line': 2, 'partial': True}
    sources = {p: (root / p).read_bytes() for p in ['a.c', 'a.h']}
    prompt, _ = build_prompt('변경안 단계', [{'fqn': 'a', 'file_path': 'a.c'}], sources, METHODS, None, companions=excerpts)
    assert [c['path'] for c in json.loads(prompt)['companions_available']] == ['b.c', 'c.c']
    validate_edit_context(prompt, advice()['edits'])
    bad = advice()['edits'] + [{'path': 'b.c', 'old': 'return y;', 'new': 'return 0;'}]
    with pytest.raises(ValueError):
        validate_edit_context(prompt, bad)


@pytest.mark.parametrize('mutate, message', [
    (lambda d: d['edits'].append({'path': 'b.c', 'old': '\treturn y;', 'new': '\treturn 0;'}), '#include'),
    (lambda d: d['companions'].append({'path': 'z.c', 'reason': '이유입니다.'}), '함께 수정'),
    (lambda d: d['edits'].pop(2), '함께 수정'),
    (lambda d: d['creates'][0].update(content=TYPES + 'int f(void){return 1;}\n'), '선언'),
    (lambda d: d['creates'][0].update(path='a.h'), '이미'),
    (lambda d: d['creates'][0].update(path='../x.h'), '경로'),
    (lambda d: d['creates'][0].update(path='types.c'), '헤더'),
    (lambda d: [e.update(new='#include "a2.h"\n') for e in d['edits'][1:]] and d['edits'][0].update(new=''), '사용'),
    (lambda d: d['edits'].append({'path': 'a.h', 'old': 'void setupMenu(void);', 'new': 'void setupMenu(int);'}) or d['edits'].append(
        {'path': 'a.c', 'old': '\tJE_byte x = 1;', 'new': '\tJE_byte x = 2;'}), '일치'),
])
def test_unsafe_link_refactors_are_rejected(root, mutate, message):
    data = advice()
    mutate(data)
    with pytest.raises(ValueError, match=message):
        preview(root, data)


def test_declarations_change_may_not_touch_function_bodies(root):
    data = advice()
    data['file_reviews'][0] = review('a.c', 'refactor', 'declarations')
    data['edits'].append({'path': 'a.c', 'old': '\tJE_byte x = 1;', 'new': '\tJE_byte x = 2;'})
    with pytest.raises(ValueError, match='함수 본문'):
        preview(root, data)


def test_functions_path_still_requires_targets(root):
    data = advice()
    data['file_reviews'][0] = review('a.c', 'refactor', 'functions', [])
    with pytest.raises(ValueError):
        assistant.validate_scope(data, ['a.c', 'a.h'], preview=True, companions={'b.c', 'c.c'})


def test_assistant_job_offers_companions_and_applies_link_refactor(tmp_path, monkeypatch):
    pytest.importorskip('fastapi')
    import time
    from fastapi.testclient import TestClient
    from game_si.web.app import create_app
    captured = {}

    def fake(service, mode, prompt, model='', api_key='', **kw):
        captured['prompt'] = json.loads(prompt)
        return copy.deepcopy(advice())
    monkeypatch.setattr(assistant, 'call_provider', fake)
    with TestClient(create_app(tmp_path / 'jobs'), base_url='http://127.0.0.1:8765') as client:
        h = {'X-Game-SI-Token': client.get('/api/session').json()['token'], 'Origin': 'http://127.0.0.1:8765'}
        files = {'g/a.h': A_H, 'g/a.c': A_C, 'g/b.c': B_C, 'g/c.c': C_C}
        job = client.post('/api/import/files', headers=h, data={'paths': json.dumps(list(files)), 'name': 'link'},
                          files=[('files', (p.split('/')[-1], t.encode(), 'application/octet-stream')) for p, t in files.items()]).json()
        manager = client.app.state.manager
        manager.update(job['id'], options={'subdir': 'g'})
        result = manager.directory(job['id']) / 'result'
        result.mkdir()
        raw = {'cc': 1, 'coupling': 1, 'dependency_cycle': 0, 'global_state': 0, 'game_loop_centrality': 0}
        metrics = {'classes': [{'fqn': n, 'name': n, 'file_path': f'{n}.c', 'out_neighbors': [] if n == 'a' else ['a'],
                                'in_neighbors': ['b', 'c'] if n == 'a' else [], 'global_state': 0} for n in 'abc'],
                   'methods': METHODS, 'cycles': []}
        scoring = {'class_scores': [dict(fqn=n, name=n, file_path=f'{n}.c', loc=5, si=s, grade='C', raw=raw) for n, s in [('a', 90.0), ('b', 50.0), ('c', 10.0)]],
                   'grade_distribution': {'C': 3}, 'analysis_status': {'state': 'complete', 'language': 'c'}}
        (result / 'metrics.json').write_text(json.dumps(metrics))
        (result / 'scoring.json').write_text(json.dumps(scoring))
        manager.update(job['id'], state='complete')
        body = {'action': 'preview', 'candidates': ['a'], 'service': 'claude', 'mode': 'cli', 'direct': True}
        assert client.post(f"/api/jobs/{job['id']}/assistant", headers=h, json=body).status_code == 202
        for _ in range(100):
            state = client.get(f"/api/jobs/{job['id']}/assistant").json()
            if state['state'] != 'running':
                break
            time.sleep(0.05)
        assert state['state'] == 'complete', state.get('error')
        assert [s['path'] for s in captured['prompt']['sources']] == ['a.c', 'a.h']
        assert [c['path'] for c in captured['prompt']['companions_available']] == ['b.c', 'c.c']
        roles = {f['path']: f['role'] for f in state['preview']['files']}
        assert roles == {'a.h': 'target', 'b.c': 'companion', 'c.c': 'companion', 'types.h': 'created'}
        assert state['target_paths'] == ['a.c', 'a.h'] and state['plan_source'] == 'direct'
        assert client.post(f"/api/jobs/{job['id']}/assistant/apply", headers=h, json={'preview_id': state['preview_id']}).status_code == 202
        for _ in range(600):
            state = client.get(f"/api/jobs/{job['id']}/assistant").json()
            if state['state'] != 'running':
                break
            time.sleep(0.1)
        assert state['state'] == 'complete', state.get('error')
        copy_root = manager.directory(job['id']) / 'revisions' / state['revision'] / 'source'
        assert (copy_root / 'types.h').is_file() and '#include "types.h"' in (copy_root / 'b.c').read_text('utf8')
        assert (manager.directory(job['id']) / 'input/g/b.c').read_text('utf8').replace('\r\n', '\n') == B_C
