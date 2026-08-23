# RouteContract 3분 시연 영상 스토리보드

상태: 2분 53초 촬영안. 안정 `v0.1.0`과 제출 revision을 동결하고, 외부 결과는 증거
cutoff의 실제 상태(`rc_only` 또는 `zero`)로 확정한 뒤 녹화한다. 별도 stable 전용
form/protocol이 없으므로 final-stable-result 분기는 fail-closed다.

핵심 문장:

> ShardingSphere-JDBC는 한 SQL을 여러 DB로 나눠 실행할 수 있다. 기능 결과가 같아도 hook이 보고한 실행 시도는 달라질 수 있으며, RouteContract는 새 기록을 사람이 승인한 기록과 비교해 의도하지 않은 차이를 CI 실패로 돌려준다.

## 영상 형식과 연속 실제 화면 규칙

최종 영상은 **참가자 음성·합성 음성·배경음악·효과음이 없는 무음 영상**이다. 아래 한국어
문구를 burned-in caption으로만 표시한다. 빈 audio track을 넣어 음성 gate를 우회하지 않고,
로컬 final MP4는 `ffprobe` 기준 audio stream이 정확히 0개여야 한다.

`0:00.000–2:53.000`의 모든 프레임은 final revision에서 직접 녹화한 실제 terminal·browser·source
화면이어야 한다.

- terminal에서는 실제 명령을 입력하는 순간, 실행 중 상태, 실제 출력과 종료 상태를 한 흐름으로
  보여 준다. `video-demo-session.sh`의 `mysql`·`fingerprint`·`ci`는 실제 하위 실행의
  machine-readable test/verifier 출력에서 검증한 `ROUTECONTRACT_*` marker와 RCM·
  `BUILD FAILED` 줄을 바꾸지 않고 추출해 보여 준다.
  고정 요약표로 재구성하거나 다른 화면에 다시 옮겨 적지 않는다.
- browser에서는 로그아웃한 공개 GitHub의 실제 URL, 페이지 chrome, 클릭과 짧은 scroll을 함께
  보여 준다. 공개 API 값을 슬라이드나 별도 문서에 옮겨 적지 않는다.
- source에서는 final revision의 tracked file path와 실제 줄을 보여 준다. 예제 코드를 발표용
  편집기나 메모 앱에 다시 입력하지 않는다.
- 제목·로고 화면, 슬라이드, 요약판, 모의 terminal, 좌우 합성 화면, 재작성한 결과 화면,
  정지 screenshot 삽입, 검은 전환 화면은 한 프레임도 쓰지 않는다. 구간 전환은 실제 화면에서
  다른 실제 화면으로 바로 자른다.
- browser와 source를 읽는 동안에도 cursor 이동, 줄 선택, click 또는 짧은 scroll 중 하나가
  보여야 한다. 읽기 시간을 위해 잠시 멈출 수 있지만 UI를 숨겨 발표 자료처럼 만들지 않는다.
- Gradle/Testcontainers 대기 구간만 8배속하고 그 실제 terminal 위에
  `실제 실행 · 대기 구간 8×`를 표시한다. 결과 줄, source, browser 증거는 배속하지 않는다.
- 화면에 없는 실행이나 결과를 자막으로 암시하지 않는다. 외부 결과 분기는 하나만 선택한다.

자막은 한 화면에 한 판단만 남긴 쉬운 한국어다. 제품명과 정확한 관측 경계에 필요한
`hook`, `JDBC`, `MySQL`, `CI`, `SQL` 외에는 내부 코드명과 영어 용어를 자막에서 빼고,
그 세부는 실제 화면에만 남긴다. 각 cue는 4~9초, cue 사이는 최소 0.5초, 공백을 제외한 표시
글자 수는 초당 8자 이하, 한 줄 34자 이하, 최대 두 줄이다.

`submission/video-caption-cues.json`이 cue 시각·문구·분기의 유일한 원본이다. 최종 SRT와
burned-in caption은 이 JSON에서 생성한다. 아래 표는 촬영자가 읽기 위한 generated/reference-only
mirror이며 JSON과 byte-for-byte 같아야 한다. 표를 직접 고쳐 JSON과 다른 두 번째 원본으로
만들지 않는다. 2:25–2:34에는 JSON에서 실제 cutoff 상태와 같은 분기 하나만 선택한다.

| 분기 | 시작 | 종료 | 1행 | 2행 |
|---|---:|---:|---|---|
| 공통 | 0:00.500 | 0:05.200 | RouteContract는 JDBC 실행 기록을 | 승인본과 비교합니다 |
| 공통 | 0:05.700 | 0:11.500 | ShardingSphere의 기능 결과는 같아도 | 관측된 실행 시도는 1회→2회 |
| 공통 | 0:12.500 | 0:19.000 | 방금 실행한 실제 MySQL 결과입니다 | 명령과 종료 상태를 함께 봅니다 |
| 공통 | 0:19.500 | 0:27.000 | 승인된 기록은 실행 한 번입니다 | 변경된 기록은 두 번입니다 |
| 공통 | 0:27.500 | 0:35.000 | 기능 결과는 그대로 한 행입니다 | 달라진 것은 내부 실행 모습입니다 |
| 공통 | 0:35.500 | 0:44.500 | 정한 한도를 넘자 두 위반을 냈습니다 | 자동 승인하지 않고 검토를 요구합니다 |
| 공통 | 0:46.500 | 0:52.500 | CI에 연결하면 exit 1 | 의도한 실패로 빌드를 멈춥니다 |
| 공통 | 0:53.000 | 0:59.500 | 승인 기록은 자동으로 바뀌지 않습니다 | 사람이 차이를 본 뒤에만 바꿉니다 |
| 공통 | 1:00.500 | 1:07.000 | 공개 배포 파일과 검사값을 확인합니다 | 빈 저장소에 직접 설치합니다 |
| 공통 | 1:07.500 | 1:14.500 | 설치한 파일로 실제 MySQL을 실행합니다 | 통과한 공개 기록을 직접 봅니다 |
| 공통 | 1:15.000 | 1:21.500 | 기존 기능 테스트를 그대로 감쌉니다 | 새 기록은 승인본과 비교됩니다 |
| 공통 | 1:22.500 | 1:28.500 | 실행 횟수는 그대로 한 번입니다 | 그래도 기록의 모양은 달라졌습니다 |
| 공통 | 1:29.000 | 1:35.000 | 입력값은 저장하지 않습니다 | 자료형 개수만 한 개에서 두 개로 바뀝니다 |
| 공통 | 1:35.500 | 1:39.500 | 횟수만 같아도 승인하지 않습니다 | SQL 뜻은 판단하지 않습니다 |
| 공통 | 1:40.500 | 1:47.000 | 실제 MySQL 여덟 사례를 스무 번씩 | 모두 같은 기록으로 되풀이했습니다 |
| 공통 | 1:47.500 | 1:54.500 | 동시에 실행한 20쌍은 섞이지 않았습니다 | 실제 호출의 겹침은 측정하지 않았습니다 |
| 공통 | 1:55.500 | 2:01.500 | 기록을 한 작업별로 묶고 | 사람이 승인한 기준과 비교합니다 |
| 공통 | 2:02.000 | 2:06.500 | 의도치 않은 차이는 CI 실패 | 승인 기준은 자동으로 바뀌지 않습니다 |
| 공통 | 2:07.500 | 2:15.000 | 제출 코드와 안정판이 같은 코드인지 | 공개 이력에서 직접 확인합니다 |
| 공통 | 2:15.500 | 2:24.500 | 코드 변경 검사와 main 검사 결과를 | 실제 공개 화면에서 확인합니다 |
| zero | 2:25.500 | 2:33.500 | 독립 검증은 공개 양식으로 받습니다 | 없는 결과는 만들지 않습니다 |
| rc_only | 2:25.500 | 2:33.500 | 정해진 양식의 RC 결과 접수는 1건 | 자기 확인 진술이며 안정판 검증은 아닙니다 |
| 공통 | 2:34.500 | 2:41.000 | 검증 범위는 5.5.3 동기 실행 | 성능·거래 완료를 판단하지 않습니다 |
| 공통 | 2:41.500 | 2:48.000 | 기능 결과가 같아도 hook 보고 실행 시도는 | 한 번에서 두 번으로 달라질 수 있습니다 |
| 공통 | 2:48.500 | 2:52.500 | 새 기록을 승인본과 비교해 | CI에서 의도치 않은 차이를 멈춥니다 |

발표 순서는 아래 공개 오픈소스 시연 영상의 결과 우선·baseline/candidate 비교·실행 뒤 증거
제시 방식을 비교 참고해 2026년 3분 제한에 맞게 재구성했다.

## 촬영 전 개인정보 안전 셸

실제 저장소 위치가 보이지 않도록 저장소 루트로 이동한 뒤 **녹화 전에** 설정한다.

```bash
export PS1='routecontract$ ' RPROMPT=''
printf '\033]0;RouteContract demo\007'
clear
exec zsh -df
```

- terminal 제목 표시줄은 자르거나 위 명령으로 고정한다. `pwd`, `env`, `docker ps`, IDE 전체
  화면은 녹화하지 않는다.
- 알림·메일·Git credential helper UI를 끄고, 1080p에서 110열 이상이 보이도록 글자 크기를
  맞춘다.
- 공개 browser 구간은 로그아웃 창에서 미리 연 repository 공개 URL만 사용한다. 개인 tab,
  bookmark bar, browser profile, extension icon은 숨긴다.
- `video-demo-session.sh`는 하위 명령의 stdout/stderr 전체를 화면에 흘리지 않는다. 이 영상에서
  쓰는 `mysql`·`fingerprint`·`ci` mode는 종료 코드와 고유한 marker를 먼저 검증한 뒤
  machine-readable test/verifier 출력에서 실제로 일치한 `ROUTECONTRACT_*` marker, RCM,
  `BUILD FAILED` 줄만 그대로 추출하고 `verified_child_exit`를 덧붙인다. 고정 요약문은 출력하지
  않는다. 로컬 경로, 동적 포트, 컨테이너 ID, 원문 SQL, 바인드 값은 촬영 화면에 나오지 않는다.
- `VIDEO_DEMO_ERROR`가 나오면 녹화를 중단한다. 원본 script는 녹화 밖에서만 실행해 원인을
  확인한다.
- `mysql`과 `fingerprint`는 실제 MySQL을 실행하고 `0`, `ci`는 검증된 intentional-red
  gate일 때만 `1`을 반환한다. wrapper 검증 자체가 깨지면 구별 가능한 `2`를 반환한다.

## 0:00–0:12 — 실제 MySQL 명령을 직접 입력하고 한 번만 실행

완료된 결과 화면이나 별도 도입 화면에서 시작하지 않는다. final revision의 실제 terminal에서
`./scripts/video-demo-session.sh mysql`을 직접 입력하고 Enter를 누르는 순간부터 시작한다. 실제
대기 구간만 8배속하고 그 terminal 위에 `실제 실행 · 대기 구간 8×`를 표시한다. 결과가 나오면
같은 terminal에서 marker와 `verified_child_exit 0`을 그대로 보여 준다. 이 marker는 실제 하위
실행의 machine-readable test 결과에서 추출한 줄이지, 촬영용 고정 요약이 아니다. 같은 명령을
영상에서 다시 실행하지 않는다.

실제 화면 흐름:

1. **실제 terminal 화면:** 0:00.000–0:05.000에 command를 직접 입력하고 Enter를 누른다.
   경로 일부를 실제로 입력한 뒤 Tab 자동완성을 한 번 보여 주며, 완성된 명령을 붙여넣지 않는다.
2. **같은 실제 terminal 화면:** 0:05.000–0:10.500에는 실제 대기만 8배속하며 실행 중인 화면을 남긴다.
3. **같은 실제 terminal 화면:** 0:10.500–0:12.000에는 아래 marker와 검증된 child exit가 나타나는
   순간을 자르지 않고 보여 준다.

```text
ROUTECONTRACT_MANIFEST_DEMO businessResult=UNCHANGED observedPhysicalAttempts=1->2 verificationStatus=POLICY_VIOLATION blockingCodes=[RCM201,RCM202] privacy=MINIMIZED
verified_child_exit     0
```

화면 자막: `submission/video-caption-cues.json`의 `0:00–0:12` 공통 cue 2개를 그대로 사용한다.

## 0:12–0:46 — 방금 실행한 결과에서 tracked manifest 비교로 이어가기

0:00에 시작한 같은 실제 실행의 marker와 검증한 exit를 먼저 읽는다. 바로 이어 final revision의 tracked approved/candidate JSON과 expected diff를
실제 source viewer에서 연다. 파일을 발표용으로
재작성하지 않고 repository-relative path와 line chrome을 남긴다.

실제 화면 흐름:

1. **0:12.000–0:19.000, 같은 실제 terminal 화면:**
   `ROUTECONTRACT_MANIFEST_DEMO` marker의 `businessResult=UNCHANGED`와
   `observedPhysicalAttempts=1->2`, 이어 `verified_child_exit 0`을 차례로 선택한다. 긴 marker는
   terminal의 실제 줄바꿈 그대로 보여 준다.
2. **0:19.000부터 바로 이어지는 실제 source 화면:**
   `examples/manifests/find-paid-orders-by-user.approved.json`에서
   `"observedPhysicalAttemptCount":1`을 찾는다.
3. **실제 source 화면:** 같은 위치의 `candidate.json`으로 tab을 바꾸고
   `"observedPhysicalAttemptCount":2`와 두 reviewed alias를 찾는다.
4. **실제 source 화면:** `find-paid-orders-by-user.expected-diff.txt`를 열어 실제
   `RCM201`·`RCM202` 두 줄을 선택한다.

한 번만 실행한 terminal에는 하위 실행에서 검증·추출한 다음 두 줄만 결과로 보인다.

```text
ROUTECONTRACT_MANIFEST_DEMO businessResult=UNCHANGED observedPhysicalAttempts=1->2 verificationStatus=POLICY_VIOLATION blockingCodes=[RCM201,RCM202] privacy=MINIMIZED
verified_child_exit     0
```

화면 자막: `submission/video-caption-cues.json`의 `0:12–0:45` 공통 cue 4개를 그대로 사용한다.

`1 -> 2`는 관측 계약의 승인 예산을 넘었다는 뜻일 뿐, 그 자체가 성능 결함이나 잘못된 SQL을
증명하지 않는다. `verified_child_exit 0`도 회귀가 없다는 뜻이 아니라, 실제 MySQL 결과와
committed manifest bytes가 예상한 위반 marker를 냈고 wrapper가 그 child exit를 검증했다는
뜻이다.

## 0:46–1:00 — 로컬 intentional-red 경로를 실제 terminal에서 실행

이 구간은 실제 GitHub Actions 실패 화면이 아니다. CI에 넣을 수 있는 같은 assertion이
non-zero를 반환하는지 local final revision에서 확인하는 intentional-red 실행이다.

실제 화면 흐름:

1. **실제 terminal 화면:** 0:46.000–0:51.000에 `./scripts/video-demo-session.sh ci`를 직접
   입력하고 Enter를 누른다. 경로 일부를 입력한 뒤 Tab 자동완성을 한 번 보여 주며 붙여넣지 않는다.
2. **같은 실제 terminal 화면:** 0:51.000–0:54.000에는 실제 대기만 8배속한다. 이어 실제
   하위 출력에서 허용된 전체 줄로 검증한 marker, RCM 두 줄, 엄격한 duration 형식의
   `BUILD FAILED in …` 줄과 `verified_child_exit 1`을 0:58.000까지 보여 준다.
3. **같은 실제 terminal 화면:** 0:58.000에 prompt가 돌아오면 `echo $?`를 입력하고 1:00.000까지
   실제 shell exit `1`을 확인한다. 이 구간에는 source나 다른 화면을 끼우지 않는다.

```text
    ROUTECONTRACT_FILE_CI_DEMO approvedAttempts=1 candidateAttempts=2 status=POLICY_VIOLATION blockingCodes=[RCM201,RCM202]
    - RCM201 BLOCKING ATTEMPT_BUDGET_EXCEEDED: maximum=1, observed=2
    - RCM202 BLOCKING DATA_SOURCE_BUDGET_EXCEEDED: maximum=1, observed=2
BUILD FAILED in <실제 Gradle 소요 시간>
verified_child_exit     1
```

위 블록은 재구성할 표가 아니라 실제 terminal에서 찾을 줄의 모양이다. marker·RCM은 허용한
전체 줄과 정확히 일치할 때만, `BUILD FAILED`는 제한된 duration-only 전체 줄과 일치할 때만
내보낸다. 앞뒤에 다른 문자열이 붙은 줄은 숨기고 wrapper error 2로 중단한다. 소요 시간은 해당
take의 실제 값이며, wrapper가 덧붙이는 값은 검증한 `verified_child_exit`뿐이다. tracked
approved/candidate JSON과 diff는 0:12–0:46에서 이미 보여 줬으므로 반복하지 않는다.

화면 자막: `submission/video-caption-cues.json`의 `0:46–1:00` 공통 cue 2개를 그대로 사용한다. 실제 화면과 자막은
`CI에 연결하면 exit 1`이라고 조건부로만 설명한다. 이 local task 자체가 required CI check이거나
실제 PR을 막았다고 말하지 않는다.

## 1:00–1:22 — 실제 공개 Release와 실제 사용 source

안정판 공개 검증이 모두 끝난 뒤에만 로그아웃 browser로 촬영한다. 별도 요약 화면을 만들지
않고 실제 GitHub Release, Actions run, tracked source 사이를 click한다.

실제 화면 흐름:

1. **실제 browser 화면:** repository의 `v0.1.0` Release page에서 tag와 asset 목록을 짧게
   scroll해 JAR·POM·SBOM·`SHA256SUMS`를 보여 준다.
2. **실제 browser 화면:** exact-tag `Release evidence` run을 click하고 Release-asset consumer
   step의 checksum/attestation 확인, 격리된 Maven repository 설치, MySQL PASS 줄을 찾는다.
3. **실제 source 화면:** public repository의 실제 Quick Start 또는 consumer test source를
   열어 공개 좌표와 `RouteContract.capture(...)`가 기존 assertion을 감싸는 줄을 선택한다.

로컬 `standalone` subcommand는 same-checkout publication을 쓰므로 stable Release 설치 증거로
보여 주지 않는다. 실제 source에는 다음 사용 모양이 있어야 하며 별도 화면에 재입력하지 않는다.

```java
RouteSnapshot snapshot = RouteContract.capture("orders.find", () -> {
    Order actual = repository.find(userId);
    assertEquals(expectedOrderId, actual.id());
});
RouteAssertions.assertThat(snapshot).hasExactlyObservedPhysicalAttempts(1);
```

화면 자막: `submission/video-caption-cues.json`의 `1:00–1:22` 공통 cue 3개를 그대로 사용한다. 관측 경계가 필요하면
실제 `README.md` source에서 `SQLExecutionHook`으로 보고된 물리 JDBC 실행 시도와
`complete route plan을 판정하지 않습니다`가 함께 있는 줄을 보여 준다. transaction commit
경계는 실제 `docs/architecture.md`의 event lifecycle 문장으로 확인하고 overlay로 다시 쓰지
않는다.

## 1:22–1:40 — 같은 횟수의 구조 변화도 실제 terminal에서 확인

실제 화면 흐름:

1. **실제 terminal 화면:** `./scripts/video-demo-session.sh fingerprint`를 직접 입력한다.
2. **같은 실제 terminal 화면:** 실제 대기만 8배속하고 machine-readable test 출력에서 그대로
   추출된 `ROUTECONTRACT_FINGERPRINT_DRIFT_DEMO` marker의
   `observedPhysicalAttempts=1->1`, `fingerprintMultiset=CHANGED`,
   `parameterTypeShape=[Long]->[Long,Long]`과 `verified_child_exit 0`을 차례로 선택한다.
3. **바로 이어지는 실제 source 화면:** final revision의
   `find-order-by-user-after-strategy-change.expected-diff.txt`를 열어 실제 RCM301·RCM302 줄을
   짧게 scroll한다.

```text
ROUTECONTRACT_FINGERPRINT_DRIFT_DEMO businessResult=UNCHANGED observedPhysicalAttempts=1->1 observedDataSourceAliases=[orders-odd]->[orders-odd] fingerprintMultiset=CHANGED parameterTypeShape=[Long]->[Long,Long] verificationStatus=DRIFT blockingCodes=[RCM301,RCM302] privacy=MINIMIZED
verified_child_exit     0
```

화면 자막: `submission/video-caption-cues.json`의 `1:22–1:40` 공통 cue 3개를 그대로 사용한다. 결과 줄과 source는
배속하지 않는다. RouteContract가 SQL 의미 동치를 판단한다고 말하지 않는다.

## 1:40–1:55 — 실제 공개 실행 로그에서 반복 결과 확인

텍스트를 옮겨 적지 않고 exact final revision의 공개 MySQL Actions log를 browser에서 연다.

실제 화면 흐름:

1. **실제 browser 화면:** 공개 Actions run의 실제 log search로
   `ROUTECONTRACT_CORPUS repetitions=20 cases=8 uniqueSignaturesPerCase=1` marker를 찾아 해당
   줄을 선택한다.
2. **같은 실제 browser 화면:** `simultaneousPairs=20`과 `mixedCaptures=0` marker로 이동한다.
3. **실제 source 화면:** `docs/architecture.md`의 동시성 limitation 줄을 열어 physical callback
   overlap을 force하거나 measure하지 않았다는 실제 문장을 보여 준다.

화면 자막: `submission/video-caption-cues.json`의 `1:40–1:55` 공통 cue 2개를 그대로 사용한다. 이 결과는 정상
반환하고 caller가 interrupt되지 않은 동기식 PreparedStatement 범위다. 동시 physical callback
또는 모든 thread safety를 증명했다고 말하지 않는다.

## 1:55–2:07 — 실제 Quick Start source에서 승인 흐름 확인

실제 화면 흐름:

1. **실제 source 화면:** public repository의 `README.md` Quick Start에서
   `RouteContract.capture(...)`로 한 application operation의 기록을 묶는 실제 줄을 선택한다.
2. **같은 실제 source 화면:** `writeCandidate(approvedPath, candidatePath, candidate)`와
   `ManifestAssertions.assertMatched(result)`로 이동해 candidate가 별도 파일로 생성되고 승인본과
   다른 기록이 assertion 실패가 되는 줄을 선택한다.
3. **같은 실제 source 화면:** candidate가 approved를 자동으로 덮어쓰지 않고 사람이 diff를 본
   뒤 교체한다는 바로 다음 실제 문장에서 끝낸다.

화면 자막: `submission/video-caption-cues.json`의 `1:55–2:07` 공통 cue 2개를 그대로 사용한다.
기존 도구와 prior-art 경계는 보고서와 `docs/competitive-analysis.md`에 남기고, 이 12초는 제품의
capture→candidate→사람 승인→CI 실패 흐름만 보여 준다.

## 2:07–2:25 — 실제 공개 GitHub 화면에서 안정판 증거 확인

다음 공통 증거가 실제로 공개된 뒤에만 녹화한다.

- 제출 revision full SHA를 가리키는 annotated stable `v0.1.0` tag의 peeled commit
- merge PR에서 ruleset-required `Java 17 / MySQL integration / SBOM`과
  `Dependency review` success
- 같은 final SHA의 main-push `Java 17 / MySQL integration / SBOM` success

실제 화면 흐름:

1. **실제 browser 화면:** 2:07.000–2:15.000 (8초 dwell). 미리 연 logged-out GitHub commit page에서
   제출 full SHA를 3초 이상 읽게 둔 뒤 annotated `v0.1.0` tag를 click한다. tag object와 peeled
   commit을 구분하고, peeled commit이 제출 full SHA와 같은 줄에서 3초 이상 머문다.
2. **실제 browser 화면:** 2:15.000–2:19.500 (4.5초 dwell). 미리 연 merge PR의 Checks tab으로 한 번
   전환한다. ruleset-required check 이름 네 개와 PASS 상태가 한 화면에 보이게 맞춰 두고,
   전환 뒤 남은 시간을 scroll 없이 머문다.
3. **실제 browser 화면:** 2:19.500–2:25.000 (5.5초 dwell). 미리 연 final main-push Actions run으로
   한 번 전환한다. 같은 final SHA와 `Java 17 / MySQL integration / SBOM` PASS가 한 화면에
   보이게 맞춰 두고 끝까지 머문다. `Dependency review`는 PR-only라 main push 증거로 세지 않는다.

exact-tag `Release evidence` run, consumer PASS와 immutable Release asset은 1:00–1:22의 실제
browser 구간에서 이미 확인했으므로 이 18초에 반복해 넘기지 않는다.

full SHA·tree·run ID·PR 번호·Release URL을 별도 요약 화면에 옮겨 적지 않는다. 실제 browser
주소와 GitHub UI에서 보여 주며, tag object SHA와 peeled commit SHA를 같은 값이라고 쓰지 않는다.

화면 자막: `submission/video-caption-cues.json`의 `2:07–2:25` 공통 cue 2개를 그대로 사용한다.

## 2:25–2:34 — 실제 공개 Issue 화면에서 외부 결과 확인

외부 결과는 증거 cutoff에 다음 두 상태 중 정확히 하나로 동결한다. 최종 보고서의 구조화
`external_evidence.branch`, package manifest의 `video.external_evidence_branch`, 실제 browser 화면·burned-in caption은 같은 분기를 사용한다:
`rc_only` ↔ `rc-only-result`, `zero` ↔ `0-result`.

- **rc-only-result 분기:** 선택한 분기의 결정적 공개 화면 하나인 실제 result Issue만 보여 준다. `정해진 양식의 RC 결과 접수 1건`, `참가자의 자기 확인 진술`, `stable 검증·adoption 아님`을 그 Issue의 실제 문구로 확인한다. activation·모집·프로토콜 링크는 보고서와 영상 설명에 남기고 이 9초에 다른 화면으로 전환하지 않는다. API·form 검사는 진술 형식과 public account association을 확인할 뿐 실제 사람·독립성을 자동 증명하지 않는다.
- **0-result 분기:** 선택한 분기의 결정적 공개 화면 하나인 실제 Discussion #28만 보여 준다. 공개 평가 절차와 `slot request` 경로를 실제 문구로 확인하고, 댓글 0건 상태를 숨기지 않는다. `stable 외부 검증 미확보`와 exact cutoff·결과 수는 보고서와 package evidence에 남기고 이 9초에 다른 화면으로 전환하지 않는다. 없는 결과를 만들거나 사용자 수·채택을 추정하지 않고, protocol URL만으로 모집했다고 주장하지 않는다.

실제 화면 흐름:

1. **실제 browser 화면:** 2:25.000에 선택한 분기의 결정적 공개 화면 하나를 이미 읽을 수 있는
   위치로 연다. URL과 GitHub UI를 남기고 필요한 공개 평가 절차 또는 RC/stable 경계 줄만 cursor로 선택한다.
   같은 화면에서 8초 동안 전환·scroll 없이 머문다.

다른 분기의 문구나 화면은 한 프레임도 넣지 않는다. 실제 사람·독립성·채택·endorsement를 추정하지 않는다. 실제 결함 수정 PR이나 RouteContract-specific upstream 질문은 실제로 게시한
경우에만 browser에서 연다. 게시하지 않았다면 browser 화면과 자막에서 제외한다.

화면 자막: `submission/video-caption-cues.json`의 `2:25–2:34`에서 실제 구조화 분기와 일치하는 cue 1개만 쓴다.

## 2:34–2:53 — 실제 지원 경계 뒤 핵심 효용으로 마무리

끝 화면도 제목판이나 요약판이 아니다. 실제 public source에서 사용 코드와 limitation을 차례로
찾고 2:53.000에 source 화면 위에서 끝낸다. 검은 frame이나 end slate를 붙이지 않는다.

실제 화면 흐름:

1. **실제 source 화면:** `docs/architecture.md`의 5.5.3 event lifecycle에서 정상 반환이
   transaction commit이나 business success를 증명하지 않는 실제 줄을 선택한다.
2. **실제 source 화면:** `README.md` 첫 설명의 기능 결과 동일·hook 보고 실행 1→2 실제 줄로
   이동한다.
3. **실제 source 화면:** Quick Start의 `ManifestAssertions.assertMatched(result)`와 candidate가
   approved를 자동으로 덮어쓰지 않는 실제 줄을 선택하고 2:53.000에 그 화면 위에서 끝낸다.

화면 자막: `submission/video-caption-cues.json`의 `2:34–2:53` 공통 cue 3개를 그대로 사용한다.

## 고정 자막·YouTube 문안

`submission/video-caption-cues.json`에서 SRT와 burned-in caption을 생성한다. 위 표는 같은
JSON에서 만든 사람용 mirror일 뿐 별도 원본이 아니다. 1920×1080 기준 자막은 48px 이상,
한 번에 두 줄 이하, 좌우 5%·아래 8% safe area 안에 두고 배경과 4.5:1 이상의 명도
대비를 확보한다. terminal 핵심 수치나 browser/source의 선택 줄을 자막으로 가리지 않는다.
YouTube 접근성 자막도 같은 문구·시각으로 올리되 영상에 이미 구워진 자막을 제거하거나 바꾸지
않는다.

- 제목: `RouteContract — ShardingSphere-JDBC 숨은 실행 변화를 CI에서 검사`
- 설명 첫 문단: `ShardingSphere-JDBC는 한 SQL을 여러 DB로 나눠 실행할 수 있습니다. 기능 테스트 결과가 같아도 hook이 보고한 물리 JDBC 실행 시도는 달라질 수 있습니다. RouteContract는 이를 사람이 승인한 기록과 비교하며, CI에 연결하면 승인되지 않은 차이를 테스트 실패로 돌려주는 Java 17 테스트 라이브러리입니다.`
- 설명 범위: `지원: ShardingSphere-JDBC 5.5.3 · 정상 반환/비-interrupt · 동기식 non-batch PreparedStatement · MySQL 8.4.11 fixture.`
- 설명 링크: `Repository: https://github.com/ym0506/routecontract`
- 설명 고지: `Apache ShardingSphere와 제휴·endorsement 관계가 없는 독립 third-party project입니다.`

## 최종 녹화 게이트

- [ ] 영상 속 revision과 제출 revision이 같다.
- [ ] 0:00.000부터 2:53.000까지 모든 frame이 실제 terminal·browser·source 중 하나이며 제목판,
  슬라이드, 요약판, 모의 terminal, 재작성 결과, screenshot 삽입, 검은 전환 frame이 없다.
- [ ] 각 terminal 명령의 입력, 실행 중 상태, 실제 결과와 exit를 같은 take에서 확인했다.
- [ ] actual browser 구간은 로그아웃 공개 페이지의 URL과 UI를 보이며, public 값을 별도 화면에
  옮겨 적지 않았다.
- [ ] actual source 구간은 final revision의 tracked path와 실제 줄을 보이며 예제를 다시
  입력하지 않았다.
- [ ] final main SHA의 Ubuntu root build와 exact-tag `Release evidence`의 Release-asset
  consumer가 성공했다. same-checkout standalone 결과를 stable 설치 증거로 쓰지 않는다.
- [ ] main ruleset이 `Java 17 / MySQL integration / SBOM`과 `Dependency review`를 required로
  지정하고, 전자 job이 contract assertion semantics를 test한다. intentional-red task 자체를
  required check이라고 말하지 않는다.
- [ ] local intentional-red 구간은 `CI에 연결하면 exit 1`이라고만 설명하며 실제 GitHub Actions
  failure나 실제 PR 차단이라고 부르지 않는다.
- [ ] baseline/candidate의 실제 `ROUTECONTRACT_MANIFEST_DEMO` marker와
  `verified_child_exit 0`을 재확인하고, 곧바로 tracked JSON·diff를 보여 줬다.
- [ ] intentional-red script가 실제 child output에서 추출한 marker·RCM201·RCM202·
  `BUILD FAILED`와 `verified_child_exit 1`을 출력하고 실제 shell exit도 1이다.
- [ ] fingerprint terminal과 actual source가 RCM301·RCM302,
  `parameterTypeShape=[Long]->[Long,Long]`, `privacy=MINIMIZED`를 보여 준다.
- [ ] 세 핵심 terminal 명령과 source/browser 화면에서 `/Users/`, `jdbc:`, `localhost:포트`,
  `127.0.0.1:포트`, `SELECT`, `t_order`, `ds_0`, `ds_1`, `user_id`, `row 201`, `= 3`,
  `BETWEEN 3`이 나오지 않는다.
- [ ] 제출 SHA와 같은 안정 `v0.1.0` Release assets, SBOM, checksum이 공개되어 있다.
- [ ] commit↔annotated tag, merge PR required checks, final main-push checks를 정한 8초·4.5초·
  5.5초 dwell로 분리해 실제 GitHub 화면에서 검증했다.
- [ ] 외부 결과 browser 구간은 exact-tag `rc-only-result` 또는 `0-result` 중 구조화 보고서와
  같은 하나만 표시하고, 선택한 분기의 결정적 공개 화면 하나에서 8초 동안 전환·scroll 없이
  머문다. RC-only는 안정판 검증·adoption이 아님과 안정판 외부 검증 미확보를 밝힌다.
  owner가 아닌 User account와 14개 self-attestation은 API로 확인하되, 실제
  비작성자·no-AI·no-same-checkout 여부는 participant 진술이며 자동 증명이라고 말하지 않는다.
  final-stable-result는 별도 stable 전용 form/protocol 전까지 사용하지 않는다.
- [ ] 영상 속 test 수가 final revision과 일치한다.
- [ ] 로컬 경로, token, Docker credential, 알림, 개인 mail, browser profile이 보이지 않는다.
- [ ] 최종 로컬 파일은 `ffprobe` 기준 1920×1080 이상이고 audio stream이 정확히 0개이며,
  허용된 일반 encoder/language/handler tag 외에 명시적으로 금지한 identity·location·device
  metadata tag가 없다.
- [ ] 1080p에서 terminal·browser·source 글자가 읽히며 자막이 잘리지 않는다.
- [ ] 모든 SRT와 burned-in caption이 `submission/video-caption-cues.json`과 byte-for-byte 같은
  문구·시각·분기이고, reference 표도 JSON mirror와 일치한다. 두 줄, 48px, safe area, 대비,
  읽기 밀도 기준을 지키며 실제 선택 줄을 가리지 않는다.
- [ ] 참가자 음성·합성 음성·배경음악·효과음·빈 audio track이 없고 화면에 없는 실행이나
  결과를 자막으로 암시하지 않는다.
- [ ] YouTube는 공개·non-live·연령 제한 없음 상태이고 다운로드 가능한 1080p 이상 format이
  처리됐으며, 재생시간이 2:50~2:55이고 로그인 없이 재생된다.
- [ ] 자동 gate가 판독하지 않는 실제 화면·burned-in caption 일치와 화면 가독성은 owner가
  checksummed local file과 로그아웃 public 1080p 영상을 처음부터 끝까지 직접 보며 확인했다.

## 금지 표현

- `RouteContract가 전체 route plan을 관측한다.`
- `실행 수가 곧 shard 또는 physical table 수다.`
- `CALLBACK_RETURNED가 commit 또는 business success를 뜻한다.`
- `동시 test로 모든 thread safety가 증명됐다.`
- `batch·reactive·Proxy·모든 ShardingSphere version을 지원한다.`
- `datasource-proxy는 물리 실행을 관측할 수 없다.`
- `manifest를 익명화했다.`
- `SBOM이 있으므로 security·license 문제가 없다.`
- `ShardingSphere가 RouteContract를 인정했다.`
- `세계 최초·유일·100% 검출.`
- local intentional-red 실행을 실제 CI run이나 실제 PR 차단이라고 말한다.
- 아직 공개되지 않은 Release, 사용자, CI 또는 upstream 반응을 완료형으로 말한다.

## 공개 오픈소스 시연 참고 링크

- [AutoRAG](https://www.youtube.com/watch?v=T-iOcb58-gI)
- [Hot Updater](https://www.youtube.com/watch?v=5FYX0P0Zn9I)
- [Zephyr Raspberry Pi 5](https://www.youtube.com/watch?v=ihgS2g6g0OQ)
- [OSSDoctor](https://www.youtube.com/watch?v=DX4OoAcOn24)
