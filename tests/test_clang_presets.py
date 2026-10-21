"""Build settings the app keeps for its demo game: recognised only for the prepared original source."""
import json
import shutil

import pytest

from game_si.web import clang_presets


@pytest.fixture
def preset(tmp_path, monkeypatch):
    original = tmp_path / 'prepared' / 'src'
    original.mkdir(parents=True)
    (original / 'main.c').write_text('int main(void) { return 0; }\n', encoding='utf8')
    (original / 'game.h').write_text('int game(void);\n', encoding='utf8')
    monkeypatch.setitem(clang_presets.PRESETS, 'demo', {**clang_presets.PRESETS['opentyrian'], 'name': 'Demo', 'baseline': original})
    monkeypatch.setattr(clang_presets, 'toolchain_includes', lambda: [tmp_path / 'msvc' / 'include'])
    return original


def test_only_the_identical_source_is_recognised(tmp_path, preset):
    job = tmp_path / 'job' / 'input'
    shutil.copytree(preset.parent, job / 'Game')
    assert {'key': 'demo', 'name': 'Demo', 'folder': 'Game/src'} in clang_presets.detect(job)
    assert clang_presets.match(job / 'Game')['folder'] == 'src'
    (job / 'Game/src/main.c').write_text('int main(void) { return 1; }\n', encoding='utf8')   # edited copy
    assert not any(hit['key'] == 'demo' for hit in clang_presets.detect(job))


def test_database_lists_every_implementation_file_with_the_preset_options(tmp_path, preset):
    out = clang_presets.write_database(preset, 'demo', tmp_path / 'compile_commands.json')
    entries = json.loads(out.read_text('utf8'))
    assert [e['file'] for e in entries] == ['main.c'] and entries[0]['directory'] == str(preset)
    args = entries[0]['arguments']
    assert '-std=c17' in args and '-DTARGET_WIN32' in args and any(a.endswith('SDL2-2.32.10/include') for a in args)


def test_revision_database_moves_paths_to_the_copy(tmp_path, preset):
    copy = tmp_path / 'rev' / 'source'
    shutil.copytree(preset, copy)
    preset_db = clang_presets.revision_database({'preset': 'demo', 'preset_folder': '.'}, preset, copy, tmp_path / 'a.json')
    assert json.loads(preset_db.read_text('utf8'))[0]['directory'] == str(copy)
    own = tmp_path / 'own.json'   # a compile_commands.json the user supplied for their own project
    own.write_text(json.dumps([{'directory': str(preset), 'file': str(preset / 'main.c'),
                                'arguments': ['clang', f'-I{preset.as_posix()}/include', '-c', str(preset / 'main.c')]}]), encoding='utf8')
    moved = json.loads(clang_presets.revision_database({'compile_commands': str(own)}, preset, copy, tmp_path / 'b.json').read_text('utf8'))[0]
    assert moved['directory'] == str(copy) and moved['file'] == str(copy / 'main.c')
    assert moved['arguments'][1] == f'-I{copy.as_posix()}/include'
