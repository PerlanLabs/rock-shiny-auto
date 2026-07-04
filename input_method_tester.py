from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
import time

import rock_shiny_auto as core


VK_F = core.VK["F"]
VK_ESC = core.VK["ESC"]
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001
KEYEVENTF_KEYUP = core.KEYEVENTF_KEYUP
MOUSEEVENTF_LEFTDOWN = core.MOUSEEVENTF_LEFTDOWN
MOUSEEVENTF_LEFTUP = core.MOUSEEVENTF_LEFTUP
MOUSEEVENTF_ABSOLUTE = core.MOUSEEVENTF_ABSOLUTE
MOUSEEVENTF_MOVE = core.MOUSEEVENTF_MOVE
SM_CXSCREEN = 0
SM_CYSCREEN = 1

user32 = core.user32
kernel32 = core.kernel32
shell32 = ctypes.windll.shell32

user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.POINTER(ctypes.c_ulong)]
user32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_ulong)]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]


def is_admin() -> bool:
    try:
        return bool(shell32.IsUserAnAdmin())
    except Exception:
        return False


def vk_input(vk: int, is_up: bool) -> core.INPUT:
    flags = KEYEVENTF_KEYUP if is_up else 0
    return core.INPUT(type=core.INPUT_KEYBOARD, union=core.INPUT_UNION(ki=core.KEYBDINPUT(vk, 0, flags, 0, None)))


def sendinput_vk(vk: int, hold: float = 0.10) -> None:
    down = vk_input(vk, False)
    up = vk_input(vk, True)
    user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(core.INPUT))
    time.sleep(hold)
    user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(core.INPUT))


def sendinput_scancode(vk: int, hold: float = 0.10) -> None:
    core.send_key(vk, hold_seconds=hold)


def keybd_event_key(vk: int, hold: float = 0.10) -> None:
    scan = user32.MapVirtualKeyW(vk, core.MAPVK_VK_TO_VSC)
    user32.keybd_event(vk, scan, 0, None)
    time.sleep(hold)
    user32.keybd_event(vk, scan, KEYEVENTF_KEYUP, None)


def postmessage_key(hwnd: int, vk: int, hold: float = 0.10) -> None:
    scan = user32.MapVirtualKeyW(vk, core.MAPVK_VK_TO_VSC)
    down_lparam = 1 | (scan << 16)
    up_lparam = 1 | (scan << 16) | (1 << 30) | (1 << 31)
    user32.PostMessageW(hwnd, WM_KEYDOWN, vk, down_lparam)
    time.sleep(hold)
    user32.PostMessageW(hwnd, WM_KEYUP, vk, up_lparam)


def click_setcursor_sendinput(x: int, y: int) -> None:
    core.click_screen(x, y)


def click_sendinput_absolute(x: int, y: int) -> None:
    screen_w = max(1, int(user32.GetSystemMetrics(SM_CXSCREEN)) - 1)
    screen_h = max(1, int(user32.GetSystemMetrics(SM_CYSCREEN)) - 1)
    nx = int(int(x) * 65535 / screen_w)
    ny = int(int(y) * 65535 / screen_h)
    move = core.INPUT(
        type=core.INPUT_MOUSE,
        union=core.INPUT_UNION(mi=core.MOUSEINPUT(nx, ny, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, 0, None)),
    )
    down = core.INPUT(type=core.INPUT_MOUSE, union=core.INPUT_UNION(mi=core.MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, None)))
    up = core.INPUT(type=core.INPUT_MOUSE, union=core.INPUT_UNION(mi=core.MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, None)))
    inputs = (core.INPUT * 3)(move, down, up)
    user32.SendInput(3, inputs, ctypes.sizeof(core.INPUT))


def click_mouse_event(x: int, y: int) -> None:
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)


def click_postmessage(hwnd: int, client_x: int, client_y: int) -> None:
    lparam = (int(client_y) << 16) | int(client_x)
    user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lparam)
    time.sleep(0.03)
    user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
    time.sleep(0.06)
    user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)


KEY_METHODS = [
    ("sendinput_scancode", "当前主程序方式：SendInput + 扫描码", sendinput_scancode),
    ("sendinput_vk", "SendInput + 虚拟键码", sendinput_vk),
    ("keybd_event", "旧接口 keybd_event", keybd_event_key),
    ("postmessage_key", "窗口消息 PostMessage WM_KEYDOWN/UP", postmessage_key),
]

MOUSE_METHODS = [
    ("setcursor_sendinput", "当前主程序方式：SetCursorPos + SendInput 点击", click_setcursor_sendinput),
    ("sendinput_absolute", "SendInput 绝对移动 + 点击", click_sendinput_absolute),
    ("mouse_event", "旧接口 mouse_event 点击", click_mouse_event),
    ("postmessage_click", "窗口消息 PostMessage 鼠标点击", click_postmessage),
]


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


def run_key_tests(win: core.GameWindow, results: list[str]) -> None:
    print("\n=== F 键测试 ===")
    print("每个方法会切到游戏窗口并按一次 F。")
    print("请观察互动菜单是否打开。打开后请手动关闭菜单，再继续下一个测试。")

    for name, desc, func in KEY_METHODS:
        input(f"\n准备测试 [{name}] {desc}，按 Enter 开始...")
        win = core.read_game_window(win.hwnd)
        core.focus_window(win.hwnd, 0.8)
        time.sleep(0.25)
        try:
            if name == "postmessage_key":
                func(win.hwnd, VK_F)
            else:
                func(VK_F)
        except Exception as exc:
            print(f"执行失败：{exc}")
            results.append(f"KEY {name}: error {exc}")
            continue
        answer = ask_result("F 菜单是否打开？y=成功 n=失败 q=停止：")
        results.append(f"KEY {name}: {answer}")
        if answer == "q":
            return
        input("请确认菜单已关闭，然后按 Enter 继续...")


def choose_click_point(win: core.GameWindow) -> tuple[int, int, int, int]:
    print("\n点击位置：")
    print("1. 画面中心，用于测试鼠标是否能点到游戏")
    print("2. 申请访问按钮位置，用于配合已打开的 F 菜单测试")
    raw = input("选择点击位置，默认 1：").strip()
    rel = [0.5, 0.5]
    if raw == "2":
        config = core.load_config(core.app_base_dir() / "config.json")
        rel = config.get("coords", {}).get("guest_request_access", [0.903, 0.943])
    client_x = int(win.width * float(rel[0]))
    client_y = int(win.height * float(rel[1]))
    screen_x, screen_y = core.client_to_screen(win.hwnd, client_x, client_y)
    print(f"将点击 client=({client_x},{client_y}) screen=({screen_x},{screen_y}) rel={rel}")
    return client_x, client_y, screen_x, screen_y


def run_mouse_tests(win: core.GameWindow, results: list[str]) -> None:
    print("\n=== 鼠标点击测试 ===")
    print("如果测试申请访问按钮，请先手动打开 F 菜单并确认按钮可见。")
    client_x, client_y, screen_x, screen_y = choose_click_point(win)
    for name, desc, func in MOUSE_METHODS:
        input(f"\n准备测试 [{name}] {desc}，按 Enter 开始...")
        win = core.read_game_window(win.hwnd)
        core.focus_window(win.hwnd, 0.8)
        time.sleep(0.25)
        try:
            if name == "postmessage_click":
                func(win.hwnd, client_x, client_y)
            else:
                func(screen_x, screen_y)
        except Exception as exc:
            print(f"执行失败：{exc}")
            results.append(f"MOUSE {name}: error {exc}")
            continue
        answer = ask_result("这次点击是否生效？y=成功 n=失败 q=停止：")
        results.append(f"MOUSE {name}: {answer}")
        if answer == "q":
            return


def save_results(results: list[str]) -> None:
    path = Path("input_test_results.txt")
    text = "\n".join(results) + "\n"
    path.write_text(text, encoding="utf-8")
    print(f"\n结果已写入：{path.resolve()}")
    print(text)


def main() -> int:
    print("RockShinyAuto 输入方式测试器")
    print(f"当前进程管理员权限：{'是' if is_admin() else '否'}")
    print("如果游戏是管理员权限启动，建议也用管理员权限运行这个测试器。")
    win = choose_window()
    print(f"\n测试窗口：hwnd={win.hwnd} title={win.title!r}")
    results: list[str] = []

    while True:
        print("\n选择测试：")
        print("1. 测试 F 键输入方式")
        print("2. 测试鼠标点击方式")
        print("3. 全部测试")
        print("q. 退出")
        raw = input("请输入：").strip().lower()
        if raw == "1":
            run_key_tests(win, results)
            save_results(results)
        elif raw == "2":
            run_mouse_tests(win, results)
            save_results(results)
        elif raw == "3":
            run_key_tests(win, results)
            run_mouse_tests(win, results)
            save_results(results)
        elif raw == "q":
            save_results(results)
            return 0
        else:
            print("输入无效。")


if __name__ == "__main__":
    raise SystemExit(main())
