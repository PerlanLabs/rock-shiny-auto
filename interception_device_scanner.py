from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time

import rock_shiny_auto as core


def setup_console() -> None:
    if os.name == "nt":
        os.system("chcp 65001 > nul")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def pause(message: str = "按 Enter 退出...") -> None:
    try:
        input(f"\n{message}")
    except EOFError:
        pass


def import_interception():
    try:
        import interception  # type: ignore
        from interception import exceptions  # type: ignore
    except Exception as exc:
        print("无法加载驱动输入组件。请确认这是完整发布包里的 DeviceScanner.exe。")
        print(f"错误：{exc}")
        pause()
        raise SystemExit(1) from exc
    return interception, exceptions


def check_driver(interception, exceptions) -> bool:
    try:
        interception.auto_capture_devices(verbose=True)
        print(f"当前自动识别：keyboard={interception.get_keyboard()} mouse={interception.get_mouse()}")
        return True
    except exceptions.DriverNotFoundError:
        print("\n没有检测到 Interception 驱动，或安装后还没有重启。")
        print("请先用管理员 PowerShell 运行：")
        print("powershell -NoProfile -ExecutionPolicy Bypass -File .\\install_interception_driver.ps1")
        print("安装完成后重启 Windows，再运行 DeviceScanner.exe。")
        return False
    except Exception as exc:
        print(f"\n驱动检测失败：{exc}")
        return False


def load_config() -> tuple[Path, dict]:
    config_path = core.app_base_dir() / "config.json"
    return config_path, core.load_config(config_path)


def choose_window(config: dict) -> core.GameWindow | None:
    keyword = str(config.get("window_title_keyword") or "")
    while True:
        windows = core.enum_game_windows(keyword)
        if windows:
            print("\n检测到游戏窗口：")
            for idx, win in enumerate(windows, 1):
                print(f"{idx}. hwnd={win.hwnd} | {win.title} | {win.width}x{win.height} | rect={win.rect}")
            raw = input("\n请选择要测试的窗口编号，一般选择 2P 刷新号窗口，输入 q 退出：").strip().lower()
            if raw == "q":
                return None
            if raw.isdigit() and 1 <= int(raw) <= len(windows):
                return core.read_game_window(windows[int(raw) - 1].hwnd)
            print("输入无效，请重新选择。")
        else:
            raw = input("\n没有检测到游戏窗口。请打开游戏后按 Enter 重试，或输入 q 退出：").strip().lower()
            if raw == "q":
                return None


def ask_result(prompt: str) -> str:
    while True:
        raw = input(prompt).strip().lower()
        if raw in {"y", "n", "q"}:
            return raw
        print("请输入 y / n / q。")


def press_key(interception, key: str, keyboard_device: int) -> None:
    interception.set_devices(keyboard=keyboard_device)
    interception.key_down(key)
    time.sleep(0.10)
    interception.key_up(key)


def click_screen(interception, x: int, y: int, mouse_device: int) -> None:
    interception.set_devices(mouse=mouse_device)
    interception.click(x, y, button="left", clicks=1, delay=0.15)


def scan_keyboards(interception, win: core.GameWindow) -> list[int]:
    print("\n=== 键盘设备扫描 ===")
    print("将依次测试 keyboard 0-9。每次会聚焦所选游戏窗口并按一次 F。")
    print("如果游戏里的 F 交互菜单打开了，就输入 y；没反应输入 n；输入 q 可跳过。")
    input("\n准备好后按 Enter 开始键盘扫描...")

    hits: list[int] = []
    for device in range(10):
        print(f"\n测试 keyboard={device}")
        core.focus_window(win.hwnd, 0.80)
        time.sleep(0.25)
        try:
            press_key(interception, "f", device)
            answer = ask_result(f"keyboard={device} 是否有效？y=有效 n=无效 q=停止键盘扫描：")
        except Exception as exc:
            print(f"keyboard={device} 执行失败：{exc}")
            answer = "n"
        if answer == "y":
            hits.append(device)
        if answer == "q":
            break
        input("如果菜单打开了，请先手动关闭。按 Enter 继续...")
    return hits


def request_button_screen_pos(win: core.GameWindow, config: dict) -> tuple[int, int]:
    rel = config.get("coords", {}).get("guest_request_access", [0.903, 0.943])
    client_x = int(win.width * float(rel[0]))
    client_y = int(win.height * float(rel[1]))
    return core.client_to_screen(win.hwnd, client_x, client_y)


def scan_mice(interception, win: core.GameWindow, config: dict) -> list[int]:
    print("\n=== 鼠标设备扫描 ===")
    print("将依次测试 mouse 10-19。")
    print("请手动打开 2P 的 F 交互菜单，并让“申请访问”按钮显示出来。")
    print("如果点击生效了，就输入 y；没反应输入 n；输入 q 可跳过。")
    input("\n准备好后按 Enter 开始鼠标扫描...")

    x, y = request_button_screen_pos(win, config)
    print(f"测试点击坐标：screen=({x}, {y})")

    hits: list[int] = []
    for device in range(10, 20):
        print(f"\n测试 mouse={device}")
        core.focus_window(win.hwnd, 0.80)
        time.sleep(0.25)
        try:
            click_screen(interception, x, y, device)
            answer = ask_result(f"mouse={device} 是否有效？y=有效 n=无效 q=停止鼠标扫描：")
        except Exception as exc:
            print(f"mouse={device} 执行失败：{exc}")
            answer = "n"
        if answer == "y":
            hits.append(device)
        if answer == "q":
            break
        input("如果菜单被点掉了，请重新打开 F 菜单。按 Enter 继续...")
    return hits


def save_results(keyboard_hits: list[int], mouse_hits: list[int]) -> Path:
    path = core.app_base_dir() / "device_scan_results.txt"
    lines = [
        "Interception device scan results",
        f"KEYBOARD_OK: {keyboard_hits}",
        f"MOUSE_OK: {mouse_hits}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n扫描结果已写入：{path}")
    print("\n".join(lines))
    return path


def update_config(config_path: Path, keyboard_device: int, mouse_device: int) -> None:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    input_config = data.setdefault("input", {})
    input_config["backend"] = "interception"
    input_config["keyboard_device"] = int(keyboard_device)
    input_config["mouse_device"] = int(mouse_device)
    config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def maybe_update_config(config_path: Path, keyboard_hits: list[int], mouse_hits: list[int]) -> None:
    if not keyboard_hits or not mouse_hits:
        print("\n没有同时找到可用键盘和鼠标设备，暂不修改 config.json。")
        return

    keyboard_device = keyboard_hits[0]
    mouse_device = mouse_hits[0]
    print("\n建议写入 config.json 的设备：")
    print(f"keyboard_device = {keyboard_device}")
    print(f"mouse_device = {mouse_device}")
    answer = ask_result("是否自动写入 config.json？y=写入 n=不写 q=不写：")
    if answer == "y":
        update_config(config_path, keyboard_device, mouse_device)
        print("已写入 config.json。重新打开主程序后生效。")


def main() -> int:
    setup_console()
    print("Interception 设备扫描器")
    print("用途：找出当前电脑可用的 keyboard_device 和 mouse_device。")

    interception, exceptions = import_interception()
    if not check_driver(interception, exceptions):
        pause()
        return 1

    config_path, config = load_config()
    win = choose_window(config)
    if win is None:
        pause()
        return 0

    keyboard_hits = scan_keyboards(interception, win)
    mouse_hits = scan_mice(interception, win, config)
    save_results(keyboard_hits, mouse_hits)
    maybe_update_config(config_path, keyboard_hits, mouse_hits)
    pause()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
