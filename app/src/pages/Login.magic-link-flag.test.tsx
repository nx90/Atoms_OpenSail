/**
 * Regression tests for the magic_link_login feature flag UI gating.
 *
 * Backend enforces the flag at the router (returns 404 when disabled;
 * backend integration tests cover that). These tests pin the UI behavior:
 *
 *   Flag ON:
 *     - Landing view is the password form.
 *     - Magic-link sign-in is reachable through an explicit switch.
 *
 *   Flag OFF:
 *     - Landing view is the classic password form.
 *     - NO affordance to switch to magic-link anywhere in the DOM.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Mock everything Login.tsx pulls in that would make jsdom unhappy.
vi.mock('../lib/api', () => ({
  authApi: { login: vi.fn(), verify2fa: vi.fn(), resend2faCode: vi.fn() },
  revokeServerSession: vi.fn(),
}));
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ checkAuth: vi.fn() }),
}));
vi.mock('../theme/ThemeContext', () => ({
  useTheme: () => ({ refreshUserTheme: vi.fn() }),
}));
vi.mock('../components/PulsingGridSpinner', () => ({
  PulsingGridSpinner: () => null,
}));
vi.mock('../components/ui/TesslateLogo', () => ({ TesslateLogo: () => null }));
vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

// useFeatureFlag is the thing we're actually testing — controllable per-test.
const useFeatureFlagMock = vi.fn<(flag: string) => boolean>();
vi.mock('../contexts/useFeatureFlag', () => ({
  useFeatureFlag: (flag: string) => useFeatureFlagMock(flag),
}));

beforeEach(() => {
  useFeatureFlagMock.mockReset();
});

async function renderLogin() {
  const { default: Login } = await import('./Login');
  render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>
  );
}

describe('Login page: magic_link_login feature flag UI gating', () => {
  it('flag ON: landing view is the password form', async () => {
    useFeatureFlagMock.mockImplementation((flag) => (flag === 'magic_link_login' ? true : false));
    await renderLogin();

    expect(screen.getByPlaceholderText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^sign in$/i })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /sign in with an email link instead/i })
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /send sign-in link/i })).not.toBeInTheDocument();
  });

  it('flag OFF: landing view is the password form without magic-link controls', async () => {
    useFeatureFlagMock.mockImplementation(() => false);
    await renderLogin();

    expect(screen.getByPlaceholderText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^sign in$/i })).toBeInTheDocument();
    // Every magic-link affordance is absent.
    expect(screen.queryByRole('button', { name: /send sign-in link/i })).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /sign in with password instead/i })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /sign in with an email link instead/i })
    ).not.toBeInTheDocument();
  });

  it('flag ON: users can switch to the magic-link form', async () => {
    useFeatureFlagMock.mockImplementation((flag) => (flag === 'magic_link_login' ? true : false));
    await renderLogin();

    fireEvent.click(screen.getByRole('button', { name: /sign in with an email link instead/i }));

    expect(screen.getByRole('button', { name: /send sign-in link/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /continue with google/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /continue with github/i })).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/password/i)).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /sign in with password instead/i })
    ).toBeInTheDocument();
  });
});
