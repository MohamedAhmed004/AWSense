import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ command, mode, isPreview }) => {
  const localApi = 'http://localhost:8000'
  const apiPath = '/api/v1'
  const apiUrl = process.env.VITE_API_URL ?? loadEnv(mode, process.cwd(), 'VITE_').VITE_API_URL
  const useDevProxy = command === 'serve' && !isPreview &&
    (!apiUrl || apiUrl === `${localApi}${apiPath}`)

  return {
    plugins: [react()],
    define: useDevProxy ? {
      'import.meta.env.VITE_API_URL': JSON.stringify(apiPath),
    } : {},
    server: {
      port: 5173,
      proxy: {
        '/api': { target: localApi, changeOrigin: true },
      },
    },
  }
})
