from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import getpass
import hashlib
import json
import math
import os
import platform
from pathlib import Path
import queue
import random
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Callable


DEFAULT_CONFIG = {
    "window_title_keyword": "洛克王国",
    "activation_url": "",
    "license": {
        "enabled": False,
        "activation_url": "",
        "product": "RockShinyAuto",
        "state_file": "license_state.json",
        "request_timeout_seconds": 8.0,
        "recheck_interval_seconds": 300.0,
        "allow_offline_seconds": 0.0,
    },
    "audio_template": "shiny_prompt.m4a",
    "audio_sample_rate": 48000,
    "audio_threshold": 0.58,
    "audio_window_seconds": 7.0,
    "audio_check_interval_seconds": 0.20,
    "cycle_limit": 0,
    "resize_windows": True,
    "target_client_size": [1280, 800],
    "focus_titlebar_click": False,
    "focus_client_click": False,
    "input": {
        "backend": "interception",
        "keyboard_device": 0,
        "mouse_device": 10,
    },
    "randomization": {
        "enabled": True,
        "wait_jitter_ratio": 0.18,
        "wait_jitter_max_seconds": 0.35,
        "idle_actions": {
            "enabled": True,
            "space_chance": 0.10,
            "space_hold": 0.060,
            "min_wait_seconds": 0.70,
            "labels": ["After leave click", "Between cycles"],
        },
    },
    "delays": {
        "after_focus": 0.80,
        "after_focus_click": 0.25,
        "before_guest_f": 1.20,
        "guest_f_attempts": 1,
        "guest_f_hold": 0.100,
        "guest_f_retry_wait": 0.25,
        "after_key": 0.18,
        "after_open_menu": 0.80,
        "after_request": 0.30,
        "before_host_f": 1.20,
        "host_f_attempts": 1,
        "host_f_hold": 0.060,
        "host_f_retry_wait": 0.25,
        "after_host_f": 0.35,
        "after_accept": 4.00,
        "listen_after_join": 5.50,
        "after_open_leave_menu": 0.45,
        "after_leave_click": 2.40,
        "between_cycles": 0.35,
    },
    "coords": {
        "focus_client": [0.50, 0.50],
        "guest_request_access": [0.903, 0.943],
        "guest_leave_world": [0.447, 0.232],
    },
}

PACKAGED_LICENSE_CONFIG = {
    "enabled": True,
    "activation_url": "",
    "product": "RockShinyAuto",
    "state_file": "license_state.json",
    "request_timeout_seconds": 8.0,
    "recheck_interval_seconds": 300.0,
    "allow_offline_seconds": 0.0,
}


def is_packaged_app() -> bool:
    return bool(getattr(sys, "frozen", False))


VK = {
    "F": 0x46,
    "U": 0x55,
    "SPACE": 0x20,
    "F8": 0x77,
    "F9": 0x78,
    "F10": 0x79,
    "ESC": 0x1B,
}

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_MOVE = 0x0001
SW_RESTORE = 9
SW_SHOW = 5
ASFW_ANY = -1
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_SHOWWINDOW = 0x0040
GWL_STYLE = -16
GWL_EXSTYLE = -20
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WH_KEYBOARD_LL = 13
HC_ACTION = 0
HOTKEY_PAUSE = 1001
HOTKEY_RESUME = 1002
HOTKEY_END = 1003
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

HMODULE = getattr(wintypes, "HMODULE", wintypes.HANDLE)
kernel32.GetModuleHandleW.restype = HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
user32.SetWindowsHookExW.restype = wintypes.HANDLE
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, HMODULE, wintypes.DWORD]
user32.CallNextHookEx.restype = wintypes.LPARAM
user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]

try:
    user32.SetProcessDPIAware()
except Exception:
    pass


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


LOW_LEVEL_KEYBOARD_PROC = ctypes.WINFUNCTYPE(
    wintypes.LPARAM,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


@dataclass(frozen=True)
class GameWindow:
    hwnd: int
    title: str
    rect: tuple[int, int, int, int]
    client_rect: tuple[int, int, int, int]

    @property
    def width(self) -> int:
        return self.client_rect[2] - self.client_rect[0]

    @property
    def height(self) -> int:
        return self.client_rect[3] - self.client_rect[1]


def log(message: str) -> None:
    stamp = time.strftime("%H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def public_default_config() -> dict:
    data = json.loads(json.dumps(DEFAULT_CONFIG, ensure_ascii=False))
    data.pop("activation_url", None)
    data.pop("license", None)
    return data


def load_config(path: Path) -> dict:
    if not path.exists():
        default_config = public_default_config() if is_packaged_app() else DEFAULT_CONFIG
        path.write_text(json.dumps(default_config, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"Created default config: {path}")
    with path.open("r", encoding="utf-8") as fh:
        loaded = json.load(fh)
    return deep_merge(DEFAULT_CONFIG, loaded)


def deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def effective_license_config(config: dict) -> dict:
    if is_packaged_app():
        return deep_merge(DEFAULT_CONFIG["license"], PACKAGED_LICENSE_CONFIG)
    license_config = config.get("license", {})
    if not isinstance(license_config, dict):
        license_config = {}
    return deep_merge(DEFAULT_CONFIG["license"], license_config)


_active_input_config = dict(DEFAULT_CONFIG["input"])
_interception_module = None
_interception_devices: tuple[int | None, int | None] | None = None


def configure_input(config: dict) -> None:
    global _active_input_config
    input_config = config.get("input", {})
    if not isinstance(input_config, dict):
        input_config = {}
    _active_input_config = deep_merge(DEFAULT_CONFIG["input"], input_config)


def input_backend() -> str:
    return str(_active_input_config.get("backend") or "win32").strip().lower()


def get_interception():
    global _interception_module, _interception_devices
    if _interception_module is None:
        try:
            import interception  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "Interception input backend is selected, but interception-python is not available. "
                "Run: python -m pip install -r requirements.txt"
            ) from exc
        _interception_module = interception

    keyboard = int(_active_input_config.get("keyboard_device", 0))
    mouse = int(_active_input_config.get("mouse_device", 10))
    devices = (keyboard, mouse)
    if _interception_devices != devices:
        try:
            _interception_module.set_devices(keyboard=keyboard, mouse=mouse)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to select Interception devices keyboard={keyboard}, mouse={mouse}. "
                "Run interception_input_tester.py and update config.json input devices."
            ) from exc
        _interception_devices = devices
    return _interception_module


class LicenseError(RuntimeError):
    pass


def utc_now() -> float:
    return time.time()


def read_json_file(path: Path, default: dict | None = None) -> dict:
    if not path.exists():
        return dict(default or {})
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(default or {})


def write_json_file(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_windows_machine_guid() -> str:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
    except Exception:
        return ""


def machine_fingerprint() -> str:
    parts = [
        "RockShinyAuto",
        platform.node(),
        platform.machine(),
        getpass.getuser(),
        get_windows_machine_guid(),
        str(uuid.getnode()),
    ]
    raw = "|".join(part for part in parts if part)
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def post_json(url: str, payload: dict, timeout: float) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LicenseError(f"License server HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LicenseError(f"Cannot reach license server: {exc}") from exc
    except TimeoutError as exc:
        raise LicenseError("License server request timed out.") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LicenseError(f"License server returned invalid JSON: {text[:200]}") from exc
    if not isinstance(data, dict):
        raise LicenseError("License server returned an invalid response.")
    return data


class LicenseGuard:
    def __init__(self, config: dict, config_path: Path, activation_code: str | None = None) -> None:
        self.config = effective_license_config(config)
        if is_packaged_app():
            self.activation_url = str(self.config.get("activation_url") or PACKAGED_LICENSE_CONFIG["activation_url"]).rstrip("/")
        else:
            self.activation_url = str(self.config.get("activation_url") or config.get("activation_url") or "").rstrip("/")
        self.product = str(self.config.get("product") or "RockShinyAuto")
        self.timeout = float(self.config.get("request_timeout_seconds", 8.0))
        self.recheck_interval = max(30.0, float(self.config.get("recheck_interval_seconds", 300.0)))
        self.allow_offline_seconds = max(0.0, float(self.config.get("allow_offline_seconds", 0.0)))
        self.machine_id = machine_fingerprint()
        self.state_path = self._resolve_state_path(config_path)
        self.activation_code = activation_code
        self._state = read_json_file(self.state_path)
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_ok = float(self._state.get("last_ok", 0.0) or 0.0)
        self._error: str | None = None

    @staticmethod
    def enabled(config: dict) -> bool:
        if is_packaged_app():
            return True
        license_config = config.get("license", {})
        return bool(isinstance(license_config, dict) and license_config.get("enabled", False))

    def _resolve_state_path(self, config_path: Path) -> Path:
        state_file = Path(str(self.config.get("state_file") or "license_state.json"))
        if state_file.is_absolute():
            return state_file
        return config_path.parent / state_file

    def _endpoint(self, name: str) -> str:
        if not self.activation_url:
            raise LicenseError("License server URL is not configured.")
        return f"{self.activation_url}/{name.lstrip('/')}"

    def _current_code(self) -> str:
        code = self.activation_code or str(self._state.get("activation_code") or "").strip()
        if code:
            return code
        entered = input("请输入激活码 / Enter activation code: ").strip()
        if not entered:
            raise LicenseError("Activation code is required.")
        self.activation_code = entered
        return entered

    def _base_payload(self, code: str) -> dict:
        return {
            "code": code,
            "machine_id": self.machine_id,
            "product": self.product,
            "client_version": "1",
        }

    def activate(self, code: str) -> None:
        data = post_json(self._endpoint("activate"), self._base_payload(code), self.timeout)
        if not data.get("ok"):
            raise LicenseError(str(data.get("message") or "Activation failed."))
        self._save_success(code, data)
        log(f"Activation OK: {data.get('message', 'licensed')}")

    def validate(self, interactive: bool = False) -> None:
        code = self._current_code()
        if not self._state.get("activation_code") or code != self._state.get("activation_code"):
            self.activate(code)
            return
        payload = self._base_payload(code)
        payload["token"] = self._state.get("token")
        try:
            data = post_json(self._endpoint("validate"), payload, self.timeout)
        except LicenseError:
            if self._can_use_offline():
                log("Warning: license server unavailable; using recent successful license cache.")
                return
            if interactive:
                raise
            raise

        if not data.get("ok"):
            raise LicenseError(str(data.get("message") or "License rejected."))
        self._save_success(code, data)

    def _can_use_offline(self) -> bool:
        if self.allow_offline_seconds <= 0 or self._last_ok <= 0:
            return False
        return utc_now() - self._last_ok <= self.allow_offline_seconds

    def _save_success(self, code: str, data: dict) -> None:
        now = utc_now()
        self._last_ok = now
        self._error = None
        self._state = {
            "activation_code": code,
            "machine_id": self.machine_id,
            "product": self.product,
            "token": data.get("token", ""),
            "message": data.get("message", ""),
            "last_ok": now,
            "last_ok_text": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
        }
        write_json_file(self.state_path, self._state)

    def start_background_checks(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="license-guard", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while self._running:
            time.sleep(self.recheck_interval)
            if not self._running:
                return
            try:
                self.validate(interactive=False)
            except Exception as exc:
                with self._lock:
                    self._error = str(exc)
                return

    def close(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def raise_if_blocked(self) -> None:
        with self._lock:
            error = self._error
        if error:
            raise LicenseError(f"License check failed: {error}")

    def status_text(self) -> str:
        code = str(self._state.get("activation_code") or "")
        masked = code[:4] + "..." + code[-4:] if len(code) > 8 else code or "(none)"
        last_ok = str(self._state.get("last_ok_text") or "(never)")
        return (
            f"license_enabled=True\n"
            f"activation_url={self.activation_url or '(empty)'}\n"
            f"product={self.product}\n"
            f"machine_id={self.machine_id}\n"
            f"state_file={self.state_path}\n"
            f"code={masked}\n"
            f"last_ok={last_ok}"
        )


def enum_game_windows(title_keyword: str) -> list[GameWindow]:
    windows: list[GameWindow] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value
        if title_keyword not in title:
            return True
        if user32.IsIconic(hwnd):
            return True
        rect = RECT()
        client = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        if not user32.GetClientRect(hwnd, ctypes.byref(client)):
            return True
        if client.right - client.left < 300 or client.bottom - client.top < 300:
            return True
        windows.append(
            GameWindow(
                hwnd=hwnd,
                title=title,
                rect=(rect.left, rect.top, rect.right, rect.bottom),
                client_rect=(client.left, client.top, client.right, client.bottom),
            )
        )
        return True

    user32.EnumWindows(enum_proc, 0)
    windows.sort(key=lambda item: (item.rect[1], item.rect[0], item.hwnd))
    return windows


def read_game_window(hwnd: int) -> GameWindow:
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    rect = RECT()
    client = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError(f"GetWindowRect failed for hwnd={hwnd}")
    if not user32.GetClientRect(hwnd, ctypes.byref(client)):
        raise RuntimeError(f"GetClientRect failed for hwnd={hwnd}")
    return GameWindow(
        hwnd=hwnd,
        title=buffer.value,
        rect=(rect.left, rect.top, rect.right, rect.bottom),
        client_rect=(client.left, client.top, client.right, client.bottom),
    )


def get_window_long(hwnd: int, index: int) -> int:
    try:
        func = user32.GetWindowLongPtrW
    except AttributeError:
        func = user32.GetWindowLongW
    return int(func(hwnd, index))


def resize_window_client(win: GameWindow, width: int, height: int) -> GameWindow:
    current = read_game_window(win.hwnd)
    if current.width == int(width) and current.height == int(height):
        log(f"Window hwnd={win.hwnd} already has client {current.width}x{current.height}; resize skipped.")
        return current

    style = get_window_long(win.hwnd, GWL_STYLE)
    exstyle = get_window_long(win.hwnd, GWL_EXSTYLE)
    desired = RECT(0, 0, int(width), int(height))
    if not user32.AdjustWindowRectEx(ctypes.byref(desired), style, False, exstyle):
        raise RuntimeError(f"AdjustWindowRectEx failed for hwnd={win.hwnd}")
    outer_w = desired.right - desired.left
    outer_h = desired.bottom - desired.top
    x, y = win.rect[0], win.rect[1]
    user32.ShowWindow(win.hwnd, SW_RESTORE)
    if not user32.SetWindowPos(win.hwnd, 0, x, y, outer_w, outer_h, SWP_SHOWWINDOW):
        error = kernel32.GetLastError()
        log(f"Warning: SetWindowPos failed for hwnd={win.hwnd}, error={error}; continuing with current size.")
        return read_game_window(win.hwnd)
    time.sleep(0.20)
    resized = read_game_window(win.hwnd)
    log(
        f"Resized hwnd={win.hwnd} to client {resized.width}x{resized.height} "
        f"(target {width}x{height})"
    )
    return resized


def choose_windows(windows: list[GameWindow], host_hwnd: int | None, guest_hwnd: int | None) -> tuple[GameWindow, GameWindow]:
    by_hwnd = {win.hwnd: win for win in windows}
    if host_hwnd and guest_hwnd:
        try:
            return by_hwnd[host_hwnd], by_hwnd[guest_hwnd]
        except KeyError as exc:
            raise SystemExit(f"Configured window handle is not available: {exc}") from exc

    if len(windows) < 2:
        raise SystemExit("Need at least two visible game windows. Open both 1P and 2P clients first.")

    print("\nDetected game windows:")
    for idx, win in enumerate(windows, 1):
        print(f"  {idx}. hwnd={win.hwnd} title={win.title!r} rect={win.rect} client={win.width}x{win.height}")

    if len(windows) == 2:
        return visual_choose_two_windows(windows)

    print("\nMore than two matching windows were found.")
    print("The script will bring each candidate to the front; label the ones you want to use.")
    return visual_label_windows(windows)


def read_index(prompt: str, maximum: int, disallow: int | None = None) -> int:
    while True:
        raw = input(prompt).strip()
        if raw.isdigit():
            value = int(raw)
            if 1 <= value <= maximum and value != disallow:
                return value
        print("Invalid selection.")


def visual_choose_two_windows(windows: list[GameWindow]) -> tuple[GameWindow, GameWindow]:
    print("\nVisual selection:")
    print("I will bring window A to the front. Look at the game account on screen, then choose what it is.")
    focus_window(windows[0].hwnd, 0.50)
    answer = read_choice("\nThe focused window is: [1] 1P host  [2] 2P guest  [r] show other first: ", {"1", "2", "r"})
    if answer == "r":
        focus_window(windows[1].hwnd, 0.50)
        answer = read_choice("Now the focused window is: [1] 1P host  [2] 2P guest: ", {"1", "2"})
        return (windows[1], windows[0]) if answer == "1" else (windows[0], windows[1])
    return (windows[0], windows[1]) if answer == "1" else (windows[1], windows[0])


def visual_label_windows(windows: list[GameWindow]) -> tuple[GameWindow, GameWindow]:
    host: GameWindow | None = None
    guest: GameWindow | None = None
    for idx, win in enumerate(windows, 1):
        focus_window(win.hwnd, 0.50)
        while True:
            answer = read_choice(
                f"\nFocused candidate {idx}/{len(windows)}. Label it: [1] 1P host  [2] 2P guest  [s] skip  [r] refocus: ",
                {"1", "2", "s", "r"},
            )
            if answer == "r":
                focus_window(win.hwnd, 0.50)
                continue
            if answer == "1":
                host = win
            elif answer == "2":
                guest = win
            break
        if host and guest:
            return host, guest
    raise SystemExit("Did not select both 1P and 2P windows.")


def read_choice(prompt: str, choices: set[str]) -> str:
    while True:
        answer = input(prompt).strip().lower()
        if answer in choices:
            return answer
        print("Invalid selection.")


def focus_window(hwnd: int, after_focus: float) -> None:
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    for attempt in range(5):
        force_foreground_window(hwnd)
        time.sleep(after_focus / 2)
        if user32.GetForegroundWindow() == hwnd:
            break
    time.sleep(after_focus)


def force_foreground_window(hwnd: int) -> None:
    foreground = user32.GetForegroundWindow()
    current_thread = kernel32.GetCurrentThreadId()
    foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    attached: list[int] = []

    for thread_id in {foreground_thread, target_thread}:
        if thread_id and thread_id != current_thread:
            if user32.AttachThreadInput(current_thread, thread_id, True):
                attached.append(thread_id)

    try:
        try:
            user32.AllowSetForegroundWindow(ASFW_ANY)
        except Exception:
            pass
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.ShowWindow(hwnd, SW_SHOW)
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
        user32.BringWindowToTop(hwnd)
        user32.SetActiveWindow(hwnd)
        user32.SetFocus(hwnd)
        user32.SetForegroundWindow(hwnd)
        try:
            user32.SwitchToThisWindow(hwnd, True)
        except Exception:
            pass
    finally:
        for thread_id in attached:
            user32.AttachThreadInput(current_thread, thread_id, False)


def window_title(hwnd: int) -> str:
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def click_title_bar(hwnd: int, strict: bool = True) -> bool:
    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        if strict:
            raise RuntimeError(f"GetWindowRect failed for hwnd={hwnd}")
        return False
    x = rect.left + min(180, max(40, rect.right - rect.left - 40))
    y = rect.top + 15
    return click_screen(x, y, strict=strict)


def client_to_screen(hwnd: int, x: int, y: int) -> tuple[int, int]:
    point = POINT(x, y)
    if not user32.ClientToScreen(hwnd, ctypes.byref(point)):
        raise RuntimeError("ClientToScreen failed")
    return point.x, point.y


def key_input(vk: int, is_up: bool) -> INPUT:
    scan = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if is_up else 0)
    return INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(ki=KEYBDINPUT(0, scan, flags, 0, None)))


INTERCEPTION_KEY_NAMES = {
    VK["F"]: "f",
    VK["U"]: "u",
    VK["ESC"]: "esc",
    VK["SPACE"]: "space",
}


def release_key(vk: int) -> None:
    if input_backend() == "interception":
        key_name = INTERCEPTION_KEY_NAMES.get(vk)
        if key_name:
            try:
                get_interception().key_up(key_name)
            except Exception:
                pass
            return
    up = key_input(vk, True)
    user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))


def release_common_keys() -> None:
    for vk in (VK["F"], VK["U"], VK["ESC"]):
        release_key(vk)


def send_key(vk: int, hold_seconds: float = 0.060) -> None:
    if input_backend() == "interception":
        key_name = INTERCEPTION_KEY_NAMES.get(vk)
        if not key_name:
            raise RuntimeError(f"Interception key mapping is missing for vk={vk}.")
        interception = get_interception()
        try:
            interception.key_up(key_name)
            time.sleep(0.02)
            interception.key_down(key_name)
            time.sleep(hold_seconds)
            interception.key_up(key_name)
        except Exception as exc:
            raise RuntimeError(
                "Interception key input failed. Confirm the driver is installed, Windows was rebooted, "
                "and config.json uses the tested keyboard_device."
            ) from exc
        return

    release_key(vk)
    time.sleep(0.02)
    down = key_input(vk, False)
    up = key_input(vk, True)
    sent = user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
    if sent != 1:
        raise RuntimeError("SendInput key down failed. Try running PowerShell or VS Code as administrator.")
    time.sleep(hold_seconds)
    sent = user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
    if sent != 1:
        raise RuntimeError("SendInput key up failed. Try running PowerShell or VS Code as administrator.")


def click_screen(x: int, y: int, strict: bool = True) -> bool:
    if input_backend() == "interception":
        try:
            get_interception().click(int(x), int(y), button="left", clicks=1, delay=0.10)
            return True
        except Exception as exc:
            message = (
                "Interception mouse input failed. Confirm the driver is installed, Windows was rebooted, "
                "and config.json uses the tested mouse_device."
            )
            if strict:
                raise RuntimeError(message) from exc
            log(f"Warning: {message} ({exc})")
            return False

    if not user32.SetCursorPos(int(x), int(y)):
        message = f"SetCursorPos failed at ({int(x)}, {int(y)}), error={kernel32.GetLastError()}"
        if strict:
            raise RuntimeError(message)
        log(f"Warning: {message}; click skipped.")
        return False
    down = INPUT(type=INPUT_MOUSE, union=INPUT_UNION(mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, None)))
    up = INPUT(type=INPUT_MOUSE, union=INPUT_UNION(mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, None)))
    inputs = (INPUT * 2)(down, up)
    sent = user32.SendInput(2, inputs, ctypes.sizeof(INPUT))
    if sent != 2:
        message = "SendInput mouse click failed. Try running PowerShell or VS Code as administrator."
        if strict:
            raise RuntimeError(message)
        log(f"Warning: {message}")
        return False
    return True


def click_relative(win: GameWindow, rel_xy: list[float], strict: bool = True) -> bool:
    x = int(win.width * float(rel_xy[0]))
    y = int(win.height * float(rel_xy[1]))
    sx, sy = client_to_screen(win.hwnd, x, y)
    return click_screen(sx, sy, strict=strict)


def is_pressed(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


class Hotkeys:
    def __init__(self) -> None:
        self.paused = False
        self.stop = False
        self._last: dict[int, float] = {}
        self._last_action: dict[str, float] = {}
        self._down_state: dict[int, bool] = {}
        self._lock = threading.Lock()
        self._running = True
        self._message_thread: threading.Thread | None = None
        self._poll_thread: threading.Thread | None = None
        self._message_thread_id = 0
        self._ready = threading.Event()
        self._hook_handle = None
        self._hook_proc = None
        self._hotkeys = {
            HOTKEY_PAUSE: ("F8", VK["F8"], "pause"),
            HOTKEY_RESUME: ("F9", VK["F9"], "resume"),
            HOTKEY_END: ("F10", VK["F10"], "end"),
        }
        self._vk_to_action = {vk: (name, action) for name, vk, action in self._hotkeys.values()}
        self._down_state = {vk: is_pressed(vk) for _name, vk, _action in self._hotkeys.values()}
        self.start_global_hotkeys()

    def close(self) -> None:
        self._running = False
        if self._message_thread_id:
            user32.PostThreadMessageW(self._message_thread_id, WM_QUIT, 0, 0)
        if self._message_thread is not None:
            self._message_thread.join(timeout=1.0)
            self._message_thread = None
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=1.0)
            self._poll_thread = None

    def start_global_hotkeys(self) -> None:
        self._poll_thread = threading.Thread(target=self._poll_loop, name="hotkey-polling", daemon=True)
        self._message_thread = threading.Thread(target=self._global_hotkey_loop, name="global-hotkeys", daemon=True)
        self._poll_thread.start()
        self._message_thread.start()
        if self._ready.wait(timeout=1.5):
            log("Hotkeys ready: F8 pause, F9 resume, F10 end. (global + hook + polling)")
        else:
            log("Hotkeys ready: F8 pause, F9 resume, F10 end. (polling thread active)")

    def _global_hotkey_loop(self) -> None:
        self._message_thread_id = kernel32.GetCurrentThreadId()
        registered: list[int] = []
        for hotkey_id, (name, vk, _action) in self._hotkeys.items():
            if user32.RegisterHotKey(None, hotkey_id, 0, vk):
                registered.append(hotkey_id)
                log(f"Registered global hotkey {name}.")
            else:
                log(f"Warning: failed to register {name}; hook/polling will still check it.")
        self._install_keyboard_hook()
        self._ready.set()
        msg = MSG()
        try:
            while self._running:
                result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result == 0:
                    break
                if result == -1:
                    log("Warning: global hotkey message loop failed; hook/polling remain active.")
                    break
                if msg.message == WM_HOTKEY:
                    item = self._hotkeys.get(int(msg.wParam))
                    if item:
                        name, _vk, action = item
                        self.handle_action(action, source=f"global {name}")
        finally:
            if self._hook_handle:
                user32.UnhookWindowsHookEx(self._hook_handle)
                self._hook_handle = None
            for hotkey_id in registered:
                user32.UnregisterHotKey(None, hotkey_id)

    def _install_keyboard_hook(self) -> None:
        @LOW_LEVEL_KEYBOARD_PROC
        def hook_proc(n_code: int, w_param: int, l_param: int) -> int:
            if n_code == HC_ACTION and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                item = self._vk_to_action.get(int(info.vkCode))
                if item:
                    name, action = item
                    self.handle_action(action, source=f"hook {name}")
            return user32.CallNextHookEx(self._hook_handle, n_code, w_param, l_param)

        self._hook_proc = hook_proc
        self._hook_handle = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            ctypes.cast(self._hook_proc, ctypes.c_void_p),
            kernel32.GetModuleHandleW(None),
            0,
        )
        if self._hook_handle:
            log("Low-level keyboard hook installed for F8/F9/F10.")
        else:
            log(f"Warning: keyboard hook install failed, error={kernel32.GetLastError()}; polling remains active.")

    def _poll_loop(self) -> None:
        while self._running:
            self.tick()
            time.sleep(0.025)

    def tick(self) -> None:
        now = time.monotonic()
        actions = (
            ("F8", "pause"),
            ("F9", "resume"),
            ("F10", "end"),
        )
        for name, action in actions:
            vk = VK[name]
            pressed = is_pressed(vk)
            was_pressed = self._down_state.get(vk, False)
            self._down_state[vk] = pressed
            if not pressed or was_pressed:
                continue
            if now - self._last.get(vk, 0.0) < 0.60:
                continue
            self._last[vk] = now
            self.handle_action(action, source=f"polling {name}")

    def handle_action(self, action: str, source: str) -> None:
        now = time.monotonic()
        with self._lock:
            if now - self._last_action.get(action, 0.0) < 0.35:
                return
            self._last_action[action] = now
            if action == "pause":
                self.paused = True
                log(f"Paused. ({source})")
            elif action == "resume":
                self.paused = False
                log(f"Resumed. ({source})")
            elif action == "end":
                self.stop = True
                self.paused = False
                log(f"End requested. ({source})")

    def sleep(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.tick()
            if self.stop:
                return
            while self.paused and not self.stop:
                self.tick()
                time.sleep(0.05)
            time.sleep(0.03)


class ShinyDetected(RuntimeError):
    pass


class AudioDetector:
    def __init__(
        self,
        template_path: Path,
        sample_rate: int,
        threshold: float,
        window_seconds: float,
        check_interval: float,
    ) -> None:
        self.template_path = template_path
        self.requested_sample_rate = int(sample_rate)
        self.threshold = float(threshold)
        self.window_seconds = float(window_seconds)
        self.check_interval = float(check_interval)
        self._sc = None
        self._np = None
        self._template = None
        self._sample_rate = 0
        self._speaker = None
        self._mic = None
        self._queue: queue.Queue = queue.Queue()
        self._chunks: list = []
        self._thread: threading.Thread | None = None
        self._monitor_thread: threading.Thread | None = None
        self._running = False
        self._record_error: Exception | None = None
        self._matched_event = threading.Event()
        self.last_score = 0.0

    @property
    def enabled(self) -> bool:
        return self._template is not None

    @property
    def matched(self) -> bool:
        return self._matched_event.is_set()

    def prepare(self) -> None:
        if not self.template_path.exists():
            raise FileNotFoundError(f"Audio template not found: {self.template_path}")
        import numpy as np  # type: ignore
        import soundcard as sc  # type: ignore

        self._np = np
        self._sc = sc
        self._sample_rate = self.requested_sample_rate
        self._speaker = sc.default_speaker()
        self._mic = sc.get_microphone(id=str(self._speaker.name), include_loopback=True)
        template = decode_audio_mono(self.template_path, self._sample_rate)
        template = np.asarray(template, dtype=np.float32)
        template = trim_silence(template)
        if template.size < int(0.20 * self._sample_rate):
            raise RuntimeError("Audio template is too short after silence trimming.")
        template = template - float(template.mean())
        norm = float(np.linalg.norm(template))
        if norm <= 1e-6:
            raise RuntimeError("Audio template has no usable signal.")
        self._template = template / norm
        log(
            "Audio detector ready: "
            f"{self.template_path.name}, {self._sample_rate} Hz, "
            f"{template.size / self._sample_rate:.2f}s, speaker={self._speaker.name}"
        )

    def start(self) -> None:
        if self._sc is None or self._np is None:
            self.prepare()
        self._chunks.clear()
        self._record_error = None
        self._matched_event.clear()
        self.last_score = 0.0
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._running = True
        self._thread = threading.Thread(target=self._record_loop, name="audio-loopback", daemon=True)
        self._thread.start()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, name="audio-monitor", daemon=True)
        self._monitor_thread.start()
        time.sleep(0.10)
        if self._record_error:
            raise RuntimeError(f"Audio loopback failed: {self._record_error}") from self._record_error

    def _record_loop(self) -> None:
        assert self._np is not None
        assert self._mic is not None
        frames = max(512, int(0.10 * self._sample_rate))
        try:
            with self._mic.recorder(samplerate=self._sample_rate, channels=2, blocksize=frames) as recorder:
                while self._running:
                    data = recorder.record(numframes=frames)
                    if data.ndim == 1:
                        mono = data
                    else:
                        mono = data.mean(axis=1)
                    self._queue.put(mono.astype("float32", copy=False).copy())
        except Exception as exc:
            self._record_error = exc

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._monitor_thread is not None:
            self._monitor_thread.join(timeout=1.0)
            self._monitor_thread = None

    def _monitor_loop(self) -> None:
        assert self._np is not None
        max_samples = int(self.window_seconds * self._sample_rate)
        next_check = time.monotonic()
        while self._running:
            if self._record_error is not None:
                return
            self._drain_audio_queue(max_samples)
            now = time.monotonic()
            if now >= next_check:
                self._check_current_audio()
                next_check = now + self.check_interval
            time.sleep(0.02)

    def _drain_audio_queue(self, max_samples: int) -> None:
        assert self._np is not None
        drained = False
        while True:
            try:
                self._chunks.append(self._queue.get_nowait())
                drained = True
            except queue.Empty:
                break
        if drained:
            merged = self._np.concatenate(self._chunks)
            if merged.size > max_samples:
                merged = merged[-max_samples:]
                self._chunks = [merged]

    def _check_current_audio(self) -> None:
        if self._matched_event.is_set() or not self._chunks:
            return
        assert self._np is not None
        merged = self._np.concatenate(self._chunks)
        self.last_score = normalized_template_score(merged, self._template, self._np)
        if self.last_score >= self.threshold:
            self._matched_event.set()
            log(f"Global shiny prompt detected: score={self.last_score:.3f}, threshold={self.threshold:.3f}")

    def listen_until_match(self, seconds: float, hotkeys: Hotkeys) -> bool:
        if not self.enabled:
            return False
        started = time.monotonic()
        while time.monotonic() - started < seconds:
            hotkeys.tick()
            if hotkeys.stop:
                return False
            if self._record_error is not None:
                raise RuntimeError(f"Audio loopback stopped: {self._record_error}") from self._record_error
            if self.matched:
                return True
            while hotkeys.paused and not hotkeys.stop:
                hotkeys.tick()
                time.sleep(0.05)
            time.sleep(0.02)
        return False


def decode_audio_mono(path: Path, sample_rate: int):
    import imageio_ffmpeg  # type: ignore
    import numpy as np  # type: ignore

    exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        exe,
        "-v",
        "error",
        "-i",
        str(path),
        "-f",
        "f32le",
        "-acodec",
        "pcm_f32le",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "pipe:1",
    ]
    data = subprocess.check_output(cmd)
    return np.frombuffer(data, dtype=np.float32)


def trim_silence(samples, ratio: float = 0.04):
    import numpy as np  # type: ignore

    if samples.size == 0:
        return samples
    peak = float(np.max(np.abs(samples)))
    if peak <= 1e-8:
        return samples
    mask = np.abs(samples) > peak * ratio
    if not bool(mask.any()):
        return samples
    indices = np.where(mask)[0]
    pad = int(0.04 * len(samples))
    start = max(0, int(indices[0]) - pad)
    end = min(len(samples), int(indices[-1]) + pad)
    return samples[start:end]


def normalized_template_score(samples, template, np_module) -> float:
    np = np_module
    m = int(template.size)
    n = int(samples.size)
    if n < m:
        return 0.0
    x = samples.astype(np.float32, copy=False)
    x = x - float(x.mean())
    size = 1 << int(math.ceil(math.log2(n + m - 1)))
    corr = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(template[::-1], size), size)
    valid = corr[m - 1 : n]

    x2 = x * x
    csum = np.concatenate(([0.0], np.cumsum(x2, dtype=np.float64)))
    energy = csum[m:] - csum[:-m]
    denom = np.sqrt(np.maximum(energy, 1e-12))
    scores = np.abs(valid) / denom
    return float(np.max(scores)) if scores.size else 0.0


def beep_found() -> None:
    for _ in range(6):
        kernel32.Beep(1400, 150)
        time.sleep(0.07)


class ShinyAutomation:
    def __init__(
        self,
        host: GameWindow,
        guest: GameWindow,
        config: dict,
        detector: AudioDetector | None,
        dry_run: bool,
        license_guard: LicenseGuard | None = None,
    ) -> None:
        self.host = host
        self.guest = guest
        self.config = config
        self.detector = detector
        self.hotkeys = Hotkeys()
        self.dry_run = dry_run
        self.license_guard = license_guard
        configure_input(config)

    @property
    def d(self) -> dict:
        return self.config["delays"]

    def score_text(self) -> str:
        if not self.detector or not self.detector.enabled:
            return "score=n/a"
        return f"score={self.detector.last_score:.3f}/{self.detector.threshold:.3f}"

    def step_log(self, message: str) -> None:
        log(f"{message} | {self.score_text()}")

    def randomization_config(self) -> dict:
        config = self.config.get("randomization", {})
        return config if isinstance(config, dict) else {}

    def randomized_wait_seconds(self, seconds: float) -> float:
        randomization = self.randomization_config()
        if not bool(randomization.get("enabled", False)) or seconds <= 0:
            return seconds
        ratio = max(0.0, float(randomization.get("wait_jitter_ratio", 0.0) or 0.0))
        max_jitter = max(0.0, float(randomization.get("wait_jitter_max_seconds", 0.0) or 0.0))
        jitter = seconds * ratio
        if max_jitter > 0:
            jitter = min(jitter, max_jitter)
        if jitter <= 0:
            return seconds
        return max(0.0, seconds + random.uniform(-jitter, jitter))

    def idle_action_delay(self, seconds: float, label: str) -> float | None:
        idle = self.randomization_config().get("idle_actions", {})
        if not isinstance(idle, dict) or not bool(idle.get("enabled", False)) or self.dry_run:
            return None
        if seconds < float(idle.get("min_wait_seconds", 0.0) or 0.0):
            return None
        labels = idle.get("labels", [])
        if isinstance(labels, list) and labels:
            lowered = label.lower()
            if not any(str(item).lower() in lowered for item in labels):
                return None
        chance = max(0.0, min(1.0, float(idle.get("space_chance", 0.0) or 0.0)))
        if random.random() >= chance:
            return None
        earliest = min(seconds * 0.35, max(0.0, seconds - 0.10))
        latest = max(earliest, seconds * 0.75)
        return random.uniform(earliest, latest)

    def perform_idle_action(self) -> None:
        idle = self.randomization_config().get("idle_actions", {})
        hold_seconds = 0.060
        if isinstance(idle, dict):
            hold_seconds = float(idle.get("space_hold", hold_seconds) or hold_seconds)
        self.step_log("Idle action SPACE")
        send_key(VK["SPACE"], hold_seconds=hold_seconds)

    def sleep(self, seconds: float, label: str = "Wait") -> None:
        original_seconds = max(0.0, seconds)
        seconds = self.randomized_wait_seconds(original_seconds)
        if seconds > 0:
            if abs(seconds - original_seconds) >= 0.01:
                self.step_log(f"{label} {seconds:.2f}s (base {original_seconds:.2f}s)")
            else:
                self.step_log(f"{label} {seconds:.2f}s")
        deadline = time.monotonic() + max(0.0, seconds)
        idle_at = self.idle_action_delay(seconds, label)
        idle_done = False
        while time.monotonic() < deadline:
            self.raise_if_license_blocked()
            self.raise_if_audio_detected()
            self.hotkeys.tick()
            if self.hotkeys.stop:
                return
            while self.hotkeys.paused and not self.hotkeys.stop:
                self.raise_if_license_blocked()
                self.raise_if_audio_detected()
                self.hotkeys.tick()
                time.sleep(0.05)
            if idle_at is not None and not idle_done and time.monotonic() >= deadline - seconds + idle_at:
                self.perform_idle_action()
                idle_done = True
            time.sleep(0.03)
        self.raise_if_license_blocked()
        self.raise_if_audio_detected()

    def raise_if_license_blocked(self) -> None:
        if self.license_guard:
            self.license_guard.raise_if_blocked()

    def raise_if_audio_detected(self) -> None:
        if not self.detector or not self.detector.enabled:
            return
        if self.detector._record_error is not None:
            raise RuntimeError(f"Audio loopback stopped: {self.detector._record_error}") from self.detector._record_error
        if self.detector.matched:
            raise ShinyDetected()

    def focus(self, win: GameWindow) -> bool:
        self.step_log(f"Focus hwnd={win.hwnd} title={win.title}")
        if not self.dry_run:
            focus_window(win.hwnd, self.d["after_focus"])
            if bool(self.config.get("focus_titlebar_click", True)):
                if click_title_bar(win.hwnd, strict=False):
                    self.sleep(self.d.get("after_focus_click", 0.10), "After titlebar focus click")
            if bool(self.config.get("focus_client_click", True)):
                if click_relative(win, self.config["coords"].get("focus_client", [0.50, 0.50]), strict=False):
                    self.sleep(self.d.get("after_focus_click", 0.10), "After client focus click")
            foreground = user32.GetForegroundWindow()
            if foreground != win.hwnd:
                self.step_log(
                    "Warning: focused window is not foreground. "
                    f"foreground hwnd={foreground}, title={window_title(foreground)!r}"
                )
                focused = False
            else:
                self.step_log(f"Foreground confirmed hwnd={foreground}")
                focused = True
            release_common_keys()
            return focused
        else:
            self.sleep(self.d["after_focus"], "Dry-run focus wait")
            return True

    def key(self, key_name: str, hold_seconds: float | None = None) -> None:
        hold_label = f", hold={hold_seconds:.2f}s" if hold_seconds is not None else ""
        self.step_log(f"Key {key_name}{hold_label}")
        if not self.dry_run:
            send_key(VK[key_name], hold_seconds=hold_seconds if hold_seconds is not None else 0.060)
        self.sleep(self.d["after_key"], f"After key {key_name}")

    def click(self, win: GameWindow, coord_name: str) -> None:
        rel = self.config["coords"][coord_name]
        self.step_log(f"Click {coord_name} at relative {rel}")
        if not self.dry_run:
            click_relative(win, rel)
        self.sleep(0.10, f"After click {coord_name}")

    def run(self) -> None:
        cycle_limit = int(self.config.get("cycle_limit", 0))
        cycle = 0
        if self.detector and self.detector.enabled:
            self.detector.start()
        try:
            while not self.hotkeys.stop:
                cycle += 1
                if cycle_limit and cycle > cycle_limit:
                    self.step_log("Cycle limit reached.")
                    return
                self.step_log(f"Cycle {cycle} start. F8 pause, F9 resume, F10 end.")
                found = self.run_cycle(cycle)
                if found:
                    self.step_log("Shiny prompt detected. Automation stopped and world is kept as-is.")
                    beep_found()
                    return
                self.sleep(self.d["between_cycles"], "Between cycles")
        except ShinyDetected:
            self.step_log("Shiny prompt detected globally. Automation stopped and world is kept as-is.")
            beep_found()
            return
        finally:
            if self.detector:
                self.detector.stop()
            if self.license_guard:
                self.license_guard.close()
            self.hotkeys.close()

    def run_cycle(self, cycle: int) -> bool:
        if not self.focus(self.guest):
            self.step_log("2P focus was not confirmed; skip request click to avoid dragging the game camera.")
            return False
        self.guest_open_menu_by_key()
        self.sleep(self.d["after_open_menu"], "After 2P menu open")
        self.click(self.guest, "guest_request_access")
        self.sleep(self.d["after_request"], "After 2P request")

        self.focus(self.host)
        self.host_accept_by_key()

        self.focus(self.guest)
        self.sleep(self.d["after_accept"], "After 1P accept")

        found = False
        if self.detector and self.detector.enabled:
            self.step_log("Global audio monitor active")
            self.sleep(float(self.d["listen_after_join"]), "After join listen/stabilize")
            self.step_log("Audio score checkpoint")
        else:
            self.sleep(self.d["listen_after_join"], "After join wait")

        if found or self.hotkeys.stop:
            return found

        self.focus(self.guest)
        self.key("U")
        self.sleep(self.d["after_open_leave_menu"], "After leave menu open")
        self.click(self.guest, "guest_leave_world")
        self.sleep(self.d["after_leave_click"], "After leave click")
        self.step_log(f"Cycle {cycle} finished, no prompt detected.")
        return False

    def guest_open_menu_by_key(self) -> None:
        self.sleep(self.d.get("before_guest_f", 0.70), "Before 2P F")
        attempts = max(1, int(self.d.get("guest_f_attempts", 1)))
        hold_seconds = float(self.d.get("guest_f_hold", self.d.get("host_f_hold", 0.100)))
        for attempt in range(1, attempts + 1):
            self.step_log(f"2P F attempt {attempt}/{attempts}")
            self.key("F", hold_seconds=hold_seconds)
            if attempt < attempts:
                self.sleep(self.d.get("guest_f_retry_wait", 0.25), "Between 2P F attempts")

    def host_accept_by_key(self) -> None:
        self.sleep(self.d.get("before_host_f", self.d.get("before_guest_f", 1.20)), "Before 1P F")
        attempts = max(1, int(self.d.get("host_f_attempts", 1)))
        hold_seconds = float(self.d.get("host_f_hold", 0.060))
        for attempt in range(1, attempts + 1):
            self.step_log(f"Host accept F attempt {attempt}/{attempts}")
            self.key("F", hold_seconds=hold_seconds)
            if attempt < attempts:
                self.sleep(self.d.get("host_f_retry_wait", 0.25), "Between 1P F attempts")
        self.sleep(self.d.get("after_host_f", 0.35), "After 1P F")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automate Rock Kingdom shiny refresh loop.")
    parser.add_argument("--config", default=None, help="Path to config JSON. Defaults to config.json beside the exe/script.")
    parser.add_argument("--list-windows", action="store_true", help="Only list matching game windows.")
    parser.add_argument("--host-hwnd", type=int, default=None, help="1P host window handle.")
    parser.add_argument("--guest-hwnd", type=int, default=None, help="2P guest window handle.")
    parser.add_argument("--resize-windows", action="store_true", help="Force resize both game windows to target_client_size.")
    parser.add_argument("--no-resize-windows", action="store_true", help="Do not resize game windows.")
    parser.add_argument("--no-audio", action="store_true", help="Run without audio detection.")
    parser.add_argument("--audio-test", action="store_true", help="Only test audio detection for 15 seconds.")
    parser.add_argument("--hotkey-debug", action="store_true", help="Only test F8/F9/F10 hotkeys.")
    parser.add_argument("--hotkey-debug-seconds", type=float, default=20.0, help="Seconds to run --hotkey-debug.")
    parser.add_argument("--test-active-f", action="store_true", help="After a countdown, press F in the current foreground window.")
    parser.add_argument("--test-guest-f", action="store_true", help="Only test 2P focus and F key.")
    parser.add_argument("--test-guest-request", action="store_true", help="Only test 2P focus, F key, and request click.")
    parser.add_argument("--test-host-accept", action="store_true", help="Only test 1P focus and accept action.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without clicking or pressing keys.")
    parser.add_argument("--activate", help="Activate this copy with the provided activation code, then exit.")
    parser.add_argument("--license-status", action="store_true", help="Print local license status and machine id, then exit.")
    parser.add_argument("--clear-license", action="store_true", help="Delete local license activation cache, then exit.")
    return parser.parse_args()


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).resolve() if args.config else app_base_dir() / "config.json"
    config = load_config(config_path)
    configure_input(config)
    license_guard: LicenseGuard | None = None

    if args.license_status:
        guard = LicenseGuard(config, config_path)
        if not LicenseGuard.enabled(config):
            print("license_enabled=False")
            print(f"machine_id={guard.machine_id}")
            print(f"state_file={guard.state_path}")
        else:
            print(guard.status_text())
        return 0

    if args.clear_license:
        guard = LicenseGuard(config, config_path)
        if guard.state_path.exists():
            guard.state_path.unlink()
            print(f"Deleted local license state: {guard.state_path}")
        else:
            print(f"No local license state found: {guard.state_path}")
        return 0

    if args.activate:
        guard = LicenseGuard(config, config_path, activation_code=args.activate)
        try:
            guard.activate(args.activate)
        except LicenseError as exc:
            print(f"Activation failed: {exc}")
            return 4
        return 0

    if LicenseGuard.enabled(config):
        license_guard = LicenseGuard(config, config_path)
        try:
            license_guard.validate(interactive=True)
        except LicenseError as exc:
            print(f"\nLicense check failed: {exc}\n")
            return 4
        log("License check OK.")

    if args.hotkey_debug:
        hotkeys = Hotkeys()
        deadline = time.monotonic() + max(1.0, float(args.hotkey_debug_seconds))
        log("Hotkey debug started. F8=pause, F9=resume, F10=end. You can focus the game now.")
        try:
            while time.monotonic() < deadline and not hotkeys.stop:
                hotkeys.tick()
                time.sleep(0.03)
            log(f"Hotkey debug finished. paused={hotkeys.paused}, stop={hotkeys.stop}")
        finally:
            hotkeys.close()
        return 0

    windows = enum_game_windows(str(config["window_title_keyword"]))
    if args.list_windows:
        if not windows:
            print("No matching windows found.")
        for idx, win in enumerate(windows, 1):
            print(f"{idx}. hwnd={win.hwnd} title={win.title!r} rect={win.rect} client={win.width}x{win.height}")
        return 0

    if args.test_active_f:
        input("\nPress Enter, then click the 2P game window within 5 seconds. The script will press F in the foreground window...")
        for left in range(5, 0, -1):
            log(f"Sending F in {left}...")
            time.sleep(1)
        foreground = user32.GetForegroundWindow()
        log(f"Foreground before F: hwnd={foreground}, title={window_title(foreground)!r}")
        release_common_keys()
        time.sleep(0.20)
        send_key(VK["F"])
        log("Active-window F test finished.")
        return 0

    detector = None
    if not args.no_audio and not args.test_guest_f and not args.test_guest_request and not args.test_host_accept:
        template_path = Path(str(config["audio_template"]))
        if not template_path.is_absolute():
            template_path = config_path.parent / template_path
        detector = AudioDetector(
            template_path=template_path,
            sample_rate=int(config["audio_sample_rate"]),
            threshold=float(config["audio_threshold"]),
            window_seconds=float(config["audio_window_seconds"]),
            check_interval=float(config["audio_check_interval_seconds"]),
        )
        try:
            detector.prepare()
        except Exception as exc:
            print(f"\nAudio detector is not ready: {exc}")
            print("Fix audio_template in config.json, or run with --no-audio for timing-only testing.\n")
            return 2

    if args.audio_test:
        if detector is None:
            raise SystemExit("--audio-test needs audio detection.")
        hotkeys = Hotkeys()
        detector.start()
        try:
            log("Audio test started for 15 seconds. Play the shiny prompt now if you want to test matching.")
            matched = detector.listen_until_match(15.0, hotkeys)
            log(f"matched={matched}, score={detector.last_score:.3f}, threshold={detector.threshold:.3f}")
        finally:
            detector.stop()
            hotkeys.close()
        return 0

    host, guest = choose_windows(windows, args.host_hwnd, args.guest_hwnd)
    print("\nSelected:")
    print(f"  1P host : hwnd={host.hwnd}, rect={host.rect}, client={host.width}x{host.height}")
    print(f"  2P guest: hwnd={guest.hwnd}, rect={guest.rect}, client={guest.width}x{guest.height}")

    should_resize = bool(config.get("resize_windows", False))
    if args.resize_windows:
        should_resize = True
    if args.no_resize_windows:
        should_resize = False
    if should_resize:
        size = config.get("target_client_size", [1280, 800])
        target_w, target_h = int(size[0]), int(size[1])
        host = resize_window_client(host, target_w, target_h)
        guest = resize_window_client(guest, target_w, target_h)
        print("\nAfter resize:")
        print(f"  1P host : hwnd={host.hwnd}, rect={host.rect}, client={host.width}x{host.height}")
        print(f"  2P guest: hwnd={guest.hwnd}, rect={guest.rect}, client={guest.width}x{guest.height}")

    automation = ShinyAutomation(
        host=host,
        guest=guest,
        config=config,
        detector=detector,
        dry_run=args.dry_run,
        license_guard=license_guard,
    )
    if args.test_guest_f:
        try:
            input("\nThis will only focus 2P and press F once. Press Enter to test...")
            automation.focus(guest)
            automation.sleep(automation.d.get("before_guest_f", 0.70), "Before 2P F test")
            automation.key("F")
            automation.step_log("2P F test finished. Check whether the 2P interaction menu opened.")
        finally:
            automation.hotkeys.close()
        return 0

    if args.test_guest_request:
        try:
            input("\nPut both characters face-to-face, then press Enter to test only the 2P request action...")
            automation.focus(guest)
            automation.sleep(automation.d.get("before_guest_f", 0.70), "Before 2P F test")
            automation.key("F")
            automation.sleep(automation.d["after_open_menu"], "After 2P menu open test")
            automation.click(guest, "guest_request_access")
            automation.step_log("2P request test finished.")
        finally:
            automation.hotkeys.close()
        return 0

    if args.test_host_accept:
        try:
            input("\nMake sure 1P already has an access request visible, then press Enter to test only 1P F accept...")
            automation.focus(host)
            automation.host_accept_by_key()
            automation.step_log("1P F accept test finished.")
        finally:
            automation.hotkeys.close()
        return 0

    input("\nPut both characters face-to-face, keep the game windows in windowed/borderless mode, then press Enter to start...")
    if license_guard:
        license_guard.start_background_checks()
    automation.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
