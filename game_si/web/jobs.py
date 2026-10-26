"""Local job records and isolated execution of the canonical analyze command."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import psutil

from . import clang_presets
from .inputs import inspect_source, target_path

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTIVE = {'importing', 'running'}


class BusyError(ValueError):
    pass


def write_json(path: Path, data) -> None:
    """Write a state file whole (through a temporary file). On Windows the swap is refused while the
    file is open elsewhere for a moment (a page reading the state), so it is tried again briefly."""
    temporary = path.with_name(f'{path.name}.{uuid.uuid4().hex[:8]}.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    for attempt in range(40):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 39:
                temporary.unlink(missing_ok=True)
                raise
            time.sleep(0.05)


class JobManager:
    def __init__(self, root: Path, timeout: float = 1800):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.lock = threading.RLock()
        self.records = {}
        self.processes = {}
        self.threads = []
        self.cancellations = set()
        self.import_workers = set()
        self.closed = False
        for path in self.root.glob('*/job.json'):
            try:
                record = json.loads(path.read_text(encoding='utf-8'))
                required = {'id', 'name', 'kind', 'state', 'created_at', 'stage', 'source', 'scan', 'error'}
                if (not isinstance(record, dict) or not required.issubset(record)
                        or record['state'] not in ACTIVE | {'ready', 'complete', 'partial', 'failed', 'interrupted'}
                        or not isinstance(record['created_at'], (int, float))):
                    continue
                if path.parent != self.directory(record['id']):
                    continue
                self.records[record['id']] = record
                if record['state'] in ACTIVE:
                    self.update(record['id'], state='interrupted', error='프로그램이 종료되어 중단된 작업입니다.')
                if isinstance(record['scan'], dict) and 'source_bytes' not in record['scan']:
                    try:
                        record['scan']['source_bytes'] = inspect_source(path.parent / 'input')['source_bytes']
                    except (OSError, ValueError):
                        record['scan']['source_bytes'] = None
                    self._save(record)
            except (OSError, ValueError, KeyError, TypeError):
                continue

    def directory(self, ident: str) -> Path:
        if not re.fullmatch(r'[0-9a-f]{32}', ident):
            raise ValueError('올바르지 않은 작업 번호입니다.')
        return self.root / ident

    def _save(self, record):
        write_json(self.directory(record['id']) / 'job.json', record)

    def update(self, ident, **values):
        with self.lock:
            self.records[ident].update(values)
            self._save(self.records[ident])

    def create(self, name: str, kind: str, *, reserve_import: bool = False) -> dict:
        with self.lock:
            if self.closed or self.import_workers or any(r['state'] in ACTIVE for r in self.records.values()):
                raise BusyError('현재 작업이 끝난 뒤 새 분석을 시작해 주세요.')
            ident = uuid.uuid4().hex
            self.directory(ident).mkdir()
            (self.directory(ident) / 'input').mkdir()
            record = dict(id=ident, name=(name.strip() or '새 분석')[:100], kind=kind,
                          state='importing', stage='소스 준비', created_at=time.time(),
                          started_at=None, finished_at=None, error=None, scan=None, source={})
            record['deleted_at'] = None
            self.records[ident] = record
            self._save(record)
            if reserve_import:
                self.import_workers.add(ident)
            return self.get(ident)

    def ready(self, ident: str, source=None):
        scan = inspect_source(self.directory(ident) / 'input')
        try:   # folders that are the prepared demo game: they can get the precise (Clang) analysis
            scan['presets'] = clang_presets.detect(self.directory(ident) / 'input')
        except OSError:
            scan['presets'] = []
        with self.lock:
            if self.closed or ident in self.cancellations or self.records[ident]['state'] != 'importing':
                return
            self.update(ident, state='ready', stage='분석 대상 확인', scan=scan, source=source or {})

    def fail(self, ident, error):
        with self.lock:
            if self.records[ident]['state'] != 'interrupted':
                self.update(ident, state='failed', error=str(error), finished_at=time.time())

    def get(self, ident: str, include_deleted: bool = False) -> dict:
        self.directory(ident)
        with self.lock:
            if ident not in self.records or (self.records[ident].get('deleted_at') and not include_deleted):
                raise KeyError(ident)
            result = dict(self.records[ident])
            result['deleted_at'] = result.get('deleted_at')
            result['can_delete'] = (not result['deleted_at'] and result['state'] not in ACTIVE
                                    and ident not in self.import_workers and ident not in self.processes)
        log_path = self.directory(ident) / 'analysis.log'
        log = ''
        if log_path.exists():
            with log_path.open('rb') as stream:
                stream.seek(max(0, log_path.stat().st_size - 12000))
                log = stream.read(12000).decode('utf-8', errors='replace')
        if result['state'] == 'running':
            for marker, label in [('[ast]', '코드 분석'), ('[metrics]', '지표 계산'),
                                  ('[si]', '검토 순위 계산'), ('[html]', '결과 생성')]:
                if marker in log:
                    result['stage'] = label
        started = result.get('started_at') or result['created_at']
        result['elapsed_seconds'] = max(0, int((result.get('finished_at') or time.time()) - started))
        result['log'] = log
        result['result_url'] = (f'/results/{ident}/index.html'
                                if not result['deleted_at'] and result['state'] in {'complete', 'partial'} else None)
        return result

    def list(self, include_deleted: bool = False) -> list[dict]:
        with self.lock:
            identifiers = sorted(self.records, key=lambda i: self.records[i]['created_at'], reverse=True)
            return [self.get(i, include_deleted=include_deleted) for i in identifiers
                    if include_deleted or not self.records[i].get('deleted_at')]

    def delete(self, ident: str) -> dict:
        with self.lock:
            record = self.get(ident)
            if not record['can_delete']:
                raise BusyError('작업이 완전히 종료된 뒤 기록을 삭제해 주세요.')
            self.update(ident, deleted_at=time.time())
            return self.get(ident, include_deleted=True)

    def restore(self, ident: str) -> dict:
        with self.lock:
            self.get(ident, include_deleted=True)
            self.update(ident, deleted_at=None)
            return self.get(ident)

    def _resolve(self, ident, options):
        # 'clang-auto': precise analysis with the build settings recognised for a known game.
        if options.get('backend') != 'clang-auto':
            return options
        local = options.get('local_path', '').strip()
        root = Path(local).resolve() if local else self.directory(ident) / 'input'
        subdir = options.get('subdir', '.')
        selected = root if subdir == '.' else target_path(root, subdir)
        hit = clang_presets.match(selected) if selected.is_dir() else None
        if not hit:
            raise ValueError('이 폴더는 자동 인식된 빌드 설정과 맞지 않습니다. 기본 분석을 선택해 주세요.')
        library = clang_presets.libclang()
        if library is None:
            raise ValueError('정밀 분석에 필요한 Clang 라이브러리를 찾지 못했습니다. 기본 분석을 선택해 주세요.')
        folder = selected if hit['folder'] == '.' else selected / hit['folder']
        database = clang_presets.write_database(folder, hit['key'], self.directory(ident) / 'compile_commands.json')
        return {**options, 'lang': clang_presets.PRESETS[hit['key']]['language'], 'backend': 'clang',
                'compile_commands': str(database), 'clang_library': str(library),
                'preset': hit['key'], 'preset_folder': hit['folder']}

    def _command(self, ident, options):
        lang = options.get('lang', 'auto')
        backend = options.get('backend', 'tree-sitter')
        if lang not in {'auto', 'csharp', 'c', 'cpp'} or backend not in {'tree-sitter', 'clang'}:
            raise ValueError('분석 언어 또는 분석 방식이 올바르지 않습니다.')
        local = options.get('local_path', '').strip()
        root = Path(local).resolve() if local else self.directory(ident) / 'input'
        if not root.is_dir():
            raise ValueError('원본 소스 폴더를 찾지 못했습니다. 폴더 경로를 확인해 주세요.')
        subdir = options.get('subdir', '.')
        selected = root if subdir == '.' else target_path(root, subdir)
        if not selected.is_dir():
            raise ValueError('선택한 소스 하위 폴더를 찾지 못했습니다.')
        scan = inspect_source(selected)
        if lang == 'auto' and scan['languages']['csharp'] and (scan['languages']['c'] or scan['languages']['cpp']):
            raise ValueError('C#과 C/C++가 섞여 있습니다. 분석 언어와 하위 폴더를 선택해 주세요.')
        command = [sys.executable, '-u', '-m', 'game_si', 'analyze', str(selected),
                   '--lang', lang, '--out', str(self.directory(ident) / 'result'),
                   '--project-name', self.records[ident]['name']]
        if backend == 'clang':
            if lang not in {'c', 'cpp'}:
                raise ValueError('컴파일 설정 기반 분석에서는 C 또는 C++를 선택해 주세요.')
            database = Path(options.get('compile_commands', ''))
            if not database.is_file():
                raise ValueError('compile_commands.json 경로가 필요합니다. 원본 소스 폴더와 함께 설정해 주세요.')
            command += ['--cpp-backend', 'clang', '--compile-commands', str(database.resolve())]
            library = options.get('clang_library', '').strip()
            if library:
                if not Path(library).is_file():
                    raise ValueError('libclang 라이브러리 경로를 확인해 주세요.')
                command += ['--clang-library', str(Path(library).resolve())]
        return command

    def start(self, ident: str, options: dict):
        self.directory(ident)
        with self.lock:
            self.get(ident)
            if self.closed or self.import_workers or any(r['state'] in ACTIVE for r in self.records.values()):
                raise BusyError('현재 작업이 끝난 뒤 분석을 시작해 주세요.')
            if self.records[ident]['state'] != 'ready':
                raise ValueError('새 소스를 가져온 뒤 분석을 시작해 주세요.')
            options = self._resolve(ident, options)
            command = self._command(ident, options)
            self.update(ident, state='running', stage='분석기 준비', started_at=time.time(), options=options)
            worker = threading.Thread(target=self._run, args=(ident, command), daemon=True)
            self.threads.append(worker)
            worker.start()

    @staticmethod
    def _stop(process):
        if process.poll() is not None:
            return
        try:
            parent = psutil.Process(process.pid)
            children = parent.children(recursive=True)
            for child in reversed(children):
                try:
                    child.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            parent.kill()
            psutil.wait_procs(children + [parent], timeout=2)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            process.kill()
        process.wait(timeout=3)

    def _run(self, ident, command):
        process = None
        try:
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            dotnet = Path(r'C:\Program Files\dotnet')
            if (dotnet / 'dotnet.exe').is_file():
                env['PATH'] = str(dotnet) + os.pathsep + env.get('PATH', '')
            with (self.directory(ident) / 'analysis.log').open('w', encoding='utf-8') as output:
                with self.lock:
                    if self.closed or ident in self.cancellations:
                        self.update(ident, state='interrupted', finished_at=time.time(), error='분석이 중단되었습니다.')
                        return
                    process = subprocess.Popen(command, cwd=REPO_ROOT, env=env,
                                               stdout=output, stderr=subprocess.STDOUT, shell=False,
                                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    self.processes[ident] = process
                deadline = time.monotonic() + self.timeout
                while process.poll() is None:
                    if self.closed or ident in self.cancellations or time.monotonic() > deadline:
                        self._stop(process)
                        self.update(ident, state='interrupted', finished_at=time.time(),
                                    error='분석이 중단되었거나 제한 시간을 초과했습니다. 범위를 줄여 다시 시도해 주세요.')
                        return
                    time.sleep(.1)
            result_dir = self.directory(ident) / 'result'
            expected = {0: 'complete', 3: 'partial'}.get(process.returncode)
            status = json.loads((result_dir / 'analysis_status.json').read_text(encoding='utf-8'))
            if not expected or status['state'] != expected or not (result_dir / 'index.html').is_file():
                raise ValueError('분석 결과를 만들지 못했습니다. 소스와 설정을 확인해 주세요. 상세 기록에서 원인을 볼 수 있습니다.')
            scoring = json.loads((result_dir / 'scoring.json').read_text(encoding='utf-8'))
            if scoring.get('analysis_status') != status:
                raise ValueError('점수와 분석 상태가 일치하지 않아 결과를 표시하지 않습니다.')
            with self.lock:
                if self.closed or ident in self.cancellations:
                    self.update(ident, state='interrupted', finished_at=time.time(), error='분석이 중단되었습니다.')
                else:
                    self.update(ident, state=expected, stage='분석 종료', finished_at=time.time())
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            if process and process.poll() is None:
                self._stop(process)
            self.fail(ident, '분석 결과를 생성하지 못했습니다. 입력·설정을 확인해 주세요. ' + str(exc))
        finally:
            with self.lock:
                self.processes.pop(ident, None)

    def cancel(self, ident: str):
        with self.lock:
            self.get(ident)
            self.cancellations.add(ident)
            if self.records[ident]['state'] == 'importing':
                self.update(ident, state='interrupted', finished_at=time.time(), error='소스 가져오기가 중단되었습니다.')

    def close(self):
        with self.lock:
            self.closed = True
            identifiers = [i for i, r in self.records.items() if r['state'] in ACTIVE]
            for ident in identifiers:
                self.cancel(ident)
        for worker in self.threads:
            worker.join(timeout=4)
