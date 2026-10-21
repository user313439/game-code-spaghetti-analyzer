# docs 폴더 안내

`docs/`에는 공개 문서, 내부 작업 문서, 중간보고서 제출 자료가 섞여 있습니다.
헷갈리면 이 파일에서 목적별로 찾으면 됩니다.

## 가장 자주 볼 파일

| 파일 | 용도 |
|---|---|
| `local-web-guide.md` | 로컬 웹 실행·GitHub/파일 입력·정밀 분석(시연 게임)·분석 기록·실제 시연 순서 |
| `ai-refactoring-guide.md` | 2026-10-20 재설계 웹의 AI 처방·리팩토링·검증 흐름, 변경안 검사 규칙, 엉킴 총량, AI 연결 |
| `superpowers/specs/2026-10-19-web-redesign-design.md` | 웹 재설계 설계서(4단계 화면·라운드·처방 계약)와 구현과 다른 점 |
| `web-final-review.md` | 10월 13일 기준 웹 검수 기록(재설계 이전). 현재 흐름은 위 두 안내서 기준 |
| `benchmark-manifest.md` | 전체 검증 결과와 재현 명령. 보고서/발표 자료의 핵심 근거 |
| `si-formula.md` | G-SI 공식, 가중치, 등급 체계 설명 |
| `progress_checklist.md` | 산출물과 테스트 점검표 |
| `final-verification.md` | 2026-10-03 최종판 재검증, 현재 결과의 해석·재현 조건 |
| `refinement-review.md` | 2026-10-04 고정 8사례의 보완 결과·연구 검증·남은 한계. 고정 실험 수치 기준 |
| `safety-ui-review.md` | 2026-10-05 기본 오류 안내·HTML 개선 기록. 이후 Clang·웹 검수와 구분 |
| `compiler-aware-cpp.md` | 선택형 Clang 분석 사용법·파일 단위 범위·DOOM 3/OpenRCT2 검수와 한계 |
| `case-study-review.md` | 양방향 후보의 실제 소스 검토와 해석 주의 사례 |
| `_ops/handover.md` | 새 AI 세션에 넘기는 전체 인수인계 노트 |
| `_midterm_phase/submission_guide.md` | 중간보고서 제출 절차 상세 |
| `_ops/folder_guide.md` | 더 자세한 폴더 설명 메모 |

## 공개 문서

이 파일들은 GitHub에 올라가는 공개 문서입니다.

| 파일 | 설명 |
|---|---|
| `ast-schema.md` | AST JSON 스키마 |
| `benchmark-manifest.md` | OpenRA, Chocolate Doom, OpenRCT2 검증 결과 종합 |
| `si-formula.md` | G-SI 산식과 가중치 운용 |
| `progress_checklist.md` | 결과/보안/재현 점검표 |
| `phase_e_survey.md` | 사용자 피드백 설문 양식 |
| `local-web-guide.md` | 현재 웹 사용 안내 |
| `ai-refactoring-guide.md` | AI 처방·리팩토링·검증 안내 |
| `superpowers/specs/2026-10-19-web-redesign-design.md` | 웹 재설계 설계서 |
| `web-final-review.md` | 10월 13일 웹 검수 기록(재설계 이전) |
| `multi-advisor-verification-2026-10-18.md`, `joint-advisor-verification-2026-10-19.md`, `advisor-experience-verification-2026-10-18.md`, `ai-refactoring-verification-2026-10-18.md` | 재설계 이전 AI 검토 화면의 검증 기록 |
| `maintenance-workflow-verification-2026-10-19.md` | OpenTyrian 실제 수정·빌드·계산 비교·직접 플레이 검증 기록 |

## 내부 작업 문서

이 파일들은 로컬 전용입니다. 대부분 `.gitignore`로 막혀 있습니다.

| 파일/폴더 | 설명 |
|---|---|
| `_midterm_phase/` | 중간보고서 제출 단계 자료 |
| `_post_midterm_phase/` | 제출 이후 피드백, v1.0 push, 최종보고서 자료 |
| `_ops/` | 인수인계, 폴더 안내 같은 운영 메모 |
| `_planning/` | 상세 개발 계획 초안과 운영 로드맵 |
| `_verification/2026-10-03/` | 기존 결과를 보존하고 별도로 재실행한 분석·검증 결과 |
| `_private/` | 신청서 PDF, 임시 키 메모 같은 개인/비밀 파일 |
| `_verify_midterm.py` | 기존 명령을 유지하는 중간보고서 검증 wrapper |

## 중간보고서 제출 자료

| 파일/폴더 | 설명 |
|---|---|
| `_midterm_phase/중간보고서_안영진.docx` | 실제 제출·승인받은 중간보고서 기준본 |
| `_midterm_phase/report_v2.docx` | 이전 작업 초안. 제출본과 구분 |
| `_midterm_phase/report_plain.txt` | docx와 동기화된 텍스트 백업 |
| `_midterm_phase/report_v2.docx.bak` | docx 백업 |
| `_midterm_phase/figures/` | 중간보고서 그림 PNG/SVG |
| `_midterm_phase/form/(양식)_연구논문작품_중간보고서.hwp` | 학교 배포 hwp 양식 |
| `_midterm_phase/checklist.md` | 수동 제출 체크리스트 |
| `_midterm_phase/codex_prompt.md` | 새 AI 세션용 Phase 1 프롬프트 |
| `_midterm_phase/README.md` | Phase 1 요약 |

## 중간보고서 제출 기록을 다시 볼 순서

1. `_midterm_phase/README.md`
2. `_midterm_phase/submission_guide.md`
3. `_midterm_phase/checklist.md`
4. `_verify_midterm.py` 실행

```powershell
py -3.10 docs\_verify_midterm.py
```

위 순서는 과거 중간보고서 단계용이며 승인된 제출본이나 앞으로 작성할 최종보고서를 검증하지 않습니다. 현재 마무리는 `web-final-review.md` → `progress_checklist.md` → `benchmark-manifest.md` 순서로 확인합니다. 최종보고서·발표 자료는 학교 지정 양식과 승인된 중간보고서를 별도로 참고합니다.

## commit 주의

아래는 절대 commit하지 않습니다.

| 패턴 | 이유 |
|---|---|
| `docs/_*` | 내부 작업물, 인수인계, 보고서 초안 |
| `docs/_private/` | 개인정보/비밀 파일 |
| `*.hwp`, `*.hwpx` | 학교 양식/제출 파일 |
| `docs/*draft*.md` | 초안 |
| `docs/*roadmap*.md` | 내부 일정 문서 |
| `docs/_midterm_phase/figures/` | 중간보고서 로컬 그림 자료 |
