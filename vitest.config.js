import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  resolve: {
    alias: {
      '@js': path.resolve(__dirname, 'memes_api/js'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    dir: 'tests/js',
  },
});
