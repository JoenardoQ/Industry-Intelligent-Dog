"""DomainIntelApp - 低饱和桌面工作台与来源优先研究入口.

联网研究与抓取由 DomainIntelSearch 子进程执行并按行业分目录写入 DomainIntelData。
本程序：
  - 行业选择（DomainIntelData 下的行业文件夹）
  - 定期更新开关（写 control.json；内置调度线程按日/周/月/季触发抓取子进程）
  - 展示全部定期类别（每日：新闻/GitHub/融资/招聘/CEO/论文；周/月/季产物）
  - 来源质量门槛 → 产业链 → 多类型实体的严格顺序初始化
  - 信息源、行业报告查看
  - 每个条目卡片：标题 + abstract + 链接，可打开、可删除（无编辑）
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from . import dataio

# ---------------- 低饱和浅色主题 ----------------
BG = "#F3F5F6"; BG2 = "#FFFFFF"; BG3 = "#E2E7EA"
FG = "#1F2B31"; FG_DIM = "#5D6A71"
ACCENT = "#607D8B"; GREEN = "#718A79"; AMBER = "#9A8565"
PURPLE = "#81798F"; RED = "#A16F6F"; CYAN = "#66858A"
BORDER = "#C7D0D5"
FONT = "Microsoft YaHei UI"

CAT_META = {
    "news":    ("新闻", ACCENT), "github": ("GitHub", "#52636C"),
    "funding": ("融资", GREEN),  "hiring": ("招聘", AMBER),
    "ceo":     ("CEO发言", PURPLE), "papers": ("论文", CYAN),
}
PERIOD_META = {"weekly": "每周行业总结", "monthly": "每月产业分析",
               "quarterly": "每季财报分析"}


def open_path(path: str):
    try:
        if "://" in str(path):
            webbrowser.open(path); return
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError:
        webbrowser.open(Path(path).as_uri())


class ScrollFrame(tk.Frame):
    """可滚动容器."""
    def __init__(self, parent, bg=BG):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(
            self._win, width=e.width))
        self.inner.bind("<Enter>", lambda e: self.canvas.bind_all(
            "<MouseWheel>", self._on_wheel))
        self.inner.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _on_wheel(self, e):
        # 只响应当前可见的滚动区——修复多标签页下滚轮滚到隐藏页内容的冲突
        if not self.canvas.winfo_ismapped():
            return
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()


class IntelApp:
    def __init__(self, root: tk.Tk, data_root: Path):
        self.root = root
        self.data_root = Path(data_root)
        self.folder = None
        self.daily_cat = "all"
        self.daily_date = None
        self.daily_origin = "all"
        self._daily_shown = self.PAGE_SIZE
        self._sched_stop = threading.Event()
        self._sched_thread = None

        self._setup_window()
        self._setup_style()
        self._build_ui()
        self._reload_industries()
        self._start_scheduler()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    def _setup_window(self):
        self.root.title("IntDog 领域情报中心")
        self.root.geometry("1320x850")
        self.root.minsize(1000, 640)
        self.root.configure(bg=BG)
        try:
            self.root.iconbitmap(str(Path(__file__).resolve().parents[1] / "app" / "intdog.ico"))
        except tk.TclError:
            pass

    def _setup_style(self):
        s = ttk.Style(self.root)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure(".", background=BG, foreground=FG, fieldbackground=BG2,
                    bordercolor=BORDER, lightcolor=BG2, darkcolor=BORDER,
                    font=(FONT, 10))
        s.configure("Treeview", background=BG2, foreground=FG,
                    fieldbackground=BG2, rowheight=26, borderwidth=0, font=(FONT, 10))
        s.configure("Treeview.Heading", background=BG3, foreground=FG_DIM,
                    borderwidth=0, font=(FONT, 9, "bold"))
        s.map("Treeview", background=[("selected", "#DCE5E8")],
              foreground=[("selected", FG)])
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=BG2, foreground=FG_DIM,
                    padding=(14, 8), font=(FONT, 10))
        s.map("TNotebook.Tab", background=[("selected", BG2)],
              foreground=[("selected", ACCENT)])
        s.configure("TCombobox", fieldbackground=BG2, background=BG3,
                    foreground=FG, arrowcolor=FG_DIM)
        self.root.option_add("*TCombobox*Listbox.background", BG2)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        s.configure("Horizontal.TProgressbar", background=ACCENT,
                    troughcolor=BG3, borderwidth=0)

    def _btn(self, parent, text, cmd, color=ACCENT, fg="#fff", padx=10):
        b = tk.Label(parent, text=text, bg=color, fg=fg, padx=padx, pady=6,
                     cursor="hand2", font=(FONT, 9), relief="flat")
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.config(relief="solid", bd=1))
        b.bind("<Leave>", lambda e: b.config(relief="flat", bd=0))
        return b

    # ------------------------------------------------------------------
    # 顶栏：行业选择 + 定期开关
    # ------------------------------------------------------------------
    def _build_ui(self):
        head = tk.Frame(self.root, bg=BG2, highlightbackground=BORDER,
                        highlightthickness=1)
        head.pack(fill="x", padx=14, pady=(12, 7))
        brand = tk.Frame(head, bg=BG2)
        brand.pack(side="left", padx=(14, 10), pady=8)
        tk.Label(brand, text="IntDog", bg=BG2, fg=FG,
                 font=(FONT, 15, "bold")).pack(anchor="w")
        tk.Label(brand, text="行业情报工作台", bg=BG2, fg=FG_DIM,
                 font=(FONT, 8)).pack(anchor="w")

        tk.Label(head, text="行业", bg=BG2, fg=FG_DIM, font=(FONT, 9)).pack(
            side="left", padx=(18, 4))
        self.ind_var = tk.StringVar()
        self.ind_cb = ttk.Combobox(head, textvariable=self.ind_var, width=16,
                                   state="readonly")
        self.ind_cb.pack(side="left")
        self.ind_cb.bind("<<ComboboxSelected>>", lambda e: self._on_industry())

        # 定期开关
        self.toggle_btn = tk.Label(head, text="", bg=BG3, fg=FG, padx=12,
                                   pady=6, cursor="hand2", font=(FONT, 9, "bold"))
        self.toggle_btn.pack(side="left", padx=16)
        self.toggle_btn.bind("<Button-1>", lambda e: self._toggle_periodic())
        self.sched_lbl = tk.Label(head, text="", bg=BG2, fg=FG_DIM, font=(FONT, 8))
        self.sched_lbl.pack(side="left")

        self._btn(head, "初始化行业研究", self._open_bootstrap_dialog,
                  color=ACCENT, fg="#FFFFFF", padx=14).pack(side="right", padx=(8, 14))
        self._btn(head, "⟳", self._refresh_all, color=BG3, fg=FG).pack(side="right", padx=(6, 0))
        self._btn(head, "打开数据目录", lambda: open_path(str(self.data_root)),
                  color=BG3, fg=FG).pack(side="right")

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=12, pady=(4, 8))
        self._build_daily_tab()
        self._build_knowledge_tab()
        self._build_period_tab()
        self._build_research_tab()
        self._build_sources_tab()
        self._build_reports_tab()
        self._build_statusbar()

    # ------------------------------------------------------------------
    # 行业与开关
    # ------------------------------------------------------------------
    def _reload_industries(self):
        self._inds = dataio.list_industries(self.data_root)
        names = [i["folder"] for i in self._inds]
        self.ind_cb.config(values=names)
        if names and not self.ind_var.get():
            self.ind_cb.current(0)
        self._on_industry()

    def _on_industry(self):
        self.folder = self.ind_var.get() or None
        if not self.folder:
            return
        self._update_toggle()
        self._refresh_all()

    def _open_bootstrap_dialog(self):
        """行业选择后，用严格的“来源→产业链→实体”顺序连接 Agent。"""
        win = tk.Toplevel(self.root)
        win.title("初始化行业研究")
        win.geometry("720x650")
        win.minsize(660, 590)
        win.resizable(True, True)
        win.configure(bg=BG)
        win.transient(self.root)
        win.grab_set()
        win.bind("<Escape>", lambda _event: win.destroy())

        card = tk.Frame(win, bg=BG2, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="both", expand=True, padx=20, pady=20)
        tk.Label(card, text="来源优先的行业研究", bg=BG2, fg=FG,
                 font=(FONT, 15, "bold")).pack(anchor="w", padx=18, pady=(18, 3))
        tk.Label(card, text="先建立可信、全面且中外平衡的信息源地图；通过门槛后才研究产业链和实体。",
                 bg=BG2, fg=FG_DIM, font=(FONT, 9), wraplength=620,
                 justify="left").pack(anchor="w", padx=18)

        form = tk.Frame(card, bg=BG2)
        form.pack(fill="x", padx=18, pady=(18, 8))
        tk.Label(form, text="行业名称", bg=BG2, fg=FG_DIM, font=(FONT, 9)).grid(
            row=0, column=0, sticky="w", pady=6)
        industry_var = tk.StringVar(value=self.folder or "")
        tk.Entry(form, textvariable=industry_var, bg=BG, fg=FG, insertbackground=FG,
                 relief="flat", font=(FONT, 10), width=34).grid(
            row=0, column=1, sticky="ew", padx=(12, 0), ipady=6)
        tk.Label(form, text="执行方式", bg=BG2, fg=FG_DIM, font=(FONT, 9)).grid(
            row=1, column=0, sticky="w", pady=6)
        mode_var = tk.StringVar(value="Codex 套餐（推荐）")
        mode = ttk.Combobox(form, textvariable=mode_var, state="readonly", width=31,
                            values=["Codex 套餐（推荐）", "生成 Agent 任务包",
                                    "OpenAI API",
                                    "DeepSeek API", "Qwen API", "Azure OpenAI"])
        mode.grid(row=1, column=1, sticky="ew", padx=(12, 0))
        form.columnconfigure(1, weight=1)

        steps = tk.Frame(card, bg=BG)
        steps.pack(fill="x", padx=18, pady=8)
        step_labels = []
        for index, text in enumerate(("发现并审计信息源", "基于合格来源重建产业链", "按产业链发现实体"), 1):
            label = tk.Label(steps, text=f"{index}  {text}", bg=BG, fg=FG_DIM,
                             anchor="w", padx=10, pady=7, font=(FONT, 9))
            label.pack(fill="x", pady=1)
            step_labels.append(label)

        progress = ttk.Progressbar(card, mode="indeterminate")
        output = tk.Text(card, height=10, bg=BG, fg=FG_DIM, relief="flat",
                         font=("Consolas", 8), wrap="word", padx=8, pady=6)
        output.pack(fill="both", expand=True, padx=18, pady=(5, 8))
        output.insert("end", "等待开始。Codex 套餐模式使用本机 ChatGPT 登录，无需 API Key。\n")
        output.config(state="disabled")

        actions = tk.Frame(card, bg=BG2)
        actions.pack(fill="x", padx=18, pady=(0, 18))

        def log(line):
            if not output.winfo_exists():
                return
            for index, label in enumerate(step_labels, 1):
                if f"[{index}/3]" in line:
                    label.config(bg="#DCE6E8", fg=ACCENT,
                                 font=(FONT, 9, "bold"))
            output.config(state="normal")
            output.insert("end", line.rstrip() + "\n")
            output.see("end")
            output.config(state="disabled")

        def finish(code):
            if not win.winfo_exists():
                return
            progress.stop(); progress.pack_forget()
            start_btn.config(text="重试", state="normal")
            cancel_btn.config(state="normal")
            if code == 0:
                log("完成：成果仍标记为草稿，需人工复核。")
                self._reload_industries(); self._set_status("行业研究初始化完成")
            else:
                log("失败：请查看上方错误；未通过门槛的下游阶段不会执行。")

        def run_worker(command):
            try:
                proc = subprocess.Popen(command, cwd=str(self._search_dir()),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                    encoding="utf-8", errors="replace",
                    creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0))
                for line in proc.stdout:
                    self.root.after(0, lambda value=line: log(value))
                code = proc.wait()
            except OSError as exc:
                self.root.after(0, lambda: log(f"启动失败：{exc}")); code = 1
            self.root.after(0, lambda: finish(code))

        def start():
            industry = industry_var.get().strip()
            if not industry:
                messagebox.showwarning("缺少行业", "请输入要研究的行业名称。", parent=win)
                return
            provider = {"Codex 套餐（推荐）": "codex", "OpenAI API": "openai",
                        "DeepSeek API": "deepseek",
                        "Qwen API": "qwen", "Azure OpenAI": "azure"}.get(mode_var.get())
            command = [sys.executable, "-u", "-m", "src.main", "bootstrap-industry",
                       "--industry", industry]
            if provider:
                command.extend(["--provider", provider])
            start_btn.config(text="正在初始化…", state="disabled")
            cancel_btn.config(state="disabled")
            progress.pack(fill="x", padx=18, pady=(0, 5), before=output); progress.start(12)
            log("开始：信息源门槛 → 产业链门槛 → 实体覆盖门槛")
            threading.Thread(target=run_worker, args=(command,), daemon=True).start()

        cancel_btn = tk.Button(actions, text="取消", command=win.destroy, bg=BG3, fg=FG,
                               relief="flat", padx=14, pady=6, font=(FONT, 9))
        cancel_btn.pack(side="right")
        start_btn = tk.Button(actions, text="开始初始化", command=start, bg=ACCENT,
                              fg="#FFFFFF", activebackground=CYAN, relief="flat",
                              padx=16, pady=6, font=(FONT, 9, "bold"))
        start_btn.pack(side="right", padx=(0, 8))

        def center_dialog():
            if not win.winfo_exists():
                return
            win.update_idletasks()
            width = min(760, max(660, win.winfo_reqwidth()))
            height = min(700, max(590, win.winfo_reqheight()))
            x = max(0, self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2)
            y = max(0, self.root.winfo_rooty() + (self.root.winfo_height() - height) // 2)
            win.geometry(f"{width}x{height}+{x}+{y}")

        win.after_idle(center_dialog)

    def _update_toggle(self):
        ctrl = dataio.read_control(self.data_root, self.folder)
        en = ctrl.get("periodic_enabled", False)
        self.toggle_btn.config(
            text=("● 定期更新：开" if en else "○ 定期更新：关"),
            bg=(GREEN if en else BG3), fg=("#0b1a12" if en else FG))

    def _toggle_periodic(self):
        if not self.folder:
            return
        ctrl = dataio.read_control(self.data_root, self.folder)
        new = not ctrl.get("periodic_enabled", False)
        dataio.set_periodic(self.data_root, self.folder, new)
        self._update_toggle()
        self._set_status(f"{self.folder} 定期更新已{'开启' if new else '关闭'}")
        self._reload_industries_silent()

    def _reload_industries_silent(self):
        self._inds = dataio.list_industries(self.data_root)

    # ------------------------------------------------------------------
    # 标签1：每日情报（卡片：标题+abstract+链接，可删；搜索/分页/排序）
    # ------------------------------------------------------------------
    PAGE_SIZE = 30   # 每日情报每屏卡片数（百级条目全渲染会卡）

    def _build_daily_tab(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text="  每日情报  ")

        # 第一行：类别筛选（带条数）
        bar = tk.Frame(tab, bg=BG)
        bar.pack(fill="x", padx=8, pady=(8, 2))
        cats = [("all", "全部", FG)] + [(k, v[0], v[1]) for k, v in CAT_META.items()]
        self._cat_btns = {}
        for key, label, color in cats:
            b = tk.Label(bar, text=label, bg=BG3, fg=color, padx=10, pady=3,
                         cursor="hand2", font=(FONT, 9))
            b.pack(side="left", padx=(0, 5))
            b.bind("<Button-1>", lambda e, k=key: self._set_cat(k))
            self._cat_btns[key] = b

        # 第二行：日期 + 搜索 + 排序 + 计数
        bar2 = tk.Frame(tab, bg=BG)
        bar2.pack(fill="x", padx=8, pady=(2, 4))
        tk.Label(bar2, text="日期", bg=BG, fg=FG_DIM, font=(FONT, 9)).pack(side="left")
        self.date_var = tk.StringVar(value="最近一天")
        self.date_cb = ttk.Combobox(bar2, textvariable=self.date_var, width=12,
                                    state="readonly")
        self.date_cb.pack(side="left", padx=(4, 14))
        self.date_cb.bind("<<ComboboxSelected>>", lambda e: self._on_date())

        tk.Label(bar2, text="搜索", bg=BG, fg=FG_DIM, font=(FONT, 9)).pack(side="left")
        self.search_var = tk.StringVar()
        se = tk.Entry(bar2, textvariable=self.search_var, bg=BG2, fg=FG,
                      insertbackground=FG, relief="flat", width=20,
                      font=(FONT, 9))
        se.pack(side="left", padx=(4, 4), ipady=2)
        se.bind("<Return>", lambda e: self._refresh_daily())
        self._btn(bar2, "🔍", self._refresh_daily, color=BG3, fg=FG,
                  padx=8).pack(side="left")
        self._btn(bar2, "✕", self._clear_search, color=BG3, fg=FG_DIM,
                  padx=8).pack(side="left", padx=(4, 14))

        tk.Label(bar2, text="排序", bg=BG, fg=FG_DIM, font=(FONT, 9)).pack(side="left")
        self.sort_var = tk.StringVar(value="默认")
        scb = ttk.Combobox(bar2, textvariable=self.sort_var, width=8,
                           state="readonly", values=["默认", "可信度"])
        scb.pack(side="left", padx=(4, 0))
        scb.bind("<<ComboboxSelected>>", lambda e: self._refresh_daily())

        tk.Label(bar2, text="网站", bg=BG, fg=FG_DIM, font=(FONT, 9)).pack(
            side="left", padx=(14, 4))
        self.origin_var = tk.StringVar(value="全部")
        ocb = ttk.Combobox(bar2, textvariable=self.origin_var, width=9,
                           state="readonly", values=["全部", "中文网站", "外文网站"])
        ocb.pack(side="left")
        ocb.bind("<<ComboboxSelected>>", lambda e: self._refresh_daily())

        self.count_lbl = tk.Label(bar2, text="", bg=BG, fg=FG_DIM, font=(FONT, 9))
        self.count_lbl.pack(side="right")

        self.daily_scroll = ScrollFrame(tab, bg=BG)
        self.daily_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 6))

    def _clear_search(self):
        self.search_var.set("")
        self._refresh_daily()

    def _set_cat(self, key):
        self.daily_cat = key
        for k, b in self._cat_btns.items():
            b.config(relief=("sunken" if k == key else "flat"))
        self._refresh_daily()

    def _on_date(self):
        v = self.date_var.get()
        self.daily_date = None if v == "最近一天" else v
        self._refresh_daily()

    def _refresh_dates(self):
        dates = dataio.list_daily_dates(self.data_root, self.folder)
        self.date_cb.config(values=["最近一天"] + dates)

    def _load_more(self):
        self._daily_shown += self.PAGE_SIZE
        self._refresh_daily(reset_page=False)

    def _refresh_daily(self, reset_page=True):
        if not self.folder:
            return
        if reset_page:
            self._daily_shown = self.PAGE_SIZE
        # 一次取全天全部类别：用于类别计数 + 本地过滤（避免多次读盘）
        all_items = dataio.list_daily(self.data_root, self.folder,
                                      date=self.daily_date)
        counts = {}
        for it in all_items:
            c = it.get("_cat") or it.get("category", "")
            counts[c] = counts.get(c, 0) + 1
        self._cat_btns["all"].config(text=f"全部({len(all_items)})")
        for k, (lab, _c) in CAT_META.items():
            self._cat_btns[k].config(text=f"{lab}({counts.get(k, 0)})")

        # 类别过滤
        items = all_items
        if self.daily_cat != "all":
            items = [it for it in items
                     if (it.get("_cat") or it.get("category")) == self.daily_cat]
        origin_choice = {"中文网站": "china", "外文网站": "foreign"}.get(
            self.origin_var.get())
        if origin_choice:
            items = [it for it in items if dataio.source_origin(it) == origin_choice]
        # 关键词过滤（标题 + 摘要）
        kw = self.search_var.get().strip().lower()
        if kw:
            items = [it for it in items
                     if kw in (str(it.get("title", "")) + " "
                               + str(it.get("abstract", ""))).lower()]
        # 排序（默认保持源顺序；可信度=高→低，同级按独立来源数）
        if self.sort_var.get() == "可信度":
            items = sorted(items, key=lambda x: (-x.get("credibility", 0),
                                                 -x.get("source_count", 1)))

        self.daily_scroll.clear()
        if not items:
            hint = ("没有匹配的情报，换个关键词试试" if kw else
                    "（暂无数据。先在 DomainIntelSearch 运行 crawl-daily，"
                    "或开启右上角「定期更新」）")
            tk.Label(self.daily_scroll.inner, text=hint,
                     bg=BG, fg=FG_DIM, font=(FONT, 11)).pack(pady=30)
            self.count_lbl.config(text="0 条")
            return
        shown = items[:self._daily_shown]
        for it in shown:
            self._daily_card(it)
        if len(items) > len(shown):
            self._btn(self.daily_scroll.inner,
                      f"▼ 加载更多（还有 {len(items) - len(shown)} 条）",
                      self._load_more, color=BG3, fg=ACCENT,
                      padx=16).pack(pady=10)
        china_count = sum(1 for it in all_items if dataio.source_origin(it) == "china")
        foreign_count = sum(1 for it in all_items if dataio.source_origin(it) == "foreign")
        self.count_lbl.config(text=(f"显示 {len(shown)}/{len(items)} 条 · "
                                    f"中文 {china_count} / 外文 {foreign_count}"))

    def _daily_card(self, it):
        cat = it.get("_cat") or it.get("category", "")
        label, color = CAT_META.get(cat, (cat, FG))
        card = tk.Frame(self.daily_scroll.inner, bg=BG2,
                        highlightbackground=BG3, highlightthickness=1)
        card.pack(fill="x", pady=4, padx=2)

        top = tk.Frame(card, bg=BG2)
        top.pack(fill="x", padx=10, pady=(8, 0))
        tk.Label(top, text=label, bg=BG3, fg=color, padx=6, pady=1,
                 font=(FONT, 8)).pack(side="left")
        # 可信度徽标（多源交叉验证产出：高/中/低 + 独立来源数 + 是否被印证）
        cred = it.get("credibility_label")
        if cred:
            sc = it.get("source_count", 1)
            ccolor = {"高": GREEN, "中": AMBER}.get(cred, FG_DIM)
            mark = "✓" if it.get("verified") else ""
            cbtn = tk.Label(top, text=f"可信度{cred}{mark} 源{sc}", bg=BG3,
                            fg=ccolor, padx=6, pady=1, font=(FONT, 8),
                            cursor="hand2")
            cbtn.pack(side="left", padx=(6, 0))
            cbtn.bind("<Button-1>", lambda e, x=it: self._show_refs(x))
        # 标题（点击打开链接）
        title = tk.Label(top, text=it.get("title", ""), bg=BG2, fg=FG,
                         anchor="w", justify="left", wraplength=860,
                         font=(FONT, 11, "bold"), cursor="hand2")
        title.pack(side="left", fill="x", expand=True, padx=8)
        title.bind("<Button-1>", lambda e: open_path(it.get("url", "")))
        self._btn(top, "删除", lambda: self._del_daily(it), color=BG3,
                  fg=RED, padx=8).pack(side="right")
        self._btn(top, "打开 ↗", lambda: open_path(it.get("url", "")),
                  color=BG3, fg=ACCENT, padx=8).pack(side="right", padx=(0, 5))

        # abstract
        ab = it.get("abstract") or it.get("summary") or ""
        if ab:
            tk.Label(card, text=ab, bg=BG2, fg=FG_DIM, anchor="w",
                     justify="left", wraplength=940,
                     font=(FONT, 9)).pack(fill="x", padx=10, pady=(3, 0))
        # 链接
        origin_label = "中文网站" if dataio.source_origin(it) == "china" else "外文网站"
        meta = (f"{origin_label} · {it.get('source','')} · {it.get('date','')} · "
                f"🔗 {it.get('url','')}")
        link = tk.Label(card, text=meta, bg=BG2, fg=ACCENT, anchor="w",
                        justify="left", wraplength=940, font=(FONT, 8),
                        cursor="hand2")
        link.pack(fill="x", padx=10, pady=(2, 8))
        link.bind("<Button-1>", lambda e: open_path(it.get("url", "")))

    def _del_daily(self, it):
        if not messagebox.askyesno("删除确认",
                                   f"删除该条「{it.get('title','')[:40]}」？"):
            return
        ok = dataio.delete_daily_item(self.data_root, self.folder,
                                      it.get("_date"), it.get("_cat"),
                                      (it.get("url") or it.get("title") or "")[:200])
        self._set_status("已删除" if ok else "删除失败")
        self._refresh_daily()

    def _show_refs(self, it):
        """弹窗展示该条目的交叉验证信息（互相印证的来源）."""
        refs = it.get("references") or []
        cred = it.get("credibility", "-")
        label = it.get("credibility_label", "-")
        sc = it.get("source_count", 1)
        lines = [f"可信度：{cred}（{label}） · 独立来源 {sc} 家", ""]
        if not refs:
            lines.append("暂无其它独立来源印证（单一来源，建议自行核实）。")
        else:
            lines.append("以下独立来源报道了同一事件：")
            for r in refs:
                lines.append(f"  [{r.get('source','')}] {r.get('title','')}")
                lines.append(f"    {r.get('url','')}")
        messagebox.showinfo("交叉验证 · 溯源", "\n".join(lines))

    # ------------------------------------------------------------------
    # 标签2：知识结构（三层树，实体可删）
    # ------------------------------------------------------------------
    def _build_knowledge_tab(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text="  知识结构  ")
        bar = tk.Frame(tab, bg=BG)
        bar.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(bar, text="行业 → 产业链 → 实体（企业 / 高校研究组）",
                 bg=BG, fg=FG_DIM, font=(FONT, 9)).pack(side="left")
        self._btn(bar, "⟳ 刷新", self._refresh_knowledge,
                  color=BG3, fg=FG).pack(side="right")
        self.k_scroll = ScrollFrame(tab, bg=BG)
        self.k_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 6))

    def _refresh_knowledge(self):
        if not self.folder:
            return
        k = dataio.read_knowledge(self.data_root, self.folder)
        self.k_scroll.clear()
        ind = k["industry"]
        tk.Label(self.k_scroll.inner,
                 text=f"行业：{ind.get('name', self.folder)}",
                 bg=BG, fg=FG, font=(FONT, 13, "bold")).pack(anchor="w", pady=(6, 8))
        if not k["chains"]:
            tk.Label(self.k_scroll.inner,
                     text="（暂无产业链/实体。用 DomainIntelSearch 的 knowledge 命令添加）",
                     bg=BG, fg=FG_DIM, font=(FONT, 10)).pack(anchor="w")
        for c in k["chains"]:
            cf = tk.Frame(self.k_scroll.inner, bg=BG2,
                          highlightbackground=BG3, highlightthickness=1)
            cf.pack(fill="x", pady=4, padx=2)
            tk.Label(cf, text=f"◈ 产业链：{c['name']}（{len(c.get('entities', []))} 实体）",
                     bg=BG2, fg=CYAN, font=(FONT, 11, "bold")).pack(
                anchor="w", padx=10, pady=(8, 2))
            for e in c.get("entities", []):
                row = tk.Frame(cf, bg=BG2)
                row.pack(fill="x", padx=10, pady=2)
                type_labels = {"company": "企业", "research_group": "研究机构",
                               "regulator": "监管", "association": "协会",
                               "person": "人物", "technology": "技术",
                               "product": "产品", "facility": "设施"}
                tag = type_labels.get(e.get("type"), "实体")
                tcolor = ACCENT if e.get("type") == "company" else PURPLE
                tk.Label(row, text=tag, bg=BG3, fg=tcolor, padx=6, pady=1,
                         font=(FONT, 8)).pack(side="left")
                nm = tk.Label(row, text=f"{e.get('name')}  {e.get('country','')}",
                              bg=BG2, fg=FG, font=(FONT, 10))
                nm.pack(side="left", padx=8)
                if e.get("url"):
                    self._btn(row, "↗", lambda u=e["url"]: open_path(u),
                              color=BG3, fg=ACCENT, padx=6).pack(side="left")
                self._btn(row, "删除", lambda i=e["id"], n=e["name"]: self._del_entity(i, n),
                          color=BG3, fg=RED, padx=6).pack(side="right")
                if e.get("description"):
                    tk.Label(cf, text=e["description"], bg=BG2, fg=FG_DIM,
                             anchor="w", wraplength=900,
                             font=(FONT, 8)).pack(fill="x", padx=30, pady=(0, 4))
            tk.Frame(cf, bg=BG2, height=6).pack()

    def _del_entity(self, eid, name):
        if not messagebox.askyesno("删除确认", f"删除实体「{name}」？"):
            return
        ok = dataio.delete_entity(self.data_root, self.folder, eid)
        self._set_status("已删除实体" if ok else "删除失败")
        self._refresh_knowledge()

    # ------------------------------------------------------------------
    # 标签3：定期产物（周/月/季，可删）
    # ------------------------------------------------------------------
    def _build_period_tab(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text="  定期产物  ")
        bar = tk.Frame(tab, bg=BG)
        bar.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(bar, text="每周行业总结 / 每月产业分析 / 每季财报分析",
                 bg=BG, fg=FG_DIM, font=(FONT, 9)).pack(side="left")
        self._btn(bar, "⟳ 刷新", self._refresh_period, color=BG3, fg=FG).pack(side="right")
        self.p_scroll = ScrollFrame(tab, bg=BG)
        self.p_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 6))

    def _refresh_period(self):
        if not self.folder:
            return
        self.p_scroll.clear()
        empty = True
        for kind, label in PERIOD_META.items():
            items = dataio.list_period(self.data_root, self.folder, kind)
            tk.Label(self.p_scroll.inner, text=f"■ {label}",
                     bg=BG, fg=CYAN, font=(FONT, 12, "bold")).pack(
                anchor="w", pady=(10, 4))
            if not items:
                tk.Label(self.p_scroll.inner, text="  （暂无）",
                         bg=BG, fg=FG_DIM, font=(FONT, 9)).pack(anchor="w")
                continue
            empty = False
            for it in items:
                self._period_card(kind, it)
        if empty:
            tk.Label(self.p_scroll.inner,
                     text="开启右上角「定期更新」后，系统会按周期自动生成。",
                     bg=BG, fg=FG_DIM, font=(FONT, 10)).pack(pady=10)

    def _period_card(self, kind, it):
        card = tk.Frame(self.p_scroll.inner, bg=BG2,
                        highlightbackground=BG3, highlightthickness=1)
        card.pack(fill="x", pady=3, padx=2)
        top = tk.Frame(card, bg=BG2)
        top.pack(fill="x", padx=10, pady=6)
        tk.Label(top, text=it.get("_key", ""), bg=BG2, fg=FG,
                 font=(FONT, 10, "bold")).pack(side="left")
        tk.Label(top, text=it.get("generated_at", ""), bg=BG2, fg=FG_DIM,
                 font=(FONT, 8)).pack(side="left", padx=10)
        self._btn(top, "删除", lambda: self._del_period(kind, it), color=BG3,
                  fg=RED, padx=8).pack(side="right")
        self._btn(top, "打开 ↗", lambda: open_path(it.get("_file", "")),
                  color=BG3, fg=ACCENT, padx=8).pack(side="right", padx=(0, 5))
        summ = it.get("summary", "")
        if summ:
            tk.Label(card, text=summ, bg=BG2, fg=FG_DIM, anchor="w",
                     wraplength=900, font=(FONT, 9)).pack(fill="x", padx=10, pady=(0, 6))

    def _del_period(self, kind, it):
        if not messagebox.askyesno("删除确认",
                                   f"删除{PERIOD_META[kind]}「{it.get('_key')}」？"
                                   f"\n（移入回收站，可恢复）"):
            return
        ok = dataio.delete_period(self.data_root, self.folder, kind, it.get("_key"))
        self._set_status("已删除（移入回收站）" if ok else "删除失败")
        self._refresh_period()

    # ------------------------------------------------------------------
    # 标签：研究助手（竞争格局 / 事件影响 / 深度报告）
    # ------------------------------------------------------------------
    def _build_research_tab(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text="  研究助手  ")
        bar = tk.Frame(tab, bg=BG)
        bar.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(bar, text="竞争格局 · 事件影响分析 · 深度研究报告（由 DomainIntelSearch 产出）",
                 bg=BG, fg=FG_DIM, font=(FONT, 9)).pack(side="left")
        self._btn(bar, "⟳ 刷新", self._refresh_research,
                  color=BG3, fg=FG).pack(side="right")
        self.r_scroll = ScrollFrame(tab, bg=BG)
        self.r_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 6))

    def _refresh_research(self):
        if not self.folder:
            return
        self.r_scroll.clear()
        self._research_landscape()
        self._research_impact()
        self._research_deep()

    # ---- 竞争格局 ----
    def _research_landscape(self):
        data = dataio.read_landscape(self.data_root, self.folder)
        ls = data["landscape"]
        tk.Label(self.r_scroll.inner,
                 text="■ 竞争格局（四类玩家，跟踪份额/地位变化）",
                 bg=BG, fg=CYAN, font=(FONT, 12, "bold")).pack(anchor="w", pady=(4, 2))
        if not ls:
            tk.Label(self.r_scroll.inner,
                     text="  （暂无。在 DomainIntelSearch 运行 landscape 命令生成）",
                     bg=BG, fg=FG_DIM, font=(FONT, 9)).pack(anchor="w")
            return
        tiers = ls.get("tiers", {})
        labels = ls.get("labels", {})
        tcolors = {"leader": GREEN, "challenger": ACCENT,
                   "emerging": AMBER, "declining": RED}
        for key in ("leader", "challenger", "emerging", "declining"):
            entries = tiers.get(key, [])
            row = tk.Frame(self.r_scroll.inner, bg=BG2,
                           highlightbackground=BG3, highlightthickness=1)
            row.pack(fill="x", pady=2, padx=2)
            tk.Label(row, text=f"{labels.get(key, key)}（{len(entries)}）",
                     bg=BG2, fg=tcolors[key],
                     font=(FONT, 10, "bold")).pack(anchor="w", padx=10, pady=(6, 2))
            txt = ("  ".join(f"{e['name']}（{e.get('mentions',0)}次提及）"
                             for e in entries)) or "（无）"
            tk.Label(row, text=txt, bg=BG2, fg=FG, wraplength=920, anchor="w",
                     justify="left", font=(FONT, 9)).pack(fill="x", padx=10,
                                                          pady=(0, 6))
        tk.Label(self.r_scroll.inner,
                 text=f"  更新于 {ls.get('generated_at','')} · 历史快照 "
                      f"{len(data.get('history', []))} 天",
                 bg=BG, fg=FG_DIM, font=(FONT, 8)).pack(anchor="w", pady=(0, 8))

    # ---- 事件影响 ----
    def _research_impact(self):
        tk.Label(self.r_scroll.inner,
                 text="■ 事件影响分析（事件 → 受影响公司 / 供应链 / 论文 / 政策）",
                 bg=BG, fg=CYAN, font=(FONT, 12, "bold")).pack(anchor="w", pady=(6, 2))
        analyses = dataio.list_impact_analyses(self.data_root, self.folder)
        events = dataio.read_impact_events(self.data_root, self.folder).get("events", [])

        if analyses:
            tk.Label(self.r_scroll.inner, text=f"已分析 {len(analyses)} 个事件（点「查看」看关联结果）：",
                     bg=BG, fg=FG_DIM, font=(FONT, 9)).pack(anchor="w", pady=(2, 2))
            for a in analyses:
                row = tk.Frame(self.r_scroll.inner, bg=BG2,
                               highlightbackground=BG3, highlightthickness=1)
                row.pack(fill="x", pady=2, padx=2)
                tk.Label(row, text=a["event"], bg=BG2, fg=FG,
                         font=(FONT, 10, "bold")).pack(side="left", padx=10, pady=6)
                tk.Label(row,
                         text=f"公司{a['companies']} · 产业链{a['chains']} · "
                              f"论文{a['papers']} · 政策{a['policies']}",
                         bg=BG2, fg=FG_DIM, font=(FONT, 8)).pack(side="left", padx=8)
                self._btn(row, "查看", lambda s=a["slug"]: self._show_impact(s),
                          color=BG3, fg=ACCENT, padx=8).pack(side="right", padx=6)
        else:
            tk.Label(self.r_scroll.inner,
                     text="  （暂无分析。在 DomainIntelSearch 运行 impact --event \"事件\" 生成）",
                     bg=BG, fg=FG_DIM, font=(FONT, 9)).pack(anchor="w")

        if events:
            tk.Label(self.r_scroll.inner,
                     text=f"检测到的最新行业事件（{len(events)} 条，前 8 条）：",
                     bg=BG, fg=FG_DIM, font=(FONT, 9)).pack(anchor="w", pady=(8, 2))
            for e in events[:8]:
                row = tk.Frame(self.r_scroll.inner, bg=BG2)
                row.pack(fill="x", pady=1, padx=2)
                cl = e.get("credibility_label", "低")
                cc = {"高": GREEN, "中": AMBER}.get(cl, FG_DIM)
                tk.Label(row, text=f"{cl}·源{e.get('source_count',1)}",
                         bg=BG3, fg=cc, padx=5, pady=1,
                         font=(FONT, 8)).pack(side="left", padx=(6, 6))
                t = tk.Label(row, text=e.get("title", "")[:70], bg=BG2, fg=FG,
                             anchor="w", font=(FONT, 9), cursor="hand2")
                t.pack(side="left", fill="x", expand=True)
                t.bind("<Button-1>", lambda ev, u=e.get("url", ""): open_path(u))

        # 详情区（点「查看」后填充）
        self._impact_detail = tk.Text(self.r_scroll.inner, bg=BG2, fg=FG,
                                      relief="flat", wrap="word", height=14,
                                      font=(FONT, 9), padx=10, pady=8,
                                      state="disabled")

    def _show_impact(self, slug):
        data = dataio.read_impact(self.data_root, self.folder, slug)
        if not data:
            return
        L = [f"事件：{data.get('event','')}",
             f"分析时间：{data.get('generated_at','')}", ""]
        L.append("【受影响公司】")
        for d in data.get("affected_detail", []):
            L.append(f"  · {d['name']} — {d['reason']}")
        if not data.get("affected_detail"):
            L.append("  （未命中知识库实体——可先用 knowledge 命令补充实体）")
        L.append("")
        L.append("【关联产业链】" + ("、".join(data.get("affected_chains", [])) or "（无）"))
        L.append("")
        L.append(f"【相关政策】{len(data.get('related_policies', []))} 条")
        for p in data.get("related_policies", [])[:6]:
            L.append(f"  · {p['title']}")
            L.append(f"    {p.get('source','')} {p.get('url','')}")
        L.append("")
        L.append(f"【相关论文】{len(data.get('related_papers', []))} 条")
        for p in data.get("related_papers", [])[:6]:
            L.append(f"  · {p['title']}")
            L.append(f"    {p.get('url','')}")
        L.append("")
        L.append("※ 叙事性影响分析（影响等级/传导路径/启示）见同目录 analysis_task.json，"
                 "交给任意 agent 执行后回写 analysis.md。")
        w = self._impact_detail
        w.config(state="normal")
        w.delete("1.0", "end")
        w.insert("1.0", "\n".join(L))
        w.config(state="disabled")
        if not w.winfo_ismapped():
            w.pack(fill="x", padx=2, pady=(6, 4))

    # ---- 深度研究报告 ----
    def _research_deep(self):
        tk.Label(self.r_scroll.inner,
                 text="■ 深度研究报告（季度 / 产业链 / 竞争格局 / 市场）",
                 bg=BG, fg=CYAN, font=(FONT, 12, "bold")).pack(anchor="w", pady=(6, 2))
        tasks = dataio.read_deep_tasks(self.data_root, self.folder)
        done = {Path(r["path"]).name
                for r in dataio.list_deep_reports(self.data_root, self.folder)}
        if not tasks:
            tk.Label(self.r_scroll.inner,
                     text="  （暂无。在 DomainIntelSearch 运行 deep-reports 命令生成任务包）",
                     bg=BG, fg=FG_DIM, font=(FONT, 9)).pack(anchor="w")
            return
        for t in tasks:
            outfile = Path(t["output_file"]).name
            ready = outfile in done
            row = tk.Frame(self.r_scroll.inner, bg=BG2,
                           highlightbackground=BG3, highlightthickness=1)
            row.pack(fill="x", pady=2, padx=2)
            tk.Label(row, text=t["title"], bg=BG2, fg=FG,
                     font=(FONT, 10, "bold")).pack(side="left", padx=10, pady=6)
            tk.Label(row, text="✅ 已生成" if ready else "⏳ 待 agent 执行回写",
                     bg=BG2, fg=(GREEN if ready else FG_DIM),
                     font=(FONT, 8)).pack(side="left", padx=8)
            if ready:
                p = self.data_root / self.folder / t["output_file"]
                self._btn(row, "打开 ↗", lambda pp=str(p): open_path(pp),
                          color=BG3, fg=ACCENT, padx=8).pack(side="right", padx=6)
        tk.Label(self.r_scroll.inner,
                 text="  任务包 prompt 见 one_time/reports/deep_tasks.json；"
                      "把 prompt 交给任意 agent 执行，成品回写到 deep/ 目录。",
                 bg=BG, fg=FG_DIM, font=(FONT, 8)).pack(anchor="w", pady=(2, 8))

    # ------------------------------------------------------------------
    # 标签4：信息源
    # ------------------------------------------------------------------
    def _build_sources_tab(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text="  信息源  ")
        bar = tk.Frame(tab, bg=BG)
        bar.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(bar, text="该行业监控的信息源（由 DomainIntelSearch 信息源发现生成）",
                 bg=BG, fg=FG_DIM, font=(FONT, 9)).pack(side="left")
        self._btn(bar, "⟳ 刷新", self._refresh_sources, color=BG3, fg=FG).pack(side="right")
        self.s_scroll = ScrollFrame(tab, bg=BG)
        self.s_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 6))

    def _refresh_sources(self):
        if not self.folder:
            return
        src = dataio.read_sources(self.data_root, self.folder)
        self.s_scroll.clear()
        labels = {"official": "政府/监管/统计", "associations": "行业协会/标准组织",
                  "blogs": "博客", "platforms": "平台/社区", "self_media": "自媒体",
                  "news": "新闻媒体", "journals": "学术会议/期刊",
                  "financials": "公司财报", "finance": "金融资讯"}
        status = dataio.read_bootstrap_status(self.data_root, self.folder)
        if status:
            state_labels = {"waiting_for_agent": "等待 Agent", "ready_for_review": "待人工复核",
                            "blocked_by_source_gate": "来源门槛未通过",
                            "blocked_by_value_chain_gate": "产业链门槛未通过"}
            sf = tk.Frame(self.s_scroll.inner, bg=BG2, highlightbackground=BORDER,
                          highlightthickness=1)
            sf.pack(fill="x", pady=(6, 8), padx=2)
            tk.Label(sf, text="研究初始化", bg=BG2, fg=FG,
                     font=(FONT, 10, "bold")).pack(side="left", padx=10, pady=8)
            tk.Label(sf, text=state_labels.get(status.get("state"), status.get("state", "")),
                     bg=BG3, fg=AMBER, padx=8, pady=2,
                     font=(FONT, 8)).pack(side="left")
            audit = status.get("stages", {}).get("sources", {}).get("audit", {})
            if audit:
                tk.Label(sf, text=(f"{audit.get('total', 0)} 源 · "
                                  f"{audit.get('unique_domains', 0)} 域名 · "
                                  f"{audit.get('primary_count', 0)} 一手源"),
                         bg=BG2, fg=FG_DIM, font=(FONT, 8)).pack(side="right", padx=10)
                balance = audit.get("origin_counts", {})
                if balance:
                    tk.Label(sf, text=(f"中文 {balance.get('china', 0)} : "
                                      f"外文 {balance.get('foreign', 0)}"),
                             bg=BG2, fg=ACCENT, font=(FONT, 8, "bold")).pack(
                        side="right", padx=8)
        all_sources = [item for key in labels for item in (src.get(key, []) or [])]
        china_sources = sum(1 for item in all_sources if dataio.source_origin(item) == "china")
        foreign_sources = sum(1 for item in all_sources if dataio.source_origin(item) == "foreign")
        ratio = round(foreign_sources / china_sources, 2) if china_sources else "∞"
        balance_card = tk.Frame(self.s_scroll.inner, bg=BG2,
                                highlightbackground=BORDER, highlightthickness=1)
        balance_card.pack(fill="x", pady=(6, 8), padx=2)
        tk.Label(balance_card, text="中外来源结构", bg=BG2, fg=FG,
                 font=(FONT, 10, "bold")).pack(side="left", padx=10, pady=8)
        balance_ok = (isinstance(ratio, float) and 1.2 <= ratio <= 1.8)
        tk.Label(balance_card,
                 text=f"中文 {china_sources} : 外文 {foreign_sources}（外文/中文 {ratio}）",
                 bg=BG3, fg=(GREEN if balance_ok else AMBER), padx=8, pady=2,
                 font=(FONT, 8, "bold")).pack(side="right", padx=10)
        any_src = False
        for cat, label in labels.items():
            items = src.get(cat, [])
            tk.Label(self.s_scroll.inner, text=f"■ {label}（{len(items)}）",
                     bg=BG, fg=CYAN, font=(FONT, 11, "bold")).pack(anchor="w", pady=(8, 2))
            for s in items:
                any_src = True
                row = tk.Frame(self.s_scroll.inner, bg=BG2,
                               highlightbackground=BG3, highlightthickness=1)
                row.pack(fill="x", pady=2, padx=2)
                nm = tk.Label(row, text=s.get("name", ""), bg=BG2, fg=FG,
                              font=(FONT, 10), cursor="hand2")
                nm.pack(side="left", padx=10, pady=5)
                nm.bind("<Button-1>", lambda e, u=s.get("url", ""): open_path(u))
                origin = "中文" if dataio.source_origin(s) == "china" else "外文"
                tk.Label(row, text=origin, bg=BG3, fg=ACCENT, padx=5, pady=1,
                         font=(FONT, 8)).pack(side="left", padx=(0, 6))
                tk.Label(row, text=s.get("note", ""), bg=BG2, fg=FG_DIM,
                         font=(FONT, 8)).pack(side="left", padx=6)
                self._btn(row, "↗", lambda u=s.get("url", ""): open_path(u),
                          color=BG3, fg=ACCENT, padx=6).pack(side="right", padx=6)
        if not any_src:
            tk.Label(self.s_scroll.inner,
                     text="（暂无信息源。运行 init-industry 生成）",
                     bg=BG, fg=FG_DIM, font=(FONT, 10)).pack(pady=20)

    # ------------------------------------------------------------------
    # 标签5：行业报告
    # ------------------------------------------------------------------
    def _build_reports_tab(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text="  行业报告  ")
        bar = tk.Frame(tab, bg=BG)
        bar.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(bar, text="近五年趋势 / 近两年流行 / 近半年技术（one_time/reports）",
                 bg=BG, fg=FG_DIM, font=(FONT, 9)).pack(side="left")
        self._btn(bar, "⟳ 刷新", self._refresh_reports, color=BG3, fg=FG).pack(side="right")

        paned = tk.PanedWindow(tab, orient="horizontal", bg=BG, sashwidth=4,
                               borderwidth=0)
        paned.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        left = tk.Frame(paned, bg=BG2)
        self.rep_list = tk.Listbox(left, bg=BG2, fg=FG, relief="flat",
                                   font=(FONT, 10), selectbackground=BG3,
                                   activestyle="none", exportselection=False)
        self.rep_list.pack(fill="both", expand=True, padx=6, pady=6)
        self.rep_list.bind("<<ListboxSelect>>", lambda e: self._on_report())
        paned.add(left, width=280)
        right = tk.Frame(paned, bg=BG)
        self._btn(right, "外部打开 ↗", self._open_report, color=BG3,
                  fg=ACCENT).pack(anchor="e", pady=(0, 4))
        self.rep_text = tk.Text(right, bg=BG2, fg=FG, relief="flat", wrap="word",
                                font=(FONT, 10), padx=10, pady=8, state="disabled")
        self.rep_text.pack(fill="both", expand=True)
        paned.add(right)

    def _refresh_reports(self):
        if not self.folder:
            return
        self._reps = dataio.list_reports(self.data_root, self.folder)
        self.rep_list.delete(0, "end")
        for r in self._reps:
            self.rep_list.insert("end", f"{r['name']}  ({r['size']//1024}KB)")
        if not self._reps:
            self.rep_list.insert("end", "（暂无报告）")

    def _on_report(self):
        sel = self.rep_list.curselection()
        if not sel or sel[0] >= len(self._reps):
            return
        r = self._reps[sel[0]]
        self._cur_report = r
        self.rep_text.config(state="normal")
        self.rep_text.delete("1.0", "end")
        self.rep_text.insert("1.0", dataio.read_text(Path(r["path"])))
        self.rep_text.config(state="disabled")

    def _open_report(self):
        if getattr(self, "_cur_report", None):
            open_path(self._cur_report["path"])

    # ------------------------------------------------------------------
    # 状态栏 + 调度线程
    # ------------------------------------------------------------------
    def _build_statusbar(self):
        sb = tk.Frame(self.root, bg=BG2)
        sb.pack(fill="x", side="bottom")
        self.st = tk.Label(sb, text="就绪", bg=BG2, fg=FG_DIM, font=(FONT, 9))
        self.st.pack(side="left", padx=14, pady=5)

    def _set_status(self, msg):
        self.st.config(text=msg)

    def _refresh_all(self):
        if not self.folder:
            return
        self._refresh_dates()
        self._refresh_daily()
        self._refresh_knowledge()
        self._refresh_period()
        self._refresh_research()
        self._refresh_sources()
        self._refresh_reports()

    def _search_dir(self) -> Path:
        return self.data_root.parent / "DomainIntelSearch"

    def _start_scheduler(self):
        def loop():
            while not self._sched_stop.is_set():
                try:
                    self._sched_tick()
                except Exception as exc:
                    self.root.after(0, lambda msg=f"调度器错误: {type(exc).__name__}: {exc}":
                                    self._set_status(msg))
                self._sched_stop.wait(60)
        self._sched_thread = threading.Thread(target=loop, daemon=True)
        self._sched_thread.start()

    def _sched_tick(self):
        """检查所有行业，到期则触发对应周期抓取."""
        now = datetime.now()
        weekday_number = {"monday": 0, "tuesday": 1, "wednesday": 2,
                          "thursday": 3, "friday": 4, "saturday": 5,
                          "sunday": 6}
        for ind in dataio.list_industries(self.data_root):
            folder = ind["folder"]
            ctrl = dataio.read_control(self.data_root, folder)
            if not ctrl.get("periodic_enabled"):
                continue
            last = ctrl.get("last_run", {})
            today = now.strftime("%Y-%m-%d")
            iso = now.isocalendar()
            week = f"{iso[0]}-W{iso[1]:02d}"
            month = now.strftime("%Y-%m")
            quarter = f"{now.year}-Q{(now.month-1)//3+1}"
            try:
                hour, minute = (int(part) for part in
                                str(ctrl.get("daily_time", "08:00")).split(":", 1))
                after_daily_time = (now.hour, now.minute) >= (hour, minute)
            except (TypeError, ValueError):
                after_daily_time = True
            weekly_day = weekday_number.get(str(ctrl.get("weekly_day", "monday")).lower(), 0)
            try:
                monthly_day = max(1, min(28, int(ctrl.get("monthly_day", 1))))
            except (TypeError, ValueError):
                monthly_day = 1
            try:
                quarter_months = {int(value) for value in
                                  ctrl.get("quarterly_months", [1, 4, 7, 10])}
            except (TypeError, ValueError):
                quarter_months = {1, 4, 7, 10}
            jobs = []
            if after_daily_time and last.get("daily") != today:
                jobs.append(("daily", "crawl-daily", today))
            if (after_daily_time and now.weekday() >= weekly_day
                    and last.get("weekly") != week):
                jobs.append(("weekly", "crawl-weekly", week))
            if (after_daily_time and now.day >= monthly_day
                    and last.get("monthly") != month):
                jobs.append(("monthly", "crawl-monthly", month))
            if (after_daily_time and now.month in quarter_months
                    and now.day >= monthly_day and last.get("quarterly") != quarter):
                jobs.append(("quarterly", "crawl-quarterly", quarter))
            for kind, cmd, key in jobs:
                ok, detail = self._run_crawl(folder, cmd)
                state = {"state": "succeeded" if ok else "failed",
                         "finished_at": datetime.now().isoformat(timespec="seconds"),
                         "detail": detail[-2000:]}
                ctrl.setdefault("job_status", {})[kind] = state
                if ok:
                    ctrl.setdefault("last_run", {})[kind] = key
                dataio.write_json(self.data_root / folder / "control.json", ctrl)
                self.root.after(0, lambda f=folder, k=kind, o=ok:
                                self._set_status(f"{f} 的{k}任务"
                                                 f"{'完成' if o else '失败'}"))
        # 更新顶栏提示
        self.root.after(0, self._update_sched_lbl)

    def _update_sched_lbl(self):
        enabled = [i["folder"] for i in dataio.list_industries(self.data_root)
                   if i["periodic_enabled"]]
        self.sched_lbl.config(
            text=("调度中: " + ",".join(enabled) if enabled else ""))

    def _run_crawl(self, folder, cmd):
        sdir = self._search_dir()
        if not sdir.exists():
            return False, f"抓取目录不存在: {sdir}"
        try:
            result = subprocess.run(
                [sys.executable, "-m", "src.main", cmd, "--folder", folder],
                cwd=str(sdir),
                creationflags=(subprocess.CREATE_NO_WINDOW
                               if sys.platform == "win32" else 0),
                capture_output=True, text=True, timeout=1800, check=False)
            detail = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
            return result.returncode == 0, detail.strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"{type(exc).__name__}: {exc}"

    def _on_close(self):
        self._sched_stop.set()
        self.root.destroy()
