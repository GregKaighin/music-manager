import re
import shutil
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from database import Database

_FORBIDDEN = re.compile(r'[\\/:*?"<>|]')
_TRAIL     = re.compile(r'[\. ]+$')


def _safe(name: str, max_len: int = 90) -> str:
    name = _FORBIDDEN.sub('_', name)
    name = _TRAIL.sub('', name)
    return name[:max_len] or '_'


def _target(output_dir: Path, row: dict) -> Path:
    artist     = _safe(row.get('album_artist') or row.get('artist') or 'Unknown Artist')
    album      = _safe(row.get('album') or 'Unknown Album')
    title      = _safe(row.get('title') or 'Unknown Title')
    year       = row.get('year')
    track_num  = row.get('track_number')
    disc_num   = row.get('disc_number')
    ext        = Path(row['file_path']).suffix

    album_folder = f"{year} - {album}" if year else album

    if track_num is not None:
        prefix = (f"{disc_num}-{track_num:02d}" if disc_num and disc_num > 1
                  else f"{track_num:02d}")
        stem = f"{prefix} - {title}"
    else:
        stem = title

    return output_dir / artist / album_folder / (stem + ext)


def _no_conflict(path: Path) -> Path:
    if not path.exists():
        return path
    stem, ext = path.stem, path.suffix
    for i in range(2, 9999):
        candidate = path.parent / f"{stem} ({i}){ext}"
        if not candidate.exists():
            return candidate
    return path


class Organizer:
    def __init__(self, db: Database, console: Console):
        self.db      = db
        self.console = console

    def organize(self, output_dir: Path, dry_run: bool = False, move: bool = False):
        tracks = self.db.get_all_tracks()
        if not tracks:
            self.console.print("[yellow]No tracks in database. Run 'scan' first.[/yellow]")
            return

        op = "Move" if move else "Copy"

        plan: list[tuple[Path, Path]] = []
        for row in tracks:
            src = Path(row['file_path'])
            if not src.exists():
                continue
            dst = _no_conflict(_target(output_dir, dict(row)))
            if src.resolve() != dst.resolve():
                plan.append((src, dst))

        if not plan:
            self.console.print("[green]✓ All files are already organised.[/green]")
            return

        # Preview table
        table = Table(
            title=f"[bold]{op} plan — {len(plan)} files[/bold]",
            show_lines=False, expand=True,
        )
        table.add_column("Source file",  style="dim",  max_width=45)
        table.add_column("→",            width=3,      justify="center")
        table.add_column("Destination",  max_width=65)

        for src, dst in plan[:60]:
            table.add_row(src.name, "→", str(dst.relative_to(output_dir)))
        if len(plan) > 60:
            table.add_row(f"… and {len(plan) - 60} more", "", "")

        self.console.print(table)

        if dry_run:
            self.console.print(f"\n[yellow]Dry run — no files were {op.lower()}d.[/yellow]")
            return

        if not Confirm.ask(f"\n{op} {len(plan)} files into [bold]{output_dir}[/bold]?"):
            self.console.print("Cancelled.")
            return

        done = errors = 0
        for src, dst in plan:
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), dst) if move else shutil.copy2(src, dst)
                done += 1
            except Exception as e:
                self.console.print(f"[red]Error[/red] {src.name}: {e}")
                errors += 1

        self.console.print(f"\n[green]✓[/green] {op}d {done} files", end='')
        if errors:
            self.console.print(f"  [red]✗ {errors} errors[/red]", end='')
        self.console.print()
