import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// dev 时把 /api 代理到本机 serve（python -m review_tool serve，默认 8765）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8765' },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
  },
})
