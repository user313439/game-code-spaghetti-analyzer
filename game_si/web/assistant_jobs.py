"""Independent advice/preview tasks; source edits create isolated revisions."""
from __future__ import annotations

from copy import deepcopy
import difflib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import shutil
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from statistics import median

from . import assistant, clang_presets, diagnosis
from .inputs import target_path
from .jobs import BusyError, REPO_ROOT, write_json
from .assistant_context import (_ast_functions, _inserted_helpers, build_deep_prompt, build_prompt, measure_functions,
                                validate_edit_context, validate_target_methods, validate_preview_targets)
from .assistant_reviews import AssistantReviews

DEEP_PARALLEL = 5            # files worked on at once (each is one AI program); five is the most a change takes
DEEP_DEADLINE = 25 * 60      # files not started by then are skipped and can be retried
DEEP_FINAL = {'done', 'no_changes', 'failed', 'skipped', 'cancelled'}
DEEP_PASSES = 3              # one file may be handed to the AI up to this many times in a row
DEEP_FILE_BUDGET = 15 * 60   # no further pass when the next one would end after this (seconds since the file started)
DEEP_CONTINUE_CC = 40        # a further pass only while a target function still branches this much
DEEP_MIN_GAIN = 5            # ... and only after a pass that took away at least this many branches (and 5%)
DEEP_WORTH_CC = 15           # a file whose target functions all branch less than this is not sent at all


def merge_deep_passes(data, step, path):
    """The reply of a later pass added to what the earlier passes said: the file's targets, change and
    evidence together (the whole change is checked against them), the summary lines one after another."""
    merged = deepcopy(data)
    row = next(r for r in merged['file_reviews'] if r['path'] == path)
    new = next((r for r in step['file_reviews'] if r['path'] == path), None)
    if new is not None:
        row['targets'] = list(dict.fromkeys(row['targets'] + new['targets']))
        row['change'] = row['change'] + '\n' + new['change']
        row['evidence'] = row['evidence'] + new['evidence']
    merged['overview']['change'] += '\n' + step['overview']['change']
    merged['uncertainty'] = '\n'.join(filter(None, [merged.get('uncertainty', ''), step.get('uncertainty', '')]))
    merged['edits'] = merged.get('edits', []) + step.get('edits', [])
    return merged


def merge_deep_advice(results, title, previous=None):
    """One summary for files done separately: every line names its file. Built by the program (no
    extra AI call); `previous` is the summary of an earlier pass that a retry adds to."""
    previous = previous or {}
    overview = {'title': title}
    for key in ['problem', 'reason', 'change', 'expected_effect']:
        parts = [previous['overview'][key]] if previous.get('overview', {}).get(key) else []
        parts += [f"[{Path(o['unit']['file_path']).name}] {o['data']['overview'][key]}" for o in results]
        overview[key] = '\n'.join(parts)
    reviews, seen = [], set()
    for row in list(previous.get('file_reviews', [])) + [r for o in results for r in o['data']['file_reviews']]:
        if row['path'] not in seen:
            seen.add(row['path'])
            reviews.append(row)
    pick = lambda key: list(previous.get(key, [])) + [x for o in results for x in o['data'].get(key, [])]
    return {'overview': overview, 'file_reviews': reviews, 'relationships': pick('relationships'),
            'reasons': pick('reasons'), 'suggestions': pick('suggestions'), 'tests': pick('tests'),
            'uncertainty': '\n'.join(filter(None, [previous.get('uncertainty', '')] + [o['data'].get('uncertainty', '') for o in results])),
            'edits': pick('edits'), 'companions': [], 'creates': [], 'mode': 'deep'}


class AssistantJobs:
    def __init__(self, manager):
        self.manager = manager
        self.lock = threading.RLock()
        self.states = {}
        self.threads = []
        self.reviews = AssistantReviews(self)
        self._worker = threading.local()   # run id of the task this worker thread is doing

    def folder(self, ident):
        record = self.manager.get(ident)
        if record['state'] not in {'complete', 'partial'}:
            raise BusyError('정적 분석을 먼저 완료해 주세요.')   # 409, like /diagnosis and /tangle
        return self.manager.directory(ident)

    def source(self, ident):
        record = self.manager.get(ident)
        options = record.get('options', {})
        root = Path(options['local_path']).resolve() if options.get('local_path') else self.folder(ident) / 'input'
        return root if options.get('subdir', '.') == '.' else target_path(root, options['subdir'])

    # --- rounds: each applied change builds on the previous revision ------------------
    def _rounds_path(self, ident):
        return self.folder(ident) / 'rounds.json'

    def rounds(self, ident):
        path = self._rounds_path(ident)
        with self.lock:
            if path.is_file():
                return json.loads(path.read_text('utf8'))
            data = self._migrate(ident)
            try:   # written once, so later state changes cannot lose the migrated round
                self._save_rounds(ident, data)
            except OSError:
                pass
            return data

    def _migrate(self, ident):
        # Jobs from before rounds existed: their applied revision becomes round 1. assistant.json
        # may have lost the revision key (a later request replaced the state), so fall back to the
        # newest revision folder that finished applying (re-analysed and packaged).
        state = self.get(ident)
        folder = self.folder(ident) / 'revisions'
        finished = lambda rev: (folder / rev / 'result/scoring.json').is_file() and (folder / rev / 'modified-source.zip').is_file()
        revision = state.get('revision') if state.get('revision') and finished(state['revision']) else None
        if revision is None and folder.is_dir():
            done = [p for p in folder.iterdir() if p.is_dir() and re.fullmatch('[a-f0-9]{32}', p.name) and finished(p.name)]
            if done:
                revision = max(done, key=lambda p: (p / 'modified-source.zip').stat().st_mtime).name
        if revision is None:
            return {'rounds': [], 'current': 0}
        source = folder / revision / 'source'
        original, revised = self._manifest(self.source(ident)), self._manifest(source)
        files = sorted(rel for rel, fingerprint in revised.items() if original.get(rel) != fingerprint)
        if not (folder / revision / 'manifest.json').is_file():
            (folder / revision / 'manifest.json').write_text(json.dumps(revised, indent=1), encoding='utf8')
        applied = state.get('finished_at') if state.get('revision') == revision else (folder / revision / 'modified-source.zip').stat().st_mtime
        return {'rounds': [{'round': 1, 'revision': revision, 'base': None, 'applied_at': applied, 'files': files,
                            'plan_source': state.get('plan_source', 'review'), 'checks': {}, 'migrated': True}], 'current': 1}

    @staticmethod
    def _manifest(root):
        # SHA-256 of every source file in a tree: written when a round is applied, checked before a build.
        return {p.relative_to(root).as_posix(): assistant.digest(p.read_bytes())
                for p in sorted(root.rglob('*')) if p.is_file() and not p.is_symlink() and p.suffix.lower() in assistant.EXTENSIONS}

    def verify_revision(self, ident, revision):
        # The revision's source must still be exactly what was applied and re-analysed.
        folder = self.folder(ident) / 'revisions' / revision
        path = folder / 'manifest.json'
        current = self._manifest(folder / 'source')
        if not path.is_file():   # revisions applied before manifests existed: record them now
            path.write_text(json.dumps(current, indent=1), encoding='utf8')
            return
        if json.loads(path.read_text('utf8')) != current:
            raise ValueError('적용 후 수정본 소스가 바뀌어 빌드할 수 없습니다. 변경안을 다시 적용해 주세요.')

    def _save_rounds(self, ident, data):
        write_json(self._rounds_path(ident), data)

    def current_revision(self, ident):
        data = self.rounds(ident)
        return data['rounds'][data['current'] - 1]['revision'] if data['current'] else None

    def base_source(self, ident):
        revision = self.current_revision(ident)
        return self.folder(ident) / 'revisions' / revision / 'source' if revision else self.source(ident)

    def current_result(self, ident):
        revision = self.current_revision(ident)
        return self.folder(ident) / 'revisions' / revision / 'result' if revision else self.folder(ident) / 'result'

    def undo_round(self, ident):
        with self.lock:
            if self.get(ident).get('state') == 'running':
                raise BusyError('진행 중인 AI 작업을 기다려 주세요.')
            data = self.rounds(ident)
            if not data['current']:
                raise ValueError('되돌릴 수정 라운드가 없습니다.')
            data['current'] -= 1
            self._save_rounds(ident, data)
            # A preview reviewed on the undone round must not be applied on the earlier one.
            state = self.states[ident]
            if 'preview' in state or 'preview_id' in state:
                state.pop('preview', None)
                state.pop('preview_id', None)
                self._save(ident)
            return data

    def record_check(self, ident, number, key, value):
        with self.lock:
            data = self.rounds(ident)
            if not 1 <= number <= len(data['rounds']):
                raise KeyError('round')
            data['rounds'][number - 1].setdefault('checks', {})[key] = value
            self._save_rounds(ident, data)
            return data

    def round_changes(self, ident, number):
        """The code of each function a round changed, before and after (new helper functions too), as
        unified diffs. C/C++ functions are found with tree-sitter by their full declarator; their CC and
        length come from each side's own analysis of that file. Other files are shown as a whole."""
        data = self.rounds(ident)
        if not 1 <= number <= len(data['rounds']):
            raise KeyError('round')
        item = data['rounds'][number - 1]
        folder = self.folder(ident) / 'revisions'
        before_root = folder / item['base'] / 'source' if item.get('base') else self.source(ident)
        after_root = folder / item['revision'] / 'source'
        before_result = folder / item['base'] / 'result' if item.get('base') else self.folder(ident) / 'result'

        def measures(result):
            # (file, function name) -> [{cc, loc}, …] in source order, from that analysis itself.
            try:
                methods = json.loads((result / 'metrics.json').read_text('utf8')).get('methods', [])
            except (OSError, ValueError):
                return {}
            found = {}
            for m in sorted(methods, key=lambda m: m.get('start_line') or 0):
                found.setdefault((str(m.get('file_path', '')).replace('\\', '/'), m.get('name')), []).append(
                    {'cc': m.get('cc') or 0, 'loc': m.get('loc') or 0})
            return found
        measured_before, measured_after = measures(before_result), measures(folder / item['revision'] / 'result')

        def read(root, rel):
            try:
                return assistant.source_file(root, rel).read_bytes().decode('utf-8-sig', errors='replace')
            except ValueError:
                return ''

        def unified(old, new, rel):
            ends = lambda text: text if not text or text.endswith('\n') else text + '\n'   # function text has no final newline
            return ''.join(difflib.unified_diff(ends(old).splitlines(True), ends(new).splitlines(True),
                                                fromfile='원본/' + rel, tofile='수정본/' + rel, n=3))

        def functions(rel, text, measured):
            # Every definition by its full declarator (overloads stay apart), with its own measures.
            rows, seen = {}, {}
            for identity, row in _ast_functions(rel, text).items():
                if not row['name']:
                    continue
                index = seen.get(row['name'], 0)
                seen[row['name']] = index + 1
                values = measured.get((rel, row['name']), [])
                rows[identity] = {'name': row['name'], 'source': row['source'].decode('utf8', errors='replace'),
                                  'measure': values[index] if index < len(values) else None}
            return rows

        rows = []
        for rel in item.get('files', []):
            before, after = read(before_root, rel), read(after_root, rel)
            if Path(rel).suffix.lower() not in {'.c', '.h', '.cpp', '.cc', '.cxx', '.hpp', '.cs'}:
                if before != after:
                    rows.append({'file': rel, 'name': None, 'diff': unified(before, after, rel)})
                continue
            old, new = functions(rel, before, measured_before), functions(rel, after, measured_after)
            for identity in list(new) + [i for i in old if i not in new]:
                o, n = old.get(identity), new.get(identity)
                if o and n and o['source'] == n['source']:
                    continue
                rows.append({'file': rel, 'name': (n or o)['name'], 'before': o and o['measure'], 'after': n and n['measure'],
                             'created': o is None, 'removed': n is None,
                             'diff': unified(o['source'] if o else '', n['source'] if n else '', rel)})
        drop = lambda r: (r.get('before') or {}).get('cc', 0) - (r.get('after') or {}).get('cc', 0) if r.get('before') and r.get('after') else -1
        rows.sort(key=lambda r: (r.get('name') is None, r.get('created', False), -drop(r), r['file'], r.get('name') or ''))
        return {'round': number, 'functions': rows}

    def candidates(self, ident):
        data = json.loads((self.current_result(ident) / 'scoring.json').read_text('utf8'))
        rows = sorted(data.get('class_scores', []), key=lambda r: (-float(r.get('si', 0)), r.get('fqn', '')))
        output = []
        for row in rows:
            relative = str(row.get('file_path', '')).replace('\\', '/')
            try:
                assistant.source_file(self.base_source(ident), relative)
            except ValueError:
                continue
            output.append({k: row.get(k) for k in ['fqn', 'si', 'grade', 'raw', 'top_reasons']} | {'file_path': relative})
        return output

    def _save(self, ident):
        write_json(self.folder(ident) / 'assistant.json', self.states[ident])

    def _mine(self, ident):
        # False once the task was cancelled or replaced: a late worker must not overwrite the state.
        run = getattr(self._worker, 'run', None)
        return run is None or self.states.get(ident, {}).get('run_id') == run

    def _progress(self, ident, stage, label, step, total=4, indeterminate=False):
        with self.lock:
            if not self._mine(ident):
                return
            self.states[ident]['progress'] = dict(stage=stage, label=label, step=step,
                                                 total=total, indeterminate=indeterminate)
            self._save(ident)

    def cancel(self, ident):
        # Stop an AI request (proposal or change preview); applying a change cannot be cancelled.
        with self.lock:
            self.get(ident)
            state = self.states[ident]
            if state.get('state') != 'running' or state.get('action') not in {'advice', 'preview'}:
                raise ValueError('취소할 AI 요청이 없습니다.')
            run = state.pop('run_id', None)   # the running worker is no longer the owner
            step = (state.get('progress') or {}).get('step', 0)
            for row in state.get('workers', []):
                if row['state'] not in DEEP_FINAL:
                    row.update(state='cancelled', error='요청을 취소해 멈췄습니다.')
                    passes = row.get('passes') or []
                    if row.get('step', 1) > 1 and len(passes) < row['step']:   # a later pass was under way
                        row['passes'] = passes + [{'step': row['step'], 'state': 'cancelled'}]
            state.update(state='cancelled', error=None, finished_at=time.time(), message='AI 요청을 취소했습니다.',
                         progress=dict(stage='cancelled', label='취소했습니다.', step=step, total=4, indeterminate=False))
            self._save(ident)
        assistant.cancel_owner(('assistant', ident, run))
        return self.get(ident)

    def _finish(self, ident):
        state = self.states[ident]
        finished = time.time()
        history = state.setdefault('timings', {})
        key = f"{state['action']}:{state['service']}:{state['mode']}:{state.get('model', '')}:{len(state.get('candidates', [state['candidate']]))}"
        history[key] = (history.get(key, []) + [round(finished-state['started_at'], 2)])[-5:]
        state.update(state='complete', finished_at=finished,
                     progress=dict(stage='complete', label='완료했습니다.', step=4, total=4, indeterminate=False))
        self._save(ident)

    def get(self, ident):
        self.folder(ident)
        with self.lock:
            if ident not in self.states:
                path = self.folder(ident) / 'assistant.json'
                state = json.loads(path.read_text('utf8')) if path.is_file() else {'state': 'idle'}
                if state.get('state') == 'running':
                    state.update(state='interrupted', error='프로그램이 종료되어 AI 작업이 중단되었습니다.')
                self.states[ident] = state
            return deepcopy(self.states[ident])

    def start(self, ident, body):
        self.folder(ident)
        action = body.get('action')
        if action == 'review':
            return self.reviews.start(ident,body)
        if action not in {'advice', 'preview'}:
            raise ValueError('AI 요청 종류를 확인해 주세요.')
        names = body.get('candidates') or ([body['candidate']] if body.get('candidate') else [])
        if (not isinstance(names, list) or not 1 <= len(names) <= 5
                or any(not isinstance(n, str) for n in names) or len(set(names)) != len(names)):
            raise ValueError('서로 다른 검토 후보를 1개부터 5개까지 선택해 주세요.')
        available = {c['fqn']: c for c in self.candidates(ident)}
        if any(name not in available for name in names):
            raise ValueError('검토할 소스 후보를 선택해 주세요.')
        selected = [available[name] for name in sorted(names)]
        if len({c['file_path'] for c in selected}) != len(selected):
            raise ValueError('같은 파일의 후보는 하나만 선택해 주세요.')
        assistant.validate_connection(body)
        service, mode = body.get('service'), body.get('mode')
        root = self.base_source(ident)
        sources = {c['file_path']: assistant.source_file(root, c['file_path']).read_bytes() for c in selected}
        if action == 'preview':
            for c in selected:
                for header in assistant.paired_headers(root, c['file_path']):
                    sources.setdefault(header, assistant.source_file(root, header).read_bytes())
        # 'deep': each file goes to its own AI call with its functions whole (several at once);
        # without it, one joint call for all files (also used for links between files).
        deep = action == 'preview' and body.get('strategy') == 'deep'
        retry = body.get('retry_of') if deep else None
        companions = self._companions(ident, names, sources) if action == 'preview' and not deep else {}
        fingerprints = {path: assistant.digest(raw) for path, raw in sources.items()}
        first = selected[0]
        keep = None
        with self.lock:
            previous = self.get(ident)
            prescriptions = getattr(self, 'prescriptions', None)
            if previous['state'] == 'running' or self.reviews.busy(ident) or (prescriptions and prescriptions.busy(ident)):
                raise BusyError('진행 중인 AI 작업을 기다려 주세요.')
            if retry:
                # Redo some files of a deep change and add them to it: same round, same original code.
                done = {f['path'] for f in (previous.get('preview') or {}).get('files', [])}
                if (previous.get('preview_id') != retry or previous.get('state') != 'complete' or previous.get('mode_deep') is not True
                        or previous.get('base_revision') != self.current_revision(ident)
                        or any(c['file_path'] in done for c in selected)
                        or any(previous.get('source_hashes', {}).get(p, h) != h for p, h in fingerprints.items())):
                    raise ValueError('지난 변경안이 바뀌어 이 파일만 다시 만들 수 없습니다. 변경안을 처음부터 다시 만들어 주세요.')
                # The files already in the change must still be exactly what their change was made from.
                for path, fingerprint in previous.get('source_hashes', {}).items():
                    try:
                        current = assistant.digest(assistant.source_file(root, path).read_bytes())
                    except ValueError:
                        current = None
                    if current != fingerprint:
                        raise ValueError('지난 변경안을 만든 뒤 원본 코드가 바뀌어 이 파일만 다시 만들 수 없습니다. 변경안을 처음부터 다시 만들어 주세요.')
                keep = {'preview': previous.get('preview') or {'files': []}, 'change_advice': previous.get('change_advice'),
                        'workers': [w for w in previous.get('workers', []) if w['key'] not in names],
                        'source_hashes': previous.get('source_hashes', {}), 'candidates': previous.get('candidates', [])}
            prior_names = previous.get('candidates') or [previous.get('candidate')]
            prior_hashes = previous.get('source_hashes') or {previous.get('file_path'): previous.get('source_sha256')}
            advice=None
            if action == 'preview':
                if (previous.get('advice') and prior_hashes==fingerprints and set(prior_names)==set(names)
                        and previous['state'] in {'complete','failed'}
                        and (previous.get('service'),previous.get('mode'),previous.get('model',''))
                            ==(service,mode,body.get('model',''))):
                    advice=previous.get('change_advice') or previous['advice']
                else:
                    advice=self.reviews.selected_advice(ident,selected,fingerprints,service,mode,body.get('model',''))
                if body.get('use_prescription'):
                    advice=self._prescription_prior(ident, names) or advice
                if not advice and not (body.get('use_prescription') or body.get('direct')):
                    raise ValueError('현재 후보·원본·AI 연결과 일치하는 개선 제안이나 사전 검토가 필요합니다. 다시 검토해 주세요.')
            history = previous.get('timings', {})
            timing_key = f"{action}:{service}:{mode}:{body.get('model', '')}:{len(selected)}"
            samples = history.get(timing_key, [])
            # A file asked again keeps count of its tries and the reason it was turned down last time
            # (read before `state`, which is the same record, is cleared below).
            earlier = {w['key']: w for w in previous.get('workers', [])} if previous.get('action') == 'preview' else {}
            state = previous if action == 'preview' else {'timings': history}
            if advice is not None:
                state['advice']=advice
            state.update(state='running', action=action, error=None, candidate=first['fqn'],
                         candidates=sorted(names), source_hashes=fingerprints, target_paths=sorted(sources),
                         companion_candidates=sorted(companions),
                         plan_source='prescription' if body.get('use_prescription') else 'direct' if body.get('direct') else 'review',
                         service=service, mode=mode, model=body.get('model', ''),
                         file_path=first['file_path'], source_sha256=fingerprints[first['file_path']],
                         started_at=time.time(), finished_at=None, run_id=uuid.uuid4().hex,
                         estimated_seconds=round(median(samples)) if samples else None,
                         estimate_samples=len(samples),
                         progress=dict(stage='prepare', label='선택한 코드와 지표를 준비합니다.', step=0, total=4, indeterminate=False))
            for key in ['preview', 'preview_id', 'revision_url', 'download_url', 'revision',
                        'comparison', 'message', 'change_advice', 'no_changes', 'workers', 'preview_failures', 'mode_deep']:
                state.pop(key, None)
            state['base_revision'] = self.current_revision(ident)   # the round this change builds on
            if deep:
                state['mode_deep'] = True
                state['workers'] = (keep or {}).get('workers', []) + [
                    {'key': c['fqn'], 'path': c['file_path'], 'label': Path(c['file_path']).name, 'state': 'waiting',
                     'attempt': earlier.get(c['fqn'], {}).get('attempt', 1) + 1 if c['fqn'] in earlier else 1,
                     'last_error': earlier[c['fqn']].get('error') if earlier.get(c['fqn'], {}).get('state') in {'failed', 'skipped'} else None}
                    for c in selected]
                state['progress'] = dict(stage='ai', label=f'AI가 파일 {len(selected)}개를 나눠 정리하고 있습니다', step=1, total=4, indeterminate=True)
            if keep:
                state['candidates'] = sorted(set(keep['candidates']) | set(names))
                state['source_hashes'] = {**keep['source_hashes'], **fingerprints}
            self.states[ident] = state
            self._save(ident)
        # Credentials remain only in this worker's memory; never in task records/logs.
        worker = threading.Thread(target=self._generate_deep if deep else self._generate,
                                  args=(ident, dict(body), selected, sources, advice, keep if deep else companions, state['run_id']),
                                  daemon=True)
        self.threads.append(worker)
        worker.start()
        return self.get(ident)

    def _companions(self, ident, names, sources):
        """Files of units that use a selected unit: they may need their #include/using lines updated."""
        try:
            units = diagnosis.load(self.current_result(ident))['units']
        except (OSError, ValueError, KeyError):
            return {}
        wanted = set(names)
        paths = []
        for unit in units:
            path = str(unit.get('file', '')).replace('\\', '/')
            if wanted & set(unit.get('calls', [])) and path and path not in sources and path not in paths:
                paths.append(path)
        return assistant.companion_excerpts(self.base_source(ident), paths[:60])

    def _prescription_prior(self, ident, names):
        prescriptions = getattr(self, 'prescriptions', None)
        state = prescriptions.get(ident) if prescriptions else {}
        result = state.get('result')
        if not result or state.get('stale') or result.get('done'):
            return None
        files = {u['fqn']: u.get('file', '') for u in diagnosis.load(self.current_result(ident))['units']}
        rows = [f for f in result['files'] if f['name'] in set(names)]
        if not rows:
            return None
        return {'overview': {'title': result['headline'], 'problem': rows[0]['reason'], 'reason': result.get('benefit', ''),
                             'change': ' '.join(f['change_idea'] for f in rows), 'expected_effect': result.get('benefit', '')},
                'file_reviews': [{'path': files.get(f['name'], f['name']), 'finding': f['reason'], 'change': f['change_idea'],
                                  'expected_effect': f['expected'], 'decision': '연결 정리' if f['kind'] == 'link' else '파일 안 정리',
                                  'targets': f.get('targets', [])} for f in rows],
                'suggestions': [f['change_idea'] for f in rows]}

    def _generate(self, ident, body, selected, sources, advice, companions=None, run=None):
        companions = companions or {}
        self._worker.run = run
        data = None
        try:
            stage = '변경안 단계' if body['action'] == 'preview' else '제안 단계'
            methods=json.loads((self.current_result(ident)/'metrics.json').read_text('utf8')).get('methods',[])
            prompt,context=build_prompt(stage,selected,sources,methods,advice,companions=companions)
            with self.lock:
                if self._mine(ident):
                    self.states[ident]['context']=context
            self._progress(ident, 'ai', 'AI가 선택한 코드를 함께 검토하고 있습니다.', 1, indeterminate=True)
            with assistant.owned_by(('assistant', ident, run)):
                data = assistant.call_provider(body['service'], body['mode'], prompt, body.get('model', ''), body.get('api_key', ''),
                                                  **assistant.connection_extras(body))
            assistant.validate_scope(data,list(sources),preview=body['action']=='preview',companions=set(companions))
            validate_target_methods(data,methods)
            if body['action']=='preview':
                validate_edit_context(prompt,data.get('edits',[]))
            self._progress(ident, 'validate', 'AI 응답과 모든 원본 파일을 확인합니다.', 2)
            for path, raw in sources.items():
                if assistant.digest(assistant.source_file(self.base_source(ident), path).read_bytes()) != assistant.digest(raw):
                    raise ValueError('AI 생성 중 원본 코드가 변경되었습니다. 다시 생성해 주세요.')
            with self.lock:
                if not self._mine(ident):
                    return
                state = self.states[ident]
                if body['action'] == 'preview':
                    allowed = set(sources) | {c['path'] for c in data.get('companions', [])}
                    if any(e.get('path') not in allowed for e in data.get('edits', [])):
                        raise ValueError('선택한 파일과 함께 수정되는 파일 밖의 변경안은 적용할 수 없습니다.')
                    self._progress(ident, 'preview', '선택한 파일들의 코드 비교를 준비합니다.', 3)
                    if data.get('edits'):
                        preview=assistant.preview_changes(self.base_source(ident), data['edits'], data.get('creates', []))
                        validate_preview_targets(data,methods,preview,companions=set(companions))
                        state['preview'] = preview
                        state['preview_id'] = uuid.uuid4().hex
                    else:
                        state['no_changes'] = True
                    state['change_advice'] = data
                else:
                    state['advice'] = data
                self._finish(ident)
        except Exception as exc:
            if data is not None:   # keep the rejected AI reply locally so a failure can be explained
                try:
                    (self.folder(ident) / 'assistant-rejected-reply.json').write_text(
                        json.dumps({'error': str(exc), 'reply': data}, ensure_ascii=False, indent=1), encoding='utf8')
                except (OSError, TypeError, ValueError):
                    pass
            self._fail(ident, exc)
        finally:
            body.pop('api_key', None)

    # --- one click, several files in depth: one AI call per file, a few at once ----------------
    def _worker_update(self, ident, key, **fields):
        with self.lock:
            if not self._mine(ident):
                return
            for row in self.states[ident].get('workers', []):
                if row['key'] == key:
                    row.update(fields)
            rows = self.states[ident].get('workers', [])
            count = lambda *states: sum(row['state'] in states for row in rows)
            finished, total = count(*DEEP_FINAL), len(rows)
            parts = [f'완료 {count("done")}개'] + ([f'바꿀 곳 없음 {count("no_changes")}개'] if count('no_changes') else []) \
                + ([f'거절 {count("failed", "skipped")}개'] if count('failed', 'skipped') else []) + [f'진행 중 {count("running", "checking")}개']
            # The bar moves through the AI stage (1 of 4) as files finish, instead of standing still.
            self.states[ident]['progress'] = dict(stage='ai', label=f'파일 {total}개 중 ' + ' · '.join(parts),
                                                 step=1 + finished / max(total, 1), total=4, indeterminate=False)
            self._save(ident)

    @staticmethod
    def _deep_rules(path, sources, data, prompt, methods):
        assistant.validate_scope(data, list(sources), preview=True, companions=set())
        if data.get('creates') or data.get('companions'):
            raise ValueError('깊게 정리에서는 새 파일이나 함께 수정되는 파일을 만들 수 없습니다.')
        if any(e.get('path') != path for e in data.get('edits', [])):
            raise ValueError(f'{path} 밖의 파일을 바꾸는 변경은 적용할 수 없습니다.')
        if any(r['decision'] == 'refactor' and r.get('change_type') != 'functions' for r in data['file_reviews']):
            raise ValueError('깊게 정리에서는 함수 본문 변경만 할 수 있습니다.')
        validate_target_methods(data, methods)
        validate_edit_context(prompt, data.get('edits', []))

    def _check_deep(self, ident, path, sources, data, prompt, methods):
        """The usual checks for one file, plus: functions only, this file only, nothing new."""
        self._deep_rules(path, sources, data, prompt, methods)
        if not data.get('edits'):
            return []
        preview = assistant.preview_changes(self.base_source(ident), data['edits'], [])
        validate_preview_targets(data, methods, preview, companions=set())
        return preview['files']

    def _keep_rejected(self, ident, path, exc, data, suffix=''):
        """The reply a check turned down, as it arrived, for looking into it later."""
        if data is None:
            return
        try:
            (self.folder(ident) / f"assistant-rejected-{Path(path).name}{suffix}.json").write_text(
                json.dumps({'error': str(exc), 'reply': data}, ensure_ascii=False, indent=1), encoding='utf8')
        except (OSError, TypeError, ValueError):
            pass

    def _salvage(self, ident, path, sources, data, prompt, methods):
        """A reply the checks turned down may still hold a sound part (no AI call): leave out helpers that
        nothing calls and target functions it did not really change, or one edit at a time, and check the
        rest again. Returns (files, data, left-out names) or None."""
        def inserted(edit):   # the helper names an edit puts in front of a function, or []
            old, new = edit.get('old', ''), edit.get('new', '')
            return _inserted_helpers(path, new[:-len(old)]) if old and new.endswith(old) and new != old else []

        def prune(edits):   # drop insertions none of the other kept edits calls
            while True:
                unused = next((e for e in edits if inserted(e) and not any(
                    re.search(r'\b' + re.escape(name) + r'\s*\(', other.get('new', ''))
                    for name in inserted(e) for other in edits if other is not e)), None)
                if unused is None:
                    return edits
                edits = [e for e in edits if e is not unused]

        edits = data.get('edits', [])
        review = next((r for r in data['file_reviews'] if r['path'] == path), None)
        if not edits or review is None or not review.get('targets'):
            return None
        targets = list(review['targets'])
        subsets = [[t for t in targets if t != left] for left in targets] if len(targets) > 1 else []
        tries = [prune(edits)] + [prune([e for e in edits if e is not drop]) for drop in edits if not inserted(drop)]
        attempts = 0
        for kept in tries:
            if not kept or attempts >= 12:
                continue
            for chosen in [targets] + subsets:
                attempts += 1
                trial = deepcopy(data)
                trial['edits'] = kept
                next(r for r in trial['file_reviews'] if r['path'] == path)['targets'] = chosen
                try:
                    files = self._check_deep(ident, path, sources, trial, prompt, methods)
                except ValueError:
                    continue
                if files:
                    left = [t for t in targets if t not in chosen] + sorted(
                        {n for e in edits if e not in kept for n in inserted(e)})
                    return files, trial, left
        return None

    def _ask_deep(self, ident, body, run, prompt):
        with assistant.owned_by(('assistant', ident, run)):
            return assistant.call_provider(body['service'], body['mode'], prompt, body.get('model', ''), body.get('api_key', ''),
                                           schema=assistant.DEEP_SCHEMA, guidance=assistant.GUIDANCE + assistant.DEEP_GUIDANCE, timeout=assistant.DEEP_TIMEOUT,
                                           max_output=assistant.DEEP_OUTPUT_TOKENS, **assistant.connection_extras(body))

    def _continue_deep(self, ident, key, body, run, unit, path, own, methods, advice, targets, files, data, started):
        """Later passes on one file. Each asks the AI to go on from the text the last accepted pass left,
        is checked on that text, and is kept only if the whole change from the original still passes the
        usual checks. Stops when the targets are small, a pass helps little, time runs short or a pass is
        rejected; the last accepted change stays. Returns (files, data, note), or Nones when cancelled."""
        original, current = files[0]['before'], files[0]['after']
        names = {m.get('name') for m in methods if m.get('file_path', '').replace('\\', '/') == path}
        others = [m for m in methods if m.get('file_path', '').replace('\\', '/') != path]

        def target_cc(text):
            measured = {m['name']: m['cc'] for m in measure_functions(path, text)}
            return [measured.get(t, 0) for t in targets]

        # What each pass did, for the page: its own change and moved blocks in the AI's words, the
        # helpers it added and the targets' complexity before and after it; or why it was not kept.
        passes = []

        def record(state, reply=None, helpers=(), cc=None, reason=None):
            review = next((r for r in (reply or {}).get('file_reviews', []) if r.get('path') == path), {})
            passes.append({'step': step, 'state': state, 'change': review.get('change', ''), 'evidence': review.get('evidence', []),
                           'helpers': list(helpers), 'reason': reason,
                           'cc': [{'name': t, 'before': b, 'after': a} for t, (b, a) in zip(targets, cc)] if cc else []})
            self._worker_update(ident, key, passes=deepcopy(passes))
        first_cc = target_cc(original)
        before, after = sum(first_cc), target_cc(current)
        took, step, note = time.time() - started, 1, None
        record('kept', data, files[0].get('added_helpers', []), list(zip(first_cc, after)))
        while step < DEEP_PASSES:
            gained = before - sum(after)
            if (max(after, default=0) < DEEP_CONTINUE_CC or gained < max(DEEP_MIN_GAIN, before * 0.05)
                    or time.time() - started + took > DEEP_FILE_BUDGET or not self._mine(ident)):
                break
            step += 1
            measured = [m for m in measure_functions(path, current) if m['name'] in names]
            texts = {p: current.encode('utf8') if p == path else raw for p, raw in own.items()}
            helpers = sorted({h for f in files for h in f.get('added_helpers', [])})
            prompt, _ = build_deep_prompt(unit, path, texts, measured + others, advice, targets,
                                          continuation={'pass': step, 'helpers': helpers})
            self._worker_update(ident, key, state='running', step=step)
            begun, reply = time.time(), None
            try:
                reply = self._ask_deep(ident, body, run, prompt)
                if not self._mine(ident):
                    return None, None, None
                self._worker_update(ident, key, state='checking')
                self._deep_rules(path, own, reply, prompt, measured + others)
                if not reply.get('edits'):
                    record('empty', reply)
                    step -= 1
                    break
                with tempfile.TemporaryDirectory(prefix='game-si-pass-') as folder:
                    root = Path(folder)
                    target = root.joinpath(*path.split('/'))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(current, encoding='utf8', newline='')
                    step_preview = assistant.preview_changes(root, reply['edits'], [])
                    validate_preview_targets(reply, measured + others, step_preview, companions=set())
                merged = merge_deep_passes(data, reply, path)
                whole = assistant.preview_changes(self.base_source(ident), [{'path': path, 'old': original, 'new': step_preview['files'][0]['after']}], [])
                validate_preview_targets(merged, methods, whole, companions=set())
            except Exception as exc:
                answered = reply is not None or getattr(exc, 'reply', None) is not None   # else the request itself failed
                reply = reply if reply is not None else getattr(exc, 'reply', None)
                if reply is not None:
                    try:
                        (self.folder(ident) / f"assistant-rejected-{Path(path).name}-pass{step}.json").write_text(
                            json.dumps({'error': str(exc), 'reply': reply}, ensure_ascii=False, indent=1), encoding='utf8')
                    except (OSError, TypeError, ValueError):
                        pass
                if not self._mine(ident):
                    return None, None, None
                reason = str(exc) if isinstance(exc, ValueError) else '검사를 마치지 못했습니다.'
                # Said as it was: turned down by the checks, or no answer at all (a used-up limit above all).
                kind, why = (('limit', 'AI 사용 한도에 걸려') if isinstance(exc, assistant.LimitReached)
                             else ('rejected', '검사에서 빠져') if answered else ('failed', 'AI가 답하지 못해'))
                note = f'이어서 정리한 {step}단계는 {why} {step - 1}단계까지만 반영했습니다.'
                record(kind, reply, reason=reason[:600])
                self._worker_update(ident, key, note_detail=reason[:600], stopped_at=step - 1)
                step -= 1
                break
            had = {h for f in files for h in f.get('added_helpers', [])}
            new_helpers = [h for h in whole['files'][0].get('added_helpers', []) if h not in had]
            files, data, current = whole['files'], merged, whole['files'][0]['after']
            took, before, previous, after = time.time() - begun, sum(after), after, target_cc(current)   # the next gain is this pass's own
            record('kept', reply, new_helpers, list(zip(previous, after)))
        if step > 1 and note is None:
            note = f'AI를 {step}번 이어서 불러 단계적으로 정리했습니다.'
        self._worker_update(ident, key, steps_done=step)
        return files, data, note

    def _generate_deep(self, ident, body, selected, sources, advice, keep=None, run=None):
        self._worker.run = run
        try:
            methods = json.loads((self.current_result(ident) / 'metrics.json').read_text('utf8')).get('methods', [])
            hints = {row.get('path'): row.get('targets', []) for row in (advice or {}).get('file_reviews', [])}
            deadline = time.time() + DEEP_DEADLINE

            def work(unit):
                self._worker.run = run   # thread-local: every worker thread carries the task it belongs to
                key, path = unit['fqn'], unit['file_path']
                own = {p: raw for p, raw in sources.items() if p == path or p in assistant.paired_headers(self.base_source(ident), path)}
                if not self._mine(ident):
                    return None
                if time.time() > deadline:
                    self._worker_update(ident, key, state='skipped', error='전체 제한 시간이 지나 시작하지 않았습니다.')
                    return None
                started, data, first = time.time(), None, None   # first: why the first reply was turned down
                try:
                    prompt, context = build_deep_prompt(unit, path, own, methods, advice, hints.get(path, ()))
                    # Already simple enough: no AI request (and no quota) for this file.
                    measured = {m.get('name'): m.get('cc') or 0 for m in methods if m.get('file_path', '').replace('\\', '/') == path}
                    if max((measured.get(t, 0) for t in context['targets']), default=0) < DEEP_WORTH_CC:
                        self._worker_update(ident, key, state='no_changes', targets=context['targets'], seconds=0,
                                            error=f'고칠 만큼 복잡한 함수가 없어(복잡도 {DEEP_WORTH_CC} 미만) AI를 부르지 않았습니다.')
                        return None
                    self._worker_update(ident, key, state='running', mode=context['mode'], started_at=started,
                                        sent_kb=round(context['sent_source_bytes'] / 1024), file_kb=round(context['total_source_bytes'] / 1024),
                                        targets=context['targets'], skipped_targets=context['skipped_targets'], step=1, steps=DEEP_PASSES)
                    if not self._mine(ident):   # cancelled while the prompt was built: no AI request at all
                        return None
                    for attempt in (1, 2):
                        data = None
                        try:
                            data = self._ask_deep(ident, body, run, prompt)
                            if not self._mine(ident):
                                return None
                            self._worker_update(ident, key, state='checking')
                            files, kept = self._check_deep(ident, path, own, data, prompt, methods), None
                        except ValueError as exc:
                            if (not self._mine(ident) or isinstance(exc, assistant.LimitReached)
                                    or isinstance(exc.__cause__, subprocess.TimeoutExpired)):
                                raise   # a timeout or a used-up limit is not asked again: it would most likely fail again
                            answered = data is not None   # a reply in the right form, turned down by the checks
                            data = data if answered else getattr(exc, 'reply', None)
                            self._keep_rejected(ident, path, exc, data, '' if attempt == 1 else '-retry')
                            kept = self._salvage(ident, path, own, data, prompt, methods) if answered else None
                            if kept is None and attempt == 1:
                                # Asked once more by the program itself, told why: a smaller, complete change.
                                first = str(exc)
                                self._worker_update(ident, key, state='running', retried=True, retry_reason=first[:600])
                                prompt, context = build_deep_prompt(unit, path, own, methods, advice, hints.get(path, ()), retry=first)
                                continue
                            if kept is None:
                                raise
                            files, data = kept[0], kept[1]
                        break
                    notes = []
                    if first:
                        notes.append('첫 답이 검사에 걸려, 이유를 알려 주고 한 번 더 만들었습니다.')
                    if kept and kept[2]:
                        notes.append(f"검사를 통과하지 못한 부분({', '.join(kept[2])})은 빼고 나머지를 반영했습니다.")
                    note = ' '.join(notes) or None
                    if files:
                        files, data, later = self._continue_deep(ident, key, body, run, unit, path, own, methods, advice,
                                                                 context['targets'], files, data, started)
                        if files is None:   # cancelled
                            return None
                        note = ' '.join(filter(None, [note, later])) or None
                    changed = sorted({t for r in data['file_reviews'] if r['decision'] == 'refactor' for t in r['targets']})
                    helpers = sorted({h for f in files for h in f.get('added_helpers', [])})
                    self._worker_update(ident, key, state='done' if files else 'no_changes', seconds=round(time.time() - started),
                                        changed=changed, helpers=helpers, error=None if files else (data.get('uncertainty') or '')[:600],
                                        note=note if files else None)
                    return {'unit': unit, 'data': data, 'files': files, 'sent': context['sent_source_bytes']}
                except Exception as exc:
                    data = data if data is not None else getattr(exc, 'reply', None)
                    self._keep_rejected(ident, path, exc, data, '-retry' if first else '')
                    message = str(exc) if isinstance(exc, ValueError) else '이 파일의 변경안을 만들지 못했습니다.'
                    if isinstance(exc.__cause__, subprocess.TimeoutExpired):
                        message = (f'AI가 {assistant.DEEP_TIMEOUT // 60}분 안에 답하지 못했습니다. 원본은 그대로이며, '
                                   '이 파일만 다시 만들거나 빼고 진행할 수 있습니다.')
                    self._worker_update(ident, key, state='failed', error=message, seconds=round(time.time() - started))
                    return None

            with ThreadPoolExecutor(max_workers=DEEP_PARALLEL) as pool:
                outcomes = list(pool.map(work, selected))
            if not self._mine(ident):
                return
            self._progress(ident, 'validate', 'AI 응답과 모든 원본 파일을 확인합니다.', 2)
            for path, raw in sources.items():
                if assistant.digest(assistant.source_file(self.base_source(ident), path).read_bytes()) != assistant.digest(raw):
                    raise ValueError('AI 생성 중 원본 코드가 변경되었습니다. 다시 생성해 주세요.')
            results = [o for o in outcomes if o]
            changed = [o for o in results if o['files']]
            files = list((keep or {}).get('preview', {}).get('files', [])) + [f for o in changed for f in o['files']]
            if len({f['path'] for f in files}) != len(files):
                raise ValueError('두 작업이 같은 파일을 바꾸었습니다. 다시 생성해 주세요.')
            with self.lock:
                if not self._mine(ident):
                    return
                state = self.states[ident]
                failed = [{k: w.get(k) for k in ['key', 'path', 'label', 'state', 'error']} for w in state['workers']
                          if w['state'] in {'failed', 'skipped'}]
                state['sent_source_bytes'] = sum(o['sent'] for o in results)
                state['context'] = {'mode': 'deep', 'sent_source_bytes': state['sent_source_bytes']}
                if not files:
                    if failed:
                        raise ValueError(' / '.join(f"{w['label']}: {w['error']}" for w in failed)[:1500])
                    state['no_changes'] = True
                    state['change_advice'] = merge_deep_advice(results, self._deep_title(ident, state, len(results)), (keep or {}).get('change_advice'))
                else:
                    self._progress(ident, 'preview', '파일별 변경안을 하나로 묶어 비교를 준비합니다.', 3)
                    state['preview'] = {'files': files}
                    state['preview_id'] = uuid.uuid4().hex
                    state['change_advice'] = merge_deep_advice(changed or results, self._deep_title(ident, state, len({f['path'] for f in files if not f.get('created')})),
                                                               (keep or {}).get('change_advice'))
                state['preview_failures'] = failed
                self._finish(ident)
        except Exception as exc:
            self._fail(ident, exc)
        finally:
            body.pop('api_key', None)

    def _deep_title(self, ident, state, count):
        prescriptions = getattr(self, 'prescriptions', None)
        result = (prescriptions.get(ident) if prescriptions else {}).get('result') or {}
        if state.get('plan_source') == 'prescription' and result.get('headline'):
            return result['headline']
        return f'{count}개 파일의 복잡한 함수를 한 번에 정리합니다' if count else '바꿀 곳을 찾지 못했습니다'

    def _fail(self, ident, exc):
        with self.lock:
            if not self._mine(ident):
                return
            self.states[ident].update(state='failed', error=str(exc) if isinstance(exc, ValueError)
                                      else '작업을 완료하지 못했습니다. 입력과 AI 연결을 확인해 주세요.', finished_at=time.time())
            self._save(ident)

    def apply(self, ident, preview_id):
        with self.lock:
            state = self.get(ident)
            if state['state'] == 'running':
                raise BusyError('진행 중인 작업을 기다려 주세요.')
            if not preview_id or state.get('preview_id') != preview_id or not state.get('preview'):
                raise ValueError('최신 변경안을 먼저 검토해 주세요.')
            if state.get('base_revision') != self.current_revision(ident):
                raise ValueError('변경안을 만든 뒤 라운드가 바뀌었습니다. 현재 수정본 기준으로 변경안을 다시 만들어 주세요.')
            for item in state['preview']['files']:
                if item.get('created'):
                    assistant.new_file_path(self.base_source(ident), item['path'])   # must still not exist
                    continue
                if assistant.digest(assistant.source_file(self.base_source(ident), item['path']).read_bytes()) != item['sha256']:
                    raise ValueError('원본 코드가 변경되었습니다. 변경안을 다시 생성해 주세요.')
            for path, fingerprint in state.get('source_hashes', {}).items():
                if assistant.digest(assistant.source_file(self.base_source(ident), path).read_bytes()) != fingerprint:
                    raise ValueError('검토에 사용한 원본 코드가 변경되었습니다. 변경안을 다시 생성해 주세요.')
            samples = state.get('timings', {}).get(f"apply:{state['service']}:{state['mode']}:{state.get('model', '')}:{len(state.get('candidates', [state['candidate']]))}", [])
            state.update(state='running', action='apply', error=None, started_at=time.time(), finished_at=None, run_id=uuid.uuid4().hex,
                         estimated_seconds=round(median(samples)) if samples else None, estimate_samples=len(samples),
                         progress=dict(stage='copy', label='원본을 보존하고 별도 수정본을 만듭니다.', step=0, total=4, indeterminate=False))
            state.pop('preview_id', None)  # single-use approval
            self.states[ident] = state
            self._save(ident)
            worker = threading.Thread(target=self._apply, args=(ident, state['preview'], state['run_id']), daemon=True)
            self.threads.append(worker)
            worker.start()
        return self.get(ident)

    def _apply(self, ident, preview, run=None):
        self._worker.run = run
        revision = uuid.uuid4().hex
        base_result = self.current_result(ident)
        base_revision = self.current_revision(ident)
        folder = self.folder(ident) / 'revisions' / revision
        source, output = folder / 'source', folder / 'result'
        try:
            assistant.apply_changes(self.base_source(ident), source, preview,self.states[ident].get('source_hashes',{}))
            (folder / 'manifest.json').write_text(json.dumps(self._manifest(source), indent=1), encoding='utf8')
            self._progress(ident, 'analyze', '수정한 소스 전체를 다시 정적 분석합니다.', 1, indeterminate=True)
            options = self.manager.get(ident).get('options', {})
            env = assistant.cli_environment()
            dotnet = Path(r'C:\Program Files\dotnet')
            if dotnet.is_dir():
                env['PATH'] = str(dotnet) + os.pathsep + env.get('PATH', '')
            command = [sys.executable, '-u', '-m', 'game_si', 'analyze', str(source),
                       '--lang', options.get('lang', 'auto'), '--out', str(output),
                       '--project-name', self.manager.get(ident)['name'] + ' · AI 수정본']
            # Game-loop entries stay those of the first analysis, so a new helper's name cannot move the scores.
            first = json.loads((self.folder(ident) / 'result' / 'metrics.json').read_text('utf8'))
            entries = folder / 'loop_entries.json'
            entries.write_text(json.dumps(sorted([m['file_path'], m['name']] for m in first.get('methods', [])
                                                 if m.get('is_game_loop_entry'))), encoding='utf8')
            command += ['--loop-entries', str(entries)]
            # Precise (Clang) analysis: the same compile settings, with paths moved to this copy.
            if options.get('backend') == 'clang':
                try:
                    database = clang_presets.revision_database(options, self.source(ident), source, folder / 'compile_commands.json')
                except (OSError, ValueError, KeyError) as exc:
                    raise ValueError('수정본은 생성했지만 정밀 분석(Clang) 설정을 사본에 맞추지 못했습니다. 원본은 보존되어 있습니다.') from exc
                command += ['--cpp-backend', 'clang', '--compile-commands', str(database)]
                if options.get('clang_library'):
                    command += ['--clang-library', options['clang_library']]
            with (folder / 'analysis.log').open('w', encoding='utf8') as log:
                result = subprocess.Popen(command, cwd=REPO_ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                with assistant.PROCESS_LOCK:
                    assistant.PROCESSES.add(result)
                try:
                    result.wait(timeout=300)
                except subprocess.TimeoutExpired:
                    assistant.terminate_process(result)
                    raise ValueError('수정본 재분석 제한 시간을 초과했습니다. 원본은 보존되어 있습니다.')
                finally:
                    with assistant.PROCESS_LOCK:
                        assistant.PROCESSES.discard(result)
            if result.returncode not in {0, 3} or not (output / 'scoring.json').is_file():
                raise ValueError('수정본은 생성했지만 재분석에 실패했습니다. 원본은 보존되어 있습니다.')
            self._progress(ident, 'compare', '파일과 함수별 전후 결과를 비교하고 있습니다.', 2)
            before = json.loads((base_result / 'scoring.json').read_text('utf8'))
            after = json.loads((output / 'scoring.json').read_text('utf8'))
            changed = {p['path'] for p in preview['files']}
            compared = changed | set(self.states[ident].get('source_hashes', {}))
            comparison = {'before': [c for c in before.get('class_scores', []) if c.get('file_path', '').replace('\\', '/') in compared],
                          'after': [c for c in after.get('class_scores', []) if c.get('file_path', '').replace('\\', '/') in compared],
                          'note': 'G-SI는 각 집합 내부 상대 순위입니다. 원시 지표와 코드 변화·테스트를 함께 확인하세요.'}
            old_methods = json.loads((base_result / 'metrics.json').read_text('utf8')).get('methods', [])
            new_methods = json.loads((output / 'metrics.json').read_text('utf8')).get('methods', [])
            old_by_name = {m['fqn']: m for m in old_methods if m.get('file_path', '').replace('\\', '/') in changed}
            new_by_name = {m['fqn']: m for m in new_methods if m.get('file_path', '').replace('\\', '/') in changed}
            comparison['functions'] = []
            for name in sorted(old_by_name.keys() | new_by_name.keys()):
                old, new = old_by_name.get(name), new_by_name.get(name)
                if old is None or new is None or (old.get('cc'), old.get('loc')) != (new.get('cc'), new.get('loc')):
                    comparison['functions'].append({'name': name, 'before': {k: old.get(k) for k in ['cc', 'loc']} if old else None,
                                                   'after': {k: new.get(k) for k in ['cc', 'loc']} if new else None})
            (folder / 'comparison.json').write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding='utf8')
            self._progress(ident, 'package', '검토할 결과와 수정본 파일을 정리합니다.', 3)
            shutil.make_archive(str(folder / 'modified-source'), 'zip', source)
            status = json.loads((output / 'scoring.json').read_text('utf8')).get('analysis_status', {})
            with self.lock:
                rounds = self.rounds(ident)
                kept = rounds['rounds'][:rounds['current']]
                # Rounds undone before this one leave the active list but stay on record.
                discarded = rounds.get('discarded', []) + rounds['rounds'][rounds['current']:]
                kept.append({'round': len(kept) + 1, 'revision': revision, 'base': base_revision, 'applied_at': time.time(),
                             'files': [f['path'] for f in preview['files']], 'plan_source': self.states[ident].get('plan_source', 'review'),
                             'candidates': self.states[ident].get('candidates', []),
                             **round_notes(self.states[ident].get('change_advice') or {}, changed),
                             'checks': {'original_preserved': True, 'matches_preview': True,
                                        'reanalyzed': {'state': status.get('state'), 'analyzed_files': status.get('analyzed_files'),
                                                       'syntax_files': status.get('syntax_files')}}})
                self._save_rounds(ident, {'rounds': kept, 'current': len(kept), **({'discarded': discarded} if discarded else {})})
                self.states[ident].update(revision=revision, round=len(kept),
                    revision_url=f'/revisions/{ident}/{revision}/index.html',
                    download_url=f'/revisions/{ident}/{revision}/modified-source.zip',
                    comparison=comparison, finished_at=time.time(),
                    message='별도 수정본 생성과 재분석이 완료되었습니다.')
                self._finish(ident)
        except Exception as exc:
            self._fail(ident, exc)
            return
        prescriptions = getattr(self, 'prescriptions', None)
        if prescriptions is not None:
            prescriptions.auto_next(ident)

    def close(self):
        assistant.close_providers()
        self.reviews.close()
        for worker in self.threads:
            worker.join(timeout=1)


def split_check(text):
    """'설정 화면 | 음량 막대 조절하기' -> ('설정 화면', '음량 막대 조절하기'); older checks have no place."""
    place, bar, action = text.partition('|')
    return (place.strip(), action.strip()) if bar and place.strip() and action.strip() else ('', text.strip())


def round_notes(advice, changed):
    """What a round keeps for the result and finishing pages: how it changed the code (functions split,
    or declarations moved) and the behaviour to try in the game, from the AI's checks per changed file."""
    reviews = [r for r in advice.get('file_reviews') or [] if isinstance(r, dict) and r.get('path') in changed]
    edited = [r for r in reviews if r.get('decision') == 'refactor'] or reviews
    method = 'declarations' if edited and all(r.get('change_type') == 'declarations' for r in edited) else 'functions'
    checks, seen = [], set()
    for row in edited:
        for text in row.get('checks') or []:
            if not isinstance(text, str) or not text.strip() or text.strip() in seen:
                continue
            seen.add(text.strip())
            where, action = split_check(text)
            checks.append({'where': where, 'action': action, 'file': row['path'], 'targets': list(row.get('targets') or [])[:4]})
    return {'method': method, 'play_checks': checks[:24]}
