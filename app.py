import os
import sys
import json
import uuid
import glob
import threading
import subprocess
from pathlib import Path

import yt_dlp

from flask import Flask, request, jsonify, send_file, render_template, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
    DOWNLOAD_DIR = BASE_DIR / "downloads"
    HISTORY_FILE = BASE_DIR / "history.json"
    TOOLS_DIR = str(BASE_DIR / "tools")
    FFMPEG = os.path.join(TOOLS_DIR, "ffmpeg.exe")
    if not os.path.exists(FFMPEG):
        try:
            import imageio_ffmpeg
            FFMPEG = str(Path(imageio_ffmpeg.get_ffmpeg_exe()).parent / "ffmpeg.exe")
        except Exception:
            FFMPEG = "ffmpeg"
else:
    BASE_DIR = Path(__file__).resolve().parent
    DOWNLOAD_DIR = Path("/tmp/reclip/downloads")
    HISTORY_FILE = Path("/tmp/reclip/history.json")
    TOOLS_DIR = str(BASE_DIR / "tools")
    FFMPEG = "ffmpeg"

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

jobs = {}


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
        "ffmpeg_location": FFMPEG,
        "postprocessors": postprocessors,
        "progress_hooks": [progress_hook],
        "writesubtitles": subtitles,
        "subtitleslangs": ["en"] if subtitles else None,
        "subtitlesformat": "srt/vtt/best",
    }
    if merge_ext:
        ydl_opts["merge_output_format"] = merge_ext
    if trim_start and trim_end:
        ydl_opts["download_ranges"] = [{"start_time": trim_start, "end_time": trim_end}]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        files = glob.glob(str(DOWNLOAD_DIR / f"{job_id}.*"))
        if not files:
            job["status"] = "error"
            job["error"] = "Download completed but no file was found"
            return

        if format_choice == "audio":
            target = [f for f in files if f.endswith(".mp3")]
            chosen = target[0] if target else files[0]
        else:
            target = [f for f in files if f.endswith(".mp4")]
            chosen = target[0] if target else files[0]

        for f in files:
            if f != chosen:
                try:
                    os.remove(f)
                except OSError:
                    pass

        job["status"] = "done"
        job["file"] = chosen
        job["progress"] = {"downloaded": 1, "total": 1, "speed": 0, "eta": 0}
        ext = os.path.splitext(chosen)[1]
        title = job.get("title", "").strip()
        if title:
            safe_title = "".join(c for c in title if c not in r'\/:*?"<>|').strip()[:100].strip()
            job["filename"] = f"{safe_title}{ext}" if safe_title else os.path.basename(chosen)
        else:
            job["filename"] = os.path.basename(chosen)

        history = load_history()
        history.insert(0, {
            "url": url,
            "title": job.get("title", ""),
            "thumbnail": job.get("thumbnail", ""),
            "filename": job["filename"],
            "format": format_choice,
            "timestamp": str(uuid.uuid4())[:8],
        })
        save_history(history[:100])
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)


@app.route("/")
def index():
    return render_template("index.html")


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
        "ffmpeg_location": FFMPEG,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        best_by_height = {}
        for f in info.get("formats", []):
            height = f.get("height")
            if height and f.get("vcodec", "none") != "none":
                tbr = f.get("tbr") or 0
                if height not in best_by_height or tbr > (best_by_height[height].get("tbr") or 0):
                    best_by_height[height] = f

        formats = []
        for height, f in best_by_height.items():
            formats.append({
                "id": f["format_id"],
                "label": f"{height}p",
                "height": height,
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
        return jsonify({"error": str(e)}), 400


@app.route("/api/playlist", methods=["POST"])
def get_playlist_info():
    data = request.json
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "ffmpeg_location": FFMPEG,
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
    return send_file(job["file"])


@app.route("/api/ytdlp-version")
def ytdlp_version():
    try:
        import yt_dlp
        return jsonify({"version": yt_dlp.version.__version__})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
