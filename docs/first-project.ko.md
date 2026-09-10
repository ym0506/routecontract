# 기존 테스트 하나에 RouteContract 적용하기

[English](first-project.md) · [실행 가능한 예제](../examples/first-project/README.md) · [리포트 미리보기](evidence/ci-review-report-example.md)

Maven이나 Gradle로 실행할 수 있는 테스트 예제입니다. 쿼리를 바꿔도 원하는 주문은
반환되지만 데이터 소스를 한 곳 더 조회하는 상황을 만들고, RouteContract의 추가 검사가
실패하는 것을 확인합니다. DB 설정과 검토된 기준 파일이 예제에 들어 있습니다.

**Maven Central의 RouteContract 0.1.3**, **Java 17 또는 21**,
정확히 **ShardingSphere-JDBC 5.5.3**을 사용합니다. 지원 범위는 동기식·비배치
`PreparedStatement` 호출입니다.

브라우저에서 합성 예제를 체험하거나, Docker가 실행 중인 로컬 환경에서 따라 할 수 있습니다.
예제 코드는 저장소 main에 있고, 라이브러리는 Central에서 받습니다.

<a id="try-in-your-browser"></a>

## 브라우저에서 체험하기

GitHub 계정과 자신의 fork에서 Actions를 실행할 권한이 필요합니다. Java·Docker·빌드 도구는
GitHub가 제공하는 실행 환경에서 작동하므로 **컴퓨터에 따로 설치하지 않아도 됩니다.**

1. [RouteContract를 자신의 계정으로 fork](https://github.com/ym0506/routecontract/fork)합니다.
2. **자신의 fork**에서 **Actions**를 엽니다. 활성화 안내가 나오면 Actions를 활성화한 뒤
   workflow 목록에서 **First project**를 선택합니다.
3. **Run workflow**를 누르고 `main` 브랜치와 기본값 **Maven**으로 실행합니다.
   **Gradle**, **Both**도 선택할 수 있습니다. Java는 **17**(기본값), **21**, **Both** 중 선택합니다.
   예전에 만든 fork에 이 선택 항목이 없다면 먼저 main 브랜치를 동기화하세요.
4. 새 실행을 열고 완료 후 **Summary**에서 세 단계를 확인합니다.

   | 단계 | 정확히 검증하는 업무 행 | 관측 실행 시도 / 별칭 | 계약 결과 |
   | --- | --- | --- | --- |
   | 정상 조회 | 주문 201 / 사용자 3 / PAID | 1 / 1 | `MATCH` |
   | 같은 결과를 반환하는 범위 조회 | 동일한 행 | 2 / 2 | `POLICY_VIOLATION`: 실행 2회·데이터 소스 2개가 각각 상한 1을 초과 |
   | 정상 조회로 복구 | 동일한 행 | 1 / 1 | `MATCH` |

   **예상한 거부와 정상 복구를 모두 확인해야 체험 workflow가 성공합니다.** 범위 조회 테스트
   자체는 실패합니다. 의존성·컴파일·Docker 오류는 계약 거부로 인정하지 않으며, 확인하지
   못한 단계는 요약에 `Not verified`로 표시합니다.
5. 실행 화면의 **Artifacts**에서 **first-project-Maven** 또는 **first-project-Gradle**을
   내려받습니다. Java 21 결과에는 **-java21** 접미사가 붙습니다. `build/lifecycle-evidence/` 아래 `match/`, `range/`, `restored/`에 각 단계의
   `candidate.json`, `review.json`, `review.md`를 보관합니다. `range/review.md`부터 보세요.

workflow는 capture가 없는 기준 파일을 자동 승인하지 않는지도 확인합니다. 비교에는 예제의
기존 검토된 합성 기준을 사용하며 그 파일을 바꾸지 않습니다. 자신의 애플리케이션 기준을
승인하는 과정은 별도입니다. 체험 후 [자신의 테스트 하나에 적용](#자신의-테스트와-ci로-옮기기)하세요.

**Run workflow**가 보이지 않으면 자신의 fork인지, 기본 브랜치에 workflow가 있는지
확인하세요. [GitHub 수동 실행 안내](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)도 참고할 수 있습니다.

## 예제 실행

로컬 실행에는 Java 17 또는 21과 실행 중인 Docker가 필요합니다. 처음에는 의존성과 MySQL 이미지를
내려받으므로 시간이 더 걸릴 수 있습니다.

```bash
git clone https://github.com/ym0506/routecontract.git
cd routecontract/examples/first-project
```

아래에서 사용하는 빌드 도구 하나를 선택하세요.

| 빌드 도구 | 기본 비교 실행 |
| --- | --- |
| Maven 3.9.x | `mvn -B test` |
| Gradle wrapper | `../../gradlew -p . test --rerun-tasks` |

Maven은 `JAVA_HOME`으로 선택한 Java 17 또는 21로 예제를 컴파일하고 실행합니다.
Gradle 기본값은 Java 17입니다. 설치된 Java 21을 쓰려면 이 문서의 **모든** Gradle 명령에
`-ProutecontractJavaVersion=21`을 추가하거나, 셸 세션에 `ROUTECONTRACT_EXAMPLE_JAVA_VERSION=21`을
설정하세요. 테스트는 실제 JVM, 예제 클래스 버전, Central 배포 JAR이 맞는지도 확인합니다.
[런타임 검증과 한계](java21-runtime-acceptance.md)를 참고하세요.

기본 실행은 예제에 포함된 검토된 기준 파일과 비교합니다. 업무 결과 assertion과 계약 비교가
통과하고, `build/routecontract/review.md`와 `review.json`에 `MATCH`가 나와야 합니다.
Docker·컴파일·다운로드 오류는 실행 환경 문제이므로 계약 위반과 구분해서 확인하세요.

## 같은 업무 결과에서 실행 변화 확인

앞에서 통과한 실행과 같은 기준 파일을 사용합니다. 범위 조회로 바꾸면 주문 `201 / 3 / PAID`는
그대로 반환되지만, JDBC 실행 시도와 사용한 데이터 소스가 각각 하나에서 둘로 늘어납니다.
앞에서 선택한 빌드 도구로 실행하세요.

**Maven:**

```bash
mvn -B test -Droutecontract.query=range
```

**Gradle:**

```bash
../../gradlew -p . test --rerun-tasks -ProutecontractQuery=range
```

**이 명령은 실패해야 합니다.** 테스트는 주문 반환값을 확인하고 리포트를 쓴 뒤, 실행 검사를
실패시킵니다. `build/routecontract/review.md`를 열어 다음 내용을 확인하세요.

| 표시 | 뜻 | 이 예제의 수치 |
| --- | --- | --- |
| `POLICY_VIOLATION` | 관측한 횟수나 개수가 허용 상한을 넘었습니다. | 주문 반환값은 맞지만 테스트는 실패합니다. |
| `RCM201` | hook이 보고한 물리 JDBC 실행 시도가 너무 많습니다. | 기준은 최대 1회, 관측은 2회. |
| `RCM202` | 사용한 데이터 소스의 서로 다른 별칭이 너무 많습니다. | 기준은 최대 1개, 관측은 2개. |

**별칭(alias)**은 설정된 데이터 소스에 붙이는 민감하지 않은 이름입니다. 예제는 `ds_0`을
`orders-even`, `ds_1`을 `orders-odd`로 표시합니다. 예산(budget)은 허용 상한입니다.
이 수치가 물리 테이블 개수나 성능 저하를 뜻하지는 않습니다.

실패 리포트를 읽은 뒤 query 옵션 없이 원래 명령을 다시 실행하면 `MATCH`로 돌아옵니다.
생성된 리포트는 실행할 때마다 바뀌지만 예제의 기준 파일은 그대로 유지됩니다. 자기 프로젝트의
변경이라면 쿼리·샤딩 설정을 확인하고, 의도하지 않은 추가 실행은 수정합니다. 의도한 변경이면
새 기준을 검토합니다.

## 자신의 테스트와 CI로 옮기기

실행 횟수부터 검사하려면 Java 테스트 코드에 기대값을 적으면 됩니다. **JSON 기준 파일은 선택 사항입니다.**
[Central 테스트 의존성](../README.md#install-013)을 추가하고, 기존 ShardingSphere 설정을 유지한 채
동기식 repository/service 호출 한 개를 감쌉니다.

```java
var captured = RouteContract.captureResult("orders.find-paid", () -> orders.findPaidOrders("equality"));
assertEquals(expectedOrders, captured.value());
RouteAssertions.assertThat(captured.snapshot())
        .hasAtMostObservedPhysicalAttempts(1)
        .hasAtMostDistinctObservedDataSourceNames(1);
```

`RouteContract`와 `RouteAssertions`는 `io.github.ym0506.routecontract`에서, `assertEquals`는
JUnit에서 import합니다. `orders`와 `expectedOrders`는 기존 테스트의 조회 객체와 기대 반환값입니다.
호출과 허용 상한은 자기 테스트의 데이터·샤딩 설정을 보고 정하세요. 위의 최대 1은 이 합성 예제의
기준입니다. 수집이 불완전하거나 상한을 넘으면 일반 테스트와 CI 빌드가 실패합니다.

같은 예제에서 이 방식을 실행할 수 있습니다. 빌드 도구 하나를 선택하세요.

```bash
mvn -B test -Droutecontract.mode=assert
# 또는:
../../gradlew -p . test --rerun-tasks -ProutecontractMode=assert
```

Maven에는 `-Droutecontract.query=range`, Gradle에는 `-ProutecontractQuery=range`를 추가하면
같은 주문 반환을 확인한 뒤 `expected at most 1 observed physical attempts, but observed 2`로
실패합니다. 원래 명령을 다시 실행하면 통과합니다. 이 모드에서는 콘솔이나 JUnit 결과를 읽으세요.
JSON 기준·candidate·리포트를 읽거나 쓰지 않으므로, 기존 리포트 파일은 이전 실행의 결과입니다.
First project 워크플로도 이 방식의 통과 → 실패 → 원복을 검사합니다.

위 두 assertion은 횟수만 검사합니다. SQL fingerprint, 파라미터 타입 형태, 저장된 데이터 소스 집합을
비교하거나 리포트의 `RCM` 코드를 만들지는 않습니다. 그 비교와 Markdown/JSON 리포트가 필요하면
아래 기준 파일 절차를 사용하세요. Java 17 또는 21과 테스트 런타임의 정확한 ShardingSphere 5.5.3 조건은 같습니다.

## 첫 기준을 직접 검토하기

기본 check 모드 예제에는 **baseline**, 즉 예상 실행과 허용 상한을 검토해 저장한 JSON 파일이 있습니다.
**candidate**는 이번 실행에서 관측한 내용을 담은 파일입니다. 자기 테스트에서 JSON 비교를 선택했다면
candidate를 만들고 검토한 뒤 그 테스트의 기준으로 삼습니다. 아래에서는 새 경로로 이 과정을
연습합니다.

<details>
<summary>Maven</summary>

```bash
mvn -B test -Droutecontract.mode=capture \
  -Droutecontract.baseline=baselines/first-review.approved.json
```

</details>

<details>
<summary>Gradle</summary>

```bash
../../gradlew -p . test --rerun-tasks -ProutecontractMode=capture \
  -ProutecontractBaseline=baselines/first-review.approved.json
```

</details>

`build/routecontract/candidate.json`을 열고 업무 assertion, 실행 시도 수, 데이터 소스 별칭,
SQL fingerprint와 파라미터 타입 형태, 허용 예산을 테스트·설정과 함께 검토하세요.
예제에서는 실행 시도 1회와 관측 별칭 1개를 허용합니다. capture 성공은 기준 승인이나
CI 비교 성공을 뜻하지 않습니다.

이 합성 예제를 직접 검토한 뒤, 아직 없는 경로에 기준 파일을 만듭니다.

```bash
cp -n build/routecontract/candidate.json baselines/first-review.approved.json
```

`cp -n`은 이미 있는 기준 파일을 바꾸지 않습니다. 자신의 프로젝트에서는 담당자가 정상적인
코드 리뷰 과정으로 candidate를 검토하고 기준 파일을 테스트와 함께 커밋해야 합니다.
예제 기준 파일을 다른 업무의 기준으로 복사하지 마세요.

<details>
<summary>Maven</summary>

```bash
mvn -B test -Droutecontract.baseline=baselines/first-review.approved.json
```

</details>

<details>
<summary>Gradle</summary>

```bash
../../gradlew -p . test --rerun-tasks \
  -ProutecontractBaseline=baselines/first-review.approved.json
```

</details>

`MATCH`가 나와야 합니다. 기준 파일이 없으면 비교는 실패하며, candidate를 기준으로 자동
승인하지 않습니다.

### JSON 비교를 CI에 연결하기

1. 기존 호출과 반환값 검증을 유지합니다. 작업 ID, 데이터 소스의 민감하지 않은 별칭, 실행 예산을
   정합니다. candidate와 baseline 경로를 분리하고, 첫 candidate는 담당자가 직접 검토합니다.
2. 일반 테스트에서는 `ManifestReviewReport.compare`로 비교하고 리포트를 저장한 뒤
   `ManifestAssertions.assertMatched`를 호출합니다. CI는 검토한 기준을 사용하는 check
   모드로 실행합니다.

[영문 가이드의 CI 예제](first-project.md#keep-the-result-beside-ci)를 사용해 결과를 작업 요약에
표시할 수 있습니다. 테스트 실패를 그대로 유지하고, 각 실행의 새 결과를 아티팩트로 보관하세요.
기준 변경은 코드와 함께 검토합니다.

막힌 경우 [짧은 피드백 양식](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml)에
버전, 빌드 도구, 도달한 단계와 짧은 오류 코드를 남겨주세요. 비공개 SQL·바인딩 값·접속 정보·전체
로그는 자신의 환경에 보관하세요. 적용을 포기한 이유도 도움이 됩니다.

첫 적용을 마친 뒤에는 다음 실제 SQL·설정 변경에서도 사용해 보고 결과가 도움이 되었는지
알려주세요. 예제 실행, 자기 프로젝트 통합, 후속 변경에서의 재사용은 [구분해서 기록합니다](user-feedback.md#recording-use-and-evidence).
