"""Windows entry point for the local Camoufox identity launcher."""

import ctypes

try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except (AttributeError, OSError):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)

def main():
    try:
        import tkinter as tk

        from launcher.gui import App

        root = tk.Tk()
        App(root)
        root.mainloop()
    except Exception as exc:
        ctypes.windll.user32.MessageBoxW(
            None,
            f"启动失败：{type(exc).__name__}: {exc}\n"
            "可运行 .venv\\Scripts\\python.exe run.py 查看详细错误。",
            "Camoufox 身份启动器",
            0x10,
        )
        raise


if __name__ == "__main__":
    main()
