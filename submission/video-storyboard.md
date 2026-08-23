# RouteContract 3분 시연 영상 스토리보드

상태: 2분 53초 촬영안. 안정 `v0.1.0`·제출 revision을 동결하고, 외부 결과는 증거 cutoff의 실제 상태(RC-only 또는 0-result)로 확정한 뒤 녹화한다. 별도 stable 전용 form/protocol이 없으므로 final-stable-result 분기는 fail-closed다.

핵심 문장:

> 기능 테스트 결과는 같아도 ShardingSphere가 보고한 JDBC 실행 구조는 달라질 수 있다. RouteContract는 승인되지 않은 변화를 CI에서 차단한다.

타이밍 규칙: 아래 내레이션은 문장 그대로 읽고 외부 결과 분기는 하나만 선택한다. 각 구간은
표시된 종료 시각 1초 전까지 말을 끝내 화면 전환 여백을 남긴다. 자연 속도로 세 번 재서 가장
긴 take가 구간을 넘으면 배속하지 말고 문장을 더 줄인다. 터미널 대기 구간 외 음성·화면을
가속하지 않고, 즉석 설명은 넣지 않는다.

고정 문구의 합성음 sanity check는 macOS Yuna 180 wpm과 `ffprobe`로 실측했다. 아래 값은
문구 길이의 정적 gate이며, 각 발화는 구간 길이보다 최소 1초 짧다. 테스트는 실제 스토리보드
문장의 UTF-8 SHA-256을 이 측정 fixture에 결속한다. 최종 녹화에서는 사람 목소리로 세 번
재어 같은 1초 전환 여백을 다시 확인한다.

| 발화 | Yuna 180 wpm | 구간 길이 | 1초 여백 후 상한 |
|---|---:|---:|---:|
| opening | 8.420초 | 12초 | 11초 |
| MySQL | 17.673초 | 34초 | 33초 |
| intentional-red CI | 10.938초 | 14초 | 13초 |
| install/workflow | 15.586초 | 22초 | 21초 |
| fingerprint | 15.624초 | 18초 | 17초 |
| reproducibility | 12.988초 | 15초 | 14초 |
| comparison | 10.100초 | 12초 | 11초 |
| public stable | 8.493초 | 18초 | 17초 |
| rc-only | 7.239초 | 9초 | 8초 |
| zero | 6.600초 | 9초 | 8초 |
| conclusion | 14.028초 | 19초 | 18초 |

발표 순서는 아래 공개 오픈소스 시연 영상의 결과 우선·baseline/candidate 비교·실행 뒤 증거 제시 방식을 비교 참고해 2026년 3분 제한에 맞게 재구성했다.

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

## 0:00–0:12 — 대상과 결과를 함께 보여 주는 훅

긴 로고나 제목 화면을 쓰지 않는다. 0:00–0:03에는 뒤에서 실제로 실행한 final-revision
terminal의 `businessResult UNCHANGED`, `observedAttempts 1 -> 2`, `RCM201 RCM202`만
flash-forward하고 `actual final-revision output`을 표시한다. 0:03–0:11에는 작은
`RouteContract` 오버레이와 함께 대상·첫 적용면을 먼저 고정하고 좌우 분할 화면을 보여 준다.

```text
ShardingSphere-JDBC 5.5.3 · 기존 Java 통합 테스트

기능 결과             같은 한 행 → 같은 한 행
hook 보고 JDBC 시도   1 → 2
RouteContract          RCM201·RCM202 · CI BLOCK

관측 경계: SQLExecutionHook-reported physical JDBC execution attempts
```

내레이션:

> 같은 행을 반환해 기능 테스트는 통과했지만, ShardingSphere가 보고한 JDBC 실행 시도는 1회에서 2회로 늘었습니다.

## 0:12–0:46 — 실제 MySQL baseline과 candidate

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
RCM201                  ATTEMPT_BUDGET_EXCEEDED: maximum=1, observed=2
RCM202                  DATA_SOURCE_BUDGET_EXCEEDED: maximum=1, observed=2
privacy                 raw child output withheld | raw SQL/binds not retained
aliases                 reviewed aliases remain | minimized != anonymized
demoMeaning             expected violation verified
demo_exit               0
```

내레이션:

> 최종 revision의 실제 MySQL 테스트입니다. 두 경우 모두 같은 한 행을 반환했습니다. 하지만 SQLExecutionHook이 보고한 물리 JDBC 실행 시도와 검토한 data-source alias는 1개에서 2개로 늘어 RCM201과 RCM202가 발생했습니다.

녹화 규칙:

- 첫 3초 hook에 쓴 결과도 이 실제 final-revision 실행에서 잘라 온다. 재작성한 terminal 카드를 만들지 않는다.
- 명령 시작과 최종 marker는 정상 속도.
- Gradle/Testcontainers 대기 구간만 8배속.
- 화면에 `실제 실행 · 대기 구간 8×` 표시.
- `RCM201`과 `RCM202`의 code·reason·`maximum=1, observed=2`가 한 화면에 모두 보이게
  확대한다. 좌우 빈 여백만 crop하고 코드나 수치는 자르지 않는다.

동일한 결과와 candidate diff는 한 흐름 안에서 확대한다. 원문 SQL 대신 `equality predicate`와 `same-value range predicate`라는 설명용 라벨만 사용하고, 구체적인 조회 값과 row 식별자는 표시하지 않는다. 재현 명령의 `demo_exit=0`은 회귀가 없다는 뜻이 아니라 예상한 회귀와 manifest bytes를 테스트가 정확히 검증했다는 뜻이다.

manifest 화면 콜아웃:

- `approved: 1 / [orders-odd]`
- `candidate: 2 / [orders-even, orders-odd]`
- `candidate는 approved를 자동으로 덮어쓰지 않음`
- `원문 SQL·바인드 값 미저장 · manifest에는 검토한 alias만 기록`
- `alias는 비민감 이름 사용 · minimized ≠ anonymized`

## 0:46–1:00 — 실제 non-zero CI gate

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

> 변경안이 승인 기준을 넘어서 CI gate가 exit 1로 멈춥니다. 기준 파일은 자동 갱신되지 않아, 의도한 변경만 사람이 diff를 검토해 승인합니다.

화면 콜아웃: `도구 고장 아님 · 예상한 위반을 검증한 실패` · `approved 자동 갱신 없음`

## 1:00–1:22 — 설치와 검증 workflow

화면은 실제 stable 공개 검증 뒤 **고정 화면 세 장만** 순서대로 보여 준다. 각 화면은 다음
화면으로 넘어가기 전에 핵심 한 줄을 읽을 시간을 둔다.

1. Release 검증 카드

```text
GitHub Release assets → SHA-256 / attestation verification → isolated Maven repository
ROUTECONTRACT_RELEASE_ASSET_CONSUMER · result=VERIFIED_MYSQL
```

공개 `Release evidence` run의 provenance가 보이는 고정 cut에서 다음 marker를 보여 준다. 로컬
`standalone` subcommand는 같은-checkout publication을 사용하므로 stable Release 설치 증거로
사용하지 않는다.

2. 설치 좌표 카드

```gradle
testImplementation("io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.0")
```

3. 기존 테스트에 붙이는 실제 API 카드

```java
RouteSnapshot snapshot = RouteContract.capture("orders.find", () -> {
    Order actual = repository.find(userId);
    assertEquals(expectedOrderId, actual.id()); // 기존 기능 assertion
});
RouteAssertions.assertThat(snapshot).hasExactlyObservedPhysicalAttempts(1);
```

화면 아래에는 `candidate → 사람이 검토한 approved diff → CI`와 `approved 자동 갱신 없음`을
붙인다. `capture(operationId)`가 기존 business assertion을 감싸고, candidate가 approved를
자동 갱신하지 않는다는 두 사실이 한 화면에서 읽혀야 한다.

화면 하단 범위:

```text
ShardingSphere-JDBC 5.5.3 · Java 17
SQLExecutionHook-reported physical JDBC execution attempts
≠ complete route plan ≠ transaction commit
```

내레이션:

> 프로젝트가 공개 안정판 자산의 checksum을 확인해 빈 Maven 저장소에 설치했고, 소비자 테스트가 실제 MySQL에서 통과했습니다. 사용자는 기존 테스트를 capture로 감싸 이번 관측값을 승인본과 CI에서 비교합니다.

## 1:22–1:40 — count가 같아도 구조가 달라지면 차단

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
parameterTypeShape      1xLong -> 2xLong (values not retained)
verificationStatus      DRIFT
blockingCodes           [RCM301,RCM302]
privacy                 raw child output withheld | raw SQL/binds not retained
aliases                 reviewed aliases remain | minimized != anonymized
fingerprint_demo_exit   0
```

내레이션:

> 실행 수와 검토한 data-source alias가 모두 1이어도 구조는 달라집니다. strict 정책에서는 fingerprint와 parameter type shape 변화를 RCM301·RCM302로 차단합니다. SQL 의미 동치는 판정하지 않습니다.

녹화 규칙:

- 명령 입력·실행 시작과 `[SAME-BUDGET FINGERPRINT DRIFT]`, `fingerprint_demo_exit 0` 최종
  marker는 정상 속도로 보여 준다.
- Gradle/Testcontainers 대기 구간만 8배속하고, 그 구간에만
  `실제 실행 · 대기 구간 8×` 오버레이를 표시한다.
- 결과 행과 RCM301·RCM302를 읽는 구간은 배속하지 않는다.

## 1:40–1:55 — 재현성과 지원 경계

한 장의 검증 카드만 보여 준다.

```text
real MySQL 8.4.11 · exact ShardingSphere-JDBC 5.5.3
8 cases × 20 = 160 captures · unique signature per case = 1
20 concurrent caller-operation pairs · mixed captures = 0
raw SQL / parameter values not retained
```

내레이션:

> 실제 MySQL 8개 사례를 20회씩 반복해 사례별 구조 signature가 하나였습니다. 동시에 연 caller-operation 20쌍도 섞이지 않았지만, physical callback 중첩은 측정하지 않았습니다.

이 결과는 정상 반환하고 caller가 interrupt되지 않은 동기식 PreparedStatement 범위에만 적용된다. “동시 physical callback을 증명했다”라고 말하지 않는다.

## 1:55–2:07 — 공정한 기존 도구 비교

화면:

```text
datasource-proxy: per-physical-data-source wiring can also observe 1 -> 2
RouteContract: operation correlation -> manifest -> reviewed diff -> CI assertion
```

내레이션:

> datasource-proxy도 물리 data source마다 연결하면 같은 변화를 봅니다. RouteContract는 이를 operation별 승인과 CI 검사로 묶습니다.

## 2:07–2:25 — exact public stable OSS 증거

화면 상단 라벨: `프로젝트 자체 공개 검증`

다음 공통 증거가 실제로 공개된 뒤에만 녹화한다.

- 제출 revision full SHA와 같은 annotated stable `v0.1.0` tag
- 그 final SHA의 main-push `Java 17 / MySQL integration / SBOM` success
- merge PR에서 ruleset-required `Java 17 / MySQL integration / SBOM`과 `Dependency review` success
- PR head와 final main의 exact tree 일치
- exact tag SHA의 successful `Release evidence` run
- immutable Release의 JAR·sources·Javadoc·POM·SBOM·`SHA256SUMS`
- 빈 Maven 저장소에서 Release 자산을 검증한 consumer 결과

화면은 브라우저를 실시간 탐색하거나 스크롤하지 않고, 최종 manifest와 공개 API에서 옮긴
값을 다시 대조한 **고정 화면 한 장**만 보여 준다. full SHA·tree·run ID·PR 번호·정확한
URL은 작은 근거 줄에 남기고, 심사위원이 읽어야 할 네 결과만 크게 표시한다.

tag object SHA와 commit SHA가 같은 것처럼 쓰지 않는다. full SHA·tree·run ID·PR 번호·정확한
URL은 카드의 작은 근거 줄에 남기되, 핵심 결과는 크게 표시한다.

```text
PUBLIC STABLE v0.1.0 — 프로젝트 자체 공개 검증

IDENTITY  제출 revision = main = peeled v0.1.0 commit
CHECKS    PR required checks · main CI · release evidence  PASS
ASSETS    checksum · POM · SBOM 검증
CONSUMER  Release 자산 설치 후 MySQL  PASS

main push            Java 17 / MySQL integration / SBOM  PASS
main push            Dependency review  SKIPPED (PR-only)
PR <number>           Java/MySQL/SBOM PASS | Dependency review PASS
PR tree               <tree>
final main tree       <same tree>
근거: <full SHA> · <tree> · <run ID> · <PR> · <Release URL>
```

내레이션:

> 제출 revision과 stable tag, main CI, 필수 PR 검사, Release 자산을 같은 revision으로 공개 검증했습니다.

## 2:25–2:34 — cutoff 외부 결과 현황과 커뮤니티 기록

화면 상단 라벨: `외부 결과 현황 — 프로젝트 자체 검증과 별도`

외부 결과는 증거 cutoff에 다음 두 상태 중 정확히 하나로 동결한다. 최종 보고서의
구조화 `external_evidence.branch`, package manifest의 `video.external_evidence_branch`,
실제 영상 카드·내레이션은 같은 분기를 사용한다:
`rc_only` ↔ `rc-only-result`, `zero` ↔ `0-result`.

- **rc-only-result 분기:** `exact RC 공개 모집`, `형식에 맞게 공개 제출된 RC 설치 결과 1건`, `stable 검증·adoption 아님`, `결과·활성화·모집·프로토콜 링크`의 네 줄만 표시한다.
- **0-result 분기:** `형식에 맞게 공개 제출된 설치 결과 0건`, `stable 외부 검증 미확보`, `활성화·모집·프로토콜 링크`, `0건 ≠ 사용자 수·채택률·가치 0`의 네 줄만 표시한다. protocol URL만으로 모집했다고 주장하지 않는다.

14개 체크와 API 편집 필드 같은 내부 검증 세부는 보고서·영상 본문에 나열하지 않는다. 한 장의
카드를 약 6초간 고정하고 결과 수와 RC/stable 경계만 말한다. 남은 약 2초는 결론 화면
전환에 쓴다. 실제 사람·독립성·채택·endorsement를 추정하지 않는다.

실제 결함이 발견된 경우에만 그 결함을 수정한 PR을 보여 준다. RouteContract-specific upstream
질문은 실제로 게시한 경우에만 질문과 현재 상태를 보여 준다. 게시하지 않았다면 카드와 내레이션에서 제외한다.

내레이션:

- rc-only-result 분기: “cutoff까지 형식에 맞게 제출된 RC 설치 결과는 1건입니다. stable 검증이나 채택은 아닙니다.”
- 0-result 분기: “cutoff까지 형식에 맞게 제출된 설치 결과는 0건이며, stable 외부 검증도 없습니다.”

## 2:34–2:53 — 결론

화면:

```text
Target: Java teams using/evaluating ShardingSphere-JDBC 5.5.3
First surface: existing integration tests
same result · hidden execution regression · blocking CI contract
CALLBACK_RETURNED ≠ JDBC completion ≠ COMMIT
normal return · caller not interrupted at close
synchronous non-batch PreparedStatement only
```

내레이션:

> 기존 기능 테스트가 통과해도 실행 구조는 달라질 수 있습니다. ShardingSphere-JDBC 5.5.3 팀은 RouteContract로 그 변화를 사람이 승인한 기준과 비교해 merge 전에 검토하거나 차단할 수 있습니다.

## 고정 자막·YouTube 문안

모든 내레이션은 의미를 줄이지 않은 한국어 자막으로 함께 넣는다. 1920×1080 기준 자막은
48px 이상, 한 번에 두 줄 이하, 좌우 5%·아래 8% safe area 안에 두고 배경과 4.5:1 이상의
명도 대비를 확보한다. terminal 핵심 수치·RCM code를 자막으로 가리지 않는다.

- 제목: `RouteContract — ShardingSphere-JDBC 숨은 실행 회귀를 CI에서 차단`
- 설명 첫 문단: `기능 테스트 결과가 같아도 ShardingSphere가 보고한 JDBC 실행 시도는 달라질 수 있습니다. RouteContract는 이를 사람이 승인한 기준과 비교해 CI에서 검토하거나 차단하는 Java 17 테스트 라이브러리입니다.`
- 설명 범위: `지원: ShardingSphere-JDBC 5.5.3 · 정상 반환/비-interrupt · 동기식 non-batch PreparedStatement · MySQL 8.4.11 fixture.`
- 설명 링크: `Repository: https://github.com/ym0506/routecontract`
- 설명 고지: `Apache ShardingSphere와 제휴·endorsement 관계가 없는 독립 third-party project입니다.`

## 최종 녹화 게이트

- [ ] 영상 속 revision과 제출 revision이 같다.
- [ ] final main SHA의 Ubuntu root build와 exact-tag `Release evidence`의 Release-asset consumer가 성공했다. 같은-checkout standalone 결과를 stable 설치 증거로 쓰지 않는다.
- [ ] main ruleset이 `Java 17 / MySQL integration / SBOM`과 `Dependency review`를 required로 지정하고, 전자 job이 contract assertion semantics를 테스트한다. intentional-red task 자체를 required check라고 말하지 않는다.
- [ ] baseline/candidate marker와 `demo_exit=0`을 재확인했다.
- [ ] `demo_exit=0` 옆에 `expected violation verified`가 표시된다.
- [ ] intentional-red script가 RCM201·RCM202와 `ci_exit=1`을 출력한다.
- [ ] RCM301·RCM302 화면도 최종 revision의 실제 결과다.
- [ ] fingerprint 화면에 `parameterTypeShape 1xLong -> 2xLong`과 `values not retained`가 표시된다.
- [ ] 세 핵심 촬영 명령과 삽입 그림의 화면 출력에서 `/Users/`, `jdbc:`, `localhost:포트`, `127.0.0.1:포트`, `SELECT`, `t_order`, `ds_0`, `ds_1`, `user_id`, `row 201`, `= 3`, `BETWEEN 3`이 나오지 않는다.
- [ ] 제출 SHA와 같은 안정 `v0.1.0` release assets, SBOM, checksum이 공개되어 있다.
- [ ] final main SHA의 main-push check와 merge PR의 required checks를 분리하고, PR/final tree 일치를 검증했다.
- [ ] 외부 결과 카드는 exact-tag RC-only-result 또는 0-result 중 구조화 보고서와 같은 하나만 표시한다. RC-only는 최종 안정 검증·adoption이 아님과 최종 안정 외부 검증 미확보를 모두 밝힌다. owner가 아닌 User 계정과 14개 self-attestation은 API로 확인하되, 실제 비작성자·no-AI·no-same-checkout 여부는 participant 진술이며 자동 증명이라고 말하지 않는다. final-stable-result는 별도 stable 전용 form/protocol 전까지 사용하지 않는다.
- [ ] 영상 속 테스트 수가 최종 revision과 일치한다.
- [ ] 로컬 경로, 토큰, Docker credential, 알림, 개인 메일이 보이지 않는다.
- [ ] 최종 로컬 파일은 `ffprobe` 기준 1920×1080 이상이고 audio stream이 1개 이상이며, 허용된 일반 encoder/language/handler tag 외에 명시적으로 금지한 identity·location·device metadata tag가 없다.
- [ ] 1080p에서 terminal 글자가 읽히며 자막이 잘리지 않는다.
- [ ] 모든 내레이션 자막이 두 줄·48px·safe area·대비 기준을 지키고 terminal 핵심 수치를 가리지 않는다.
- [ ] 외부 결과 분기 하나만 포함해 내레이션을 세 번 실측했고, 가장 긴 take도 각 구간 종료 1초 전까지 끝났다. 시간을 맞추기 위한 음성 배속이나 즉석 문장을 넣지 않았다.
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

## 공개 오픈소스 시연 참고 링크

- [AutoRAG](https://www.youtube.com/watch?v=T-iOcb58-gI)
- [Hot Updater](https://www.youtube.com/watch?v=5FYX0P0Zn9I)
- [Zephyr Raspberry Pi 5](https://www.youtube.com/watch?v=ihgS2g6g0OQ)
- [OSSDoctor](https://www.youtube.com/watch?v=DX4OoAcOn24)
