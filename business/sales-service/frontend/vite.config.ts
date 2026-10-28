import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: '/sales/',
  plugins: [react()],
  resolve: {
    dedupe: ['react', 'react-dom', 'lucide-react'],
  },
  optimizeDeps: {
    exclude: ['@eai/workflow-embed'],
  },
  server: {
    proxy: {
      '/sales/api': {
        target: 'http://127.0.0.1:3104',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/sales\/api/, '/api/v1'),
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
