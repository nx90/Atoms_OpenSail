import { describe, expect, it } from 'vitest';

import { createDefaultAppConfig } from './tesslateConfigDefaults';

describe('createDefaultAppConfig', () => {
  it('returns a ready-to-save React app configuration', () => {
    expect(createDefaultAppConfig()).toEqual({
      directory: '.',
      port: 3000,
      start: 'npm install && npm run dev -- --host 0.0.0.0',
      build: 'npm run build',
      output: 'dist',
      framework: 'react',
      env: {},
    });
  });

  it('returns independent environment maps', () => {
    const first = createDefaultAppConfig();
    const second = createDefaultAppConfig();

    first.env.API_URL = 'https://example.com';

    expect(second.env).toEqual({});
  });
});