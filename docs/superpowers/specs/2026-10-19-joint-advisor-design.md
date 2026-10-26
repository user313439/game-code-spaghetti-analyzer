# 공동 검토·파일 탭·사전 검토

사용자가 2026-10-19 직전 설명의 진행을 승인했다. 같은 폴더에서 구현하며 브랜치/커밋/push/유료 API/학교 제출은 하지 않는다. 현재 실제 미적용 preview와 과거 보고서/시연을 보존한다. 검증에는 별도 검사 작업과 명시적 대체 AI 응답을 사용한다.

## 데이터 계약

새 응답은 기존 overview/reasons/suggestions/tests/uncertainty/edits와 함께 다음을 갖는다.

- `file_reviews`: 선택 파일 전체에 대해 정확히 하나씩. 필드 `path, role, finding, reason, change, expected_effect, impact, decision, evidence, checks`. decision은 `refactor`, `keep`, `needs_context`. evidence/checks는 문자열 배열, 나머지는 문자열. 경로/누락/중복을 서버 검사한다. preview에서 실제 수정할 파일과 refactor 판단이 일치해야 한다.
- `relationships`: 선택 파일 사이 실제 관계와 함께 확인할 동작을 설명하는 문자열 배열. 없는 관계를 만들지 않는다.
- 기존 저장 응답은 file_reviews가 없어도 그대로 표시하며 새 설명을 실제 AI 응답인 것처럼 만들어 넣지 않는다.

원본 파일당180KB 한도와 교체12개 제한을 유지한다. 전송 JSON은360KB 이내다. 큰 묶음은 파일 앞부분과 메트릭/AST상 관련 함수의 문맥을 한도 안에서 추출한다. full/focused, 파일별 실제 제공 범위와 모든 원본 SHA를 기록한다. 모든 파일 원문 전체를 검토했다고 표현하지 않는다. 발췌가 부족하면 needs_context로 보류한다. preview도 선택한 문맥에서 근거가 있는 정확한 문자열 변경만 적용 검증한다.

## 사전 검토 API

- 기존 `/api/jobs/{id}/assistant` 상태/preview/apply 호환 유지.
- `GET .../assistant/review`: 별도 사전검토 상태. idle/running/complete/failed, advice, candidates(선택 fqn 목록), source_hashes, service/mode/model, progress, started_at, context, cached.
- 기존 assistant POST의 action=`review`는 서버가 서로 다른 파일의 G-SI 상위5개를 골라 공동 제안을 생성한다. service/mode/model/api_key는 기존 요청 형식. 기존 assistant.json 미적용 preview를 바꾸지 않는다.
- 캐시는 `assistant_reviews.json`에 별도 저장. 파일 SHA/후보와 지표/서비스/방식/모델/프롬프트 버전이 같으면 재사용한다. 오래된 원본에는 캐시를 표시하지 않는다.
- 연결을 선택한 사용자가 ‘상위 5개 미리 검토’를 누르면 한 번 준비한다. 페이지 열기나 후보 클릭만으로 유료/구독 AI 요청을 자동 생성하지 않는다. 저장한 설명은 후보 선택 시 바로 표시한다. 기존 선택에 대한 새 제안/preview 경로도 유지한다.

## UI

공동 overview 아래 파일별 탭으로 구체적인 역할/근거/이유/변경 또는 유지 판단을 표시한다. 코드 비교도 탭으로 전환하며 유지 파일은 변경 없음으로 표시한다. 결과는 전체 결론과 파일별 카드/탭, 실제 지표 변화로 구성하고 슬래시 나열을 없앤다. 과거 응답에서 개별 설명이 없으면 확인된 범위만 표시한다.

진행 카드는 작업/단계/막대/경과 시간만 기본 표시한다. 근거 없는 백분율/예상 시간을 만들지 않는다. 게임 카드는 `demo-name` 제목, `demo-description` 짧은 설명, 우측 하단 실행 버튼과 활성 작업 중에만 진행 표시를 둔다. 오류만 조건부 노출한다. 게임 API는 기존 필드와 함께 `started_at`, `progress:{stage,label,step,total,indeterminate}`를 제공한다. 새 게임 AI/적용/실행은 검증에서 하지 않는다.

표는 native table 레이아웃과 가로 스크롤 래퍼로 전체 폭을 채운다. 저장된 보고서/CSP/sandbox를 유지하고 응답용 JS/CSS만 수정한다. iframe 루트의 중첩 세로 스크롤이 재발하지 않게 실제 폭/높이를 검수한다.
