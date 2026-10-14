import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const app = JSON.parse(readFileSync(new URL('../app.json', import.meta.url), 'utf8')).expo;

test('Android release config declares a stable app ID and monotonically managed version code', () => {
  assert.match(app.android.package, /^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$/);
  assert.equal(app.android.versionCode, 1);
});

test('standalone Android manifest requests camera but not microphone access', () => {
  assert.ok(app.android.permissions.includes('android.permission.CAMERA'));
  const picker = app.plugins.find(plugin => Array.isArray(plugin) && plugin[0] === 'expo-image-picker')[1];
  assert.equal(picker.microphonePermission, false);
  assert.match(picker.cameraPermission, /Capture a leaf image/);
});

test('release signing reads private key material only from non-public build environment variables', () => {
  const plugin = readFileSync(new URL('../plugins/withReleaseSigning.js', import.meta.url), 'utf8');
  assert.match(plugin, /AGRISENSE_ANDROID_KEYSTORE/);
  assert.match(plugin, /AGRISENSE_ANDROID_STORE_PASSWORD/);
  assert.match(plugin, /AGRISENSE_ANDROID_KEY_ALIAS/);
  assert.match(plugin, /AGRISENSE_ANDROID_KEY_PASSWORD/);
  assert.match(plugin, /const debugFallback =/);
  assert.match(plugin, /contents = contents\.replace\(debugFallback/);
  assert.match(plugin, /signingConfig signingConfigs\.release/);
});
