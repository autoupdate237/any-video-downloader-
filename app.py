#!/usr/bin/env python3
"""
Any Video Downloader — paste any video link, download video/audio in all qualities.
Backend: Flask + yt-dlp (supports YouTube + 1000+ sites).
"""

import os
import re
import ipaddress
import socket
import shutil
import logging
import tempfile
import threading
import urllib.parse

import imageio_ffmpeg
import yt_dlp
from flask import (
    Flask,
    after_this_request,
    request,
    jsonify,
    send_file,
    Response,
    render_template,
    abort,
)

app = Flask(__name__)

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5000"))
ALLOW_PRIVATE_URLS = os.environ.get("ALLOW_PRIVATE_URLS", "0") == "1"
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "3"))
COOKIES_FILE = os.environ.get("YTDLP_COOKIES_FILE", "")
COOKIES_FROM_BROWSER = os.environ.get("YTDLP_COOKIES_FROM_BROWSER", "")
PROXY = os.environ.get("YTDLP_PROXY", "")
PLAYER_CLIENT = os.environ.get("YTDLP_PLAYER_CLIENT", "")

JOB_SEM = threading.BoundedSemaphore(MAX_CONCURRENT_JOBS)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("avd")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def base_opts() -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": 25,
        "retries": 3,
        "extractor_retries": 2,
        "nocheckcertificate": True,
        "noplaylist": True,
        "playlist_items": "1",
        "ffmpeg_location": FFMPEG_PATH,
        "http_headers": {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9,bn;q=0.8"},
    }
    if COOKIES_FILE and os.path.isfile(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    if COOKIES_FROM_BROWSER:
        opts["cookiesfrombrowser"] = (COOKIES_FROM_BROWSER,)
    if PROXY:
        opts["proxy"] = PROXY
    if PLAYER_CLIENT:
        opts["extractor_args"] = {"youtube": {"player_client": PLAYER_CLIENT.split(",")}}
    return opts


def human_size(n) -> str:
    if not n:
        return ""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return ""


def sanitize_filename(name: str, fallback: str = "video") -> str:
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", name or "").strip().rstrip(". ")
    name = re.sub(r"\s+", " ", name)
    return (name[:140] or fallback)


def is_safe_url(raw: str) -> bool:
    try:
        p = urllib.parse.urlparse(raw)
        if p.scheme not in ("http", "https") or not p.hostname:
            return False
        if ALLOW_PRIVATE_URLS:
            return True
        host = p.hostname
        # Block anything that resolves to private/loopback addresses (SSRF guard)
        if host in ("localhost",) or host.endswith(".localhost") or host.endswith(".local"):
            return False
        for fam, proto in ((socket.AF_INET, 0), (socket.AF_INET6, 0)):
            try:
                infos = socket.getaddrinfo(host, None, fam, proto)
            except socket.gaierror:
                continue
            for info in infos:
                ip = ipaddress.ip_address(info[4][0])
                if (
                    ip.is_private
                    or ip.is_loopback
                    or ip.is_link_local
                    or ip.is_reserved
                    or ip.is_multicast
                ):
                    return False
        return True
    except Exception:
        return False


def friendly_error(exc: Exception) -> tuple[str, str]:
    """Return (message_bn, message_en) for a yt-dlp error."""
    msg = str(exc)
    low = msg.lower()
    if "sign in to confirm" in low or "not a bot" in low or "cookies" in low and "youtube" in low:
        return (
            "YouTube bot-check করেছে। সার্ভারে cookies সেট করুন (README দেখুন)।",
            "YouTube asked for sign-in/bot verification. Configure cookies on the server (see README).",
        )
    if "private video" in low:
        return ("এই ভিডিওটি প্রাইভেট।", "This video is private.")
    if "members-only" in low or "join this channel" in low:
        return ("এটি members-only ভিডিও।", "This is a members-only video.")
    if "age" in low and ("confirm your age" in low or "age-restricted" in low):
        return (
            "বয়স-সীমাবদ্ধ ভিডিও — cookies ছাড়া ডাউনলোড সম্ভব নয়।",
            "Age-restricted video — requires cookies/sign-in.",
        )
    if "geo" in low and ("restrict" in low or "block" in low) or "not available in your country" in low:
        return ("এই ভিডিও আপনার দেশে ব্লকড।", "Video is geo-blocked in the server's country.")
    if "live" in low and ("event" in low or "stream" in low):
        return ("লাইভ স্ট্রিম ডাউনলোড করা যায় না।", "Live streams cannot be downloaded.")
    if "unsupported url" in low:
        return (
            "এই লিংক সাপোর্টেড নয়। লিংকটি ঠিক আছে কিনা দেখুন।",
            "Unsupported URL. Please check the link.",
        )
    if "is not a valid url" in low:
        return ("লিংকটি সঠিক নয়।", "The link is not valid.")
    if "video unavailable" in low:
        return ("ভিডিওটি পাওয়া যাচ্ছে না (মুছে ফেলা হয়েছে বা ব্লকড)।", "Video unavailable (removed or blocked).")
    if "ssl" in low or "connection" in low or "timed out" in low or "network" in low:
        return (
            "সার্ভার থেকে সাইটে কানেকশন পাওয়া যাচ্ছে না। নেটওয়ার্ক/ফায়ারওয়াল চেক করুন।",
            "Cannot reach the site from the server. Check network/firewall.",
        )
    if "copyright" in low:
        return ("কপিরাইটের কারণে ডাউনলোড ব্লক করা হয়েছে।", "Download blocked due to copyright.")
    return ("ভিডিওর তথ্য আনা যায়নি।", "Could not fetch video info.")


# --------------------------------------------------------------------------- #
# Format processing
# --------------------------------------------------------------------------- #
def process_formats(info: dict) -> dict:
    fmts = info.get("formats") or []
    video_by_height = {}
    audio_list = []

    for f in fmts:
        vcodec = f.get("vcodec") or "none"
        acodec = f.get("acodec") or "none"
        if vcodec != "none" and f.get("height"):
            h = int(f["height"])
            score = (
                1 if (f.get("ext") == "mp4" and f.get("protocol", "") not in ("m3u8", "m3u8_native")) else 0,
                1 if acodec != "none" else 0,
                (f.get("tbr") or 0),
            )
            cur = video_by_height.get(h)
            if cur is None or score > cur["_score"]:
                item = {
                    "format_id": f["format_id"],
                    "quality": f"{h}p",
                    "height": h,
                    "ext": f.get("ext", "mp4"),
                    "fps": f.get("fps"),
                    "has_audio": acodec != "none",
                    "needs_merge": acodec == "none",
                    "filesize": f.get("filesize") or f.get("filesize_approx"),
                    "protocol": f.get("protocol", "https"),
                    "_score": score,
                }
                video_by_height[h] = item
        elif vcodec == "none" and acodec != "none":
            audio_list.append(
                {
                    "format_id": f["format_id"],
                    "abr": f.get("abr") or 0,
                    "ext": f.get("ext", "m4a"),
                    "filesize": f.get("filesize") or f.get("filesize_approx"),
                    "protocol": f.get("protocol", "https"),
                }
            )

    videos = sorted(video_by_height.values(), key=lambda x: -x["height"])
    for v in videos:
        v["filesize_string"] = human_size(v["filesize"])
        v.pop("_score", None)

    # Fallback for direct links / sites without metadata (e.g. a bare .mp4 URL):
    # offer the best available format as a single "Original quality" entry.
    if not videos and not audio_list and fmts:
        best = max(fmts, key=lambda f: (f.get("tbr") or 0, f.get("filesize") or 0))
        acodec = best.get("acodec")
        vcodec = best.get("vcodec")
        videos.append(
            {
                "format_id": best["format_id"],
                "quality": "Original",
                "height": None,
                "ext": best.get("ext", "mp4"),
                "fps": best.get("fps"),
                "has_audio": True,
                "needs_merge": False,
                "filesize": best.get("filesize") or best.get("filesize_approx"),
                "protocol": best.get("protocol", "https"),
                "filesize_string": human_size(best.get("filesize") or best.get("filesize_approx")),
            }
        )

    seen, audios = set(), []
    for a in sorted(audio_list, key=lambda x: -x["abr"]):
        key = round(a["abr"])
        if key in seen:
            continue
        seen.add(key)
        a["quality"] = f"{int(round(a['abr']))} kbps" if a["abr"] else a["ext"].upper()
        a["filesize_string"] = human_size(a["filesize"])
        audios.append(a)
        if len(audios) >= 4:
            break

    return {"video": videos, "audio": audios}


def extract_info_safe(url: str, download: bool = False) -> dict:
    opts = base_opts()
    opts["skip_download"] = not download
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=download)


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify(ok=True, ffmpeg=os.path.isfile(FFMPEG_PATH), yt_dlp=yt_dlp.version.__version__)


@app.post("/api/info")
def api_info():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify(ok=False, error="লিংক দিন।", error_en="Please provide a URL."), 400
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if not is_safe_url(url):
        return (
            jsonify(ok=False, error="লিংকটি অনুমোদিত নয়।", error_en="This URL is not allowed."),
            400,
        )
    try:
        info = extract_info_safe(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        bn, en = friendly_error(e)
        log.warning("info failed for %s: %s", url, e)
        return jsonify(ok=False, error=bn, error_en=en), 502
    except Exception as e:  # noqa: BLE001
        log.exception("unexpected error for %s", url)
        return jsonify(ok=False, error="সার্ভার সমস্যা।", error_en="Server error."), 500

    if info.get("_type") == "playlist":
        entries = info.get("entries") or []
        info = entries[0] if entries else info

    fmts = process_formats(info)
    if not fmts["video"] and not fmts["audio"]:
        return (
            jsonify(
                ok=False,
                error="কোনো ডাউনলোডযোগ্য ফরম্যাট পাওয়া যায়নি।",
                error_en="No downloadable formats found.",
            ),
            502,
        )

    payload = {
        "ok": True,
        "id": info.get("id"),
        "title": info.get("title") or "Untitled",
        "uploader": info.get("uploader") or info.get("channel") or info.get("uploader_id") or "",
        "duration": info.get("duration"),
        "duration_string": info.get("duration_string") or "",
        "thumbnail": info.get("thumbnail")
        or ((info.get("thumbnails") or [{}])[-1].get("url") if info.get("thumbnails") else None),
        "webpage_url": info.get("webpage_url") or url,
        "extractor": (info.get("extractor_key") or "").replace("Generic", "Direct link"),
        "is_live": bool(info.get("is_live")),
        "view_count": info.get("view_count"),
        **fmts,
    }
    return jsonify(payload)


@app.get("/download")
def download():
    url = (request.args.get("url") or "").strip()
    fid = (request.args.get("fid") or "").strip()
    mode = (request.args.get("mode") or "video").strip()
    quality = (request.args.get("q") or "").strip()

    if not url or not is_safe_url(url):
        abort(400, "Invalid URL")

    title_hint = sanitize_filename(urllib.parse.unquote(request.args.get("t") or "video"))

    # ---- MP3 conversion -------------------------------------------------- #
    if mode == "audio-mp3":
        if not JOB_SEM.acquire(blocking=False):
            return jsonify(
                ok=False,
                error="সার্ভার ব্যস্ত, একটু পরে চেষ্টা করুন।",
                error_en="Server busy, please retry shortly.",
            ), 429
        try:
            return _send_converted(url, "mp3", title_hint)
        finally:
            JOB_SEM.release()

    if not fid:
        abort(400, "Missing format id")

    # ---- Re-extract to get fresh, server-usable URLs ---------------------- #
    try:
        info = extract_info_safe(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        bn, en = friendly_error(e)
        return jsonify(ok=False, error=bn, error_en=en), 502

    if info.get("_type") == "playlist":
        entries = info.get("entries") or []
        info = entries[0] if entries else info

    fmt = next((f for f in (info.get("formats") or []) if str(f.get("format_id")) == fid), None)
    if fmt is None:
        return jsonify(ok=False, error="ফরম্যাট পাওয়া যায়নি।", error_en="Format not found."), 404

    vcodec = fmt.get("vcodec") or "none"
    acodec = fmt.get("acodec") or "none"

    ext = fmt.get("ext") or "mp4"
    if mode == "audio":
        ext = fmt.get("ext") or "m4a"
        base = f"{title_hint} ({quality or 'audio'})"
    else:
        base = f"{title_hint} ({quality or str(fmt.get('height', '') ) + 'p' if fmt.get('height') else quality or ext})"
    fname = sanitize_filename(base, "download") + "." + ext

    proto = fmt.get("protocol", "https") or "https"

    # ---- Progressive (video+audio or pure audio): stream passthrough ----- #
    if vcodec == "none" or acodec != "none":
        direct = fmt.get("url")
        if not direct:
            return jsonify(ok=False, error="সরাসরি লিংক নেই।", error_en="No direct link."), 502
        if "m3u8" in proto or "dash" in proto:
            # manifest URL — browser can't save it; download & remux via ffmpeg
            if not JOB_SEM.acquire(blocking=False):
                return jsonify(
                    ok=False, error="সার্ভার ব্যস্ত।", error_en="Server busy."
                ), 429
            try:
                return _send_exact_format(url, fid, fname)
            finally:
                JOB_SEM.release()
        headers = dict(fmt.get("http_headers") or {})
        return _passthrough(direct, headers, fname, ext)

    # ---- Video-only (DASH): download + merge with ffmpeg ------------------ #
    if not JOB_SEM.acquire(blocking=False):
        return jsonify(
            ok=False,
            error="সার্ভার ব্যস্ত, একটু পরে চেষ্টা করুন।",
            error_en="Server busy, please retry shortly.",
        ), 429
    try:
        return _send_merged(url, fid, fname)
    finally:
        JOB_SEM.release()


def _passthrough(direct_url: str, headers: dict, fname: str, ext: str) -> Response:
    """Stream the media through the server (works even when the browser can't)."""
    import requests  # local import: only needed for downloads

    fwd = {k: v for k, v in headers.items() if k.lower() in (
        "user-agent", "referer", "accept", "accept-language", "cookie"
    )}
    fwd.setdefault("User-Agent", UA)
    range_header = request.headers.get("Range")
    if range_header:
        fwd["Range"] = range_header

    try:
        upstream = requests.get(direct_url, headers=fwd, stream=True, timeout=(15, 60), allow_redirects=True)
    except Exception as e:  # noqa: BLE001
        log.warning("passthrough failed: %s", e)
        return jsonify(ok=False, error="ডাউনলোড শুরু করা যায়নি।", error_en="Could not start download."), 502

    if upstream.status_code not in (200, 206):
        upstream.close()
        return jsonify(ok=False, error="মিডিয়া সার্ভার রেসপন্স দেয়নি।", error_en="Media server refused."), 502

    resp_headers = {
        "Content-Disposition": f'attachment; filename="{fname}"',
        "Accept-Ranges": "bytes",
    }
    for h in ("Content-Length", "Content-Range"):
        if h in upstream.headers:
            resp_headers[h] = upstream.headers[h]

    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=256 * 1024):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    return Response(generate(), status=upstream.status_code,
                    content_type=upstream.headers.get("Content-Type", "application/octet-stream"),
                    headers=resp_headers)


def _download_to_temp(url: str, extra_opts: dict, outtmpl: str):
    """Run yt-dlp download in a temp dir; return (tempdir, filepath)."""
    td = tempfile.mkdtemp(prefix="avd_")
    opts = base_opts()
    opts.update(
        {
            "outtmpl": os.path.join(td, outtmpl),
            "skip_download": False,
            "noprogress": True,
            "quiet": True,
            "restrictfilenames": False,
        }
    )
    opts.update(extra_opts)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        path = None
        if isinstance(info, dict):
            rds = info.get("requested_downloads") or []
            if rds:
                path = rds[0].get("filepath")
        if not path or not os.path.isfile(path):
            # fallback: newest file in tempdir
            files = [os.path.join(td, f) for f in os.listdir(td)]
            if not files:
                raise RuntimeError("download produced no file")
            path = max(files, key=os.path.getmtime)
        return td, path
    except Exception:
        shutil.rmtree(td, ignore_errors=True)
        raise


def _send_exact_format(url: str, fid: str, fname: str):
    """Download exactly one format (e.g. HLS stream) to temp and send."""
    try:
        td, path = _download_to_temp(url, {"format": fid}, "%(title).140s.%(ext)s")
    except yt_dlp.utils.DownloadError as e:
        bn, en = friendly_error(e)
        return jsonify(ok=False, error=bn, error_en=en), 502
    except Exception:  # noqa: BLE001
        log.exception("exact format download failed")
        return jsonify(ok=False, error="ডাউনলোড ব্যর্থ।", error_en="Download failed."), 500

    @after_this_request
    def _cleanup(response):
        shutil.rmtree(td, ignore_errors=True)
        return response

    return send_file(path, as_attachment=True, download_name=fname, conditional=True)


def _send_merged(url: str, fid: str, fname: str):
    """Download selected video-only format + best audio, merge to mp4, send."""
    extra = {
        "format": f"{fid}+bestaudio/{fid}/best",
        "merge_output_format": "mp4",
    }
    try:
        td, path = _download_to_temp(url, extra, "%(title).140s.%(ext)s")
    except yt_dlp.utils.DownloadError as e:
        bn, en = friendly_error(e)
        return jsonify(ok=False, error=bn, error_en=en), 502
    except Exception as e:  # noqa: BLE001
        log.exception("merge failed")
        return jsonify(ok=False, error="মার্জ করা যায়নি।", error_en="Merge failed."), 500

    @after_this_request
    def _cleanup(response):
        shutil.rmtree(td, ignore_errors=True)
        return response

    return send_file(path, as_attachment=True, download_name=fname, conditional=True)


def _send_converted(url: str, codec: str, title_hint: str):
    """Extract audio to mp3 and send."""
    extra = {
        "format": "bestaudio/best",
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": codec, "preferredquality": "192"}
        ],
    }
    try:
        td, path = _download_to_temp(url, extra, "%(title).140s.%(ext)s")
    except yt_dlp.utils.DownloadError as e:
        bn, en = friendly_error(e)
        return jsonify(ok=False, error=bn, error_en=en), 502
    except Exception as e:  # noqa: BLE001
        log.exception("audio convert failed")
        return jsonify(ok=False, error="অডিও কনভার্ট করা যায়নি।", error_en="Audio conversion failed."), 500

    fname = f"{title_hint} (MP3 192kbps).{codec}"

    @after_this_request
    def _cleanup(response):
        shutil.rmtree(td, ignore_errors=True)
        return response

    return send_file(path, as_attachment=True, download_name=fname, conditional=True)


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, threaded=True, debug=os.environ.get("FLASK_DEBUG") == "1")
