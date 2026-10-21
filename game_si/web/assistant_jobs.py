"""Independent advice/preview tasks; source edits create isolated revisions."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import subprocess
import shutil
import sys
import threading
import time
import uuid
from statistics import median

from . import assistant, clang_presets, diagnosis
from .inputs import target_path
from .jobs import BusyError, REPO_ROOT
from .assistant_context import build_prompt, validate_edit_context, validate_target_methods, validate_preview_targets
from .assistant_reviews import AssistantReviews


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
        path = self._rounds_path(ident)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf8')
        temporary.replace(path)

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
        path = self.folder(ident) / 'assistant.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.states[ident], ensure_ascii=False, indent=2), encoding='utf8')
        temporary.replace(path)

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
        service, mode = body.get('service'), body.get('mode')
        if service not in assistant.SERVICES or mode not in {'cli', 'api'}:
            raise ValueError('AI 연결 방식을 선택해 주세요.')
        if mode == 'api' and not body.get('api_key'):
            raise ValueError('사용자 본인의 API 키가 필요합니다.')
        root = self.base_source(ident)
        sources = {c['file_path']: assistant.source_file(root, c['file_path']).read_bytes() for c in selected}
        if action == 'preview':
            for c in selected:
                for header in assistant.paired_headers(root, c['file_path']):
                    sources.setdefault(header, assistant.source_file(root, header).read_bytes())
        companions = self._companions(ident, names, sources) if action == 'preview' else {}
        fingerprints = {path: assistant.digest(raw) for path, raw in sources.items()}
        first = selected[0]
        with self.lock:
            previous = self.get(ident)
            prescriptions = getattr(self, 'prescriptions', None)
            if previous['state'] == 'running' or self.reviews.busy(ident) or (prescriptions and prescriptions.busy(ident)):
                raise BusyError('진행 중인 AI 작업을 기다려 주세요.')
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
                        'comparison', 'message', 'change_advice', 'no_changes']:
                state.pop(key, None)
            state['base_revision'] = self.current_revision(ident)   # the round this change builds on
            self.states[ident] = state
            self._save(ident)
        # Credentials remain only in this worker's memory; never in task records/logs.
        worker = threading.Thread(target=self._generate,
                                  args=(ident, dict(body), selected, sources, advice, companions, state['run_id']), daemon=True)
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
                                  'expected_effect': f['expected'], 'decision': '연결 정리' if f['kind'] == 'link' else '파일 안 정리'} for f in rows],
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
                data = assistant.call_provider(body['service'], body['mode'], prompt, body.get('model', ''), body.get('api_key', ''))
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

    def close(self):
        assistant.close_providers()
        self.reviews.close()
        for worker in self.threads:
            worker.join(timeout=1)
