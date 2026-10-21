"""Trusted OpenTyrian build/launch recipe; proposed code cannot choose commands."""
import difflib
from pathlib import Path
import json
import os
import shutil
import subprocess

from . import assistant as ai
from .demo import DemoGame, source_tree
from .jobs import BusyError, REPO_ROOT

MSBUILD = Path(r'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\MSBuild\Current\Bin\MSBuild.exe')


class CasualDemo(DemoGame):
    def __init__(self, assistant, root=None):
        super().__init__(assistant, root or REPO_ROOT / 'docs/_demo_phase_v2')
        self.prefixes = {}

    def _prefix(self, ident):
        """'' or 'src/' when the job's analysed source equals the demo's original source; None otherwise."""
        if ident not in self.prefixes:
            prefix = None
            try:
                baseline = source_tree(self.root / '01_original/source/src')
                root = self.assistant.source(ident)
                if source_tree(root) == baseline:
                    prefix = ''
                elif (root / 'src').is_dir() and source_tree(root / 'src') == baseline:
                    prefix = 'src/'
            except (OSError, ValueError, KeyError, AttributeError):
                return None   # e.g. analysis still running: decide again on the next request
            self.prefixes[ident] = prefix
        return self.prefixes[ident]

    def registered(self, ident):
        return super().registered(ident) or self._prefix(ident) is not None

    def get(self, ident):
        state = super().get(ident)
        if not state.get('available'):
            return state
        state.update(name='OpenTyrian · 우주선을 조종하는 캐주얼 비행 슈팅',
                     game_title='OpenTyrian', description='우주선을 조종하며 적을 피하고 물리치는 비행 슈팅 게임입니다.',
                     controls='방향키로 이동하고 Space를 누르고 있으면 연속 발사합니다. Enter로 메뉴 선택 · Esc로 뒤로 이동/게임 메뉴 · P로 일시 정지합니다. 게임 종료 후 다시 실행할 수 있습니다.')
        if state.get('revision') != self.current_revision(ident):
            state['verification_summary'] = '현재 수정본의 게임 준비와 동작 확인은 아직 완료되지 않았습니다. 이전 수정본의 검사 결과는 현재 수정본에 적용하지 않습니다.'
            return state
        verification = self.root / '02_modified' / state.get('revision', '-') / 'verification.json'
        if verification.is_file():
            data = json.loads(verification.read_text('utf8'))
            state['verification_summary'] = data.get('summary', '')
        else:
            state['verification_summary'] = ('빌드 완료를 확인했습니다. 직접 플레이 검증은 별도로 진행해 주세요.'
                if state['state'] == 'complete' else '게임 준비 후 빌드 결과와 확인한 동작을 표시합니다.')
        return state

    def _build(self, ident, state):
        revision = state['revision']
        folder = self.root / '02_modified' / revision
        try:
            self._save({'state':'running', 'revision':revision,
                        'progress':self._progress('copy', '시연 원본을 복사하고 있습니다.', 0)})
            source, build, game = folder/'source', folder/'build', folder/'game'
            if not source.exists():
                shutil.copytree(self.root/'01_original/source', source)
            self._save({'state':'running', 'revision':revision,
                        'progress':self._progress('validate', '적용된 변경과 시연 원본을 확인하고 있습니다.', 1)})
            baseline = self.root/'01_original/source/src'
            original_root = self.assistant.source(ident)
            revised = self.assistant.folder(ident)/'revisions'/revision/'source'
            self.verify(ident, revision)
            prefix = self._prefix(ident) or ''
            before, after = source_tree(original_root), source_tree(revised)
            if set(before) - set(after):
                raise ValueError('삭제된 소스 파일은 시연 빌드에서 지원하지 않습니다.')
            diffs = []
            # Every round builds on the previous one, so compare the whole current revision with the original.
            for rel, fingerprint in sorted(after.items()):
                if before.get(rel) == fingerprint:
                    continue
                if prefix and not rel.startswith(prefix):
                    raise ValueError('시연 게임 소스 밖의 파일이 바뀌어 빌드할 수 없습니다.')
                target = rel[len(prefix):]
                original = baseline / target
                if rel in before and ai.digest(original.read_bytes()) != before[rel]:
                    raise ValueError('시연 원본과 분석한 코드가 일치하지 않습니다.')
                if rel not in before and original.exists():
                    raise ValueError('새 파일이 시연 원본의 기존 파일과 겹칩니다.')
                destination = source/'src'/target
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(revised/rel, destination)
                old = original.read_text('utf8', errors='replace').splitlines(True) if rel in before else []
                diffs.append(''.join(difflib.unified_diff(old, (revised/rel).read_text('utf8', errors='replace').splitlines(True),
                                                          fromfile='원본/'+rel, tofile='수정본/'+rel)))
            build.mkdir(parents=True, exist_ok=True)
            sdl = self.root/'dependencies/SDL2-2.32.10'
            command = [str(MSBUILD), str(source/'visualc/opentyrian.vcxproj'), '/m:4',
                       '/p:Configuration=Release', '/p:Platform=x64', '/p:PlatformToolset=v143',
                       '/p:WITH_NETWORK=false', '/p:SDL2BaseDir='+str(sdl),
                       '/p:OutDir='+str(build)+'\\', '/p:IntDir='+str(build/'obj')+'\\', '/p:TargetName=opentyrian']
            self._save({'state':'running', 'revision':revision,
                        'progress':self._progress('build', '시연 게임을 빌드하고 있습니다.', 2)})
            with (folder/'build.log').open('wb') as log:
                process = subprocess.Popen(command, cwd=self.root, stdout=log, stderr=subprocess.STDOUT,
                                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                with ai.PROCESS_LOCK:
                    ai.PROCESSES.add(process)
                try:
                    process.wait(timeout=300)
                except subprocess.TimeoutExpired:
                    ai.terminate_process(process)
                    raise ValueError('게임 빌드 제한 시간을 초과했습니다. 빌드 기록을 확인해 주세요.')
                finally:
                    with ai.PROCESS_LOCK:
                        ai.PROCESSES.discard(process)
            if process.returncode or not (build/'opentyrian.exe').is_file():
                raise ValueError('게임 빌드에 실패했습니다. 시연 폴더의 build.log를 확인해 주세요.')
            self._save({'state':'running', 'revision':revision,
                        'progress':self._progress('package', '실행 파일과 분석 결과를 정리하고 있습니다.', 3)})
            game.mkdir(exist_ok=True)
            shutil.copy2(build/'opentyrian.exe', game/'opentyrian.exe')
            shutil.copy2(sdl/'lib/x64/SDL2.dll', game/'SDL2.dll')
            (game/'opentyrian.cfg').touch(exist_ok=True)
            shutil.copytree(self.assistant.folder(ident)/'revisions'/revision/'result', folder/'analysis', dirs_exist_ok=True)
            (folder/'changes.diff').write_text('\n'.join(diffs), encoding='utf8')
            self._save({'state':'complete', 'revision':revision,
                        'progress':self._progress('complete', '시연 게임 준비를 완료했습니다.', 4, False),
                        'executable_sha256':ai.digest((game/'opentyrian.exe').read_bytes()),
                        'message':'수정된 OpenTyrian 게임 빌드를 완료했습니다.'})
        except Exception as exc:
            self._save({'state':'failed','revision':revision,'error':str(exc) if isinstance(exc, ValueError)
                        else '게임 준비에 실패했습니다. 시연 폴더와 빌드 도구를 확인해 주세요.'})

    def launch(self, ident, version):
        with self.lock:
            state = self.get(ident)
            if not state.get('available') or state['state'] != 'complete' or version != 'modified':
                raise ValueError('변경안을 적용하고 수정된 시연 게임을 준비해 주세요.')
            if self.current_revision(ident) != state['revision']:
                raise ValueError('현재 수정본으로 게임을 다시 준비해 주세요.')
            if self.process and self.process.poll() is None:
                raise BusyError('실행 중인 게임을 종료한 뒤 다시 실행해 주세요.')
            game = self.root/'02_modified'/state['revision']/'game'
            executable = game/'opentyrian.exe'
            if ai.digest(executable.read_bytes()) != state['executable_sha256']:
                raise ValueError('실행 파일이 변경되었습니다. 게임을 다시 준비해 주세요.')
            env = os.environ.copy()
            env['SDL_RENDER_DRIVER'] = 'software'
            log = (game/'play.log').open('ab')
            try:
                self.process = subprocess.Popen([str(executable),'--no-joystick','--data='+str(self.root/'dependencies/data')],
                    cwd=game, env=env, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            finally:
                log.close()
            return {'message':'수정된 OpenTyrian을 실행했습니다. 게임에서 이동·발사 동작을 확인해 주세요. 조작 방법은 아래에서 펼쳐 볼 수 있습니다.'}
