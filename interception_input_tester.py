from __future__ import annotations

from pathlib import Path
import time

import rock_shiny_auto as core


def import_interception():
    try:
        import interception  # type: ignore
        from interception import exceptions  # type: ignore
    except Exception as exc:
        raise SystemExit(
            "无法导入 interception-python。请先运行：\n"
            "python -m pip install -r requirements.txt\n\n"
            f"错误：{exc}"
        ) from exc
    return interception, exceptions


def check_driver(interception, exceptions) -> None:
    try:
        interception.auto_capture_devices(verbose=True)
    except exceptions.DriverNotFoundError as exc:
        raise SystemExit(
            "\nInterception 驱动未安装或未生效。\n"
            "请用管理员 PowerShell 运行：\n"
            "powershell -NoProfile -ExecutionPolicy Bypass -File .\\install_interception_driver.ps1\n\n"
            "安装完成后重启 Windows，再运行本测试器。\n"
        ) from exc


def choose_window() -> core.GameWindow:
    config_path = core.app_base_dir() / "config.json"
    config = core.load_config(config_path)
    windows = core.enum_game_windows(str(config["window_title_keyword"]))
    if not windows:
        raise SystemExit("没有检测到游戏窗口，请先打开游戏。")

    print("\n检测到窗口：")
    for idx, win in enumerate(windows, 1):
        print(f"{idx}. hwnd={win.hwnd} title={win.title!r} client={win.width}x{win.height} rect={win.rect}")

    while True:
        raw = input("\n选择要测试的窗口编号，一般选 2P：").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(windows):
            return core.read_game_window(windows[int(raw) - 1].hwnd)
        print("输入无效。")


def ask_result(prompt: str) -> str:
    while True:
        raw = input(prompt).strip().lower()
        if raw in {"y", "n", "q"}:
            return raw
        print("请输入 y / n / q。")


def save_results(results: list[str]) -> None:
    path = Path("interception_test_results.txt")
    text = "\n".join(results) + "\n"
    path.write_text(text, encoding="utf-8")
    print(f"\n结果已写入：{path.resolve()}")
    print(text)


def press_f(interception, keyboard_device: int | None = None) -> None:
    if keyboard_device is not None:
        interception.set_devices(keyboard=keyboard_device)
    interception.key_down("f")
    time.sleep(0.10)
    interception.key_up("f")


def click_screen(interception, x: int, y: int, mouse_device: int | None = None) -> None:
    if mouse_device is not None:
        interception.set_devices(mouse=mouse_device)
    interception.click(x, y, button="left", clicks=1, delay=0.15)


def run_default_test(interception, win: core.GameWindow, results: list[str]) -> None:
    print("\n=== 默认设备测试 ===")
    interception.auto_capture_devices(verbose=True)
    print(f"当前 keyboard={interception.get_keyboard()} mouse={interception.get_mouse()}")

    input("\n准备测试默认设备 F 键。按 Enter 后会聚焦窗口并按 F...")
    core.focus_window(win.hwnd, 0.8)
    time.sleep(0.25)
    try:
        press_f(interception)
        answer = ask_result("F 菜单是否打开？y=成功 n=失败 q=停止：")
    except Exception as exc:
        print(f"执行失败：{exc}")
        answer = f"error {exc}"
    results.append(f"DEFAULT KEY keyboard={interception.get_keyboard()}: {answer}")
    if answer == "q":
        return

    input("如果菜单打开了，请先手动关闭。按 Enter 继续鼠标测试...")
    config = core.load_config(core.app_base_dir() / "config.json")
    rel = config.get("coords", {}).get("guest_request_access", [0.903, 0.943])
    client_x = int(win.width * float(rel[0]))
    client_y = int(win.height * float(rel[1]))
    screen_x, screen_y = core.client_to_screen(win.hwnd, client_x, client_y)
    print(f"将点击申请访问位置 screen=({screen_x},{screen_y}) rel={rel}")
    core.focus_window(win.hwnd, 0.8)
    time.sleep(0.25)
    try:
        click_screen(interception, screen_x, screen_y)
        answer = ask_result("点击是否生效？y=成功 n=失败 q=停止：")
    except Exception as exc:
        print(f"执行失败：{exc}")
        answer = f"error {exc}"
    results.append(f"DEFAULT MOUSE mouse={interception.get_mouse()}: {answer}")


def run_keyboard_device_scan(interception, win: core.GameWindow, results: list[str]) -> None:
    print("\n=== 键盘设备扫描 ===")
    print("会依次尝试 keyboard 0-9。每次按一次 F。")
    for device in range(10):
        input(f"\n准备测试 keyboard={device}，按 Enter 开始...")
        core.focus_window(win.hwnd, 0.8)
        time.sleep(0.25)
        try:
            press_f(interception, keyboard_device=device)
            answer = ask_result(f"keyboard={device} 的 F 是否生效？y=成功 n=失败 q=停止：")
        except Exception as exc:
            print(f"执行失败：{exc}")
            answer = f"error {exc}"
        results.append(f"KEYBOARD {device}: {answer}")
        if answer == "q":
            return
        input("如果菜单打开了，请先手动关闭。按 Enter 继续...")


def run_mouse_device_scan(interception, win: core.GameWindow, results: list[str]) -> None:
    print("\n=== 鼠标设备扫描 ===")
    print("会依次尝试 mouse 10-19。建议先手动打开 F 菜单，让申请访问按钮可见。")
    config = core.load_config(core.app_base_dir() / "config.json")
    rel = config.get("coords", {}).get("guest_request_access", [0.903, 0.943])
    client_x = int(win.width * float(rel[0]))
    client_y = int(win.height * float(rel[1]))
    screen_x, screen_y = core.client_to_screen(win.hwnd, client_x, client_y)
    print(f"将点击 screen=({screen_x},{screen_y}) rel={rel}")

    for device in range(10, 20):
        input(f"\n准备测试 mouse={device}，按 Enter 开始...")
        core.focus_window(win.hwnd, 0.8)
        time.sleep(0.25)
        try:
            click_screen(interception, screen_x, screen_y, mouse_device=device)
            answer = ask_result(f"mouse={device} 点击是否生效？y=成功 n=失败 q=停止：")
        except Exception as exc:
            print(f"执行失败：{exc}")
            answer = f"error {exc}"
        results.append(f"MOUSE {device}: {answer}")
        if answer == "q":
            return


def main() -> int:
    interception, exceptions = import_interception()
    check_driver(interception, exceptions)

    print("\nInterception 驱动已检测到。")
    win = choose_window()
    results: list[str] = []

    while True:
        print("\n选择测试：")
        print("1. 默认设备测试")
        print("2. 扫描 keyboard 0-9")
        print("3. 扫描 mouse 10-19")
        print("4. 全部测试")
        print("q. 退出")
        raw = input("请输入：").strip().lower()
        if raw == "1":
            run_default_test(interception, win, results)
            save_results(results)
        elif raw == "2":
            run_keyboard_device_scan(interception, win, results)
            save_results(results)
        elif raw == "3":
            run_mouse_device_scan(interception, win, results)
            save_results(results)
        elif raw == "4":
            run_default_test(interception, win, results)
            run_keyboard_device_scan(interception, win, results)
            run_mouse_device_scan(interception, win, results)
            save_results(results)
        elif raw == "q":
            save_results(results)
            return 0
        else:
            print("输入无效。")


if __name__ == "__main__":
    raise SystemExit(main())
