import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def connect(path: Path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS plants (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS observations (
                id TEXT PRIMARY KEY,
                plant_id TEXT NOT NULL REFERENCES plants(id),
                image_path TEXT NOT NULL, created_at TEXT NOT NULL,
                disease TEXT NOT NULL, severity REAL,
                confidence REAL NOT NULL, predictor TEXT NOT NULL,
                is_mock INTEGER NOT NULL,
                temperature REAL NOT NULL, humidity REAL NOT NULL,
                soil_type TEXT NOT NULL, soil_condition TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS observations_by_plant
            ON observations(plant_id, created_at);
        """)

        # Phase 2B: classification has no severity labels. Preserve old rows while
        # making severity nullable; SQLite requires rebuilding this table.
        columns = db.execute("PRAGMA table_info(observations)").fetchall()
        if any(row['name'] == 'severity' and row['notnull'] for row in columns):
            db.execute('BEGIN')
            db.execute("""CREATE TABLE observations_nullable (
                id TEXT PRIMARY KEY,
                plant_id TEXT NOT NULL REFERENCES plants(id),
                image_path TEXT NOT NULL, created_at TEXT NOT NULL,
                disease TEXT NOT NULL, severity REAL,
                confidence REAL NOT NULL, predictor TEXT NOT NULL,
                is_mock INTEGER NOT NULL,
                temperature REAL NOT NULL, humidity REAL NOT NULL,
                soil_type TEXT NOT NULL, soil_condition TEXT NOT NULL
            )""")
            db.execute("INSERT INTO observations_nullable SELECT * FROM observations")
            db.execute("DROP TABLE observations")
            db.execute("ALTER TABLE observations_nullable RENAME TO observations")
            db.execute("CREATE INDEX observations_by_plant ON observations(plant_id, created_at)")
