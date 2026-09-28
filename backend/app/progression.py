"""Measurement comparison only. No approved severity policy ships with Phase 5."""
from dataclasses import dataclass
from datetime import datetime
import math


@dataclass(frozen=True)
class ComparisonPolicy:
    version: str
    source: str
    method: str
    measurement_version: str
    scale: str
    tolerance: float

    def __post_init__(self):
        if (not all((self.version, self.source, self.method, self.measurement_version, self.scale))
                or not math.isfinite(self.tolerance) or self.tolerance < 0):
            raise ValueError('A complete, explicitly validated comparison policy is required.')


def progression(rows, tracking_ref=None, policy=None):
    result = dict(status='unavailable', reason=None, message=None, previous_id=None,
                  latest_id=None, previous_observed_at=None, latest_observed_at=None,
                  delta=None, policy_version=None, measurement=None, tracking_ref=tracking_ref)

    def unavailable(reason, message, insufficient=False):
        return dict(result, status='insufficient_data' if insufficient else 'unavailable',
                    reason=reason, message=message)

    selected = [row for row in rows if row.get('tracking_ref') == tracking_ref] if tracking_ref else rows
    if len(selected) < 2:
        return unavailable('too_few_observations', 'At least two comparable observations are required.', True)
    if not tracking_ref:
        return unavailable('tracking_reference_required', 'Select the same leaf or site reference to assess comparability.')
    # API supplies chronological rows. Never skip the latest record to find a nicer pair.
    previous, latest = selected[-2:]
    result.update(previous_id=previous['id'], latest_id=latest['id'],
                  previous_observed_at=previous.get('observed_at'), latest_observed_at=latest.get('observed_at'))
    if previous['plant_id'] != latest['plant_id']:
        return unavailable('different_plants', 'Observations belong to different plants.')
    if any(row['is_mock'] for row in (previous, latest)):
        return unavailable('synthetic_observations', 'Synthetic demo values cannot establish plant health progression.')
    if any(row.get('severity') is None for row in (previous, latest)):
        return unavailable('severity_unavailable', 'Severity has not been measured. Disease classification alone does not measure severity.')
    if any(not isinstance(row['severity'], (int, float)) or isinstance(row['severity'], bool)
           or not math.isfinite(row['severity']) or not 0 <= row['severity'] <= 100 for row in (previous, latest)):
        return unavailable('invalid_measurement', 'Severity measurements are invalid.')
    try:
        times = [datetime.fromisoformat(row['observed_at']) for row in (previous, latest)]
        if any(value.tzinfo is None for value in times) or times[0] >= times[1]:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return unavailable('observation_time_unavailable', 'Distinct, ordered observation times are required; save times are insufficient.')
    if (any(row.get('duplicate_of') for row in (previous, latest))
            or not all(row.get('image_sha256') for row in (previous, latest))
            or previous['image_sha256'] == latest['image_sha256']):
        return unavailable('distinct_evidence_required', 'Distinct recorded image evidence is required.')
    keys = ('disease', 'severity_source', 'severity_method', 'severity_version', 'severity_scale')
    if any(not previous.get(key) or previous.get(key) != latest.get(key) for key in keys):
        return unavailable('incompatible_measurements', 'Disease context and severity measurement provenance must match.')
    if (previous.get('checkpoint_id') != latest.get('checkpoint_id')
            or (latest['severity_source'] == 'model' and not latest.get('checkpoint_id'))):
        return unavailable('incompatible_models', 'Model versions differ; these measurements are not comparable.')
    if policy is None:
        return unavailable('comparison_policy_unavailable', 'No validated severity comparison policy is configured.')
    expected = (policy.source, policy.method, policy.measurement_version, policy.scale)
    if tuple(latest[key] for key in keys[1:]) != expected:
        return unavailable('comparison_policy_mismatch', 'The comparison policy does not cover these measurements.')
    delta = latest['severity'] - previous['severity']
    status = 'improving' if delta < -policy.tolerance else 'worsening' if delta > policy.tolerance else 'stable'
    return dict(result, status=status, delta=delta, policy_version=policy.version,
                measurement={key: latest[key] for key in keys},
                message='Change in the recorded severity measurements; not a whole-plant diagnosis.')
