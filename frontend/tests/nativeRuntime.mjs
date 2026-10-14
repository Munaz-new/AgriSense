// Load the installed RN FormData and Expo patch/encoder, not a Map approximation.
// OS networking remains a double: these tests do not claim device verification.
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { transformSync } from '@babel/core';
import ts from 'typescript';

export function loadTs(relative, globals = {}) {
  const exports = {};
  const source = readFileSync(new URL(relative, import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  runInNewContext(compiled, { exports, Error, TypeError, Blob, Uint8Array, TextEncoder, ...globals });
  return exports;
}

const rnExports = {};
const source = readFileSync(new URL('../node_modules/react-native/Libraries/Network/FormData.js', import.meta.url), 'utf8');
const compiled = transformSync(source, { configFile: false, babelrc: false,
  plugins: ['@babel/plugin-transform-flow-strip-types', '@babel/plugin-transform-modules-commonjs'],
}).code;
runInNewContext(compiled, { exports: rnExports });
const { installFormDataPatch } = loadTs('../node_modules/expo/src/winter/FormData.ts');
export const NativeFormData = installFormDataPatch(rnExports.default);
export const { convertFormDataAsync } = loadTs('../node_modules/expo/src/winter/fetch/convertFormData.ts', {
  require: () => ({ blobToArrayBufferAsync: blob => blob.arrayBuffer() }),
});
