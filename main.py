import sys
from pathlib import Path

import click
from rich.console import Console

console = Console(legacy_windows=False)


@click.group()
def cli():
    """Music Collection Manager

    \b
    Commands:
      scan      Index your music library into a local database
      report    Terminal summary + HTML report with quality info
      organise  Copy/move files into Artist / Year-Album / Track structure
    """


@cli.command()
@click.argument('music_dir', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option('--db', default='music.db', show_default=True,
              type=click.Path(path_type=Path), help='Database file location')
def scan(music_dir, db):
    """Scan MUSIC_DIR and build (or update) the database."""
    from scanner import Scanner
    from database import Database
    db_obj = Database(db)
    Scanner(db_obj, console).scan(music_dir)
    db_obj.close()


@cli.command()
@click.option('--db',     default='music.db',          show_default=True,
              type=click.Path(path_type=Path))
@click.option('--output', default='music_report.html', show_default=True,
              type=click.Path(path_type=Path), help='HTML report output path')
def report(db, output):
    """Show quality summary and export an HTML report."""
    from database import Database
    from reporter import Reporter
    if not Path(db).exists():
        console.print(f"[red]No database found at '{db}'. Run 'scan' first.[/red]")
        sys.exit(1)
    db_obj = Database(db)
    r = Reporter(db_obj, console)
    r.print_summary()
    r.export_html(Path(output))
    db_obj.close()
    console.print(f"\nOpen the report: [bold]{Path(output).resolve()}[/bold]")


@cli.command()
@click.argument('output_dir', type=click.Path(file_okay=False, path_type=Path))
@click.option('--db',      default='music.db', show_default=True,
              type=click.Path(path_type=Path))
@click.option('--dry-run', is_flag=True,
              help='Preview the plan without touching any files')
@click.option('--move',    is_flag=True,
              help='Move files instead of copying (default: copy)')
def organise(output_dir, db, dry_run, move):
    """Organise music into OUTPUT_DIR using Artist / Year-Album / Track layout.

    Defaults to copying files. Use --move to relocate them instead.
    Always shows a preview; asks for confirmation before proceeding.
    """
    from database import Database
    from organizer import Organizer
    if not Path(db).exists():
        console.print(f"[red]No database found at '{db}'. Run 'scan' first.[/red]")
        sys.exit(1)
    db_obj = Database(db)
    Organizer(db_obj, console).organize(output_dir, dry_run=dry_run, move=move)
    db_obj.close()


if __name__ == '__main__':
    cli()
