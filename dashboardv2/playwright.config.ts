import { defineConfig, devices } from '@playwright/test';

const testApiUrl = process.env.VITE_API_URL || 'http://localhost:8000';

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'npm run build && npm run preview -- --host 127.0.0.1 --port 4173',
    env: {
      ...process.env,
      VITE_API_URL: testApiUrl,
      VITE_COPILOT_ENABLED: process.env.VITE_COPILOT_ENABLED || 'true',
      VITE_LOCAL_DEV_AUTH: 'false',
      VITE_ADMIN_AI_OPS_ENABLED: 'true',
    },
    port: 4173,
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
