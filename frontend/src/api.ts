import { Platform } from 'react-native';
import type { ImagePickerAsset } from 'expo-image-picker';

export const API_URL = (process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '');
export type Plant = { id: string; name: string; created_at: string; crop_name: string | null };
export type SoilCondition = 'Dry' | 'Normal' | 'Wet';
export type Observation = {
  id: string; plant_id: string; image_path: string; created_at: string;
  disease: string | null; severity: number | null; confidence: number | null; predictor: string | null; is_mock: boolean;
  analysis_status: 'not_requested' | 'completed' | 'legacy_unknown';
  observed_at: string | null; tracking_ref: string | null; notes: string | null;
  request_id: string | null; duplicate_of: string | null; checkpoint_id: string | null;
  severity_source: string | null; severity_method: string | null; severity_version: string | null; severity_scale: string | null;
  temperature: number; humidity: number; soil_type: string; soil_condition: SoilCondition;
};
export type ValidationResult = { is_valid: boolean; reason: string; message: string };
export type Prediction = { disease: string; severity: number | null; confidence: number; predictor: string; is_mock: boolean };
export type Progression = {
  status: 'unavailable' | 'insufficient_data' | 'improving' | 'stable' | 'worsening';
  reason: string | null; message: string; delta: number | null; tracking_ref: string | null;
  previous_id: string | null; latest_id: string | null;
  previous_observed_at: string | null; latest_observed_at: string | null;
  policy_version: string | null; measurement: Record<string, string> | null;
};
export type Health = { status: string; prediction_mode: string; is_mock: boolean;
  capabilities: { record_only: boolean; validated_analysis: boolean; severity_measurement: boolean; health_progression: boolean };
  analysis_message: string };
export type RecordDetails = { request_id: string; observed_at: string | null; tracking_ref: string | null; notes: string | null };
export class ImageValidationError extends Error {
  constructor(public validation: ValidationResult) { super(validation.message); }
}
export type Environment = Pick<Observation, 'temperature' | 'humidity' | 'soil_type' | 'soil_condition'>;

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(`${API_URL}${path}`, { ...options, signal: controller.signal });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      if (body.detail?.is_valid === false) throw new ImageValidationError(body.detail);
      throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status}). Check your input.`);
    }
    return await response.json() as T;
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw new Error('Request timed out. Refresh history before retrying; the scan may have saved.');
    if (error instanceof TypeError) throw new Error(`Cannot reach ${API_URL}. Start the backend and check EXPO_PUBLIC_API_URL and your network.`);
    throw error;
  } finally { clearTimeout(timeout); }
}

async function imageForm(image: ImagePickerAsset): Promise<FormData> {
  const form = new FormData();
  if (Platform.OS === 'web') {
    const blob = await (await fetch(image.uri)).blob();
    form.append('image', blob, image.fileName || 'leaf.jpg');
  } else {
    // React Native's FormData supports URI-backed files; browser typings do not.
    form.append('image', { uri: image.uri, name: image.fileName || 'leaf.jpg', type: image.mimeType || 'image/jpeg' } as unknown as Blob);
  }
  return form;
}

export const api = {
  health: () => request<Health>('/health'),
  plants: () => request<Plant[]>('/plants'),
  addPlant: (name: string, cropName: string | null = null) => request<Plant>('/plants', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, crop_name: cropName }),
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
  async predict(image: ImagePickerAsset) {
    return request<Prediction>('/predict', { method: 'POST', body: await imageForm(image) });
  },
  async scan(id: string, image: ImagePickerAsset, environment: Environment) {
    const form = await imageForm(image);
    for (const [key, value] of Object.entries(environment)) form.append(key, String(value));
    return request<Observation>(`/plants/${id}/observations`, { method: 'POST', body: form });
  },
};
