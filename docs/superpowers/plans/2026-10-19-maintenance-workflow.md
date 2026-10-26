# 유지보수 흐름 구현과 최종보고서 갱신 계획

> **For agentic workers:** Use subagent-driven-development for isolated ownership and independent reviews. No branches, worktrees, commits or paid API calls. User approved the design discussed in chat.

**Goal:** 점수 기반 검토에서 실제 수정·관련 동작 검증까지 사용 가능한 흐름을 완성하고 검증 결과를 최종보고서v3에 반영한다.

**Architecture:** 기존 분석 엔진은 유지한다. AI 입력과 파일별 판단을 구체적인 함수에 연결하고 현재 단계의 데이터로 화면을 만든다. 사전 검토를 재사용하며 과거 실제 기록과 새 시연 작업은 분리한다.

**Tech Stack:** Python/FastAPI, 기존 정적 JS/CSS, 공식 Codex CLI 계정 연결, 기존 MSBuild/SDL2/OpenTyrian, Word/OOXML와 PDF 검수.

- [x] 보존 기준: 이전 actual assistant.json·학교/중간/v2 해시·Git 상태 기록. 현재 UI/preview 어긋남을 데이터로 재현.
- [x] backend: tests/test_joint_advisor.py와 관련 기존 fixture에 targets/함수 문맥·선택 부분 prior·사전 검토 기반 preview 실패 검사를 먼저 추가. 실패 확인 후 assistant.py/context/jobs/reviews를 작은 단위로 수정. 예: fresh_reply(refactor, targets=[])는 거절, 캐시5개에서2개 선택 preview의 previous_advice에2개만 존재, 실제targets 함수의 본문이 전송에 포함됨. 관련 검사 실행.
- [x] UI: tests/test_advisor_ui_flow.py/presentation.py에 최신 change_advice 우선, 전체5개 판단 표시, legacy 빈 탭/문맥 경고 부재, 제약은 접힘, cached 검토 기반 preview 행동을 먼저 검증. assistant.html/js/css/view를 수정. 적용 문구/버튼을 인접 배치하고 실제 수치와 AI 기대를 구분. 관련 검사/구문 확인.
- [x] 통합 검토: 사양 준수 후 품질 독립 검토. 이전 records 보존, 선택/현재 단계/서비스 일치와 실패 경로 확인.
- [x] 실제 시연: 이전 입력을 보존해 별도 job/case 구성. 실제 구독 Codex review→preview 응답을 저장하고5개 판단/targets/변경범위를 직접 대조. 검토 후사본apply→재분석. 편리한 시작 파일과 증거 폴더를 마련.
- [x] 실제 검증: 원본·수정본 빌드, 선택된 변경에 대한 계산/동작 회귀 검사, 허용되는 게임 조작/화면 캡처. 개선은 실제 차이만 기록. 실패 시 수정·재검사.
- [x] 브라우저: 블루/다크/화이트와 좁은 폭, 후보선택/단일·다중파일/코드비교/진행/결과/실행을 확인. 내용·단계·파일 수의 일치까지 검수. 전체 관련 테스트 후 전체 suite와 독립 최종검토.
- [ ] 보고서: 학교 HWP/PPTX 요구사항과 승인 중간DOCX, v2 읽기. 기존35쪽 분량·스타일 유지해 별도v3 Word/PDF 생성. 새 사례와 고정연구를 구분. 전체 페이지 PNG를 열어 표/그림/캡션/참고문헌/쪽나눔 검수.
- [ ] 완료 증거: 원본·Git 보존/실제 새실험·테스트·화면·시연절차와 보고서 검수 결과를 저장. 시작 링크·v3 산출물·실제로 확인한 범위와 남은 제한을 전달.
