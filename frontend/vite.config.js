import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // 開発サーバの /api の転送先。既定は手元の Django。iPhone のライブリロードで
  // デプロイ済みのバックエンドを使うときは DEV_API_PROXY_TARGET に書く
  // （docs/ios.md の「10.」。VITE_ で始めないので画面のコードには入らない）。
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react()],
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: './src/test/setup.js',
      testTimeout: 10000,
    },
    server: {
      host: '127.0.0.1',
      port: 5173,
      proxy: {
        '/api': {
          target: env.DEV_API_PROXY_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
