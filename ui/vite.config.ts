import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Fixed file names: the host rewrites the addresses in index.html and adds its own
// cache buster, so hashed names would only leave stale files behind in the repo.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    rollupOptions: {
      output: {
        entryFileNames: 'assets/index.js',
        chunkFileNames: 'assets/index.js',
        assetFileNames: (asset) => (asset.name?.endsWith('.css') ? 'assets/index.css' : 'assets/[name][extname]'),
      },
    },
  },
  server: {
    port: 5174,
    proxy: { '/comic_lettering': 'http://127.0.0.1:7860', '/file=': 'http://127.0.0.1:7860' },
  },
})
