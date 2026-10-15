"""Browser-independent checks for the localhost upload and status UI."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest


STATIC = Path(__file__).resolve().parents[1] / 'game_si' / 'web' / 'static'


def test_report_sort_marker_does_not_replace_the_tooltip():
    source = (STATIC.parents[1] / 'report.py').read_text(encoding='utf-8')
    assert 'th.sortable::before {{ content: " ↕";' in source
    assert 'th.sortable::after {{ content: " ↕";' not in source


def run_js(body):
    source = STATIC / 'app.js'
    assert source.is_file(), 'The browser application has not been implemented'
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is needed to execute the browser-independent UI checks')
    script = (
        'const assert = require("node:assert/strict");\n'
        f'const ui = require({json.dumps(str(source))});\n'
        '(async () => {\n' + body + '\n})().catch(error => { '
        'console.error(error); process.exitCode = 1; });'
    )
    result = subprocess.run([node], input=script, text=True, encoding='utf-8', capture_output=True)
    assert result.returncode == 0, result.stderr


def run_browser_js(body, search='', examples=None):
    run_js('''
    class Element {
      constructor(tag = 'div') {
        this.tagName = tag; this.children = []; this.listeners = {};
        this.attributes = {}; this.value = ''; this.textContent = ''; this.hidden = false;
        this.classList = {toggle() {}, add() {}, remove() {}};
      }
      append(...children) { this.children.push(...children); }
      replaceChildren(...children) { this.children = children; }
      setAttribute(name, value) { this.attributes[name] = value; }
      getAttribute(name) { return this.attributes[name]; }
      removeAttribute(name) { delete this.attributes[name]; }
      addEventListener(name, handler) { this.listeners[name] = handler; }
      focus() {}
      showModal() {}
      click() { return this.listeners.click?.({target:this}); }
    }
    const elements = new Map();
    const element = id => {
      if (!elements.has(id)) elements.set(id, new Element());
      return elements.get(id);
    };
    global.document = {documentElement:new Element('html'), getElementById:element, querySelectorAll:() => [],
      createElement:tag => new Element(tag), createElementNS:(_, tag) => new Element(tag)};
    global.window = {listeners:{}, addEventListener(name, handler) { this.listeners[name] = handler; }};
    global.location = {hash:'#history', search:''' + json.dumps(search) + '''};
    const job = id => ({id, name:id, state:'ready', created_at:1, can_delete:true,
      deleted_at:null, source:{}, scan:{languages:{c:1}, folders:['.'], source_bytes:1}});
    const jobs = [job('a'), job('b')], requests = new Map();
    const response = data => ({ok:true, json:async () => data});
    global.fetch = async (url, options = {}) => {
      if (url === '/api/session') return response({token:'session', limits:{}});
      if (url === '/api/jobs?include_deleted=true') return response(jobs);
      if (url === '/api/examples') return response(''' + json.dumps(examples or []) + ''');
      if (options.method === 'POST') return response({...job('b'), deleted_at:1});
      return new Promise(resolve => requests.set(url, data => resolve(response(data))));
    };
    const source = require.resolve(''' + json.dumps(str(STATIC / 'app.js')) + ''');
    delete require.cache[source];
    require(source);
    const flush = () => new Promise(resolve => setImmediate(resolve));
    await flush();
    const buttons = () => element('history-list').children.map(row => row.children[1].children);
    const resolveJob = id => requests.get(`/api/jobs/${id}`)(job(id));
    ''' + body)


@pytest.mark.parametrize('search,expected', [('', 'blue'), ('?theme=invalid', 'blue'), ('?theme=blue', 'blue'), ('?theme=dark', 'dark'), ('?theme=light', None)])
def test_blue_default_theme_preserves_explicit_white_and_dark(search, expected):
    run_browser_js('''
    assert.equal(document.documentElement.getAttribute('data-preview-theme'),
      ''' + ('undefined' if expected is None else json.dumps(expected)) + ''');
    ''', search=search)


def test_dark_preview_colors_match_the_existing_report_palette():
    css = (STATIC / 'app.css').read_text(encoding='utf-8')
    assert 'html[data-preview-theme="dark"]' in css
    preview = css.split('html[data-preview-theme="dark"]', 1)[1]
    for declaration in ['--bg:#0f172a', '--surface:#111827', '--ink:#e5e7eb', '--muted:#94a3b8', '--teal:#60a5fa']:
        assert declaration in preview
    assert ':root{--bg:#f7f8f6' in css
    assert 'html[data-preview-theme="dark"] .collection-item{background:var(--surface)}' in css


def test_dark_preview_has_readable_helpers_and_distinct_control_boundaries():
    css = (STATIC / 'app.css').read_text(encoding='utf-8')
    preview = css.split('/* Opt-in preview', 1)[1]
    assert 'border-color:#64748b;color:var(--ink)' in preview
    assert 'box-shadow:inset 0 -2px 0 var(--teal)' in preview
    assert '.field-help{font-size:12px}' in preview
    assert '.collection-item p{font-size:13px}' in preview


def test_theme_links_remain_local_and_preserve_explicit_dark_results():
    run_js('''
    const path = '/examples/openra-game/index.html';
    assert.equal(ui.previewResultUrl(path, 'light'), path + '?theme=light');
    assert.equal(ui.previewResultUrl(path, 'dark'), path + '?theme=dark');
    assert.equal(ui.previewResultUrl(path, ''), path);
    assert.equal(ui.previewResultUrl(path, '<script>'), path);
    assert.equal(ui.previewResultUrl('https://evil.example/index.html', 'light'), null);
    assert.equal(ui.previewResultUrl(path + '?redirect=evil', 'light'), null);
    ''')


@pytest.mark.parametrize('theme', ['light', 'blue', 'dark', ''])
def test_white_preview_reaches_live_history_and_both_example_link_groups(theme):
    run_browser_js('''
    const theme = ''' + json.dumps(theme or 'blue') + ''';
    const selected = buttons()[0][0].click();
    requests.get('/api/jobs/a')({...job('a'),state:'complete',result_url:'/results/a/index.html'});
    await selected;
    assert.equal(element('result-link').href, '/results/a/index.html?theme=' + theme);
    jobs[0] = {...job('a'),state:'complete',result_url:'/results/a/index.html'};
    await element('refresh-history').click();
    assert.equal(buttons()[0][0].href, '/results/a/index.html?theme=' + theme);
    location.hash = '#examples'; window.listeners.hashchange(); await flush();
    const links = root => root.children.flatMap(child => child.tagName === 'a' ? [child.href] : links(child));
    assert.deepEqual(links(element('examples-list')), ['/examples/openra-game/index.html?theme=' + theme]);
    assert.deepEqual(links(element('auxiliary-list')), ['/examples/openra-server/index.html?theme=' + theme]);
    ''', search='?theme=' + theme if theme else '', examples=[
        {'name': 'OpenRA.Game', 'url': '/examples/openra-game/index.html', 'project': 'OpenRA', 'auxiliary': False},
        {'name': 'OpenRA.Server', 'url': '/examples/openra-server/index.html', 'project': 'OpenRA', 'auxiliary': True},
    ])


def test_blue_preview_is_a_separate_opt_in_version():
    run_browser_js('''
    assert.equal(document.documentElement.getAttribute('data-preview-theme'), 'blue');
    assert.equal(ui.previewResultUrl('/results/a/index.html', 'blue'), '/results/a/index.html?theme=blue');
    ''', search='?theme=blue')
    css = (STATIC / 'app.css').read_text(encoding='utf-8')
    assert 'html[data-preview-theme="blue"]' in css
    assert '--bg:#eaf2f9' in css and '--teal:#356d9b' in css
    assert 'html[data-preview-theme="blue"] :is(button,a,input,select,summary,[tabindex]):focus-visible{outline-color:var(--teal)}' in css


def test_latest_history_detail_selection_wins_out_of_order_responses():
    run_browser_js('''
    const first = buttons()[0][0].click();
    const second = buttons()[1][0].click();
    resolveJob('b'); await second;
    assert.equal(element('source-label').textContent, 'b');
    resolveJob('a'); await first;
    assert.equal(element('source-label').textContent, 'b');
    ''')


@pytest.mark.parametrize('action', ['reset', 'navigate', 'delete'])
def test_history_detail_response_cannot_override_later_action(action):
    run_browser_js('''
    const selected = buttons()[0][0].click();
    const action = ''' + json.dumps(action) + ''';
    if (action === 'reset') element('reset-button').click();
    if (action === 'navigate') {
      location.hash = '#examples'; window.listeners.hashchange();
    }
    if (action === 'delete') {
      buttons()[1][1].click();
      element('delete-dialog').returnValue = 'delete';
      element('delete-dialog').listeners.close();
    }
    await flush();
    const hash = location.hash;
    resolveJob('a'); await selected;
    assert.equal(location.hash, hash);
    assert.equal(element('import-form').hidden, false);
    ''')


def test_history_refresh_does_not_cancel_current_detail_selection():
    run_browser_js('''
    const selected = buttons()[0][0].click();
    await element('refresh-history').click();
    resolveJob('a'); await selected;
    assert.equal(element('source-label').textContent, 'a');
    assert.equal(location.hash, 'analyze');
    ''')


def test_front_page_has_two_accessible_inputs_and_local_assets():
    page = STATIC / 'index.html'
    assert page.is_file(), 'The localhost frontend has not been implemented'
    html = page.read_text(encoding='utf-8')
    assert '게임 코드를 더 명확하게.' in html
    assert 'Game Code Spaghetti Analyzer' in html
    assert html.count('role="tab"') == 2
    assert 'accept=".zip"' in html and 'webkitdirectory multiple' in html
    assert 'aria-live="polite"' in html
    assert '<details id="advanced-options">' in html
    assert '<form id="import-form" novalidate>' in html
    assert 'id="change-source-button"' in html
    assert 'app.css' in html and 'app.js' in html
    assert 'https://' not in html
    css = (STATIC / 'app.css').read_text(encoding='utf-8')
    assert 'prefers-reduced-motion' in css and ':focus-visible' in css
    assert 'innerHTML' not in (STATIC / 'app.js').read_text(encoding='utf-8')


def test_history_sorting_is_pure_and_uses_imported_source_size():
    run_js('''
    const jobs = [{id:'old',name:'B',created_at:1,scan:{source_bytes:200}},
      {id:'new',name:'B',created_at:4,scan:{source_bytes:200}},
      {id:'small',name:'A',created_at:2,scan:{source_bytes:10}},
      {id:'unknown',name:'Z',created_at:9,scan:null}];
    const before = JSON.stringify(jobs);
    assert.deepEqual(ui.sortJobs(jobs,'latest').map(j => j.id), ['unknown','new','small','old']);
    assert.deepEqual(ui.sortJobs(jobs,'name').map(j => j.id), ['small','new','old','unknown']);
    assert.deepEqual(ui.sortJobs(jobs,'size').map(j => j.id), ['new','old','small','unknown']);
    assert.equal(JSON.stringify(jobs), before);
    assert.equal(ui.formatSourceSize(null), '미확인');
    assert.equal(ui.formatSourceSize(undefined), '미확인');
    assert.equal(ui.formatSourceSize(1024), '1.0 KiB');
    assert.equal(ui.formatSourceSize(1048576), '1.0 MiB');
    assert.equal(ui.formatSourceSize(-1), '미확인');
    assert.equal(ui.formatSourceSize('200'), '미확인');
    assert.deepEqual(ui.sortJobs([{id:'a',created_at:1,scan:{source_bytes:1}},
      {id:'b',created_at:1,scan:{source_bytes:1}}], 'size').map(j => j.id), ['a','b']);
    ''')


def test_project_grouping_keeps_auxiliary_openra_modules_separate():
    run_js('''
    const examples = [{name:'engine',project:'OpenRA',auxiliary:false},
      {name:'common',project:'OpenRA',auxiliary:false},
      {name:'cnc',project:'OpenRA',auxiliary:true},
      {name:'doom',project:'Chocolate Doom',auxiliary:false}];
    const groups = ui.groupExamples(examples);
    assert.deepEqual(groups.projects.map(p => p.project), ['OpenRA','Chocolate Doom']);
    assert.equal(groups.projects[0].examples.length, 2);
    assert.equal(groups.auxiliary.length, 1);
    assert.equal(examples.length, 4);
    assert.equal(ui.safeResultUrl('/examples/openra-game/index.html'), '/examples/openra-game/index.html');
    assert.equal(ui.safeResultUrl('/api/session'), null);
    assert.equal(ui.safeResultUrl('/examples/../secret/index.html'), null);
    ''')


def test_history_and_local_explanation_controls_are_accessible():
    html = (STATIC / 'index.html').read_text(encoding='utf-8')
    for fragment in ['로컬 분석', 'role="tooltip"', 'aria-describedby="local-tooltip"',
                     'id="history-sort"', 'id="delete-dialog"', 'id="deleted-list"',
                     'id="undo-delete"', 'id="auxiliary-examples"']:
        assert fragment in html
    js = (STATIC / 'app.js').read_text(encoding='utf-8')
    assert 'createElementNS' in js and 'aria-label' in js and 'showModal()' in js


def test_folder_upload_filters_artifacts_and_keeps_relative_paths():
    run_js('''
    const file = (path, size = 10) => ({name: path.split('/').pop(), webkitRelativePath: path, size});
    const upload = ui.prepareUpload([
      file('Game/src/main.cpp'), file('Game/include/game.hpp'), file('Game/a.cs'),
      file('Game/.git/secret.c'), file('Game/node_modules/a.c'), file('Game/bin/a.c'),
      file('Game/obj/a.c'), file('Game/build/a.c'), file('Game/packages/a.c'),
      file('Game/.vs/a.c'), file('Game/.env'), file('Game/readme.md')
    ], 'folder');
    assert.deepEqual(upload.paths, ['Game/src/main.cpp', 'Game/include/game.hpp', 'Game/a.cs']);
    assert.equal(upload.skipped, 9);
    assert.equal(upload.bytes, 30);
    assert.throws(() => ui.prepareUpload([file('../escape.c')], 'folder'), /경로/);
    assert.throws(() => ui.prepareUpload([{name: 'main.c', size: 1}], 'folder'), /폴더/);
    ''')


def test_upload_limits_and_zip_selection_are_enforced():
    run_js('''
    assert.equal(ui.DEFAULT_LIMITS.archive_bytes, 100 * 1024 * 1024);
    assert.equal(ui.DEFAULT_LIMITS.source_bytes, 1024 * 1024 * 1024);
    assert.equal(ui.DEFAULT_LIMITS.files, 20000);
    assert.throws(() => ui.prepareUpload([{name:'a.zip', size:101}], 'zip', {archive_bytes:100}), /크기/);
    assert.throws(() => ui.prepareUpload([{name:'a.zip', size:1}, {name:'b.zip', size:1}], 'zip'), /하나/);
    assert.throws(() => ui.prepareUpload([{name:'a.rar', size:1}], 'zip'), /ZIP/);
    const f = {name:'a.c', webkitRelativePath:'Game/a.c', size:10};
    assert.throws(() => ui.prepareUpload([f], 'folder', {source_bytes:9}), /크기/);
    assert.throws(() => ui.prepareUpload([f, f], 'folder', {files:1}), /개수/);
    assert.throws(() => ui.prepareUpload([{name:'notes.txt', webkitRelativePath:'Game/notes.txt', size:1}], 'folder'), /소스/);
    ''')


def test_directory_drop_drains_every_reader_batch_and_preserves_paths():
    run_js('''
    const entry = i => ({isFile:true, name:`a${i}.c`, file: success => success({name:`a${i}.c`, size:1})});
    const batches = [Array.from({length:100}, (_,i) => entry(i)), [entry(100)], []];
    let reads = 0;
    const root = {isDirectory:true, name:'Game', createReader:() => ({readEntries:success => {reads++; success(batches.shift());}})};
    const files = await ui.readDroppedEntries([root]);
    assert.equal(reads, 3);
    assert.equal(files.length, 101);
    assert.equal(files[100].path, 'Game/a100.c');
    assert.equal(ui.prepareUpload(files, 'folder').paths[100], 'Game/a100.c');
    ''')


def test_directory_drop_stops_before_excluded_folders_and_excess_files():
    run_js('''
    const excluded = {isDirectory:true, name:'node_modules', createReader:() => {throw Error('must not read');}};
    assert.deepEqual(await ui.readDroppedEntries([excluded]), []);
    const file = {isFile:true, name:'a.c', file:ok => ok({name:'a.c', size:2})};
    await assert.rejects(() => ui.readDroppedEntries([file, file], {files:1}), /개수/);
    await assert.rejects(() => ui.readDroppedEntries([file], {source_bytes:1}), /크기/);
    ''')


def test_status_is_real_stage_and_elapsed_without_invented_percentages():
    run_js('''
    const running = ui.statusView({state:'running', stage:'클래스 추출', elapsed_seconds:65});
    assert.equal(running.title, '분석 중');
    assert.equal(running.stage, '클래스 추출');
    assert.equal(running.elapsed, '1분 5초');
    assert.equal(running.busy, true);
    assert.equal(running.result, false);
    assert.equal(ui.statusView({state:'partial', result_url:'/results/a/index.html'}).result, true);
    assert.equal(ui.statusView({state:'failed', result_url:'/results/a/index.html'}).result, false);
    assert.equal(ui.statusView({state:'interrupted'}).title, '분석 중단');
    assert.equal(ui.safeResultUrl('javascript:alert(1)'), null);
    assert.equal(ui.safeResultUrl('//other.example/result'), null);
    assert.equal(ui.safeResultUrl('https://other.example/result'), null);
    assert.equal(ui.safeResultUrl('/results/a/index.html'), '/results/a/index.html');
    ''')


def test_api_adds_session_token_to_all_posts_and_preserves_multipart_boundary():
    run_js('''
    const calls = [];
    const api = ui.createApi('session-token', async (url, options) => {
      calls.push({url, options}); return {ok:true, json:async () => ({id:'one'})};
    });
    await api('/api/jobs');
    await api('/api/jobs/one/start', {method:'POST', body:JSON.stringify({lang:'c'})});
    const multipart = {test:'form'};
    await api('/api/import/files', {method:'POST', body:multipart});
    assert.equal(calls[0].options.headers['X-Game-SI-Token'], undefined);
    assert.equal(calls[1].options.headers['X-Game-SI-Token'], 'session-token');
    assert.equal(calls[1].options.headers['Content-Type'], 'application/json');
    assert.equal(calls[2].options.headers['X-Game-SI-Token'], 'session-token');
    assert.equal(calls[2].options.headers['Content-Type'], undefined);
    const broken = ui.createApi('token', async () => ({ok:false, json:async () => ({error:'잘못된 요청'})}));
    await assert.rejects(() => broken('/api/jobs'), /잘못된 요청/);
    ''')


def test_api_preserves_readable_fastapi_errors_and_simplifies_validation_details():
    run_js('''
    const invalid = ui.createApi('token', async () => ({ok:false, json:async () => ({detail:'저장소 주소를 확인해 주세요.'})}));
    await assert.rejects(() => invalid('/api/import/github'), /저장소 주소를 확인해 주세요/);
    const validation = ui.createApi('token', async () => ({ok:false, json:async () => ({detail:[{loc:['body','url'], msg:'Field required', type:'missing'}]})}));
    await assert.rejects(() => validation('/api/import/github'), /입력값을 확인/);
    ''')


def test_history_timestamp_supports_backend_unix_seconds_and_iso_dates():
    run_js('''
    assert.equal(ui.jobDate(1791723600).getUTCFullYear(), 2026);
    assert.equal(ui.jobDate('2026-10-11T12:00:00Z').getUTCFullYear(), 2026);
    assert.equal(ui.jobDate(null), null);
    assert.equal(ui.jobDate('not-a-date'), null);
    ''')


def test_local_clang_scope_is_relative_to_original_root_and_failed_history_opens():
    run_js('''
    assert.equal(ui.buildAnalysisOptions({lang:'cpp', backend:'clang', subdir:'upload/src', local_path:'C:/Game', local_subdir:'src'}).subdir, 'src');
    assert.equal(ui.buildAnalysisOptions({lang:'cpp', backend:'clang', subdir:'repo-SHA/src', local_path:'C:/Game'}).subdir, '.');
    assert.equal(ui.buildAnalysisOptions({lang:'cpp', backend:'tree-sitter', subdir:'Game/src', local_path:'C:/Game'}).subdir, 'Game/src');
    assert.equal(ui.canInspectJob('failed'), true);
    assert.equal(ui.canInspectJob('interrupted'), true);
    ''')
    assert 'id="local-subdir"' in (STATIC / 'index.html').read_text(encoding='utf-8')
