import { Platform } from 'react-native';
import { File } from 'expo-file-system';
import type { ImagePickerAsset } from 'expo-image-picker';
import { nativeMultipartUpload, NativeUploadError } from './nativeMultipartUpload';

export const API_URL = (process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000').trim().replace(/\/+$/, '');
export class ApiError extends Error {
  constructor(public code: string, message: string) { super(message); }
}

function checkApiUrl() {
  let url: URL;
  try { url = new URL(API_URL); } catch { throw new ApiError('api_configuration', 'Invalid EXPO_PUBLIC_API_URL. Use http://YOUR_LAPTOP_LAN_IP:8000 and restart Expo with --clear.'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new ApiError('api_configuration', 'EXPO_PUBLIC_API_URL must be an HTTP(S) backend URL without credentials, query or fragment. Restart Expo with --clear after changing it.');
  }
  if (Platform.OS !== 'web' && /^(localhost\.?|127\..*|0\.0\.0\.0|\[::1\]|\[::\])$/i.test(url.hostname)) {
    throw new ApiError('api_configuration', 'Backend configuration error: localhost points to this phone. Set EXPO_PUBLIC_API_URL to http://YOUR_LAPTOP_LAN_IP:8000, restart Expo with --lan --clear, and reload Expo Go.');
  }
}
export type Plant = { id: string; name: string; created_at: string; crop_name: string | null };
export type SoilCondition = 'Dry' | 'Normal' | 'Wet';
export type Observation = {
  id: string; plant_id: string; image_path: string; created_at: string;
  prediction_score: number | null; disease: string | null; severity: number | null; confidence: number | null; predictor: string | null; is_mock: boolean;
  analysis_status: 'not_requested' | 'completed' | 'legacy_unknown';
  observed_at: string | null; observed_timezone?: string | null; tracking_ref: string | null; notes: string | null;
  request_id: string | null; duplicate_of: string | null; checkpoint_id: string | null;
  severity_source: string | null; severity_method: string | null; severity_version: string | null; severity_scale: string | null;
  temperature: number | null; humidity: number | null; soil_type: string | null; soil_condition: SoilCondition | null;
};
export type ValidationResult = { is_valid: boolean; reason: string; message: string };
export type SuitabilityState = { status: 'not_checked' | 'checking' | 'accepted' | 'rejected' | 'inconclusive' | 'unavailable'; message: string };
export class PlantSuitabilityError extends Error {
  constructor(public code: string, message: string) { super(message); }
}
export type Prediction = { prediction_score: number | null; disease: string; severity: number | null; confidence: number; predictor: string; is_mock: boolean };
export type Progression = {
  status: 'unavailable' | 'insufficient_data' | 'improving' | 'stable' | 'worsening';
  reason: string | null; message: string; delta: number | null; tracking_ref: string | null;
  previous_id: string | null; latest_id: string | null;
  previous_observed_at: string | null; latest_observed_at: string | null;
  policy_version: string | null; measurement: Record<string, string> | null;
};
export type Health = { status: string; prediction_mode: string; is_mock: boolean;
  capabilities: { record_only: boolean; tomato_analysis: boolean; technical_image_validation: boolean; plant_content_screening: boolean; severity_measurement: boolean; health_progression: boolean };
  analysis_message: string };
export type RecordDetails = { request_id: string; observed_at: string | null; observed_timezone?: string | null; tracking_ref: string | null; notes: string | null };
export class ImageValidationError extends Error {
  constructor(public validation: ValidationResult) { super(validation.message); }
}
export type Environment = Pick<Observation, 'temperature' | 'humidity' | 'soil_type' | 'soil_condition'>;

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  checkApiUrl();
  const route = path.split('?')[0].replace(/\/plants\/[^/]+/, '/plants/:id');
  const diagnostic = (state: string, status?: number, reference?: string) => {
    if (__DEV__) console.info('[AgriSense request]', { route, state, status, reference });
  };
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    diagnostic('started');
    const response = Platform.OS !== 'web' && options?.body instanceof FormData
      ? await nativeMultipartUpload(`${API_URL}${path}`, options.body, controller.signal)
      : await fetch(`${API_URL}${path}`, { ...options, signal: controller.signal });
    const reference = response.headers?.get('x-agrisense-request-id') || undefined;
    diagnostic('response', response.status, reference);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      if (body.detail?.is_valid === false) throw new ImageValidationError(body.detail);
      if (['non_plant_image', 'plant_content_uncertain', 'plant_screening_unavailable'].includes(body.detail?.code)) {
        throw new PlantSuitabilityError(body.detail.code, body.detail.message);
      }
      const detail = typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail)
        ? body.detail.map((item: { loc?: string[]; msg?: string }) => `${item.loc?.at(-1) || 'Input'}: ${item.msg || 'invalid value'}`).join('; ')
        : body.detail?.message;
      throw new ApiError(body.detail?.code || 'http_error',
        `${detail || (response.status === 413 ? 'Upload exceeds the server size limit. Choose a smaller photo.' : response.status >= 500 ? 'Backend failed to complete the request. Check its logs and retry.' : 'Request rejected. Check the selected photo and form fields.')} (HTTP ${response.status}, ${path})`);
    }
    try { return await response.json() as T; }
    catch (error) {
      if (error instanceof Error && error.name === 'AbortError') throw error;
      throw new ApiError('invalid_response', `Backend returned an invalid response for ${path}. Check the API address and backend logs. If saving, check history before retrying.`);
    }
  } catch (error) {
    if (error instanceof NativeUploadError) throw new ApiError('upload_failed', error.message);
    diagnostic(error instanceof ApiError || error instanceof PlantSuitabilityError ? error.code : error instanceof ImageValidationError ? 'image_validation_failed' : error instanceof Error && error.name === 'AbortError' ? 'timeout' : 'request_failed');
    const saving = options?.method === 'POST' && (path === '/plants' || /\/plants\/[^/]+\/(records|observations)$/.test(path));
    const recovery = saving ? ' Refresh history before retrying; the save may have completed. Retry the same submission.' : ' Refresh connection status and retry.';
    if (error instanceof Error && error.name === 'AbortError') throw new ApiError('request_timeout', `Request timed out after 30 seconds (${path}).${recovery}`);
    if (error instanceof TypeError) throw new ApiError(options?.body instanceof FormData ? 'upload_failed' : 'backend_unreachable',
      `${options?.body instanceof FormData ? 'Photo upload failed; backend receipt is unknown. ' : ''}Cannot reach ${API_URL} (${path}). Open ${API_URL}/health on the phone. Check for a changed laptop IP, same Wi-Fi, backend --host 0.0.0.0, firewall and EXPO_PUBLIC_API_URL; restart Expo with --clear after changing it.${recovery}`);
    throw error;
  } finally { clearTimeout(timeout); }
}

export async function imageBlob(image: ImagePickerAsset): Promise<Blob> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(image.uri, { signal: controller.signal });
    if (response.ok === false) throw new Error('The selected photo could not be read. Select it again.');
    return await response.blob();
  } catch {
    throw new Error('The selected photo is unavailable or took too long to read. Select it again.');
  } finally { clearTimeout(timeout); }
}

async function imageForm(image: ImagePickerAsset): Promise<FormData> {
  checkApiUrl();
  const form = new FormData();
  if (Platform.OS === 'web') {
    const blob = await imageBlob(image);
    form.append('image', blob, image.fileName || 'leaf.jpg');
  } else {
    // Check the actual cached file on every attempt: picker metadata can outlive it.
    if (!/^(file|content):\/\//.test(image.uri)) throw new ApiError('photo_unavailable', 'The native photo URI is unavailable. Retake the photo or choose it again from Gallery.');
    let file: File;
    try {
      file = new File(image.uri);
      if (!file.exists || file.size === 0) throw new Error('missing');
    } catch { throw new ApiError('photo_unavailable', 'The photo file is missing, empty or unreadable. Retake it or choose it again from Gallery. If a save was pending, check history first.'); }
    if (file.size > 10 * 1024 * 1024) throw new ApiError('upload_too_large', 'The photo is larger than 10 MB. Choose a smaller photo.');
    const extension = (image.fileName || image.uri.split('?')[0]).split('.').pop()?.toLowerCase();
    const types: Record<string, string> = { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', webp: 'image/webp', heic: 'image/heic', heif: 'image/heif' };
    const type = image.mimeType || file.type || types[extension || ''] || 'application/octet-stream';
    const suffix = Object.keys(types).find(key => types[key] === type) || 'bin';
    // React Native's FormData supports URI-backed files; browser typings do not.
    form.append('image', { uri: image.uri, name: image.fileName || `leaf.${suffix}`, type } as unknown as Blob);
  }
  return form;
}

export const api = {
  health: () => request<Health>('/health'),
  plants: () => request<Plant[]>('/plants'),
  addPlant: (name: string, cropName: string | null = null, requestId?: string) => request<Plant>('/plants', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, crop_name: cropName, request_id: requestId }),
  }),
  updatePlantCrop: (id: string, cropName: string | null) => request<Plant>(`/plants/${id}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ crop_name: cropName }),
  }),
  observations: (id: string) => request<Observation[]>(`/plants/${id}/observations`),
  progression: (id: string, trackingRef = '') => request<Progression>(`/plants/${id}/progression${trackingRef.trim() ? `?tracking_ref=${encodeURIComponent(trackingRef.trim())}` : ''}`),
  async record(id: string, image: ImagePickerAsset, environment: Environment, details: RecordDetails) {
    const form = await imageForm(image);
    for (const [key, value] of Object.entries({ ...environment, ...details })) {
      if (value !== null) form.append(key, String(value));
    }
    return request<Observation>(`/plants/${id}/records`, { method: 'POST', body: form });
  },
  async validateImage(image: ImagePickerAsset) {
    return request<ValidationResult>('/validate-image', { method: 'POST', body: await imageForm(image) });
  },
  async checkSuitability(image: ImagePickerAsset) {
    return request<{ outcome: 'plant'; message: string }>('/check-plant-suitability', { method: 'POST', body: await imageForm(image) });
  },
  async predict(image: ImagePickerAsset) {
    return request<Prediction>('/predict', { method: 'POST', body: await imageForm(image) });
  },
  async scan(id: string, image: ImagePickerAsset, environment: Environment, details: RecordDetails) {
    const form = await imageForm(image);
    for (const [key, value] of Object.entries({ ...environment, ...details })) {
      if (value !== null) form.append(key, String(value));
    }
    return request<Observation>(`/plants/${id}/observations`, { method: 'POST', body: form });
  },
};
