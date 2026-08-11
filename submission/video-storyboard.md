# RouteContract 3분 시연 영상 스토리보드

상태: 2분 55초 최종 촬영안. 공개 저장소·CI·릴리스·외부 사용자 게이트를 통과한 뒤 녹화한다.

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

> 두 쿼리는 같은 행을 반환해 기능 테스트를 모두 통과합니다. 하지만 오른쪽의 관측된 물리 JDBC 실행 시도는 한 번에서 두 번으로 늘었습니다.

## 0:08–0:22 — 정확한 제품 정의

화면:

```text
ShardingSphere-JDBC 5.5.3 · Java 17 · MySQL 8.4.11
observed JDBC attempts ≠ complete route plan ≠ transaction commit
```

내레이션:

> RouteContract는 지원되는 ShardingSphere-JDBC 동기 operation에서 공식 SQLExecutionHook이 보고한 물리 JDBC 실행 시도를 계약으로 고정합니다. 전체 route plan이나 transaction commit을 관측한다고 주장하지 않습니다.

## 0:22–0:38 — 설치와 최소 API

화면은 배포 JAR 좌표와 아래 코드만 크게 보여 준다.

```java
RouteSnapshot snapshot = RouteContract.capture(
        "find-paid-orders-by-user",
        () -> assertEquals(1, repository.findPaidOrders(request.userId())));

RouteAssertions.assertThat(snapshot)
        .hasExactlyObservedPhysicalAttempts(1);

ManifestAssertions.assertMatched(result);
```

아래 구조는 작은 오버레이로 표시한다.

```text
capture → official SQLExecutionHook → minimized snapshot
        → canonical manifest → semantic diff → CI assertion
```

내레이션:

> JAR의 SPI는 자동 발견되고, 기존 비즈니스 assertion은 그대로 유지됩니다. capture가 operation 경계를 정하고 trunk와 worker callback을 모아 최소정보 manifest와 CI assertion으로 연결합니다.

## 0:38–1:08 — 실제 MySQL baseline

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
privacy                 MINIMIZED | screen output allowlisted
demo_exit               0
```

내레이션:

> digest로 고정한 MySQL 8.4.11 두 개와 정확히 ShardingSphere-JDBC 5.5.3을 실행합니다. 등호 조회는 주문 한 행을 반환하고, 한 data-source alias에서 한 번의 실행 시도가 관측됩니다. 이 결과가 검토된 승인 manifest입니다.

녹화 규칙:

- 명령 시작과 최종 marker는 정상 속도.
- 컨테이너 기동 대기만 8배속.
- 화면에 `실제 실행 · 대기 구간 8×` 표시.

## 1:08–1:40 — 같은 비즈니스 결과, candidate 2회

화면:

- 원문 SQL을 터미널에 출력하지 않는다. 편집 화면에서는 `equality predicate`와 `same-value range predicate`라는 설명용 라벨만 좌우 비교한다.
- 양쪽 모두 `returnedRows = 1`을 표시한다. 구체적인 조회 값과 row 식별자는 표시하지 않는다.
- candidate의 count와 alias diff만 확대한다.

```text
businessResult          UNCHANGED (one row in both captures)
observedAttempts        1 -> 2
observedDataSources     1 -> 2
blockingCodes           [RCM201,RCM202]
demo_exit               0
```

내레이션:

> 같은 값 범위 조건으로 바꿔도 같은 주문 한 행이 반환됩니다. 그러나 관측 시도와 data-source 수는 각각 한 개에서 두 개로 늘어 RCM201과 RCM202가 발생합니다. 예상된 회귀를 테스트가 정확히 검증했으므로 재현 명령 자체는 0으로 종료됩니다.

manifest 화면 콜아웃:

- `approved: 1 / [orders-odd]`
- `candidate: 2 / [orders-even, orders-odd]`
- `candidate는 approved를 자동으로 덮어쓰지 않음`
- `원문 SQL·바인드 값 미저장 · manifest에는 검토한 alias만 기록`
- `alias는 비민감 이름 사용 · minimized ≠ anonymized`

## 1:40–2:03 — 실제 non-zero CI gate

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

> 같은 두 파일을 실제 CI assertion에 넣으면 시도 예산과 data-source 예산 위반을 stable code로 출력하고 build가 1로 실패합니다. 이 intentional-red task는 정상 check와 분리되어 있습니다.

## 2:03–2:23 — count가 같아도 구조가 달라지면 차단

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
privacy                 MINIMIZED | screen output allowlisted
fingerprint_demo_exit   0
```

내레이션:

> 실행 수와 data source가 모두 같은 회귀도 있습니다. table strategy를 제거한 실험은 결과와 count가 같았지만 rewritten SQL fingerprint 구조가 달라졌고, strict contract가 RCM301과 RCM302로 차단했습니다. 따라서 단순 query counter에 머물지 않습니다.

## 2:23–2:39 — 재현성과 공정한 비교

한 장의 검증 카드만 보여 준다.

```text
real MySQL 8.4.11 · exact ShardingSphere-JDBC 5.5.3
8 cases × 20 = 160 captures · unique signature per case = 1
20 concurrent caller-operation pairs · mixed captures = 0
raw SQL / parameter values not retained
datasource-proxy can also observe 1→2 when wired per physical data source
```

내레이션:

> 8개 사례를 20회씩 실행한 160 captures에서 사례별 signature는 하나였고, 서로 다른 caller thread에서 함께 시작한 operation scope 20쌍에서 섞인 capture는 0이었습니다. 이는 physical callback overlap 자체를 강제한 결과는 아닙니다. datasource-proxy도 물리 data source를 감싸면 1대2를 관측할 수 있지만, RouteContract는 correlation부터 manifest, diff, assertion까지 패키지화합니다.

이 결과는 정상 반환하고 caller가 interrupt되지 않은 동기식 PreparedStatement 범위에만 적용된다. “동시 physical callback을 증명했다”라고 말하지 않는다.

## 2:39–2:51 — 공개 OSS 증거

다음이 실제로 공개된 뒤에만 이 구간을 녹화한다.

- 제출 revision의 Ubuntu CI 성공
- `v0.1.0-rc1` 또는 최종 release와 tag
- main/source/Javadoc JAR, POM, SBOM, SHA-256
- 비작성자 quick-start 결과 Issue
- 그 피드백으로 만든 실제 수정 PR
- 공개 이슈 #38456과의 문제 연관성. upstream이 RouteContract를 승인했다는 표현은 금지한다.

실행:

```bash
./scripts/video-demo-session.sh standalone
```

이 명령은 기존 `verify-standalone-consumer.sh`의 원본 출력에서 published JAR·SPI 자동 발견·실제 MySQL marker를 검증하되, 실제 data-source 이름은 화면에 다시 내보내지 않는다. 화면:

```text
[PUBLISHED-JAR CONSUMER]
artifact                 published-jar
spi                      auto-discovered
environment              MySQL 8.4.11 | ShardingSphere-JDBC 5.5.3
observedAttempts         1
observedDataSources      1 (name withheld from screen)
privacy                  screen output allowlisted
standalone_demo_exit     0
```

내레이션:

> 독립 consumer는 project dependency 없이 배포 JAR에서 SPI를 자동 발견해 실제 MySQL을 통과했습니다. 재현 가능한 CI, release asset, SBOM과 외부 quick-start 수정 이력은 공개 링크에서 확인할 수 있습니다.

Maven Central에 실제 게시하지 않았다면 Maven Central을 언급하지 않는다.

## 2:51–2:55 — 결론

화면:

```text
same result · hidden execution regression · blocking CI contract
CALLBACK_RETURNED ≠ JDBC completion ≠ COMMIT
ShardingSphere-JDBC 5.5.3 synchronous PreparedStatement only
```

내레이션:

> 같은 결과 뒤에 숨은 관측 실행 회귀를 RouteContract가 CI 계약으로 드러냅니다. required check로 연결하면 blocking diff를 merge 전에 실패시킬 수 있습니다.

## 최종 녹화 게이트

- [ ] 영상 속 revision과 제출 revision이 같다.
- [ ] Ubuntu 공개 CI에서 root build와 standalone consumer가 성공했다.
- [ ] baseline/candidate marker와 `demo_exit=0`을 재확인했다.
- [ ] intentional-red script가 RCM201·RCM202와 `ci_exit=1`을 출력한다.
- [ ] RCM301·RCM302 화면도 최종 revision의 실제 결과다.
- [ ] 세 촬영 명령의 stdout/stderr에서 `/Users/`, `jdbc:`, `localhost:포트`, `127.0.0.1:포트`, `SELECT`, `t_order`, `ds_0`, `ds_1`이 나오지 않는다.
- [ ] release assets, SBOM, checksum이 공개되어 있다.
- [ ] 실제 외부 사용자의 quick-start 결과가 공개되어 있다.
- [ ] 영상 속 테스트 수가 최종 revision과 일치한다.
- [ ] 로컬 경로, 토큰, Docker credential, 알림, 개인 메일이 보이지 않는다.
- [ ] 1080p에서 terminal 글자가 읽히며 자막이 잘리지 않는다.
- [ ] YouTube 재생시간이 2:50~2:55이고 로그인 없이 재생된다.

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
