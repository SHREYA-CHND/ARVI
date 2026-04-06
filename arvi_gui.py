"""
ARVI — AI Mood-Based Music Assistant (YouTube Music Version)

Single-file implementation that wires together:
- GUI manager with animated background
- Song recognition engine (local + online fallback)
- Mood prediction engine with caching
- Decision controller
- YouTube Music redirector
"""

import csv
import json
import os
import threading
import time
import urllib.parse
import webbrowser

import tkinter as tk
from tkinter import messagebox

try:
    from rapidfuzz import process as rf_process, fuzz as rf_fuzz  # type: ignore
    HAS_RAPIDFUZZ = True
except Exception:
    import difflib

    HAS_RAPIDFUZZ = False

try:
    import requests  # type: ignore
except Exception:
    requests = None  # type: ignore

try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:
    BeautifulSoup = None  # type: ignore

# -----------------------------
# CONSTANTS & FILE PATHS
# -----------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SONGS_CSV = os.path.join(BASE_DIR, "songs.csv")
MOOD_CACHE_FILE = os.path.join(BASE_DIR, "mood_cache.json")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")

YTM_SEARCH_BASE = "https://music.youtube.com/search?q="

MOOD_CATEGORIES = [
    "Happy",
    "Sad",
    "Calm",
    "Romantic",
    "Energetic",
    "Party",
    "Emotional",
    "Devotional",
]

OPPOSITE_MOOD = {
    "Calm": "Energetic",
    "Energetic": "Calm",
    "Sad": "Happy",
    "Happy": "Sad",
    "Romantic": "Party",
    "Party": "Romantic",
    "Emotional": "Energetic",
    # Devotional has no explicit pair in spec; map to Calm for contrast
    "Devotional": "Calm",
}

MOOD_STYLES = {
    "Happy": ("#FFE066", "😄"),
    "Sad": ("#74C0FC", "😢"),
    "Calm": ("#B2F2BB", "😌"),
    "Energetic": ("#FF8787", "🔥"),
    "Romantic": ("#FFC9DE", "❤️"),
    "Party": ("#FFB8B8", "🎉"),
    "Emotional": ("#B197FC", "🥺"),
    "Devotional": ("#FFD8A8", "🕉️"),
}

DEFAULT_STYLE = ("#E9ECEF", "🎵")

# -----------------------------
# DATA PERSISTENCE HELPERS
# -----------------------------


def ensure_files_exist() -> None:
    """Create required data files with safe defaults if missing."""
    if not os.path.exists(SONGS_CSV):
        try:
            with open(SONGS_CSV, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["title", "artist", "mood"])
                writer.writerow(["Hai Rama Ye Kya Hua", "Unknown Artist", "Calm"])
        except Exception:
            pass

    if not os.path.exists(MOOD_CACHE_FILE):
        try:
            with open(MOOD_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    if not os.path.exists(SETTINGS_FILE):
        try:
            default_settings = {
                "animation_speed_ms": 80,
                "similarity_threshold": 70,
            }
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(default_settings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


def load_settings() -> dict:
    ensure_files_exist()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {}
            return data
    except Exception:
        return {}


def load_songs() -> list:
    ensure_files_exist()
    songs = []
    try:
        with open(SONGS_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                title = (row.get("title") or "").strip()
                artist = (row.get("artist") or "").strip()
                mood = (row.get("mood") or "").strip()
                if title:
                    songs.append({"title": title, "artist": artist, "mood": mood})
    except Exception:
        pass
    return songs


def load_mood_cache() -> dict:
    ensure_files_exist()
    try:
        with open(MOOD_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_mood_cache(cache: dict) -> None:
    try:
        with open(MOOD_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


SETTINGS = load_settings()
ALL_SONGS = load_songs()
MOOD_CACHE = load_mood_cache()

# -----------------------------
# SONG RECOGNITION ENGINE
# -----------------------------


def normalize_key(text: str) -> str:
    return " ".join(text.lower().strip().split())


def fuzzy_similarity(a: str, b: str) -> float:
    a = a.lower().strip()
    b = b.lower().strip()
    if not a or not b:
        return 0.0

    if HAS_RAPIDFUZZ:
        return float(rf_fuzz.WRatio(a, b))
    else:
        return difflib.SequenceMatcher(None, a, b).ratio() * 100.0


def find_best_local_match(query: str) -> tuple | None:
    """Return (song_row, score) or None."""
    if not ALL_SONGS:
        return None

    best_row = None
    best_score = 0.0
    for row in ALL_SONGS:
        title = row.get("title") or ""
        score = fuzzy_similarity(query, title)
        if score > best_score:
            best_score = score
            best_row = row

    if best_row is None:
        return None

    return best_row, best_score


def fetch_online_metadata(query: str) -> dict:
    """
    Online Music Search Engine.
    Tries to fetch basic metadata from YouTube Music; never raises.
    """
    url = YTM_SEARCH_BASE + urllib.parse.quote_plus(query)
    meta = {
        "search_url": url,
        "title": query,
        "keywords": "",
        "source": "online",
    }

    if requests is None:
        return meta

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=3)
        resp.raise_for_status()

        page_title = ""
        if BeautifulSoup is not None:
            soup = BeautifulSoup(resp.text, "html.parser")
            if soup.title and soup.title.string:
                page_title = soup.title.string.strip()
        else:
            # Fallback: try to extract <title> manually
            text = resp.text
            start = text.lower().find("<title>")
            end = text.lower().find("</title>")
            if 0 <= start < end:
                page_title = text[start + 7 : end].strip()

        if page_title:
            # Clean common suffix
            cleaned = page_title.replace("- YouTube Music", "").strip()
            meta["title"] = cleaned
            meta["keywords"] = cleaned
    except Exception:
        # Ignore all network/parse errors
        pass

    return meta


# -----------------------------
# MOOD PREDICTION ENGINE
# -----------------------------


def predict_mood_for_song(song_title: str, extra_text: str = "") -> str:
    """
    Deterministic, cached rule-based mood classifier.
    The same song + metadata will always yield the same mood.
    """
    key = normalize_key(song_title or extra_text or "")
    if not key:
        key = "unknown"

    cached = MOOD_CACHE.get(key)
    if isinstance(cached, str) and cached in MOOD_CATEGORIES:
        return cached

    text = f"{song_title} {extra_text}".lower()

    rules = [
        ("Happy", ["happy", "joy", "smile", "sunny", "masti", "khushi"]),
        ("Sad", ["sad", "cry", "dard", "tuta", "broken", "alone", "bewafa"]),
        ("Calm", ["calm", "relax", "chill", "lofi", "sleep", "soothing"]),
        ("Romantic", ["love", "romantic", "dil", "heart", "ishq", "mohabbat"]),
        ("Energetic", ["rock", "remix", "dj", "mix", "power", "energy"]),
        ("Party", ["party", "club", "night", "dance", "dj"]),
        ("Emotional", ["emotional", "feel", "senti", "tears", "heartbreak"]),
        ("Devotional", ["bhajan", "aarti", "bhakti", "krishna", "ram", "allah", "om"]),
    ]

    for mood, keywords in rules:
        if any(k in text for k in keywords):
            chosen = mood
            break
    else:
        # Deterministic hash-based fallback across MOOD_CATEGORIES
        idx = abs(hash(key)) % len(MOOD_CATEGORIES)
        chosen = MOOD_CATEGORIES[idx]

    MOOD_CACHE[key] = chosen
    save_mood_cache(MOOD_CACHE)
    return chosen


def get_opposite_mood(mood: str) -> str:
    return OPPOSITE_MOOD.get(mood, "Calm")


# -----------------------------
# YOUTUBE MUSIC REDIRECTOR
# -----------------------------


def open_song_on_ytm(query: str) -> None:
    url = YTM_SEARCH_BASE + urllib.parse.quote_plus(query)
    webbrowser.open(url)


def open_playlist_on_ytm(mood: str) -> None:
    search = f"{mood} playlist"
    url = YTM_SEARCH_BASE + urllib.parse.quote_plus(search)
    webbrowser.open(url)


# -----------------------------
# GUI MANAGER & ANIMATION
# -----------------------------

root = tk.Tk()
root.title("ARVI — AI Mood Music Assistant")
root.geometry("520x420")
root.minsize(480, 380)
root.configure(bg=DEFAULT_STYLE[0])


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


ANIMATION_COLORS = [
    "#FFE066",
    "#B2F2BB",
    "#74C0FC",
    "#B197FC",
    "#FFC9DE",
    "#FF8787",
]

current_bg = hex_to_rgb(DEFAULT_STYLE[0])
target_bg = hex_to_rgb(ANIMATION_COLORS[1])
ANIM_SPEED = int(SETTINGS.get("animation_speed_ms", 80) or 80)


def pick_new_target_color() -> None:
    global target_bg
    # rotate through palette deterministically
    idx = ANIMATION_COLORS.index(rgb_to_hex(target_bg)) if rgb_to_hex(target_bg) in ANIMATION_COLORS else 0
    next_idx = (idx + 1) % len(ANIMATION_COLORS)
    target_bg = hex_to_rgb(ANIMATION_COLORS[next_idx])


def step_color():
    global current_bg, target_bg
    r, g, b = current_bg
    tr, tg, tb = target_bg

    def step(c, tc):
        if c < tc:
            return c + 1
        if c > tc:
            return c - 1
        return c

    nr, ng, nb = step(r, tr), step(g, tg), step(b, tb)
    current_bg = (nr, ng, nb)
    if current_bg == target_bg:
        pick_new_target_color()

    color_hex = rgb_to_hex(current_bg)
    apply_theme(color_hex)
    root.after(ANIM_SPEED, step_color)


def apply_theme(color: str) -> None:
    root.configure(bg=color)
    for widget in (title_label, input_label, result_label, footer_label):
        widget.configure(bg=color)


# -----------------------------
# GUI LAYOUT
# -----------------------------

title_label = tk.Label(
    root,
    text="🎧 ARVI — AI Mood Music",
    font=("Segoe UI", 16, "bold"),
    bg=root["bg"],
)
title_label.pack(pady=15)

input_label = tk.Label(root, text="Enter Song Name", font=("Segoe UI", 11), bg=root["bg"])
input_label.pack()

song_entry = tk.Entry(root, width=36, font=("Segoe UI", 12))
song_entry.pack(pady=8)


status_var = tk.StringVar(value="")


def set_status(msg: str) -> None:
    status_var.set(msg)


def clear_status_later(delay_ms: int = 1500) -> None:
    root.after(delay_ms, lambda: status_var.set(""))


def on_predict_clicked():
    song = song_entry.get().strip()
    if not song:
        messagebox.showerror("ARVI", "Please enter a song name.")
        return

    set_status("Processing song…")
    t = threading.Thread(target=process_song_workflow, args=(song,), daemon=True)
    t.start()


predict_button = tk.Button(
    root,
    text="Analyze Mood",
    font=("Segoe UI", 11, "bold"),
    command=on_predict_clicked,
    bg="#212529",
    fg="white",
    relief="raised",
    padx=10,
    pady=4,
)
predict_button.pack(pady=12)

result_label = tk.Label(
    root,
    text="",
    font=("Segoe UI", 12),
    width=40,
    height=4,
    relief="ridge",
    borderwidth=2,
    bg=root["bg"],
    justify="center",
    wraplength=360,
)
result_label.pack(pady=16)

footer_label = tk.Label(
    root,
    textvariable=status_var,
    font=("Segoe UI", 9),
    bg=root["bg"],
)
footer_label.pack(side="bottom", pady=6)


# -----------------------------
# DECISION POPUP (ANIMATED)
# -----------------------------

def show_decision_popup(song_query: str, display_title: str, mood: str):
    """
    Custom popup with a simple grow animation and YES/NO buttons.
    YES -> switch to opposite mood playlist
    NO  -> stay with this song
    """

    popup = tk.Toplevel(root)
    popup.title("ARVI Decision")
    popup.transient(root)
    popup.grab_set()

    # Start small and grow
    width, height = 360, 180
    for w in range(220, width + 1, 20):
        popup.geometry(f"{w}x{height}")
        popup.update_idletasks()
        popup.update()
        time.sleep(0.01)

    popup.configure(bg=root["bg"])

    msg = (
        f"This song feels {mood.upper()}.\n\n"
        "Do you want to switch to the opposite mood?"
    )
    lbl = tk.Label(popup, text=msg, font=("Segoe UI", 11), bg=root["bg"], wraplength=320, justify="center")
    lbl.pack(pady=15)

    btn_frame = tk.Frame(popup, bg=root["bg"])
    btn_frame.pack(pady=10)

    def on_yes():
        popup.destroy()
        opposite = get_opposite_mood(mood)
        open_playlist_on_ytm(opposite)
        set_status(f"Opening {opposite} playlist on YouTube Music…")
        clear_status_later()

    def on_no():
        popup.destroy()
        # Use exact requested song name for playback
        open_song_on_ytm(song_query)
        set_status("Opening your song on YouTube Music…")
        clear_status_later()

    yes_btn = tk.Button(btn_frame, text="YES", width=10, command=on_yes, bg="#228BE6", fg="white")
    no_btn = tk.Button(btn_frame, text="NO", width=10, command=on_no)

    yes_btn.grid(row=0, column=0, padx=8)
    no_btn.grid(row=0, column=1, padx=8)

    # Center popup over root
    root.update_idletasks()
    rx = root.winfo_x()
    ry = root.winfo_y()
    rw = root.winfo_width()
    rh = root.winfo_height()
    px = rx + (rw - width) // 2
    py = ry + (rh - height) // 2
    popup.geometry(f"+{px}+{py}")


# -----------------------------
# DECISION CONTROLLER WORKFLOW
# -----------------------------


def process_song_workflow(user_query: str) -> None:
    """
    Full song flow:
    - Try local fuzzy search
    - If no good match -> online search
    - Predict mood
    - Ask user about opposite mood
    """
    try:
        similarity_threshold = float(SETTINGS.get("similarity_threshold", 70) or 70)
    except Exception:
        similarity_threshold = 70.0

    # Step 1: Local database fuzzy search
    chosen_title = user_query
    chosen_artist = ""
    chosen_source = "input"
    cached_mood = ""

    local_result = find_best_local_match(user_query)
    if local_result is not None:
        row, score = local_result
        if score >= similarity_threshold:
            chosen_title = row.get("title") or user_query
            chosen_artist = row.get("artist") or ""
            chosen_source = "local"
            cached_mood = (row.get("mood") or "").strip()

    # Step 2: Online search fallback if no suitable local match
    online_meta = {}
    if chosen_source != "local":
        online_meta = fetch_online_metadata(user_query)
        chosen_title = online_meta.get("title") or user_query
        chosen_source = "online"

    # Step 3: Mood prediction (cached where possible)
    if cached_mood and cached_mood in MOOD_CATEGORIES:
        mood = cached_mood
    else:
        extra_text = ""
        if chosen_artist:
            extra_text = chosen_artist
        elif online_meta:
            extra_text = online_meta.get("keywords", "") or chosen_title
        mood = predict_mood_for_song(chosen_title, extra_text=extra_text)

    style_color, emoji = MOOD_STYLES.get(mood, DEFAULT_STYLE)

    def ui_update():
        # Update mood display and theme, then show popup
        apply_theme(style_color)
        result_label.config(
            text=f"{emoji}  {chosen_title}\nMood: {mood.upper()}  (source: {chosen_source})"
        )
        set_status("Mood detected. Awaiting your choice…")
        # Allow UI to repaint before popup
        root.after(200, lambda: show_decision_popup(user_query, chosen_title, mood))

    root.after(0, ui_update)


# Start background animation and main loop
step_color()
root.mainloop()