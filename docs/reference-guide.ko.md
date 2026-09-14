# RouteContract 상세 가이드

상세 재현 절차와 호환성 참고 문서입니다. 현재 설치와 짧은 예제는 [한국어 README](../README.ko.md)에서 시작하세요.

[한국어 README](../README.ko.md) · [English guide](reference-guide.md) · [문서 찾기](start-here.md) · [로드맵](product-roadmap.md)

[![CI](https://github.com/ym0506/routecontract/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ym0506/routecontract/actions/workflows/ci.yml?query=branch%3Amain)

**같은 결과를 반환해도 DB 실행은 달라질 수 있습니다.**

RouteContract는 [ShardingSphere-JDBC](https://github.com/apache/shardingsphere)의
`SQLExecutionHook`이 보고한 물리 JDBC 실행 시도를 사람이 검토한 기대값으로 검사하는 Java 테스트
라이브러리입니다. 기존 반환값 검사를 유지하면서 실행 시도 수와 관측된 데이터 소스를 검사합니다.
구조 비교와 리포트가 필요하면 실행 명세를 JSON으로 저장해 비교할 수도 있습니다.

포함된 MySQL 예제는 같은 행을 반환하면서 관측된 실행 시도가 `1 → 2`로 늘어나는 변경을
`RCM201`·`RCM202`로 거부합니다. 실행 증가가 의도한 변경인지는 담당자가 검토합니다.

**지원:** Java 17 또는 21 · 정확히 ShardingSphere-JDBC 5.5.3 · 동기식·비배치 `PreparedStatement`.
[실행 경계와 한계](../docs/start-here.md#도입-전에-확인할-세-가지--check-fit)를 먼저 확인하세요.

## 시작하기

| 하고 싶은 일 | 시작점 |
| --- | --- |
| 설치 없이 검사 결과 이해하기 | [CI 리포트 읽기](evidence/ci-review-report-example.md) |
| 공개 라이브러리로 통과 → 실패 → 통과 확인 | [0.1.4 첫 프로젝트](first-project.ko.md) — Java 17 또는 21, Maven/Gradle, Docker |
| 로컬 Java·Docker 없이 실행 | [내 GitHub fork에서 실행](first-project.ko.md#try-in-your-browser) |
| 기존 테스트 한 개에 적용 | [Central 의존성](#install-014)을 추가하고 [작업 한 개 감싸기](first-project.ko.md#자신의-테스트와-ci로-옮기기); JSON 기준 파일은 선택 사항 |
| 적용 가능성 질문·경험 공유 | [짧은 피드백](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml) — 설치나 공개 저장소 없이 참여 가능 |

현재 공개 버전은 **0.1.4**입니다. 첫 프로젝트 가이드는 Maven Central의 이 버전을 사용하며,
Java 검증 API와 선택적인 Markdown·JSON 비교 리포트를 안내합니다.
예전 0.1.2 명령은 과거 결과 재현을 위해 아래 접힌 항목에 보존했습니다.
공개 피드백에는 SQL·바인딩 값·접속 정보·전체 로그를 넣지 마세요.
[도움받는 방법과 사용 사례 기록 기준](user-feedback.md)을 확인할 수 있습니다.

![같은 주문을 반환하지만 관측된 실행 시도와 데이터 소스가 하나에서 둘로 늘어난 사례.](assets/execution-comparison.svg)

<a id="install-013"></a>
<a id="install-014"></a>

## 설치

[공개 파일 검증과 Gradle·Maven 설치 결과](../docs/evidence/release-0.1.4-central.md)와
현재 [Java 17/21 런타임 검증](java21-runtime-acceptance.md)을 확인할 수 있습니다.

기존 **Java 17 또는 21 · ShardingSphere-JDBC 5.5.3** 테스트에 의존성을 추가하세요.
기존 ShardingSphere·데이터 소스 설정과 업무 결과 검사는 유지합니다.

Gradle Groovy / Kotlin DSL:

```kotlin
repositories { mavenCentral() }

dependencies {
    testImplementation("io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.4")
}
```

Maven (`pom.xml`의 `<dependencies>` 안에 추가):

```xml
<dependency>
  <groupId>io.github.ym0506.routecontract</groupId>
  <artifactId>routecontract-shardingsphere-5.5</artifactId>
  <version>0.1.4</version>
  <scope>test</scope>
</dependency>
```

동기식·비배치 `PreparedStatement` 작업 하나를 감싸는 [아래 사용 예](#가장-작은-사용-예)를 참고하세요.
RouteContract가 ShardingSphere를 설치하거나 전체 모듈의 버전을 강제하지는 않습니다.
테스트 실행에 쓰이는 ShardingSphere 모듈은 모두 정확히 5.5.3이어야 합니다.

0.1.4 의존성 설치에 예전 로컬 설치기를 실행하거나 저장소를 복제할 필요는 없습니다.
현재 Maven·Gradle 예제는 [첫 프로젝트 가이드](first-project.ko.md)를 사용하세요.

<a id="013-실행하기"></a>

## 0.1.4 실행하기

Java 17 또는 21, Maven 3.9.x와 실행 중인 Docker가 필요합니다. 처음에는 의존성과 MySQL 이미지를
내려받습니다. 새로 복제한 소스에서 실행하세요.

```bash
git clone https://github.com/ym0506/routecontract.git
cd routecontract/examples/first-project
mvn -B test
```

정확한 업무 결과 검사와 `build/routecontract/review.md`의 `MATCH`를 확인합니다.
이어서 같은 주문을 반환하는 범위 조회를 실행하세요.

```bash
mvn -B test -Droutecontract.query=range
```

이 명령은 업무 결과 검사가 통과한 뒤 `POLICY_VIOLATION`·`RCM201`·`RCM202`로 실패해야 합니다.
의존성·컴파일·Docker 오류는 이 거부를 재현한 결과가 아닙니다.
`mvn -B test`를 다시 실행하면 `MATCH`로 돌아옵니다. 포함된 기준 파일은 이 합성 데이터 예제에만
검토된 것입니다. Gradle, Java 21 선택, Java 코드에서 직접 검사하는 방법과 내 기준 파일 검토는
[전체 가이드](first-project.ko.md)를 참고하세요.

<details>
<summary>과거 0.1.2 예제와 격리 통합 도구</summary>

아래 명령은 원래 버전과 검증 범위를 유지합니다. 현재 설치의 선행 단계가 아닙니다.
[과거 2분 54초 시연](https://www.youtube.com/watch?v=pcgvNNxd1mM)도 이때의 절차를 다룹니다.

<a id="quick-start"></a>

## 과거 예제 실행

이 MySQL 시연은 `v0.1.2`에 고정되어 있습니다. 최신 리포트 기능을 먼저 보려면
[Docker 없는 v0.1.3 체험](../docs/ci-review-report.md#try-the-released-report-without-docker)을 사용하세요.

Git, Java 17, 실행 중인 Docker 데몬, Bash/POSIX 도구와 실행 가능한 Gradle Wrapper가
필요합니다. 처음 실행할 때는 공개 태그, Gradle·Maven Central 의존성, 로컬에 없는
MySQL 컨테이너 이미지를 내려받을 네트워크가 필요할 수 있습니다. MySQL 이미지는
다이제스트로 고정합니다.

```bash
(
set -euo pipefail
source_dir="routecontract-v0.1.2"
test ! -e "${source_dir}"
test ! -L "${source_dir}"
git clone --quiet --depth 1 --branch v0.1.2 --single-branch \
  https://github.com/ym0506/routecontract.git "${source_dir}"
test "$(git -C "${source_dir}" cat-file -t refs/tags/v0.1.2)" = tag
test "$(git -C "${source_dir}" rev-parse refs/tags/v0.1.2)" = 6adacbe04d60b3af83d9067a14a878d26a6c90f5
test "$(git -C "${source_dir}" rev-parse 'refs/tags/v0.1.2^{}')" = fc4fdd16c21574afa1150654ce354cf8004b138b
test "$(git -C "${source_dir}" rev-parse HEAD)" = fc4fdd16c21574afa1150654ce354cf8004b138b
test -z "$(git -C "${source_dir}" status --short)"
cd "${source_dir}"
./scripts/quickstart-demo.sh
)
```

이 명령은 실제 MySQL에서 반환값은 같고 관측 실행 시도가 `1 → 2`로 늘어나는 회귀를
검증합니다. 같은 실행 결과를 CI 검사에 넣어 `RCM201`·`RCM202`로 실패하는지도 확인합니다. 마지막에
`[ROUTECONTRACT QUICKSTART VERIFIED]`, `realMysqlDemoExit 0`,
`intentionalCiGateExit 1`, `quickstartExit 0`이 출력되면 예상한 전체 흐름이 통과한 것입니다.

<details>
<summary>정확한 종료 코드와 출력 경계</summary>

내부 CI 검사의 종료 코드 `1`은 의도한 계약 위반입니다. 시작 스크립트의 종료 코드 `0`은
그 실패까지 예상대로 확인했다는 뜻입니다. 사전 검사나 검증이 실패하면 스크립트는 `2`로
종료합니다. 하위 프로세스 출력에는 원문 SQL·파라미터·접속 정보가 섞일 수 있어 화면에
다시 출력하지 않습니다.

</details>

<details>
<summary>v0.1.2 통합 경로: Gradle·Maven 상세 절차</summary>

## 다음 단계: 첫 통합 가능성 검토하기

예제가 통과했다면 [첫 실제 통합 가이드](../docs/first-integration.md)의 지원 범위와 중단
조건을 확인하고, 기존 ShardingSphere-JDBC 5.5.3 통합 테스트에서 대표 작업 하나를
고르세요. 반환값 검사를 유지한 채 실행을 수집하고, 담당자가 검토한 기준 파일과 이후
실행 결과를 비교합니다. Gradle Groovy·Gradle Kotlin DSL 또는 Maven 3.9.14에 맞춘 격리
절차를 제공하지만, 저장소별 빌드 설정과 사람의 검토가 필요하므로 소요 시간을 정해 두지는
않습니다. `v0.1.2`는 Maven Central에 게시되지 않았으므로 검증한 GitHub 릴리스 파일을
별도의 로컬 Maven 저장소에 설치합니다.

Maven 사용자는 [검토용 시작 도구](../examples/maven-pilot/README.md#review-only-starter-bundle)를
먼저 사용하세요. 기존 테스트·작업·실행 예산·별칭을 지정하면 검토할 패치와 다음 명령을
만듭니다. 대상 저장소를 바꾸거나 기준 파일을 승인하지는 않습니다. 실행기가 필요한 Maven과
정확한 릴리스 파일을 설치하므로 미리 별도 설치를 할 필요는 없습니다.

Gradle을 사용하거나 설치를 별도로 검증하려면 아래 명령을 사용하세요. `install_root`에는
신뢰할 수 있는 기존 상위 디렉터리 아래의 새 디렉터리를 지정합니다. 경로는 정규화된 절대
경로여야 하며, 그 아래 `maven` 경로가 `~/.m2/repository`나 그 하위가 되면 안 됩니다.
공개 HTTPS 네트워크, Bash와 POSIX 도구, `curl`, Python 3.10 이상이 필요합니다. GitHub
로그인·토큰·API·GitHub CLI는 필요하지 않습니다.

```bash
(
set -euo pipefail
install_root="/absolute/path/to/new-routecontract-v0.1.2-install"
helper_url="https://raw.githubusercontent.com/ym0506/routecontract/a11c5ca1df41e4a0d25d6e211dd2274e35d5b593/scripts/install-public-v0_1_2.py"
expected_helper_size="33309"
expected_helper_sha256="bec71208b138765bbc017589cb04ef0159e015364616e14dc19c633873b9ecb8"

python3 -I -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 2)'
test ! -e "${install_root}"
test ! -L "${install_root}"
mkdir -m 700 "${install_root}"
helper="${install_root}/install-public-v0_1_2.py"
repository_dir="${install_root}/maven"
curl --disable --proto '=https' --proto-redir '=https' --tlsv1.2 \
  --fail --silent --show-error --retry 3 --connect-timeout 15 --max-time 120 \
  --max-redirs 0 --max-filesize "${expected_helper_size}" \
  --output - "${helper_url}" | \
  python3 -I -c '
import os
import sys

destination = sys.argv[1]
expected_size = int(sys.argv[2])
payload = sys.stdin.buffer.read(expected_size + 1)
if len(payload) != expected_size:
    raise SystemExit(
        f"wrapper byte count mismatch: expected {expected_size}, got {len(payload)}"
    )
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
descriptor = os.open(destination, flags, 0o600)
try:
    os.fchmod(descriptor, 0o600)
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("wrapper write made no progress")
        view = view[written:]
    os.fsync(descriptor)
finally:
    os.close(descriptor)
' "${helper}" "${expected_helper_size}"
test -f "${helper}"
test ! -L "${helper}"
actual_helper_size="$(python3 -I -c \
  'import pathlib,sys; print(pathlib.Path(sys.argv[1]).stat().st_size)' "${helper}")"
test "${actual_helper_size}" = "${expected_helper_size}"
actual_helper_sha256="$(python3 -I -c \
  'import hashlib,pathlib,sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' \
  "${helper}")"
test "${actual_helper_sha256}" = "${expected_helper_sha256}"
python3 -I "${helper}" --repository "${repository_dir}"
)
```

성공하면 정확히 `io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.2`
좌표에 배포 파일 4개와 SHA-1·SHA-256 체크섬 파일 8개가 생깁니다. 커밋에 고정한 공개
실행기는 불변 릴리스 파일을 바꾸지 않습니다. 태그 생성 후 추가한 체크섬 도구를 고정
해시로 검증해 호출합니다. 검토 유효기간인 `2026-12-05 UTC`도 그대로 적용됩니다.

어느 단계에서든 실패하면 `install_root` 전체를 조사용으로 보존하고, 수정하거나 재사용하지
말고 다른 새 절대 경로에서 시작하세요. 경로 연결 변경(`path-binding change`)이 보고되면
원래 경로가 설치용으로 확보한 디렉터리를 더 이상 가리키지 않을 수 있습니다. 원래 경로나
이동된 디렉터리 어느 쪽도 수정·삭제·재사용하지 마세요.

불변 `v0.1.2` 릴리스 본문과 해당 태그의 README는 아직 `v0.1.0` 설치 절차를 가리킵니다.
지금 읽는 `main` 문서와 가이드는 릴리스 후에 `v0.1.2` 설치를 돕도록 추가한 자료입니다.
따라서 `v0.1.2` 릴리스 자체에 완결된 설치 안내가 들어 있다는 뜻은 아닙니다. 태그 생성 후
추가한 도구와 검증기는 해당 구현의 커밋 고유 링크와 문서에 적힌 SHA-256으로 고정합니다.

긴 가이드를 처음부터 끝까지 읽지 말고, 다음 순서로 필요한 부분만 사용하세요.

1. [고정된 릴리스 파일을 설치](../docs/first-integration.md#2-install-the-exact-v012-release-assets)합니다.
2. 빌드에 맞춰 [Gradle Groovy 절차](../docs/first-integration.md#gradle-groovy-dsl-opt-in-lane),
   [Gradle Kotlin DSL 절차](../docs/first-integration.md#gradle-kotlin-dsl-opt-in-lane), 또는
   [Maven 3.9.14 절차](../docs/first-integration.md#maven-3914-opt-in-profile-lane) 하나만 선택합니다.
3. 공통 단계인 [대표 작업](../docs/first-integration.md#3-add-one-representative-operation) →
   [사람의 기준 파일 승인](../docs/first-integration.md#4-review-and-approve-the-first-baseline) →
   [CI에서 실행 결과 비교](../docs/first-integration.md#5-run-the-candidate-check-in-ci)로 이동합니다.

Maven 사용자는 저장소에 포함된 [모듈 두 개짜리 예제](../examples/maven-pilot/README.md)를
먼저 실행해 자신의 저장소와 다른 지점을 확인할 수 있습니다. 어느 절차에도 맞지 않으면
그 지점에서 중단하세요. Maven 시험 적용용 테스트 두 개를 준비한 뒤에는
[필드 6개를 담은 예제 JSON](../examples/maven-pilot/assisted-pilot.example.json)을 복사해
[실행 도구](../examples/maven-pilot/README.md#one-command-runner-for-an-adapted-external-maven-pilot)에
전달할 수 있습니다. 검증기에 필요한 입력 12개를 직접 조립하지 않고 `review`·`matched`
단계를 실행합니다.

처음 실행했거나 현재 환경에는 맞지 않는다고 판단했다면
[짧은 피드백 양식](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml)에
성공·막힌 지점·지원 범위 밖·필요 없음 중 어느 결과든 짧게 남길 수 있습니다. 공개 이슈에는
원문 SQL, 바인딩 값, JDBC URL, 실제 DB 구성, 전체 로그 같은 민감 정보를 넣지 마세요.

</details>

</details>

## 가장 작은 사용 예

```java
RouteSnapshot snapshot = RouteContract.capture("orders.find-by-user-id", () -> {
    Order actual = orderQueryService.findByUserId(3L);
    assertEquals(201L, actual.id()); // 기존 기능 assertion도 그대로 둡니다.
});

RouteAssertions.assertThat(snapshot)
        .hasCompleteCapture()
        .hasNoReportedExecutionFailures()
        .hasExactlyObservedPhysicalAttempts(1)
        .observesExactlyDataSourceNames("ds_1");
```

<a id="승인-manifest와-structural-manifest-diff"></a>

## 실행 명세를 검토하고 비교하기

작업 하나를 실행하는 동안 `SQLExecutionHook`이 보고한 물리 JDBC 실행 시도를 모아
**실행 명세(manifest)**로 저장할 수 있습니다. 실행 명세는 같은 관측값을 일정한 형식의 JSON으로
만들어, 이번 결과와 검토한 기준을 비교하기 쉽게 합니다.

비교 대상은 실행 시도 수, 데이터 소스 별칭, 훅의 보고 결과, 재작성된 SQL 원문의 해시값,
파라미터 구조입니다. SQL 두 개의 의미가 같은지 판단하거나 전체 라우팅 계획을 구하는 기능은
아닙니다.

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
ManifestVerificationResult result = new ManifestVerifier().verify(approved, candidate);
ManifestAssertions.assertMatched(result); // mismatch이면 stable RCM code와 함께 CI 실패
```

이번 실행 결과(`candidate`)를 저장해도 승인된 기준 파일(`approved`)은 덮어쓰지 않습니다.
의도한 변경이라면 담당자가 차이를 검토한 뒤 기준 파일을 교체해야 합니다.

실제 MySQL에서 동등 조건으로 조회한 기준과 같은 결과를 반환하는 `BETWEEN` 조회의 실행
명세를 [examples/manifests](../examples/manifests/README.md)에서 볼 수 있습니다. 통합 테스트는
매번 파일을 다시 만들어 기존 파일과 바이트 단위로 같은지 확인하고, 구조 비교에서 같은
RCM 진단 코드가 나오는지도 검사합니다.

<details>
<summary>데이터 소스 별칭과 strict/budgetOnly 정책</summary>

어느 데이터 소스를 어떤 별칭으로 표시할지도 검토 대상입니다. 실행 명세에는 호출자가
제공한 별칭이 저장되므로, 민감하지 않은 고정 이름을 사용하세요. 실제 데이터 소스 이름을
그대로 쓰면 그 이름이 노출됩니다. 다른 데이터 소스에 기존 별칭을 붙이면 대상이 바뀌어도
비교에서 놓칠 수 있습니다. 별칭 설정을 실행 명세와 함께 버전 관리하고 검토하세요.

- `ManifestPolicy.strict(...)`: 해시값을 포함한 구조 항목 변화도 차단합니다.
- `ManifestPolicy.budgetOnly(...)`: 시도 수·데이터 소스 집합·훅의 보고 결과 변화는 차단하고, 실행 항목의 구조만 달라진 경우는 `REVIEW_REQUIRED`로 남깁니다.
- 저장하는 JSON에는 타임스탬프, UUID, 스레드 배치, 원문 SQL, 파라미터 값, 예외 메시지가 들어가지 않습니다. 데이터 소스는 호출자가 제공한 별칭으로만 기록하므로, 공유해도 되는 이름인지 호출자가 확인해야 합니다.

같은 행, 관측 시도 `1`, 같은 데이터 소스를 보존하면서 추가 필터와 조건절 순서를 바꾼
MySQL 테스트에서는 해시값과 파라미터 타입 순서만 달라졌습니다. 이는 해당 테스트의
관측 결과일 뿐 두 SQL의 일반적인 의미 동치를 주장하지 않습니다.

| 정책 | 실행 항목의 구조만 달라졌을 때 | 고려할 점 |
|---|---|---|
| `strict` | `DRIFT`, `RCM301`·`RCM302` 차단, 검사 실패 | 재작성된 SQL의 작은 구조 변화도 검토 대상으로 삼음. 의도한 변경도 기준 파일을 갱신하기 전까지 CI에서 실패함 |
| `budgetOnly` | `REVIEW_REQUIRED`, `RCM301`·`RCM302` 차단하지 않음, `passesBlockingChecks=true` | 예산·데이터 소스 집합·훅의 보고 결과의 변화는 계속 막지만 실행 항목의 구조만 달라진 경우는 CI를 통과시키므로 수동 검토를 놓치면 구조 회귀를 허용할 수 있음 |

위 예시의 `ManifestAssertions.assertMatched(result)`는 `REVIEW_REQUIRED`도 거부합니다. 실행 항목의 구조만 달라진
경우를 CI에서 허용하는 `budgetOnly` 정책이라면 그 선택을 코드에 드러내기 위해
`ManifestAssertions.assertPassesBlockingChecks(result)`를 사용해야 합니다.

</details>

## 검증된 핵심 시나리오

| 시나리오 | 실제 검증 결과 |
|---|---|
| 동일 값 `=` → `BETWEEN` | 반환 행은 같고, 관측 시도 `1 → 2`, 데이터 소스 `[ds_1] → [ds_0, ds_1]` |
| 공개 이슈 #38456을 참고해 축소·수정한 테스트 | JOIN과 서브쿼리 결과는 모두 `COUNT=1`, 관측 시도는 각각 `1`과 `8`; 원 이슈의 충실한 재현 주장은 아님 |
| 설정 회귀 | 테이블 샤딩 전략 제거 시 실행 수와 데이터 소스는 같지만 SQL 해시값 변화 검출 |
| 결정성 | 사례 8개를 각 20회 실행해 총 160회 수집했으며, 사례마다 구조 항목이 동일함 |
| 동시에 열린 호출 작업의 수집 범위 | 단일 실행·다중 실행 작업 20쌍에서 다른 작업의 실행이 섞인 경우 0건. 물리 콜백이 시간상 겹치도록 강제하거나 겹친 시간을 측정하지는 않음 |
| 범용 JDBC 도구 비교 | datasource-proxy 외부 배치는 콜백 `1 → 1`, 물리 데이터 소스별 배치는 `1 → 2`, RouteContract도 `1 → 2` |
| 격리된 소비자 빌드 | 같은 소스로 임시 Maven 저장소에 만든 JAR와 POM만 사용하는 별도 소비자 프로젝트에서 SPI 자동 발견과 MySQL 실행 통과. 외부 채택 증거는 아님 |
| 격리된 Maven 3.9.14 시험 적용 | Java 17 기본 환경과 Java 21 호환성 환경에서 프로필 비활성 상태, 빈 캐시, SHA-256 불일치 거부, 실행 결과 생성·기준 일치를 같은 소스로 검증. ShardingSphere-JDBC 5.5.3/MySQL 8.4.11을 사용했으며, 사람의 승인이나 외부 사용자의 도입을 확인한 결과는 아님 |

현재 소스 전체를 검증하는 명령:

```bash
./gradlew --no-daemon --no-build-cache clean check assemble validateOfficialCycloneDxSbom
./scripts/verify-standalone-consumer.sh
./scripts/verify-maven-pilot.sh
./scripts/verify-maven-pilot.sh --java 21
```

모든 명령에 Docker가 필요합니다. 첫 명령은 Java 17, ShardingSphere-JDBC 5.5.3,
다이제스트로 고정한 MySQL 8.4.11 Testcontainers 환경에서 핵심 기능과 MySQL 사례 모음
테스트를 실행하고 JAR·Javadoc·SBOM을 만듭니다. 두 번째 명령은 별도 소비자 테스트 1개를
실행합니다.

세 번째와 네 번째 명령에는 정확히 Apache Maven 3.9.14가 필요합니다. 프로필 비활성 상태,
체크섬, 실행 결과 생성 경로를 각각 Java 17 기본 환경과 Java 21 실행 환경에서 검증합니다.
Java 21 환경에서는 클래스 파일의 주 버전이 65인지도 확인합니다. 이는 같은 소스에서 불변
v0.1.2와 ShardingSphere-JDBC 5.5.3/MySQL 8.4.11을 검증한 결과이며, 외부 적용용 실행기와
시작 도구의 Java 17 지원 범위를 넓히지는 않습니다.

<a id="기존-도구와의-정확한-차이"></a>

## 기존 도구와 함께 쓰는 방법

RouteContract는 사용자가 정한 작업 하나에 ShardingSphere-JDBC 5.5.3의 실행 보고를 묶습니다.
작업을 처리한 스레드의 보고를 연결하고, 저장할 정보를 줄여 실행 명세를 만든 뒤 검토한 기준과
비교합니다. 차이는 정해진 `RCM` 진단 코드로 표시하고 테스트를 실패시킬 수 있습니다.

- ShardingSphere-Proxy의 `PREVIEW SQL`, 그리고 ShardingSphere의 `sql-show`·Agent는 계획·로그·운영 관측 정보를 제공합니다.
- ShardingSphere Audit는 내장 알고리즘 기준으로 인식 가능한 샤딩 조건의 존재를 검사합니다.
- Sniffy와 datasource-proxy는 SQL 수 검증 또는 사용자 정의 JDBC 수집을 제공합니다.
- RouteContract는 이 도구들을 대체하지 않습니다. 실행 명세에서는 저장된 구조 필드를 비교하며, SQL 의미의 동등성을 판정하지 않습니다.

datasource-proxy로도 비슷한 범위의 검사를 직접 만들 수 있습니다. 물리 데이터 소스를 각각
감싼 뒤, 작업별 실행 연결·저장 정보 최소화·일정한 형식으로 정리·차이 비교·검사를 구현하는
방식입니다. RouteContract는 물리 데이터 소스를 각각 감싸는 코드 없이 이 검토 절차를 사용할
수 있도록 묶었습니다. 적용 범위는 ShardingSphere-JDBC 5.5.3입니다.

근거와 한계는 [competitive-analysis.md](../docs/competitive-analysis.md)에, 직접 비교한 datasource-proxy 테스트는 [empirical-comparison.md](../docs/empirical-comparison.md)에 있습니다.

## 코드·공개 증거 경계

주요 코드는 다음과 같이 나뉩니다. 한 디렉터리 안에 여러 역할의 파일이 있을 수 있습니다.

| 경계 | 대표 경로 | 역할 |
|---|---|---|
| 배포 라이브러리 | `routecontract-shardingsphere-5.5/src/main` | 배포 JAR에 들어가는 사용자 API와 5.5.3 SPI 제공자입니다. |
| 공개 검증·예제 | `routecontract-shardingsphere-5.5/src/test`, `examples/` | 단위 테스트, 실제 MySQL 테스트, 별도 소비자 예제입니다. 배포 JAR에는 포함되지 않습니다. |
| 혼합 자동화 | `scripts/`, `.github/workflows/`, `security/`, `gradle/` | `scripts/`에는 사용자용 시작·릴리스 파일 설치 도구와 유지관리자용 릴리스·공급망·시연 검증 도구가 함께 있습니다. 모두 사용자 실행 API에 해당하는 것은 아닙니다. |
| 검증·제출 보조 | `submission/`, `scripts/video-demo-session.sh`, `docs/evidence-matrix.md` | 검증 근거를 추적하고 결과와 재현 자료를 묶는 보조 파일입니다. 배포 제품에는 포함되지 않습니다. |

이 소스는 안정판 대상 프로젝트 버전 `0.1.4`와 대응하는 태그 이름 `v0.1.4`를 선언합니다.
소스에 버전이 적혀 있다고 공개 배포까지 검증된 것은 아닙니다. [릴리스 절차](../RELEASING.md)에
따라 주석 태그(annotated tag), 공개된 불변 정식 릴리스, 배포 검증 실행이 같은 리비전을
가리키는지 확인하고 게시 후 검증도 통과해야 합니다. 이 배포 검증은 외부 사용자의 실행
결과를 대신하지 않습니다.

<details>
<summary>역사적 RC와 공개 CI의 정확한 증거 경계</summary>

`v0.1.0-rc1`은 첫 배포 검증 시도를 보존한 주석 태그입니다. 이 실행은 다이제스트로 받은
MySQL 이미지를 변경 가능한 로컬 태그로 다시 찾는 단계에서 실패했고, 릴리스를 만들지
않았습니다. RC1을 현재 설치 후보로 사용하거나 태그를 이동하지 않습니다.
`v0.1.0-rc2`는 그 실패를 수정한 뒤 [고정한 활성화 기록](../docs/evidence/independent-rc-activation-v0.1.0-rc2.json)을
남긴 과거 사전 릴리스입니다. 해당 파일과 검증 결과를 안정 `v0.1.0`의 검증 결과나
도입 실적으로 바꿔 제시하지 않습니다.

과거 [main 리비전 `54f1c92`의 CI](https://github.com/ym0506/routecontract/actions/runs/31501026857)에서는
정상 테스트 50개와 같은 소스의 격리 소비자 테스트 1개가 실패·오류·건너뛴 테스트 없이
통과했습니다. 이 실행은 RC2나 안정 `v0.1.0`의 리비전·릴리스 파일을 검증한 결과가 아닙니다.
격리 소비자 결과도 외부 채택을 뜻하지 않습니다. 자세한 환경·원시 산출물·한계는
[공개 CI 검증 기록](../docs/public-ci-evidence.md)에서 확인할 수 있습니다. 운영환경 전반의
지원이나 일반적인 성능을 보장하는 결과는 아닙니다.

</details>

<details>
<summary>v0.1.2 GitHub 릴리스 파일을 설치하는 상세 절차</summary>

<a id="공개-release-자산을-registry-없이-사용하기"></a>

## 공개 릴리스 파일을 직접 설치하기

이 절차는 `v0.1.2` 주석 태그, 공개된 불변 정식 릴리스, 같은 리비전의 성공한 배포 검증
실행과 정확한 파일 집합이 모두 있어야 사용할 수 있습니다. 태그 생성 후 추가한 공개
실행기를 커밋·SHA-256·파일 크기로 고정해 사용합니다. 실행기가 릴리스 파일을 내려받아
검증하고, `~/.m2`가 아닌 빈 절대 경로에 정확한 좌표로 설치합니다.
[첫 실제 통합 가이드의 2단계](../docs/first-integration.md#2-install-the-exact-v012-release-assets)에는
로그인·토큰·GitHub API 없이 설치하는 방법과 파일별로 직접 검사하는 방법이 있습니다.

설치기가 출력한 로컬 Maven 저장소와 RouteContract 의존성을 기본 빌드에 바로 추가하지
마세요. [Gradle Groovy DSL](../docs/first-integration.md#gradle-groovy-dsl-opt-in-lane)과
[Gradle Kotlin DSL](../docs/first-integration.md#gradle-kotlin-dsl-opt-in-lane) 절차에서는 시험 적용
속성이 있을 때만 별도 소스 집합·작업·저장소를 활성화합니다. Maven 3.9.14 절차도 기본으로는
비활성인 프로필, 빈 소비자 캐시, 저장소별 SHA-256 검사를 사용합니다.

세 절차 모두 대표 테스트의 기존 ShardingSphere-JDBC 5.5.3 의존성을 재사용합니다. 평상시
빌드와 IDE 동기화는 시험 적용 코드와 로컬 릴리스 저장소 없이 성공해야 합니다. 빌드 구조,
도구, 저장소, 의존성 그래프, 클래스 로더가 검증된 범위와 다르다면 그대로 적용할 수 없으므로
먼저 적합성을 확인해야 합니다.

불변 `v0.1.2` 설치기에 포함된 MySQL OCI 패키지 수준의 수동 검토는 UTC
`2026-12-05`까지만 유효합니다. `2026-12-06` UTC부터 설치기는 검증을 통과시키지 않고 중단하며,
그때는 검토가 갱신된 더 최신 불변 릴리스를 사용해야 합니다. 만료 검사를 우회하지
마세요.

<details>
<summary>태그에 고정한 내부 설치기의 공급망 검증 범위</summary>

커밋에 고정한 공개 실행기는 HTTPS로 파일을 받습니다. 이어서 호출하는 내부 설치기는
태그에 고정되어 있으며 네트워크를 사용하지 않습니다. 다음 항목을 검증한 뒤 실행용·소스·
Javadoc JAR와 POM만 지정한 Maven 구조에 복사합니다.

- 정확한 공개 파일 목록과 `SHA256SUMS`, 민감 정보를 줄인 공급망 검증 자료와 공개 SBOM/POM의 해시 연결
- SNAPSHOT이 아닌 POM 좌표, 상위 POM과 재배치 설정이 없는 POM
- JAR의 네임스페이스 경로와 소스 JAR의 Java 패키지, 소스 ZIP의 단일 버전 루트
- `LICENSE`·`NOTICE`, 모든 Java 파일의 소스 루트·프로젝트 자체 패키지·경로와 선언의 일치
- 컴파일된 `.class` 및 JTS/Mahout 이름·패키지 경계, 정해진 `ym0506` 제공자 네임스페이스

기존 좌표는 덮어쓰지 않습니다. `~/.m2/repository`나 그 하위 경로를 대상으로 지정하면
거부합니다. 이어서 태그 생성 후 추가한 보조 도구를 고정 해시로 확인한 뒤 SHA-1·SHA-256
체크섬 파일 8개만 만듭니다. 배포 파일의 바이트는 바꾸지 않습니다.

체크섬은 다운로드 중 파일이 달라졌는지 확인할 뿐 게시자 신원을 인증하지는 않습니다.
반드시 해당 태그의 공개 릴리스에서 파일을 받으세요. 이름·경로·선언 패키지·의존성을
검사하는 절차이므로, 이름을 바꾸거나 복사한 코드의 실제 출처까지 판정하지는 않습니다.
릴리스 압축 파일의 내용·경로·실행 권한이 최종 태그에서 추적하는 Git 트리와 같은지는
최종 제출 패키징 검사에서 별도로 확인합니다.

</details>

같은 소스에서 앞서 만든 저장소를 RouteContract 전용으로 사용해 실제 MySQL 소비자까지
검증하려면, 별도의 빈 대상 경로를 지정해 다음 명령을 실행합니다. 이 결과는 릴리스 패키징
검증이며 외부 사용자의 도입을 확인한 결과는 아닙니다.

```bash
./scripts/verify-release-assets-consumer.sh \
  /absolute/path/to/downloaded-release-assets \
  /absolute/path/to/empty-verification-maven
```

반환값 검사는 통과하고 실행 계약 검사는 실패하는 예제만 실행하려면 다음 명령을 사용합니다.

```bash
./scripts/run-demo.sh
```

동등 조건을 같은 값의 범위 조건으로 바꿔도 업무 결과는 같습니다. 실제 MySQL에서
관측 실행 시도와 데이터 소스가 각각 `1 → 2`로 늘고, 엄격한 실행 명세 검사에서
`RCM201`·`RCM202`로 CI가 실패하는 상황을 실행합니다. 이 명령은 예상된 위반을 검증하는 테스트이므로 성공 종료합니다.

검증된 실행 명세 두 파일만 읽어 실제 CI 검사의 비정상 종료를 재현하려면 다음 명령을
사용합니다. Docker 없이 `RCM201`·`RCM202`를 출력하고 의도적으로 종료 코드 `1`을 반환하며,
전용 예제이므로 일반 `test`와 `check`에는 포함되지 않습니다.

```bash
./scripts/demo-manifest-ci-failure.sh
```

실제 MySQL에서 정규화한 파일을 재생성·대조한 다음 같은 승인본으로 빌드가 실패하는 전체
흐름을 한 명령에서 보려면 아래 스크립트를 사용합니다. 앞 단계가 모두 정상이어도 마지막
계약 검사 때문에 의도적으로 종료 코드 `1`을 반환합니다.

```bash
./scripts/demo-end-to-end-ci-failure.sh
```

</details>

## 정확한 증거 경계

관측하는 항목:

- 훅이 보고한 데이터 소스 이름
- 훅이 보고한 재작성된 SQL 원문의 SHA-256 해시값
- 파라미터 개수와 Java 타입 이름
- 호출 스레드·작업 스레드 구분 플래그(trunk/worker)
- 실행 시작, 훅의 반환 보고, 훅의 실패 보고, 종료 보고를 확인하지 못한 상태

관측하거나 증명하지 않는 항목:

- 전체 라우팅 계획 또는 `RouteContext`
- 계획된 실행 단위 전체와 모든 대상 샤드
- 정확한 물리 테이블 수
- 자동 `FULL_ROUTE`/`BROADCAST` 판정
- 트랜잭션 커밋 또는 업무 성공

`finishSuccess()`라는 ShardingSphere SPI 메서드명은 트랜잭션 커밋이나 업무 성공을 뜻하지 않습니다. RouteContract의 `CALLBACK_RETURNED`는 ShardingSphere 5.5.3이 물리 `executeSQL` 반환 뒤 해당 훅 제공자에 `finishSuccess`를 보고했다는 뜻으로만 사용합니다. 둘러싼 JDBC 작업·트랜잭션·애플리케이션 작업의 완료도 증명하지 않습니다.

## v0.1 지원 범위

현재 공개 **0.1.4**의 범위입니다. [이번 버전의 공개 소비자 검증](evidence/release-0.1.4-central.md#public-consumer-verification)과
[Java 17/21 지원을 처음 추가한 검증 기록](java21-runtime-acceptance.md)을 참고하세요.
예전 0.1.2 설치기와 외부 적용용 실행기에는 각각 문서화된 별도 제약이 적용됩니다.

이 문제는 특정 ORM이나 저장소 API에 한정되지 않습니다. Apache ShardingSphere-JDBC는
직접 JDBC로 연결하거나 MyBatis·JPA·Hibernate와 함께 사용할 수 있습니다. RouteContract의
수집 API도 특정 ORM에 종속되지 않습니다. 다만 MyBatis·JPA·Hibernate 각각의 실제 호출부터
결과까지 호환성을 검증했다는 뜻은 아닙니다.

- Java 17 또는 21
- Apache ShardingSphere-JDBC **정확히 5.5.3**
- 정상 반환하고 수집 종료 시 호출 스레드에 인터럽트가 없는 동기식 `PreparedStatement`
- MySQL 8.4.11 기반 통합 검증
- 서로 다른 호출 스레드의 동시 작업 및 테스트에서 여러 실행 시도를 보고하는 작업 스레드의 콜백

지원 범위 밖:

- ShardingSphere-Proxy
- JDBC 배치와 리액티브 실행
- 애플리케이션 자체 `@Async` 경계
- SQL Federation의 모든 실행 경로
- 다른 ShardingSphere 버전
- SQL을 실행하지 않는 정상 작업 검증
- 훅이 실패를 보고했거나 호출 스레드에 인터럽트가 발생한 작업의 실행 계약 승인

실행 전 검사에서는 클래스 경로의 `shardingsphere-infra-executor`와
`shardingsphere-infra-spi`가 구현 버전 `5.5.3`을 보고하는지, 서비스 로더가 RouteContract
제공자를 정확히 1개 찾는지 확인합니다. 전체 ShardingSphere 아티팩트의 버전 일치까지
증명하지는 않습니다. 이 조건이 맞지 않거나 수집 중에 실행 시작 보고가 관측되지 않으면
검사를 통과시키지 않습니다. Proxy·배치·리액티브 등 지원 범위 밖의 모든 경로를 자동으로
식별하고 거부하는 것은 아닙니다.
실패한 병렬 실행에서는 ShardingSphere 5.5.3이 이미 제출한 작업 스레드를 전부 기다리지 않을
수 있으므로, `REPORTED_EXECUTION_FAILURE` 수집 결과는 진단에만 사용하고 실행 예산이나
실행 명세 일치 검사를 통과시키지 않습니다.

한 번 수집할 때는 최대 10,000개의 물리 실행 시도만 보존합니다. 이를 넘으면 메모리를 계속
늘리는 대신 `RC_ATTEMPT_LIMIT_EXCEEDED` 진단과 함께 `INCOMPLETE`로 실패합니다.

<a id="의존성release-호환성-상세"></a>

## 의존성·릴리스 호환성 상세

현재 공개 **0.1.4**는 [위의 Central 좌표](#install-014)로 설치하고 기존 ShardingSphere 실행 모듈
전체가 정확히 5.5.3인지 확인합니다. RouteContract가 ShardingSphere를 내장하거나 모든 모듈 버전을
맞춰주지는 않습니다. [공개 배포 근거](evidence/release-0.1.4-central.md)와
[Java 17/21 소비자 검증](java21-runtime-acceptance.md)에서 확인된 실행 환경을 볼 수 있습니다.

<details>
<summary>과거 0.1.2 의존성 그래프·로컬 설치·Javadoc 근거</summary>

아래 버전과 제약은 당시 릴리스와 테스트 구성의 빌드 기록입니다. 현재 애플리케이션에 새로 추가할
의존성 목록이 아닙니다.

게시 후 검증을 통과한 안정 `v0.1.2` 릴리스의 정확한 좌표는
`io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.2`이며 Maven Central
게시를 주장하지 않습니다. 이 좌표를 기본 의존성 그래프에 바로 붙이지 말고
[첫 실제 통합 가이드](../docs/first-integration.md)의 격리된 시험 적용 절차에서만 사용하세요.
기존 ShardingSphere-JDBC 5.5.3 테스트의 실제 의존성 그래프를 재사용하며, 전체 실행
클래스 경로를 검토해야 합니다.

RouteContract 빌드는 의존성 코드를 배포물에 내장하지 않으며, 모듈의 `compileOnly`
ShardingSphere/BOM 선언은 공개 POM에서 소비자 버전 제약으로 전달되지 않습니다. 검증된
Gradle 테스트·실행 의존성 그래프에서는 고정한 테스트 구성에 따라 ShardingSphere 5.5.3 호환성 그래프의
Jackson 2 core·databind·datatype-jdk8·datatype-jsr310 모듈이 2.18.9로 해석되고,
Calcite Core·linq4j는 1.42.0으로 해석됩니다. JTS Core 1.19.0은 유지되지만 JTS I/O
Common은 그래프에 없어야 합니다. 단, Jackson
3.1.5도 함께 사용하는 실행 환경에서는 두 계열이 공유하는
`jackson-annotations`가 Jackson 3 BOM에 따라 2.21로 해석됩니다. 이 설정은 RouteContract가
직접 사용하는 별도 `tools.jackson.core:jackson-core:3.1.5` 제품 런타임을 대체하거나
낮추지 않습니다.

배포 검증 워크플로는 Temurin 17.0.20.1+1을 고정해 사용합니다. 이 환경에서 만든 안정
릴리스의 Javadoc 배포물에는 OpenJDK 표준 문서 생성기의 정적 파일과 `legal/` 고지가
포함됩니다. 일반 로컬 빌드는 Java 17만 요구하므로 Javadoc에 같은 버전의 파일이
포함된다고 보장하지 않습니다. 이 파일은 실행용 JAR나 실행 의존성이 아니며 상세 목록은
[THIRD_PARTY.md](../THIRD_PARTY.md)에 있습니다.

</details>

## 정보 최소화와 보안

수집 결과와 실행 명세에는 원문 SQL, 파라미터 값, 접속 설정, 예외 메시지를 저장하지 않습니다.
다만 데이터 소스 이름, 작업 ID, Java 타입 이름, 솔트(salt)를 추가하지 않은 SQL
해시값도 민감한 개발 정보일 수 있습니다. SHA-256으로 바꿨다고 익명화되는 것은 아닙니다.
v0.1에서는 기밀 값을 SQL 원문에 직접 넣지 않고, 같은 조건에서 결과를 재현할 수 있는
`PreparedStatement` 테스트를 전제로 합니다. [SECURITY.md](../SECURITY.md)를 확인하세요.

## 기여와 확장

현재 공개 `0.1.4`를 실행하거나 기존 테스트에 적용했거나, 적용 가능성을 묻고 싶다면
[짧은 피드백 양식](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml)에
성공, 막힌 지점, 지원 범위 밖 또는 필요 없음 중 어느 결과든 남길 수 있습니다. 비공개 프로젝트의 사용 경험도 환영합니다. 설치 없이 검증 방법이나 필요한 기능만 알려주셔도 됩니다.
사용 단계와 확인 가능한 근거는 [별도로 기록](../docs/user-feedback.md#recording-use-and-evidence)하며,
피드백만으로 운영 사용·보안·성능·추천을 주장하지 않습니다.

버그나 기능 제안은 정확한 ShardingSphere 버전, 사용자에게 보이는 회귀 또는 누락된
기능, 최소한의 합성 테스트 구성을
[이슈 양식](https://github.com/ym0506/routecontract/issues/new/choose)에 기록합니다. 구현 변경은
수정 전에 실패하는 테스트, 실제 MySQL 검증, 명시적인 지원 한계를 함께 제시해야 합니다.

새 어댑터나 리포트 출력 기능은 구체적인 사용자 필요, 버전별 테스트 구성, 실제 MySQL CI를 갖춘 뒤 검토합니다. 현재 v0.1 범위는 정확히 5.5.3으로 유지합니다. 전체 절차는 [기여 가이드](../CONTRIBUTING.md)에 있습니다.

## 문서와 재현 경로

- [기술 명세](../docs/specification.md)
- [아키텍처와 신뢰 경계](../docs/architecture.md)
- [경쟁 도구 분석](../docs/competitive-analysis.md)
- [datasource-proxy 실증 비교](../docs/empirical-comparison.md)
- [과거 대회 검증 목록](../docs/evidence-matrix.md)
- [같은 소스의 Maven 배포물을 사용하는 격리 예제](../examples/standalone-consumer/README.md)
- [격리된 Maven 3.9.14 도입 검증 예제](../examples/maven-pilot/README.md)
- [SBOM 생성과 검토](../docs/sbom.md)
- [출처·선행 작업 경계 공개](../ORIGIN_AND_PRIOR_WORK.md)
- [AI 보조 사용 공개](../AI_ASSISTANCE.md)
- [기여 가이드](../CONTRIBUTING.md)

## 상표와 라이선스

RouteContract는 Apache Software Foundation과 제휴하거나 보증받은 프로젝트가 아닙니다.
Apache ShardingSphere와 Apache는 Apache Software Foundation의 상표입니다.

RouteContract는 [Apache License 2.0](../LICENSE)으로 배포합니다. 직접·테스트 의존성과 배포 포함 여부는 [THIRD_PARTY.md](../THIRD_PARTY.md)를 참고하십시오.
