"""A fixed, locally prepared Chocolate Doom demonstration recipe (not AI commands)."""
from __future__ import annotations

import difflib
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import subprocess
import threading

from .assistant import digest
from .jobs import BusyError, REPO_ROOT

SOURCE_SUFFIXES = {'.c', '.h', '.cpp', '.hpp'}


def source_tree(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): digest(p.read_bytes())
            for p in root.rglob('*') if p.is_file() and p.suffix.lower() in SOURCE_SUFFIXES}


CMAKE = Path(r'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe')


class DemoGame:
    def __init__(self, assistant, root=None):
        self.assistant = assistant
        self.root = root or REPO_ROOT / 'docs/_demo_phase'
        self.lock = threading.RLock()
        self.worker = None
        self.process = None

    def current_revision(self, ident):
        current = getattr(self.assistant, 'current_revision', None)
        return current(ident) if current else self.assistant.get(ident).get('revision')

    def verify(self, ident, revision):
        # The revision source must still match the fingerprints recorded when it was applied.
        check = getattr(self.assistant, 'verify_revision', None)
        if check:
            check(ident, revision)

    def registered(self, ident):
        try:
            return json.loads((self.root / 'demo_job.json').read_text('utf8'))['id'] == ident
        except (OSError, ValueError, KeyError):
            return False

    def get(self, ident):
        if not self.registered(ident):
            return {'available': False}
        self.assistant.get(ident)
        path = self.root / 'demo_status.json'
        state = json.loads(path.read_text('utf8')) if path.exists() else {'state': 'idle'}
        if state['state'] == 'running' and (not self.worker or not self.worker.is_alive()):
            state.update(state='interrupted', error='게임 준비가 중단되었습니다. 다시 준비해 주세요.')
            if state.get('progress'):
                state['progress'].update(stage='interrupted', label='게임 준비가 중단되었습니다.', indeterminate=False)
        state.setdefault('started_at', None)
        state.setdefault('progress', None)
        return {'available': True, **state}

    @staticmethod
    def _progress(stage, label, step, indeterminate=True):
        return {'stage': stage, 'label': label, 'step': step, 'total': 4,
                'indeterminate': indeterminate}

    def _save(self, state):
        target = self.root / 'demo_status.json'
        previous = json.loads(target.read_text('utf8')) if target.exists() else {}
        if previous.get('revision') == state.get('revision') and previous.get('state') == 'running':
            state.setdefault('started_at', previous.get('started_at'))
        if state.get('state') == 'running' and not state.get('started_at'):
            state['started_at'] = datetime.now(timezone.utc).isoformat()
        if state.get('state') == 'failed' and previous.get('progress'):
            state.setdefault('progress', {**previous['progress'], 'stage': 'failed',
                                         'label': '게임 준비에 실패했습니다.', 'indeterminate': False})
        temp = target.with_suffix('.tmp')
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf8')
        temp.replace(target)
        return state

    def prepare(self, ident):
        with self.lock:
            if not self.registered(ident):
                raise ValueError('이 분석에 등록된 시연 게임이 없습니다.')
            state = self.assistant.get(ident)
            revision = self.current_revision(ident) or ''
            if state['state'] == 'running' or not re.fullmatch('[a-f0-9]{32}', revision):
                raise ValueError('변경안을 적용하고 재분석을 완료해 주세요.')
            state = dict(state, revision=revision)
            if self.worker and self.worker.is_alive():
                raise BusyError('게임 빌드가 진행 중입니다.')
            if self.process and self.process.poll() is None:
                raise BusyError('실행 중인 시연 게임을 종료한 뒤 준비해 주세요.')
            progress = self._save({'state': 'running', 'revision': revision,
                                   'progress': self._progress('copy', '시연 원본을 복사하고 있습니다.', 0)})
            self.worker = threading.Thread(target=self._build, args=(ident, state), daemon=True)
            self.worker.start()
            return {'available': True, **progress}

    def _run(self, command, folder, log):
        result = subprocess.run(command, cwd=folder, stdout=log, stderr=subprocess.STDOUT,
                                timeout=300, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise ValueError('시연 게임 빌드에 실패했습니다. 시연 폴더의 build.log를 확인해 주세요.')

    def _build(self, ident, state):
        revision = state['revision']
        folder = self.root / '02_modified' / revision
        try:
            self._save({'state': 'running', 'revision': revision,
                        'progress': self._progress('copy', '시연 원본을 복사하고 있습니다.', 0)})
            source, build, game = folder / 'source', folder / 'build', folder / 'game'
            if not source.exists():
                shutil.copytree(self.root / '01_original/source', source)
            self._save({'state': 'running', 'revision': revision,
                        'progress': self._progress('validate', '적용된 변경과 시연 원본을 확인하고 있습니다.', 1)})
            revision_source = self.assistant.folder(ident) / 'revisions' / revision / 'source'
            self.verify(ident, revision)
            # Compare the whole current revision (all rounds) with the analysed original.
            before, after = source_tree(self.assistant.source(ident)), source_tree(revision_source)
            changed = sorted(rel for rel, fingerprint in after.items() if before.get(rel) != fingerprint)
            if set(before) - set(after) or changed != ['doom/m_menu.c']:
                raise ValueError('준비된 시연은 doom/m_menu.c 한 파일의 변경만 지원합니다.')
            original = self.root / '01_original/source/src/doom/m_menu.c'
            if digest(original.read_bytes()) != before['doom/m_menu.c']:
                raise ValueError('시연 원본과 분석 원본이 일치하지 않습니다.')
            revised = revision_source / 'doom/m_menu.c'
            shutil.copy2(revised, source / 'src/doom/m_menu.c')
            change = ''.join(difflib.unified_diff(original.read_text('utf8', errors='replace').splitlines(True),
                                                  revised.read_text('utf8', errors='replace').splitlines(True),
                                                  fromfile='원본/doom/m_menu.c', tofile='수정본/doom/m_menu.c'))
            dependencies = self.root / 'dependencies'
            self._save({'state': 'running', 'revision': revision,
                        'progress': self._progress('build', '시연 게임을 빌드하고 있습니다.', 2)})
            with (folder / 'build.log').open('w', encoding='utf8') as log:
                self._run([str(CMAKE), '-S', str(source), '-B', str(build), '-G', 'Visual Studio 17 2022',
                           '-A', 'x64', '-DSDL2_DIR=' + str(dependencies / 'SDL2-2.32.10/cmake'),
                           '-DSDL2_mixer_DIR=' + str(dependencies / 'SDL2_mixer-2.8.1/cmake'),
                           '-DENABLE_SDL2_NET=OFF'], self.root, log)
                # rc.exe otherwise reads UTF-8 Korean absolute resource paths as ANSI.
                for resource in (build / 'src').glob('*-res.rc'):
                    raw = resource.read_bytes()
                    if not raw.startswith(b'#pragma code_page(65001)'):
                        resource.write_bytes(b'#pragma code_page(65001)\r\n' + raw)
                self._run([str(CMAKE), '--build', str(build), '--config', 'Release',
                           '--target', 'chocolate-doom', '--parallel', '4'], self.root, log)
            self._save({'state': 'running', 'revision': revision,
                        'progress': self._progress('package', '실행 파일과 분석 결과를 정리하고 있습니다.', 3)})
            for target, executable in [(game, build / 'src/Release/chocolate-doom.exe'),
                    (self.root / '01_original/game', self.root / '01_original/build/src/Release/chocolate-doom.exe')]:
                target.mkdir(parents=True, exist_ok=True)
                shutil.copy2(executable, target / 'chocolate-doom.exe')
                for library in ['SDL2-2.32.10', 'SDL2_mixer-2.8.1']:
                    for dll in (dependencies / library / 'lib/x64').glob('*.dll'):
                        shutil.copy2(dll, target / dll.name)
                (target / 'saves').mkdir(exist_ok=True)
            shutil.copytree(self.assistant.folder(ident) / 'result', self.root / '01_original/analysis', dirs_exist_ok=True)
            shutil.copytree(self.assistant.folder(ident) / 'revisions' / revision / 'result', folder / 'analysis', dirs_exist_ok=True)
            (folder / 'changes.diff').write_text(change, encoding='utf8')
            self._save({'state': 'complete', 'revision': revision,
                        'progress': self._progress('complete', '시연 게임 준비를 완료했습니다.', 4, False),
                        'source_sha256': digest(revised.read_bytes()), 'executable_sha256': digest((game / 'chocolate-doom.exe').read_bytes()),
                        'message': '수정본 빌드 완료 · 게임 실행으로 저장·불러오기와 플레이를 확인하세요.'})
        except Exception as exc:
            self._save({'state': 'failed', 'revision': revision,
                        'error': str(exc) if isinstance(exc, ValueError) else '게임 준비에 실패했습니다. 빌드 도구와 시연 파일을 확인해 주세요.'})

    def launch(self, ident, version):
        with self.lock:
            state = self.get(ident)
            if not state.get('available') or state['state'] != 'complete' or version not in {'original', 'modified'}:
                raise ValueError('준비된 시연 게임을 선택해 주세요.')
            if self.current_revision(ident) != state['revision']:
                raise ValueError('현재 수정본으로 게임을 다시 준비해 주세요.')
            if self.process and self.process.poll() is None:
                raise BusyError('실행 중인 시연 게임을 먼저 종료해 주세요.')
            folder = self.root / ('01_original' if version == 'original' else '02_modified/' + state['revision']) / 'game'
            executable = folder / 'chocolate-doom.exe'
            if version == 'modified' and digest(executable.read_bytes()) != state['executable_sha256']:
                raise ValueError('게임 실행 파일이 변경되었습니다. 다시 준비해 주세요.')
            wad = self.root / 'dependencies/freedoom-0.13.0/freedoom1.wad'
            self.process = subprocess.Popen([str(executable), '-iwad', str(wad), '-window', '-width', '960',
                '-height', '600', '-nomouse', '-config', str(folder / 'settings.cfg'), '-extraconfig', str(folder / 'extra.cfg'),
                '-savedir', str(folder / 'saves')], cwd=folder,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            return {'message': '게임을 실행했습니다. 방향키로 이동하고 Ctrl로 발사합니다. F2 저장 · F3 불러오기 · Esc 메뉴.'}
