#!/usr/bin/env python3
import tkinter as tk
from tkinter import messagebox
import requests
import threading
import time
import os
from PIL import Image, ImageTk, ImageStat
from io import BytesIO
from datetime import datetime

# === CONFIG ===
MACHINE = [9080, 9081, 9082, 9083]
HOST = "10.128.0.4"
DEFAULT_HEADERS = {
    "Cache-Control": "no-cache",
    "User-Agent": "PostmanRuntime/7.51.0",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}
INTERVAL = 10               # default capture interval (seconds)
SAVE_DIR = "./snapshots"
MIN_IMAGE_BYTES = 10_000    # treat anything smaller as likely placeholder (adjustable)
STATUS_POLL_TIMEOUT = 10    # seconds to wait for videoReady
SNAPSHOT_RETRIES = 3
os.makedirs(SAVE_DIR, exist_ok=True)

# === Helper: create a session per machine ===
def make_session():
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    return s

def log(msg):
    print(f"[{datetime.now()}] {msg}")

# --- Network helpers that accept session and base_url ---
def post(session, base_url, endpoint, params=None, json_body=None, timeout=30):
    url = f"{base_url}/{endpoint}"
    try:
        r = session.post(url, params=params, json=json_body or {}, timeout=timeout)
        log(f"🔄 POST {url} → {r.status_code} {r.reason}; body_len={len(r.content)}; headers={dict(r.headers)}")
        return r
    except Exception as e:
        log(f"[POST] {url} failed: {e}")
        return None

def get(session, base_url, endpoint, params=None, timeout=30, stream=False):
    url = f"{base_url}/{endpoint}"
    try:
        r = session.get(url, params=params, timeout=timeout, stream=stream)
        log(f"🔍 GET {url} → {r.status_code} {r.reason}; headers={dict(r.headers)}")
        return r
    except Exception as e:
        log(f"[GET] {url} failed: {e}")
        return None

def is_black_image(pil_img, threshold=5):
    gray = pil_img.convert("L")
    stat = ImageStat.Stat(gray)
    return stat.mean[0] < threshold and stat.stddev[0] < threshold

def save_raw_and_decode(content_bytes, name_prefix, ext="png"):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = os.path.join(SAVE_DIR, f"{name_prefix}_{timestamp}_raw.bin")
    with open(raw_path, "wb") as f:
        f.write(content_bytes)
    log(f"🧪 Raw snapshot saved: {raw_path} ({len(content_bytes)} bytes)")

    try:
        img = Image.open(BytesIO(content_bytes))
        img.load()
        filename = f"{name_prefix}_{timestamp}.{ext}"
        path = os.path.join(SAVE_DIR, filename)
        img.save(path)
        log(f"✅ Image saved: {path}")
        return path, img
    except Exception as e:
        log(f"⚠️ PIL failed to decode image: {e}")
        return None, None

def ensure_connected_and_ready(session, base_url):
    r = post(session, base_url, "connect")
    if not r or r.status_code != 200:
        log("❌ connect failed")
        return False

    start = time.time()
    while time.time() - start < STATUS_POLL_TIMEOUT:
        r = get(session, base_url, "status", timeout=5)
        if not r or r.status_code != 200:
            time.sleep(0.5)
            continue
        try:
            status = r.json()
            log(f"📡 Status: {status}")
            if status.get("connected") and status.get("videoReady"):
                return True
        except Exception as e:
            log(f"⚠️ Failed to parse status JSON: {e}")
        time.sleep(0.5)
    log("⚠️ videoReady not true within timeout")
    post(session, base_url, "disconnect")
    return False

def wake_screen(session, base_url):
    post(session, base_url, "sendmouse", params={"xCoordinate": 5, "yCoordinate": 5})
    time.sleep(0.5)

def fetch_snapshot_with_retries(session, base_url, name_prefix):
    for attempt in range(1, SNAPSHOT_RETRIES + 1):
        log(f"Attempt {attempt} to fetch snapshot from {base_url}")
        r = get(session, base_url, "snapshot", timeout=30, stream=True)
        if not r or r.status_code != 200:
            log("Snapshot request failed or returned non-200")
            continue

        try:
            content = r.content
        except Exception as e:
            log(f"Failed to read snapshot content: {e}")
            continue

        log(f"📸 Snapshot response: {r.status_code}, Content-Type: {r.headers.get('Content-Type')}, Size: {len(content)} bytes, Content-Encoding: {r.headers.get('Content-Encoding')}")
        if len(content) < MIN_IMAGE_BYTES:
            log("⚠️ Snapshot too small; likely placeholder. Will retry after wake.")
            save_raw_and_decode(content, name_prefix, ext="bin")
            wake_screen(session, base_url)
            time.sleep(0.5)
            continue

        path, img = save_raw_and_decode(content, name_prefix, ext="png")
        if img is None:
            log("⚠️ Decoding failed; retrying")
            wake_screen(session, base_url)
            time.sleep(0.5)
            continue

        if is_black_image(img):
            log("⚠️ Detected black image; retrying")
            time.sleep(0.5)
            continue

        return path
    log(f"❌ All snapshot attempts failed or returned invalid images for {base_url}")
    return None

# === GUI APP ===
class KVMApp:
    def __init__(self, root):
        self.root = root
        self.root.title("KVM Snapshot Capture (multi-machine)")
        self.running = False
        self.stop_event = threading.Event()
        self.kvm_name = tk.StringVar(value="kvm")
        self.interval_var = tk.IntVar(value=INTERVAL)
        self.image_refs = {}

        frame = tk.Frame(root)
        frame.pack(padx=8, pady=8)

        tk.Label(frame, text="Base name (prefix):").grid(row=0, column=0, sticky="w")
        tk.Entry(frame, textvariable=self.kvm_name, width=20).grid(row=0, column=1, sticky="w")

        tk.Label(frame, text="Interval (s):").grid(row=0, column=2, sticky="w", padx=(10,0))
        tk.Entry(frame, textvariable=self.interval_var, width=6).grid(row=0, column=3, sticky="w")

        self.start_btn = tk.Button(frame, text="Start", command=self.start)
        self.start_btn.grid(row=1, column=0, pady=6)

        self.stop_btn = tk.Button(frame, text="Stop", command=self.stop, state=tk.DISABLED)
        self.stop_btn.grid(row=1, column=1, pady=6)

        self.snap_btn = tk.Button(frame, text="Manual Snapshot (all)", command=self.manual_snapshot)
        self.snap_btn.grid(row=1, column=2, pady=6, columnspan=2)

        self.status = tk.Label(root, text="Idle", anchor="w")
        self.status.pack(fill="x", padx=8)

        list_frame = tk.Frame(root)
        list_frame.pack(fill="both", expand=True, padx=8, pady=6)

        self.image_listbox = tk.Listbox(list_frame, width=60, height=12)
        self.image_listbox.pack(side="left", fill="y")
        self.image_listbox.bind("<<ListboxSelect>>", self.show_image)

        self.scrollbar = tk.Scrollbar(list_frame, command=self.image_listbox.yview)
        self.image_listbox.config(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="left", fill="y")

        self.canvas = tk.Canvas(root, width=640, height=480, bg="gray90")
        self.canvas.pack(padx=8, pady=6)

    def set_status(self, text):
        log(text)
        self.status.config(text=text)

    def start(self):
        name = self.kvm_name.get().strip()
        if not name:
            messagebox.showerror("Missing base name", "Please enter a base name before starting.")
            return
        self.running = True
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.capture_loop_all, args=(name,), daemon=True)
        self.thread.start()
        self.set_status("🟢 Running (capturing from all machines)")
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)

    def stop(self):
        self.stop_event.set()
        if hasattr(self, "thread"):
            self.thread.join(timeout=2)
        self.running = False
        self.set_status("🛑 Stopped")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def manual_snapshot(self):
        name = self.kvm_name.get().strip()
        if not name:
            messagebox.showerror("Missing base name", "Please enter a base name.")
            return
        threading.Thread(target=self._single_cycle_all, args=(name,), daemon=True).start()

    def capture_loop_all(self, base_name):
        while not self.stop_event.is_set():
            self._single_cycle_all(base_name)
            interval = max(1, int(self.interval_var.get()))
            for _ in range(interval):
                if self.stop_event.is_set():
                    break
                time.sleep(1)

    def _single_cycle_all(self, base_name):
        # Iterate over all machine ports and capture from each
        for port in MACHINE:
            if self.stop_event.is_set():
                break
            base_url = f"http://{HOST}:{port}/kx"
            name_prefix = f"{base_name}_{port}"
            self.set_status(f"Connecting to {port}...")
            session = make_session()
            try:
                if not ensure_connected_and_ready(session, base_url):
                    self.set_status(f"Port {port}: connect or video not ready")
                    continue

                self.set_status(f"Port {port}: waking screen...")
                wake_screen(session, base_url)

                self.set_status(f"Port {port}: capturing snapshot...")
                path = fetch_snapshot_with_retries(session, base_url, name_prefix)
                if path:
                    self.image_listbox.insert(tk.END, os.path.basename(path))
                    self.set_status(f"Saved: {os.path.basename(path)}")
                else:
                    self.set_status(f"Port {port}: snapshot failed")

            finally:
                post(session, base_url, "disconnect")
                self.set_status(f"Port {port}: disconnected")

    def show_image(self, event):
        selection = self.image_listbox.curselection()
        if not selection:
            return
        filename = self.image_listbox.get(selection[0])
        filepath = os.path.join(SAVE_DIR, filename)
        try:
            img = Image.open(filepath)
            canvas_w = int(self.canvas["width"])
            canvas_h = int(self.canvas["height"])
            img.thumbnail((canvas_w, canvas_h))
            photo = ImageTk.PhotoImage(img)
            self.image_refs["preview"] = photo
            self.canvas.delete("all")
            self.canvas.create_image(canvas_w//2, canvas_h//2, image=photo)
        except Exception as e:
            messagebox.showerror("Error", f"Could not open image: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = KVMApp(root)
    root.mainloop()
