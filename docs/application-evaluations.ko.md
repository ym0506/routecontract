# 애플리케이션 코드로 확인한 실행 변화

[English](application-evaluations.md) · [공개 버전 체험](first-project.ko.md#try-in-your-browser)

**업무 테스트가 통과해도 어떤 실행 변화가 남을까요?** 공개 프로젝트 세 곳의 코드와
RouteContract 0.1.3으로 이 질문을 확인했습니다. 모두 RouteContract 유지관리자가 합성
데이터로 준비하고 실행한 실험입니다. 고객 사례·상대 유지관리자의 추천·독립적인 도입 실적은 아닙니다.

| 확인할 질문 | 실험 | 관측 결과 |
| --- | --- | --- |
| 결과와 횟수가 같은데 실행 대상이 바뀔 수 있나요? | [Egon-COLA 테넌트 라우팅](#횟수는-같지만-데이터-소스가-바뀌는-경우) | 모든 경우 실행 1회·별칭 1개지만, 관측 별칭이 달라집니다. |
| 같은 주문을 반환하는 두 mapper 조회에 다른 예산이 필요한가요? | [SCG 주문 조회](#같은-주문을-다른-조건으로-조회하는-경우) | 실행·별칭이 각각 1/1과 8/8입니다. |
| 기존 애플리케이션 테스트에 관측을 추가할 수 있나요? | [CityPulse 주문 조회](#기존-테스트에-관측을-추가하는-경우) | 수정한 통합 테스트 한 개가 통과하고, 마지막 조회에서 실행 2회·별칭 1개를 관측했습니다. |

여기서 **실행 시도**는 ShardingSphere의 `SQLExecutionHook`이 보고한 물리 JDBC 실행
시도입니다. 별칭은 관측된 데이터 소스 이름입니다. 물리 테이블 수·네트워크 왕복 횟수·
트랜잭션 커밋 횟수·지연시간을 측정한 값은 아닙니다.

공개 버전의 지원 범위는 **Java 17, 정확히 ShardingSphere-JDBC 5.5.3, 동기식·비배치
`PreparedStatement` 작업**입니다. 아래 Java 21·PostgreSQL 결과는 명시한 코드 경로와
의존성 조합의 실험 결과이며, 해당 환경 전반의 지원을 뜻하지 않습니다.

## 횟수는 같지만 데이터 소스가 바뀌는 경우

**Egon-COLA · `verified - ShardingSphere-JDBC 5.5.3` · PostgreSQL 합성 실험**

[고정한 Light 템플릿](https://github.com/AllenDEricDAlexander/Egon-COLA/tree/61c9fbc2bd38f199d7355662a75d2113f02c6586/egon-cola-archetypes/source-projects/egon-cola-source-light)은
테넌트 슬롯에 데이터베이스와 테이블 노드를 배정합니다. 실험에서는 라우팅 클래스 두 개와
규칙 템플릿을 수정 없이 사용했습니다. 질의·최소 스키마·데이터는 실험용으로 작성했습니다.
업무 결과만으로 실행 위치를 구분할 수 없도록, 두 목적지에 같은 행을 의도적으로 넣었습니다.

| 설정 | 업무 행 | 실행 시도 / 별칭 수 | 관측 별칭 | 참조 관측과 비교 |
| --- | --- | --- | --- | --- |
| 참조 설정 | 전체 행 동일 | 1 / 1 | `synthetic-left` | 참조 관측 |
| 설정 항목 순서만 변경 | 전체 행 동일 | 1 / 1 | `synthetic-left` | `MATCH` |
| DB 배정 교환, 테이블 suffix 유지 | 전체 행 동일 | 1 / 1 | `synthetic-right` | `DRIFT` |
| 참조 설정으로 복구 | 전체 행 동일 | 1 / 1 | `synthetic-left` | `MATCH` |

SQL fingerprint와 파라미터 타입 구조도 같습니다. 모든 capture는 COMPLETE이며 callback
실패·unknown은 없습니다. 횟수만 검사하면 네 경우 모두 통과합니다. 기대 데이터 소스
assertion은 DB 배정이 바뀐 경우를 거부하고, 구조 비교는 `RCM304`(관측 데이터 소스 집합
변경), `RCM301`·`RCM302`(데이터 소스가 포함된 실행 signature의 제거·추가)를 보고합니다.
signature 변경이 SQL fingerprint 변경을 뜻하는 것은 아닙니다.

항목 순서 변경과 원복은 비교가 의도대로 작동하는지 확인하는 대조군입니다. Egon-COLA의
결함·실제 마이그레이션·테넌트 정보 유출을 발견했다는 뜻은 아닙니다. 전체 애플리케이션이나
원래 서비스·mapper는 실행하지 않았고 애플리케이션 baseline을 승인하지 않았습니다.
진단 리포트의 “Baseline” 열은 합성 참조 관측이며, 상대 유지관리자의 승인을 뜻하지 않습니다.

**확인·재현:** [고정된 테스트·준비 도구·실행 근거](https://gist.github.com/ym0506/392bd5f05419225876c93f1a6c98c578/538e306ea8027836598de432510f2a8002c3f499#file-readme-md)
· [실제 DRIFT 리포트](https://gist.github.com/ym0506/392bd5f05419225876c93f1a6c98c578/538e306ea8027836598de432510f2a8002c3f499#file-moved-review-md).
준비 도구는 고정한 원본 세 파일을 가져와 해시를 확인한 뒤 새 디렉터리를 만듭니다.
묶음에 원본 소스를 재배포하지 않으며, 원본 파일에는 해당 프로젝트의 라이선스가 적용됩니다.

환경은 Homebrew OpenJDK 21.0.11, Maven 3.9.14, ShardingSphere-JDBC 5.5.3,
pgJDBC 42.7.13, PostgreSQL 17.11, macOS/aarch64 호스트와 digest를 고정한 컨테이너입니다.
JUnit 테스트 한 개가 네 설정을 검사합니다. 최초 실행과 전달용 준비 도구를 통한 실행은
각각 빈 Maven 캐시에서 시작했고 모두 실패·오류·skip 없이 통과했습니다. 관측·리포트
산출물 12개는 두 실행에서 바이트 단위로 같았습니다. 같은 작성자가 한 테스트를 두 번
실행한 것이며, 독립 사용자 두 명의 검증으로 세지 않습니다.

## 같은 주문을 다른 조건으로 조회하는 경우

**SCG · `verified - MySQL` · `verified - ShardingSphere-JDBC 5.5.3`**

[고정한 SCG 프로젝트](https://github.com/leoli5695/scg-dynamic-admin/tree/a6ecc490160707722b7f4478354901318f809ea3)의
`selectByUserAndSeckill`과 `selectByOrderNo`를 비교했습니다. mapper·엔티티·ShardingSphere
설정 세 파일은 그대로 두고, 별도 실험 POM과 합성 스키마에서 실제 MyBatis 조회를 실행했습니다.
1차 세션 캐시가 실제 JDBC 조회를 대신하지 않도록 각 조회에 새 세션을 사용했습니다.

| 조회 조건 | 업무 결과 | 관측 실행 시도 | 관측 별칭 |
| --- | --- | --- | --- |
| 사용자와 행사 | 전체 주문 엔티티 동일 | 1 | 1 |
| 주문 번호 | 전체 주문 엔티티 동일 | 8 | 8 |

두 capture 모두 COMPLETE이며 callback 실패·unknown은 없습니다. 단일 실행이나 단일
데이터 소스 예산을 적용하면 주문 번호 조회는 거부됩니다. 이 조회에 그 예산이 적절한지는
애플리케이션 담당자가 작업의 요구사항으로 판단해야 합니다.

**기존 조회 두 개의 차이**이며, 특정 커밋이 회귀를 일으켰다는 관측은 아닙니다.
MySQL 서버 한 개에 스키마 8개와 스키마마다 주문 테이블 16개를 구성했습니다.
실행 8회를 서버 8대나 8배의 성능 저하로 해석하지 않습니다. 전체 Spring 애플리케이션과
원래 의존성 그래프를 빌드하거나 기동하지 않았습니다.

**확인·재현:** [고정된 테스트·로컬 checkout 준비 도구·실행 근거](https://gist.github.com/ym0506/d1a9b9c5612ab2bf906fcf386e1381b0/22006f31050ee84ef717c1b013550d84d2ab0676#file-readme-md).
준비 도구에는 대상 프로젝트의 로컬 checkout이 필요합니다. Java 세 파일과 라이선스를
검증하고 원본 checkout을 유지합니다. 묶음에는 SCG 원본 소스를 재배포하지 않으며,
평가·배포에는 해당 프로젝트의 조건을 따라야 합니다.

환경은 Homebrew OpenJDK 21.0.11, Maven 3.9.14, ShardingSphere-JDBC 5.5.3,
MyBatis 3.5.15, MyBatis-Plus core 3.5.5, digest를 고정한 MySQL 8.4.11입니다.
JUnit 테스트 한 개를 최초 실험과 전달용 준비 도구로 각각 실행했고, 모두 실패·오류·skip
없이 통과했습니다. baseline은 승인하지 않았습니다.

## 기존 테스트에 관측을 추가하는 경우

**CityPulse · `verified - MySQL` · `verified - ShardingSphere-JDBC 5.5.3`**

[CityPulse `dccffc7a`](https://github.com/rexqd/citypulse-platform/tree/dccffc7a33965868a4b55ff9aae60bb831d76bad)의
두 파일 패치로 공개 테스트 의존성을 추가하고 기존 통합 테스트의 마지막 주문 조회를
capture했습니다. 애플리케이션 소스 204개와 테스트 소스 77개를 컴파일했고, 선택한 수정
테스트 한 개가 격리한 합성 MySQL·Redis 환경에서 skip 없이 통과했습니다. 기존 업무
assertion은 유지했습니다.

마지막 조회에서 **물리 JDBC 실행 시도 2회, 관측 데이터 소스 별칭 1개**를 확인했습니다.
capture는 완전했고 보고된 실행 실패는 없었습니다. 예산·승인된 baseline·회귀 실패 재현을
확립한 실험은 아닙니다. 앞선 결제 쓰기나 트랜잭션 커밋은 capture 범위 밖이고,
전체 테스트와 수정 전 원본 메서드는 별도로 실행하지 않았습니다.

**확인·재현:** [실험과 정확한 환경](evidence/citypulse-isolated-pilot-2026-09-08.md)
· [패치와 기록된 명령 안내](evidence/citypulse-isolated-pilot-reproduction-2026-09-08.md).
실행 환경은 Temurin 17.0.17, Maven 3.9.11, Spring Boot 3.2.12,
ShardingSphere-JDBC 5.5.3, MySQL 8.4.11, Redis 7.4.2입니다. 명령 안내는 격리된
환경을 먼저 준비해야 하며, 환경을 한 번에 설치하는 도구는 아닙니다.

## 내 작업에 맞는 계약 선택하기

업무 결과 assertion을 유지하세요. 실행 범위의 증가가 중요하면 예산을, 횟수만으로
요구사항을 표현할 수 없으면 기대 별칭과 구조 비교를 사용합니다. 관측 차이만으로 결함을
단정하지 않고, 의도한 변경은 새로운 baseline을 승인하기 전에 검토합니다.

[브라우저에서 체험](first-project.ko.md#try-in-your-browser)하거나
[기존 테스트 하나에 적용](first-project.ko.md)해 볼 수 있습니다.
[버전이나 필요한 검사 문의](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml)에는
설치가 필요하지 않습니다. 자체 실험·프로젝트 적용·반복 사용의 구분은
[사용 경험 기록 기준](user-feedback.md)을 참고하세요.
