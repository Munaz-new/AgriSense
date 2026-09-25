"""Sanity CLI safety/portability checks; no training or optimizer updates."""
from dataclasses import replace
import sys
from types import SimpleNamespace

import pytest

from model.agrisense_model.config import Config
from model.sanity import peak_rss_mib, validate_inputs


@pytest.fixture
def paths(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    manifest = tmp_path / 'manifest.json'
    audit = tmp_path / 'audit.json'
    manifest.write_text('{}')
    audit.write_text('{}')
    return (Config(dataset_path=str(source), manifest_path=str(manifest)),
            audit, tmp_path / 'reports' / 'sanity.json')


def test_report_inside_source_is_rejected_without_writing(paths):
    config, audit, _ = paths
    output = config.path('dataset_path') / 'report.json'
    with pytest.raises(RuntimeError, match='outside the source'):
        validate_inputs(config, audit, output)
    assert not output.exists()


def test_existing_report_is_preserved(paths):
    config, audit, output = paths
    output.parent.mkdir()
    output.write_text('previous evidence')
    with pytest.raises(RuntimeError, match='overwrite'):
        validate_inputs(config, audit, output)
    assert output.read_text() == 'previous evidence'


@pytest.mark.parametrize('missing', ['manifest', 'audit'])
def test_missing_preparation_is_rejected(paths, missing):
    config, audit, output = paths
    (config.path('manifest_path') if missing == 'manifest' else audit).unlink()
    with pytest.raises(RuntimeError, match='required'):
        validate_inputs(config, audit, output)
    assert not output.exists()


def test_reordered_classes_are_rejected(paths):
    config, audit, output = paths
    config = replace(config, class_names=tuple(reversed(config.class_names)))
    with pytest.raises(RuntimeError, match='ordered eleven'):
        validate_inputs(config, audit, output)


def test_valid_paths_do_not_create_output(paths):
    config, audit, output = paths
    validate_inputs(config, audit, output)
    assert not output.parent.exists()


def test_memory_measurement_unavailable_on_windows(monkeypatch):
    monkeypatch.setitem(sys.modules, 'resource', None)
    assert peak_rss_mib() is None


@pytest.mark.parametrize(('platform', 'rss'), [('linux', 1024), ('darwin', 1024 * 1024)])
def test_memory_units(monkeypatch, platform, rss):
    monkeypatch.setitem(sys.modules, 'resource', SimpleNamespace(
        RUSAGE_SELF=0, getrusage=lambda _: SimpleNamespace(ru_maxrss=rss)))
    monkeypatch.setattr(sys, 'platform', platform)
    assert peak_rss_mib() == 1.0
