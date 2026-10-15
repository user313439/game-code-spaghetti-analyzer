# 졸업작품 폴더 시작 안내

이 폴더는 Game Spaghetti Index(G-SI) 분석 도구 프로젝트 루트입니다.
처음 들어왔을 때는 아래 순서대로 보면 됩니다.

## 먼저 열 파일

| 순서 | 파일 | 용도 |
|---|---|---|
| 1 | `README.md` | 프로젝트 공개 소개, 핵심 결과, 실행 방법 |
| 1-1 | `docs/local-web-guide.md` | 실제 새 소스 분석용 로컬 웹 실행·시연 순서 |
| 1-2 | `docs/web-final-review.md` | 라이트 블루 확정 후 사용 검수·남은 제출 작업 |
| 1-3 | `reports/verification-publication-2026-10-15.json` | Git 반영 전 재검증과 공개 파일 선별 기록 |
| 2 | `docs/README.md` | docs 폴더 안 파일 안내 |
| 3 | `reports/index.html` | 기존 고정 실험 결과 모음; 새 분석은 로컬 웹에서 실행 |
| 4 | `docs/final-verification.md` | 최종판 재검증 결과·과거/현재 자료 구분 |
| 5 | `docs/refinement-review.md` | 최신 보완·재검수 결과. 최종보고서 작성 기준 |
| 6 | `docs/safety-ui-review.md` | 10월 5일 오류 안내·화면 보완 기록. 현재 웹 점검은 web-final-review.md 참고 |

## 루트 폴더 지도

| 항목 | 설명 | 보통 건드려도 되나 |
|---|---|---|
| `game_si/` | Python 메인 패키지. CLI, 분석, 리포트 생성 코드 | 코드 수정 요청 있을 때만 |
| `csharp-analyzer/` | .NET 8 기반 C# 분석기 | C# 분석 정확도 수정 때만 |
| `tests/` | pytest 테스트와 샘플 코드 | 코드 수정 시 같이 확인 |
| `docs/` | 문서, 보고서, 제출 가이드 | `docs/README.md` 먼저 보기 |
| `reports/` | 분석 결과 HTML/JSON 산출물 | 결과 확인/시연용 |
| `benchmarks/` | OpenRA, Chocolate Doom, OpenRCT2 외부 소스 | 수정 금지, 재현용 |
| `.github/` | GitHub Actions 샘플 | 배포/CI 수정 때만 |

## 루트에 있는 개인/로컬 파일

| 파일 | 설명 | 주의 |
|---|---|---|
| `.env` | API 키 보관 | 루트에 둬야 LLM advisor가 자동 로드함. 절대 commit 금지 |
| `docs/_private/` | 신청서 PDF, 임시 키 메모 같은 개인 파일 | 로컬 전용. 절대 commit 금지 |
| `졸업작품_전체_계획서.md` | 학교 제출용 계획서 공개판 | GitHub에 올라가는 공개 문서 |

## 자주 하는 작업

```powershell
# 중간보고서 제출 준비 검증
py -3.10 docs\_verify_midterm.py

# 테스트
py -3.10 -m pytest tests/ -q

# CLI 확인
py -3.10 -m game_si --help

# 대표 결과 열기
start reports\index.html
start reports\openra-game\index.html

# 실제 분석 웹 실행 (C# 분석에 필요한 현재 세션 PATH)
$env:PATH = "C:\Program Files\dotnet;" + $env:PATH
py -3.10 -m game_si.web --port 8766
```

## 현재 phase

중간보고서는 제출·승인 완료입니다. 제출 기준본은 `docs/_midterm_phase/중간보고서_안영진.docx`이며 덮어쓰지 않습니다.
현재는 로컬 웹의 라이트 블루 디자인을 확정한 후 실제 입력·분석 검수와 공개 문서를 정리하는 단계입니다. `docs/web-final-review.md`가 현재 상태의 진입점입니다. `docs/_post_midterm_phase/reproducibility_plan_2026-10-03.md`는 앞선 재현성 계획 기록입니다.
최종 산출물은 검증된 프로젝트, 별도 Word 최종보고서, 학교 지정 양식의 한 페이지 포스터입니다.
`docs/_verify_midterm.py`는 이전 `report_v2.docx` 및 평문 초안 검사로, 승인된 제출본이나 최종보고서 검증을 대신하지 않습니다.

10월 13일까지 기본 테마 반영·실제 사용 검수·문서를 정리했고, 10월 15일 사용자 요청으로 Git 반영 전 재검증과 공개 파일 선별을 진행합니다. 사용자 직접 체험, Git 공개, Word 최종보고서, 포스터, 영상 녹화는 구분합니다. 웹 분석은 AI가 자동 수정하는 기능이 아닙니다. 새 채팅에서 최종보고서를 작성할 때는 로컬 `docs/_ops/final_report_handoff_2026-10-15.md`를 먼저 읽습니다.

주의:
- 커밋·push는 해당 작업에 대한 사용자 명시 요청이 있을 때만 수행
- `git add -A` 금지
- `.env`, `docs/_private/`, `docs/_*`, `*.hwp`, 루트 PDF commit 금지
- 코드 새 기능 추가는 기본적으로 하지 않음
