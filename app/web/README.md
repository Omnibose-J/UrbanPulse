# UrbanPulse 화면

Next.js(App Router) + TypeScript + Tailwind v4. 설치와 실행은 저장소 루트의 `README.md` 참고.

- `src/screens/`: 화면 (홈, 검색, 이번 주, 하루 상세, 지도, 안내)
- `src/components/ui.tsx`: 공통 컴포넌트
- `src/lib/`: DB 조회, 시간·문장 규칙 (단위 테스트는 같은 폴더의 `*.test.ts`)
- `src/app/api/`: 읽기 전용 API
- `messages/`: 한국어·영어 문구
- `e2e/`: Playwright 테스트
