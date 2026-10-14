import { spawnSync } from 'node:child_process';
import { readdirSync, readFileSync } from 'node:fs';

export function validatePagesApiUrl(value) {
  let url;
  try { url = new URL(value); } catch { throw new Error('Set EXPO_PUBLIC_API_URL to https://YOUR_FRONTEND_HOST/api.'); }
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash ||
      url.pathname !== '/api' || /^(localhost|127\.|0\.|\[|\d+(?:\.\d+){3}$|.*\.(?:localhost|local|test|invalid)$)/i.test(url.hostname)) {
    throw new Error('Pages requires a public HTTPS same-origin /api endpoint without credentials.');
  }
  return url;
}

if (process.argv[1] === new URL(import.meta.url).pathname) {
  validatePagesApiUrl(process.env.EXPO_PUBLIC_API_URL);
  // Do not inherit a developer .env or permit silent localhost fallback.
  const result = spawnSync(process.execPath, ['node_modules/expo/bin/cli', 'export', '--platform', 'web', '--clear'], {
    stdio: 'inherit', env: { ...process.env, EXPO_NO_DOTENV: '1', CI: '1' },
  });
  if (result.status !== 0) process.exit(result.status ?? 1);
  const bundleDirectory = 'dist/_expo/static/js/web';
  const hasConfiguredUrl = readdirSync(bundleDirectory).filter(name => name.endsWith('.js'))
    .some(name => readFileSync(`${bundleDirectory}/${name}`, 'utf8').includes(process.env.EXPO_PUBLIC_API_URL));
  if (!hasConfiguredUrl) throw new Error('Exported web bundle does not contain the configured API URL; deployment refused.');
}
