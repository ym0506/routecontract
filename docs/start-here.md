# Start here

<a id="routecontract-시작하기--start-here"></a>

[한국어](#한국어) · [English README](../README.md)

RouteContract adds execution checks to **Java integration tests that already use ShardingSphere-JDBC**.
ShardingSphere can send one application query to several configured databases. A test that checks
only the returned rows can therefore pass after a SQL or sharding-rule change starts querying an
extra database. RouteContract lets the test also check the observed execution attempts and data sources.

<a id="목적에-맞는-한-경로만-선택하세요--choose-one-path"></a>

## Run one example

The included MySQL test asks for one user's paid orders. Both query forms return the same order:
`order 201 / user 3 / PAID`. The execution changes:

| Query predicate | Returned order | Observed JDBC attempts / data sources |
| --- | --- | --- |
| `user_id = ?`, bound value `3` | `201 / 3 / PAID` | 1 / 1 |
| `user_id BETWEEN ? AND ?`, bound values `3, 3` | Same order | 2 / 2 |

This is an intentional synthetic example. Its [INLINE sharding configuration](../examples/first-project/src/test/resources/sharding.yaml)
routes equality by `user_id % 2` and enables range queries across the configured targets.
It does not mean every `BETWEEN` query behaves this way.

**Start with the [current 0.1.3 MySQL example](first-project.md#run-the-published-dependency).**
It uses Java 17 or 21, Maven or Gradle, and Docker, and downloads the released library from Maven Central.
The database setup and a reviewed expectation for this example are included.

<a id="성공-기준--what-success-means"></a>

1. Run the normal query. The order assertion passes and the execution report says `MATCH`.
2. Select the range query. The order assertion still passes, but the added execution check fails:
   the test allows one attempt and one data source and observes two of each.
3. Read the report before restoring the normal query. Restore it and the test passes again.

`RCM201` means too many observed JDBC execution attempts; `RCM202` means too many distinct
observed data sources. In this example, each is **observed 2, allowed 1**. These are hook-reported
attempts, not physical-table counts or a measurement of latency.

Without local Docker, use the [same demonstration in your GitHub fork](first-project.md#try-in-your-browser).
To inspect the output without running anything, [read the example report](evidence/ci-review-report-example.md).

<a id="도입-전에-확인할-세-가지--check-fit"></a>

## Add it to an existing test

For **Java 17 or 21 and exact ShardingSphere-JDBC 5.5.3**, add the [0.1.3 test dependency](../README.md#install-013)
and [wrap one repository or service call](first-project.md#adapt-one-existing-test). Keep your existing
ShardingSphere setup and returned-value assertion. The supported calls are synchronous, non-batch
`PreparedStatement` operations.

Choose the expected execution for that operation. If you use a saved JSON expectation (a *baseline*),
review it before committing it; the example's baseline belongs only to its synthetic data.
On a later SQL or configuration change, an unexpected execution change can fail the ordinary test
and CI build. Inspect the change before deciding to fix it or review a new expectation.
A higher count alone does not prove a performance problem.

[Ask a question or get setup help](https://github.com/ym0506/routecontract/discussions/76).
A version and short question are enough; a private project can stay private.

## 한국어

RouteContract는 **ShardingSphere-JDBC를 이미 사용하는 Java 통합 테스트**에 넣는 라이브러리입니다.
ShardingSphere는 애플리케이션의 SQL 하나를 여러 데이터베이스로 보낼 수 있습니다.
SQL이나 샤딩 설정을 바꾼 뒤 반환된 주문은 같아도, 조회하는 DB가 하나에서 둘로 늘어날 수 있습니다.
기존 반환값 검사는 그대로 두고, 실행 시도와 사용한 데이터 소스가 정한 기준에 맞는지도 검사합니다.

[현재 0.1.3 MySQL 예제 실행](first-project.ko.md#예제-실행)부터 시작하세요.
Java 17 또는 21, Maven 또는 Gradle, Docker가 필요합니다. DB 구성과 이 예제에서 사용할 기준 파일은
이미 준비되어 있습니다. 이 기준 파일을 자기 프로젝트의 기준으로 그대로 복사하지는 마세요.

1. 정상 쿼리를 실행하면 주문 검증과 실행 검사가 모두 통과하고 `MATCH`가 나옵니다.
2. 범위 쿼리로 바꾸면 같은 주문을 반환하지만 실행 시도와 데이터 소스가 각각 1에서 2로 늘어납니다.
   테스트는 각각 최대 1을 허용하므로 실패해야 합니다.
3. 실패 리포트를 읽은 뒤 정상 쿼리로 돌아가면 다시 통과합니다.

`RCM201`은 JDBC 실행 시도 수 초과, `RCM202`는 서로 다른 데이터 소스 수 초과입니다.
이 예제에서는 둘 다 **허용 1, 관측 2**입니다. 예제의 INLINE 샤딩 설정이 범위 조회를 모든
설정 대상에 보내도록 허용해서 생기는 차이이며, 모든 `BETWEEN` 조회가 그렇다는 뜻은 아닙니다.
관측한 수치는 물리 테이블 수나 응답 시간 측정값이 아닙니다.

Docker를 설치하기 어렵다면 [자기 GitHub fork에서 같은 예제 실행](first-project.ko.md#try-in-your-browser)을
선택할 수 있습니다. 동작을 확인했다면 [기존 테스트 한 개에 적용](first-project.ko.md#자신의-테스트와-ci로-옮기기)으로
이어가세요. 자기 테스트의 반환값·실행 기준은 직접 검토해야 합니다.
현재 지원 범위는 Java 17 또는 21·정확히 ShardingSphere-JDBC 5.5.3의 동기식·비배치 `PreparedStatement`입니다.

[설치 전 질문이나 적용 도움](https://github.com/ym0506/routecontract/discussions/76)은 사용 버전과
짧은 질문으로 시작해도 됩니다. 비공개 SQL·바인딩 값·접속 정보·전체 로그를 공개할 필요는 없습니다.

<details>
<summary>Reference, earlier versions and contribution / 상세 자료·이전 버전·기여</summary>

- [Application evaluations](application-evaluations.md) · [애플리케이션 실험](application-evaluations.ko.md)
- [Report API and CLI](ci-review-report.md) · [Capture support boundary](reference-guide.md#v01-support-boundary)
- [Published 0.1.3 verification](evidence/release-0.1.3-central.md) · [Help and use records](user-feedback.md)
- **Historical 0.1.2 only:** [pinned Quick Start](reference-guide.md#quick-start), [local installer](install-local.md), [integration tooling](first-integration.md). These are not needed for the current example.
- [Contributing](../CONTRIBUTING.md) · [Roadmap](product-roadmap.md). The 0.2 core split and 5.5.2 adapter remain unreleased.

</details>
