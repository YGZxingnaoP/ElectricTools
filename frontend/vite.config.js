import { defineConfig } from 'vite'

// 开发服务器：前端 5173；/ws、/api、/health 代理到后端 8765（env\python.exe 运行的 FastAPI）
export default defineConfig({
  root: '.',
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      '/ws': { target: 'ws://127.0.0.1:8765', ws: true, changeOrigin: true },
      '/api': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8765', changeOrigin: true }
    }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true
  }
})
