import urllib.parse
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from database import Database


def _fmt_size(b) -> str:
    if not b:
        return '—'
    b = float(b)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def _fmt_dur(s) -> str:
    if not s:
        return '—'
    s = int(s)
    h, m = divmod(s, 3600)
    m //= 60
    return f"{h}h {m}m" if h else f"{m}m"


def _quality(row: dict) -> tuple[str, str, str]:
    """Returns (label, terminal_colour, html_class)."""
    n_total    = row.get('track_count', 0) or 0
    n_lossless = row.get('lossless_count', 0) or 0
    n_lossy    = row.get('lossy_count', 0) or 0
    bitrate    = row.get('avg_lossy_bitrate', 0) or 0

    if n_lossless == n_total:
        return 'Lossless', 'green', 'q-lossless'
    if n_lossless > 0:
        return 'Mixed', 'cyan', 'q-mixed'
    if bitrate >= 256:
        return f'Lossy · {int(bitrate)}k', 'yellow', 'q-high'
    if bitrate >= 128:
        return f'Lossy · {int(bitrate)}k', 'dark_orange', 'q-medium'
    if bitrate > 0:
        return f'Lossy · {int(bitrate)}k', 'red', 'q-low'
    return 'Lossy', 'red', 'q-low'


def _search_links(artist: str, album: str) -> list[tuple[str, str]]:
    q = urllib.parse.quote(f"{artist} {album}")
    return [
        ('Bandcamp',  f"https://bandcamp.com/search?q={q}"),
        ('Qobuz',     f"https://www.qobuz.com/gb-en/search?q={q}"),
        ('Discogs',   f"https://www.discogs.com/search/?q={q}&type=release"),
        ('7digital',  f"https://uk.7digital.com/search#q={q}"),
    ]


class Reporter:
    def __init__(self, db: Database, console: Console):
        self.db      = db
        self.console = console

    # ── Terminal ────────────────────────────────────────────────────────────

    def print_summary(self):
        stats = self.db.get_stats()
        total    = stats['total']    or 0
        lossless = stats['lossless'] or 0
        lossy    = stats['lossy']    or 0
        size     = stats['total_size']     or 0
        dur      = stats['total_duration'] or 0
        pct      = (lossless / total * 100) if total else 0

        self.console.print(Panel(
            f"[bold]{total}[/bold] tracks  ·  "
            f"[green]{lossless} lossless[/green]  ·  "
            f"[yellow]{lossy} lossy[/yellow]  ·  "
            f"[bold]{pct:.0f}%[/bold] lossless\n"
            f"{_fmt_size(size)}  ·  {_fmt_dur(dur)}",
            title="[bold]Music Collection[/bold]",
            expand=False,
        ))

        lossy_albums = self.db.get_lossy_albums()
        if not lossy_albums:
            self.console.print("\n[green]✓ All albums are lossless![/green]")
            return

        self.console.print(f"\n[bold]{len(lossy_albums)} albums need attention[/bold]\n")

        table = Table(show_lines=True, expand=True)
        table.add_column("Artist",  style="bold", min_width=18)
        table.add_column("Album",   min_width=22)
        table.add_column("Year",    width=6,  justify="right")
        table.add_column("Format",  width=10)
        table.add_column("Quality", width=16)
        table.add_column("Tracks",  width=7,  justify="right")
        table.add_column("Size",    width=10, justify="right")

        for row in lossy_albums:
            row = dict(row)
            label, colour, _ = _quality(row)
            table.add_row(
                row['display_artist'] or 'Unknown Artist',
                row['album']          or 'Unknown Album',
                str(row['year']) if row['year'] else '—',
                row['formats']        or '—',
                f"[{colour}]{label}[/{colour}]",
                str(row['track_count']),
                _fmt_size(row['total_size']),
            )
        self.console.print(table)

    # ── HTML export ─────────────────────────────────────────────────────────

    def export_html(self, output_path: Path):
        stats    = self.db.get_stats()
        albums   = self.db.get_albums()

        total    = stats['total']    or 0
        lossless = stats['lossless'] or 0
        lossy    = stats['lossy']    or 0
        size     = stats['total_size']     or 0
        dur      = stats['total_duration'] or 0
        pct      = (lossless / total * 100) if total else 0

        rows_html = []
        for row in albums:
            row = dict(row)
            label, _, html_class = _quality(row)
            artist = row['display_artist'] or 'Unknown Artist'
            album  = row['album']          or 'Unknown Album'

            if row['lossy_count'] > 0:
                links_html = ''.join(
                    f'<a href="{url}" target="_blank" rel="noopener">{name}</a>'
                    for name, url in _search_links(artist, album)
                )
            else:
                links_html = '<span class="none">—</span>'

            rows_html.append(
                f'<tr data-q="{html_class}">'
                f'<td>{artist}</td>'
                f'<td>{album}</td>'
                f'<td class="num">{row["year"] or "—"}</td>'
                f'<td>{row["formats"] or "—"}</td>'
                f'<td><span class="badge {html_class}">{label}</span></td>'
                f'<td class="num">{row["track_count"]}</td>'
                f'<td class="num">{_fmt_size(row["total_size"])}</td>'
                f'<td class="links">{links_html}</td>'
                f'</tr>'
            )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Music Collection Report</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0d0d0d;--card:#1a1a1a;--card2:#141414;
  --border:rgba(201,169,110,.15);--gold:#c9a96e;
  --text:#f0ece3;--muted:#777;
  --green:#4caf72;--cyan:#4ab8c8;
  --yellow:#d4b84a;--orange:#d4844a;--red:#d45a4a;
}}
body{{background:var(--bg);color:var(--text);font-family:system-ui,sans-serif;font-size:14px;padding:2rem 2.5rem;line-height:1.5}}
h1{{font-size:1.7rem;color:var(--gold);letter-spacing:.03em;margin-bottom:.2rem}}
.sub{{color:var(--muted);font-size:.85rem;margin-bottom:2rem}}

.stats{{display:flex;flex-wrap:wrap;gap:.85rem;margin-bottom:2rem}}
.stat{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:.85rem 1.3rem;min-width:130px}}
.stat-val{{font-size:1.75rem;font-weight:700;color:var(--gold);line-height:1}}
.stat-val.green{{color:var(--green)}}.stat-val.red{{color:var(--red)}}
.stat-lbl{{font-size:.68rem;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);margin-top:.25rem}}

.controls{{display:flex;flex-wrap:wrap;gap:.65rem;align-items:center;margin-bottom:1rem}}
input[type=search]{{background:var(--card);border:1px solid var(--border);color:var(--text);
  border-radius:6px;padding:.5rem .9rem;font-size:.9rem;outline:none;width:280px;transition:.15s}}
input[type=search]:focus{{border-color:var(--gold)}}
.filters{{display:flex;gap:.4rem}}
.fb{{background:var(--card);border:1px solid var(--border);color:var(--muted);
  border-radius:6px;padding:.4rem .85rem;cursor:pointer;font-size:.8rem;transition:.15s;font-family:inherit}}
.fb:hover,.fb.on{{border-color:var(--gold);color:var(--gold)}}
.count{{color:var(--muted);font-size:.82rem;margin-left:.25rem}}

.table-wrap{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;min-width:820px}}
th{{background:var(--card);color:var(--muted);font-size:.7rem;text-transform:uppercase;
  letter-spacing:.09em;padding:.65rem .75rem;text-align:left;cursor:pointer;
  user-select:none;border-bottom:1px solid var(--border);position:sticky;top:0;white-space:nowrap}}
th:hover{{color:var(--gold)}}
th .arrow{{opacity:.4;margin-left:.3rem;font-size:.7rem}}
th.sorted .arrow{{opacity:1;color:var(--gold)}}
td{{padding:.55rem .75rem;border-bottom:1px solid rgba(255,255,255,.03);vertical-align:middle}}
tr:nth-child(even) td{{background:rgba(255,255,255,.012)}}
tr:hover td{{background:rgba(201,169,110,.04)}}
.num{{text-align:right;color:var(--muted)}}
.none{{color:var(--muted)}}

.badge{{display:inline-block;font-size:.65rem;font-weight:700;letter-spacing:.07em;
  text-transform:uppercase;border-radius:20px;padding:.18rem .6rem;white-space:nowrap}}
.q-lossless{{background:rgba(76,175,114,.12);color:var(--green)}}
.q-mixed   {{background:rgba(74,184,200,.12);color:var(--cyan)}}
.q-high    {{background:rgba(212,184, 74,.12);color:var(--yellow)}}
.q-medium  {{background:rgba(212,132, 74,.12);color:var(--orange)}}
.q-low     {{background:rgba(212, 90, 74,.12);color:var(--red)}}

.links a{{color:var(--muted);text-decoration:none;font-size:.75rem;
  margin-right:.35rem;padding:.12rem .4rem;border:1px solid rgba(255,255,255,.08);
  border-radius:4px;transition:.15s;white-space:nowrap}}
.links a:hover{{color:var(--gold);border-color:var(--gold)}}

.hidden{{display:none!important}}
@media(max-width:600px){{body{{padding:1rem}}}}
</style>
</head>
<body>
<h1>Music Collection Report</h1>
<p class="sub">Generated by Music Manager</p>

<div class="stats">
  <div class="stat"><div class="stat-val">{total}</div><div class="stat-lbl">Total Tracks</div></div>
  <div class="stat"><div class="stat-val green">{lossless}</div><div class="stat-lbl">Lossless</div></div>
  <div class="stat"><div class="stat-val red">{lossy}</div><div class="stat-lbl">Lossy</div></div>
  <div class="stat"><div class="stat-val">{pct:.0f}%</div><div class="stat-lbl">Lossless</div></div>
  <div class="stat"><div class="stat-val">{_fmt_size(size)}</div><div class="stat-lbl">Total Size</div></div>
  <div class="stat"><div class="stat-val">{_fmt_dur(dur)}</div><div class="stat-lbl">Duration</div></div>
</div>

<div class="controls">
  <input type="search" id="q" placeholder="Search artist or album…" oninput="applyFilters()">
  <div class="filters">
    <button class="fb on"  onclick="setFilter('all',this)">All</button>
    <button class="fb"     onclick="setFilter('lossy',this)">Needs Upgrade</button>
    <button class="fb"     onclick="setFilter('lossless',this)">Lossless Only</button>
  </div>
  <span class="count" id="cnt"></span>
</div>

<div class="table-wrap">
<table id="tbl">
<thead><tr>
  <th onclick="sortBy(0)">Artist<span class="arrow">↕</span></th>
  <th onclick="sortBy(1)">Album<span class="arrow">↕</span></th>
  <th onclick="sortBy(2)">Year<span class="arrow">↕</span></th>
  <th onclick="sortBy(3)">Format<span class="arrow">↕</span></th>
  <th onclick="sortBy(4)">Quality<span class="arrow">↕</span></th>
  <th onclick="sortBy(5)">Tracks<span class="arrow">↕</span></th>
  <th onclick="sortBy(6)">Size<span class="arrow">↕</span></th>
  <th>Find Lossless</th>
</tr></thead>
<tbody>
{''.join(rows_html)}
</tbody>
</table>
</div>

<script>
let filter='all', sortCol=-1, sortAsc=true;

function applyFilters(){{
  const q=document.getElementById('q').value.toLowerCase();
  const rows=[...document.querySelectorAll('#tbl tbody tr')];
  let n=0;
  rows.forEach(r=>{{
    const qc=r.dataset.q;
    let show=r.textContent.toLowerCase().includes(q);
    if(filter==='lossy'    && qc==='q-lossless') show=false;
    if(filter==='lossless' && qc!=='q-lossless') show=false;
    r.classList.toggle('hidden',!show);
    if(show) n++;
  }});
  document.getElementById('cnt').textContent=n+' albums';
}}

function setFilter(f,btn){{
  filter=f;
  document.querySelectorAll('.fb').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on');
  applyFilters();
}}

function sortBy(col){{
  const tbody=document.querySelector('#tbl tbody');
  const rows=[...tbody.querySelectorAll('tr')];
  sortAsc = sortCol===col ? !sortAsc : true;
  sortCol=col;
  document.querySelectorAll('th').forEach((th,i)=>{{
    th.classList.toggle('sorted',i===col);
    if(i===col) th.querySelector('.arrow').textContent=sortAsc?'↑':'↓';
    else th.querySelector('.arrow').textContent='↕';
  }});
  rows.sort((a,b)=>{{
    const va=a.cells[col].textContent.trim();
    const vb=b.cells[col].textContent.trim();
    const na=parseFloat(va), nb=parseFloat(vb);
    if(!isNaN(na)&&!isNaN(nb)) return (na-nb)*(sortAsc?1:-1);
    return va.localeCompare(vb)*(sortAsc?1:-1);
  }});
  rows.forEach(r=>tbody.appendChild(r));
  applyFilters();
}}

window.addEventListener('DOMContentLoaded',applyFilters);
</script>
</body>
</html>"""

        output_path.write_text(html, encoding='utf-8')
        self.console.print(
            f"\n[green]✓[/green] HTML report saved → [bold]{output_path}[/bold]"
        )
