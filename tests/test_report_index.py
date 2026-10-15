"""Saved landing page: clear scopes, truthful counts and accessible case links."""

from html.parser import HTMLParser
import json
from pathlib import Path
import re


REPORTS = Path(__file__).resolve().parents[1] / 'reports'


class IndexReader(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.links = []
        self.details = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            self.links.append(attrs)
        if tag == 'details':
            self.details.append(attrs)


def page():
    return (REPORTS / 'index.html').read_text(encoding='utf-8')


def section(section_id):
    match = re.search(rf'<section id="{section_id}">(.*?)</section>', page(), re.S)
    assert match is not None, section_id
    return match.group(1)


def case_links(text):
    return [link for link in IndexReader(text).links if 'card' in link.get('class', '').split()]


def test_author_is_in_centered_intro_header():
    header = re.search(r'<header>.*?</header>', page(), re.S).group(0)
    assert '<div class="project-author">2018313439 · 안영진</div>' in header
    assert '성균관대학교 소프트웨어학과 · 졸업작품' in header


def test_landing_page_omits_duplicate_usage_summary():
    assert '대시보드 사용법 간단 정리' not in page()


def test_primary_four_cases_remain_separate_from_extension():
    main = section('main-cases')
    assert {link['href'] for link in case_links(main)} == {
        'openra-game/index.html', 'openra-mods-common/index.html',
        'chocolate-doom/index.html', 'openrct2/index.html'}
    assert '수행한 4개 사례' in main
    assert '보조 Health' in main


def test_auxiliary_cases_are_collapsed_and_all_have_live_links():
    extra = section('additional-cases')
    reader = IndexReader(extra)
    assert len(reader.details) == 1 and 'open' not in reader.details[0]
    assert '추가 분석 사례 · OpenRA 내부 모듈' in extra
    assert '별도 게임이 아니라' in extra
    assert '전체 관계를 한 번에 분석한 결과는 아닙니다' in extra
    assert {link['href'] for link in case_links(extra)} == {
        'openra-mods-cnc/index.html', 'openra-mods-d2k/index.html',
        'openra-platforms-default/index.html', 'openra-server/index.html'}
    assert all('disabled' not in link.get('class', '').split() for link in case_links(extra))
    assert '통계적 평가 불가' in extra
    assert 'scoring.json·validation.json으로 제공합니다' not in extra


def test_doom_extension_displays_current_counts_and_partial_scope():
    extension = section('cpp-extension-cases')
    assert [link['href'] for link in case_links(extension)] == ['doom3-gameplay-clang/index.html']
    assert '컴파일 설정 기반 확장 사례' in extension and '부분 분석' in extension
    assert '기존 4개 주요 사례와는 검증 범위가 다릅니다' in extension
    status = json.loads((REPORTS / 'doom3-gameplay-clang/analysis_status.json').read_text(encoding='utf-8'))
    scoring = json.loads((REPORTS / 'doom3-gameplay-clang/scoring.json').read_text(encoding='utf-8'))
    assert status['state'] == 'partial'
    assert f"게임플레이 구현 파일 {status['registered_files']:,}개 대상" in extension
    for metric, value in [('registered_files', status['registered_files']),
                          ('total_methods', scoring['total_methods']),
                          ('compiler_error_files', status['compiler_error_files']),
                          ('compiler_warning_files', status['compiler_warning_files'])]:
        assert f'data-metric="{metric}">{value:,}</span>' in extension
    assert '전체 엔진을 분석한 결과는 아닙니다' in extension
    assert '게임 버그' not in extension and '100%' not in extension


def test_nine_case_links_resolve_and_do_not_promote_three_file_sample():
    links = case_links(page())
    assert len(links) == 9
    assert len({link['href'] for link in links}) == 9
    for link in links:
        target = (REPORTS / link['href']).resolve()
        assert target.is_relative_to(REPORTS.resolve()) and target.is_file()
        assert 'openrct2-clang-sample' not in link['href']


def test_target_metadata_keeps_statistical_validation_boundary():
    targets = section('analysis-targets')
    assert 'https://github.com/id-Software/DOOM-3' in targets
    assert 'a9c49da5afb18201d31e3f0a429a037e56ce2b9a' in targets
    assert '선택형 Clang' in targets and '기본 3프로젝트 LOPO' in targets
    assert '4프로젝트 LOPO' not in targets
