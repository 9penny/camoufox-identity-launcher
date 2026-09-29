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
        self.root.tk.call("tk", "scaling", self.root.winfo_fpixels("1i") / 72)
        self.dpi = None
        self.root.bind("<Configure>", self._update_dpi)
        ttk.Style().theme_use("vista")
        self.identities = load_identities()
        self.events = queue.Queue()
        self.browser = BrowserManager(lambda *event: self.events.put(("browser", *event)))
        self.states: dict[str, str] = {}
        self.current_id: str | None = None
        self.locate_sequence = 0
        self.list_page = ttk.Frame(root, padding=18)
        self.edit_page = ttk.Frame(root, padding=18)
        self._build_list()
        self._build_edit()
        self.show_list()
        self.root.after(100, self._drain_events)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _update_dpi(self, _event=None):
        try:
            dpi = ctypes.windll.user32.GetDpiForWindow(self.root.winfo_id())
            if dpi != self.dpi:
                self.dpi = dpi
                self.root.tk.call("tk", "scaling", dpi / 72)
        except (AttributeError, OSError):
            pass

    def _build_list(self):
        top = ttk.Frame(self.list_page)
        top.pack(fill="x")
        ttk.Label(top, text="身份列表", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Button(top, text="新建身份", command=lambda: self.show_edit(None)).pack(side="right")
        ttk.Separator(self.list_page).pack(fill="x", pady=(14, 10))
        self.list_hint = ttk.Label(self.list_page, text="")
        self.list_hint.pack(anchor="w", pady=(0, 6))
        container = ttk.Frame(self.list_page)
        container.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0)
        scroll = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.rows = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.rows, anchor="nw")
        self.rows.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.canvas_window, width=e.width))
        ttk.Label(self.list_page, text=f"本地数据：{APP_DIR}").pack(anchor="w", pady=(12, 0))
        try:
            version_text = browser_version_label()
        except Exception:
            version_text = "Camoufox 浏览器版本：未安装"
        ttk.Label(self.list_page, text=version_text).pack(anchor="w", pady=(4, 0))

    def _build_edit(self):
        ttk.Label(self.edit_page, text="身份编辑", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 16))
        self.vars = {name: tk.StringVar() for name in (
            "name", "proxy_type", "host", "port", "username", "password",
            "country", "timezone", "language", "latitude", "longitude")}
        self.vars["proxy_type"].set("none")
        fields = [
            ("名称", "name"), ("代理类型", "proxy_type"), ("主机", "host"),
            ("端口", "port"), ("用户名", "username"), ("密码", "password"),
        ]
        for row, (label, key) in enumerate(fields, 1):
            ttk.Label(self.edit_page, text=label).grid(row=row, column=0, sticky="w", pady=5, padx=(0, 12))
            if key == "proxy_type":
                widget = ttk.Combobox(self.edit_page, textvariable=self.vars[key],
                                      values=("none", "http", "https", "socks5"), state="readonly")
            else:
                widget = ttk.Entry(self.edit_page, textvariable=self.vars[key], width=38,
                                   show="*" if key == "password" else "")
            widget.grid(row=row, column=1, columnspan=2, sticky="ew", pady=5)
        ttk.Separator(self.edit_page).grid(row=7, column=0, columnspan=3, sticky="ew", pady=12)
        ttk.Label(self.edit_page, text="IP 定位结果").grid(row=8, column=0, sticky="w")
        self.proxy_test_button = ttk.Button(self.edit_page, text="测试代理", command=self._test_proxy)
        self.proxy_test_button.grid(row=8, column=1, sticky="e", padx=(0, 8))
        self.locate_button = ttk.Button(self.edit_page, text="按 IP 自动填充", command=self._auto_locate)
        self.locate_button.grid(row=8, column=2, sticky="e")
        for row, (label, key) in enumerate((
            ("国家/地区代码", "country"), ("时区", "timezone"), ("语言", "language"),
            ("纬度", "latitude"), ("经度", "longitude")), 9):
            ttk.Label(self.edit_page, text=label).grid(row=row, column=0, sticky="w", pady=5, padx=(0, 12))
            ttk.Entry(self.edit_page, textvariable=self.vars[key], width=38).grid(
                row=row, column=1, columnspan=2, sticky="ew", pady=5)
        self.edit_hint = ttk.Label(self.edit_page, text="", foreground="#a33", wraplength=560)
        self.edit_hint.grid(row=14, column=0, columnspan=3, sticky="w", pady=(12, 2))
        actions = ttk.Frame(self.edit_page)
        actions.grid(row=15, column=0, columnspan=3, sticky="e", pady=(8, 0))
        ttk.Button(actions, text="取消", command=self.show_list).pack(side="right", padx=(8, 0))
        ttk.Button(actions, text="保存", command=self._save).pack(side="right")
        self.edit_page.columnconfigure(1, weight=1)
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
        if not self.identities:
            ttk.Label(self.rows, text="还没有身份。点击“新建身份”开始。", padding=20).pack(anchor="w")
            return
        header = ttk.Frame(self.rows)
        header.pack(fill="x", pady=(0, 7))
        for text_, width in (("名称", 22), ("代理位置", 25), ("运行状态", 12)):
            ttk.Label(header, text=text_, width=width).pack(side="left")
        for item in self.identities:
            identity_id = item["id"]
            row = ttk.Frame(self.rows)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=item["name"], width=22).pack(side="left")
            location = item.get("country") or "未设置"
            if item.get("ip"):
                location += " · " + item["ip"]
            ttk.Label(row, text=location, width=25).pack(side="left")
            state = self.states.get(identity_id, "stopped")
            ttk.Label(row, text={"starting": "启动中", "running": "运行中", "stopping": "停止中",
                                 "stopped": "已停止", "error": "启动失败"}.get(state, state), width=12).pack(side="left")
            for label, action in (("编辑", self.show_edit), ("启动", self._start),
                                  ("停止", self._stop), ("删除", self._delete)):
                ttk.Button(row, text=label, command=lambda ident=identity_id, fn=action: fn(ident)).pack(
                    side="left", padx=(0, 5))
            ttk.Separator(self.rows).pack(fill="x")

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
