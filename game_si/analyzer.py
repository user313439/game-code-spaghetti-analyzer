"""csharp-analyzer 바이너리 호출 어댑터.

이 모듈은 외부 프로세스로 .NET 콘솔 분석기(`csharp-analyzer`)를 호출하고,
결과 JSON을 로드하여 Python 측에서 다룰 수 있는 dict로 반환한다.

W1 단계에서는 단일 함수만 노출한다. 후속 단계에서는 다음 기능이 추가된다.
- 솔루션(.sln) 입력 지원 (W2)
- 메트릭 후처리 및 G-SI 산출 (W3~W5)
- HTML 리포트 생성 (W6~W7)
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CSHARP_ANALYZER_DIR = REPO_ROOT / "csharp-analyzer"
CSHARP_ANALYZER_DLL = (
    CSHARP_ANALYZER_DIR / "bin" / "Debug" / "net8.0" / "csharp-analyzer.dll"
)


@dataclass
class AnalyzerResult:
    """csharp-analyzer 실행 결과."""

    data: dict
    stderr: str
    returncode: int
    output_path: Path | None

    @property
    def files(self) -> list[dict]:
        return self.data.get("files", [])

    @property
    def summary(self) -> dict:
        return self.data.get("summary", {})

    @property
    def errors(self) -> list[dict]:
        return self.data.get("errors", [])


class AnalyzerNotFoundError(RuntimeError):
    """csharp-analyzer 바이너리를 찾을 수 없을 때 발생."""


class AnalyzerExecutionError(RuntimeError):
    """csharp-analyzer 실행이 비정상 종료되었을 때 발생."""


def ensure_built() -> Path:
    """csharp-analyzer DLL이 존재하는지 확인하고 경로를 반환.

    빌드되지 않은 경우 AnalyzerNotFoundError를 발생시킨다.
    """
    if CSHARP_ANALYZER_DLL.exists():
        return CSHARP_ANALYZER_DLL

    raise AnalyzerNotFoundError(
        f"csharp-analyzer가 빌드되어 있지 않습니다.\n"
        f"  expected: {CSHARP_ANALYZER_DLL}\n"
        f'  실행: cd "{CSHARP_ANALYZER_DIR}" && dotnet build'
    )


def _resolve_dotnet() -> str:
    """현재 환경의 dotnet 실행파일 경로를 결정.

    PATH에서 우선 찾고, 없으면 알려진 설치 경로를 시도한다.
    """
    found = shutil.which("dotnet")
    if found:
        return found

    candidates = [
        Path(r"C:\Program Files\dotnet\dotnet.exe"),
        Path(r"C:\Program Files (x86)\dotnet\dotnet.exe"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)

    raise AnalyzerNotFoundError(
        "dotnet 실행파일을 찾을 수 없습니다. .NET SDK가 설치되어 있는지 확인하세요."
    )


def analyze(
    input_path: Path | str,
    output_path: Path | str | None = None,
    excludes: list[str] | None = None,
) -> AnalyzerResult:
    """csharp-analyzer를 호출하여 입력 경로를 분석한다.

    Parameters
    ----------
    input_path : Path | str
        분석할 .cs 파일, 디렉토리, 또는 솔루션(.sln) 경로.
    output_path : Path | str | None
        결과 JSON을 저장할 경로. None이면 stdout으로 받아 메모리에서 파싱.
    excludes : list[str] | None
        제외할 디렉토리 이름 목록 (기본 제외 외 추가).

    Returns
    -------
    AnalyzerResult
    """
    dll = ensure_built()
    dotnet = _resolve_dotnet()

    cmd: list[str] = [dotnet, str(dll), "--input", str(input_path)]
    if output_path is not None:
        cmd += ["--output", str(output_path)]
    for ex in excludes or []:
        cmd += ["--exclude", ex]

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if proc.returncode != 0:
        raise AnalyzerExecutionError(
            f"csharp-analyzer가 종료 코드 {proc.returncode}로 실패했습니다.\n"
            f"stderr:\n{proc.stderr}"
        )

    if output_path is not None:
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.loads(proc.stdout)

    return AnalyzerResult(
        data=data,
        stderr=proc.stderr,
        returncode=proc.returncode,
        output_path=Path(output_path) if output_path is not None else None,
    )
