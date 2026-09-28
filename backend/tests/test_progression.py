"""Pure comparison fixtures only. Numbers are not plant measurements or model results."""
from copy import deepcopy

import pytest

from app.progression import ComparisonPolicy, progression


@pytest.fixture
def rows():
    common = dict(plant_id='fixture-plant', tracking_ref='fixture-leaf', is_mock=False,
                  disease='fixture-context', severity_source='test-only', severity_method='fixture-method',
                  severity_version='fixture-v1', severity_scale='fixture-percent', checkpoint_id=None,
                  duplicate_of=None)
    return [dict(common, id='a', severity=20, image_sha256='fixture-a', observed_at='2025-01-01T00:00:00Z'),
            dict(common, id='b', severity=20, image_sha256='fixture-b', observed_at='2025-01-02T00:00:00Z')]


@pytest.fixture
def policy():
    return ComparisonPolicy('test-policy-only', 'test-only', 'fixture-method', 'fixture-v1', 'fixture-percent', 2)


@pytest.mark.parametrize('latest,status', [(17, 'improving'), (18, 'stable'), (20, 'stable'), (22, 'stable'), (23, 'worsening')])
def test_comparison_math_requires_explicit_test_policy(rows, policy, latest, status):
    rows[-1]['severity'] = latest
    result = progression(rows, 'fixture-leaf', policy)
    assert result['status'] == status and result['delta'] == latest - 20
    assert result['previous_id'] == 'a' and result['latest_id'] == 'b'
    assert result['policy_version'] == 'test-policy-only'
    assert result['measurement']['severity_source'] == 'test-only'


def test_no_policy_never_claims_progression(rows):
    result = progression(rows, 'fixture-leaf')
    assert result['reason'] == 'comparison_policy_unavailable'
    assert result['status'] == 'unavailable' and result['delta'] is None


@pytest.mark.parametrize('change,reason', [
    ({'plant_id': 'different'}, 'different_plants'),
    ({'is_mock': True}, 'synthetic_observations'),
    ({'severity': None}, 'severity_unavailable'),
    ({'severity': float('nan')}, 'invalid_measurement'),
    ({'severity': 101}, 'invalid_measurement'),
    ({'severity': True}, 'invalid_measurement'),
    ({'observed_at': None}, 'observation_time_unavailable'),
    ({'observed_at': '2025-01-01T00:00:00Z'}, 'observation_time_unavailable'),
    ({'observed_at': '2025-01-02T00:00:00'}, 'observation_time_unavailable'),
    ({'image_sha256': 'fixture-a'}, 'distinct_evidence_required'),
    ({'image_sha256': None}, 'distinct_evidence_required'),
    ({'duplicate_of': 'older'}, 'distinct_evidence_required'),
    ({'disease': 'different'}, 'incompatible_measurements'),
    ({'severity_source': None}, 'incompatible_measurements'),
    ({'severity_version': 'v2'}, 'incompatible_measurements'),
    ({'checkpoint_id': 'different-model'}, 'incompatible_models'),
])
def test_ineligible_observations_never_get_direction(rows, policy, change, reason):
    rows[-1].update(change)
    result = progression(rows, 'fixture-leaf', policy)
    assert result['reason'] == reason
    assert result['status'] == 'unavailable' and result['delta'] is None


def test_reference_and_sample_coverage(rows, policy):
    assert progression([], policy=policy)['status'] == 'insufficient_data'
    assert progression(rows[:1], 'fixture-leaf', policy)['status'] == 'insufficient_data'
    assert progression(rows, policy=policy)['reason'] == 'tracking_reference_required'
    assert progression(rows, 'missing', policy)['status'] == 'insufficient_data'


def test_latest_ineligible_is_not_skipped(rows, policy):
    latest = dict(deepcopy(rows[-1]), id='latest', severity=None, observed_at='2025-01-03T00:00:00Z')
    result = progression(rows + [latest], 'fixture-leaf', policy)
    assert result['latest_id'] == 'latest' and result['reason'] == 'severity_unavailable'


def test_policy_provenance_must_match(rows, policy):
    for row in rows:
        row['severity_method'] = 'uncovered-method'
    assert progression(rows, 'fixture-leaf', policy)['reason'] == 'comparison_policy_mismatch'


@pytest.mark.parametrize('tolerance', [-1, float('nan'), float('inf')])
def test_invalid_policy_refused(tolerance):
    with pytest.raises(ValueError):
        ComparisonPolicy('test-only', 'test-only', 'test-only', 'test-only', 'test-only', tolerance)
