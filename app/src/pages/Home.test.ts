import { describe, expect, it } from 'vitest';
import { getWorkspaceCreateArgs } from './Home';

describe('getWorkspaceCreateArgs', () => {
  it('maps the Empty tile sentinel to an empty workspace', () => {
    expect(getWorkspaceCreateArgs('Scratch', '')).toEqual(['Scratch', '', 'empty']);
  });

  it('keeps template creation arguments', () => {
    expect(getWorkspaceCreateArgs('Web app', 'base-1', 'v2')).toEqual([
      'Web app',
      '',
      'base',
      undefined,
      'main',
      'base-1',
      'v2',
    ]);
  });
});