import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 실서버로 붙일 때 /api를 백엔드로 넘긴다. 브라우저 입장에서는 같은 출처(5173)라
// 서버에 CORS가 필요 없고, 로그인 쿠키가 그대로 오간다.
// 쓰려면 .env.local에 VITE_API_URL=/api/v1 (.env.example 참고). 비워 두면 목 데이터만 쓴다.
const api = { '/api': { target: 'http://localhost:8000', changeOrigin: true } }

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: { proxy: api },
  preview: { proxy: api },
})
