# Music Manager

A local music collection tool that indexes your library into a SQLite database, reports on audio quality, and organises files into a clean folder structure.

Includes both a CLI and a web UI.

---

## Features

- **Scan** — walks any directory and indexes every audio file (MP3, FLAC, AAC, OGG, WAV, AIFF, APE, WavPack, TrueAudio, WMA, Opus)
- **Dashboard** — at-a-glance stats: track count, lossless vs lossy split, total size, listening time
- **Albums browser** — sortable, searchable table with quality badges; one-click links to find lossless upgrades on Bandcamp, Qobuz, Discogs and 7digital
- **Scan page** — trigger a rescan from the browser with a live progress bar
- **Organise** — copy or move files into `Artist / Year-Album / Track` folder structure, with a preview before anything is touched
- **HTML report** — export a standalone report file via the CLI

---

## Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt`

```
pip install -r requirements.txt
```

---

## Usage

### Web UI

Start the server, then open the app in your browser:

```
python app.py
```

**[Open the app → http://localhost:5000](http://localhost:5000)**

---

### CLI

**Scan a music folder**
```
python main.py scan "E:\Music"
```

**Generate a terminal summary and HTML report**
```
python main.py report
```

**Organise files into Artist / Year-Album / Track layout**
```
python main.py organise "E:\Music-Organised"
```

Add `--dry-run` to preview without touching files, or `--move` to relocate instead of copy.

**All commands accept a `--db` option** to specify a non-default database path (default: `music.db`).

---

## Supported formats

| Format | Lossless |
|--------|----------|
| FLAC | ✓ |
| WAV | ✓ |
| AIFF | ✓ |
| APE | ✓ |
| WavPack | ✓ |
| TrueAudio | ✓ |
| ALAC (M4A) | ✓ |
| WMA Lossless | ✓ |
| MP3 | — |
| AAC / M4A | — |
| OGG | — |
| Opus | — |
| WMA | — |
