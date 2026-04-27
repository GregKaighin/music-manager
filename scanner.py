from pathlib import Path
from typing import Optional

from mutagen import File as MutagenFile
from mutagen.mp4 import MP4
from mutagen.asf import ASF
from rich.console import Console
from rich.progress import (
    BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn,
)

from database import Database, Track

AUDIO_EXTENSIONS = {
    '.mp3', '.flac', '.m4a', '.aac', '.ogg', '.opus',
    '.wma', '.wav', '.aiff', '.aif', '.ape', '.wv', '.tta',
}

LOSSLESS_EXTENSIONS = {'.flac', '.wav', '.aiff', '.aif', '.ape', '.wv', '.tta'}

FORMAT_NAMES = {
    '.mp3': 'MP3', '.flac': 'FLAC', '.ogg': 'OGG', '.opus': 'Opus',
    '.wav': 'WAV', '.aiff': 'AIFF', '.aif': 'AIFF', '.ape': 'APE',
    '.wv': 'WavPack', '.tta': 'TrueAudio', '.aac': 'AAC', '.wma': 'WMA',
}


def _is_lossless(filepath: Path, ext: str) -> bool:
    if ext in LOSSLESS_EXTENSIONS:
        return True
    if ext == '.m4a':
        try:
            codec = getattr(MP4(str(filepath)).info, 'codec', '') or ''
            return codec.lower().startswith('alac')
        except Exception:
            return False
    if ext == '.wma':
        try:
            asf = ASF(str(filepath))
            codec = str(asf.get('WM/Codec', [''])[0]).lower()
            return 'lossless' in codec
        except Exception:
            return False
    return False


def _tag(audio, *keys: str, default: str = '') -> str:
    for key in keys:
        try:
            val = audio.get(key)
            if val:
                item = val[0] if isinstance(val, list) else val
                s = str(item).strip()
                if s:
                    return s
        except Exception:
            continue
    return default


def _parse_num(val: str) -> Optional[int]:
    try:
        return int(str(val).split('/')[0])
    except (ValueError, TypeError, AttributeError):
        return None


def scan_file(filepath: Path) -> Optional[Track]:
    ext = filepath.suffix.lower()
    if ext not in AUDIO_EXTENSIONS:
        return None
    try:
        audio = MutagenFile(str(filepath), easy=True)
        if audio is None:
            return None

        info      = audio.info
        bitrate   = getattr(info, 'bitrate', None)
        bitrate   = (bitrate // 1000) if bitrate else None
        lossless  = _is_lossless(filepath, ext)

        # M4A: label as ALAC or AAC depending on codec
        if ext == '.m4a':
            fmt = 'ALAC' if lossless else 'AAC'
        else:
            fmt = FORMAT_NAMES.get(ext, ext.upper().lstrip('.'))

        year_str = _tag(audio, 'date', 'year')
        year = None
        if year_str:
            try:
                year = int(str(year_str)[:4])
            except ValueError:
                pass

        return Track(
            file_path    = str(filepath),
            file_name    = filepath.name,
            file_size    = filepath.stat().st_size,
            format       = fmt,
            is_lossless  = lossless,
            bitrate      = bitrate,
            sample_rate  = getattr(info, 'sample_rate', None),
            bit_depth    = getattr(info, 'bits_per_sample', None),
            duration     = getattr(info, 'length', None),
            artist       = _tag(audio, 'artist',      default='Unknown Artist'),
            album_artist = _tag(audio, 'albumartist', default=''),
            album        = _tag(audio, 'album',       default='Unknown Album'),
            title        = _tag(audio, 'title',       default=filepath.stem),
            year         = year,
            track_number = _parse_num(_tag(audio, 'tracknumber')),
            disc_number  = _parse_num(_tag(audio, 'discnumber')),
            genre        = _tag(audio, 'genre'),
        )
    except Exception:
        return None


class Scanner:
    def __init__(self, db: Database, console: Console):
        self.db      = db
        self.console = console

    def scan(self, music_dir: Path):
        self.console.print(f"\n[bold]Scanning[/bold] [cyan]{music_dir}[/cyan]\n")

        files = [
            p for p in music_dir.rglob('*')
            if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
        ]
        if not files:
            self.console.print("[yellow]No audio files found.[/yellow]")
            return

        ok = errors = 0
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console,
        ) as progress:
            task = progress.add_task("Reading files…", total=len(files))
            for fp in files:
                progress.update(task, description=f"[cyan]{fp.name[:55]}[/cyan]")
                track = scan_file(fp)
                if track:
                    self.db.upsert_track(track)
                    ok += 1
                else:
                    errors += 1
                progress.advance(task)

        removed = self.db.remove_missing()
        self.console.print(f"\n[green]✓[/green] {ok} tracks indexed", end='')
        if removed:
            self.console.print(f"  [dim]{removed} stale entries removed[/dim]", end='')
        if errors:
            self.console.print(f"  [red]✗ {errors} unreadable[/red]", end='')
        self.console.print()
