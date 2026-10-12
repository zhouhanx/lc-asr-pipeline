import path from 'node:path'
import react from '@vitejs/plugin-react-swc'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: true,
    coverage: {
      provider: 'v8',
      reporter: ['text-summary', 'json-summary', 'html'],
      include: [
        'src/features/browser/**/*.{ts,tsx}',
        'src/features/auth/**/*.{ts,tsx}',
        'src/features/workspace/navigation.ts',
        'src/lib/api.ts',
      ],
      exclude: ['src/**/*.test.{ts,tsx}', 'src/test/**'],
    },
  },
})
