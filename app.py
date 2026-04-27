import json
import queue
import shutil
import threading
import urllib.parse
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, Response

from database import Database
from scanner import AUDIO_EXTENSIONS, scan_file
from organizer import _no_conflict, _target

app = Flask(__name__)

_scan_tasks: dict[str, queue.Queue] = {}


def _fmt_size(b) -> str:
    if not b:
        return '—'
    b = float(b)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if b < 1024:
            return f'{b:.1f} {unit}'
        b /= 1024
    return f'{b:.1f} PB'


def _fmt_dur(s) -> str:
    if not s:
        return '—'
    s = int(s)
    h = s // 3600
    m = (s % 3600) // 60
    return f'{h}h {m}m' if h else f'{m}m'


def _quality(row: dict) -> tuple[str, str]:
    n_total    = row.get('track_count', 0) or 0
    n_lossless = row.get('lossless_count', 0) or 0
    n_lossy    = row.get('lossy_count', 0) or 0
    bitrate    = row.get('avg_lossy_bitrate', 0) or 0
    if n_lossless == n_total:
        return 'Lossless', 'q-lossless'
    if n_lossless > 0:
        return 'Mixed', 'q-mixed'
    if bitrate >= 256:
        return f'Lossy · {int(bitrate)}k', 'q-high'
    if bitrate >= 128:
        return f'Lossy · {int(bitrate)}k', 'q-medium'
    if bitrate > 0:
        return f'Lossy · {int(bitrate)}k', 'q-low'
    return 'Lossy', 'q-low'


@app.route('/')
def dashboard():
    db_path = request.args.get('db', 'music.db')
    stats = None
    if Path(db_path).exists():
        db = Database(Path(db_path))
        raw = db.get_stats()
        db.close()
        total    = raw['total']    or 0
        lossless = raw['lossless'] or 0
        lossy    = raw['lossy']    or 0
        stats = {
            'total':    total,
            'lossless': lossless,
            'lossy':    lossy,
            'pct':      f'{lossless / total * 100:.0f}' if total else '0',
            'size':     _fmt_size(raw['total_size']),
            'duration': _fmt_dur(raw['total_duration']),
        }
    return render_template('dashboard.html', stats=stats, db_path=db_path, active_page='dashboard')


@app.route('/albums')
def albums():
    db_path = request.args.get('db', 'music.db')
    return render_template('albums.html', db_path=db_path, active_page='albums')


@app.route('/scan')
def scan_page():
    db_path = request.args.get('db', 'music.db')
    return render_template('scan.html', db_path=db_path, active_page='scan')


@app.route('/organise')
def organise_page():
    db_path = request.args.get('db', 'music.db')
    return render_template('organise.html', db_path=db_path, active_page='organise')


# ── API ────────────────────────────────────────────────────────────────────

@app.route('/api/albums')
def api_albums():
    db_path = request.args.get('db', 'music.db')
    if not Path(db_path).exists():
        return jsonify([])
    db = Database(Path(db_path))
    rows = [dict(r) for r in db.get_albums()]
    db.close()
    for row in rows:
        label, cls = _quality(row)
        row['quality_label'] = label
        row['quality_class'] = cls
        row['size_fmt']      = _fmt_size(row.get('total_size'))
        row['duration_fmt']  = _fmt_dur(row.get('total_duration'))
        if (row.get('lossy_count') or 0) > 0:
            q = urllib.parse.quote(
                f"{row.get('display_artist') or ''} {row.get('album') or ''}"
            )
            row['links'] = [
                {'name': 'Bandcamp', 'url': f'https://bandcamp.com/search?q={q}'},
                {'name': 'Qobuz',    'url': f'https://www.qobuz.com/gb-en/search?q={q}'},
                {'name': 'Discogs',  'url': f'https://www.discogs.com/search/?q={q}&type=release'},
                {'name': '7digital', 'url': f'https://uk.7digital.com/search#q={q}'},
            ]
        else:
            row['links'] = []
    return jsonify(rows)


@app.route('/api/scan', methods=['POST'])
def api_scan():
    data      = request.get_json()
    music_dir = (data.get('music_dir') or '').strip()
    db_path   = (data.get('db_path')   or 'music.db').strip() or 'music.db'
    if not music_dir:
        return jsonify({'error': 'No directory specified'}), 400
    if not Path(music_dir).is_dir():
        return jsonify({'error': f'Not a directory: {music_dir}'}), 400
    task_id = str(uuid.uuid4())
    _scan_tasks[task_id] = queue.Queue()
    threading.Thread(
        target=_run_scan, args=(task_id, music_dir, db_path), daemon=True
    ).start()
    return jsonify({'task_id': task_id})


@app.route('/api/scan/<task_id>/stream')
def api_scan_stream(task_id):
    if task_id not in _scan_tasks:
        return jsonify({'error': 'Unknown task'}), 404

    def generate():
        q = _scan_tasks[task_id]
        while True:
            try:
                msg = q.get(timeout=30)
            except queue.Empty:
                yield 'data: {"type":"ping"}\n\n'
                continue
            yield f'data: {json.dumps(msg)}\n\n'
            if msg.get('type') in ('done', 'error'):
                _scan_tasks.pop(task_id, None)
                break

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


def _run_scan(task_id: str, music_dir_str: str, db_path_str: str):
    q = _scan_tasks.get(task_id)
    if q is None:
        return
    try:
        music_dir = Path(music_dir_str)
        files = [
            p for p in music_dir.rglob('*')
            if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
        ]
        if not files:
            q.put({'type': 'error', 'message': 'No audio files found.'})
            return
        q.put({'type': 'total', 'count': len(files)})
        db = Database(Path(db_path_str))
        ok = errors = 0
        for i, fp in enumerate(files):
            track = scan_file(fp)
            if track:
                db.upsert_track(track)
                ok += 1
            else:
                errors += 1
            if i % 10 == 0 or i == len(files) - 1:
                q.put({
                    'type': 'progress',
                    'current': i + 1,
                    'total': len(files),
                    'file': fp.name[:60],
                })
        removed = db.remove_missing()
        db.close()
        q.put({'type': 'done', 'ok': ok, 'errors': errors, 'removed': removed})
    except Exception as e:
        q.put({'type': 'error', 'message': str(e)})


@app.route('/api/organise/preview', methods=['POST'])
def api_organise_preview():
    data       = request.get_json()
    db_path    = (data.get('db_path')    or 'music.db').strip()
    output_dir = (data.get('output_dir') or '').strip()
    if not output_dir:
        return jsonify({'error': 'No output directory specified'}), 400
    if not Path(db_path).exists():
        return jsonify({'error': 'Database not found. Run a scan first.'}), 400
    db     = Database(Path(db_path))
    tracks = db.get_all_tracks()
    db.close()
    out  = Path(output_dir)
    plan = []
    for row in tracks:
        src = Path(row['file_path'])
        if not src.exists():
            continue
        dst = _no_conflict(_target(out, dict(row)))
        if src.resolve() != dst.resolve():
            plan.append({'src': src.name, 'dst': str(dst.relative_to(out))})
    return jsonify({'plan': plan[:100], 'total': len(plan)})


@app.route('/api/organise/execute', methods=['POST'])
def api_organise_execute():
    data       = request.get_json()
    db_path    = (data.get('db_path')    or 'music.db').strip()
    output_dir = (data.get('output_dir') or '').strip()
    move       = bool(data.get('move', False))
    if not output_dir:
        return jsonify({'error': 'No output directory specified'}), 400
    if not Path(db_path).exists():
        return jsonify({'error': 'Database not found. Run a scan first.'}), 400
    db     = Database(Path(db_path))
    tracks = db.get_all_tracks()
    db.close()
    out    = Path(output_dir)
    done = errors = 0
    for row in tracks:
        src = Path(row['file_path'])
        if not src.exists():
            continue
        dst = _no_conflict(_target(out, dict(row)))
        if src.resolve() == dst.resolve():
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst)) if move else shutil.copy2(str(src), str(dst))
            done += 1
        except Exception:
            errors += 1
    return jsonify({'done': done, 'errors': errors})


if __name__ == '__main__':
    app.run(debug=True, port=5000, threaded=True)
