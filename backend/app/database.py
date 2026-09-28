import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1
LEGACY_COLUMNS = ('id', 'plant_id', 'image_path', 'created_at', 'disease', 'severity',
                  'confidence', 'predictor', 'is_mock', 'temperature', 'humidity',
                  'soil_type', 'soil_condition')


@contextmanager
def connect(path: Path):
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize(path: Path):
    """Transactional migration of pre-Phase-5 databases; never infer old metadata."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError('Database schema is newer than this application.')
        if version == SCHEMA_VERSION:
            return
        db.execute('''CREATE TABLE IF NOT EXISTS plants (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL)''')
        if 'crop_name' not in {row['name'] for row in db.execute('PRAGMA table_info(plants)')}:
            db.execute('ALTER TABLE plants ADD COLUMN crop_name TEXT')
        old_columns = [row['name'] for row in db.execute('PRAGMA table_info(observations)')]
        if old_columns and old_columns != list(LEGACY_COLUMNS):
            raise RuntimeError('Unrecognized legacy observations schema; migration refused.')
        db.execute('''CREATE TABLE observations_v1 (
            id TEXT PRIMARY KEY,
            plant_id TEXT NOT NULL REFERENCES plants(id),
            image_path TEXT NOT NULL, created_at TEXT NOT NULL,
            disease TEXT, severity REAL CHECK(severity BETWEEN 0 AND 100),
            confidence REAL CHECK(confidence BETWEEN 0 AND 100), predictor TEXT,
            is_mock INTEGER NOT NULL CHECK(is_mock IN (0, 1)),
            temperature REAL NOT NULL, humidity REAL NOT NULL,
            soil_type TEXT NOT NULL, soil_condition TEXT NOT NULL,
            observed_at TEXT, tracking_ref TEXT, notes TEXT,
            image_sha256 TEXT, request_id TEXT, request_fingerprint TEXT,
            analysis_status TEXT NOT NULL DEFAULT 'legacy_unknown'
                CHECK(analysis_status IN ('not_requested', 'completed', 'legacy_unknown')),
            checkpoint_id TEXT, severity_source TEXT, severity_method TEXT,
            severity_version TEXT, severity_scale TEXT,
            duplicate_of TEXT REFERENCES observations_v1(id),
            UNIQUE(plant_id, request_id),
            CHECK(analysis_status != 'not_requested' OR
                (disease IS NULL AND severity IS NULL AND confidence IS NULL
                 AND predictor IS NULL AND is_mock = 0))
        )''')
        if old_columns:
            columns = ', '.join(LEGACY_COLUMNS)
            db.execute(f'INSERT INTO observations_v1 ({columns}) SELECT {columns} FROM observations')
            db.execute('DROP TABLE observations')
        db.execute('ALTER TABLE observations_v1 RENAME TO observations')
        db.execute('''CREATE INDEX observations_by_plant ON observations
            (plant_id, COALESCE(observed_at, created_at), created_at, id)''')
        db.execute('CREATE INDEX observations_by_image ON observations(plant_id, image_sha256)')
        db.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')


def insert_observation(db, observation):
    # Keys originate in server code, never in a submitted JSON object.
    columns = ', '.join(observation)
    parameters = ', '.join(':' + key for key in observation)
    db.execute(f'INSERT INTO observations ({columns}) VALUES ({parameters})', observation)
