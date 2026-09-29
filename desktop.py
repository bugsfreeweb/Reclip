import os
import sys
import time
import threading
import traceback
from pathlib import Path

PORT = 8899
URL = f"http://127.0.0.1:{PORT}"


def start_server():
    try:
        from app import app
        app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)
    except Exception:
        traceback.print_exc()


def wait_for_server():
    import urllib.request
    for _ in range(100):
        try:
            urllib.request.urlopen(URL, timeout=1)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def main():
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent
    os.chdir(base)

    import imageio_ffmpeg
    ffmpeg_dir = str(Path(imageio_ffmpeg.get_ffmpeg_exe()).parent)
    os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    if not wait_for_server():
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("ReClip", "Failed to start the local server.")
        sys.exit(1)

    import webview

    splash_url = f"{URL}/static/splash.html"

    webview.create_window(
        "ReClip",
        splash_url,
        width=1100,
        height=750,
        min_size=(800, 600),
    )
    webview.start()


if __name__ == "__main__":
    main()
