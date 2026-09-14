# Documentation

<a id="start-here"></a>

<a id="routecontract-시작하기--start-here"></a>

[English README](../README.md) · [한국어 README](../README.ko.md) · [한국어 안내](#한국어)

Start with **released 0.1.4**, Java 17 or 21, and exact ShardingSphere-JDBC 5.5.3.
The 0.2 core/adapter split and 5.5.2 support are in development, not a published installation path.

<a id="목적에-맞는-한-경로만-선택하세요--choose-one-path"></a>
<a id="성공-기준--what-success-means"></a>

<a id="run-one-example"></a>

## Try it and apply it

| Your next step | Guide | What you will see |
| --- | --- | --- |
| Understand the output first | [Example report](evidence/ci-review-report-example.md) | The same order is returned, but attempts/data sources rise from 1 to 2. |
| Run a complete example | [First project](first-project.md) · [한국어](first-project.ko.md) | A passing query, an expected execution-check failure and a passing restored query. |
| Try without local Docker | [Run in your GitHub fork](first-project.md#try-in-your-browser) | The same MySQL example and retained reports in Actions. |
| Add checks to your test | [Adapt one operation](first-project.md#adapt-one-existing-test) | Ordinary Java assertions; a saved JSON baseline is optional. |
| Review execution changes in CI | [Baseline walkthrough](first-project.md#capture-and-review-your-first-baseline) · [Report API and CLI](ci-review-report.md) | A reviewed expectation, a candidate and an explained comparison. |

<a id="도입-전에-확인할-세-가지--check-fit"></a>
<a id="add-it-to-an-existing-test"></a>

## Understand the design and choose a tool

- [Design decisions and code](design-decisions.md): why observation happens at the physical hook, how worker events are attributed, and why incomplete captures cannot pass.
- [Architecture](architecture.md) and [specification](specification.md): event lifecycle, state, contract eligibility and information boundaries.
- [API reference](reference-guide.md) · [한국어 상세 가이드](reference-guide.ko.md): APIs and detailed examples, with historical workflows labelled separately.
- [Tool comparison](competitive-analysis.md) and [datasource-proxy experiment](empirical-comparison.md): built-in diagnostics, existing JDBC tools and the cost of custom wiring.
- [Security and data handling](../SECURITY.md): what the library retains and what to review before sharing.

## Inspect results and their limits

| Evidence | Scope |
| --- | --- |
| [0.1.4 public installation checks](evidence/release-0.1.4-central.md) | Public Central artifacts; recorded Gradle/Maven and Java 17/21 consumers. |
| [Application experiments](application-evaluations.md) · [한국어](application-evaluations.ko.md) | Maintainer-run 0.1.3 evaluations: changed destinations, different budgets and capture in an existing test. |
| [Observer cost](observer-cost.md) | Local 0.1.3 timing/allocation experiment; no general latency claim. |
| [Capture retention](capture-retention.md) | Repeated-operation and retained-object diagnostics with stated limitations. |
| [Use and feedback](user-feedback.md) | Conversations, assistance, integration and repeat use distinguished from verification and publication permission. |

The release checks and experiments are maintainer-run evidence. Independent integration and
repeat use have not yet been verified. Each record retains its own version and environment;
a historical experiment does not become current-version evidence when a new release ships.

## Ask or contribute

[Ask about fit or an installation blocker](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml).
A short question and your version are enough; no installation or public repository is required.
Keep private SQL, bind values, connection details and full logs out of public issues.

For implementation work, read [Contributing](../CONTRIBUTING.md), then the
[roadmap](product-roadmap.md). A useful contribution can be a confusing diagnostic with a
reproducer, a missing safe control or a documented compatibility failure.

## 한국어

현재 공개 버전은 **0.1.4**입니다. Java 17·21과 **ShardingSphere-JDBC 5.5.3**에서,
동기식으로 실행하는 비배치 `PreparedStatement` 작업을 검사합니다.

- 동작부터 보고 싶다면 [첫 프로젝트](first-project.ko.md)를 따라가세요. 같은 주문을 반환하면서
  조회 대상이 늘어나는 상황을 만들고, 테스트가 실패하는 이유를 확인합니다.
- 설치 전에 결과만 보려면 [리포트 예제](evidence/ci-review-report-example.md)를 읽으세요.
  로컬 Docker 없이 실행하려면 [GitHub Actions 안내](first-project.ko.md#try-in-your-browser)를 이용하세요.
- 내 코드에 넣으려면 [기존 테스트에 적용하는 방법](first-project.ko.md#자신의-테스트와-ci로-옮기기)을 보세요.
  반환값 검사는 유지하고, 그 작업에 필요한 실행 횟수나 대상 검사를 더합니다.
- 설계를 검토하려면 [설계 판단과 코드](design-decisions.ko.md), 사용법을 자세히 보려면
  [한국어 상세 가이드](reference-guide.ko.md)를 읽으세요.
- 실제로 무엇을 확인했는지는 [애플리케이션 실험](application-evaluations.ko.md)과
  [0.1.4 설치 검증](evidence/release-0.1.4-central.md)에 나와 있습니다. 자체 실험과 외부 사용 실적은 구분합니다.

<details>
<summary>Earlier releases and contest records / 이전 버전·대회 기록</summary>

These records preserve their original versions and claims. They are not the recommended path
for a new installation.

- [Historical v0.1.2 Quick Start](reference-guide.md#quick-start), [local installer](install-local.md) and [integration tooling](first-integration.md).
- [Historical contest evidence matrix](evidence-matrix.md) and [August development plan](development-plan.md).
- [Release history](../CHANGELOG.md) and [release procedure](../RELEASING.md).

</details>
