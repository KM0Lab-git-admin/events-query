import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // Base relativa para que funcione en cualquier dominio
  base: './',
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: process.env.EVENTS_API_PROXY || 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/events': {
        target: process.env.EVENTS_API_PROXY || 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/query': {
        target: process.env.EVENTS_API_PROXY || 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/health': {
        target: process.env.EVENTS_API_PROXY || 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      // Imágenes locales de ingesta (FastAPI sirve repo/static/images)
      '/static/images': {
        target: process.env.EVENTS_API_PROXY || 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    }
  }
})
