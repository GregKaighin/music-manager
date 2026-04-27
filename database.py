import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class Track:
    file_path: str
    file_name: str
    file_size: int
    format: str
    is_lossless: bool
    bitrate: Optional[int]       # kbps
    sample_rate: Optional[int]   # Hz
    bit_depth: Optional[int]     # bits
    duration: Optional[float]    # seconds
    artist: str
    album_artist: str
    album: str
    title: str
    year: Optional[int]
    track_number: Optional[int]
    disc_number: Optional[int]
    genre: str


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS tracks (
                id           INTEGER PRIMARY KEY,
                file_path    TEXT UNIQUE NOT NULL,
                file_name    TEXT,
                file_size    INTEGER,
                format       TEXT,
                is_lossless  INTEGER DEFAULT 0,
                bitrate      INTEGER,
                sample_rate  INTEGER,
                bit_depth    INTEGER,
                duration     REAL,
                artist       TEXT DEFAULT 'Unknown Artist',
                album_artist TEXT,
                album        TEXT DEFAULT 'Unknown Album',
                title        TEXT DEFAULT 'Unknown Title',
                year         INTEGER,
                track_number INTEGER,
                disc_number  INTEGER,
                genre        TEXT,
                date_scanned TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_artist     ON tracks(artist);
            CREATE INDEX IF NOT EXISTS idx_album      ON tracks(album);
            CREATE INDEX IF NOT EXISTS idx_lossless   ON tracks(is_lossless);
        """)
        self.conn.commit()

    def upsert_track(self, t: Track):
        self.conn.execute("""
            INSERT INTO tracks (
                file_path, file_name, file_size, format, is_lossless,
                bitrate, sample_rate, bit_depth, duration,
                artist, album_artist, album, title, year,
                track_number, disc_number, genre, date_scanned
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(file_path) DO UPDATE SET
                file_name=excluded.file_name, file_size=excluded.file_size,
                format=excluded.format, is_lossless=excluded.is_lossless,
                bitrate=excluded.bitrate, sample_rate=excluded.sample_rate,
                bit_depth=excluded.bit_depth, duration=excluded.duration,
                artist=excluded.artist, album_artist=excluded.album_artist,
                album=excluded.album, title=excluded.title, year=excluded.year,
                track_number=excluded.track_number, disc_number=excluded.disc_number,
                genre=excluded.genre, date_scanned=excluded.date_scanned
        """, (
            t.file_path, t.file_name, t.file_size, t.format,
            1 if t.is_lossless else 0,
            t.bitrate, t.sample_rate, t.bit_depth, t.duration,
            t.artist, t.album_artist, t.album, t.title, t.year,
            t.track_number, t.disc_number, t.genre,
            datetime.now().isoformat(),
        ))
        self.conn.commit()

    def remove_missing(self):
        """Remove database entries for files that no longer exist on disk."""
        rows = self.conn.execute("SELECT file_path FROM tracks").fetchall()
        removed = 0
        for row in rows:
            if not Path(row['file_path']).exists():
                self.conn.execute("DELETE FROM tracks WHERE file_path=?", (row['file_path'],))
                removed += 1
        self.conn.commit()
        return removed

    def get_all_tracks(self) -> List[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM tracks ORDER BY artist, album, disc_number, track_number"
        ).fetchall()

    def get_stats(self) -> dict:
        row = self.conn.execute("""
            SELECT
                COUNT(*)           AS total,
                SUM(is_lossless)   AS lossless,
                COUNT(*) - SUM(is_lossless) AS lossy,
                SUM(file_size)     AS total_size,
                SUM(duration)      AS total_duration
            FROM tracks
        """).fetchone()
        return dict(row)

    def get_albums(self) -> List[sqlite3.Row]:
        return self.conn.execute("""
            SELECT
                COALESCE(NULLIF(album_artist,''), artist) AS display_artist,
                album,
                year,
                COUNT(*)                              AS track_count,
                SUM(is_lossless)                      AS lossless_count,
                COUNT(*) - SUM(is_lossless)           AS lossy_count,
                GROUP_CONCAT(DISTINCT format)         AS formats,
                ROUND(AVG(CASE WHEN is_lossless=0 THEN bitrate END)) AS avg_lossy_bitrate,
                SUM(file_size)                        AS total_size,
                SUM(duration)                         AS total_duration
            FROM tracks
            GROUP BY COALESCE(NULLIF(album_artist,''), artist), album
            ORDER BY display_artist, year, album
        """).fetchall()

    def get_lossy_albums(self) -> List[sqlite3.Row]:
        return self.conn.execute("""
            SELECT
                COALESCE(NULLIF(album_artist,''), artist) AS display_artist,
                album,
                year,
                COUNT(*)                              AS track_count,
                SUM(is_lossless)                      AS lossless_count,
                COUNT(*) - SUM(is_lossless)           AS lossy_count,
                GROUP_CONCAT(DISTINCT format)         AS formats,
                ROUND(AVG(CASE WHEN is_lossless=0 THEN bitrate END)) AS avg_lossy_bitrate,
                SUM(file_size)                        AS total_size
            FROM tracks
            GROUP BY COALESCE(NULLIF(album_artist,''), artist), album
            HAVING lossy_count > 0
            ORDER BY display_artist, year, album
        """).fetchall()

    def close(self):
        self.conn.close()
