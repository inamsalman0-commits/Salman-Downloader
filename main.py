"""
Salman Downloader
------------------
Advanced YouTube video downloader built with Python + Kivy.
Single-file app (main.py) ready to be packaged with Buildozer.

Features:
- Paste a video link, fetch title/thumbnail/available qualities + sizes
- Choose a quality and download it
- Live progress bar with percentage, download speed and ETA
- Saves finished videos into a dedicated "Salman Downloader" folder
  on the device's shared storage (visible in any file manager)
- Dark, modern UI

NOTE ON QUALITY LIST:
Only formats that already contain BOTH video and audio in a single
stream are listed. YouTube's very high qualities (1080p+) are usually
split into separate video-only and audio-only streams that need to be
merged with ffmpeg. Bundling ffmpeg inside an Android APK is heavy and
unreliable with Buildozer, so this app intentionally sticks to
combined (progressive) streams, which typically go up to 720p. This
keeps the app fast, small and 100% working out of the box.
"""

import os
import threading
import traceback
from urllib.request import urlretrieve

import yt_dlp

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.utils import platform

# ----------------------------------------------------------------------
# Global window / theme setup
# ----------------------------------------------------------------------
Window.clearcolor = (0.133, 0.133, 0.133, 1)  # #222222 dark grey background

BLUE = (0.129, 0.588, 0.953, 1)   # modern blue
GREEN = (0.298, 0.686, 0.314, 1)  # modern green
RED = (0.90, 0.30, 0.30, 1)
CARD = (0.18, 0.18, 0.18, 1)
LIGHT_TEXT = (0.95, 0.95, 0.95, 1)
MUTED_TEXT = (0.65, 0.65, 0.65, 1)

KV = '''
<RoundedButton@Button>:
    background_color: 0,0,0,0
    background_normal: ''
    background_down: ''
    color: 0.95, 0.95, 0.95, 1
    font_size: '16sp'
    bold: True
    btn_color: 0.129, 0.588, 0.953, 1
    canvas.before:
        Color:
            rgba: self.btn_color if self.state == 'normal' else (self.btn_color[0]*0.8, self.btn_color[1]*0.8, self.btn_color[2]*0.8, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [16,]

<CardBox@BoxLayout>:
    canvas.before:
        Color:
            rgba: 0.18, 0.18, 0.18, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [14,]

<RootWidget>:
    orientation: 'vertical'
    padding: [20, 20, 20, 20]
    spacing: 14

    Label:
        text: "Salman Downloader"
        font_size: '26sp'
        bold: True
        color: 0.129, 0.588, 0.953, 1
        size_hint_y: None
        height: '42sp'

    Label:
        text: "Made by Salman Inam"
        font_size: '12sp'
        color: 0.65, 0.65, 0.65, 1
        size_hint_y: None
        height: '18sp'

    TextInput:
        id: link_input
        hint_text: "Paste video link here..."
        multiline: False
        size_hint_y: None
        height: '48sp'
        background_color: 0.18, 0.18, 0.18, 1
        foreground_color: 0.95, 0.95, 0.95, 1
        hint_text_color: 0.55, 0.55, 0.55, 1
        cursor_color: 1, 1, 1, 1
        padding: [14, 12, 14, 12]
        font_size: '15sp'

    RoundedButton:
        id: fetch_btn
        text: "Fetch Video Info"
        btn_color: 0.129, 0.588, 0.953, 1
        size_hint_y: None
        height: '46sp'
        on_release: root.fetch_info()

    CardBox:
        id: info_card
        orientation: 'horizontal'
        size_hint_y: None
        height: '110sp'
        padding: 10
        spacing: 12
        opacity: 0
        disabled: True

        Image:
            id: thumb_img
            size_hint_x: None
            width: '140sp'
            allow_stretch: True
            keep_ratio: True

        BoxLayout:
            orientation: 'vertical'
            spacing: 4

            Label:
                id: title_lbl
                text: ""
                color: 0.95, 0.95, 0.95, 1
                font_size: '14sp'
                bold: True
                halign: 'left'
                valign: 'top'
                text_size: self.size
                shorten: True
                shorten_from: 'right'

            Label:
                id: meta_lbl
                text: ""
                color: 0.65, 0.65, 0.65, 1
                font_size: '12sp'
                halign: 'left'
                valign: 'top'
                text_size: self.size

    Spinner:
        id: quality_spinner
        text: "Select Quality"
        values: []
        size_hint_y: None
        height: '46sp'
        background_color: 0,0,0,0
        background_normal: ''
        background_down: ''
        color: 0.95, 0.95, 0.95, 1
        canvas.before:
            Color:
                rgba: 0.18, 0.18, 0.18, 1
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [12,]
        on_text: root.on_quality_selected(self.text)

    RoundedButton:
        id: download_btn
        text: "Download Video"
        btn_color: 0.298, 0.686, 0.314, 1
        size_hint_y: None
        height: '48sp'
        on_release: root.start_download()

    ProgressBar:
        id: progress_bar
        max: 100
        value: 0
        size_hint_y: None
        height: '10sp'

    Label:
        id: progress_lbl
        text: ""
        color: 0.95, 0.95, 0.95, 1
        font_size: '13sp'
        size_hint_y: None
        height: '20sp'

    Label:
        id: status_lbl
        text: "Paste a link and tap Fetch Video Info"
        color: 0.65, 0.65, 0.65, 1
        font_size: '13sp'
        size_hint_y: None
        height: '20sp'

    Widget:
'''


class RootWidget(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.video_info = None          # full yt-dlp info dict
        self.formats_map = {}           # display label -> format_id
        self.selected_format_id = None
        self.download_folder = get_download_folder()

    # ------------------------------------------------------------------
    # STEP 1: Fetch video info (title, thumbnail, formats)
    # ------------------------------------------------------------------
    def fetch_info(self):
        url = self.ids.link_input.text.strip()
        if not url:
            self.set_status("Please paste a video link first.", error=True)
            return

        self.ids.fetch_btn.disabled = True
        self.set_status("Fetching video info...", error=False)
        self.ids.info_card.opacity = 0
        self.ids.info_card.disabled = True
        self.ids.quality_spinner.values = []
        self.ids.quality_spinner.text = "Select Quality"
        self.ids.size_lbl_text = ""

        threading.Thread(target=self._fetch_info_thread, args=(url,), daemon=True).start()

    def _fetch_info_thread(self, url):
        try:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "noplaylist": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            formats = build_quality_list(info)
            thumb_url = info.get("thumbnail")
            thumb_path = None
            if thumb_url:
                try:
                    thumb_path = os.path.join(get_cache_folder(), "thumb.jpg")
                    urlretrieve(thumb_url, thumb_path)
                except Exception:
                    thumb_path = None

            Clock.schedule_once(
                lambda dt: self._on_info_ready(info, formats, thumb_path), 0
            )
        except Exception as e:
            traceback.print_exc()
            Clock.schedule_once(
                lambda dt: self.set_status(f"Error fetching info: {e}", error=True), 0
            )
            Clock.schedule_once(lambda dt: setattr(self.ids.fetch_btn, "disabled", False), 0)

    def _on_info_ready(self, info, formats, thumb_path):
        self.video_info = info
        self.formats_map = {label: fmt_id for label, fmt_id, _ in formats}
        self.sizes_map = {label: size_str for label, _, size_str in formats}

        self.ids.title_lbl.text = info.get("title", "Unknown title")
        duration = info.get("duration") or 0
        uploader = info.get("uploader") or "Unknown channel"
        self.ids.meta_lbl.text = f"{uploader}  |  {format_duration(duration)}"

        if thumb_path and os.path.exists(thumb_path):
            self.ids.thumb_img.source = thumb_path
            self.ids.thumb_img.reload()

        self.ids.info_card.opacity = 1
        self.ids.info_card.disabled = False

        labels = list(self.formats_map.keys())
        if labels:
            self.ids.quality_spinner.values = labels
            self.ids.quality_spinner.text = labels[0]
            self.on_quality_selected(labels[0])
            self.set_status("Video found. Choose a quality and download.", error=False)
        else:
            self.set_status("No downloadable combined formats found for this video.", error=True)

        self.ids.fetch_btn.disabled = False

    def on_quality_selected(self, label):
        self.selected_format_id = self.formats_map.get(label)
        size_str = self.sizes_map.get(label, "")
        if size_str:
            self.set_status(f"Selected: {label}  ({size_str})", error=False)

    # ------------------------------------------------------------------
    # STEP 2: Download
    # ------------------------------------------------------------------
    def start_download(self):
        if not self.video_info or not self.selected_format_id:
            self.set_status("Please fetch a video and select a quality first.", error=True)
            return

        self.ids.download_btn.disabled = True
        self.ids.fetch_btn.disabled = True
        self.ids.progress_bar.value = 0
        self.set_status("Downloading...", error=False)

        threading.Thread(target=self._download_thread, daemon=True).start()

    def _download_thread(self):
        url = self.ids.link_input.text.strip()
        out_folder = self.download_folder
        safe_title = sanitize_filename(self.video_info.get("title", "video"))
        outtmpl = os.path.join(out_folder, f"{safe_title}.%(ext)s")

        def progress_hook(d):
            Clock.schedule_once(lambda dt: self._handle_progress(d), 0)

        ydl_opts = {
            "format": self.selected_format_id,
            "outtmpl": outtmpl,
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            Clock.schedule_once(lambda dt: self._on_download_success(out_folder), 0)
        except Exception as e:
            traceback.print_exc()
            Clock.schedule_once(
                lambda dt: self.set_status(f"Download failed: {e}", error=True), 0
            )
            Clock.schedule_once(lambda dt: self._reset_buttons(), 0)

    def _handle_progress(self, d):
        status = d.get("status")
        if status == "downloading":
            downloaded = d.get("downloaded_bytes", 0) or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            speed = d.get("speed") or 0
            eta = d.get("eta")

            percent = (downloaded / total * 100) if total else 0
            self.ids.progress_bar.value = percent

            speed_str = f"{speed / (1024 * 1024):.2f} MB/s" if speed else "-- MB/s"
            eta_str = format_duration(eta) if eta is not None else "--:--"
            downloaded_str = f"{downloaded / (1024 * 1024):.1f} MB"
            total_str = f"{total / (1024 * 1024):.1f} MB" if total else "?"

            self.ids.progress_lbl.text = (
                f"{percent:0.1f}%   {downloaded_str}/{total_str}   "
                f"{speed_str}   ETA {eta_str}"
            )
            self.set_status("Downloading...", error=False)

        elif status == "finished":
            self.ids.progress_bar.value = 100
            self.set_status("Finalizing file...", error=False)

    def _on_download_success(self, out_folder):
        self.set_status(f"Success! Saved in: {out_folder}", error=False, success=True)
        self._reset_buttons()

    def _reset_buttons(self):
        self.ids.download_btn.disabled = False
        self.ids.fetch_btn.disabled = False

    # ------------------------------------------------------------------
    def set_status(self, text, error=False, success=False):
        self.ids.status_lbl.text = text
        if error:
            self.ids.status_lbl.color = RED
        elif success:
            self.ids.status_lbl.color = GREEN
        else:
            self.ids.status_lbl.color = MUTED_TEXT


# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def build_quality_list(info):
    """
    Returns a list of tuples: (display_label, format_id, size_string)
    Only formats that contain BOTH audio and video are included so the
    app never needs ffmpeg to merge streams.
    """
    results = []
    seen_heights = set()
    formats = info.get("formats", []) or []

    for fmt in formats:
        vcodec = fmt.get("vcodec")
        acodec = fmt.get("acodec")
        if not vcodec or vcodec == "none":
            continue
        if not acodec or acodec == "none":
            continue

        height = fmt.get("height")
        ext = fmt.get("ext", "mp4")
        if not height:
            continue
        if height in seen_heights:
            continue
        seen_heights.add(height)

        filesize = fmt.get("filesize") or fmt.get("filesize_approx")
        size_str = f"{filesize / (1024 * 1024):.1f} MB" if filesize else "size unknown"

        label = f"{height}p  ({ext})  -  {size_str}"
        results.append((label, fmt.get("format_id"), size_str))

    # Sort by height, highest quality first
    def height_of(item):
        try:
            return int(item[0].split("p")[0])
        except Exception:
            return 0

    results.sort(key=height_of, reverse=True)
    return results


def format_duration(seconds):
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "--:--"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


def sanitize_filename(name):
    invalid = '<>:"/\\|?*'
    for ch in invalid:
        name = name.replace(ch, "")
    return name.strip()[:120] if name.strip() else "video"


def get_download_folder():
    """
    Returns (and creates) the 'Salman Downloader' folder inside the
    device's public Downloads directory, so it shows up in any file
    manager app and stays compatible with Android 11+ scoped storage
    (works together with the MANAGE_EXTERNAL_STORAGE permission).
    """
    if platform == "android":
        try:
            from android.storage import primary_external_storage_path
            base = os.path.join(primary_external_storage_path(), "Download")
        except Exception:
            base = "/storage/emulated/0/Download"
    else:
        base = os.path.join(os.path.expanduser("~"), "Downloads")

    folder = os.path.join(base, "Salman Downloader")
    os.makedirs(folder, exist_ok=True)
    return folder


def get_cache_folder():
    if platform == "android":
        try:
            from android import mActivity
            folder = mActivity.getCacheDir().getAbsolutePath()
        except Exception:
            folder = os.path.join(os.path.expanduser("~"), ".cache")
    else:
        folder = os.path.join(os.path.expanduser("~"), ".cache")
    os.makedirs(folder, exist_ok=True)
    return folder


def request_android_permissions():
    if platform == "android":
        try:
            from android.permissions import request_permissions, Permission
            request_permissions(
                [
                    Permission.INTERNET,
                    Permission.WRITE_EXTERNAL_STORAGE,
                    Permission.READ_EXTERNAL_STORAGE,
                ]
            )
        except Exception:
            pass


# ----------------------------------------------------------------------
# App
# ----------------------------------------------------------------------
class SalmanDownloaderApp(App):
    def build(self):
        self.title = "Salman Downloader"
        request_android_permissions()
        Builder.load_string(KV)
        return RootWidget()


if __name__ == "__main__":
    SalmanDownloaderApp().run()
