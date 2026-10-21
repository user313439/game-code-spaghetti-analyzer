"""Bounded source imports. Imported projects are never built or executed."""
from __future__ import annotations

import json
import lzma
import re
import stat
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib
from pathlib import Path, PurePosixPath

MAX_ARCHIVE_BYTES = 100 * 1024 * 1024        # uploaded ZIP (stored, then extracted)
# GitHub import streams the archive and keeps only source files, so assets cost time, not disk.
MAX_DOWNLOAD_BYTES = 2 * 1024 ** 3
MAX_UNPACKED_BYTES = 8 * 1024 ** 3
MAX_ARCHIVE_MEMBERS = 500_000
DOWNLOAD_SECONDS = 15 * 60
MAX_SOURCE_BYTES = 1024 * 1024 * 1024
MAX_FILES = 20_000
IGNORED = {'.git', '.vs', 'bin', 'obj', 'node_modules', 'packages', 'build',
           'dist', '__pycache__', '.venv', 'venv', 'testresults'}
SOURCE_EXTENSIONS = {'.cs', '.c', '.cc', '.cpp', '.cxx', '.h', '.hh', '.hpp',
                     '.hxx', '.inl', '.inc'}
BODY_LANGUAGES = {'.cs': 'csharp', '.c': 'c', '.cc': 'cpp', '.cpp': 'cpp', '.cxx': 'cpp'}
GITHUB_HOSTS = {'api.github.com', 'codeload.github.com'}


def safe_relative(name: str) -> PurePosixPath:
    parts = name.split('/')
    if not name or len(name) > 1024 or any(
        not p or p in {'.', '..'} or p.endswith((' ', '.')) or
        re.search(r'[\x00-\x1f<>:"\\|?*]', p) or
        re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?', p, re.I)
        for p in parts
    ):
        raise ValueError('안전하지 않은 파일 경로입니다. 원본 소스의 이름과 폴더 구조를 확인해 주세요.')
    return PurePosixPath(name)


def is_source(name: str) -> bool:
    path = PurePosixPath(name)
    return path.suffix.lower() in SOURCE_EXTENSIONS and not any(
        p.lower() in IGNORED or p.lower().startswith('.env') for p in path.parts
    )


def target_path(root: Path, name: str) -> Path:
    path = root.joinpath(*safe_relative(name).parts).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('소스 폴더 밖의 경로는 사용할 수 없습니다.')
    return path


def extract_zip(stream, destination: Path, cancelled=lambda: False) -> None:
    """Validate all entries before writing; also count actual decompressed bytes."""
    try:
        with zipfile.ZipFile(stream) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_FILES:
                raise ValueError('ZIP 안의 파일 수가 너무 많습니다. 분석할 소스 폴더만 준비해 주세요.')
            total = 0
            seen = set()
            selected = []
            for entry in entries:
                if cancelled():
                    raise ValueError('소스 가져오기가 중단되었습니다.')
                name = entry.filename.rstrip('/') if entry.is_dir() else entry.filename
                safe_relative(name)
                key = name.casefold()
                if key in seen or stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                    raise ValueError('중복 경로·링크·암호화된 ZIP은 지원하지 않습니다.')
                seen.add(key)
                total += entry.file_size
                if total > MAX_SOURCE_BYTES:
                    raise ValueError('압축을 푼 소스 용량이 1 GiB를 초과합니다.')
                if not entry.is_dir() and is_source(name):
                    selected.append(entry)
            actual = 0
            for entry in selected:
                if cancelled():
                    raise ValueError('소스 가져오기가 중단되었습니다.')
                path = target_path(destination, entry.filename)
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, path.open('xb') as output:
                    while chunk := source.read(64 * 1024):
                        if cancelled():
                            raise ValueError('소스 가져오기가 중단되었습니다.')
                        actual += len(chunk)
                        if actual > MAX_SOURCE_BYTES:
                            raise ValueError('해제 용량 제한을 초과했습니다.')
                        output.write(chunk)
    except (zipfile.BadZipFile, zlib.error, lzma.LZMAError, EOFError, RuntimeError, NotImplementedError, OSError) as exc:
        raise ValueError('ZIP을 읽을 수 없습니다. 정상적인 소스 ZIP을 선택해 주세요.') from exc


def extract_tar_stream(stream, destination: Path, cancelled=lambda: False) -> None:
    """Read a .tar.gz once, front to back, and write only source files. Images, sounds and other
    assets pass through without touching the disk; links and special files are never written."""
    unpacked = written = files = members = 0
    seen = set()
    try:
        with tarfile.open(fileobj=stream, mode='r|gz') as archive:
            for member in archive:
                if cancelled():
                    raise ValueError('소스 가져오기가 중단되었습니다.')
                members += 1
                unpacked += max(0, member.size)
                if members > MAX_ARCHIVE_MEMBERS or unpacked > MAX_UNPACKED_BYTES:
                    raise ValueError('저장소 묶음이 너무 큽니다. 분석할 소스 폴더만 직접 선택해 주세요.')
                if not member.isfile() or not is_source(member.name):
                    continue
                safe_relative(member.name)
                key = member.name.casefold()
                if key in seen:
                    raise ValueError('대소문자만 다른 같은 경로의 소스가 있어 가져올 수 없습니다.')
                seen.add(key)
                files += 1
                written += member.size
                if files > MAX_FILES:
                    raise ValueError(f'소스 파일이 {MAX_FILES:,}개를 넘습니다. 분석할 소스 폴더만 직접 선택해 주세요.')
                if written > MAX_SOURCE_BYTES:
                    raise ValueError('소스 용량이 1 GiB를 초과합니다. 분석할 소스 폴더만 직접 선택해 주세요.')
                path = target_path(destination, member.name)
                path.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                with path.open('xb') as output:
                    while chunk := source.read(64 * 1024):
                        if cancelled():
                            raise ValueError('소스 가져오기가 중단되었습니다.')
                        output.write(chunk)
    except (tarfile.TarError, zlib.error, EOFError, OSError) as exc:
        raise ValueError('GitHub 소스 묶음을 읽지 못했습니다. 다시 시도하거나 소스 폴더를 직접 선택해 주세요.') from exc


class _Download:
    """The archive response, read with size, time and cancel limits."""

    def __init__(self, response, cancelled, deadline):
        self.response, self.cancelled, self.deadline, self.size = response, cancelled, deadline, 0

    def read(self, size=-1):
        if self.cancelled():
            raise ValueError('소스 가져오기가 중단되었습니다.')
        data = self.response.read(size if size and size > 0 else 64 * 1024)
        self.size += len(data)
        if self.size > MAX_DOWNLOAD_BYTES or time.monotonic() > self.deadline:
            raise ValueError(f'가져오기 용량({MAX_DOWNLOAD_BYTES // 1024 ** 3} GiB) 또는 시간({DOWNLOAD_SECONDS // 60}분) 제한을 '
                             '초과했습니다. 분석할 소스 폴더를 직접 선택해 주세요.')
        return data


def inspect_source(root: Path) -> dict:
    counts = dict(csharp=0, c=0, cpp=0)
    folders = {'.'}
    source_bytes = 0
    for path in root.rglob('*'):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        if not is_source(relative):
            continue
        source_bytes += path.stat().st_size
        lang = BODY_LANGUAGES.get(path.suffix.lower())
        if lang:
            counts[lang] += 1
            parent = PurePosixPath(relative).parent
            folders.add(parent.as_posix())
            folders.update(p.as_posix() for p in parent.parents)
    if not sum(counts.values()):
        raise ValueError('분석할 C#/C/C++ 소스가 없습니다. 실행 파일 대신 소스 코드를 선택해 주세요.')
    return {'languages': counts, 'folders': sorted(folders), 'source_bytes': source_bytes}


def parse_repository(url: str) -> tuple[str, str]:
    parsed = urllib.parse.urlsplit(url.strip())
    if (parsed.scheme != 'https' or parsed.netloc != 'github.com' or
            parsed.query or parsed.fragment):
        raise ValueError('https://github.com/소유자/저장소 형식의 공개 저장소 주소를 입력해 주세요.')
    match = re.fullmatch(r'/([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+)/?', parsed.path)
    if not match:
        raise ValueError('파일·브랜치 페이지가 아닌 저장소 첫 화면의 주소를 입력해 주세요.')
    owner, repo = match.groups()
    repo = repo.removesuffix('.git')
    if repo in {'', '.', '..'}:
        raise ValueError('저장소 이름을 확인해 주세요.')
    return owner, repo


def github_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.netloc not in GITHUB_HOSTS:
        raise ValueError('GitHub 공식 다운로드 주소가 아닌 연결은 차단했습니다.')
    return url


class GitHubRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        github_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_repository(url: str, destination: Path, cancelled=lambda: False) -> dict:
    owner, repo = parse_repository(url)
    opener = urllib.request.build_opener(GitHubRedirect())
    deadline = time.monotonic() + DOWNLOAD_SECONDS

    def request(address, timeout=15):
        if cancelled():
            raise ValueError('소스 가져오기가 중단되었습니다.')
        return opener.open(urllib.request.Request(github_url(address), headers={
            'User-Agent': 'Game-SI-local-analysis', 'Accept': 'application/vnd.github+json',
        }), timeout=timeout)

    def read_json(address):
        with request(address) as response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError('저장소 정보 응답이 너무 큽니다.')
            return json.loads(raw)

    try:
        base = f'https://api.github.com/repos/{owner}/{repo}'
        metadata = read_json(base)
        if metadata.get('private'):
            raise ValueError('첫 버전은 공개 GitHub 저장소만 지원합니다.')
        branch = metadata['default_branch']
        commit = read_json(base + '/commits/' + urllib.parse.quote(branch, safe=''))['sha']
        if not re.fullmatch(r'[0-9a-f]{40}', commit):
            raise ValueError('GitHub 소스 버전을 확인하지 못했습니다.')
        # GitHub builds large archives on the fly, so the first bytes may take a while.
        with request(base + '/tarball/' + commit, timeout=90) as response:
            extract_tar_stream(_Download(response, cancelled, deadline), destination, cancelled=cancelled)
        return {'repository': f'https://github.com/{owner}/{repo}', 'commit': commit, 'branch': branch}
    except urllib.error.HTTPError as exc:
        message = ('공개 저장소를 찾지 못했습니다. 주소와 공개 여부를 확인해 주세요.'
                   if exc.code == 404 else 'GitHub에서 소스를 가져오지 못했습니다. 요청 제한 또는 연결 상태를 확인해 주세요.')
        raise ValueError(message) from exc
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError('소스를 가져오지 못했습니다. 인터넷 연결을 확인하거나 ZIP/폴더를 선택해 주세요.') from exc
