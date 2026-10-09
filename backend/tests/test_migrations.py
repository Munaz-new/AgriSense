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
        assert db.execute('PRAGMA user_version').fetchone()[0] == 3


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


def test_v1_adds_timezone_without_changing_existing_records(tmp_path):
    path = tmp_path / 'v1.db'
    initialize(path)
    with connect(path) as db:
        db.execute('ALTER TABLE observations DROP COLUMN observed_timezone')
        db.execute('PRAGMA user_version = 1')
        db.execute("INSERT INTO plants VALUES ('p', 'Original', '2025-01-01', NULL)")
    initialize(path)
    initialize(path)
    with connect(path) as db:
        assert db.execute('SELECT name FROM plants').fetchone()[0] == 'Original'
        assert 'observed_timezone' in [r['name'] for r in db.execute('PRAGMA table_info(observations)')]
        assert db.execute('PRAGMA user_version').fetchone()[0] == 3


def test_v2_optional_environment_migration_preserves_rows_indexes_and_self_links(tmp_path):
    path = tmp_path / 'v2.db'
    with sqlite3.connect(path) as db:
        db.executescript('''
            CREATE TABLE observations (
                id TEXT PRIMARY KEY, temperature REAL NOT NULL, humidity REAL NOT NULL,
                soil_type TEXT NOT NULL, soil_condition TEXT NOT NULL,
                duplicate_of TEXT REFERENCES observations(id));
            CREATE INDEX observations_by_image ON observations(duplicate_of);
            INSERT INTO observations VALUES ('first', 25, 60, 'Loam', 'Dry', NULL);
            INSERT INTO observations VALUES ('second', 26, 61, 'Loam', 'Wet', 'first');
            PRAGMA user_version = 2;
        ''')
        before = db.execute('SELECT * FROM observations ORDER BY id').fetchall()
    initialize(path)
    initialize(path)
    with connect(path) as db:
        assert [tuple(r) for r in db.execute('SELECT * FROM observations ORDER BY id')] == before
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert all(r['notnull'] == 0 for r in db.execute('PRAGMA table_info(observations)') if r['name'] in {'temperature', 'humidity', 'soil_type', 'soil_condition'})
        assert db.execute("SELECT name FROM sqlite_master WHERE name='observations_by_image'").fetchone()
        db.execute("INSERT INTO observations(id) VALUES ('optional')")
