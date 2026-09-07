# RouteContract 시작하기 / Start here

업무 테스트가 성공해도 데이터베이스 실행 구조는 바뀔 수 있습니다. RouteContract는
ShardingSphere-JDBC 테스트의 **관측된 물리 JDBC 실행 시도**를 승인된 기준과 비교합니다.
예를 들어 같은 주문 한 건을 반환하는 조회가 실행 시도 `1 → 2`로 바뀌었을 때 CI에서 발견합니다.

**Business tests can pass while database execution changes.** RouteContract compares observed
ShardingSphere-JDBC physical execution attempts with a reviewed baseline, including the example
where the same result needs `1 → 2` observed attempts.

## 목적에 맞는 한 경로만 선택하세요 / Choose one path

| 목적 / Goal | 시작점 / Start | 필요한 것 / Requirements |
| --- | --- | --- |
| 동작 이해 / Understand | [2분 54초 데모 / Demo](https://www.youtube.com/watch?v=pcgvNNxd1mM) | 설치 없음 / No installation |
| 실제 DB 반례 재현 / Reproduce | [정식판 Quick Start / Released Quick Start](../README.en.md#quick-start) | Git, Java 17, Docker, network |
| CI 결과 검토 / Review a CI result | [Markdown·JSON 리포트 / Review reports](ci-review-report.md) | 개발 소스 + Java 17 / Development source + Java 17 |
| 내 테스트에 도입 / Integrate | [지원 범위와 빌드 경로 / Integration guide](first-integration.md) | 기존 테스트 / Existing test |
| 기여 / Contribute | [기여 지침 / Contributor guide](../CONTRIBUTING.md), [다음 단계 / Roadmap](product-roadmap.md) | 재현 가능한 문제 / Reproducible problem |

## 도입 전에 확인할 세 가지 / Check fit

1. **버전 / Version:** 정식 v0.1.2는 ShardingSphere-JDBC **5.5.3** 대상입니다.
   5.5.2 어댑터와 코어 분리는 [PR #62](https://github.com/ym0506/routecontract/pull/62)의 미출시 작업입니다.
2. **실행 경계 / Execution boundary:** 동기·non-batch `PreparedStatement` 작업을 대상으로 합니다.
   Proxy, 임의 async, batch, reactive와 완전한 라우팅 계획 검증은 지원 주장에 포함되지 않습니다.
3. **설치 / Distribution:** v0.1.2는 Maven Central에 없습니다. 현재는 검증된 GitHub Release 자산을
   사용합니다. 상세 가이드에서 Gradle 또는 Maven 한 경로만 선택하세요.

Released v0.1.2 supports exact ShardingSphere-JDBC 5.5.3 and synchronous non-batch
`PreparedStatement` operations. Core separation and the 5.5.2 adapter remain unreleased.
Use verified GitHub Release assets until Central publication is independently confirmed.

## 성공 기준 / What success means

기존 업무 결과 검증을 유지한 상태로 capture → candidate → 기준 검토 → CI 비교를 연결합니다.
승인된 기준과 비교할 수 없는 수집 실패를 통과로 처리하지 않습니다. 실행 증가를 발견했다고
곧바로 성능 저하나 오류로 단정하지 않으며, 의도한 변경인지는 담당자가 검토합니다.

Keep the business assertion. Capture a candidate, review the baseline, then compare in CI.
Incomplete evidence cannot justify a pass. Additional attempts alone do not prove a defect or
latency regression; review whether a change is intentional.

도입이 막히면 [피드백 양식](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml)에
도달한 단계와 중단 이유를 남길 수 있습니다. SQL·바인딩 값·접속 정보·전체 로그는 보내지 마세요.
공개 저장소의 권한 있는 관리자는 [통합 상담 / Assisted pilot](https://github.com/ym0506/routecontract/discussions/34)을
신청할 수 있습니다. 상담·로컬 실행·정식 외부 통합은 서로 다른 결과로 기록합니다.
