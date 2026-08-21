# RouteContract for ShardingSphere

[한국어](README.md) | [English](README.en.md)

[![CI](https://github.com/ym0506/routecontract/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ym0506/routecontract/actions/workflows/ci.yml?query=branch%3Amain)

> CI contracts for ShardingSphere-JDBC 5.5.3 `SQLExecutionHook`-reported physical JDBC execution attempts

RouteContract는 Apache ShardingSphere-JDBC 애플리케이션에서 하나의 application operation 동안 `SQLExecutionHook`으로 **관측된 물리 JDBC 실행 시도**를 결정적인 manifest로 만들고, SQL·설정 변경으로 생긴 관측 실행 확장과 실행 구조 변화를 CI에서 차단하는 Java 테스트 라이브러리입니다.

비즈니스 결과만 검사하면 같은 행을 정상 반환하면서도 hook이 보고한 관측 실행 시도가 `1 → 2` 또는 `1 → 8`로 늘어난 변경을 놓칠 수 있습니다. RouteContract는 operation별 실행 예산, 관측 data-source 이름, rewritten-SQL fingerprint의 구조적 diff를 별도의 회귀 계약으로 검증합니다.

코드 지도:

- 제품 라이브러리: `routecontract-shardingsphere-5.5/src/main`
- 재현·검증 예제와 제품 테스트: `examples/`, `routecontract-shardingsphere-5.5/src/test`
- 데모·설치·릴리스·증거 검증 자동화: `scripts/` — 제품 runtime API가 아님
- 대회 보고서·패키징 전용 도구: `submission/` — 제품 runtime API가 아님

이 소스의 project version은 prerelease candidate `0.1.0-rc1`이며 대응 tag 이름은
`v0.1.0-rc1`입니다. 버전 문자열이나 checkout만으로 annotated tag, 공개·불변 prerelease,
동일 revision의 release-evidence run 또는 외부 사용자 결과를 증명하지는 않습니다. 공개 RC로
사용하기 전에는 [독립 설치 연구의 activation gate](docs/independent-install-study.md#activation-gate--do-not-recruit-early)를
통과한 고정 activation record를 검증해야 합니다.

아래 50개 정상 테스트와 같은 checkout의 격리 소비자 테스트 1개는 [이전 공개 main revision
`54f1c92`의 CI](https://github.com/ym0506/routecontract/actions/runs/31501026857)에서
실패·오류·skip 0건으로 확인됐습니다. 이 과거 run은 RC1 revision이나 Release 자산을 검증하지
않으며, 격리 소비자 결과도 외부 채택 증거가 아닙니다. 자세한 환경·원시 artifact·한계는
[공개 CI 증거 기록](docs/public-ci-evidence.md)에 있습니다. 이는 수상·운영환경 지원·일반적
성능을 뜻하지 않습니다.

## Quick Start

필수 조건은 Java 17, 실행 중인 Docker daemon, Bash/POSIX 도구와 실행 가능한 Gradle
Wrapper입니다. 최초 실행은 Gradle·Maven Central 의존성과 로컬에 없는 digest-pinned MySQL
container image를 내려받기 위한 네트워크가 필요할 수 있습니다.

```bash
./scripts/quickstart-demo.sh
```

이 명령은 실제 MySQL에서 business result가 그대로인 `1 → 2` 관측 실행 회귀를 검증한 뒤,
같은 candidate를 CI gate에 넣어 `RCM201`·`RCM202` 거부를 확인합니다. 마지막에
`[ROUTECONTRACT QUICKSTART VERIFIED]`, `realMysqlDemoExit 0`,
`intentionalCiGateExit 1`, `quickstartExit 0`이 출력되면 예상한 전체 흐름이 통과한 것입니다.
내부 CI gate의 종료 코드 `1`은 의도한 계약 거부이고, quickstart 자체의 `0`은 그 거부까지
정확히 검증했다는 뜻입니다. preflight나 검증이 실패하면 quickstart는 `2`로 종료하며, 원문
SQL·parameter·connection 정보가 섞일 수 있는 하위 프로세스 원문은 화면에 다시 출력하지 않습니다.

activation gate를 통과한 RC1 Release 자산 또는 같은 checkout에서 생성한 Maven publication을
ShardingSphere-JDBC 5.5.3 소비자 테스트에 추가할 때는 Jackson 2 호환성 모듈을 먼저 정렬한
뒤 다음 exact coordinate를 선언합니다. RC1은 Maven Central 게시를 주장하지 않습니다.

```groovy
testImplementation(platform("com.fasterxml.jackson:jackson-bom:2.18.9"))
testImplementation("io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.0-rc1")
```

RouteContract는 의존성을 내장하지 않는 thin JAR이고, 모듈의 `compileOnly`
ShardingSphere/BOM 선언은 공개 POM에서 소비자 버전 제약으로 전달되지 않습니다. 검증된
Gradle test/runtime graph에서는 위 BOM에 따라 ShardingSphere 5.5.3 호환성 그래프의
Jackson 2 core·databind·datatype-jdk8·datatype-jsr310 모듈이 2.18.9로 해석됩니다. 단, Jackson
3.1.5도 함께 있는 runtime에서는 두 계열이 공유하는
`jackson-annotations`가 Jackson 3 BOM에 따라 2.21로 해석됩니다. 이 설정은 RouteContract가
직접 사용하는 별도 `tools.jackson.core:jackson-core:3.1.5` 제품 런타임을 대체하거나
낮추지 않습니다.

## 검증된 핵심 시나리오

| 시나리오 | 실제 검증 결과 |
|---|---|
| 동일 값 `=` → `BETWEEN` | 비즈니스 행은 같고, 관측 시도 `1 → 2`, data source `[ds_1] → [ds_0, ds_1]` |
| 공개 이슈 #38456에서 영감을 받아 축소·수정한 fixture | JOIN과 subquery의 결과는 모두 `COUNT=1`, 관측 시도는 각각 `1`과 `8`; 원 이슈의 충실한 재현 주장은 아님 |
| 설정 회귀 | table strategy 제거 시 실행 수와 data source는 같지만 SQL fingerprint drift 검출 |
| 결정성 | corpus 8개를 각 20회 실행한 160 captures에서 case별 구조 signature 1개 |
| 동시에 열린 caller-operation scope | single-attempt/multi-attempt scope 20쌍에서 교차 귀속 0건; 물리 callback의 시간상 중첩은 강제하거나 측정하지 않음 |
| 범용 JDBC 도구 비교 | datasource-proxy 외부 배치는 callback `1 → 1`, 물리 DS별 배치는 `1 → 2`, RouteContract도 `1 → 2` |
| 격리된 소비자 빌드 | 같은 checkout에서 임시 Maven 저장소에 생성한 JAR와 POM만 사용하는 standalone consumer에서 SPI 자동 발견과 MySQL 실행 통과. 외부 채택 증거는 아님 |

전체 50-test 검증:

```bash
./gradlew --no-daemon --no-build-cache clean check assemble prepareVerifiedSbom
./scripts/verify-standalone-consumer.sh
```

첫 명령은 Java 17, ShardingSphere-JDBC 5.5.3, digest로 고정한 MySQL 8.4.11 Testcontainers 환경에서 core 및 MySQL corpus 50개 테스트를 실행하고 JAR·Javadoc·SBOM을 생성합니다. 두 번째 명령은 별도 소비자 테스트 1개를 실행합니다. Docker가 필요합니다.

## 공개 Release 자산을 registry 없이 사용하기

이 경로는 고정 activation record가 가리키는 annotated `v0.1.0-rc1` tag, 공개·불변
prerelease, 동일 revision의 성공한 release-evidence run과 정확한 자산 집합이 모두 존재한
뒤 사용할 수 있습니다. 해당 Release에 첨부된
공개 자산 전체를 하나의 평평한 디렉터리에 내려받은 다음, `~/.m2`가 아닌 빈 절대경로를
명시합니다.

```bash
python3 scripts/install-release-assets.py \
  --release-assets-dir /absolute/path/to/downloaded-release-assets \
  --repository /absolute/path/to/routecontract-maven
```

설치기가 출력한 exact RC1 좌표를 위 Quick Start의 Jackson 2 BOM 다음에 테스트 의존성으로
사용합니다. thin POM이 소비자의 ShardingSphere/Jackson 버전을 정렬해 주지는 않습니다.

```groovy
testImplementation("io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.0-rc1")
```

설치기는 네트워크를 사용하지 않습니다. 공개 자산의 정확한 파일 목록, `SHA256SUMS`,
sanitized supply-chain evidence와 공개 SBOM/POM의 hash 결합, non-SNAPSHOT POM 좌표,
JAR 구조, source ZIP의 단일 버전 root, `LICENSE`·`NOTICE`와 관례적인 `src/main/java`·
`src/test/java` 아래 모든 Java 파일의 경로-패키지 일치,
canonical `ym0506` provider namespace를
먼저 검증한 후 main/sources/Javadoc JAR와 POM만 명시한 Maven
레이아웃에 복사합니다. 기존 좌표는 덮어쓰지 않으며 관례적인 `~/.m2/repository`와 그 하위 경로를
target으로 지정하면 거부합니다. 체크섬은 다운로드 무결성을 확인할 뿐 게시자 신원을 인증하지 않으므로, 자산은
반드시 해당 tag의 공개 Release에서 받아야 합니다. 설치기의 source ZIP 검사는 구조·필수 경로·
Java package/provider namespace 검사이며, release archive가 최종 tag의 tracked Git tree와
내용·경로·실행 권한이 동일하다는
증명은 최종 제출 packaging gate가 별도로 수행합니다.

같은 source checkout에서 그 저장소만 RouteContract 전용 repository로 사용해 실제 MySQL
소비자까지 검증하려면 별도의 빈 target으로 다음을 실행합니다. 이 검증은 release packaging
증거이지 외부 사용자의 채택 증거는 아닙니다.

```bash
./scripts/verify-release-assets-consumer.sh \
  /absolute/path/to/downloaded-release-assets \
  /absolute/path/to/empty-verification-maven
```

가장 짧은 business-green / contract-red 데모만 실행하려면 다음 한 명령을 사용합니다.

```bash
./scripts/run-demo.sh
```

동일한 비즈니스 결과에서 equality를 같은 값의 range로 바꿨을 때 관측 시도가 `1 → 2`,
data source가 `1 → 2`로 늘고 strict manifest가 `RCM201`·`RCM202`로 CI 실패하는 실제
MySQL 시나리오를 실행합니다. 이 명령은 예상된 위반을 검증하는 테스트이므로 성공 종료합니다.

검증된 manifest 두 파일만 읽어 실제 CI gate의 비정상 종료를 재현하려면 다음 명령을
사용합니다. Docker 없이 `RCM201`·`RCM202`를 출력하고 의도적으로 종료 코드 `1`을 반환하며,
전용 fixture라서 일반 `test`와 `check`에는 포함되지 않습니다.

```bash
./scripts/demo-manifest-ci-failure.sh
```

실제 MySQL에서 canonical 파일을 재생성·대조한 다음 같은 승인본으로 build가 실패하는 전체
흐름을 한 명령에서 보려면 아래 스크립트를 사용합니다. 앞 단계가 모두 정상이어도 마지막
계약 assertion 때문에 의도적으로 종료 코드 `1`을 반환합니다.

```bash
./scripts/demo-end-to-end-ci-failure.sh
```

## 가장 작은 사용 예

```java
RouteSnapshot snapshot = RouteContract.capture("orders.find-by-user-id", () -> {
    Order actual = orderRepository.findByUserId(3L);
    assertEquals(201L, actual.id()); // 기존 기능 assertion도 그대로 둡니다.
});

RouteAssertions.assertThat(snapshot)
        .hasCompleteCapture()
        .hasNoReportedExecutionFailures()
        .hasExactlyObservedPhysicalAttempts(1)
        .observesExactlyDataSourceNames("ds_1");
```

`finishSuccess()`라는 ShardingSphere SPI 메서드명은 transaction commit이나 비즈니스 성공을 뜻하지 않습니다. RouteContract의 `CALLBACK_RETURNED`는 ShardingSphere 5.5.3이 물리 `executeSQL` 반환 뒤 해당 hook provider에 `finishSuccess`를 보고했다는 뜻으로만 사용합니다. 둘러싼 JDBC operation·transaction·application action의 완료도 증명하지 않습니다.

## 승인 manifest와 CI diff

```java
DataSourceAliases aliases = DataSourceAliases.of(Map.of(
        "ds_0", "orders-a",
        "ds_1", "orders-b"));
ManifestPolicy policy = ManifestPolicy.strict(1, 1);

ObservedExecutionManifest candidate = ObservedExecutionManifest.from(
        snapshot, aliases, policy);

Path approvedPath = Path.of("route-contracts/orders.find-by-user-id.json");
Path candidatePath = Path.of("build/routecontract/orders.find-by-user-id.candidate.json");
new ManifestStore().writeCandidate(approvedPath, candidatePath, candidate);

ObservedExecutionManifest approved = new ManifestStore().read(approvedPath);
ManifestVerificationResult result = new ManifestVerifier().verify(approved, snapshot, aliases);
ManifestAssertions.assertMatched(result); // mismatch이면 stable RCM code와 함께 CI 실패
```

candidate 기록은 approved 파일을 자동으로 덮어쓰지 않습니다. 변경이 의도된 경우 사람이 diff를 검토한 뒤 명시적으로 승인본을 교체해야 합니다.

실제 MySQL equality 기준과 같은 결과를 반환하는 `BETWEEN` candidate의 canonical JSON 및
검증기 출력은 [examples/manifests](examples/manifests/README.md)에 있습니다. 통합 테스트가
매번 이 파일들을 다시 생성해 byte-for-byte 일치와 stable diff를 확인합니다.

data-source alias mapping 역시 승인 계약의 일부인 신뢰 설정입니다. manifest에는 호출자가 제공한 alias가 저장되므로, alias에는 비민감한 고정 이름만 사용해야 합니다. 실제 data-source 이름을 alias로 그대로 재사용하면 그 이름이 노출되고, 다른 실제 data source를 기존 alias로 조용히 재매핑하면 drift를 숨길 수 있습니다. mapping은 manifest와 함께 version control에서 검토해야 합니다.

- `ManifestPolicy.strict(...)`: fingerprint를 포함한 구조 signature 변화도 차단합니다.
- `ManifestPolicy.budgetOnly(...)`: 시도 수·data-source·callback outcome 변화는 차단하고, signature-only 변화는 `REVIEW_REQUIRED`로 남깁니다.
- canonical JSON에는 timestamp, UUID, thread 배치, 원문 SQL, parameter 값, exception message가 들어가지 않습니다. data source는 호출자가 제공한 alias로만 기록되며, 그 alias의 비민감성은 호출자의 책임입니다.

같은 행, 관측 시도 `1`, 같은 data source를 보존하면서 추가 filter와 predicate 순서를 바꾼
MySQL fixture에서는 fingerprint와 parameter type 순서만 달라졌습니다. 이는 그 fixture의
관측 결과일 뿐 두 SQL의 일반적인 의미 동치를 주장하지 않습니다.

| 정책 | 이 signature-only 변화의 결과 | 선택 시 tradeoff |
|---|---|---|
| `strict` | `DRIFT`, `RCM301`·`RCM302` blocking, assertion 실패 | 작은 rewritten-SQL 구조 변화도 검토·승인하게 하지만, 의도적 변화도 baseline 갱신 전까지 CI를 막음 |
| `budgetOnly` | `REVIEW_REQUIRED`, `RCM301`·`RCM302` non-blocking, `passesBlockingChecks=true` | 예산·data-source·callback outcome은 계속 막지만 signature-only 변화는 CI를 통과시키므로 수동 검토를 놓치면 구조 회귀를 허용할 수 있음 |

## 기존 도구와의 정확한 차이

RouteContract는 ShardingSphere의 관측 기능이나 일반 JDBC 도구가 “못 한다”고 주장하지 않습니다.

- ShardingSphere-Proxy의 `PREVIEW SQL`, 그리고 ShardingSphere의 `sql-show`·Agent는 계획·로그·운영 telemetry를 제공합니다.
- ShardingSphere Audit는 built-in 알고리즘 기준으로 인식 가능한 sharding condition의 존재를 검사합니다.
- Sniffy와 datasource-proxy는 SQL 수 검증 또는 사용자 정의 JDBC 수집을 제공합니다.
- RouteContract가 추가하는 것은 **caller가 정한 application-operation 경계**, ShardingSphere worker까지의 상관관계, 최소정보 canonical manifest, 승인 workflow, stable structural manifest diff, CI assertion, 실제 회귀 corpus입니다.

근거와 한계까지 포함한 비교는 [competitive-analysis.md](docs/competitive-analysis.md)에 있습니다.

## 정확한 증거 경계

관측하는 항목:

- hook이 보고한 data-source 이름
- hook이 보고한 rewritten SQL 원문의 SHA-256 fingerprint
- parameter 개수와 Java type 이름
- trunk/worker flag
- start, callback return, callback failure, terminal callback 미확인 상태

관측하거나 증명하지 않는 항목:

- 전체 route plan 또는 `RouteContext`
- 계획된 execution unit 전체와 모든 target shard
- 정확한 물리 table 수
- 자동 `FULL_ROUTE`/`BROADCAST` 판정
- transaction commit 또는 비즈니스 성공

## v0.1 지원 범위

- Java 17
- Apache ShardingSphere-JDBC **정확히 5.5.3**
- 정상 반환하고 capture 종료 시 caller가 interrupt되지 않은 동기식 `PreparedStatement`
- MySQL 8.4.11 기반 통합 검증
- 서로 다른 caller thread의 동시 operation 및 테스트 fixture의 multi-attempt worker callback

지원 범위 밖:

- ShardingSphere-Proxy
- JDBC batch와 reactive 실행
- 애플리케이션 자체 `@Async` 경계
- SQL Federation의 모든 실행 경로
- 다른 ShardingSphere 버전
- 정상적인 zero-SQL operation 검증
- callback failure 또는 caller interruption이 발생한 operation의 route 계약 승인

preflight는 classpath의 `shardingsphere-infra-executor`와 `shardingsphere-infra-spi`가 구현 버전 `5.5.3`을 보고하는지, service loader가 RouteContract provider를 정확히 1개 찾는지만 확인합니다. ShardingSphere runtime 전체 artifact 집합의 버전 일치를 증명하지 않습니다. 이 조건이 충족되지 않거나 capture 안에서 start callback이 관측되지 않으면 통과시키지 않습니다. Proxy·batch·reactive 등 범위 밖 실행 경로 전체를 자동 식별하거나 명시적으로 거부한다고 주장하지 않습니다.
실패한 병렬 실행에서는 ShardingSphere 5.5.3이 이미 제출한 worker를 전부 기다리지 않을
수 있으므로, `REPORTED_EXECUTION_FAILURE` snapshot은 진단에만 사용하고 route budget이나
manifest match를 통과시키지 않습니다.

한 capture에는 최대 10,000개의 물리 실행 시도만 보존합니다. 이를 넘으면 메모리를 계속
늘리는 대신 `RC_ATTEMPT_LIMIT_EXCEEDED` 진단과 함께 `INCOMPLETE`로 실패합니다.

## 정보 최소화와 보안

원문 SQL, parameter 값, connection properties, exception message는 snapshot/manifest에 저장하지 않습니다. 다만 data-source 이름, operation ID, Java type 이름과 unsalted SQL fingerprint도 민감한 engineering metadata가 될 수 있습니다. SHA-256 fingerprint는 익명화가 아니므로, v0.1은 기밀 literal을 inline하지 않는 결정적 `PreparedStatement` 테스트를 전제로 합니다. 자세한 내용은 [SECURITY.md](SECURITY.md)를 확인하십시오.

## 문서와 재현 경로

- [기술 명세](docs/specification.md)
- [아키텍처와 신뢰 경계](docs/architecture.md)
- [경쟁 도구 분석](docs/competitive-analysis.md)
- [datasource-proxy 실증 비교](docs/empirical-comparison.md)
- [대회 증거 매트릭스](docs/evidence-matrix.md)
- [8월 27일까지 개발 계획](docs/development-plan.md)
- [격리된 same-checkout Maven-publication consumer](examples/standalone-consumer/README.md)
- [SBOM 생성과 검토](docs/sbom.md)
- [출품 전 작업과 ShardLens 경계](ORIGIN_AND_PRIOR_WORK.md)
- [AI 보조 사용 공개](AI_ASSISTANCE.md)
- [기여 가이드](CONTRIBUTING.md)

## 프로젝트 기원

문제의식은 개인 포트폴리오 프로젝트 ShardLens의 미구현 `Route Guard` 설계에서 시작했습니다. ShardLens 애플리케이션 코드를 옮긴 것이 아니라, 그 설계 문제를 독립 설치 가능한 범용 테스트 도구·manifest·diff·MySQL corpus로 새로 구현하고 있습니다. 기존 설계와 신규 구현의 경계는 [ORIGIN_AND_PRIOR_WORK.md](ORIGIN_AND_PRIOR_WORK.md)에 공개합니다.

## 상표와 라이선스

RouteContract is an independent project and is not affiliated with or endorsed by the Apache Software Foundation. Apache ShardingSphere and Apache are trademarks of the Apache Software Foundation.

RouteContract는 [Apache License 2.0](LICENSE)으로 배포합니다. 직접·테스트 의존성과 배포 포함 여부는 [THIRD_PARTY.md](THIRD_PARTY.md)를 참고하십시오.
