<h1 align="center">
  <img src="docs/assets/routecontract-banner.png" alt="RouteContract — 조회 결과 뒤의 실행을 테스트합니다." width="900">
</h1>

<p align="center">
  <a href="https://github.com/ym0506/routecontract/actions/workflows/ci.yml?query=branch%3Amain"><img src="https://github.com/ym0506/routecontract/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="https://central.sonatype.com/artifact/io.github.ym0506.routecontract/routecontract-shardingsphere-5.5/0.1.3"><img src="https://img.shields.io/badge/Maven_Central-0.1.3-277DA1" alt="Maven Central 0.1.3"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache_2.0-182C38" alt="Apache License 2.0"></a>
</p>

<p align="center">
  <a href="#동작-확인">동작 확인</a> · <a href="#install-013">설치</a> · <a href="#사용-예">사용 예</a> · <a href="#문서">문서</a> · <a href="README.md">English</a>
</p>

**ShardingSphere-JDBC 테스트에서 반환값과 DB 실행을 함께 검사합니다.**

RouteContract는 ShardingSphere-JDBC를 사용하는 Java 앱의 통합 테스트용 라이브러리입니다. 기존 repository나
service 호출을 감싸고, 반환값 검사에 더해 **JDBC 실행 시도 횟수와 사용한 데이터 소스**를 검사합니다.

SQL을 바꾼 뒤에도 원하는 주문은 조회되지만, 이전에는 한 데이터 소스만 조회하던 코드가
두 곳을 조회할 수 있습니다. 이때 반환값 검사는 통과해도 추가한 실행 검사는 실패합니다.
JUnit·Maven·Gradle 테스트가 실패하므로 CI에서도 변경을 확인할 수 있습니다.

## 동작 확인

예제는 사용자 `3`의 결제 완료 주문을 조회합니다. 두 쿼리 모두 **주문 201, 사용자 3,
상태 PAID**를 반환합니다. 이 예제의 샤딩 규칙에서는 동등 조건이 한 데이터 소스로 향하고,
범위 조건은 설정된 두 데이터 소스를 모두 조회합니다.

| 쿼리 조건과 바인딩 값 | 반환된 주문 | JDBC 실행 시도 | 사용한 데이터 소스 |
| --- | --- | --- | --- |
| `user_id = ?`, 값 `3` | `201 / 3 / PAID` | 1회 | 1개 |
| `user_id BETWEEN ? AND ?`, 값 `3, 3` | `201 / 3 / PAID` | 2회 | 2개 |

이 테스트는 **실행 시도 최대 1회, 데이터 소스 최대 1개**를 허용합니다. 문서의 *예산(budget)*은
이 허용 상한을 뜻합니다. 범위 조회가 두 상한을 넘으면 리포트에 다음 결과가 나옵니다.

| 리포트 표시 | 이 예제에서의 뜻 |
| --- | --- |
| `POLICY_VIOLATION` | 허용 상한을 넘었으므로 계약 assertion이 실패했습니다. |
| `RCM201` | **JDBC 실행 시도 초과:** 허용 1회, 관측 2회. |
| `RCM202` | **데이터 소스 수 초과:** 허용 1개, 관측 2개. 리포트에서는 민감하지 않은 별칭으로 구분합니다. |

변경한 쿼리와 샤딩 규칙을 보고 추가 실행이 의도한 것인지 판단합니다. 의도한 변경이면
기준도 검토해서 바꾸고, 아니라면 쿼리나 설정을 수정합니다. 횟수 증가만으로 성능 저하를
단정하지는 않습니다. 수치는 `SQLExecutionHook`이 보고한 실행 시도이며, 물리 테이블 수나
전체 라우팅 계획을 뜻하지 않습니다.

![같은 주문이 반환되지만 실행 시도와 데이터 소스가 각각 하나에서 둘로 늘어 테스트의 허용 상한을 넘는 예제.](docs/assets/execution-comparison.svg)

[예제 실행](#quick-start) · [설치 없이 리포트 보기](docs/evidence/ci-review-report-example.md) ·
[예제 쿼리 소스](examples/first-project/src/test/java/io/github/ym0506/routecontract/examples/firstproject/OrderRepository.java)

## Install 0.1.3

기존 **Java 17 · ShardingSphere-JDBC 5.5.3** 테스트 프로젝트에 추가하세요.
지원하는 작업은 **동기식·비배치 `PreparedStatement` 호출**입니다.

**Gradle** — Groovy / Kotlin DSL 공통:

```kotlin
repositories { mavenCentral() }

dependencies {
    testImplementation("io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.3")
}
```

<details>
<summary><strong>Maven</strong> — pom.xml의 dependencies에 추가</summary>

```xml
<dependency>
  <groupId>io.github.ym0506.routecontract</groupId>
  <artifactId>routecontract-shardingsphere-5.5</artifactId>
  <version>0.1.3</version>
  <scope>test</scope>
</dependency>
```

</details>

기존 ShardingSphere·데이터 소스 설정을 유지하세요. 테스트 runtime의 ShardingSphere 모듈은
모두 **정확히 5.5.3**이어야 합니다. RouteContract가 ShardingSphere를 설치하거나 전체 의존성
버전을 맞춰주지는 않습니다. 이 의존성 설치에는 저장소 clone이나 로컬 설치기가 필요 없습니다.

<a id="가장-작은-사용-예"></a>

## 사용 예

기존 통합 테스트에서 작업 하나를 감쌉니다.

```java
import io.github.ym0506.routecontract.RouteAssertions;
import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.RouteSnapshot;

import static org.junit.jupiter.api.Assertions.assertEquals;

RouteSnapshot snapshot = RouteContract.capture("orders.find-by-user-id", () -> {
    Order actual = orderRepository.findByUserId(3L);
    assertEquals(201L, actual.id()); // 기존 업무 결과 assertion을 유지합니다.
});

RouteAssertions.assertThat(snapshot)
        .hasCompleteCapture()
        .hasNoReportedExecutionFailures()
        .hasExactlyObservedPhysicalAttempts(1)
        .observesExactlyDataSourceNames("ds_1");
```

`Order`와 `orderRepository`는 기존 테스트 fixture를 뜻합니다. 지원하는 JDBC 실행 범위에서
작동하는 작업을 선택하고, 예상 결과·데이터 소스 이름·실행 예산을 자신의 fixture에 맞게
정하세요. hook callback의 반환은 트랜잭션 커밋을 증명하지 않습니다.

이 Java assertion은 관측한 값을 직접 검사합니다. 실행 가능한 예제에서는 리포트를 쓰고,
이번 실행을 검토된 JSON 기준 파일과 비교하는 과정도 포함합니다.

### 기준을 검토한 뒤 CI에서 비교하기

**manifest**는 관측한 실행·데이터 소스 별칭·허용 상한을 담은 JSON 파일입니다.
**candidate**는 이번 실행 결과이고, **baseline**은 비교 기준으로 검토한 파일입니다.

1. 대표 작업을 capture하고 **candidate manifest**를 생성합니다.
2. 관측 내용, 민감하지 않은 데이터 소스 별칭, 실행 예산을 버전 관리에서 검토합니다.
3. baseline을 명시적으로 승인한 뒤 이후 candidate를 CI에서 비교합니다.

candidate 생성만으로 baseline이 승인되지는 않습니다. 의도한 변경도 새 검토를 거칩니다.
[첫 프로젝트 가이드](docs/first-project.ko.md)에서 Maven·Gradle 예제로 Central 설치부터
기준 검토와 CI 실패 확인까지 따라갈 수 있습니다.
[Manifest API 예제](docs/reference-guide.md#approved-manifests-and-structural-manifest-diffs)와
[CI 리포트 가이드](docs/ci-review-report.md)에서 Java API, Markdown·JSON 출력,
진단 코드와 조사 방법을 확인할 수 있습니다.

<a id="quick-start"></a>

## 예제 실행

**Java 17, Maven 3.9.x, 실행 중인 Docker**가 필요합니다. 처음에는 의존성과 MySQL 이미지를
내려받습니다. 예제는 **Maven Central의 0.1.3**을 사용하며, 합성 데이터에 맞게 검토한 기준 파일이
이미 들어 있습니다.

```bash
git clone https://github.com/ym0506/routecontract.git
cd routecontract/examples/first-project
mvn -B test
```

테스트가 통과하고 `build/routecontract/review.md`에 `MATCH`가 나와야 합니다.
반환된 주문과 DB 실행이 예제의 기준에 맞는다는 뜻입니다. 이제 쿼리를 바꿔 실행합니다.

```bash
mvn -B test -Droutecontract.query=range
```

**이 테스트는 실패해야 합니다.** 주문 반환값은 같지만 실행 시도와 데이터 소스가 각각
1에서 2로 늘어납니다. `build/routecontract/review.md`를 열어 위에서 설명한 두 상한 초과
(`RCM201`, `RCM202`)를 확인하세요. 다운로드·컴파일·Docker 오류는 이 예제의 예상 실패가 아닙니다.

`mvn -B test`를 다시 실행하면 원래 쿼리로 돌아가 `MATCH`가 나옵니다. 예제는 실행할 때마다
리포트를 새로 쓰므로, 원복하기 전에 실패 리포트를 읽으세요.

[Gradle 명령과 자기 테스트에 적용하는 방법](docs/first-project.ko.md) ·
[GitHub Actions에서 같은 MySQL 예제 실행](docs/first-project.ko.md#try-in-your-browser)

## 지원 범위

| 구분 | 공개 v0.1.3 |
| --- | --- |
| Java | 17 |
| ShardingSphere | JDBC, **정확히 5.5.3** |
| 실행 | 정상 반환하며 caller interruption이 없는 동기식·비배치 `PreparedStatement` 작업 |
| DB 검증 환경 | MySQL 8.4.11 · [공개 Gradle·Maven 소비자 검증](docs/evidence/release-0.1.3-central.md) |
| 검사 | capture 완전성, callback 결과, 실행 시도·데이터 소스 예산, manifest 구조 차이 |
| CI 출력 | Java assertion, 결정적인 Markdown·JSON 리포트, `ManifestReviewCli` |

Proxy, batch, reactive 실행, 애플리케이션이 만든 async 경계와 SQL Federation 경로 전반은
지원 범위 밖입니다. 관측 SQL이 없는 작업, callback 실패나 caller interruption이 있는 작업은
통과한 계약을 만들 수 없습니다. [전체 capture 경계](docs/reference-guide.md#v01-support-boundary)를 확인하세요.

**프로젝트 상태:** v0.1.3은 Maven Central에 공개되어 있습니다.
[0.2 core·adapter 분리](https://github.com/ym0506/routecontract/pull/62)는 개발 중이며 5.5.2 지원은
미출시입니다. 공개 소비자 검증은 유지관리자가 실행한 결과이고, 독립적인 외부 통합·반복 사용은
아직 확인되지 않았습니다.

## 문서

| 주제 | 안내 |
| --- | --- |
| 내 상황에 맞는 시작점 | [Start here](docs/start-here.md) |
| 공개 라이브러리를 프로젝트에 적용 | [첫 프로젝트](docs/first-project.ko.md) · [English](docs/first-project.md) |
| API·정책·상세 재현 절차 | [한국어 상세 가이드](docs/reference-guide.ko.md) · [English guide](docs/reference-guide.md) |
| CI 실패 검토 | [리포트·CLI](docs/ci-review-report.md) · [리포트 예제](docs/evidence/ci-review-report-example.md) |
| 관측 내용 이해 | [아키텍처](docs/architecture.md) · [명세](docs/specification.md) |
| 기존 도구와 비교 | [도구 비교](docs/competitive-analysis.md) · [datasource-proxy 실험](docs/empirical-comparison.md) |
| 관측 비용 확인 | [공개 0.1.3의 세 조건 비교·원시 측정·한계](docs/observer-cost.md) |
| 애플리케이션 코드 실험 | [세 가지 실험: 실행 대상·조회 예산·기존 테스트](docs/application-evaluations.ko.md) · [English](docs/application-evaluations.md) · 자체 실행 실험 |
| 릴리스 검증 | [v0.1.3 Central 검증](docs/evidence/release-0.1.3-central.md) · [증거 목록](docs/evidence-matrix.md) |
| 이전 통합 도구 | [v0.1.2 통합 가이드](docs/first-integration.md) — 과거 버전에 고정한 절차 |
| 기여 | [기여 가이드](CONTRIBUTING.md) · [로드맵](docs/product-roadmap.md) |

### 데이터 처리

snapshot과 manifest에는 원문 SQL, 바인딩 값, 접속 설정, 예외 메시지를 저장하지 않습니다.
다만 operation ID, 타입·데이터 소스 이름, SQL fingerprint도 민감한 개발 정보가 될 수 있으며,
fingerprint는 익명화가 아닙니다. 민감하지 않은 별칭과 합성 테스트 값을 사용하고,
공유 전에는 [SECURITY.md](SECURITY.md)를 확인하세요.

## 다음 버전을 함께 만들어요

ShardingSphere-JDBC를 사용한다면 [사용 버전과 SQL·설정 변경을 검증하는 방법](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml)을 알려주세요.
놓치고 있는 검사나 설치 중 막힌 지점을 짧게 적어주셔도 도움이 됩니다. 처음부터 설치하거나
공개 저장소를 준비할 필요는 없습니다. 공개 이슈에는 비공개 SQL·바인딩 값·접속 정보·전체 로그를 넣지 마세요.

재현 가능한 버그는 최소 합성 fixture와 함께 [이슈 양식](https://github.com/ym0506/routecontract/issues/new/choose)으로
남겨주세요. [사용 경험과 피드백 기록 기준](docs/user-feedback.md)도 확인할 수 있습니다.

## 라이선스

[Apache License 2.0](LICENSE). [서드파티 고지](THIRD_PARTY.md) ·
[선행 작업 공개](ORIGIN_AND_PRIOR_WORK.md) · [AI 사용 공개](AI_ASSISTANCE.md).

RouteContract는 Apache Software Foundation의 공식 프로젝트가 아니며 제휴·보증 관계가 없습니다.
Apache와 Apache ShardingSphere는 Apache Software Foundation의 상표입니다.
