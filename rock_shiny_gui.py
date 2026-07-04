from __future__ import annotations

import copy
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import rock_shiny_auto as core


APP_TITLE = "Rock Kingdom Helper"
MIN_WAIT_SCALE = 0.5
MAX_WAIT_SCALE = 2.0


def app_base_dir() -> Path:
    return core.app_base_dir()


def display_window(index: int, win: core.GameWindow) -> str:
    x, y = win.rect[0], win.rect[1]
    return f"{index}. hwnd={win.hwnd} | {win.title} | {win.width}x{win.height} | ({x},{y})"


def mask_code(code: str) -> str:
    code = code.strip()
    if len(code) <= 8:
        return code or "未激活"
    return f"{code[:4]}...{code[-4:]}"


def scaled_config(config: dict, wait_scale: float, cycle_limit: int) -> dict:
    result = copy.deepcopy(config)
    scale = min(MAX_WAIT_SCALE, max(MIN_WAIT_SCALE, float(wait_scale)))
    delays = result.get("delays", {})
    if isinstance(delays, dict):
        for key, value in list(delays.items()):
            if key.endswith("_attempts"):
                continue
            if isinstance(value, (int, float)):
                delays[key] = round(float(value) * scale, 4)
    result["cycle_limit"] = max(0, int(cycle_limit))
    result["ui_wait_scale"] = scale
    return result


class ShinyAutoGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1407x1008")
        self.root.minsize(900, 660)

        self.base_dir = app_base_dir()
        self.config_path = self.base_dir / "config.json"
        self.config = core.load_config(self.config_path)
        self.windows: list[core.GameWindow] = []
        self.window_by_display: dict[str, core.GameWindow] = {}
        self.worker: threading.Thread | None = None
        self.automation: core.ShinyAutomation | None = None
        self.stop_requested = threading.Event()
        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()

        core.log = self.enqueue_core_log

        self.host_var = tk.StringVar()
        self.guest_var = tk.StringVar()
        self.speed_var = tk.DoubleVar(value=1.0)
        self.speed_text = tk.StringVar(value="等待倍率 1.00x")
        self.audio_var = tk.BooleanVar(value=True)
        self.resize_var = tk.BooleanVar(value=True)
        self.cycle_var = tk.StringVar(value=str(int(self.config.get("cycle_limit", 0) or 0)))
        self.activation_var = tk.StringVar()
        self.status_var = tk.StringVar(value="准备就绪")
        self.license_var = tk.StringVar(value="")

        self.build_ui()
        self.refresh_windows()
        self.refresh_license_status()
        self.root.after(100, self.drain_log_queue)

    def build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        outer = ttk.Frame(self.root, padding=14)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(3, weight=1)

        title = ttk.Label(
            outer,
            text="洛克王国世界炫彩刷新自动化（Created by 佩蘭）",
            font=("Microsoft YaHei UI", 15, "bold"),
        )
        title.grid(row=0, column=0, columnspan=2, sticky="w")

        status = ttk.Label(outer, textvariable=self.status_var)
        status.grid(row=0, column=1, sticky="e")

        self.build_window_panel(outer).grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(12, 8))
        self.build_control_panel(outer).grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(12, 8))
        self.build_instruction_panel(outer).grid(row=2, column=0, sticky="nsew", padx=(0, 8), pady=8)
        self.build_license_panel(outer).grid(row=2, column=1, sticky="nsew", padx=(8, 0), pady=8)
        self.build_log_panel(outer).grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(8, 0))

    def build_window_panel(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="窗口选择", padding=12)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="1P 主世界").grid(row=0, column=0, sticky="w", pady=4)
        self.host_combo = ttk.Combobox(frame, textvariable=self.host_var, state="readonly")
        self.host_combo.grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="2P 刷新号").grid(row=1, column=0, sticky="w", pady=4)
        self.guest_combo = ttk.Combobox(frame, textvariable=self.guest_var, state="readonly")
        self.guest_combo.grid(row=1, column=1, sticky="ew", pady=4)

        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        for idx in range(4):
            buttons.columnconfigure(idx, weight=1)
        ttk.Button(buttons, text="刷新", command=self.refresh_windows).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(buttons, text="交换", command=self.swap_windows).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(buttons, text="聚焦1P", command=lambda: self.focus_selected("host")).grid(row=0, column=2, sticky="ew", padx=6)
        ttk.Button(buttons, text="聚焦2P", command=lambda: self.focus_selected("guest")).grid(row=0, column=3, sticky="ew", padx=(6, 0))

        return frame

    def build_control_panel(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="运行控制", padding=12)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, textvariable=self.speed_text).grid(row=0, column=0, sticky="w")
        speed = ttk.Scale(
            frame,
            from_=MIN_WAIT_SCALE,
            to=MAX_WAIT_SCALE,
            variable=self.speed_var,
            command=self.update_speed_label,
        )
        speed.grid(row=0, column=1, sticky="ew", padx=(10, 0))

        ttk.Label(frame, text="0.5 更快，1 当前，2 更稳").grid(row=1, column=1, sticky="w", pady=(0, 8))

        ttk.Label(frame, text="循环次数").grid(row=2, column=0, sticky="w", pady=4)
        cycle_entry = ttk.Entry(frame, textvariable=self.cycle_var, width=12)
        cycle_entry.grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(frame, text="0 表示无限循环").grid(row=3, column=1, sticky="w", pady=(0, 8))

        ttk.Checkbutton(frame, text="启用炫彩音效监听", variable=self.audio_var).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=3
        )
        ttk.Checkbutton(frame, text="按配置调整窗口尺寸", variable=self.resize_var).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=3
        )

        controls = ttk.Frame(frame)
        controls.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)
        self.start_button = ttk.Button(controls, text="启动", command=self.start)
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.stop_button = ttk.Button(controls, text="停止", command=self.stop, state="disabled")
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        return frame

    def build_instruction_panel(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="基础操作说明", padding=12)
        text = tk.Text(frame, height=10, wrap="word", relief="flat")
        text.pack(fill="both", expand=True)
        text.insert(
            "1.0",
            "1. 打开 1P 和 2P 两个游戏窗口，让两个角色面对面站好，确保两个角色可以F交互且不会交互其他角色或眠枭所。\n"
            "2. 点击“刷新”，在上方选择 1P 主世界和 2P 刷新号；不确定时可以点“聚焦”确认。\n"
            "3. 等待倍率默认 1.00，就是当前调好的节奏；0.5 更快，2.0 更慢。\n"
            "4. 点击“启动”后不要操作鼠标键盘；脚本会自动申请访问、同意访问、监听音效并退出世界。\n"
            "5. 听到炫彩提示音会自动停止。\n"
            "6. 热键：F8 暂停，F9 继续，F10 结束。\n"
            "7. 若出现鼠标键盘不点击的情况，重启游戏即可。",
        )
        text.configure(state="disabled")
        return frame

    def build_license_panel(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="授权", padding=12)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, textvariable=self.license_var).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Label(frame, text="激活码").grid(row=1, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.activation_var).grid(row=1, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(frame, text="激活/校验", command=self.activate_license).grid(row=1, column=2, sticky="ew")

        ttk.Button(frame, text="清除本机授权缓存", command=self.clear_license_state).grid(
            row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0)
        )
        return frame

    def build_log_panel(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="运行日志", padding=8)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.log_text = tk.Text(frame, height=12, wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set, state="disabled")
        return frame

    def enqueue_core_log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log_queue.put(("log", f"[{stamp}] {message}"))

    def log(self, message: str) -> None:
        self.log_queue.put(("log", message))

    def drain_log_queue(self) -> None:
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "log":
                    self.append_log(payload)
                elif kind == "status":
                    self.status_var.set(payload)
                elif kind == "done":
                    self.on_worker_done(payload)
                elif kind == "error":
                    self.on_worker_error(payload)
                elif kind == "license_refresh":
                    self.refresh_license_status()
        except queue.Empty:
            pass
        self.root.after(100, self.drain_log_queue)

    def append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message.rstrip() + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def update_speed_label(self, _value: str | None = None) -> None:
        self.speed_text.set(f"等待倍率 {self.speed_var.get():.2f}x")

    def refresh_windows(self) -> None:
        try:
            windows = core.enum_game_windows(str(self.config["window_title_keyword"]))
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"读取游戏窗口失败：{exc}")
            return

        self.windows = windows
        self.window_by_display.clear()
        displays = []
        for idx, win in enumerate(windows, 1):
            label = display_window(idx, win)
            displays.append(label)
            self.window_by_display[label] = win
        self.host_combo["values"] = displays
        self.guest_combo["values"] = displays

        if len(displays) >= 2:
            if self.host_var.get() not in displays:
                self.host_var.set(displays[0])
            if self.guest_var.get() not in displays or self.guest_var.get() == self.host_var.get():
                self.guest_var.set(displays[1])
            self.status_var.set(f"检测到 {len(displays)} 个游戏窗口")
        elif len(displays) == 1:
            self.host_var.set(displays[0])
            self.guest_var.set("")
            self.status_var.set("只检测到 1 个游戏窗口")
        else:
            self.host_var.set("")
            self.guest_var.set("")
            self.status_var.set("未检测到游戏窗口")

    def swap_windows(self) -> None:
        host, guest = self.host_var.get(), self.guest_var.get()
        self.host_var.set(guest)
        self.guest_var.set(host)

    def selected_window(self, role: str) -> core.GameWindow:
        value = self.host_var.get() if role == "host" else self.guest_var.get()
        win = self.window_by_display.get(value)
        if not win:
            raise RuntimeError("请先刷新并选择 1P/2P 游戏窗口。")
        return core.read_game_window(win.hwnd)

    def focus_selected(self, role: str) -> None:
        try:
            win = self.selected_window(role)
            core.focus_window(win.hwnd, 0.3)
            self.log(f"已聚焦 {'1P' if role == 'host' else '2P'}：hwnd={win.hwnd}")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def refresh_license_status(self) -> None:
        guard = core.LicenseGuard(self.config, self.config_path)
        if not core.LicenseGuard.enabled(self.config):
            self.license_var.set("当前 config.json 未开启授权。")
            return
        state = core.read_json_file(guard.state_path)
        code = str(state.get("activation_code") or "")
        last_ok = str(state.get("last_ok_text") or "从未校验")
        self.license_var.set(f"授权已开启：{mask_code(code)}，上次校验：{last_ok}")

    def activate_license(self) -> None:
        if not core.LicenseGuard.enabled(self.config):
            messagebox.showinfo(APP_TITLE, "当前 config.json 未开启授权，无需激活。")
            return
        code = self.activation_var.get().strip()
        if not code:
            messagebox.showwarning(APP_TITLE, "请输入激活码。")
            return
        self.status_var.set("正在激活/校验授权...")
        threading.Thread(target=self._activate_license_worker, args=(code,), daemon=True).start()

    def _activate_license_worker(self, code: str) -> None:
        try:
            guard = core.LicenseGuard(self.config, self.config_path, activation_code=code)
            guard.validate(interactive=False)
            self.log_queue.put(("status", "授权校验成功"))
            self.log_queue.put(("log", f"授权成功：{mask_code(code)}"))
            self.log_queue.put(("license_refresh", ""))
        except Exception as exc:
            self.log_queue.put(("error", f"授权失败：{exc}"))

    def clear_license_state(self) -> None:
        guard = core.LicenseGuard(self.config, self.config_path)
        if guard.state_path.exists():
            guard.state_path.unlink()
            self.activation_var.set("")
            self.refresh_license_status()
            messagebox.showinfo(APP_TITLE, "已清除本机授权缓存。")
        else:
            messagebox.showinfo(APP_TITLE, "当前没有本机授权缓存。")

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        try:
            host = self.selected_window("host")
            guest = self.selected_window("guest")
            if host.hwnd == guest.hwnd:
                raise RuntimeError("1P 和 2P 不能选择同一个窗口。")
            cycle_limit = int(self.cycle_var.get().strip() or "0")
            if cycle_limit < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(APP_TITLE, "循环次数必须是大于等于 0 的整数。")
            return
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return

        run_config = scaled_config(self.config, self.speed_var.get(), cycle_limit)
        run_config["resize_windows"] = bool(self.resize_var.get())
        self.stop_requested.clear()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status_var.set("运行中")
        audio_enabled = bool(self.audio_var.get())
        activation_code = self.activation_var.get().strip()
        self.log(
            f"启动：1P hwnd={host.hwnd}，2P hwnd={guest.hwnd}，等待倍率={run_config['ui_wait_scale']:.2f}x，"
            f"音频监听={'开' if audio_enabled else '关'}"
        )
        self.worker = threading.Thread(
            target=self.run_worker,
            args=(host, guest, run_config, audio_enabled, activation_code),
            daemon=True,
        )
        self.worker.start()

    def run_worker(
        self,
        host: core.GameWindow,
        guest: core.GameWindow,
        config: dict,
        audio_enabled: bool,
        activation_code: str,
    ) -> None:
        detector: core.AudioDetector | None = None
        license_guard: core.LicenseGuard | None = None
        try:
            if core.LicenseGuard.enabled(config):
                license_guard = core.LicenseGuard(config, self.config_path, activation_code=activation_code or None)
                if not license_guard._state.get("activation_code") and not activation_code:
                    raise core.LicenseError("请输入激活码后再启动。")
                license_guard.validate(interactive=False)
                core.log("License check OK.")
            if self.stop_requested.is_set():
                self.log_queue.put(("done", "已停止"))
                return

            if audio_enabled:
                template_path = Path(str(config["audio_template"]))
                if not template_path.is_absolute():
                    template_path = self.config_path.parent / template_path
                detector = core.AudioDetector(
                    template_path=template_path,
                    sample_rate=int(config["audio_sample_rate"]),
                    threshold=float(config["audio_threshold"]),
                    window_seconds=float(config["audio_window_seconds"]),
                    check_interval=float(config["audio_check_interval_seconds"]),
                )
                detector.prepare()
            if self.stop_requested.is_set():
                self.log_queue.put(("done", "已停止"))
                return

            if bool(config.get("resize_windows", False)):
                size = config.get("target_client_size", [1280, 800])
                host = core.resize_window_client(host, int(size[0]), int(size[1]))
                guest = core.resize_window_client(guest, int(size[0]), int(size[1]))
            if self.stop_requested.is_set():
                self.log_queue.put(("done", "已停止"))
                return

            automation = core.ShinyAutomation(
                host=host,
                guest=guest,
                config=config,
                detector=detector,
                dry_run=False,
                license_guard=license_guard,
            )
            self.automation = automation
            if license_guard:
                license_guard.start_background_checks()
            automation.run()
            self.log_queue.put(("done", "已停止"))
        except Exception as exc:
            if license_guard:
                license_guard.close()
            if detector:
                detector.stop()
            self.log_queue.put(("error", str(exc)))
        finally:
            self.automation = None

    def stop(self) -> None:
        self.stop_requested.set()
        if self.automation:
            self.automation.hotkeys.handle_action("end", source="UI stop")
            self.status_var.set("正在停止...")
        else:
            self.on_worker_done("已停止")

    def on_worker_done(self, message: str) -> None:
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.status_var.set(message)
        self.refresh_license_status()

    def on_worker_error(self, message: str) -> None:
        self.append_log(f"错误：{message}")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.status_var.set("出错")
        messagebox.showerror(APP_TITLE, message)


def main() -> None:
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("vista")
    except tk.TclError:
        pass
    ShinyAutoGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
