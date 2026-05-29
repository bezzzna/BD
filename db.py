import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "main.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id_event INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                event_date TEXT,
                id_program INTEGER,
                place TEXT,
                participants_count INTEGER,
                FOREIGN KEY (id_program) REFERENCES programs(id_program)
            );

            CREATE TABLE IF NOT EXISTS participant_programs (
                id_participant INTEGER NOT NULL,
                id_program INTEGER NOT NULL,
                PRIMARY KEY (id_participant, id_program),
                FOREIGN KEY (id_participant)
                    REFERENCES programParticipants(id_participant) ON DELETE CASCADE,
                FOREIGN KEY (id_program)
                    REFERENCES programs(id_program) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS cms_programs (
                cms_id INTEGER PRIMARY KEY,
                document_id TEXT UNIQUE,
                title TEXT,
                category TEXT,
                start_date TEXT,
                end_date TEXT,
                max_participants INTEGER,
                registration_open INTEGER,
                raw_json TEXT NOT NULL,
                synced_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS cms_applications (
                cms_id INTEGER PRIMARY KEY,
                document_id TEXT UNIQUE,
                application_status TEXT,
                confirmation_status TEXT,
                snapshot_name TEXT,
                snapshot_email TEXT,
                grade INTEGER,
                program_document_id TEXT,
                program_title TEXT,
                raw_json TEXT NOT NULL,
                synced_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS cms_application_programs (
                application_id INTEGER NOT NULL,
                program_document_id TEXT NOT NULL,
                PRIMARY KEY (application_id, program_document_id),
                FOREIGN KEY (application_id) REFERENCES cms_applications(cms_id) ON DELETE CASCADE
            );
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO participant_programs (id_participant, id_program)
            SELECT id_participant, id_program
            FROM programParticipants
            WHERE id_program IS NOT NULL
            """
        )
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        if count == 0:
            conn.executemany(
                """
                INSERT INTO events (name, event_date, id_program, place, participants_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    ("Олимпиада по робототехнике", "12.04.2026", None, "Корпус А, зал 101", 32),
                    ("Математический турнир", "25.04.2026", None, "Корпус Б, зал 205", 28),
                    ("Лабораторный день «Физика в действии»", "10.05.2026", None, "Научная лаборатория", 22),
                    ("Химический фестиваль", "18.05.2026", None, "Корпус А, актовый зал", 40),
                ],
            )


def row_to_dict(row):
    return dict(row) if row else None
