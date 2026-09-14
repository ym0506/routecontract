# RouteContract가 조회 결과와 실행 과정을 함께 검사하는 이유

[English](design-decisions.md) · [예제 실행](first-project.ko.md) · [구조와 관측 범위](architecture.md) · [상세 사용법](reference-guide.ko.md)

쿼리를 바꾼 뒤에도 원하는 주문은 그대로 조회될 수 있습니다. 하지만 그 주문을 찾으려고 DB를 하나 더 조회하거나, 실행 횟수는 같은데 다른 DB를 방문할 수 있습니다. 반환값 검사와 실행 검사는 이런 차이를 각각 확인합니다.

이 문서는 **공개 버전 0.1.4**의 설계를 설명합니다. 지원 범위는 **Java 17·21, 정확히 ShardingSphere-JDBC 5.5.3**입니다. [0.2의 코어·어댑터 분리 작업](https://github.com/ym0506/routecontract/pull/62)은 아직 배포되지 않았습니다.

## 먼저 요구사항을 정하고, 그에 맞는 검사를 고릅니다

| 이 작업이 지켜야 할 조건 | 사용할 검사 | 이 검사만으로 알 수 없는 것 |
| --- | --- | --- |
| 기대한 주문을 반환한다 | 기존 반환값 검사 | 어느 DB를 방문했는지 |
| 합의한 실행량을 넘지 않는다 | 실행 시도 수와 서로 다른 데이터 소스 수의 상한 | 응답 시간이나 서버 수 |
| 정해진 대상으로 실행한다 | 예상 데이터 소스 이름 또는 검토한 별칭 검사 | 트랜잭션 커밋이나 고객별 데이터 격리 여부 |
| 검토한 실행 구조를 유지한다 | 정해진 형식으로 저장한 실행 명세 비교 | 발견한 차이가 실제 결함인지 |

[첫 프로젝트 테스트](../examples/first-project/src/test/java/io/github/ym0506/routecontract/examples/firstproject/OrderContractTest.java)는 반환된 행부터 확인합니다. 동등 조건 조회와 같은 값의 범위 조회는 같은 주문을 반환하지만, 관측한 물리 JDBC 실행 시도는 각각 1회와 2회입니다.

[횟수는 같고 대상만 바뀌는 실험](application-evaluations.md#same-count-different-data-source)도 있습니다. 실행 횟수만 세면 놓칠 수 있는 조건을 보여줍니다. 이 실험은 합성 데이터를 사용했으며, 라우팅 코드를 가져온 애플리케이션에 결함이 있다는 뜻은 아닙니다.

## 1. ShardingSphere가 물리 작업을 정한 뒤 관측합니다

ShardingSphere 바깥에 JDBC 래퍼를 두면 애플리케이션이 호출한 논리 SQL을 볼 수 있습니다. ShardingSphere는 그 SQL을 여러 물리 실행으로 나눌 수 있습니다. RouteContract는 해당 버전의 `SQLExecutionHook`으로 물리 JDBC 실행 콜백에서 전달하는 데이터 소스 이름과 재작성된 SQL을 관측합니다.

지원하는 실행 경로에서는 각 물리 데이터 소스를 따로 감쌀 필요가 없습니다. 물론 각 데이터 소스를 감싸는 방법도 가능합니다. [datasource-proxy 비교 실험](empirical-comparison.md)은 두 위치에 래퍼를 두고, 작업별로 실행을 구분하는 코드도 직접 구성했습니다. JDBC 실행 횟수를 세는 것 자체는 새로운 기능이 아닙니다.

대신 특정 버전의 동작에 의존합니다. 실행 시도 수는 물리 테이블 수나 전체 라우팅 계획이 아닙니다. 한 번의 실행에 여러 테이블을 묶은 `UNION ALL`이 들어갈 수도 있습니다. 수집 전 검사는 `infra-executor`·`infra-spi`의 버전과 SPI 제공자 등록을 확인합니다. 전체 의존성 구성을 검사하거나 버전을 맞춰 주지는 않으므로, 모든 ShardingSphere 모듈을 정확히 5.5.3으로 유지해야 합니다.

확인할 코드: [훅 어댑터](../routecontract-shardingsphere-5.5/src/main/java/io/github/ym0506/routecontract/internal/RouteContractSqlExecutionHook.java), [실행 환경 사전 검사](../routecontract-shardingsphere-5.5/src/main/java/io/github/ym0506/routecontract/internal/ShardingSphere553Preflight.java), [지원하지 않는 구성을 거부하는 테스트](../routecontract-shardingsphere-5.5/src/test/java/io/github/ym0506/routecontract/internal/ShardingSphere553PreflightTest.java).

## 2. 작업 스레드의 이벤트가 어느 요청에 속하는지 구분합니다

서비스 메서드 하나가 여러 SQL을 실행할 수 있고, ShardingSphere는 스레드 풀에서 물리 작업을 처리할 수 있습니다. 프로그램 전체에서 횟수를 세면 여러 작업이 섞입니다. 호출한 스레드에서만 세면 다른 스레드의 실행을 놓칠 수 있습니다.

RouteContract는 수집할 작업마다 식별 토큰을 부여합니다. 지원하는 ShardingSphere 실행기가 작업을 제출할 때 그 문맥을 작업 스레드로 전달합니다. 훅 인스턴스는 토큰으로 해당 수집 대상을 찾고, 자신에게 들어온 시작과 종료 이벤트를 짝지어 기록합니다. 애플리케이션 작업에서 예외가 발생해도 호출 스레드의 문맥과 등록된 수집 대상을 정리합니다.

이 방식은 해당 미들웨어의 문맥 전달 기능에 의존합니다. 애플리케이션이 별도로 만든 스레드, 리액티브 흐름, `@Async`까지 전달된다고 보장하지 않습니다. [반복 MySQL 테스트 기록](architecture.md#correlation)도 여러 호출의 수집 구간이 동시에 열렸다는 사실과, 물리 콜백이 실제로 같은 순간 실행됐다는 사실을 구분합니다.

확인할 코드: [CaptureRegistry](../routecontract-shardingsphere-5.5/src/main/java/io/github/ym0506/routecontract/internal/CaptureRegistry.java), [CaptureScope](../routecontract-shardingsphere-5.5/src/main/java/io/github/ym0506/routecontract/internal/CaptureScope.java), [수집 테스트](../routecontract-shardingsphere-5.5/src/test/java/io/github/ym0506/routecontract/RouteContractTest.java). 반복 실행 뒤 객체가 남는지는 [별도 진단 기록](capture-retention.md)에서 범위와 한계를 확인할 수 있습니다.

## 3. 불완전하게 관측했다면 통과시키지 않습니다

“실행 시도가 0회 관측됐다”는 말은 SQL이 실행되지 않았다는 뜻일 수도 있고, 유효한 수집 결과를 얻지 못했다는 뜻일 수도 있습니다. 병렬 작업이 실패하면 제출한 작업이 모두 끝나기 전에 호출이 반환될 수 있습니다. 이때까지 모인 이벤트만 전체 실행량으로 판단하면 통과해서는 안 되는 테스트를 통과시킬 수 있습니다.

계약 검사를 통과하려면 호출이 정상 반환되고 종료 시 호출 스레드가 인터럽트되지 않아야 합니다. 관측한 실행이 있어야 하고, 종료 결과가 빠지거나 수집기 진단이 남아 있어서도 안 됩니다. 콜백이 실패를 보고한 경우도 통과할 수 없습니다. 보관 한도를 넘으면 불완전한 수집으로 처리합니다. 일정 시간 기다리는 것만으로 모든 작업의 종료를 증명할 수는 없습니다.

따라서 일부 수집 결과는 진단용으로만 사용할 수 있습니다. `finishSuccess`는 감싼 물리 `executeSQL` 호출이 반환됐다는 보고입니다. 바깥의 JDBC 작업이나 트랜잭션이 성공했다는 보장은 아닙니다. 통과 판단의 지원 범위는 동기식·비배치 `PreparedStatement`이며, 결과가 확정된 뒤 도착하는 모든 콜백을 감지한다고 보장하지 않습니다.

확인할 코드: [RouteAssertions](../routecontract-shardingsphere-5.5/src/main/java/io/github/ym0506/routecontract/RouteAssertions.java), [MutableCapture](../routecontract-shardingsphere-5.5/src/main/java/io/github/ym0506/routecontract/internal/MutableCapture.java). [MySQL 회귀 테스트 모음](../examples/mysql/src/test/java/io/github/ym0506/routecontract/example/ObservedExecutionRegressionCorpusMySqlTest.java)은 반환값과 실행 조건을 따로 검사합니다.

## 4. 이벤트 도착 순서 대신 실행 구조를 비교합니다

같은 작업도 스레드 실행 순서에 따라 이벤트가 들어오는 순서는 달라질 수 있습니다. 이 순서나 시각, 무작위 수집 식별자를 기준 파일에 저장하면 의미 없는 차이가 생깁니다. 실행 명세는 구조가 같은 항목을 묶어 정렬하고, 같은 항목이 몇 번 있었는지 기록합니다. 같은 실행들의 순서만 바뀌면 같다고 판단하지만, 한 번 실행하던 것을 두 번 실행하면 차이로 남습니다.

원본 SQL과 바인딩 값 대신 SQL 지문과 매개변수의 개수·타입을 저장합니다. 데이터 소스 이름은 호출자가 검토한 별칭으로 바꿉니다. **보관하는 데이터를 줄이는 방식이며 익명화를 보장하지 않습니다.** 추측하기 쉬운 SQL은 해시도 대조할 수 있고, 타입 이름은 내부 구조를 드러낼 수 있습니다. 별칭 대응 관계를 잘못 바꾸면 대상 변경을 숨길 수도 있습니다. 지문은 정확히 재작성된 SQL을 기준으로 하므로 두 쿼리의 의미가 같은지 증명하지 않습니다.

확인할 코드: [ObservedExecutionManifest](../routecontract-shardingsphere-5.5/src/main/java/io/github/ym0506/routecontract/manifest/ObservedExecutionManifest.java), [명세 정렬·중복 집계·검증 테스트](../routecontract-shardingsphere-5.5/src/test/java/io/github/ym0506/routecontract/manifest/ObservedExecutionManifestTest.java). 자료를 공유하기 전에는 [데이터 처리 범위](../SECURITY.md)도 확인하세요.

## 5. 관측 결과와 승인한 기준을 분리합니다

새로 실행할 때마다 기준 파일을 자동으로 바꾸면, 테스트가 찾아야 할 변화도 사라집니다. 후보 파일은 이번에 관측한 내용을, 기준 파일은 검토자가 받아들인 내용을 담습니다. 라이브러리는 후보를 쓰고 별도 기준과 비교합니다. 자동 승인 기능은 없으며, 후보 파일을 쓸 때 기준 파일과 같은 대상을 가리키는 경로도 거부합니다.

검증기는 호환성과 수집 결과의 통과 자격을 먼저 확인한 뒤, 허용량과 구조 차이를 검사합니다. 리포트를 생성하는 것만으로 빌드가 실패하지는 않습니다. `assertMatched`와 CLI는 일치하지 않는 모든 결과를 거부합니다. 별도 API인 `assertPassesBlockingChecks`는 검토만 필요한 `REVIEW_REQUIRED` 결과를 허용하므로, 이 정책이 필요할 때 명시적으로 선택해야 합니다. 차이가 의도한 것인지 SQL과 설정을 확인한 뒤 기준 변경을 결정하세요.

확인할 코드: [ManifestStore](../routecontract-shardingsphere-5.5/src/main/java/io/github/ym0506/routecontract/manifest/ManifestStore.java), [ManifestVerifier](../routecontract-shardingsphere-5.5/src/main/java/io/github/ym0506/routecontract/manifest/ManifestVerifier.java). [리포트 안내](ci-review-report.md)와 [첫 프로젝트](first-project.ko.md)에서 실제 검토 흐름을 따라갈 수 있습니다.

## 6. 도입을 결정할 때는 검증한 범위도 함께 봅니다

- [0.1.4 공개 설치 검증](evidence/release-0.1.4-central.md): 공개 배포 파일과 실제 Java·MySQL·빌드 도구 조합의 검사 기록입니다.
- [애플리케이션 실험](application-evaluations.ko.md): 작성자가 공개 프로젝트의 일부 코드로 실행한 범위와 실행하지 않은 범위를 구분합니다.
- [0.1.3 관측 비용 실험](observer-cost.md): 메모리 할당과 시간 측정 기록입니다. 반복 측정에서 시간 변화의 방향이 달라 일정한 성능 비용 비율을 주장하지 않습니다.
- [사용 경험과 피드백](user-feedback.md): 실험, 대화, 프로젝트 적용, 반복 사용을 구분합니다. 외부의 독립적인 반복 사용은 아직 확인되지 않았습니다.

기존 JDBC 리스너로 필요한 검사를 이미 하고 있다면 그 방법도 함께 비교하세요. 지원하는 ShardingSphere 환경에서 실행 변화가 반복해서 검증의 빈틈으로 남는다면, [기존 테스트 하나에 적용](first-project.ko.md#자신의-테스트와-ci로-옮기기)하고 예상 동작을 알고 있는 변경으로 결과를 판단해 보세요.
