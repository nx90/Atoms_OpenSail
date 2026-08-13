import type { AppConfig } from '../types/tesslateConfig';

export function createDefaultAppConfig(): AppConfig {
  return {
    directory: '.',
    port: 3000,
    start: 'npm install && npm run dev -- --host 0.0.0.0 --port 3000 --strictPort',
    build: 'npm run build',
    output: 'dist',
    framework: 'react',
    env: {},
  };
}