import type { Observation, Progression } from './api';

export function homeHealthSummary(records: ReadonlyArray<Pick<Observation, 'severity'>> | undefined) {
  if (!records || records.length < 2) return 'Insufficient data';
  if (records.every(record => record.severity === null)) {
    return 'Progression unavailable because severity was not measured.';
  }
  // Stored values (including zero and synthetic values) do not establish comparability.
  return 'Stored severity values are available. Open the health dashboard for comparison availability.';
}

export function recordLabels(record: Pick<Observation, 'disease' | 'severity' | 'confidence' | 'is_mock' | 'analysis_status'>) {
  const unanalysed = record.analysis_status === 'not_requested';
  return {
    disease: unanalysed || record.disease === null ? 'Disease not assessed' : record.disease,
    severity: unanalysed || record.severity === null ? 'Severity not measured' : `${record.severity}% ${record.is_mock ? 'synthetic demo severity' : 'recorded severity'}`,
    confidence: unanalysed || record.confidence === null ? 'Confidence unavailable' : `${Number(record.confidence.toFixed(1))}% ${record.is_mock ? 'synthetic confidence' : 'prediction score (uncalibrated)'}`,
    notice: record.is_mock ? 'DEVELOPMENT MOCK • Historical demo values, not a diagnosis.'
      : unanalysed ? 'Recorded without analysis. No disease or severity conclusion.'
      : record.analysis_status === 'legacy_unknown' ? 'Historical analysis • measurement provenance may be unavailable.'
      : 'Experimental AI prediction — not a validated diagnosis. This is not a whole-plant health assessment. Plant screening does not establish tomato identity or diagnostic accuracy; screening provenance is unavailable for historical records. Scores are uncalibrated and do not represent verified correctness. Even a high score or healthy label may be wrong. If symptoms disagree, seek local diagnostic advice.',
  };
}

export function progressionLabel(value: Progression) {
  if (value.status === 'insufficient_data') return 'Insufficient data';
  if (value.status === 'unavailable' || value.delta === null || !Number.isFinite(value.delta) || !value.policy_version || !value.measurement) return 'Progression unavailable';
  return value.status === 'improving' ? 'Improving' : value.status === 'worsening' ? 'Worsening' : value.status === 'stable' ? 'Stable' : 'Progression unavailable';
}

export function observationTime(value: string): string | null {
  if (!value.trim()) return null;
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/.test(value.trim())) {
    throw new Error('Use an ISO observation time with timezone, for example YYYY-MM-DDTHH:mm:ss+05:30, or leave it blank.');
  }
  const [year, month, day] = value.trim().slice(0, 10).split('-').map(Number);
  // JavaScript otherwise normalizes impossible dates such as February 30.
  const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
  if (year < 100 || month < 1 || month > 12 || day < 1 || day > daysInMonth) throw new Error('Observation date does not exist or is outside the supported range.');
  const date = new Date(value.trim());
  if (!Number.isFinite(date.getTime()) || date.getTime() > Date.now()) throw new Error('Observation time must be valid and must not be in the future.');
  return date.toISOString();
}

export function requestId() {
  // Identity only; no measurement or prediction is generated. Reuse for every retry.
  return `record-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
}

export function retryId(pendingId: string | null, create = requestId) {
  return pendingId ?? create();
}

export function captureObservation(date = new Date()) {
  const offset = -date.getTimezoneOffset();
  const sign = offset >= 0 ? '+' : '-';
  const zone = `${sign}${String(Math.floor(Math.abs(offset) / 60)).padStart(2, '0')}:${String(Math.abs(offset) % 60).padStart(2, '0')}`;
  return { observedAt: date.toISOString(), observedTimezone: `${Intl.DateTimeFormat().resolvedOptions().timeZone || 'Local'} (UTC${zone})` };
}

export function isTomato(plant: { crop_name?: string | null } | null) {
  return plant?.crop_name?.trim().toLowerCase() === 'tomato';
}

export function scanBlockers(state: {
  busy: boolean; selected: { crop_name?: string | null } | null; image: unknown;
  validation: { is_valid: boolean } | null;
  suitability?: { status: string };
  health: { capabilities: { tomato_analysis: boolean; record_only: boolean } } | null;
  pendingAnalysis: boolean | null; temperature: string; humidity: string; soilType: string; condition: string;
}, analyze: boolean): string[] {
  const reasons: string[] = [];
  if (state.busy) reasons.push('Please wait for the current operation.');
  if (state.pendingAnalysis !== null && state.pendingAnalysis !== analyze) reasons.push('Retry the same action or discard the draft after checking history.');
  if (!state.selected) reasons.push('Select a plant first.');
  if (analyze && !isTomato(state.selected)) reasons.push('Select or create a plant with crop set to tomato.');
  if (!state.health) reasons.push('Backend availability is unknown. Refresh connection status.');
  else if (analyze ? !state.health.capabilities.tomato_analysis : !state.health.capabilities.record_only) reasons.push(analyze ? 'Real tomato model unavailable. You can save without analysis.' : 'Record saving is unavailable.');
  if (!state.image) reasons.push('Select a real photo.');
  else if (!state.validation?.is_valid) reasons.push('Validate the selected image successfully.');
  if (analyze && state.suitability?.status !== 'accepted') reasons.push('Plant suitability must be accepted before disease analysis. Check the selected photo.');
  if (state.temperature.trim() && (!Number.isFinite(Number(state.temperature)) || Number(state.temperature) < -50 || Number(state.temperature) > 70)) reasons.push('Temperature must be between -50 and 70°C.');
  if (state.humidity.trim() && (!Number.isFinite(Number(state.humidity)) || Number(state.humidity) < 0 || Number(state.humidity) > 100)) reasons.push('Humidity must be between 0 and 100%.');
  if (state.soilType.trim().length > 100) reasons.push('Soil type must be 100 characters or fewer.');
  if ((!analyze || state.condition) && !['Dry', 'Normal', 'Wet'].includes(state.condition)) reasons.push('Select the observed soil condition.');
  return reasons;
}
