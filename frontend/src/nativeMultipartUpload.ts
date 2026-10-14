/** React Native XHR consumes URI-backed FormData through its native networking
 * module. Expo SDK 57's global fetch uses a different encoder that rejects it.
 * Keep this transport local to native uploads; never set a multipart boundary.
 */
export class NativeUploadError extends Error {}

type UploadResponse = Pick<Response, 'ok' | 'status' | 'json'> & {
  headers: Pick<Headers, 'get'>;
};

export function nativeMultipartUpload(url: string, body: FormData, signal: AbortSignal): Promise<UploadResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    let settled = false;
    const cleanup = () => {
      signal.removeEventListener('abort', abort);
      xhr.onload = xhr.onerror = xhr.onabort = xhr.ontimeout = null;
    };
    const fail = (error: Error) => {
      if (settled) return;
      settled = true; cleanup(); reject(error);
    };
    const aborted = () => {
      const error = new Error('Photo upload aborted.');
      error.name = 'AbortError';
      return error;
    };
    const abort = () => {
      fail(aborted());
      // Release the native request as well as rejecting the JS promise.
      try { xhr.abort(); } catch { /* Already stopped; the promise is rejected. */ }
    };
    if (signal.aborted) { fail(aborted()); return; }
    xhr.onload = () => {
      if (settled) return;
      if (xhr.status === 0) { fail(new TypeError('Network request failed')); return; }
      const status = xhr.status;
      const text = xhr.responseText;
      settled = true; cleanup();
      resolve({ ok: status >= 200 && status < 300, status,
        headers: { get: name => xhr.getResponseHeader(name) },
        json: async () => JSON.parse(text) });
    };
    xhr.onerror = () => fail(new TypeError('Network request failed'));
    xhr.onabort = xhr.ontimeout = () => fail(aborted());
    signal.addEventListener('abort', abort, { once: true });
    try {
      xhr.open('POST', url);
      xhr.send(body);
    } catch {
      fail(new NativeUploadError('Photo upload could not start. Retake the photo or choose it again from Gallery, then retry. If a save was pending, check history first.'));
    }
  });
}
