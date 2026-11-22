
FireRoute 개발 인계서
작성일: 2026-11-17 (한국 시간)

1. 프로젝트와 현재 상태

FireRoute는 2026 oneM2M × ETSI MEC 해커톤용 화재 대피·구조 안내 시스템이다. 제출 목표일은 2026-11-20이다.

가상 화재·연기·붕괴 상황을 실제 oneM2M 서버에 저장하고, 위험 구역을 피하는 경로와 가상 주민의 이동을 계산한다. 안내 장치 3개의 명령 수신·적용 여부를 확인하고, 주민·구조대 웹 화면에 표시한다.

현재 로컬 MEC 플랫폼 등록 → 위험 계산 서비스 호출 → oneM2M 결과 전달 → Group 장치 제어 → 대시보드까지 실제 통합 검사가 통과했다. 화재·주민·장치는 시뮬레이션이고, CSE 통신과 MEC API 호출은 실제 구현을 사용한다. 실물 센서·실제 위치 측정·검증된 화재 안전 모델은 없다.

개발은 로컬 환경을 우선한다. Hosted MEC 접속·배포는 별도 지시 전까지 보류한다. 영상 촬영은 사용자가 맡기로 했다.

2. 저장소와 실행 환경

저장소: https://github.com/gaevalja/fire-route.git
현재 PC 경로: /home/lilkid/fire-evac/fire-route
개발 브랜치: feature/p1-hazard-validation
기준 커밋: ecc5116b3bb2af4c95a78aa654110f90124e0e0c

인계서 작성 시 로컬 HEAD와 origin/feature/p1-hazard-validation 추적 참조가 같고, 미커밋 변경 사항은 없다. main이 최신 개발 내용을 포함한다고 가정하지 말고 위 브랜치·커밋을 기준으로 시작한다.

주요 커밋:

- ced58cc: 공식 로컬 MEC011 구성요소와 CSE 카탈로그 연결
- e2f7a05: MEC 위험 계산 서비스·FireRoute 전용 IPE·대시보드 구현
- ecc5116: CouchDB 기동 설정 수정

환경: WSL2 Ubuntu + Docker Compose.
앱 실행 기준: Python 3.12, 호스트 Node.js 24.22.1.
호스트에는 Docker/Compose, Python 3, Node.js, make, git가 필요하다. Go 1.25.0은 이미지 빌드 단계에서 사용하므로 호스트 Go 설치는 필요 없다. Compose는 !override와 additional_contexts를 지원해야 한다. 실제 브라우저 검사는 Chrome 및 정상 작동하는 브라우저 sandbox가 필요하다.

핵심 구성:

- ACME CSE 2026.5.1: 실제 oneM2M 서버. 버전별 종료 수정 패치 포함.
- 공식 ETSI Sandbox의 App Enablement/MEC011 및 Sandbox Controller: Go 구현.
- Redis 6.2.24, CouchDB 3.5.2.1, InfluxDB 1.8.10: 공식 구성요소의 저장소 의존성.
- Python 백엔드·위험 계산 서비스·전용 IPE, 빌드 없는 HTML/CSS/JavaScript 화면.

공식 MEC 백엔드 소스 기준: STF_685 / 8c66f08e443be174f109fe2ac645247c9afcd449.
공식 프런트엔드 소스도 확보했지만 현재 시연 화면은 FireRoute 자체 대시보드다. 전체 Kubernetes Sandbox UI를 설치한 상태는 아니다.

3. 동작 구조와 용어

CSE는 oneM2M 서버, AE는 앱 식별 자원, CNT는 데이터 컨테이너, CIN은 데이터 항목, SUB는 구독, ACP는 접근 권한, Group/fanOutPoint는 여러 장치에 명령을 전달하는 기능이다. ACK는 장치가 명령을 적용한 뒤 남기는 응답이다. IPE는 서로 다른 서비스의 요청·결과를 연결하는 중계 프로그램이다.

MEC 모드의 처리 흐름:
  원본 화재 엔진의 현재 프레임 생성
  → 실제 CSE에 센서 CIN 저장·조회 및 SUB 알림 확인
  → CSE 요청 CIN/SUB를 통해 FireRoute IPE에 계산 요청
  → 공식 MEC 등록소에서 실제 등록된 위험 계산 서비스를 검색·호출
  → 결과 CIN 저장·조회 및 SUB 수신
  → 백엔드가 원본 이벤트·사건·버전·결과 해시·유효시간 검증
  → 실제 Group/fanOutPoint로 안내 장치 3개에 명령 전달
  → 독립 장치 프로세스가 각자 ACK 생성
  → 역할별 대시보드에서 CSE 기록 조회

안내 장치는 실제 하드웨어가 아닌 독립 Python 프로세스다. Group 성공 응답과 장치 ACK는 구분해서 검증한다.

MEC 모드는 결과가 누락·불일치·만료되면 로컬 계산만으로 정상인 것처럼 계속하지 않는다. UNKNOWN/DEGRADED로 처리하며 불완전한 거래는 명시적 초기화가 필요하다.

현재 배포는 Docker로 실행한 외부 앱을 실제 MEC 플랫폼에 등록한 방식이다. IPE도 FireRoute 프로젝트 전용 구현이다. 공식 meep-ipe 실행, MEC033/046 서비스, VM 배치, CSE를 MEC 앱으로 실행하는 Option C는 검증하지 않았다. 현재 CSE는 로컬 standalone IN-CSE이며 MN-CSE/상위 IN-CSE 등록 구조가 아니다.

4. 완료·검증된 기능

- 실제 CSE의 AE/CNT/CIN/SUB/ACP/Group 자원 생성·조회와 HTTP/oneM2M 응답 검증.
- 센서 이벤트 수집, 실제 구독 검증 요청과 알림 수신, 중복·순서·유효시간 처리.
- 화재·연기 차단 구역에 따른 경로 재계산, 붕괴 구역 제외, 대피 불가 시 방향 제거.
- 고정 출발점 안내와 가상 주민 이동·통로 정체·출구 도착·잔류 인원 추적.
- 주민·구조대 로그인 분리, 구조대 전용 인원 정보와 실제 ACP 접근 거부 검사.
- Group 명령 전달, 장치별 독립 ACK, 정지 장치에 대한 INCOMPLETE 판정.
- 관측 만료 시 STALE/UNKNOWN 표시, 방향·현재 위치 제거, 구조대의 과거 스냅샷 조회.
- CSE 제어 종료·재시작에서 정상 종료 코드 0, 키·AE/CNT/CIN 유지 및 기본 키 경고 해소 확인.
- 비정상 입력·센서 침묵·주입한 읽기 링크 장애·제어된 CSE 중단 후 복구 검사.
- 별도 프로파일의 MQTT→CSE→HTTP/SUB, 브라우저/API HTTPS, 인증서 기반 CSE mTLS 검사.
- 로컬 observer 기준 성능 측정과 증빙 수집 코드. 기존 수치는 새 MEC 경로의 성능 결과가 아니다.
- 공식 MEC 앱 ID 발급, READY 확인, 서비스 등록·검색·실제 위험 계산 호출.
- 전용 IPE의 CSE 요청/결과 연결, 중복 계산 방지, 불확실한 CREATE 재전송 방지.
- 위험 계산 SQLite 저널과 IPE inbox/outbox. 저장소 재개방에 따른 계산 상태 복원은 단위·오프라인 검사로 확인했다.
- CouchDB 초기 기동 장애 수정. 읽기 전용 설정 bind 대신 이미지에 설정을 포함하고, 기본 사용자 소유권과 Bash 상태 검사를 사용한다. 이후 실제 기동과 통합 검사가 통과했다.

최신 검사 결과:

- Python 단위 테스트: 414개 PASS.
- 프런트엔드 로직: 16개 PASS. 브라우저 구동 도구 단위 검사: 25개 PASS.
- 원본 729프레임 오프라인 비교: 위험 계산 저널과 원래 모델의 결과 일치, 4개 위험 단계 확인.
- LOCAL_MEC_RISK_IPE_E2E: 12개 PASS. 실제 728프레임, 정상 0초·우회 466초·붕괴 600초·고립 727초, Group 4회와 각 단계 3개 장치 ACK 확인.
- LOCAL_MEC_DASHBOARD: 20개 PASS. 실제 MEC 결과 사용, 두 이동 모드, 역할 제한, 주민 이동, 인원 보존, 31초 관측 만료와 과거 스냅샷 확인.
- 과거 efc65cb 커밋의 비-MEC 로컬 구성: clean archive 전체 19단계 PASS. 이 결과를 최신 MEC 구성의 clean 재현 결과로 사용하면 안 된다.

최신 MEC 검사 두 개는 HTTP/API와 실제 CSE/MEC 동작 검사다. 3002 화면의 실제 브라우저 렌더링 검사는 아직 하지 않았다. 과거 3001/HTTPS 화면의 브라우저 검사 성공과 구분한다.

5. 실행·중단 방법

현재 PC에서 일반 사용:
  cd /home/lilkid/fire-evac/fire-route
  make demo-mec-up

접속: http://127.0.0.1:3002/
접속 코드 위치: .runtime/access-codes.json
주민 또는 구조대 역할에 맞는 코드를 로컬에서 확인한다. 실제 코드·키 값은 이 문서에 포함하지 않았다.

구조대는 초기화, +1초/+30초, 자동 진행·일시정지, 가상 주민·층 선택, 장치 C 중지를 사용할 수 있다. 테스트 후나 일시정지 후 30초가 지나면 관측 만료가 정상이다. 초기화하면 새 사건으로 시작한다. 모의 시간과 실제 실행 시간은 다르다.

MEC 전체 통합 검사:
  make p1-mec-services

이 명령은 원본 시나리오 생성 → 서비스 기동 → 12개 E2E 검사 → 20개 대시보드 검사까지 실행한다. 성공 후 서비스는 계속 실행된다. 각 JSON 결과의 state=PASS와 failed_checks를 확인한다.

로그 확인·중단:
  make mec-services-logs
  make mec-services-down

서비스 상태:
  docker compose -p fire-route-mec-services -f compose.mec-services.yaml --profile mec-dashboard ps

mec-services-down은 해당 프로젝트를 중단하며 데이터 볼륨은 보존한다. 기존 데이터를 지우는 down -v나 volume prune을 초기 문제 해결 절차로 사용하지 않는다.

구성별 주소:

- 3002: 현재 MEC 연동 대시보드.
- 8091: 위 구성의 MEC API. /mec_service_mgmt/v1/services에서 서비스 목록 조회.
- 3001: 기존 10층 비-MEC 대시보드. make demo-scenario-up / make down 사용.
- 8090: 이전 최소 MEC 검색 검사 구성. make p1-mec-local / make mec-local-down 사용.
- 3000: 초기 3층 대시보드 회귀용. 현재 주 시연 대상이 아니다.

새 PC에서 시작:
  git clone --branch feature/p1-hazard-validation https://github.com/gaevalja/fire-route.git
  cd fire-route
  make mec-local-prepare
  make p1-mec-services
  make demo-mec-up

처음에는 이미지와 공식 소스 다운로드가 필요하다. mec-local-prepare는 소스 확보 단계이며 서비스 실행 명령이 아니다. 공식 소스 브랜치가 변경되어 고정 커밋 검증에 실패하면 임의로 버전 검사를 해제하지 말고 infra/mec/upstream.json과 소스 lock을 확인한다. 새 PC에서 이 전체 절차를 재현한 기록은 아직 없다.

6. 코드와 증빙 위치

backend/
  센서 수집, 사건·경로 관리, Group 전달, 인증·역할 API, 기본 시나리오 실행.
frontend/scenario/
  현재 10층 대시보드. frontend/ 루트는 초기 3층 화면.
simulator/scenarios/fire_evac/
  공급된 화재 엔진 원본 7개 파일과 manifest. 변경하지 않는 기준 소스.
simulator/evacuation.py, mec/risk/evacuation.py
  가상 주민 이동과 경로·차단·통로 수용량 모델.
mec/risk/service.py
  독립 위험 계산 HTTP 서비스와 프레임/결과 SQLite 저널.
mec/service_client.py
  공식 MEC 앱·서비스 등록, 검색, 제한된 HTTP 호출.
mec/interworking/
  FireRoute 전용 IPE, CSE 요청·결과 구독, outbox, 결과 검증·구독 정리.
mec/dashboard.py
  기본 시나리오에 MEC 결과 필수 경로를 연결하는 대시보드 모드.
onem2m/
  HTTP/MQTT 클라이언트, 자원 bootstrap, ACP, Group 및 결정 데이터 처리.
infra/, compose*.yaml, Makefile
  이미지, 소스 확보·버전 고정, CSE 종료 패치, TLS, 프로파일별 실행·검사.
tests/
  단위·프런트엔드·브라우저·실제 통합 검사.
fixtures/evacuation_assumptions.json
  측정되지 않은 건물 치수·보행 속도·인구·정체·차단 정책의 명시적 가정값.
docs/
  요구사항 PRD, ARCHITECTURE, TEST_PLAN, DECISIONS, RUBRIC, 실행 문서.
docs/submission/
  기사 초안, 발표 HTML, 아키텍처 SVG, 영상 대본. 게시·제출 완료본이 아니다.
evidence/<UTC 실행 ID>/
  summary, assertions, 실제 요청·응답, 알림, 자원 ID, 실행 소스 해시 등 원본 증빙.
.runtime/
  생성된 시나리오, 로컬 접속 코드·키, 공식 MEC 소스·lock, 임시 릴리스.

핵심 증빙 폴더(현재 PC 저장소 기준 상대 경로):

- evidence/20261116-130954Z-61c5296f/: 최신 MEC E2E 12개 PASS.
- evidence/20261116-131533Z-8c101e70/: 최신 MEC 대시보드 20개 PASS.
- evidence/20261116-130616Z-e8ee9df3/: 414개 단위 검사와 CouchDB 수정 검사.
- evidence/20261116-044349Z-18300187/: 과거 비-MEC clean archive 19단계 PASS.
- evidence/20261116-040708Z-ba53f73b/: 별도 mTLS CSE 검사 11개 PASS.

evidence/와 .runtime/, Docker 데이터 볼륨은 Git에 포함되지 않는다. 원본 검증 결과가 필요하면 위 증빙을 별도로 인계받아야 한다. 새 환경의 코드·키는 준비 명령으로 생성한다. 기존 CSE 자원과 상태까지 그대로 이어받으려면 데이터 볼륨과 해당 키의 별도 인계가 필요하다.

중요: README, docs/STATUS.md, docs/MEC_SERVICES.md, AGENTS.md 일부에는 최종 성공 전의 “CouchDB 실패/미검증” 문구가 남아 있다. 위 최신 두 PASS 증빙이 그 뒤의 결과다. 후임자는 우선 문서를 최신 검증 범위에 맞게 정리해야 한다.

7. 남은 작업과 진행 순서

우선 1 — 최신 상태 문서화와 재현

- 최신 MEC E2E/대시보드 PASS를 STATUS·README·MEC_SERVICES·평가 항목 표와 제출 자료에 반영한다.
- 새 clone/깨끗한 커밋에서 최신 MEC 소스 확보·이미지 빌드·전체 통합 검사를 재현한다.
- 기존 verify-local/verify-clean은 비-MEC 중심 19단계 계획이다. 새 MEC 검사를 실제로 포함하고 실패·미실행 단계를 구분하도록 확장한다.

우선 2 — MEC 모드의 실제 브라우저 검사

- 3002에서 구조대·주민 로그인, 경로·주민 선택, ACK, 만료·초기화·로그아웃·모바일 화면을 실제 Chrome으로 검사한다.
- tests/browser/dashboard.mjs는 --port 3002를 지원하지만 summary/meta의 MEC 상태가 unavailable로 고정돼 있다. MEC 모드에 맞는 상태 검증·증빙 표기를 먼저 수정한다.
- 화면의 “MEC 경유 계산 확인”이 실제 최신 결과에만 표시되는지, 오류·만료 시 숨겨지는지 확인한다.

우선 3 — 새 MEC 경로의 보안·장애 검증

- 현재 MEC 구성은 내부 HTTP와 개발용 CSE Originator 헤더를 사용한다. 별도 mTLS/HTTPS 성공을 이 구성 전체에 적용된 결과로 간주하면 안 된다.
- 필요 범위를 정해 주 구성의 CSE 인증, API/콜백 암호화, MQTT TLS를 적용하고 실제 권한·역할·Group 회귀 검사를 수행한다.
- 위험 계산/IPE/앱 프로세스 강제 종료·재시작, 부분 fan-out, CREATE 응답 유실을 실제 프로세스·통신 장애로 검증한다. 현재는 관련 단위 검사 및 제한된 CSE 중단·복구 검사까지 완료된 상태다.
- 새 MEC 경로의 지연·실패율을 별도로 측정한다. 기존 docs/PERFORMANCE.md의 비-MEC observer 수치로 MEC 성능 향상을 주장하지 않는다.

우선 4 — 최종 제출물

- Hackster.io 기사·아키텍처·발표 자료를 최신 실제 구성/검증 결과로 수정하고 링크·재현 절차를 정리한다.
- GitHub의 최종 브랜치 통합·릴리스, 외부 게시·최종 제출 여부는 별도 확인한다.
- 영상은 사용자가 담당한다. 실제 게시/제출 결과는 현재 검증 기록에 없다.

조건부 후속 범위

- Hosted Sandbox 로그인·권한·API·배포 방식은 미검증이며 별도 허가 전까지 접속·배포하지 않는다.
- 공식 meep-ipe/MEC033/046, Option C, 상위 CSE 등록, VM/Kubernetes 배치, 다중 호스트 orchestration은 미완료다. 필요성과 실제 지원 여부를 확인한 뒤 선택한다.
- 고급 의미 모델(SDT/SAREF), CSE handover, 실제 위치 서비스, FL, AI/MCP는 현재 핵심 구현 범위에 없다. 해커톤 모든 평가 항목을 구현할 필요는 없다.

8. 개발 시 유지할 기준

선정 시나리오는 10층+옥상, 162구역, 기본 고정 출발점 F7-R3, 가상 주민 170명이다. 화재·연기 값은 원본의 0~100 상대 지수이며 온도·ppm으로 변환하지 않는다. 길이·인구·속도·차단 임계값은 측정값이 아닌 가정이다.

기존 원본 7개 파일과 fixtures의 가정값은 임의 변경하지 않는다. 별도 시나리오·정책 변경은 출처와 새 검사를 남긴다. 현재 자연 위험 실행은 늦은 위험 단계 전에 주민 전원이 출구에 도달한 사례가 있으므로, 갇힌 사람 구조나 붕괴만의 경로 변경 효과를 입증한 실행으로 설명하지 않는다.

CSE 자원과 실제 응답을 Mock 또는 자체 데이터베이스로 대체하지 않는다. 유효하지 않은 관측·통신 장애가 위험을 해제하거나 오래된 경로를 새 경로처럼 보이게 하면 안 된다. Group 성공만으로 장치 ACK를 성공 처리하지 않는다.

위험 계산 저널은 현재 20,000프레임 상한이 있다. 초과하면 처리 실패로 닫히며 자동으로 데이터를 지우지 않는다. 반복 시연·장시간 운영 전에 보존 정책을 정해야 한다.

ACME 종료 수정, Controller의 Couch 인증 설정 수정, Couch 이미지의 설정 소유권 처리는 버전별 코드다. 의존성을 바꾸면 패치·기동·데이터 유지·권한 검사를 다시 확인한다.

일반 검사 명령:
  make test-unit
  make test-frontend
  make test-scenario
  make test-browser-driver
  make p1-mec-services

기존 구성 회귀 검사:
  make local-stability
  make p1-hazards
  make p1-faults
  make p1-recovery
  make p1-latency
  make p1-cse-security
  make verify-clean

통합·장애 검사는 한 번에 하나씩 실행한다. 기존 구성 회귀 명령은 해당 데모를 재생성·중단할 수 있으므로 주 시연과 분리해서 실행한다. Chrome이 필요한 검사와 실제 Docker 검사는 단위 테스트 성공만으로 대체할 수 없다.

최신 검증 문서를 수정한 뒤의 Git 작업 예시:
  git status
  git add docs/STATUS.md docs/MEC_SERVICES.md
  git commit -m "docs: record verified local MEC integration"
  git push origin feature/p1-hazard-validation

다른 코드를 수정했으면 git add 뒤에 그 파일 경로를 지정한다.

개발은 feature 브랜치에서 진행하고 원본 증빙·기존 데이터·다른 사람의 작업을 덮어쓰지 않는다. 새 검증 결과는 실행 ID·소스 버전·검사 범위를 함께 기록한다.
