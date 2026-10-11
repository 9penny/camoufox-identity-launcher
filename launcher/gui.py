from __future__ import annotations

import ctypes
import queue
import re
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from language_tags import tags

from .browser import BrowserManager, browser_version_label
from .network import LocationError, ProxyCheckError, locate, test_proxy
from .storage import APP_DIR, delete_profile, load_identities, new_id, save_identities


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Camoufox 身份启动器")
        self.root.geometry("1040x760")
        self.root.minsize(860, 620)
        self.root.tk.call("tk", "scaling", self.root.winfo_fpixels("1i") / 72)
        self.dpi = None
        self.root.bind("<Configure>", self._update_dpi)
        self._configure_styles()
        self.identities = load_identities()
        self.events = queue.Queue()
        self.browser = BrowserManager(lambda *event: self.events.put(("browser", *event)))
        self.states: dict[str, str] = {}
        self.current_id: str | None = None
        self.locate_sequence = 0
        self.list_page = ttk.Frame(root, padding=(32, 28), style="App.TFrame")
        self.edit_page = ttk.Frame(root, padding=(32, 28), style="App.TFrame")
        self._build_list()
        self._build_edit()
        self.show_list()
        self.root.after(100, self._drain_events)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _configure_styles(self):
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        self.root.configure(background="#F4F6FA")
        style.configure("TFrame", background="#F4F6FA")
        style.configure("App.TFrame", background="#F4F6FA")
        style.configure("Card.TFrame", background="#FFFFFF")
        style.configure("TLabel", background="#F4F6FA", foreground="#182230",
                        font=("Segoe UI", 10))
        style.configure("Eyebrow.TLabel", background="#F4F6FA", foreground="#52627A",
                        font=("Segoe UI", 9, "bold"))
        style.configure("Title.TLabel", background="#F4F6FA", foreground="#152238",
                        font=("Segoe UI", 24, "bold"))
        style.configure("Subtitle.TLabel", background="#F4F6FA", foreground="#65748B",
                        font=("Segoe UI", 10))
        style.configure("Section.TLabel", background="#FFFFFF", foreground="#182230",
                        font=("Segoe UI", 12, "bold"))
        style.configure("CardTitle.TLabel", background="#FFFFFF", foreground="#182230",
                        font=("Segoe UI", 12, "bold"))
        style.configure("CardBody.TLabel", background="#FFFFFF", foreground="#66758A",
                        font=("Segoe UI", 9))
        style.configure("Field.TLabel", background="#FFFFFF", foreground="#48566B",
                        font=("Segoe UI", 9, "bold"))
        style.configure("Muted.TLabel", background="#F4F6FA", foreground="#718096",
                        font=("Segoe UI", 9))
        style.configure("Hint.TLabel", background="#FFFFFF", foreground="#52627A",
                        font=("Segoe UI", 9), wraplength=680)
        style.configure("Primary.TButton", background="#2764D8", foreground="#FFFFFF",
                        padding=(15, 9), borderwidth=0, font=("Segoe UI", 10, "bold"))
        style.map("Primary.TButton", background=[("active", "#1E50B4"), ("disabled", "#AABBDD")],
                  foreground=[("disabled", "#F4F6FA")])
        style.configure("Secondary.TButton", background="#E9EEF6", foreground="#24344D",
                        padding=(11, 7), borderwidth=0, font=("Segoe UI", 9, "bold"))
        style.map("Secondary.TButton", background=[("active", "#DCE5F1")])
        style.configure("Quiet.TButton", background="#FFFFFF", foreground="#52627A",
                        padding=(9, 6), borderwidth=0, font=("Segoe UI", 9))
        style.map("Quiet.TButton", background=[("active", "#EEF2F8")])
        style.configure("Danger.TButton", background="#FFF0F0", foreground="#B42318",
                        padding=(9, 6), borderwidth=0, font=("Segoe UI", 9))
        style.map("Danger.TButton", background=[("active", "#FDE0E0")])
        style.configure("Status.Running.TLabel", background="#E8F7EF", foreground="#167346",
                        padding=(9, 4), font=("Segoe UI", 9, "bold"))
        style.configure("Status.Starting.TLabel", background="#FFF5DE", foreground="#946200",
                        padding=(9, 4), font=("Segoe UI", 9, "bold"))
        style.configure("Status.Error.TLabel", background="#FFF0F0", foreground="#B42318",
                        padding=(9, 4), font=("Segoe UI", 9, "bold"))
        style.configure("Status.Stopped.TLabel", background="#EDF1F6", foreground="#536277",
                        padding=(9, 4), font=("Segoe UI", 9, "bold"))
        style.configure("TEntry", padding=(9, 8), fieldbackground="#FFFFFF",
                        foreground="#182230", bordercolor="#D7DFEA", lightcolor="#D7DFEA",
                        darkcolor="#D7DFEA")
        style.configure("TCombobox", padding=(8, 7), fieldbackground="#FFFFFF",
                        foreground="#182230", bordercolor="#D7DFEA", arrowcolor="#52627A")
        style.configure("Vertical.TScrollbar", background="#D9E1EC", troughcolor="#F4F6FA",
                        bordercolor="#F4F6FA", arrowsize=12)

    def _update_dpi(self, _event=None):
        try:
            dpi = ctypes.windll.user32.GetDpiForWindow(self.root.winfo_id())
            if dpi != self.dpi:
                self.dpi = dpi
                self.root.tk.call("tk", "scaling", dpi / 72)
        except (AttributeError, OSError):
            pass

    def _build_list(self):
        top = ttk.Frame(self.list_page, style="App.TFrame")
        top.pack(fill="x", pady=(0, 24))
        title_group = ttk.Frame(top, style="App.TFrame")
        title_group.pack(side="left", fill="x", expand=True)
        ttk.Label(title_group, text="CAMOUFOX  /  PROFILE MANAGER", style="Eyebrow.TLabel").pack(anchor="w")
        ttk.Label(title_group, text="浏览器身份", style="Title.TLabel").pack(anchor="w", pady=(5, 2))
        ttk.Label(title_group, text="为不同用途创建独立的浏览器环境，设置和数据保存在本机。",
                  style="Subtitle.TLabel").pack(anchor="w")
        ttk.Button(top, text="＋  新建身份", style="Primary.TButton",
                   command=lambda: self.show_edit(None)).pack(side="right", anchor="center", padx=(18, 0))

        summary = ttk.Frame(self.list_page, style="App.TFrame")
        summary.pack(fill="x", pady=(0, 14))
        self.identity_count = tk.StringVar(value="0")
        self.running_count = tk.StringVar(value="0")
        for parent, label, variable in (
            (summary, "已创建身份", self.identity_count),
            (summary, "正在运行", self.running_count),
        ):
            card = ttk.Frame(parent, style="Card.TFrame", padding=(16, 11))
            card.pack(side="left", fill="x", expand=True, padx=(0, 10))
            ttk.Label(card, textvariable=variable, style="CardTitle.TLabel",
                      font=("Segoe UI", 17, "bold")).pack(anchor="w")
            ttk.Label(card, text=label, style="CardBody.TLabel").pack(anchor="w", pady=(1, 0))

        self.list_hint = ttk.Label(self.list_page, text="", style="Subtitle.TLabel", wraplength=850)
        self.list_hint.pack(anchor="w", fill="x", pady=(0, 8))
        container = ttk.Frame(self.list_page)
        container.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0, background="#F4F6FA")
        scroll = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.rows = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.rows, anchor="nw")
        self.rows.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.canvas_window, width=e.width))
        ttk.Label(self.list_page, text=f"本地数据  ·  {APP_DIR}", style="Muted.TLabel",
                  wraplength=900).pack(anchor="w", pady=(14, 0))
        try:
            version_text = browser_version_label()
        except Exception:
            version_text = "Camoufox 浏览器版本：未安装"
        ttk.Label(self.list_page, text=version_text, style="Muted.TLabel").pack(anchor="w", pady=(4, 0))

    def _build_edit(self):
        top = ttk.Frame(self.edit_page, style="App.TFrame")
        top.pack(fill="x", pady=(0, 20))
        ttk.Button(top, text="←  返回", style="Quiet.TButton", command=self.show_list).pack(side="left", padx=(0, 16))
        title_group = ttk.Frame(top, style="App.TFrame")
        title_group.pack(side="left", fill="x", expand=True)
        ttk.Label(title_group, text="设置一个独立的浏览器环境", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_group, text="代理、位置与语言参数都只应用于这个身份。",
                  style="Subtitle.TLabel").pack(anchor="w", pady=(3, 0))
        self.vars = {name: tk.StringVar() for name in (
            "name", "proxy_type", "host", "port", "username", "password",
            "country", "timezone", "language", "latitude", "longitude")}
        self.vars["proxy_type"].set("none")
        proxy_card = ttk.Frame(self.edit_page, style="Card.TFrame", padding=20)
        proxy_card.pack(fill="x", pady=(0, 14))
        ttk.Label(proxy_card, text="代理连接", style="Section.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(proxy_card, text="可留空直连；如使用代理，请填写代理服务提供的地址和凭据。",
                  style="CardBody.TLabel").grid(row=1, column=0, columnspan=4, sticky="w", pady=(3, 14))

        def add_field(parent, label, key, row, column, span=1, kind="entry"):
            field = ttk.Frame(parent, style="Card.TFrame")
            field.grid(row=row, column=column, columnspan=span, sticky="ew",
                       padx=(0, 12 if column == 0 and span == 2 else 0), pady=(0, 12))
            ttk.Label(field, text=label, style="Field.TLabel").pack(anchor="w", pady=(0, 5))
            if kind == "proxy":
                widget = ttk.Combobox(field, textvariable=self.vars[key],
                                      values=("none", "http", "https", "socks5"), state="readonly")
            else:
                widget = ttk.Entry(field, textvariable=self.vars[key], show="*" if key == "password" else "")
            widget.pack(fill="x")
            return widget

        add_field(proxy_card, "身份名称", "name", 2, 0, 4)
        add_field(proxy_card, "代理类型", "proxy_type", 3, 0, 2, "proxy")
        add_field(proxy_card, "代理主机", "host", 3, 2, 2)
        add_field(proxy_card, "端口", "port", 4, 0, 2)
        add_field(proxy_card, "用户名（可选）", "username", 4, 2, 2)
        add_field(proxy_card, "密码（可选）", "password", 5, 0, 4)
        proxy_card.columnconfigure(0, weight=1, uniform="proxy")
        proxy_card.columnconfigure(1, weight=1, uniform="proxy")
        proxy_card.columnconfigure(2, weight=1, uniform="proxy")
        proxy_card.columnconfigure(3, weight=1, uniform="proxy")

        geo_card = ttk.Frame(self.edit_page, style="Card.TFrame", padding=20)
        geo_card.pack(fill="x")
        geo_header = ttk.Frame(geo_card, style="Card.TFrame")
        geo_header.grid(row=0, column=0, columnspan=4, sticky="ew")
        geo_titles = ttk.Frame(geo_header, style="Card.TFrame")
        geo_titles.pack(side="left", fill="x", expand=True)
        ttk.Label(geo_titles, text="位置与语言", style="Section.TLabel").pack(anchor="w")
        ttk.Label(geo_titles, text="检测代理出口位置，或按需手动调整。",
                  style="CardBody.TLabel").pack(anchor="w", pady=(3, 0))
        self.proxy_test_button = ttk.Button(geo_header, text="测试代理", command=self._test_proxy,
                                            style="Quiet.TButton")
        self.locate_button = ttk.Button(geo_header, text="按 IP 自动填充", command=self._auto_locate,
                                        style="Secondary.TButton")
        self.proxy_test_button.pack(side="right", padx=(8, 0))
        self.locate_button.pack(side="right")
        add_field(geo_card, "国家/地区代码", "country", 1, 0, 2)
        add_field(geo_card, "时区", "timezone", 1, 2, 2)
        add_field(geo_card, "语言", "language", 2, 0, 2)
        add_field(geo_card, "纬度", "latitude", 2, 2, 1)
        add_field(geo_card, "经度", "longitude", 2, 3, 1)
        for col in range(4):
            geo_card.columnconfigure(col, weight=1, uniform="geo")
        self.edit_hint = ttk.Label(geo_card, text="", style="Hint.TLabel", wraplength=760)
        self.edit_hint.grid(row=3, column=0, columnspan=4, sticky="w", pady=(0, 0))
        actions = ttk.Frame(self.edit_page, style="App.TFrame")
        actions.pack(fill="x", pady=(18, 0))
        ttk.Button(actions, text="取消", style="Quiet.TButton", command=self.show_list).pack(side="right", padx=(8, 0))
        ttk.Button(actions, text="保存身份", style="Primary.TButton", command=self._save).pack(side="right")
        for key in ("proxy_type", "host", "port", "username", "password"):
            self.vars[key].trace_add("write", self._proxy_changed)

    def _proxy_changed(self, *_args):
        if getattr(self, "loading_form", False):
            return
        self.locate_sequence += 1
        self.proxy_test_sequence = getattr(self, "proxy_test_sequence", 0) + 1
        self.proxy_test_button.configure(state="normal")
        self.locate_button.configure(state="normal")
        self.ip = ""
        for key in ("country", "timezone", "language", "latitude", "longitude"):
            self.vars[key].set("")
        self.edit_hint.configure(text="代理已变更，请重新按 IP 定位或手动填写地理参数。")

    def show_list(self):
        self.locate_sequence += 1
        self.current_id = None
        self.edit_page.pack_forget()
        self.list_page.pack(fill="both", expand=True)
        self._render_list()

    def _render_list(self):
        for child in self.rows.winfo_children():
            child.destroy()
        self.identity_count.set(str(len(self.identities)))
        self.running_count.set(str(sum(self.states.get(item["id"]) in ("starting", "running", "stopping")
                                       for item in self.identities)))
        if not self.identities:
            empty = ttk.Frame(self.rows, style="Card.TFrame", padding=28)
            empty.pack(fill="x", pady=8)
            ttk.Label(empty, text="还没有浏览器身份", style="CardTitle.TLabel").pack(anchor="w")
            ttk.Label(empty, text="创建第一个身份后，可为它配置独立代理、语言和位置参数。",
                      style="CardBody.TLabel").pack(anchor="w", pady=(5, 14))
            ttk.Button(empty, text="＋  创建第一个身份", style="Primary.TButton",
                       command=lambda: self.show_edit(None)).pack(anchor="w")
            return
        for item in self.identities:
            identity_id = item["id"]
            card = ttk.Frame(self.rows, style="Card.TFrame", padding=(18, 14))
            card.pack(fill="x", pady=(0, 10))
            card.columnconfigure(0, weight=1)
            details = ttk.Frame(card, style="Card.TFrame")
            details.grid(row=0, column=0, sticky="ew")
            ttk.Label(details, text=item["name"], style="CardTitle.TLabel").pack(anchor="w")
            metadata = []
            proxy_type = item.get("proxy_type", "none")
            if proxy_type and proxy_type != "none":
                metadata.append(f"{proxy_type.upper()}  {item.get('host', '')}:{item.get('port', '')}")
            else:
                metadata.append("直连")
            metadata.append(item.get("country") or "位置未设置")
            if item.get("ip"):
                metadata.append(item["ip"])
            ttk.Label(details, text="  ·  ".join(metadata), style="CardBody.TLabel").pack(anchor="w", pady=(4, 0))
            state = self.states.get(identity_id, "stopped")
            state_text = {"starting": "启动中", "running": "运行中", "stopping": "停止中",
                          "stopped": "已停止", "error": "启动失败"}.get(state, state)
            state_style = {"running": "Status.Running.TLabel", "starting": "Status.Starting.TLabel",
                           "stopping": "Status.Starting.TLabel", "error": "Status.Error.TLabel"}.get(
                               state, "Status.Stopped.TLabel")
            right = ttk.Frame(card, style="Card.TFrame")
            right.grid(row=0, column=1, sticky="e", padx=(18, 0))
            ttk.Label(right, text=state_text, style=state_style).pack(side="left", padx=(0, 12))
            ttk.Button(right, text="编辑", style="Quiet.TButton",
                       command=lambda ident=identity_id: self.show_edit(ident)).pack(side="left", padx=(0, 5))
            if state in ("starting", "running", "stopping"):
                ttk.Button(right, text="停止", style="Secondary.TButton",
                           command=lambda ident=identity_id: self._stop(ident)).pack(side="left", padx=(0, 5))
            else:
                ttk.Button(right, text="启动", style="Primary.TButton",
                           command=lambda ident=identity_id: self._start(ident)).pack(side="left", padx=(0, 5))
            ttk.Button(right, text="删除", style="Danger.TButton",
                       command=lambda ident=identity_id: self._delete(ident)).pack(side="left")

    def show_edit(self, identity_id: str | None):
        if identity_id and self.browser.running(identity_id):
            messagebox.showerror("正在运行", "请先停止浏览器，再编辑此身份。")
            return
        self.proxy_test_sequence = getattr(self, "proxy_test_sequence", 0) + 1
        item = next((x for x in self.identities if x["id"] == identity_id), {})
        self.current_id = identity_id
        self.locate_sequence += 1
        self.loading_form = True
        for key, var in self.vars.items():
            var.set(str(item.get(key, "none" if key == "proxy_type" else "")))
        self.ip = item.get("ip", "")
        self.loading_form = False
        self.locate_button.configure(state="normal")
        self.edit_hint.configure(text="")
        self.list_page.pack_forget()
        self.edit_page.pack(fill="both", expand=True)

    def _proxy_fields(self) -> dict:
        kind = self.vars["proxy_type"].get()
        if kind not in ("none", "http", "https", "socks5"):
            raise ValueError("代理类型无效")
        host = self.vars["host"].get().strip()
        port = self.vars["port"].get().strip()
        if kind != "none":
            if not host or any(c in host for c in "/@ "):
                raise ValueError("请填写有效代理主机名或 IP，不包含协议前缀")
            if not port.isdigit() or not 1 <= int(port) <= 65535:
                raise ValueError("代理端口须为 1–65535")
        return {"proxy_type": kind, "host": host if kind != "none" else "",
                "port": port if kind != "none" else "", "username": self.vars["username"].get() if kind != "none" else "",
                "password": self.vars["password"].get() if kind != "none" else ""}

    def _auto_locate(self):
        try:
            proxy = self._proxy_fields()
        except ValueError as exc:
            self.edit_hint.configure(text=str(exc))
            return
        self.locate_sequence += 1
        sequence = self.locate_sequence
        self.locate_button.configure(state="disabled")
        self.edit_hint.configure(text="正在通过所选代理查询出口 IP 并定位…")

        def worker():
            try:
                result = locate(proxy)
                self.events.put(("location", sequence, result, ""))
            except LocationError as exc:
                self.events.put(("location", sequence, None, str(exc)))
            except Exception:
                self.events.put(("location", sequence, None,
                                 "定位时发生错误。请检查代理配置与 GeoIP 数据，或手动填写地理参数。"))
        threading.Thread(target=worker, daemon=True).start()

    def _test_proxy(self):
        try:
            proxy = self._proxy_fields()
        except ValueError as exc:
            self.edit_hint.configure(text=str(exc))
            return
        self.proxy_test_sequence = getattr(self, "proxy_test_sequence", 0) + 1
        sequence = self.proxy_test_sequence
        self.proxy_test_button.configure(state="disabled")
        self.edit_hint.configure(text="正在测试代理并查询出口 IP…")

        def worker():
            try:
                ip = test_proxy(proxy)
                self.events.put(("proxy_check", sequence, ip, ""))
            except ProxyCheckError as exc:
                self.events.put(("proxy_check", sequence, None, str(exc)))
            except Exception:
                self.events.put(("proxy_check", sequence, None,
                                 "代理测试发生意外错误，请检查代理配置后重试。"))
        threading.Thread(target=worker, daemon=True).start()

    def _save(self):
        try:
            proxy = self._proxy_fields()
            name = self.vars["name"].get().strip()
            if not name:
                raise ValueError("请填写身份名称")
            country = self.vars["country"].get().strip().upper()
            timezone = self.vars["timezone"].get().strip()
            language = self.vars["language"].get().strip()
            if not re.fullmatch(r"[A-Z]{2}", country):
                raise ValueError("国家/地区须为两位代码，例如 CN、US")
            if not timezone or not re.fullmatch(r"[A-Za-z0-9_+./-]+", timezone):
                raise ValueError("请填写 IANA 时区，例如 Asia/Shanghai")
            if not tags.check(language):
                raise ValueError("语言格式无效，例如 zh-CN、en-US")
            lat = float(self.vars["latitude"].get())
            lon = float(self.vars["longitude"].get())
            if not -90 <= lat <= 90 or not -180 <= lon <= 180:
                raise ValueError("纬度须在 -90–90，经度须在 -180–180")
            record = {"id": self.current_id or new_id(), "name": name, **proxy,
                      "ip": self.ip, "country": country, "timezone": timezone,
                      "language": language, "latitude": str(lat), "longitude": str(lon)}
            updated = [record if item["id"] == self.current_id else item for item in self.identities]
            if self.current_id is None:
                updated.append(record)
            save_identities(updated)
            self.identities = updated
            self.show_list()
        except (ValueError, OSError) as exc:
            self.edit_hint.configure(text=str(exc))

    def _start(self, identity_id: str):
        item = next(x for x in self.identities if x["id"] == identity_id)
        self.list_hint.configure(text="")
        self.states[identity_id] = "starting"
        self.browser.start(item)
        self._render_list()

    def _stop(self, identity_id: str):
        self.browser.stop(identity_id)

    def _delete(self, identity_id: str):
        if self.browser.running(identity_id):
            messagebox.showerror("正在运行", "请先停止浏览器，再删除此身份。")
            return
        item = next(x for x in self.identities if x["id"] == identity_id)
        if not messagebox.askyesno("删除身份", f"删除“{item['name']}”及其全部本地浏览器数据？此操作无法撤销。"):
            return
        try:
            updated = [x for x in self.identities if x["id"] != identity_id]
            save_identities(updated)
            self.identities = updated
            delete_profile(identity_id)
            self.states.pop(identity_id, None)
            self._render_list()
        except OSError as exc:
            messagebox.showerror("删除失败", str(exc))

    def _drain_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "browser":
                    _, identity_id, state, detail = event
                    if state != "stopped" or self.states.get(identity_id) != "error":
                        self.states[identity_id] = state
                    if state == "error":
                        self.list_hint.configure(text=f"启动失败：{detail}")
                    if self.current_id is None:
                        self._render_list()
                elif event[0] == "location":
                    _, sequence, result, error = event
                    if sequence != self.locate_sequence or self.current_id is None and not self.edit_page.winfo_ismapped():
                        continue
                    self.locate_button.configure(state="normal")
                    if error:
                        self.edit_hint.configure(text=error)
                    else:
                        self.ip = result["ip"]
                        for key in ("country", "timezone", "language", "latitude", "longitude"):
                            self.vars[key].set(result[key])
                        self.edit_hint.configure(text=f"出口 IP：{self.ip}。请核对定位结果后保存。")
                elif event[0] == "proxy_check":
                    _, sequence, ip, error = event
                    if sequence != getattr(self, "proxy_test_sequence", 0):
                        continue
                    self.proxy_test_button.configure(state="normal")
                    if error:
                        self.edit_hint.configure(text=error)
                    else:
                        self.edit_hint.configure(text=f"代理连接正常，出口 IP：{ip}")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _close(self):
        self.browser.stop_all()
        if self.browser.any_running():
            self.list_hint.configure(text="正在关闭浏览器…")
            self.root.after(300, self._close)
        else:
            self.root.destroy()
