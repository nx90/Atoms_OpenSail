import { afterEach, describe, expect, it, vi } from 'vitest';
import { generateUuid } from './uuid';

describe('generateUuid', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('uses crypto.randomUUID when available', () => {
    vi.stubGlobal('crypto', {
      randomUUID: () => '12345678-1234-4234-8234-123456789abc',
    });

    expect(generateUuid()).toBe('12345678-1234-4234-8234-123456789abc');
  });

  it('generates an RFC 4122 version 4 UUID without randomUUID', () => {
    vi.stubGlobal('crypto', {
      getRandomValues: (bytes: Uint8Array) => {
        bytes.fill(0);
        return bytes;
      },
    });

    expect(generateUuid()).toBe('00000000-0000-4000-8000-000000000000');
  });
});