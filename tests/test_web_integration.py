"""Real analyzer execution through the web-facing job manager."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

import pytest

pytest.importorskip('psutil')
from game_si.web.inputs import extract_zip
from game_si.web.jobs import JobManager


def completed(manager, ident, options):
    manager.ready(ident)
    manager.start(ident, options)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        job = manager.get(ident)
        if job['state'] != 'running':
            assert job['state'] == 'complete', job
            folder = manager.directory(ident) / 'result'
            return json.loads((folder / 'metrics.json').read_text(encoding='utf-8'))
        time.sleep(.05)
    pytest.fail('Web analysis timed out')


def test_zip_folder_and_cli_have_identical_metrics(tmp_path):
    manager = JobManager(tmp_path / 'jobs')
    text = 'int Tick(int x){if(x) return 1; return 0;}'
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, 'w') as z:
        z.writestr('game/main.c', text)
    try:
        first = manager.create('zip', 'zip')['id']
        extract_zip(io.BytesIO(raw.getvalue()), manager.directory(first) / 'input')
        a = completed(manager, first, {'lang': 'c'})
        second = manager.create('folder', 'folder')['id']
        folder = manager.directory(second) / 'input/game'
        folder.mkdir()
        (folder / 'main.c').write_text(text, encoding='utf-8')
        b = completed(manager, second, {'lang':'c'})
        direct = tmp_path / 'direct'
        result = subprocess.run([sys.executable, '-m', 'game_si', 'analyze', str(folder.parent),
            '--lang', 'c', '--out', str(direct)], capture_output=True, timeout=30)
        assert result.returncode == 0, result.stderr
        c = json.loads((direct / 'metrics.json').read_text(encoding='utf-8'))
        # Job IDs deliberately isolate input folders; only their provenance differs.
        assert a.pop('input_path') != b.pop('input_path')
        c.pop('input_path')
        assert a == b == c
    finally:
        manager.close()


def test_web_csharp_runs_existing_roslyn(tmp_path):
    if not (shutil.which('dotnet') or Path(r'C:\Program Files\dotnet\dotnet.exe').exists()):
        pytest.skip('The existing C# analyzer requires .NET')
    manager = JobManager(tmp_path)
    try:
        ident = manager.create('C# sample', 'folder')['id']
        (manager.directory(ident) / 'input/Game.cs').write_text(
            'public class Game { public int Tick(int x) { if(x>0) return x; return 0; } }', encoding='utf-8')
        assert completed(manager, ident, {'lang':'csharp'})
    finally:
        manager.close()


def test_web_clang_uses_original_source_scope(tmp_path):
    library = os.environ.get('GAME_SI_TEST_CLANG_LIBRARY')
    if not library or not Path(library).is_file():
        pytest.skip('Set GAME_SI_TEST_CLANG_LIBRARY for native integration')
    pytest.importorskip('clang.cindex')
    original = tmp_path / 'original'
    original.mkdir()
    source = original / 'game.cpp'
    source.write_text('int Tick(int x){if(x) return 1; return 0;}', encoding='utf-8')
    database = original / 'compile_commands.json'
    database.write_text(json.dumps([{'directory': str(original), 'file':'game.cpp',
        'arguments':['clang++','-std=c++17','game.cpp']}]), encoding='utf-8')
    manager = JobManager(tmp_path / 'jobs')
    try:
        ident = manager.create('Clang sample', 'folder')['id']
        copied = manager.directory(ident) / 'input/upload'
        copied.mkdir()
        (copied / 'game.cpp').write_bytes(source.read_bytes())
        assert completed(manager, ident, {'lang':'cpp', 'backend':'clang', 'local_path':str(original),
            'subdir':'.', 'compile_commands':str(database), 'clang_library':library})
    finally:
        manager.close()
