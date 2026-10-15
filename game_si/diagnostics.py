"""분석 가능한 입력과 추출 결과의 상태를 구분한다. 정확성을 보증하지 않는다."""
from pathlib import Path


def validate_analysis_input(path: Path, lang: str, excludes=()) -> None:
    from .cpp_analyzer import BODY_EXTENSIONS, DEFAULT_EXCLUDE_DIRS
    supported = {'.cs'} if lang == 'csharp' else BODY_EXTENSIONS
    if path.is_file():
        if path.suffix.lower() not in supported:
            raise ValueError('지원하지 않는 입력 파일입니다. C# 또는 C/C++ 소스 파일이나 소스 폴더를 지정하세요. '
                             '프로젝트·솔루션 파일, 게임 실행 파일은 직접 분석하지 않습니다.')
        return
    ignored = set(excludes) | (DEFAULT_EXCLUDE_DIRS if lang != 'csharp' else
                              {'bin', 'obj', '.git', '.vs', 'packages', 'node_modules', 'TestResults'})
    if not any(p.is_file() and p.suffix.lower() in supported and
               not any(part in ignored for part in p.relative_to(path).parts)
               for p in path.rglob('*')):
        raise ValueError('선택한 언어로 분석할 지원 소스 파일이 없습니다. '
                         '소스 폴더·언어·제외 폴더 설정을 확인하세요. C/C++ 헤더만 있는 입력은 지원하지 않습니다.')


def summarize_analysis(data: dict, lang: str) -> dict:
    if data.get('backend') == 'clang':
        return _summarize_clang(data, lang)
    files = data.get('files', [])
    def relative_issues(items):
        root = Path(data.get('input_path', '.'))
        if root.is_file():
            root = root.parent
        rows = []
        for item in items:
            row = dict(item)
            try:
                row['path'] = Path(row.get('path', '')).relative_to(root).as_posix()
            except ValueError:
                pass
            rows.append(row)
        return rows
    errors = relative_issues(data.get('errors', []))
    diagnostics = relative_issues(data.get('diagnostics', []))
    classes = [c for f in files for c in f.get('classes', [])]
    methods = sum(len(c.get('methods', [])) for c in classes)
    has_code = lang == 'csharp' or any(f.get('has_code', f.get('loc', 0) > 0) for f in files)
    failed = not files or not classes or not has_code or (diagnostics and not methods)
    state = 'failed' if failed else 'partial' if errors or diagnostics else 'complete'
    limits = ['결과는 선택한 언어와 분석 대상에 한정됩니다. 완료 표시는 코드 전체를 정확히 이해했다는 보증이 아닙니다.',
              '동적 호출·이벤트·런타임 상태와 이름 패턴 밖의 게임 루프는 완전히 해석하지 않습니다.']
    if lang == 'csharp':
        limits.append('C# 프로젝트 설정과 외부 DLL을 자동으로 읽지 않습니다. 해석되지 않은 호출은 이름 기반 근사 또는 연결 누락이 발생할 수 있습니다.')
    else:
        limits.append('C/C++는 구문 기반 분석입니다. 매크로·템플릿·헤더 본문과 외부 라이브러리의 완전한 의미 해석은 지원하지 않습니다.')
    return dict(state=state, language=lang, analyzed_files=len(files),
                failed_files=len({e.get('path', '') for e in errors}),
                syntax_files=len({d.get('path', '') for d in diagnostics}),
                errors=errors, diagnostics=diagnostics, limitations=limits)


def _summarize_clang(data: dict, lang: str) -> dict:
    root = Path(data.get('input_path', '.'))
    if root.is_file():
        root = root.parent

    def relative_issues(items):
        rows = []
        for item in items:
            row = dict(item)
            for key in ('path', 'input_path'):
                if key not in row:
                    continue
                try:
                    row[key] = Path(row[key]).relative_to(root).as_posix()
                except ValueError:
                    pass
            rows.append(row)
        return rows

    files = data.get('files', [])
    errors = relative_issues(data.get('errors', []))
    compiler = relative_issues(data.get('compiler_diagnostics', []))
    compiler_errors = [d for d in compiler if d.get('severity') in ('error', 'fatal')]
    compiler_warnings = [d for d in compiler if d.get('severity') == 'warning']
    methods = sum(len(c.get('methods', [])) for f in files for c in f.get('classes', []))
    state = 'failed' if not methods else 'partial' if errors or compiler_errors else 'complete'
    configuration = data.get('configuration', {})
    limits = [
        '분석 단위는 구현 파일입니다. 파일 간 의존성은 선택한 구현 파일에서 연결한 심볼을 이용한 근사이며 정확한 클래스 그래프가 아닙니다.',
        '원시 CC와 파일 간 결합도·순환·전역 상태·게임 루프 지표를 함께 확인하세요. G-SI는 분석 집합 내부의 상대 검토 순위이며 절대 품질이나 결함 확률이 아닙니다.',
        'compile_commands.json에서 파일별 첫 등록 항목 하나의 설정만 선택합니다. 다른 설정·플랫폼·전처리 분기와 미등록 파일은 분석 범위 밖입니다.',
        '헤더는 컴파일 문맥에 사용하지만 헤더 안의 함수 본문을 별도 분석 단위로 추출하지 않습니다. 헤더에서 발생한 진단은 원래 구현 파일별로 집계합니다.',
        '직접 호출은 컴파일 시점 심볼로 연결합니다. 가상 호출의 동적 대상·함수 포인터·이벤트·런타임 상태와 이름 패턴 밖의 게임 루프를 완전히 해석하지 않습니다.',
        'CC는 range-for와 중첩 람다 본문을 제외하고 default 분기를 포함합니다. 매크로 생성 함수의 원본 스니펫은 제공하지 않습니다.',
        '호환 libclang으로 분석한 결과이며 원본 빌드 성공을 뜻하지 않습니다. 분석 완료도 전체 코드의 정확한 해석을 보증하지 않습니다.',
    ]
    return dict(state=state, language=lang, backend='clang', analysis_unit='implementation_file',
                runtime=data.get('runtime', {}), configuration=configuration,
                analyzed_files=len(files), registered_files=len(configuration.get('entries', [])),
                unregistered_files=len(configuration.get('unregistered_files', [])),
                failed_files=len({e.get('path', '') for e in errors}), syntax_files=0,
                compiler_error_files=len({d.get('input_path', '') for d in compiler_errors}),
                compiler_warning_files=len({d.get('input_path', '') for d in compiler_warnings}),
                compiler_error_count=len(compiler_errors), compiler_warning_count=len(compiler_warnings),
                errors=errors, diagnostics=[], compiler_diagnostics=compiler, limitations=limits)
