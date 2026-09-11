# 기존 테스트 하나에 RouteContract 적용하기

[English](first-project.md) · [실행 가능한 예제](../examples/first-project/README.md) · [리포트 미리보기](evidence/ci-review-report-example.md)

기존 업무 결과 검증을 유지하면서, 관측된 물리 JDBC 실행 시도가 검토한 기준과 같은지
확인하는 과정입니다. **Maven Central의 RouteContract 0.1.3**, **Java 17**,
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
   **Gradle**, **Both**도 선택할 수 있습니다. 예전에 만든 fork에 `build_tool` 선택이 없다면
   먼저 main 브랜치를 동기화하세요.
4. 새 실행을 열고 완료 후 **Summary**에서 세 단계를 확인합니다.

   | 단계 | 정확히 검증하는 업무 행 | 관측 실행 시도 / 별칭 | 계약 결과 |
   | --- | --- | --- | --- |
   | 정상 조회 | 주문 201 / 사용자 3 / PAID | 1 / 1 | `MATCH` |
   | 같은 결과를 반환하는 범위 조회 | 동일한 행 | 2 / 2 | `POLICY_VIOLATION`: `RCM201`, `RCM202` |
   | 정상 조회로 복구 | 동일한 행 | 1 / 1 | `MATCH` |

   **예상한 거부와 정상 복구를 모두 확인해야 체험 workflow가 성공합니다.** 범위 조회 테스트
   자체는 실패합니다. 의존성·컴파일·Docker 오류는 계약 거부로 인정하지 않으며, 확인하지
   못한 단계는 요약에 `Not verified`로 표시합니다.
5. 실행 화면의 **Artifacts**에서 **first-project-Maven** 또는 **first-project-Gradle**을
   내려받습니다. `build/lifecycle-evidence/` 아래 `match/`, `range/`, `restored/`에 각 단계의
   `candidate.json`, `review.json`, `review.md`를 보관합니다. `range/review.md`부터 보세요.

workflow는 capture가 없는 기준 파일을 자동 승인하지 않는지도 확인합니다. 비교에는 예제의
기존 검토된 합성 기준을 사용하며 그 파일을 바꾸지 않습니다. 자신의 애플리케이션 기준을
승인하는 과정은 별도입니다. 체험 후 [자신의 테스트 하나에 적용](#자신의-테스트와-ci로-옮기기)하세요.

**Run workflow**가 보이지 않으면 자신의 fork인지, 기본 브랜치에 workflow가 있는지
확인하세요. [GitHub 수동 실행 안내](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)도 참고할 수 있습니다.

## 예제 실행

로컬 실행에는 Java 17과 실행 중인 Docker가 필요합니다. 처음에는 의존성과 MySQL 이미지를
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

기본 실행은 예제에 포함된 검토된 기준 파일과 비교합니다. 업무 결과 assertion과 계약 비교가
통과하고, `build/routecontract/review.md`와 `review.json`에 `MATCH`가 나와야 합니다.
Docker·컴파일·다운로드 오류는 실행 환경 문제이므로 계약 위반과 구분해서 확인하세요.

## 첫 기준을 직접 검토하기

새 기준을 만드는 과정을 연습하려면 candidate를 생성합니다.

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

## 같은 업무 결과에서 실행 변화 확인

범위 조건을 사용하는 예제 변형을 실행하면 동일한 주문 행을 반환하면서 관측된 물리 JDBC
실행 시도가 **1회에서 2회**로 늘어납니다.

<details>
<summary>Maven</summary>

```bash
mvn -B test -Droutecontract.query=range \
  -Droutecontract.baseline=baselines/first-review.approved.json
```

</details>

<details>
<summary>Gradle</summary>

```bash
../../gradlew -p . test --rerun-tasks -ProutecontractQuery=range \
  -ProutecontractBaseline=baselines/first-review.approved.json
```

</details>

**이 명령은 실패해야 합니다.** `build/routecontract/review.md`에서 `POLICY_VIOLATION`,
실행 시도 예산을 뜻하는 `RCM201`, 관측 별칭 예산을 뜻하는 `RCM202`를 확인하세요.
업무 결과 assertion은 통과하고 계약 비교가 실패합니다. 기준 파일은 바뀌지 않습니다.
query 옵션을 빼고 다시 실행하면 `MATCH`로 돌아옵니다.

관측된 시도 수는 물리 테이블 수나 전체 실행 계획이 아닙니다. 실행 시도가 늘었다는 사실만으로
성능 저하를 단정할 수 없으며, 의도한 변경인지는 담당자가 판단합니다.

## 자신의 테스트와 CI로 옮기기

1. 기존 프로젝트에 [Central 테스트 의존성](../README.md#install-013)을 추가합니다.
   ShardingSphere와 데이터 소스 구성은 기존 것을 사용하며, 테스트 런타임의 모든
   ShardingSphere 모듈 버전이 정확히 5.5.3이어야 합니다.
2. 대표 repository/service 호출을 `RouteContract.captureResult`로 감싸고, candidate를 쓰기
   전에 반환값을 기존 assertion으로 검증합니다. `capture` 내부에서 업무 결과를 검증하는
   방법도 가능합니다. 자신의 테스트 fixture를 사용하세요.
3. 작업 ID, 데이터 소스의 민감하지 않은 별칭, 실행 예산을 정합니다. candidate와 baseline
   경로를 분리하고, 첫 candidate는 담당자가 직접 검토합니다.
4. 일반 테스트에서는 `ManifestReviewReport.compare`로 비교하고 리포트를 저장한 뒤
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
