"""DomainIntelApp 入口：启动加载页后进入行业情报工作台.

运行方式：
  开发模式:  python -m desktop.main        （在 DomainIntelApp 目录下）
  指定数据根: INTDOG_DATA_ROOT=D:/path/to/DomainIntelData python -m desktop.main

本程序不做抓取；抓取由 DomainIntelSearch 完成并写入 DomainIntelData。
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

from . import dataio
from .app import IntelApp
from .dpi import apply_tk_scaling, enable_high_dpi


def main():
    enable_high_dpi()
    data_root = dataio.find_data_root()
    root = tk.Tk()
    apply_tk_scaling(root)
    root.title("IntDog 正在启动")
    root.geometry("520x250")
    root.resizable(False, False)
    root.configure(bg="#F3F5F6")
    frame = tk.Frame(root, bg="#FFFFFF", highlightbackground="#D7DDE1",
                     highlightthickness=1)
    frame.pack(fill="both", expand=True, padx=18, pady=18)
    tk.Label(frame, text="IntDog", bg="#FFFFFF", fg="#27343B",
             font=("Microsoft YaHei UI", 20, "bold")).pack(anchor="w", padx=24, pady=(28, 2))
    status = tk.Label(frame, text="正在加载行业数据与运行状态…", bg="#FFFFFF",
                      fg="#6F7C83", font=("Microsoft YaHei UI", 10))
    status.pack(anchor="w", padx=24, pady=(0, 18))
    bar = ttk.Progressbar(frame, mode="indeterminate", length=420)
    bar.pack(padx=24, fill="x"); bar.start(10)

    def launch():
        bar.stop()
        for child in root.winfo_children():
            child.destroy()
        root.resizable(True, True)
        IntelApp(root, data_root)

    root.after(180, launch)
    root.mainloop()


if __name__ == "__main__":
    sys.exit(main())
