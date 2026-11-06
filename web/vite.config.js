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
  // W15：npm test（vitest run）；jsdom 模拟浏览器，测试文件与源码同目录 *.test.js(x)
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    include: ['src/**/*.test.{js,jsx}'],
    restoreMocks: true,
  },
})
