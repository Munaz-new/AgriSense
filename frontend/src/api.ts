import { Platform } from 'react-native';
import type { ImagePickerAsset } from 'expo-image-picker';

export const API_URL = (process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '');
export type Plant = { id: string; name: string; created_at: string };
export type SoilCondition = 'Dry' | 'Normal' | 'Wet';
export type Observation = {
  id: string; plant_id: string; image_path: string; created_at: string;
  disease: string; severity: number | null; confidence: number; predictor: string; is_mock: boolean;
  temperature: number; humidity: number; soil_type: string; soil_condition: SoilCondition;
};
export type ValidationResult = { is_valid: boolean; reason: string; message: string };
export type Prediction = Pick<Observation, 'disease' | 'severity' | 'confidence' | 'predictor' | 'is_mock'>;
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
  health: () => request<{ status: string; prediction_mode: string; is_mock: boolean }>('/health'),
  plants: () => request<Plant[]>('/plants'),
  addPlant: (name: string) => request<Plant>('/plants', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }),
  }),
  observations: (id: string) => request<Observation[]>(`/plants/${id}/observations`),
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
