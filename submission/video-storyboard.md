# RouteContract 3분 시연 영상 스토리보드

상태: 2분 52초 촬영안. 안정 `v0.1.0`·제출 revision을 동결하고, 외부 결과는 증거 cutoff의 실제 상태(qualified result 또는 0건)로 확정한 뒤 녹화한다.

핵심 문장:

> 같은 비즈니스 결과 뒤에 숨은 관측 실행 회귀를 CI 계약으로 드러낸다.

2024 학생 대상 AutoRAG의 단일 개발자 여정, 2025 일반 대상 Hot Updater의 baseline/candidate 인과 비교, 2025 일반 금상 Zephyr RPi5의 실제 실행 뒤 OSS 증거 배치를 참고했다. 수상과 영상 형식 사이의 인과관계를 주장하지 않으며, 2026년 3분 제한에 맞는 전달 구조만 참고한다.

## 촬영 전 개인정보 안전 셸

실제 저장소 위치가 보이지 않도록 저장소 루트로 이동한 뒤 **녹화 전에** 설정한다.

```bash
export PS1='routecontract$ ' RPROMPT=''
printf '\033]0;RouteContract demo\007'
clear
exec zsh -df
```

- 터미널 제목 표시줄은 자르거나 위 명령으로 고정한다. `pwd`, `env`, `docker ps`, IDE 전체 화면은 녹화하지 않는다.
- 알림·메일·Git credential helper UI를 끄고, 1080p에서 110열 이상이 보이도록 글자 크기를 맞춘다.
- `video-demo-session.sh`는 하위 명령의 stdout/stderr를 화면에 흘리지 않는다. 기대한 marker와 종료 코드를 먼저 검증한 뒤 고정된 허용 목록만 출력하므로 로컬 경로, 동적 포트, 컨테이너 ID, 원문 SQL, 바인드 값이 촬영 화면에 나오지 않는다.
- `VIDEO_DEMO_ERROR`가 나오면 녹화를 중단한다. 원본 스크립트는 녹화 밖에서만 실행해 원인을 확인한다.
- `mysql`과 `fingerprint`는 실제 MySQL을 실행하고 `0`, `ci`는 검증된 intentional-red gate일 때만 `1`을 반환한다. wrapper 검증 자체가 깨지면 구별 가능한 `2`를 반환한다.

## 0:00–0:08 — 결과부터 보여 주는 훅

긴 로고나 제목 화면을 쓰지 않는다. 작은 `RouteContract` 오버레이와 함께 좌우 분할 화면을 즉시 보여 준다.

```text
baseline                         candidate
businessRowsEqual=true           businessRowsEqual=true
observedAttempts=1               observedAttempts=2
                                 RCM201 RCM202
```

내레이션:

> 두 쿼리는 같은 행을 반환합니다. 그러나 물리 JDBC 실행 시도는 한 번에서 두 번으로 늘었습니다.

## 0:08–0:21 — 정확한 제품 정의

화면:

```text
ShardingSphere-JDBC 5.5.3 · Java 17 · MySQL 8.4.11
observed JDBC attempts ≠ complete route plan ≠ transaction commit
```

내레이션:

> RouteContract는 ShardingSphere hook이 보고한 JDBC 실행 시도를 계약으로 고정합니다. route plan이나 commit은 보지 않습니다.

## 0:21–0:35 — 설치와 최소 API

화면은 먼저 아래 설치 경계를 보여 준 뒤 좌표와 코드를 크게 보여 준다. Maven Central에
게시된 것처럼 보이면 안 된다.

```text
immutable GitHub Release assets → SHA-256 / attestation verification
→ explicit isolated Maven repository · not published to Maven Central
```

```gradle
testImplementation("io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.0")
```

```java
RouteSnapshot snapshot = RouteContract.capture(
        "find-paid-orders-by-user",
        () -> assertEquals(1, repository.findPaidOrders(request.userId())));

RouteAssertions.assertThat(snapshot)
        .hasCompleteCapture()
        .hasNoReportedExecutionFailures()
        .hasExactlyObservedPhysicalAttempts(1);
```

아래 구조는 작은 오버레이로 표시한다.

```text
capture → ShardingSphere-JDBC 5.5.3 SQLExecutionHook → minimized snapshot
        → canonical manifest → semantic diff → CI assertion
```

내레이션:

> 검증한 GitHub Release 자산을 명시한 격리 Maven 저장소에 설치하면 JAR의 SPI가 자동 발견됩니다. 기존 assertion은 유지하고, capture 결과를 최소정보 manifest와 CI assertion으로 연결합니다.

## 0:35–1:10 — 실제 MySQL baseline과 candidate

실행:

```bash
./scripts/video-demo-session.sh mysql
```

이 명령은 내부적으로 기존 `run-demo.sh`를 실행한다. 실제 MySQL test와 committed manifest bytes, `ROUTECONTRACT_MANIFEST_DEMO` marker를 검증한 뒤 다음 촬영용 허용 목록만 보여 준다.

```text
[MYSQL BASELINE -> CANDIDATE]
environment             Java 17 | MySQL 8.4.11 digest-pinned | ShardingSphere-JDBC 5.5.3
businessResult          UNCHANGED (one row in both captures)
observedAttempts        1 -> 2
observedDataSources     1 -> 2
approvedAliases         [orders-odd]
candidateAliases        [orders-even,orders-odd]
verificationStatus      POLICY_VIOLATION
blockingCodes           [RCM201,RCM202]
privacy                 raw child output withheld | raw SQL/binds not retained
aliases                 reviewed aliases remain | minimized != anonymized
demo_exit               0
```

내레이션:

> 고정한 MySQL 8.4.11 두 개와 ShardingSphere-JDBC 5.5.3을 실행합니다. 두 조건은 같은 한 행을 반환하지만 hook이 보고한 시도와 관측 alias 수는 한 개에서 두 개로 늘어 RCM201과 RCM202가 발생합니다.

녹화 규칙:

- 명령 시작과 최종 marker는 정상 속도.
- 컨테이너 기동 대기만 8배속.
- 화면에 `실제 실행 · 대기 구간 8×` 표시.

동일한 결과와 candidate diff는 한 흐름 안에서 확대한다. 원문 SQL 대신 `equality predicate`와 `same-value range predicate`라는 설명용 라벨만 사용하고, 구체적인 조회 값과 row 식별자는 표시하지 않는다. 재현 명령의 `demo_exit=0`은 회귀가 없다는 뜻이 아니라 예상한 회귀와 manifest bytes를 테스트가 정확히 검증했다는 뜻이다.

manifest 화면 콜아웃:

- `approved: 1 / [orders-odd]`
- `candidate: 2 / [orders-even, orders-odd]`
- `candidate는 approved를 자동으로 덮어쓰지 않음`
- `원문 SQL·바인드 값 미저장 · manifest에는 검토한 alias만 기록`
- `alias는 비민감 이름 사용 · minimized ≠ anonymized`

## 1:10–1:34 — 실제 non-zero CI gate

실행:

```bash
./scripts/video-demo-session.sh ci
```

반드시 보여 줄 실제 출력:

```text
[INTENTIONAL CI GATE]
approvedAttempts        1
candidateAttempts       2
verificationStatus      POLICY_VIOLATION
blockingCodes           [RCM201,RCM202]
RCM201 BLOCKING ATTEMPT_BUDGET_EXCEEDED: maximum=1, observed=2
RCM202 BLOCKING DATA_SOURCE_BUDGET_EXCEEDED: maximum=1, observed=2
BUILD FAILED (intentional)
ci_exit                 1
```

내레이션:

> 같은 두 manifest를 CI assertion에 넣으면 예산 위반을 stable code로 출력하고 build가 1로 실패합니다. 이 red task는 정상 check와 분리돼 있습니다.

## 1:34–1:55 — count가 같아도 구조가 달라지면 차단

실행:

```bash
./scripts/video-demo-session.sh fingerprint
```

이 명령은 기존 MySQL corpus의 table-strategy-removal 사례를 실행하고 테스트가 낸 안전 marker를 검증한다. 화면:

```text
[SAME-BUDGET FINGERPRINT DRIFT]
businessResult          UNCHANGED
observedAttempts        1 -> 1
observedDataSources     1 -> 1
observedAliases         [orders-odd] -> [orders-odd]
fingerprintMultiset     CHANGED
verificationStatus      DRIFT
blockingCodes           [RCM301,RCM302]
privacy                 raw child output withheld | raw SQL/binds not retained
aliases                 reviewed aliases remain | minimized != anonymized
fingerprint_demo_exit   0
```

내레이션:

> 실행 수와 data source가 모두 같아도 rewritten SQL fingerprint 구조가 달라지면 strict contract가 RCM301과 RCM302로 차단합니다. 단순 query counter와 다른 지점입니다.

## 1:55–2:17 — 재현성과 지원 경계

한 장의 검증 카드만 보여 준다.

```text
real MySQL 8.4.11 · exact ShardingSphere-JDBC 5.5.3
8 cases × 20 = 160 captures · unique signature per case = 1
20 concurrent caller-operation pairs · mixed captures = 0
raw SQL / parameter values not retained
datasource-proxy can also observe 1→2 when wired per physical data source
```

내레이션:

> 실제 MySQL 160회에서 사례별 signature는 하나였고, 동시에 시작한 caller operation 20쌍의 capture 혼합은 0이었습니다. physical callback overlap을 증명한 수치는 아닙니다.

이 결과는 정상 반환하고 caller가 interrupt되지 않은 동기식 PreparedStatement 범위에만 적용된다. “동시 physical callback을 증명했다”라고 말하지 않는다.

## 2:17–2:28 — 공정한 기존 도구 비교

화면:

```text
datasource-proxy: per-physical-data-source wiring can also observe 1 -> 2
RouteContract: operation correlation -> manifest -> reviewed diff -> CI assertion
```

내레이션:

> datasource-proxy도 1대2를 봅니다. RouteContract는 상관관계, 승인 manifest와 diff를 한 계약으로 묶습니다.

## 2:28–2:44 — 공개 OSS 증거

다음 공통 증거가 실제로 공개된 뒤에 이 구간을 녹화한다.

- 제출 revision의 Ubuntu CI 성공
- main에 blocking contract check를 요구하는 branch rule/ruleset
- 제출 revision과 같은 안정 `v0.1.0` release와 annotated tag
- main/source/Javadoc JAR, POM, SBOM, SHA-256

외부 결과는 증거 cutoff에 다음 중 정확히 하나의 상태로 동결한다.

- **qualified-result 분기:** Issue #9의 모든 acceptance criteria(사람 비작성자·비협업자, 정확히 활성화된 immutable RC, first outcomes 전 비공개 설정 도움 없음)를 충족한 참가자가 본인 계정과 환경으로 남긴 원본 first-outcome dedicated independent-install Issue를 보여 준다. 이를 `독립 clean-install 첫 결과`로만 표시하고 adoption·실사용 증거로 부르지 않는다.
- **0-result 분기:** Issue #9의 activation/protocol, 공개 모집 시작·cutoff, `qualified non-author first outcomes: 0`, `independent external validation not obtained before cutoff`를 보여 준다. author·AI·clone 결과를 외부 결과로 대체하지 않는다.

실제 결함이 발견된 경우에만 그 결함을 수정한 PR을 보여 준다. RouteContract-specific upstream 질문은 실제로 게시한 경우에만 질문과 현재 상태를 보여 준다. 게시하지 않았다면 카드와 내레이션에서 제외하고 upstream 확인이 없음을 유지한다. 응답이나 승인을 받았다고 과장하지 않는다.

화면은 로그아웃한 브라우저에서 최종 tag/SHA, green CI, exact Release assets와 두 외부 분기 중 하나의 상태 카드를 보여 준다. upstream 카드는 실제 질문이 있는 경우에만 추가한다. 같은 checkout의 `standalone` fixture는 공개 패키징 검증이지 외부 채택 증거가 아니므로 본편에서 실행하지 않는다. 최종 Release 자산을 내려받아 빈 Maven 저장소에서 검증한 결과는 CI 링크로만 제시한다.

내레이션:

- qualified-result 분기: “최종 revision의 CI와 checksummed Release를 공개했고, 비작성자 독립 clean-install 첫 결과 1건을 adoption과 구분해 링크했습니다.”
- 0-result 분기: “최종 revision의 CI와 checksummed Release를 공개했습니다. 공개 모집 cutoff까지 qualified 비작성자 첫 결과는 0건이어서 외부 검증 미확보를 그대로 표시했습니다.”

upstream 질문을 게시했다면 “upstream 질문과 현재 공개 상태도 링크했습니다.”라고만 이어서 말한다. 게시하지 않았다면 이 문장을 말하지 않는다.

Maven Central에 실제 게시하지 않았다면 Maven Central을 언급하지 않는다.

## 2:44–2:52 — 결론

화면:

```text
same result · hidden execution regression · blocking CI contract
CALLBACK_RETURNED ≠ JDBC completion ≠ COMMIT
5.5.3 · normal return · caller not interrupted at close
synchronous non-batch PreparedStatement only
```

내레이션:

> 같은 결과 뒤에서 hook이 보고한 실행 회귀를 assertion으로 막습니다. 지원 범위는 5.5.3의 정상 반환 동기식 non-batch PreparedStatement이며 capture 종료 시 caller가 interrupt되지 않은 경우입니다.

## 최종 녹화 게이트

- [ ] 영상 속 revision과 제출 revision이 같다.
- [ ] Ubuntu 공개 CI에서 root build와 standalone consumer가 성공했다.
- [ ] main ruleset이 `Java 17 / MySQL integration / SBOM`과 `Dependency review`를 required로 지정하고, 전자 job이 contract assertion semantics를 테스트한다. intentional-red task 자체를 required check라고 말하지 않는다.
- [ ] baseline/candidate marker와 `demo_exit=0`을 재확인했다.
- [ ] intentional-red script가 RCM201·RCM202와 `ci_exit=1`을 출력한다.
- [ ] RCM301·RCM302 화면도 최종 revision의 실제 결과다.
- [ ] 세 핵심 촬영 명령과 삽입 그림의 화면 출력에서 `/Users/`, `jdbc:`, `localhost:포트`, `127.0.0.1:포트`, `SELECT`, `t_order`, `ds_0`, `ds_1`, `user_id`, `row 201`, `= 3`, `BETWEEN 3`이 나오지 않는다.
- [ ] 제출 SHA와 같은 안정 `v0.1.0` release assets, SBOM, checksum이 공개되어 있다.
- [ ] 외부 결과 카드는 실제 qualified Issue 또는 공개 모집기간·cutoff·0건·외부 검증 미확보 중 정확히 하나를 표시하며, author·AI·clone을 외부 결과로 세지 않는다.
- [ ] 영상 속 테스트 수가 최종 revision과 일치한다.
- [ ] 로컬 경로, 토큰, Docker credential, 알림, 개인 메일이 보이지 않는다.
- [ ] 최종 로컬 파일은 `ffprobe` 기준 1920×1080 이상이고 audio stream이 1개 이상이며, 허용된 일반 encoder/language/handler tag 외에 명시적으로 금지한 identity·location·device metadata tag가 없다.
- [ ] 1080p에서 terminal 글자가 읽히며 자막이 잘리지 않는다.
- [ ] YouTube는 공개·non-live·연령 제한 없음 상태이고 다운로드 가능한 1080p 이상 format이 처리됐으며, 재생시간이 2:50~2:55이고 로그인 없이 재생된다.
- [ ] 자동 gate가 판독하지 않는 음량·clipping·내레이션 진실성·화면 가독성은 owner가 로컬 파일과 로그아웃 공개 1080p 영상을 처음부터 끝까지 직접 듣고 보며 확인했다.

## 금지 표현

- `RouteContract가 전체 route plan을 관측한다.`
- `실행 수가 곧 shard 또는 physical table 수다.`
- `CALLBACK_RETURNED가 commit 또는 비즈니스 성공을 뜻한다.`
- `동시 테스트로 모든 thread safety가 증명됐다.`
- `batch·reactive·Proxy·모든 ShardingSphere 버전을 지원한다.`
- `datasource-proxy는 물리 실행을 관측할 수 없다.`
- `manifest를 익명화했다.`
- `SBOM이 있으므로 보안·라이선스 문제가 없다.`
- `ShardingSphere가 RouteContract를 인정했다.`
- `세계 최초·유일·100% 검출.`
- 아직 공개되지 않은 release, 사용자, CI 또는 upstream 반응을 완료형으로 말한다.

## 공식 영상 참고 링크

- [AutoRAG — 2024 학생 대상](https://www.youtube.com/watch?v=T-iOcb58-gI)
- [Hot Updater — 2025 일반 대상](https://www.youtube.com/watch?v=5FYX0P0Zn9I)
- [Zephyr Raspberry Pi 5 — 2025 일반 금상](https://www.youtube.com/watch?v=ihgS2g6g0OQ)
- [OSSDoctor — 2025 학생 은상](https://www.youtube.com/watch?v=DX4OoAcOn24)
