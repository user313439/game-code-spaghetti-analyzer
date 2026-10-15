import importlib
import importlib.util
import io
import json
import stat
import zipfile

import pytest


def inputs():
    assert importlib.util.find_spec('game_si.web') is not None, 'Local web feature is missing'
    return importlib.import_module('game_si.web.inputs')


def archive(rows):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as z:
        for name, text in rows:
            z.writestr(name, text)
    data.seek(0)
    return data


@pytest.mark.parametrize('name', ['../x.c', '/x.c', 'C:/x.c', 'a/../../x.c',
                                  'a\\x.c', 'a:x.c', 'CON.c', 'a/NUL', 'a./x.c', 'x.c '])
def test_unsafe_relative_paths_are_rejected(name):
    with pytest.raises(ValueError):
        inputs().safe_relative(name)


def test_valid_unicode_relative_path():
    assert inputs().safe_relative('게임/src/main.cpp').as_posix() == '게임/src/main.cpp'


@pytest.mark.parametrize('name', ['COM¹.c', 'LPT².c', 'COM³.h'])
def test_windows_superscript_devices_rejected(name):
    with pytest.raises(ValueError):
        inputs().safe_relative(name)


def test_cancelled_import_never_opens_connection(tmp_path, monkeypatch):
    monkeypatch.setattr('urllib.request.OpenerDirector.open', lambda *a, **k: pytest.fail('Cancelled request connected'))
    with pytest.raises(ValueError, match='중단'):
        inputs().fetch_repository('https://github.com/a/b', tmp_path, cancelled=lambda: True)


def test_zip_extract_preserves_source_and_omits_non_source(tmp_path):
    inputs().extract_zip(archive([('repo/src/main.c', 'int Tick(){return 1;}'),
                                 ('repo/.env', 'secret'), ('repo/.git/config', 'private'),
                                 ('repo/README.md', 'doc')]), tmp_path)
    assert (tmp_path / 'repo/src/main.c').exists()
    assert not (tmp_path / 'repo/.env').exists()
    assert not (tmp_path / 'repo/.git/config').exists()
    scan = inputs().inspect_source(tmp_path)
    assert scan['languages'] == {'csharp': 0, 'c': 1, 'cpp': 0}
    assert 'repo/src' in scan['folders']


def test_zip_traversal_never_writes_outside(tmp_path):
    with pytest.raises(ValueError):
        inputs().extract_zip(archive([('../escape.c', 'bad')]), tmp_path / 'input')
    assert not (tmp_path / 'escape.c').exists()


def test_zip_duplicate_case_and_symlink_rejected(tmp_path):
    with pytest.raises(ValueError):
        inputs().extract_zip(archive([('a.c', 'a'), ('A.c', 'b')]), tmp_path)
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as z:
        info = zipfile.ZipInfo('link.c')
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(info, '../outside')
    data.seek(0)
    with pytest.raises(ValueError):
        inputs().extract_zip(data, tmp_path)


def test_zip_actual_size_and_corruption(tmp_path, monkeypatch):
    module = inputs()
    monkeypatch.setattr(module, 'MAX_SOURCE_BYTES', 2)
    with pytest.raises(ValueError):
        module.extract_zip(archive([('a.c', '123')]), tmp_path)
    with pytest.raises(ValueError):
        module.extract_zip(io.BytesIO(b'notzip'), tmp_path)


@pytest.mark.parametrize('url', ['http://github.com/a/b', 'https://github.com.evil/a/b',
                                'https://github.com/a/b/tree/main', 'https://u@github.com/a/b',
                                'https://github.com/a/b?x=1', 'https://github.com:443/a/b',
                                'https://127.0.0.1/a/b', 'https://github.com/a/../b'])
def test_repository_url_validation(url):
    with pytest.raises(ValueError):
        inputs().parse_repository(url)


def test_repository_url_accepts_git_suffix():
    assert inputs().parse_repository('https://github.com/id-Software/DOOM-3.git') == ('id-Software', 'DOOM-3')


def test_download_redirect_is_allowlisted():
    module = inputs()
    handler = module.GitHubRedirect()
    import urllib.request
    req = urllib.request.Request('https://api.github.com/repos/a/b/zipball/abc')
    with pytest.raises(ValueError):
        handler.redirect_request(req, None, 302, '', {}, 'http://127.0.0.1/private')


def test_source_inspection_rejects_no_implementation(tmp_path):
    (tmp_path / 'only.h').write_text('int f();')
    with pytest.raises(ValueError, match='소스'):
        inputs().inspect_source(tmp_path)


def test_source_bytes_include_headers_but_not_artifacts(tmp_path):
    for name, data in [('game.c', b'int f(){return 1;}'), ('game.h', b'int f();'),
                       ('readme.md', b'ignored'), ('build/generated.cpp', b'ignored')]:
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
    scan = inputs().inspect_source(tmp_path)
    assert scan['source_bytes'] == len(b'int f(){return 1;}int f();')
    assert scan['languages'] == {'csharp': 0, 'c': 1, 'cpp': 0}


def test_corrupt_deflate_is_a_readable_error(tmp_path):
    import struct
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('game.c', 'int Tick(){return 0;}')
    data = bytearray(raw.getvalue())
    offset = 30 + struct.unpack_from('<H', data, 26)[0] + struct.unpack_from('<H', data, 28)[0]
    data[offset] = 255
    with pytest.raises(ValueError, match='ZIP'):
        inputs().extract_zip(io.BytesIO(data), tmp_path)


def test_corrupt_lzma_is_a_readable_error(tmp_path):
    import struct
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, 'w', compression=zipfile.ZIP_LZMA) as z:
        z.writestr('game.c', 'int Tick(){return 0;}')
    data = bytearray(raw.getvalue())
    offset = 30 + struct.unpack_from('<H', data, 26)[0] + struct.unpack_from('<H', data, 28)[0]
    data[offset + 4] = 255
    with pytest.raises(ValueError, match='ZIP'):
        inputs().extract_zip(io.BytesIO(data), tmp_path)
