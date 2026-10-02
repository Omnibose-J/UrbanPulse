# UrbanPulse

서울 핫플에 언제 가면 좋은지 알려 주는 서비스. 가고 싶은 장소는 그대로 두고, 문 닫힌 시간과 가장 붐비는 시간을 피한 시간대를 오늘부터 7일 뒤까지 추천함.

- 대상: 서울시 실시간 도시데이터 121곳 (역세권 247곳은 실험 기능)
- 화면: 모바일 웹 + PC 지도, 한국어·영어
- 상태(2026-10-02): 로컬에서 전부 동작. 클라우드 배포는 아직 안 함

## 구성

| 폴더 | 내용 |
|---|---|
| `app/engine/` | Python 엔진. 30분마다 수집, 매일 예측·추천·평가를 계산해서 DB에 저장 |
| `app/web/` | Next.js 화면. 저장된 값만 읽음 |
| `app/supabase/` | DB 스키마(마이그레이션)와 테스트 |
| `models/` | 학습된 예측 모델 |
| `analysis/scripts/` | 수치의 근거가 된 실험 코드 (실행·수정 금지, 읽기용) |
| `scripts/` | 작업 스케줄 등록, 클라우드 이전 스크립트(`scripts/cloud/`) |
| `design/` | 화면 시안 (브라우저로 열면 됨) |
| `docs/` | 문서 전부 (아래 표) |

## 문서

| 문서 | 내용 |
|---|---|
| `docs/specs/UrbanPulse_PRD.md` | 한 장 요약. 처음이면 이것부터 |
| `docs/specs/UrbanPulse_서비스정의서.md` | 무엇을 왜 만드는지, 실험 결과 |
| `docs/specs/UrbanPulse_구현설계서.md` | 구조, DB, 작업, 검증 규칙 |
| `docs/specs/UrbanPulse_디자인명세서.md` | 화면, 색·글자 규칙, 문구 |
| `docs/RUNBOOK.md` | 클라우드로 옮기는 순서와 운영 방법 |
| `docs/sow/SOW-MC.md` | 클라우드 이전 때 확인할 항목 |
| `docs/tracking/findings.md` | 아직 안 고친 문제 목록 |
| `AGENTS.md`, `docs/LLM_PROJECT_MAP.md` | 코딩 에이전트용 규칙과 파일 지도 (영어) |

## 로컬 실행

준비물: Python 3.10, Node 24, Docker Desktop, Supabase CLI

```powershell
# 1. 엔진 설치
pip install -e .

# 2. DB 띄우기 (Docker 필요)
cd app
supabase start
supabase status -o env      # 여기 나온 값을 .env에 넣음
cd ..

# 3. 환경 변수
copy .env.example .env      # 값 채우기 (아래 참고)

# 4. 화면
cd app/web
npm install
npm run dev                 # http://localhost:3000
```

`.env`에 넣을 값

- `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`: `supabase status -o env` 출력에서 복사
- `SEOUL_API_KEY`: 서울 열린데이터광장 인증키 (실시간 도시데이터)
- `KASI_API_KEY`: 공공데이터포털 인증키 (한국천문연구원 특일 정보)
- `ADMIN_TOKEN`: 아무 긴 문자열. `/admin` 화면 비밀번호로 씀

`.env`는 커밋하지 않음(`.gitignore`에 있음).

### 데이터

API 키만으로는 DB를 채울 수 없음. 장소 목록과 8~9월 과거 데이터가 있어야 예측이 나오는데 그 원본(6GB)은 저장소에 없음. 대신 DB를 통째로 담은 파일(`app/supabase/seed/urbanpulse-db.dump`, 약 6MB)이 저장소에 들어 있음.

```powershell
# supabase start 를 한 뒤, 저장소에 든 DB 파일을 넣음
powershell -File scripts\db_import.ps1

# 그다음 최신 상태로 맞춤
python -m engine collect     # 지금 데이터 수집
python -m engine forecast    # 예측과 추천 다시 계산
```

- `db_import`는 빈 DB에만 넣음. 이미 데이터가 있으면 아무것도 하지 않고 멈춤
- DB 파일은 만든 시점의 상태임. 새로 만들려면 `powershell -File scripts\db_export.ps1` 후 커밋 (자주 하면 저장소가 커지니 필요할 때만)
- 30분 수집은 한 PC에서만 돌리는 것을 권장 (API 호출 한도를 같이 씀)

Windows 작업 스케줄러에 등록하려면 `scripts/register_collect_task.ps1`, `register_forecast_task.ps1`, `register_evaluate_task.ps1`.
