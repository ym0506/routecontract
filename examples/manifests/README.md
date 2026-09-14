# Canonical manifest example

이 디렉터리는 설명용으로 손으로 꾸민 fixture가 아닙니다. MySQL 통합 테스트가
ShardingSphere-JDBC 5.5.3과 digest로 고정한 MySQL 8.4.11 두 개에서 실제로 생성한 canonical
manifest와 verifier 출력을 저장합니다. 이름에 버전이 없는 기존 JSON 네 개는 공개 v0.1에서
생성된 schema 1 역사 증거이며 byte-for-byte로 보존합니다. `shardingsphere-5.5.3.schema2`가
포함된 JSON은 v0.2가 exact runtime identity를 기록해 새로 생성한 현재 증거입니다.

- `find-paid-orders-by-user.shardingsphere-5.5.3.schema2.approved.json`: `user_id = ?` 기준. 같은 비즈니스 행 1개를 반환하고
  관측된 물리 JDBC 실행 시도는 1개, data-source alias는 `orders-odd` 하나입니다.
- `find-paid-orders-by-user.shardingsphere-5.5.3.schema2.candidate.json`: 같은 값을 `BETWEEN ? AND ?`로 표현한 mutation.
  비즈니스 행은 그대로지만 관측된 실행 시도는 2개, alias는 `orders-even`과 `orders-odd`입니다.
- `find-paid-orders-by-user.expected-diff.txt`: strict policy가 출력하는 결정적 차단 코드입니다.
- `find-order-by-user-after-strategy-change.shardingsphere-5.5.3.schema2.approved.json`: database/table strategy가 모두 있는
  기준 설정입니다. 관측된 실행 시도와 alias는 각각 1개입니다.
- `find-order-by-user-after-strategy-change.shardingsphere-5.5.3.schema2.candidate.json`: table strategy만 제거한 설정입니다.
  같은 비즈니스 행과 동일한 `1 attempt / 1 alias` budget을 유지하지만, 관측된 SQL
  fingerprint와 parameter 구조가 달라집니다.
- `find-order-by-user-after-strategy-change.expected-diff.txt`: count budget만으로는 놓치는 위
  구조 변화를 strict manifest가 `RCM301`과 `RCM302`로 차단한 verifier 출력입니다.

alias mapping은 테스트에서 `ds_0 -> orders-even`, `ds_1 -> orders-odd`로 명시합니다. 실제
data-source 이름, 원문 SQL, parameter 값은 manifest에 저장되지 않습니다. SQL fingerprint는
익명화가 아니라 exact hook SQL String의 UTF-8 SHA-256이므로 내부 engineering metadata로
취급해야 합니다.

다음 명령은 실제 데이터베이스에서 두 manifest를 다시 만들고 committed bytes 및 diff와
정확히 같은지 검증합니다.

```bash
./scripts/run-demo.sh
```

위 명령은 예상된 위반까지 검증하므로 성공하면 종료 코드 `0`을 반환합니다. 실제 CI gate처럼
checked-in 승인본과 후보본을 파일에서 읽고 `ManifestAssertions.assertMatched(...)`가 build를
실패시키는 모습을 보려면 다음 명령을 실행합니다. Docker는 필요하지 않으며, `RCM201`과
`RCM202`를 출력한 뒤 의도한 종료 코드 `1`을 반환합니다. 이 intentional-red fixture는
이름에 버전이 없는 보존된 schema 1 pair를 읽어 이전 승인본 호환성도 함께 검증합니다.

```bash
./scripts/demo-manifest-ci-failure.sh
```

raw Gradle task도 동일합니다.

```bash
./gradlew --no-daemon --no-build-cache \
  :routecontract-shardingsphere-5.5:manifestCiFailureDemo --rerun-tasks
```

실제 MySQL 재생성부터 non-zero CI gate까지 한 명령으로 연결한 심사용 흐름은 다음과
같습니다. 성공 경로를 먼저 통과한 뒤 마지막 assertion에서 의도적으로 종료 코드 `1`을
반환합니다.

```bash
./scripts/demo-end-to-end-ci-failure.sh
```

이 intentional-failure fixture에는 전용 JUnit tag를 사용하므로 일반 `test`와 `check`에는
포함되지 않습니다.

candidate는 승인본이 아닙니다. 실패 예시와 검토 자료로만 version control에 둡니다.

같은 budget 안의 table-strategy-removal fixture는 다음 단일 실제-MySQL 테스트가 다시
생성하고, 저장된 두 JSON과 byte-for-byte로 비교하며, 예상 diff와 privacy 경계를 함께
검증합니다.

```bash
./gradlew --no-daemon --no-build-cache --max-workers=1 \
  :mysql-example:test \
  --tests 'io.github.ym0506.routecontract.example.ObservedExecutionRegressionCorpusMySqlTest.strategyRemovalProducesTwoDifferentObservableRegressionShapes' \
  --rerun-tasks
```
