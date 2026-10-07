import os
import re
import sys
import json
import time
import uuid
import glob
import threading
import subprocess
from pathlib import Path

import yt_dlp

from flask import Flask, request, jsonify, send_file, render_template, send_from_directory, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

def _ffmpeg_works(path):
    try:
        if not path or not os.path.exists(path):
            return False
        r = subprocess.run([path, "-version"], capture_output=True, timeout=15)
        return r.returncode == 0
    except Exception:
        return False


def _resolve_ffmpeg(candidates):
    # 1. Explicit bundled / installed candidates (verified by execution).
    for c in candidates:
        if _ffmpeg_works(c):
            return c
    # 2. Anything already on PATH (e.g. user-installed ffmpeg, like the
    #    original reclip.sh setup expects).
    import shutil
    found = shutil.which("ffmpeg")
    if found:
        return found
    # 3. Last resort: first candidate that at least exists — let yt-dlp try.
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return ""


if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
    APP_HOME = Path(sys.executable).resolve().parent
    DOWNLOAD_DIR = APP_HOME / "downloads"
    HISTORY_FILE = APP_HOME / "history.json"
    TOOLS_DIR = str(BASE_DIR / "tools")
    _ffmpeg_candidates = [
        os.path.join(str(APP_HOME), "ffmpeg.exe"),
        os.path.join(str(APP_HOME / "tools"), "ffmpeg.exe"),
        os.path.join(TOOLS_DIR, "ffmpeg.exe"),
    ]
    try:
        import imageio_ffmpeg
        _ffmpeg_candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    FFMPEG = _resolve_ffmpeg(_ffmpeg_candidates)
else:
    BASE_DIR = Path(__file__).resolve().parent
    DOWNLOAD_DIR = Path("/tmp/reclip/downloads")
    HISTORY_FILE = Path("/tmp/reclip/history.json")
    TOOLS_DIR = str(BASE_DIR / "tools")
    _web_candidates = [
        os.path.join(TOOLS_DIR, "ffmpeg.exe"),
        os.path.join(TOOLS_DIR, "ffmpeg"),
    ]
    try:
        import imageio_ffmpeg
        _web_candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    FFMPEG = _resolve_ffmpeg(_web_candidates) or "ffmpeg"

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

# Make the bundled ffmpeg discoverable the same way the original
# reclip.sh setup does (ffmpeg on PATH).
for _tools_dir in {TOOLS_DIR, str(DOWNLOAD_DIR.parent / "tools")}:
    if _tools_dir and os.path.isdir(_tools_dir):
        os.environ["PATH"] = _tools_dir + os.pathsep + os.environ.get("PATH", "")

APP_VERSION = "1.2.0"
jobs = {}

MEDIA_EXTS = (".mp4", ".mkv", ".webm", ".mp3", ".m4a", ".opus", ".ogg")
SKIP_EXTS = (".srt", ".vtt", ".json", ".part", ".ytdl", ".temp", ".tmp")


def friendly_ydl_error(err):
    msg = str(err)
    low = msg.lower()
    if "sign in to confirm you" in low and "bot" in low:
        return ("YouTube is asking for bot verification on this network "
                "(tried the default player, embedded/mobile/TV players and browser cookies). "
                "Wait a few minutes and retry, try MP3/audio only, or update yt-dlp. "
                "Staying signed in to YouTube in Chrome/Edge on this PC gives the best chance.")
    if "ffmpeg" in low and ("not installed" in low or "not found" in low or "merg" in low):
        return ("Video+audio merge needs ffmpeg, which ReClip could not find. "
                "Reinstall ReClip (ffmpeg ships inside), or place ffmpeg.exe next to ReClip.exe, then retry. "
                f"Original error: {msg[:160]}")
    if "unsupported url" in low:
        return "This URL is not supported."
    if "private" in low:
        return "This video is private."
    if "unavailable" in low:
        return "Video is unavailable."
    if "403" in low:
        return "Access denied by the platform (403)."
    if "404" in low:
        return "Video not found (404)."
    if "timed out" in low or "timed out" in msg:
        return "Request timed out — try again."
    return msg[:300]


def pick_media_file(files, format_choice):
    media = [f for f in files
             if f.lower().endswith(MEDIA_EXTS)
             and not f.lower().endswith(SKIP_EXTS)]
    if not media:
        return None
    if format_choice == "audio":
        audio = [f for f in media if f.lower().endswith((".mp3", ".m4a", ".opus", ".ogg"))]
        return audio[0] if audio else None
    video = [f for f in media if f.lower().endswith((".mp4", ".mkv", ".webm"))]
    return video[0] if video else media[0]


PLAYER_CLIENTS = ["web_embedded", "tv_embedded", "android", "ios", "tv", "web"]
COOKIE_BROWSERS = ["chrome", "edge", "firefox", "brave", "opera"]
_bot_blocks = {"count": 0, "first": 0.0}


def _bot_blocked_recently(limit=10, window=600):
    now = time.time()
    if now - _bot_blocks["first"] > window:
        _bot_blocks["count"] = 0
        _bot_blocks["first"] = now
    return _bot_blocks["count"] >= limit


def _note_bot_block():
    now = time.time()
    if now - _bot_blocks["first"] > 600:
        _bot_blocks["count"] = 0
        _bot_blocks["first"] = now
    _bot_blocks["count"] += 1


def _is_bot_error(err):
    low = str(err).lower()
    return "sign in to confirm you" in low and "bot" in low


def download_with_client_fallback(ydl_opts, url, job=None):
    if _bot_blocked_recently():
        raise RuntimeError(
            "Too many YouTube bot-blocks in a row — waiting a few minutes "
            "before retrying so the IP is not flagged further."
        )
    # Pass 1: exactly like the original reclip (default player client).
    base_opts = dict(ydl_opts)
    base_opts.pop("extractor_args", None)
    try:
        with yt_dlp.YoutubeDL(base_opts) as ydl:
            ydl.download([url])
        return
    except Exception as e:
        if not _is_bot_error(e):
            raise
        _note_bot_block()
        if job is not None:
            job["progress"] = {"downloaded": 0, "total": 0, "speed": 0, "eta": 0}
        last_err = e
        # Pass 2: alternate player clients (embedded/mobile/TV).
        try:
            opts = dict(ydl_opts)
            opts["extractor_args"] = {"youtube": {"player_client": list(PLAYER_CLIENTS)}}
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            return
        except Exception as ce:
            last_err = ce
        # Pass 3: same clients + signed-in browser cookies.
        for browser in COOKIE_BROWSERS:
            try:
                cookie_opts = dict(ydl_opts)
                cookie_opts["extractor_args"] = {"youtube": {"player_client": list(PLAYER_CLIENTS)}}
                cookie_opts["cookiesfrombrowser"] = (browser,)
                with yt_dlp.YoutubeDL(cookie_opts) as ydl:
                    ydl.download([url])
                return
            except Exception as be:
                last_err = be
                continue
        raise last_err


def load_history():
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except Exception:
            return []
    return []


def save_history(history):
    HISTORY_FILE.write_text(json.dumps(history, indent=2))


def run_download(job_id, url, format_choice, format_id, trim_start=None, trim_end=None, subtitles=False):
    job = jobs[job_id]
    out_template = str(DOWNLOAD_DIR / f"{job_id}.%(ext)s")

    if format_choice == "audio":
        format_str = "bestaudio/best"
        postprocessors = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}]
        merge_ext = None
    elif format_id:
        format_str = f"{format_id}+bestaudio/best"
        postprocessors = []
        merge_ext = "mp4"
    else:
        format_str = "bestvideo+bestaudio/best"
        postprocessors = []
        merge_ext = "mp4"

    if subtitles:
        postprocessors.append({"key": "FFmpegEmbedSubtitle"})

    def progress_hook(d):
        if d["status"] == "downloading":
            job["progress"] = {
                "downloaded": d.get("downloaded_bytes", 0),
                "total": d.get("total_bytes") or d.get("total_bytes_estimate", 0),
                "speed": d.get("speed", 0),
                "eta": d.get("eta", 0),
            }
        elif d["status"] == "finished":
            job["progress"] = {"downloaded": 1, "total": 1, "speed": 0, "eta": 0}

    ydl_opts = {
        "format": format_str,
        "outtmpl": out_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": postprocessors,
        "progress_hooks": [progress_hook],
        "writesubtitles": subtitles,
        "subtitleslangs": ["en"] if subtitles else None,
        "subtitlesformat": "srt/vtt/best",
        "extractor_args": {
            "youtube": {
                "player_client": list(PLAYER_CLIENTS),
            }
        },
        "concurrent_fragment_downloads": 4,
        "http_chunk_size": 10485760,
        "retries": 3,
        "fragment_retries": 3,
        "skip_unavailable_fragments": True,
        "socket_timeout": 30,
    }
    if merge_ext:
        ydl_opts["merge_output_format"] = merge_ext
    if FFMPEG and _ffmpeg_works(FFMPEG):
        # Classic directory form, exactly like --ffmpeg-location on the CLI.
        ydl_opts["ffmpeg_location"] = os.path.dirname(FFMPEG) if os.path.isfile(FFMPEG) else FFMPEG
    if trim_start and trim_end:
        ydl_opts["download_ranges"] = [{"start_time": trim_start, "end_time": trim_end}]

    for stale in glob.glob(str(DOWNLOAD_DIR / f"{job_id}.*")):
        try:
            os.remove(stale)
        except OSError:
            pass

    try:
        download_with_client_fallback(ydl_opts, url, job)

        files = glob.glob(str(DOWNLOAD_DIR / f"{job_id}.*"))
        if not files:
            job["status"] = "error"
            job["error"] = "Download completed but no file was found"
            return

        chosen = pick_media_file(files, format_choice)
        if not chosen:
            job["status"] = "error"
            job["error"] = "Download produced no playable media file (only subtitles/metadata found)"
            return

        for f in files:
            if f != chosen:
                try:
                    os.remove(f)
                except OSError:
                    pass

        actual_size = os.path.getsize(chosen)
        if actual_size < 1024:
            job["status"] = "error"
            job["error"] = f"Downloaded file is incomplete ({actual_size} bytes). Try again or pick another quality."
            try:
                os.remove(chosen)
            except OSError:
                pass
            return
        job["status"] = "done"
        job["file"] = chosen
        job["progress"] = {"downloaded": 1, "total": 1, "speed": 0, "eta": 0}
        job["actual_size"] = actual_size
        job["total_size"] = actual_size
        ext = os.path.splitext(chosen)[1]
        title = job.get("title", "").strip()
        if title:
            safe_title = "".join(c for c in title if c not in r'\/:*?"<>|').strip()[:100].strip()
            job["filename"] = f"{safe_title}{ext}" if safe_title else os.path.basename(chosen)
        else:
            job["filename"] = os.path.basename(chosen)

        history = load_history()
        history.insert(0, {
            "id": uuid.uuid4().hex[:10],
            "url": url,
            "title": job.get("title", ""),
            "thumbnail": job.get("thumbnail", ""),
            "filename": job["filename"],
            "format": format_choice,
            "q": job.get("quality", ""),
            "size": actual_size,
            "ts": int(time.time() * 1000),
            "timestamp": str(uuid.uuid4())[:8],
            "savedTo": None,
        })
        save_history(history[:100])
    except Exception as e:
        job["status"] = "error"
        job["error"] = friendly_ydl_error(e)
        for stale in glob.glob(str(DOWNLOAD_DIR / f"{job_id}.*")):
            try:
                if os.path.getsize(stale) < 1024:
                    os.remove(stale)
            except OSError:
                pass


@app.route("/")
def index():
    return render_template("index.html", version=APP_VERSION)


@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory(BASE_DIR / "static", filename)


@app.route("/api/info", methods=["POST"])
def get_info():
    data = request.json
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
    }
    if FFMPEG:
        ydl_opts["ffmpeg_location"] = FFMPEG
    try:
        info = None
        last_err = None
        for clients_set in (None, ["web_embedded"], ["android"], ["ios"], ["tv"]):
            try:
                opts = dict(ydl_opts)
                if clients_set is None:
                    opts.pop("extractor_args", None)
                else:
                    opts["extractor_args"] = {"youtube": {"player_client": clients_set}}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                break
            except Exception as e:
                last_err = e
                continue
        if info is None:
            raise last_err

        best_by_height = {}
        for f in info.get("formats", []):
            height = f.get("height")
            if height and f.get("vcodec", "none") != "none":
                tbr = f.get("tbr") or 0
                if height not in best_by_height or tbr > (best_by_height[height].get("tbr") or 0):
                    best_by_height[height] = f

        formats = []
        for height, f in best_by_height.items():
            size = f.get("filesize") or f.get("filesize_approx") or 0
            formats.append({
                "id": f["format_id"],
                "label": f"{height}p",
                "height": height,
                "size": size,
            })
        formats.sort(key=lambda x: x["height"], reverse=True)

        return jsonify({
            "title": info.get("title", ""),
            "thumbnail": info.get("thumbnail", ""),
            "duration": info.get("duration"),
            "uploader": info.get("uploader", ""),
            "formats": formats,
        })
    except Exception as e:
        return jsonify({"error": friendly_ydl_error(e)}), 400


@app.route("/api/playlist", methods=["POST"])
def get_playlist_info():
    data = request.json
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "tv"],
            }
        },
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        entries = info.get("entries", [])
        urls = [entry.get("url") or entry.get("webpage_url") for entry in entries if entry]
        return jsonify({"urls": urls})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/download", methods=["POST"])
def start_download():
    data = request.json
    url = data.get("url", "").strip()
    format_choice = data.get("format", "video")
    format_id = data.get("format_id")
    title = data.get("title", "")
    thumbnail = data.get("thumbnail", "")
    trim_start = data.get("trim_start")
    trim_end = data.get("trim_end")
    subtitles = data.get("subtitles", False)

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    job_id = uuid.uuid4().hex[:10]
    jobs[job_id] = {
        "status": "downloading",
        "url": url,
        "title": title,
        "quality": format_id or "",
        "thumbnail": thumbnail,
        "progress": {"downloaded": 0, "total": 0, "speed": 0, "eta": 0},
    }

    thread = threading.Thread(target=run_download, args=(job_id, url, format_choice, format_id, trim_start, trim_end, subtitles))
    thread.daemon = True
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def check_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "status": job["status"],
        "error": job.get("error"),
        "filename": job.get("filename"),
        "progress": job.get("progress", {}),
        "actual_size": job.get("actual_size", 0),
        "size": job.get("actual_size", 0),
    })


@app.route("/api/file/<job_id>")
def download_file(job_id):
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "File not ready"}), 404
    return send_file(job["file"], as_attachment=True, download_name=job["filename"])


@app.route("/api/preview/<job_id>")
def preview_file(job_id):
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "File not ready"}), 404
    
    file_path = job["file"]
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
    
    # Support range requests for video streaming
    file_size = os.path.getsize(file_path)
    range_header = request.headers.get('Range', None)

    if range_header:
        match = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if match:
            g = match.groups()
            byte1 = int(g[0]) if g[0] else 0
            byte2 = int(g[1]) if g[1] else file_size - 1
            byte1 = max(0, min(byte1, file_size - 1))
            byte2 = min(byte2, file_size - 1)
            length = byte2 - byte1 + 1
            with open(file_path, 'rb') as f:
                f.seek(byte1)
                data = f.read(length)
            rv = Response(
                data, 206, mimetype='video/mp4',
                headers={
                    'Content-Range': f'bytes {byte1}-{byte2}/{file_size}',
                    'Accept-Ranges': 'bytes',
                    'Content-Length': str(length),
                },
            )
            return rv

    mimetype = 'audio/mpeg' if file_path.endswith('.mp3') else 'video/mp4'
    response = send_file(file_path, mimetype=mimetype)
    response.headers['Accept-Ranges'] = 'bytes'
    return response


@app.route("/api/ytdlp-version")
def ytdlp_version():
    try:
        import yt_dlp
        return jsonify({"version": yt_dlp.version.__version__})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/diagnostics")
def diagnostics():
    import shutil
    cands = []
    if getattr(sys, "frozen", False):
        app_home = str(Path(sys.executable).resolve().parent)
        meipass = str(Path(sys._MEIPASS))
        raw = [
            os.path.join(app_home, "ffmpeg.exe"),
            os.path.join(app_home, "tools", "ffmpeg.exe"),
            os.path.join(meipass, "tools", "ffmpeg.exe"),
        ]
        try:
            import imageio_ffmpeg
            raw.append(imageio_ffmpeg.get_ffmpeg_exe())
        except Exception as e:
            raw.append(f"<imageio error: {e}>")
    else:
        raw = [os.path.join(TOOLS_DIR, "ffmpeg.exe")]
    for c in raw:
        exists = bool(c) and os.path.exists(c)
        cands.append({"path": c, "exists": exists, "works": _ffmpeg_works(c) if exists else False})
    return jsonify({
        "app_version": APP_VERSION,
        "frozen": getattr(sys, "frozen", False),
        "ffmpeg_in_use": FFMPEG,
        "ffmpeg_works": _ffmpeg_works(FFMPEG),
        "candidates": cands,
        "path_ffmpeg": shutil.which("ffmpeg"),
        "download_dir": str(DOWNLOAD_DIR),
        "download_dir_writable": os.access(str(DOWNLOAD_DIR), os.W_OK),
        "yt_dlp": __import__("yt_dlp").version.__version__,
    })


@app.route("/api/update-ytdlp", methods=["POST"])
def update_ytdlp():
    if getattr(sys, "frozen", False):
        return jsonify({"error": "Update is only available in development mode. Download the latest ReClip.exe from GitHub releases."}), 400
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "-U", "yt-dlp"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            return jsonify({"error": result.stderr.strip()}), 500
        import yt_dlp
        return jsonify({"ok": True, "version": yt_dlp.version.__version__})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/history", methods=["GET"])
def get_history():
    return jsonify({"history": load_history()})


@app.route("/api/history", methods=["POST"])
def add_history():
    data = request.json
    url = data.get("url", "").strip()
    title = data.get("title", "")
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    history = load_history()
    history.insert(0, {
        "url": url,
        "title": title,
        "thumbnail": data.get("thumbnail", ""),
        "filename": data.get("filename", ""),
        "format": data.get("format", "video"),
        "timestamp": str(uuid.uuid4())[:8],
    })
    save_history(history[:100])
    return jsonify({"ok": True})


@app.route("/api/history", methods=["DELETE"])
def clear_history():
    save_history([])
    return jsonify({"ok": True})


@app.route("/api/history/remove", methods=["POST"])
def remove_history_item():
    data = request.json
    timestamp = data.get("timestamp", "")
    history = load_history()
    history = [h for h in history if h.get("timestamp") != timestamp]
    save_history(history)
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8899))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port)
