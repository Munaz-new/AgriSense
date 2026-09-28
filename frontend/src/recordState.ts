import type { Observation, Progression } from './api';

export function recordLabels(record: Pick<Observation, 'disease' | 'severity' | 'confidence' | 'is_mock' | 'analysis_status'>) {
  const unanalysed = record.analysis_status === 'not_requested';
  return {
    disease: unanalysed || record.disease === null ? 'Disease not assessed' : record.disease,
    severity: unanalysed || record.severity === null ? 'Severity not measured' : `${record.severity}% ${record.is_mock ? 'synthetic demo severity' : 'recorded severity'}`,
    confidence: unanalysed || record.confidence === null ? 'Confidence unavailable' : `${record.confidence}% ${record.is_mock ? 'synthetic confidence' : 'model confidence (uncalibrated)'}`,
    notice: record.is_mock ? 'DEVELOPMENT MOCK • Historical demo values, not a diagnosis.'
      : unanalysed ? 'Recorded without analysis. No disease or severity conclusion.'
      : record.analysis_status === 'legacy_unknown' ? 'Historical analysis • measurement provenance may be unavailable.'
      : 'Stored analysis result • not a whole-plant health assessment.',
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
