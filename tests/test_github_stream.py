"""GitHub import streams the tar.gz archive and writes only source files (assets never reach the disk)."""
import io
import json
import tarfile

import pytest

from game_si.web import inputs

COMMIT = 'a' * 40


def tarball(rows, links=()):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w:gz') as tar:
        header = tarfile.TarInfo('pax_global_header')
        header.type = tarfile.XGLTYPE
        tar.addfile(header)
        for name, content in rows:
            raw = content if isinstance(content, bytes) else content.encode('utf8')
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            tar.addfile(info, io.BytesIO(raw))
        for name, target in links:
            info = tarfile.TarInfo(name)
            info.type = tarfile.SYMTYPE
            info.linkname = target
            tar.addfile(info)
    return data.getvalue()


def fake_github(monkeypatch, archive, seen=None):
    def open_(self, request, timeout=None):
        url = request.full_url
        if seen is not None:
            seen.append((url, timeout))
        if url.endswith('/repos/a/game'):
            return io.BytesIO(json.dumps({'private': False, 'default_branch': 'main'}).encode())
        if url.endswith('/commits/main'):
            return io.BytesIO(json.dumps({'sha': COMMIT}).encode())
        if url.endswith('/tarball/' + COMMIT):
            return io.BytesIO(archive)
        raise AssertionError(url)
    monkeypatch.setattr('urllib.request.OpenerDirector.open', open_)


def test_only_source_files_are_written(tmp_path, monkeypatch):
    big_asset = b'\0' * (3 * 1024 * 1024)     # stands for images and sounds
    seen = []
    fake_github(monkeypatch, tarball([('a-game-123/src/main.cpp', 'int main(){return 0;}'),
                                      ('a-game-123/src/game.h', 'struct Game;'),
                                      ('a-game-123/data/sprites.png', big_asset),
                                      ('a-game-123/.env', 'SECRET=1')],
                                     links=[('a-game-123/src/evil.c', '/etc/passwd')]), seen)
    result = inputs.fetch_repository('https://github.com/a/game', tmp_path / 'input')
    files = sorted(p.relative_to(tmp_path / 'input').as_posix() for p in (tmp_path / 'input').rglob('*') if p.is_file())
    assert files == ['a-game-123/src/game.h', 'a-game-123/src/main.cpp']
    assert result['commit'] == COMMIT and not (tmp_path / 'repository.zip').exists()
    assert any(url.endswith('/tarball/' + COMMIT) and timeout == 90 for url, timeout in seen)


def test_archives_over_the_old_100_mib_limit_are_fine_when_the_code_is_small(tmp_path, monkeypatch):
    monkeypatch.setattr(inputs, 'MAX_ARCHIVE_BYTES', 1024)          # the ZIP-upload limit does not apply here
    fake_github(monkeypatch, tarball([('g/src/a.c', 'int a;'), ('g/music.ogg', b'x' * 200_000)]))
    inputs.fetch_repository('https://github.com/a/game', tmp_path / 'input')
    assert (tmp_path / 'input/g/src/a.c').is_file()


def test_download_limit_traversal_and_cancel(tmp_path, monkeypatch):
    archive = tarball([('g/src/a.c', 'int a;'), ('g/big.bin', b'x' * 300_000)])
    fake_github(monkeypatch, archive)
    monkeypatch.setattr(inputs, 'MAX_DOWNLOAD_BYTES', 100)
    with pytest.raises(ValueError, match='제한을 초과'):
        inputs.fetch_repository('https://github.com/a/game', tmp_path / 'one')
    monkeypatch.setattr(inputs, 'MAX_DOWNLOAD_BYTES', 2 * 1024 ** 3)
    fake_github(monkeypatch, tarball([('g/../../outside.c', 'int x;')]))
    with pytest.raises(ValueError):
        inputs.fetch_repository('https://github.com/a/game', tmp_path / 'two')
    assert not (tmp_path / 'outside.c').exists()
    calls = []
    fake_github(monkeypatch, archive)
    with pytest.raises(ValueError, match='중단'):
        inputs.extract_tar_stream(io.BytesIO(archive), tmp_path / 'three', cancelled=lambda: calls.append(1) or len(calls) > 1)


def test_source_count_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(inputs, 'MAX_FILES', 2)
    with pytest.raises(ValueError, match='소스 파일이'):
        inputs.extract_tar_stream(io.BytesIO(tarball([(f'g/{i}.c', 'int x;') for i in range(3)])), tmp_path)
