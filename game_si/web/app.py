"""Loopback-only HTTP endpoints; no arbitrary source or filesystem serving."""
from __future__ import annotations

from contextlib import asynccontextmanager
import json
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from . import diagnosis, inputs, tangle as tangle_measure
from .prescription import Prescriptions
from .jobs import BusyError, JobManager, REPO_ROOT
from .assistant_jobs import AssistantJobs
from .assistant import capabilities
from .demo import DemoGame
from .casual_demo import CasualDemo

STATIC = Path(__file__).parent / 'static'
APP_UI = STATIC / 'app'


def report_response(path: Path, theme: str | None = None, embedded: bool = False):
    theme = theme if theme in {'light', 'dark', 'blue'} else 'blue'
    if path.suffix != '.html' or (theme == 'dark' and not embedded):
        return FileResponse(path)
    document = path.read_text(encoding='utf-8')
    if '</head>' not in document:
        return FileResponse(path)
    css = (STATIC / 'report-light.css').read_text(encoding='utf-8') if theme != 'dark' else ''
    if theme == 'blue':
        css += '\n' + (STATIC / 'report-blue.css').read_text(encoding='utf-8')
    style = f'<style id="report-{theme}-preview">' + css + '</style>'
    if embedded:
        style += '<style>' + (STATIC / 'report-embed.css').read_text('utf8') + '</style>'
    document = document.replace('</body>', '<script id="report-layout-preview">' + (STATIC / 'report-embed.js').read_text('utf8') + '</script></body>')
    return HTMLResponse(document.replace('</head>', style + '</head>', 1))


EXAMPLES = {
    'openra-game': 'OpenRA.Game', 'openra-mods-common': 'OpenRA.Mods.Common',
    'chocolate-doom': 'Chocolate Doom', 'openrct2': 'OpenRCT2',
    'doom3-gameplay-clang': 'DOOM 3 · 컴파일 설정 기반 부분 분석',
    'openra-mods-cnc': 'OpenRA.Mods.Cnc', 'openra-mods-d2k': 'OpenRA.Mods.D2k',
    'openra-platforms-default': 'OpenRA.Platforms.Default', 'openra-server': 'OpenRA.Server',
}
EXAMPLE_PROJECTS = {
    'OpenRA': dict(genre='실시간 전략 (RTS)', language='C#',
                   description='Command & Conquer, Red Alert, Dune 2000 같은 고전 RTS를 재구현하는 오픈소스 프로젝트입니다.',
                   focus='엔진과 공통 게임 로직의 구조·의존성·검토 순위를 살펴볼 수 있습니다.'),
    'Chocolate Doom': dict(genre='고전 FPS', language='C',
                           description='고전 DOS Doom의 동작을 재현하는 소스 포트입니다.',
                           focus='src 구현 파일의 구조·복잡도·전역 상태 지표를 살펴볼 수 있습니다.'),
    'OpenRCT2': dict(genre='테마파크 경영 시뮬레이션', language='C++',
                     description='RollerCoaster Tycoon 2를 바탕으로 한 오픈소스 프로젝트입니다.',
                     focus='코어 구현 파일의 구조·의존성과 상대 검토 순위를 살펴볼 수 있습니다.'),
    'DOOM 3': dict(genre='FPS', language='C++',
                   description='id Software의 공식 DOOM 3 소스 코드입니다.',
                   focus='게임플레이 코드를 Clang으로 부분 분석한 결과와 진단·분석 한계를 확인할 수 있습니다.'),
}
EXAMPLE_SCOPES = {
    'openra-game': ('OpenRA', 'OpenRA.Game · 엔진'),
    'openra-mods-common': ('OpenRA', 'OpenRA.Mods.Common · 공통 게임 로직'),
    'chocolate-doom': ('Chocolate Doom', 'src · 구현 파일'),
    'openrct2': ('OpenRCT2', 'src/openrct2 · 코어 (UI·Android 제외)'),
    'doom3-gameplay-clang': ('DOOM 3', 'neo/game · 게임플레이 · Clang'),
}


class BodyLimitError(ValueError):
    pass


class LocalOnlyMiddleware:
    def __init__(self, app, token):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = {k.decode('latin1').lower(): v.decode('latin1') for k, v in scope['headers']}
        host = headers.get('host', '')
        origin = headers.get('origin')
        valid = bool(re.fullmatch(r'(127\.0\.0\.1|localhost)(:[0-9]{1,5})?', host))
        valid = valid and (not origin or origin == 'http://' + host)
        valid = valid and headers.get('sec-fetch-site') != 'cross-site'
        if scope['method'] not in {'GET', 'HEAD'}:
            valid = valid and secrets.compare_digest(headers.get('x-game-si-token', ''), self.token)
        if not valid:
            return await JSONResponse({'detail': '이 PC의 프로그램 화면에서 다시 시도해 주세요.'}, 403)(scope, receive, send)
        limit = (64 * 1024 if headers.get('content-type', '').startswith('application/json')
                 else inputs.MAX_SOURCE_BYTES + 32 * 1024 * 1024)
        try:
            length = int(headers.get('content-length', '0'))
        except ValueError:
            length = limit + 1
        if length < 0 or length > limit:
            return await JSONResponse({'detail': '업로드 요청 용량이 너무 큽니다.'}, 413)(scope, receive, send)
        total = 0

        async def bounded_receive():
            nonlocal total
            message = await receive()
            total += len(message.get('body', b''))
            if total > limit:
                raise BodyLimitError('업로드 요청 용량이 너무 큽니다.')
            return message

        async def secure_send(message):
            if message['type'] == 'http.response.start':
                report = scope['path'].startswith(('/results/', '/examples/')) or (scope['path'].startswith('/revisions/') and scope['path'].endswith('.html'))
                csp = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                       "img-src data:; sandbox allow-scripts allow-downloads; base-uri 'none'; form-action 'none'"
                       if report else "default-src 'self'; script-src 'self'; style-src 'self'; "
                       "img-src 'self' data:; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'")
                message['headers'] = list(message.get('headers', [])) + [
                    (b'content-security-policy', csp.encode()), (b'x-content-type-options', b'nosniff'),
                    (b'referrer-policy', b'no-referrer'), (b'cache-control', b'no-store')]
            await send(message)
        await self.app(scope, bounded_receive, secure_send)


class RepositoryRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    url: str = Field(max_length=500)
    name: str = Field(default='', max_length=100)


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    lang: str = Field(default='auto', max_length=20)
    subdir: str = Field(default='.', max_length=1024)
    backend: str = Field(default='tree-sitter', max_length=20)
    local_path: str = Field(default='', max_length=2048)
    compile_commands: str = Field(default='', max_length=2048)
    clang_library: str = Field(default='', max_length=2048)


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: str = Field(max_length=20)
    service: str = Field(max_length=20)
    mode: str = Field(max_length=10)
    candidate: str = Field(default='', max_length=2048)
    candidates: list[Annotated[str, Field(max_length=2048)]] = Field(default_factory=list, max_length=5)
    model: str = Field(default='', max_length=100)
    api_key: str = Field(default='', max_length=500, repr=False)
    use_prescription: bool = False
    direct: bool = False


class PlayRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ok: bool
    note: str = Field(default='', max_length=300)


class PrescriptionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    service: str = Field(max_length=20)
    mode: str = Field(max_length=10)
    model: str = Field(default='', max_length=100)
    api_key: str = Field(default='', max_length=500, repr=False)


class ApplyRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    preview_id: str = Field(max_length=32)


class DemoLaunchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: str = Field(max_length=10)


def create_app(jobs_root: Path | None = None) -> FastAPI:
    token = secrets.token_hex(32)
    manager = JobManager(jobs_root or REPO_ROOT / '.cache/web/jobs')
    assistant = AssistantJobs(manager)
    prescriptions = Prescriptions(assistant, current=lambda ident: (assistant.current_result(ident), assistant.current_revision(ident), assistant.base_source(ident)))
    assistant.prescriptions = prescriptions
    demo = DemoGame(assistant)
    casual_demo = CasualDemo(assistant)
    maintenance_demo = CasualDemo(assistant, REPO_ROOT / 'docs/_demo_phase_v3')
    def demo_for(ident):
        if maintenance_demo.registered(ident):
            return maintenance_demo
        return casual_demo if casual_demo.registered(ident) else demo

    @asynccontextmanager
    async def lifespan(app):
        yield
        prescriptions.close()
        assistant.close()
        manager.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.manager = manager
    app.state.assistant = assistant
    app.state.prescriptions = prescriptions
    app.state.demo = demo
    app.state.casual_demo = casual_demo
    app.state.maintenance_demo = maintenance_demo
    app.add_middleware(LocalOnlyMiddleware, token=token)

    @app.exception_handler(ValueError)
    async def bad_input(request, exc):
        code = 413 if isinstance(exc, BodyLimitError) else 409 if isinstance(exc, BusyError) else 400
        return JSONResponse({'detail': str(exc)}, status_code=code)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({'detail': '작업 또는 결과를 찾지 못했습니다.'}, status_code=404)

    @app.get('/')
    def home():
        return FileResponse(APP_UI / 'index.html', media_type='text/html; charset=utf-8')

    @app.get('/ui/{filename}')
    def ui_asset(filename: str):
        if not re.fullmatch(r'[a-z0-9-]+\.(js|css)', filename) or not (APP_UI / filename).is_file():
            raise KeyError(filename)
        media = 'text/javascript' if filename.endswith('.js') else 'text/css'
        return FileResponse(APP_UI / filename, media_type=f'{media}; charset=utf-8')

    @app.get('/api/session')
    def session():
        return {'token': token, 'limits': {'archive_bytes': inputs.MAX_ARCHIVE_BYTES,
                                         'source_bytes': inputs.MAX_SOURCE_BYTES, 'files': inputs.MAX_FILES}}

    @app.get('/workspace/{ident}')
    def workspace(ident: str):
        # Links saved from the previous UI open the same analysis in the redesigned app; the
        # diagnosis page itself explains an analysis that has not finished yet.
        if not re.fullmatch('[a-f0-9]{32}', ident):
            raise KeyError(ident)
        manager.get(ident)
        return RedirectResponse(f'/#/job/{ident}/diagnosis', status_code=307)

    @app.get('/api/assistant/connections')
    def connections():
        return capabilities()

    @app.get('/api/jobs/{ident}/assistant/candidates')
    def candidates(ident: str):
        return assistant.candidates(ident)

    @app.get('/api/jobs/{ident}/assistant')
    def assistant_state(ident: str):
        state = assistant.get(ident)
        # A preview made on another round can no longer be applied; the page asks for a new one.
        state['preview_stale'] = bool(state.get('preview')) and state.get('base_revision') != assistant.current_revision(ident)
        return state

    @app.get('/api/jobs/{ident}/assistant/review')
    def assistant_review(ident: str):
        return assistant.reviews.get(ident)

    @app.post('/api/jobs/{ident}/assistant', status_code=202)
    def generate_advice(ident: str, body: AssistantRequest):
        return assistant.start(ident, body.model_dump())

    @app.post('/api/jobs/{ident}/assistant/apply', status_code=202)
    def apply_advice(ident: str, body: ApplyRequest):
        return assistant.apply(ident, body.preview_id)

    @app.post('/api/jobs/{ident}/assistant/cancel')
    def cancel_advice(ident: str):
        return assistant.cancel(ident)

    @app.get('/api/jobs/{ident}/demo')
    def demo_state(ident: str):
        manager.get(ident)
        return demo_for(ident).get(ident)

    @app.post('/api/jobs/{ident}/demo/prepare', status_code=202)
    def prepare_demo(ident: str):
        return demo_for(ident).prepare(ident)

    @app.post('/api/jobs/{ident}/demo/launch')
    def launch_demo(ident: str, body: DemoLaunchRequest):
        return demo_for(ident).launch(ident, body.version)

    @app.get('/revisions/{ident}/{revision}/{filename}')
    def revision_result(ident: str, revision: str, filename: str, theme: str | None = None):
        assistant.folder(ident)
        if not re.fullmatch('[a-f0-9]{32}', revision) or filename not in {'index.html', 'modified-source.zip', 'comparison.json'}:
            raise KeyError(filename)
        folder = manager.directory(ident) / 'revisions' / revision
        path = folder / ('result/index.html' if filename == 'index.html' else filename)
        if not path.is_file():
            raise KeyError(filename)
        return report_response(path, theme) if filename == 'index.html' else FileResponse(path)

    @app.get('/api/jobs')
    def history(include_deleted: bool = False):
        return manager.list(include_deleted=include_deleted)

    def result_folder(ident, revision=None):
        record = manager.get(ident)
        if record['state'] not in {'complete', 'partial'}:
            raise BusyError('분석이 끝난 뒤 진단을 볼 수 있습니다.')
        folder = manager.directory(ident) / 'result'
        if revision is not None:
            if not re.fullmatch('[a-f0-9]{32}', revision):
                raise ValueError('올바르지 않은 수정본 번호입니다.')
            folder = manager.directory(ident) / 'revisions' / revision / 'result'
        if not (folder / 'scoring.json').is_file() or not (folder / 'metrics.json').is_file():
            raise KeyError('result')
        return folder

    @app.get('/api/jobs/{ident}/diagnosis')
    def job_diagnosis(ident: str, revision: str | None = None):
        folder = result_folder(ident, revision)
        current = None
        if revision is None:
            current = assistant.current_revision(ident)
            if current:
                folder = result_folder(ident, current)
        data = dict(diagnosis.load(folder))
        rounds = assistant.rounds(ident)
        data['round'] = rounds['current'] if revision is None else next((r['round'] for r in rounds['rounds'] if r['revision'] == revision), None)
        data['revision'] = current if revision is None else revision
        return data

    @app.get('/api/jobs/{ident}/prescription')
    def job_prescription(ident: str):
        assistant.folder(ident)
        return prescriptions.get(ident)

    @app.post('/api/jobs/{ident}/prescription', status_code=202)
    def start_prescription(ident: str, body: PrescriptionRequest):
        assistant.folder(ident)
        return prescriptions.start(ident, body.model_dump())

    @app.post('/api/jobs/{ident}/prescription/cancel')
    def cancel_prescription(ident: str):
        assistant.folder(ident)
        return prescriptions.cancel(ident)

    @app.get('/api/jobs/{ident}/tangle')
    def job_tangle(ident: str):
        def measured(folder):
            return tangle_measure.measure(json.loads((folder / 'metrics.json').read_text('utf8')))
        base = measured(result_folder(ident))
        data = assistant.rounds(ident)
        rounds = [{'round': 0, 'revision': None, 'active': True, **tangle_measure.compare(base, base)}]
        for item in data['rounds']:
            folder = result_folder(ident, item['revision'])
            rounds.append({'round': item['round'], 'revision': item['revision'], 'active': item['round'] <= data['current'],
                           **tangle_measure.compare(base, measured(folder))})
        return {'rounds': rounds, 'current': data['current']}

    @app.get('/api/jobs/{ident}/rounds')
    def job_rounds(ident: str):
        data = assistant.rounds(ident)
        for item in data['rounds']:
            path = manager.directory(ident) / 'revisions' / item['revision'] / 'comparison.json'
            item['comparison'] = json.loads(path.read_text('utf8')) if path.is_file() else None
        return data

    @app.post('/api/jobs/{ident}/rounds/undo')
    def undo_round(ident: str):
        return assistant.undo_round(ident)

    @app.post('/api/jobs/{ident}/rounds/{number}/play')
    def confirm_play(ident: str, number: int, body: PlayRequest):
        return assistant.record_check(ident, number, 'play', {'ok': body.ok, 'note': body.note, 'at': time.time()})

    @app.get('/api/jobs/{ident}')
    def job(ident: str):
        return manager.get(ident)

    @app.post('/api/import/github', status_code=202)
    def github(body: RepositoryRequest):
        owner, repo = inputs.parse_repository(body.url)
        job = manager.create(body.name or repo, 'github', reserve_import=True)

        def import_source():
            try:
                source = inputs.fetch_repository(body.url, manager.directory(job['id']) / 'input',
                                                 cancelled=lambda: manager.closed or job['id'] in manager.cancellations)
                manager.ready(job['id'], source)
            except (ValueError, OSError) as exc:
                manager.fail(job['id'], exc)
            finally:
                with manager.lock:
                    manager.import_workers.discard(job['id'])

        worker = threading.Thread(target=import_source, daemon=True)
        manager.threads.append(worker)
        worker.start()
        return job

    @app.post('/api/import/files', status_code=201)
    async def files(request: Request):
        async with request.form(max_files=inputs.MAX_FILES, max_fields=10, max_part_size=24 * 1024 * 1024) as form:
            uploads = form.getlist('files')
            paths = json.loads(str(form.get('paths', '[]')))
            if (not uploads or not isinstance(paths, list) or len(paths) != len(uploads)
                    or len(paths) > inputs.MAX_FILES or not all(isinstance(p, str) for p in paths)):
                raise ValueError('ZIP 또는 소스 폴더를 다시 선택해 주세요.')
            seen = set()
            for name in paths:
                inputs.safe_relative(name)
                if name.casefold() in seen:
                    raise ValueError('이름이 중복되는 파일이 있습니다.')
                seen.add(name.casefold())
            if not all(hasattr(f, 'read') for f in uploads):
                raise ValueError('파일 업로드 형식을 확인해 주세요.')
            is_zip = len(paths) == 1 and paths[0].lower().endswith('.zip')
            label = paths[0].split('/')[0]
            name = str(form.get('name', ''))[:100] or label
            created = manager.create(name, 'zip' if is_zip else 'folder', reserve_import=True)
            ident = created['id']
            destination = manager.directory(ident) / 'input'
            def cancelled():
                return manager.closed or ident in manager.cancellations
            def check_cancelled():
                if cancelled():
                    raise ValueError('소스 가져오기가 중단되었습니다.')
            def copy_inputs():
                total = 0
                if is_zip:
                    archive = manager.directory(ident) / 'upload.zip'
                    with archive.open('xb') as output:
                        while chunk := uploads[0].file.read(64 * 1024):
                            check_cancelled()
                            total += len(chunk)
                            if total > inputs.MAX_ARCHIVE_BYTES:
                                raise ValueError('ZIP은 100 MiB 이하로 준비해 주세요.')
                            output.write(chunk)
                    inputs.extract_zip(archive, destination, cancelled=cancelled)
                else:
                    for upload, relative in zip(uploads, paths):
                        check_cancelled()
                        if not inputs.is_source(relative):
                            continue
                        path = inputs.target_path(destination, relative)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        with path.open('xb') as output:
                            while chunk := upload.file.read(64 * 1024):
                                check_cancelled()
                                total += len(chunk)
                                if total > inputs.MAX_SOURCE_BYTES:
                                    raise ValueError('소스 용량이 1 GiB를 초과합니다.')
                                output.write(chunk)
                manager.ready(ident)
            try:
                await run_in_threadpool(copy_inputs)
                return manager.get(ident)
            except (ValueError, OSError) as exc:
                manager.fail(ident, exc)
                raise ValueError(str(exc)) from exc
            finally:
                with manager.lock:
                    manager.import_workers.discard(ident)

    @app.post('/api/jobs/{ident}/start', status_code=202)
    def start(ident: str, options: AnalysisRequest):
        manager.start(ident, options.model_dump())
        return manager.get(ident)

    @app.post('/api/jobs/{ident}/cancel', status_code=202)
    def cancel(ident: str):
        manager.cancel(ident)
        return manager.get(ident)

    @app.post('/api/jobs/{ident}/delete')
    def delete(ident: str):
        record = manager.get(ident)
        if record['state'] in {'complete', 'partial'} and (assistant.get(ident)['state'] == 'running' or assistant.reviews.busy(ident)
                                                           or prescriptions.busy(ident)):
            raise BusyError('AI 작업이 끝난 뒤 기록을 삭제해 주세요.')
        return manager.delete(ident)

    @app.post('/api/jobs/{ident}/restore')
    def restore(ident: str):
        return manager.restore(ident)

    @app.get('/results/{ident}/{filename}')
    def result(ident: str, filename: str, theme: str | None = None, embedded: bool = False):
        if filename not in {'index.html', 'scoring.json', 'analysis_status.json'}:
            raise KeyError(filename)
        record = manager.get(ident)
        path = manager.directory(ident) / 'result' / filename
        if record['state'] not in {'complete', 'partial'} or not path.is_file():
            raise KeyError(ident)
        return report_response(path, theme, embedded=embedded)

    @app.get('/api/examples')
    def examples():
        result = []
        for slug, name in EXAMPLES.items():
            folder = REPO_ROOT / 'reports' / slug
            if not (folder / 'index.html').is_file():
                continue
            project, scope = EXAMPLE_SCOPES.get(slug, ('OpenRA', name + ' · 보조 모듈'))
            try:
                state = json.loads((folder / 'analysis_status.json').read_text(encoding='utf-8'))['state']
            except (OSError, ValueError, KeyError):
                state = None
            scope += ' · 부분 분석' if state == 'partial' else ' · 분석 완료' if state == 'complete' else ''
            result.append(dict(name=name, url=f'/examples/{slug}/index.html', project=project,
                               scope=scope, auxiliary=slug not in EXAMPLE_SCOPES, **EXAMPLE_PROJECTS[project]))
        return result

    @app.get('/examples/{slug}/{filename}')
    def example(slug: str, filename: str, theme: str | None = None):
        if slug not in EXAMPLES or filename not in {'index.html', 'validation.html', 'timeseries.html'}:
            raise KeyError(slug)
        path = REPO_ROOT / 'reports' / slug / filename
        if not path.is_file():
            raise KeyError(filename)
        return report_response(path, theme)

    return app
