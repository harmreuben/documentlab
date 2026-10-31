import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// During development, Vite (port 5173) forwards API calls to Django (port 8000).
// Both then share one origin, so Django's session and CSRF cookies just work.
const backend = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': backend,
      '/admin': backend,
      '/static': backend,
    },
  },
})
