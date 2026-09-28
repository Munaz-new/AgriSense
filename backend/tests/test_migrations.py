"""Migrations run against disposable databases only."""
import sqlite3

import pytest

from app.database import connect, initialize


def test_fresh_schema_idempotence_and_foreign_keys(tmp_path):
    path = tmp_path / 'new.db'
    initialize(path)
    with connect(path) as db:
        before = [tuple(row) for row in db.execute('SELECT * FROM sqlite_master ORDER BY name')]
    initialize(path)
    with connect(path) as db:
        assert [tuple(row) for row in db.execute('SELECT * FROM sqlite_master ORDER BY name')] == before
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1


def test_unknown_schema_rolls_back_all_changes(tmp_path):
    path = tmp_path / 'unknown.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE plants(id TEXT PRIMARY KEY, name TEXT, created_at TEXT)')
        db.execute('CREATE TABLE observations(id TEXT, custom_data TEXT)')
        db.execute("INSERT INTO observations VALUES ('keep', 'evidence')")
    with pytest.raises(RuntimeError, match='Unrecognized'):
        initialize(path)
    with connect(path) as db:
        assert 'crop_name' not in [row['name'] for row in db.execute('PRAGMA table_info(plants)')]
        assert tuple(db.execute('SELECT * FROM observations').fetchone()) == ('keep', 'evidence')
        assert db.execute('PRAGMA user_version').fetchone()[0] == 0


def test_future_schema_is_refused_without_changes(tmp_path):
    path = tmp_path / 'future.db'
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA user_version = 999')
    with pytest.raises(RuntimeError, match='newer'):
        initialize(path)
    with connect(path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 999
        assert db.execute('SELECT name FROM sqlite_master').fetchall() == []
