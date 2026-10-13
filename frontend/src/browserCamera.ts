import type { ImagePickerResult } from 'expo-image-picker';

function cameraError(error: unknown): Error {
  const name = (error as { name?: string })?.name;
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return new Error('Camera access was denied or blocked. Allow camera access in your browser site settings and retry, or choose from the gallery.');
  }
  if (name === 'NotFoundError' || name === 'OverconstrainedError') {
    return new Error('No usable camera was found. Connect or enable a camera and retry, or choose from the gallery.');
  }
  return new Error('The camera is unavailable or in use. Close other camera apps or tabs and retry, or choose from the gallery.');
}

/** A user-triggered browser camera, never an implicit file-picker fallback.
 * The caller owns the returned blob URL and must revoke it after replacement.
 */
export async function captureBrowserPhoto(signal: AbortSignal): Promise<ImagePickerResult> {
  if (typeof window === 'undefined' || !window.isSecureContext) {
    throw new Error('Browser camera needs HTTPS or localhost. A phone using a plain HTTP laptop LAN address cannot use it. Use the native app or choose from the gallery.');
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('This browser does not support live camera capture. Use a supported browser or the native app, or choose from the gallery.');
  }
  if (signal.aborted) return { canceled: true, assets: null };
  const dialog = document.createElement('dialog');
  if (typeof dialog.showModal !== 'function') {
    throw new Error('This browser does not support the camera preview. Use a newer browser, the native app or the gallery.');
  }
  dialog.setAttribute('aria-label', 'Take a plant photo');
  dialog.style.cssText = 'box-sizing:border-box;width:min(94vw,640px);max-height:94dvh;overflow:auto;border:0;border-radius:20px;padding:20px;background:#fff;color:#173d2b;font:16px system-ui;';
  const title = document.createElement('h2');
  title.textContent = 'Take a plant photo';
  const status = document.createElement('p');
  status.setAttribute('role', 'status');
  status.textContent = 'Allow camera access when your browser asks. No audio is recorded.';
  const video = document.createElement('video');
  video.autoplay = true; video.muted = true; video.playsInline = true;
  video.setAttribute('aria-label', 'Live camera preview');
  video.style.cssText = 'display:block;width:100%;max-height:55dvh;object-fit:contain;background:#17251e;border-radius:12px;';
  const capture = document.createElement('button');
  capture.type = 'button'; capture.textContent = 'Capture photo'; capture.disabled = true;
  const cancel = document.createElement('button');
  cancel.type = 'button'; cancel.textContent = 'Cancel camera';
  for (const button of [capture, cancel]) {
    button.style.cssText = 'min-height:48px;padding:12px 20px;margin:12px 8px 0 0;border-radius:12px;border:1px solid #226342;font:inherit;cursor:pointer;';
  }
  capture.style.background = '#226342'; capture.style.color = '#fff';
  dialog.append(title, status, video, capture, cancel);

  return new Promise((resolve, reject) => {
    let stream: MediaStream | null = null;
    let finished = false;
    let capturing = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const previousFocus = document.activeElement as HTMLElement | null;
    const stopStream = () => {
      stream?.getTracks().forEach(track => { track.onended = null; track.stop(); });
      stream = null;
      video.srcObject = null;
    };
    const finish = (result: ImagePickerResult | null = null, error?: Error) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      stopStream();
      signal.removeEventListener('abort', abort);
      window.removeEventListener('pagehide', abort);
      window.removeEventListener('popstate', abort);
      document.removeEventListener('visibilitychange', hidden);
      dialog.close(); dialog.remove();
      previousFocus?.focus();
      if (error) reject(error);
      else resolve(result || { canceled: true, assets: null });
    };
    const abort = () => finish();
    const hidden = () => { if (document.hidden) finish(); };
    cancel.onclick = abort;
    dialog.oncancel = event => { event.preventDefault(); finish(); };
    signal.addEventListener('abort', abort, { once: true });
    window.addEventListener('pagehide', abort);
    window.addEventListener('popstate', abort);
    document.addEventListener('visibilitychange', hidden);
    const ready = () => {
      if (finished || capturing || video.readyState < 2 || !video.videoWidth || !video.videoHeight) return;
      clearTimeout(timer);
      capture.disabled = false;
      status.textContent = 'Frame a clear, well-lit leaf, then tap Capture photo. You can review or retake it before upload.';
    };
    video.onloadeddata = ready;
    video.oncanplay = ready;
    video.onerror = () => finish(null, cameraError(null));
    capture.onclick = () => {
      if (finished || capturing || capture.disabled) return;
      capturing = true; capture.disabled = true;
      try {
        if (video.videoWidth < 224 || video.videoHeight < 224 || video.readyState < 2) {
          throw new Error('The camera image is too small or not ready. Retake the photo with a camera supporting at least 224 × 224 pixels.');
        }
        const canvas = document.createElement('canvas');
        const scale = Math.min(1, 2048 / Math.max(video.videoWidth, video.videoHeight));
        canvas.width = Math.round(video.videoWidth * scale);
        canvas.height = Math.round(video.videoHeight * scale);
        const context = canvas.getContext('2d');
        if (!context) throw new Error('This browser could not capture a photo. Retry or use the gallery.');
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        // Release camera hardware as soon as the frame has been copied.
        stopStream();
        status.textContent = 'Preparing photo…';
        timer = setTimeout(() => finish(null, new Error('Preparing the photo took too long. Please retry.')), 15000);
        canvas.toBlob(blob => {
          if (finished) return;
          if (!blob?.size) { finish(null, new Error('The camera returned an empty photo. Please retake it.')); return; }
          const uri = URL.createObjectURL(blob);
          finish({ canceled: false, assets: [{ uri, width: canvas.width, height: canvas.height,
            mimeType: blob.type, fileName: 'camera-photo.jpg', fileSize: blob.size, type: 'image' }] });
        }, 'image/jpeg', 0.9);
      } catch (error) {
        finish(null, error instanceof Error ? error : cameraError(error));
      }
    };
    try {
      document.body.append(dialog); dialog.showModal(); cancel.focus();
      // Request only video. Rear-facing is a preference, not a requirement.
      navigator.mediaDevices.getUserMedia({ audio: false,
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1600 }, height: { ideal: 1200 } },
      }).then(async acquired => {
        // Permission can resolve after Cancel, navigation or unmount.
        if (finished) { acquired.getTracks().forEach(track => track.stop()); return; }
        stream = acquired;
        stream.getTracks().forEach(track => { track.onended = () => finish(null, cameraError(null)); });
        video.srcObject = stream;
        timer = setTimeout(() => finish(null, new Error('The camera preview did not start. Close other camera apps and retry.')), 15000);
        try { await video.play(); ready(); }
        catch (error) { finish(null, cameraError(error)); }
      }, error => finish(null, cameraError(error)));
    } catch (error) { finish(null, cameraError(error)); }
  });
}
