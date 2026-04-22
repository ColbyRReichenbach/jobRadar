/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_LOCAL_DEV_AUTH?: string;
  readonly VITE_SENTRY_DSN?: string;
  readonly VITE_CHROME_EXTENSION_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
