# -*- coding: utf-8 -*-
"""Launch the TaskDock desktop panel.

Usage:
    python app.py
    pythonw app.py
    python app.py --data-dir C:\\Temp\\taskdock-test
"""

import argparse
import ctypes

_MUTEX = None


def acquire_single_instance():
    """Keep one panel per desktop session, except for isolated preview/test data."""
    global _MUTEX
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetLastError(0)
        _MUTEX = kernel32.CreateMutexW(None, False, "Local\\TaskDock_SingleInstance")
        if not _MUTEX:
            return True
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            return False
        return True
    except Exception:
        return True


def show_already_running():
    try:
        ctypes.windll.user32.MessageBoxW(
            0,
            "旁挂清单已经在运行。\n\n如果窗口收起了，请点击屏幕右边缘的「任务清单」标签展开。",
            "旁挂清单",
            0x40,
        )
    except Exception:
        pass


def enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="TaskDock desktop task panel")
    parser.add_argument("--data-dir", default=None, help="override the data directory")
    parser.add_argument("--demo", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-show", action="store_true", help="build the window without showing it")
    args = parser.parse_args()

    enable_dpi_awareness()
    if args.data_dir is None and not acquire_single_instance():
        show_already_running()
        return None
    from taskdock.ui_app import build_app

    app = build_app(data_dir=args.data_dir, seed=args.demo, auto_show=not args.no_show)
    if not args.no_show:
        app.mainloop()
    return app


if __name__ == "__main__":
    main()
