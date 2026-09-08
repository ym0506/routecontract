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
| 실제 DB 반례 재현 / Reproduce | [v0.1.2 고정 Quick Start / Pinned Quick Start](reference-guide.md#quick-start) | Git, Java 17, Docker, network |
| CI 결과 검토 / Review a CI result | [미리보기 / Preview](evidence/ci-review-report-example.md) · [v0.1.3 리포트 생성 / Generate a report](ci-review-report.md#try-the-released-report-without-docker) | 미리보기는 설치 없음; 생성은 Git·Java 17·network / No install to preview; Git, Java 17 and network to generate |
| v0.1.3 설치 / Install v0.1.3 | [Maven Central 의존성 / Maven Central dependency](../README.md#install-013) | Java 17, ShardingSphere-JDBC 5.5.3, Gradle/Maven |
| v0.1.2 자산 설치 / Install v0.1.2 assets | [고정 로컬 설치 명령 / Pinned local installer](install-local.md) | Python 3.10+, curl, POSIX, network |
| v0.1.2 통합 참고 / v0.1.2 integration reference | [지원 범위와 빌드 경로 / Integration guide](first-integration.md) | Java 17, 기존 테스트 / Existing test |
| 질문·경험 공유 / Ask or share | [짧은 피드백 / Short feedback](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml), [도움받기 / Get help](user-feedback.md) | 설치 불필요 / No installation |
| 기여 / Contribute | [기여 지침 / Contributor guide](../CONTRIBUTING.md), [다음 단계 / Roadmap](product-roadmap.md) | 재현 가능한 문제 / Reproducible problem |

## 도입 전에 확인할 세 가지 / Check fit

1. **버전 / Version:** 최신 정식 v0.1.3은 ShardingSphere-JDBC **5.5.3** 대상이며 Markdown·JSON 리포트를 포함합니다.
   5.5.2 어댑터와 코어 분리는 [PR #62](https://github.com/ym0506/routecontract/pull/62)의 미출시 작업입니다.
2. **실행 경계 / Execution boundary:** 동기·non-batch `PreparedStatement` 작업을 대상으로 합니다.
   Proxy, 임의 async, batch, reactive와 완전한 라우팅 계획 검증은 지원 주장에 포함되지 않습니다.
3. **설치 / Distribution:** v0.1.3은 GitHub Release와 Maven Central에서 사용할 수 있습니다.
   [일반 테스트 의존성 설치](../README.md#install-013)와 [Central 검증 기록](evidence/release-0.1.3-central.md)을 참고하세요.
   기존 로컬 설치·파일럿 가이드는 v0.1.2에 고정되어 있습니다. 리포트 체험 경로는 v0.1.3을 사용합니다.

Released v0.1.3 supports exact ShardingSphere-JDBC 5.5.3 and synchronous non-batch
`PreparedStatement` operations, and includes Markdown/JSON reports. Use its
[ordinary Maven Central test dependency](../README.md#install-013); see the
[public verification record](evidence/release-0.1.3-central.md). Existing local-install and
assisted-pilot paths remain pinned to v0.1.2. The source-tag report example remains available.
Core separation and the 5.5.2 adapter remain unreleased.

## 성공 기준 / What success means

기존 업무 결과 검증을 유지한 상태로 capture → candidate → 기준 검토 → CI 비교를 연결합니다.
승인된 기준과 비교할 수 없는 수집 실패를 통과로 처리하지 않습니다. 실행 증가를 발견했다고
곧바로 성능 저하나 오류로 단정하지 않으며, 의도한 변경인지는 담당자가 검토합니다.

Keep the business assertion. Capture a candidate, review the baseline, then compare in CI.
Incomplete evidence cannot justify a pass. Additional attempts alone do not prove a defect or
latency regression; review whether a change is intentional.

도입이 막히면 [피드백 양식](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml)에
도달한 단계와 중단 이유를 남길 수 있습니다. SQL·바인딩 값·접속 정보·전체 로그는 보내지 마세요.
비공개 프로젝트도 자신의 환경에서 사용할 수 있으며, 설치 없이 사용 버전과 현재 검증 방법만
알려주셔도 됩니다. 소스 공개나 저장소 관리자 자격은 대화의 조건이 아닙니다.
[도움받는 방법과 사용·증거 기록 기준 / Help and evidence](user-feedback.md)에서 단계별 경로를 확인하세요.

Private-project use and questions before installation are welcome. Choose one existing test you are
authorized to modify. A reviewed baseline and a successful check can be kept in local tests or private
CI; public evidence is optional. Technical support limits above still apply.
