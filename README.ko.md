<h1 align="center">
  <img src="docs/assets/routecontract-banner.png" alt="RouteContract — 조회 결과 뒤의 실행을 테스트합니다." width="900">
</h1>

<p align="center">
  <a href="https://github.com/ym0506/routecontract/actions/workflows/ci.yml?query=branch%3Amain"><img src="https://github.com/ym0506/routecontract/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="https://central.sonatype.com/artifact/io.github.ym0506.routecontract/routecontract-shardingsphere-5.5/0.1.4"><img src="https://img.shields.io/badge/Maven_Central-0.1.4-277DA1" alt="Maven Central 0.1.4"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache_2.0-182C38" alt="Apache License 2.0"></a>
</p>

<p align="center">
  <a href="#사용-예">사용 예</a> · <a href="#동작-확인">동작 확인</a> · <a href="#install-014">설치</a> · <a href="#문서">문서</a> · <a href="README.md">English</a>
</p>

**같은 주문이 조회돼도, 조회하는 데이터베이스는 늘어날 수 있습니다.**

쿼리나 샤딩 설정을 바꾼 뒤에도 주문 조회 테스트는 통과할 수 있습니다. 하지만 그 사이
조회하는 DB가 한 곳에서 두 곳으로 늘어났다면, 반환된 주문만 확인하는 테스트로는
그 변화를 알 수 없습니다.

RouteContract는 기존 ShardingSphere-JDBC 통합 테스트에 DB 실행 검사를 추가합니다.
반환값 검사를 유지하면서 작업의 **JDBC 실행 시도 횟수와 사용한 데이터 소스**를 함께
검사합니다. 정해 둔 횟수나 대상에서 벗어나 검사가 실패하면, 일반 JUnit·Maven·Gradle
테스트와 CI 빌드도 실패해 변경을 확인할 수 있습니다.

**공개 0.1.4:** Java 17·21, ShardingSphere-JDBC **5.5.3**, 동기식·비배치 `PreparedStatement` 테스트를 지원합니다.

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
    assertEquals(201L, actual.id()); // 기존 반환값 검사를 유지합니다.
});

RouteAssertions.assertThat(snapshot)
        .hasCompleteCapture()
        .hasNoReportedExecutionFailures()
        .hasExactlyObservedPhysicalAttempts(1)
        .observesExactlyDataSourceNames("ds_1");
```

`Order`는 반환값 타입, `orderRepository`는 자신의 테스트에서 사용하는 조회 객체입니다.
지원하는 JDBC 실행 범위에서 작업 하나를 고르고, 예상 결과·데이터 소스 이름·실행 예산을
테스트 데이터와 샤딩 설정에 맞춰 정하세요. 훅이 실행의 반환을 보고해도 트랜잭션 커밋까지
확인한 것은 아닙니다.

이 코드는 관측한 값을 Java 테스트에서 직접 검사합니다. JSON 기준 파일은 선택 사항입니다.
[실행 가능한 예제](#quick-start)에서는 리포트를 쓰고, 이번 실행을 검토한 기준과 비교하는
과정도 확인할 수 있습니다.

## 동작 확인

예제는 사용자 `3`의 결제 완료 주문을 조회합니다. 두 쿼리 모두 **주문 201, 사용자 3,
상태 PAID**를 반환합니다. 이 예제의 샤딩 규칙에서는 동등 조건이 한 데이터 소스로 향하고,
범위 조건은 설정된 두 데이터 소스를 모두 조회합니다.

| 쿼리 조건과 바인딩 값 | 반환된 주문 | JDBC 실행 시도 | 사용한 데이터 소스 |
| --- | --- | --- | --- |
| `user_id = ?`, 값 `3` | `201 / 3 / PAID` | 1회 | 1개 |
| `user_id BETWEEN ? AND ?`, 값 `3, 3` | `201 / 3 / PAID` | 2회 | 2개 |

이 테스트에서 허용하는 상한은 **실행 시도 1회, 데이터 소스 1개**입니다. 문서에서는
이 상한을 실행 예산이라고 부릅니다. 범위 조회가 두 상한을 넘으면 리포트에 다음 결과가 나옵니다.

| 리포트 표시 | 이 예제에서의 뜻 |
| --- | --- |
| `POLICY_VIOLATION` | 허용 상한을 넘었으므로 계약 검사가 실패했습니다. |
| `RCM201` | **JDBC 실행 시도 초과:** 허용 1회, 관측 2회. |
| `RCM202` | **데이터 소스 수 초과:** 허용 1개, 관측 2개. 리포트에서는 민감하지 않은 별칭으로 구분합니다. |

변경한 쿼리와 샤딩 규칙을 보고 추가 실행이 의도한 것인지 판단합니다. 의도한 변경이면
기준도 검토해서 바꾸고, 아니라면 쿼리나 설정을 수정합니다. 횟수 증가만으로 성능 저하를
단정하지는 않습니다. 수치는 `SQLExecutionHook`이 보고한 실행 시도이며, 물리 테이블 수나
전체 라우팅 계획을 뜻하지 않습니다.

![같은 주문이 반환되지만 실행 시도와 데이터 소스가 각각 하나에서 둘로 늘어 테스트의 허용 상한을 넘는 예제.](docs/assets/execution-comparison.svg)

[예제 실행](#quick-start) · [설치 없이 리포트 보기](docs/evidence/ci-review-report-example.md) ·
[예제 쿼리 소스](examples/first-project/src/test/java/io/github/ym0506/routecontract/examples/firstproject/OrderRepository.java)

**공개된 실제 버그의 재현:** [INSERT SELECT가 “1행 처리 성공”을 반환하면서 shadow DB에
쓰는 사례](experiments/shadow-insert-select/README.md)를 실제 MySQL·공개 5.5.3에서 확인했습니다.
결과와 실행 횟수가 같아도 대상 DB 이름 검사가 필요한 이유를 보여 줍니다. 원래 보고자의
기여를 명시했으며 정상 대조군과 계약 검사가 실패하는 명령을 함께 제공합니다.

<a id="install-013"></a>
<a id="install-014"></a>

## 설치

기존 **Java 17 또는 21 · ShardingSphere-JDBC 5.5.3** 테스트 프로젝트에 추가하세요.
지원하는 작업은 **동기식·비배치 `PreparedStatement` 호출**입니다.

**Gradle** — Groovy / Kotlin DSL 공통:

```kotlin
repositories { mavenCentral() }

dependencies {
    testImplementation("io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.4")
}
```

<details>
<summary><strong>Maven</strong> — pom.xml의 dependencies에 추가</summary>

```xml
<dependency>
  <groupId>io.github.ym0506.routecontract</groupId>
  <artifactId>routecontract-shardingsphere-5.5</artifactId>
  <version>0.1.4</version>
  <scope>test</scope>
</dependency>
```

</details>

기존 ShardingSphere·데이터 소스 설정을 유지하세요. 테스트 실행에 쓰는 ShardingSphere 모듈은
모두 **정확히 5.5.3**이어야 합니다. RouteContract가 ShardingSphere를 설치하거나 전체 의존성
버전을 맞춰주지는 않습니다. 저장소를 복제하거나 별도의 로컬 설치기를 실행할 필요는 없습니다.

<a id="quick-start"></a>

## 예제 실행

**Java 17 또는 21, Maven 3.9.x, 실행 중인 Docker**가 필요합니다. 처음에는 의존성과 MySQL 이미지를
내려받습니다. 예제는 **Maven Central의 0.1.4**를 사용하며, 합성 데이터에 맞게 검토한 기준 파일이
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

<details>
<summary>검토한 JSON 기준과 CI에서 비교하려면</summary>

### 기준을 검토한 뒤 CI에서 비교하기

관측한 실행·데이터 소스 별칭·허용 상한을 JSON 파일로 저장할 수도 있습니다. 이 파일을
**실행 명세(manifest)**라고 부릅니다. 이번 실행에서 만든 파일이 `candidate`, 검토를 마쳐
비교 기준으로 삼은 파일이 `baseline`입니다.

1. 대표 작업의 실행을 수집해 `candidate` 파일을 만듭니다.
2. 관측 내용, 민감하지 않은 데이터 소스 별칭, 실행 예산을 버전 관리에서 검토합니다.
3. 담당자가 기준 파일을 승인한 뒤, 이후 실행 결과를 CI에서 비교합니다.

실행 결과를 저장하는 것과 기준을 승인하는 것은 별도 단계입니다. 의도한 변경도 새 검토를 거칩니다.
[첫 프로젝트 가이드](docs/first-project.ko.md)에서 Maven·Gradle 예제로 Central 설치부터
기준 검토와 CI 실패 확인까지 따라갈 수 있습니다.
[실행 명세 API 예제](docs/reference-guide.ko.md#실행-명세를-검토하고-비교하기)와
[CI 리포트 가이드](docs/ci-review-report.md)에서 Java API, Markdown·JSON 출력,
진단 코드와 조사 방법을 확인할 수 있습니다.

</details>

## 지원 범위

| 구분 | 공개 v0.1.4 |
| --- | --- |
| Java | 17과 21; [런타임 검증](docs/evidence/release-0.1.4-central.md#public-consumer-verification) |
| ShardingSphere | JDBC, **정확히 5.5.3** |
| 실행 | 정상 반환하고 호출 스레드에 인터럽트가 없는 동기식·비배치 `PreparedStatement` 작업 |
| DB 검증 환경 | MySQL 8.4.11 · [공개 Gradle·Maven 소비자 검증](docs/evidence/release-0.1.4-central.md) |
| 검사 | 수집 완전성, 훅의 처리 결과, 실행 시도·데이터 소스 예산, 실행 명세의 구조 차이 |
| CI 출력 | Java 검증 API, 같은 입력에 같은 내용을 내는 Markdown·JSON 리포트, `ManifestReviewCli` |

ShardingSphere-Proxy, 배치·리액티브 실행, 애플리케이션이 만든 비동기 작업과 SQL Federation
경로 전반은 지원하지 않습니다. SQL 실행이 관측되지 않거나 훅이 실패를 보고한 작업, 호출
스레드가 인터럽트된 작업도 계약 검사를 통과할 수 없습니다.
[수집 범위와 한계](docs/reference-guide.ko.md#v01-지원-범위)를 확인하세요.

**프로젝트 상태:** v0.1.4는 Maven Central에 공개되어 있습니다.
[코어와 어댑터를 분리하는 0.2](https://github.com/ym0506/routecontract/pull/62)는 개발 중이며 5.5.2 지원은
미출시입니다. 공개 소비자 검증은 유지관리자가 실행한 결과이고, 독립적인 외부 통합·반복 사용은
아직 확인되지 않았습니다.

## 문서

| 하고 싶은 일 | 문서 |
| --- | --- |
| 내 테스트에 적용하기 | [첫 프로젝트 가이드](docs/first-project.ko.md) |
| API와 정책 확인하기 | [상세 가이드](docs/reference-guide.ko.md) · [CI 리포트](docs/ci-review-report.md) |
| 관측 원리와 한계 이해하기 | [설계 결정과 이유](docs/design-decisions.ko.md) · [아키텍처](docs/architecture.md) |
| 실제 코드에서 얻은 결과 보기 | [애플리케이션 실험 세 가지](docs/application-evaluations.ko.md) · 유지관리자가 실행한 실험 |
| 공개 배포 검증 확인하기 | [0.1.4 Central 검증](docs/evidence/release-0.1.4-central.md) · [전체 검증 목록](docs/evidence-matrix.md) |
| 다른 도구와 비교하거나 기여하기 | [도구 비교](docs/competitive-analysis.md) · [기여 가이드](CONTRIBUTING.md) · [전체 문서](docs/start-here.md) |

### 데이터 처리

수집 결과와 실행 명세에는 원문 SQL, 바인딩 값, 접속 설정, 예외 메시지를 저장하지 않습니다.
다만 작업 ID, 타입·데이터 소스 이름, SQL의 해시값도 민감한 개발 정보가 될 수 있습니다.
해시값으로 바꿨다고 익명화되는 것은 아닙니다. 민감하지 않은 별칭과 합성 테스트 값을 사용하고,
공유 전에는 [SECURITY.md](SECURITY.md)를 확인하세요.

## 다음 버전을 함께 만들어요

ShardingSphere-JDBC를 사용한다면 [사용 버전과 SQL·설정 변경을 검증하는 방법](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml)을 알려주세요.
놓치고 있는 검사나 설치 중 막힌 지점을 짧게 적어주셔도 도움이 됩니다. 처음부터 설치하거나
공개 저장소를 준비할 필요는 없습니다. 공개 이슈에는 비공개 SQL·바인딩 값·접속 정보·전체 로그를 넣지 마세요.

재현 가능한 버그는 최소한의 합성 테스트 구성과 함께 [이슈 양식](https://github.com/ym0506/routecontract/issues/new/choose)으로
남겨주세요. [사용 경험과 피드백 기록 기준](docs/user-feedback.md)도 확인할 수 있습니다.

## 라이선스

[Apache License 2.0](LICENSE). [서드파티 고지](THIRD_PARTY.md) ·
[선행 작업 공개](ORIGIN_AND_PRIOR_WORK.md) · [AI 사용 공개](AI_ASSISTANCE.md).

RouteContract는 Apache Software Foundation의 공식 프로젝트가 아니며 제휴·보증 관계가 없습니다.
Apache와 Apache ShardingSphere는 Apache Software Foundation의 상표입니다.
