# Origin and prior work

## 프로젝트 기원

RouteContract의 문제의식은 개인 포트폴리오 프로젝트 ShardLens에서 샤딩된 callback 경로의 회귀를 어떻게 막을지 설계하는 과정에서 나왔습니다.

ShardLens는 결제 provider 응답 유실, 멱등성, webhook, reconciliation과 샤딩 이후 신뢰성을 다루는 애플리케이션 실험 프로젝트입니다. RouteContract는 그중 라우팅 회귀 검증 문제만 독립적인 오픈소스 테스트 도구로 일반화합니다.

## 출품 전 존재한 작업

- ShardLens 문서에 Route Guard의 개념과 예시 manifest가 설계 수준으로 존재했습니다.
- 관련 Apache ShardingSphere 커널 수정 [PR #39112](https://github.com/apache/shardingsphere/pull/39112)는 GitHub 사용자 `Develop-KIM`이 열었고 2026-07-29에 병합되지 않은 채 닫혔습니다. 공개 review는 이 문제가 단일 route-engine 분기보다 넓은 계층 간 의미 계약을 필요로 한다고 지적했습니다. 현재 참가자 계정과 `Develop-KIM`의 동일 소유 여부는 확인되지 않았으므로, 이 문서는 해당 PR을 참가자의 기여로 주장하지 않습니다.
- 독립 RouteContract 저장소, 배포 패키지, operation-scoped collector, JUnit API, manifest diff, 검증 corpus는 존재하지 않았습니다.

## ShardLens와 RouteContract의 경계

| 구분 | 출품 전 ShardLens | 이 저장소의 RouteContract |
|---|---|---|
| 목적과 사용자 | 결제 provider, 멱등성, webhook, reconciliation과 샤딩 이후 신뢰성을 함께 다루는 포트폴리오 애플리케이션 | ShardingSphere-JDBC 5.5.3 사용자가 테스트에서 라우팅 회귀를 검토하도록 돕는 독립 라이브러리 |
| 당시 상태 | Route Guard와 versioned manifest의 설계 및 예시만 존재; 실행 collector·검증 라이브러리는 미구현 | `SQLExecutionHook` adapter, operation capture, assertion, manifest codec/verifier와 MySQL corpus를 새로 구현 |
| 증거 의미 | 의도한 `routeClass`, target shard 수, actual SQL 수를 표현하는 애플리케이션 설계 | hook이 보고한 data-source 이름과 물리 JDBC 실행 시도, rewritten-SQL fingerprint 및 callback outcome을 관측 |
| 자동 판정 범위 | ShardLens 도메인에서 원하는 정책을 표현하는 설계 | complete route plan, target shard 수, physical table 수 또는 commit 성공을 자동 추론하지 않음 |
| 코드 경계 | ShardLens 애플리케이션 소스 | ShardLens 애플리케이션 소스를 복사하지 않은 별도 패키지와 별도 검증 corpus |

따라서 정확한 기원 설명은 “ShardLens와 무관한 신규 아이디어”가 아니라, **ShardLens에서 문서로만 설계했던 라우팅 회귀 문제를 애플리케이션에 종속되지 않는 좁은 테스트 라이브러리로 새로 구현했다**입니다. 반대로 ShardLens의 설계 자체까지 RouteContract에서 처음 발명했다고 주장하지 않습니다.

## 이 저장소에서 새로 개발하는 범위

- ShardingSphere 5.5.3 `SQLExecutionHook` adapter
- trunk/worker 실행을 하나의 application operation으로 묶는 capture lifecycle
- parameter 원문을 저장하지 않는 `SQLExecutionHook`-reported physical JDBC execution-attempt model
- hook이 보고한 data-source 이름 및 관측 실행 시도 예산
- canonical manifest record/verify
- semantic diff와 CI 실패 리포트
- 실제 MySQL regression corpus
- 독립 설치 예제, CI, 릴리스, 라이선스 및 기여 문서

## 공개 개발 이력 원칙

독립 RouteContract 구현과 검증은 2026-08-11 로컬 작업으로 시작했습니다. 첫 공개는 그
시점까지의 작업을 하나의 정직한 bootstrap import로 남기며, 이미 끝난 코드를 과거
Issue·PR처럼 나누거나 날짜를 소급하지 않습니다. 공개 이후의 CI 안정화, 릴리스, 외부
설치 피드백과 수정은 실제 Issue → branch → PR → self-review → merge 이력으로 남깁니다.

RouteContract의 참가자·공개 저장소 계정은 `ym0506`으로 확정했습니다. `Develop-KIM`과
참가자의 소유 관계는 별도로 확인되지 않았으므로 PR #39112는 문제 조사에 참고한 외부
이력으로만 기술하고, 개인 기여·커뮤니티 활동·upstream 환류 점수의 근거로 사용하지
않습니다.

## 코드 재사용 원칙

ShardLens의 애플리케이션 코드는 이 저장소로 복사하지 않습니다. 외부 프로젝트 코드는 공식 dependency와 공개 SPI를 통해 사용하며, 소스 복사가 필요한 경우 해당 파일의 저작권·라이선스와 변경 내용을 별도로 표시합니다.

## 지원·수상 이력

정부·지자체·공공기관 예산에 따른 동일·유사 프로젝트 지원 또는 수상 여부는 제출 전에 참가자가 최종 확인하고, 해당하면 공식 중복수혜 확인서에 공개합니다.
