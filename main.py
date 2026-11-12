import customtkinter as ctk
from tkinter import Menu, TclError, messagebox
import ipaddress
import queue
import socket
import statistics
import threading
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from ping3 import ping


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class PingApp(ctk.CTk):
    BG = "#0C1114"
    PANEL = "#12191D"
    PANEL_DARK = "#0A0F12"
    BORDER = "#29363B"
    TEXT = "#E3E9E6"
    MUTED = "#829097"
    GREEN = "#69D1A5"
    AMBER = "#E3B66F"
    RED = "#E77D77"
    BLUE = "#78A9FF"

    def __init__(self):
        super().__init__()
        self.title("PingDesk")
        self.geometry("1180x760")
        self.minsize(1000, 650)
        self.configure(fg_color=self.BG)

        self._events = queue.Queue()
        self._cancel_ping = threading.Event()
        self._ping_running = False
        self._closing = False
        self._results_data = []
        self.protocol("WM_DELETE_WINDOW", self.close_app)

        self.build_interface()
        self.after(100, self.process_worker_events)

    def build_interface(self):
        shell = ctk.CTkFrame(self, fg_color="transparent")
        shell.pack(fill="both", expand=True, padx=22, pady=(16, 14))

        topbar = ctk.CTkFrame(shell, fg_color="transparent", height=56)
        topbar.pack(fill="x", pady=(0, 12))
        topbar.pack_propagate(False)

        ctk.CTkLabel(
            topbar,
            text="NET / 01",
            text_color=self.GREEN,
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold")
        ).pack(side="left", padx=(2, 14))
        ctk.CTkFrame(topbar, width=1, fg_color=self.BORDER).pack(
            side="left", fill="y", pady=8
        )
        title_block = ctk.CTkFrame(topbar, fg_color="transparent")
        title_block.pack(side="left", padx=14)
        ctk.CTkLabel(
            title_block,
            text="Сетевая диагностика",
            text_color=self.TEXT,
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_block,
            text="ICMP echo  /  HTTP response",
            text_color=self.MUTED,
            font=ctk.CTkFont(family="Consolas", size=10)
        ).pack(anchor="w", pady=(2, 0))

        self.status_label = ctk.CTkLabel(
            topbar,
            text="●  READY",
            text_color=self.GREEN,
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold")
        )
        self.status_label.pack(side="right", padx=4)

        ctk.CTkFrame(shell, height=1, fg_color=self.BORDER).pack(fill="x")

        workarea = ctk.CTkFrame(shell, fg_color="transparent")
        workarea.pack(fill="both", expand=True, pady=(16, 0))

        self.input_panel = ctk.CTkFrame(
            workarea,
            width=306,
            fg_color=self.PANEL,
            border_color=self.BORDER,
            border_width=1,
            corner_radius=6
        )
        self.input_panel.pack(side="left", fill="y")
        self.input_panel.pack_propagate(False)

        input_top = ctk.CTkFrame(self.input_panel, fg_color="transparent")
        input_top.pack(fill="x", padx=15, pady=(14, 7))
        ctk.CTkLabel(
            input_top,
            text="TARGETS",
            text_color=self.TEXT,
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold")
        ).pack(side="left")
        self.target_count_label = ctk.CTkLabel(
            input_top,
            text="00",
            text_color=self.MUTED,
            font=ctk.CTkFont(family="Consolas", size=11)
        )
        self.target_count_label.pack(side="right")

        ctk.CTkLabel(
            self.input_panel,
            text="IP, domain, or URL — one per line",
            text_color=self.MUTED,
            font=ctk.CTkFont(size=10)
        ).pack(anchor="w", padx=15, pady=(0, 10))

        self.text_input = ctk.CTkTextbox(
            self.input_panel,
            height=230,
            fg_color=self.PANEL_DARK,
            text_color="#CDE7D8",
            border_color=self.BORDER,
            border_width=1,
            corner_radius=4,
            font=ctk.CTkFont(family="Consolas", size=12),
            scrollbar_button_color="#36474A",
            scrollbar_button_hover_color="#4A6061"
        )
        self.text_input.pack(fill="x", padx=14)
        self.text_input.insert("1.0", "google.com\n8.8.8.8")
        self.text_input.bind("<Control-KeyPress>", self.handle_paste_shortcut, add="+")
        self.text_input.bind("<Button-3>", self.show_text_context_menu, add="+")
        self.text_input.bind("<KeyRelease>", self.update_target_count, add="+")

        self.text_context_menu = Menu(self, tearoff=0)
        self.text_context_menu.add_command(
            label="Вставить",
            command=self.paste_from_clipboard
        )
        self.text_context_menu.add_command(
            label="Выделить всё",
            command=lambda: self.text_input.tag_add("sel", "1.0", "end")
        )
        self.update_target_count()

        button_row = ctk.CTkFrame(self.input_panel, fg_color="transparent")
        button_row.pack(fill="x", padx=14, pady=(9, 0))
        self.paste_button = ctk.CTkButton(
            button_row,
            text="ВСТАВИТЬ",
            command=self.paste_from_clipboard,
            height=31,
            width=104,
            fg_color="#253239",
            hover_color="#34464B",
            text_color=self.TEXT,
            corner_radius=4,
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold")
        )
        self.paste_button.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self.clear_button = ctk.CTkButton(
            button_row,
            text="СБРОС",
            command=self.clear_results,
            height=31,
            width=76,
            fg_color="#253239",
            hover_color="#34464B",
            text_color=self.TEXT,
            corner_radius=4,
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold")
        )
        self.clear_button.pack(side="left", expand=True, fill="x", padx=(5, 0))

        self.ping_button = ctk.CTkButton(
            self.input_panel,
            text="ЗАПУСТИТЬ ПРОВЕРКУ",
            command=self.start_ping,
            height=42,
            fg_color="#28785D",
            hover_color="#32906F",
            text_color="#F3FFF8",
            corner_radius=4,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.ping_button.pack(fill="x", padx=14, pady=(14, 12))

        ctk.CTkFrame(self.input_panel, height=1, fg_color=self.BORDER).pack(
            fill="x", padx=14, pady=(0, 12)
        )
        ctk.CTkLabel(
            self.input_panel,
            text="ПРОФИЛЬ",
            text_color=self.MUTED,
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold")
        ).pack(anchor="w", padx=15, pady=(0, 8))
        ctk.CTkLabel(
            self.input_panel,
            text="ICMP     3 попытки · 2 сек\nWEB      GET · 3 сек\nDNS      IPv4 предпочтительно",
            justify="left",
            text_color="#B7C2C0",
            font=ctk.CTkFont(family="Consolas", size=10)
        ).pack(anchor="w", padx=15)
        ctk.CTkLabel(
            self.input_panel,
            text="Домен без схемы: HTTPS, затем HTTP.\nURL с путём проверяется как введён.",
            justify="left",
            text_color=self.MUTED,
            font=ctk.CTkFont(size=10),
            wraplength=265
        ).pack(anchor="w", padx=15, pady=(12, 0))
        ctk.CTkLabel(
            self.input_panel,
            text="LOG  →  Desktop\\ping_results.txt",
            text_color="#65747A",
            font=ctk.CTkFont(family="Consolas", size=9)
        ).pack(side="bottom", anchor="w", padx=15, pady=13)

        results_panel = ctk.CTkFrame(workarea, fg_color="transparent")
        results_panel.pack(side="left", fill="both", expand=True, padx=(16, 0))

        results_head = ctk.CTkFrame(results_panel, fg_color="transparent", height=38)
        results_head.pack(fill="x", pady=(0, 9))
        results_head.pack_propagate(False)
        ctk.CTkLabel(
            results_head,
            text="РЕЗУЛЬТАТЫ",
            text_color=self.TEXT,
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold")
        ).pack(side="left")
        self.results_summary = ctk.CTkLabel(
            results_head,
            text="00 checked   /   00 ICMP   /   00 WEB",
            text_color=self.MUTED,
            font=ctk.CTkFont(family="Consolas", size=10)
        )
        self.results_summary.pack(side="right")

        self.table_frame = ctk.CTkFrame(
            results_panel,
            fg_color=self.PANEL,
            border_color=self.BORDER,
            border_width=1,
            corner_radius=6
        )
        self.table_frame.pack(fill="both", expand=True)
        self.column_weights = (1, 5, 1, 1, 1, 2, 2)
        headers = ["#", "TARGET / RESOLVED IP", "MIN", "AVG", "MAX", "WEB", "ICMP"]
        self.header_frame = ctk.CTkFrame(
            self.table_frame,
            fg_color="#1B252A",
            corner_radius=3
        )
        self.header_frame.pack(fill="x", padx=9, pady=(9, 5))
        for index, header in enumerate(headers):
            ctk.CTkLabel(
                self.header_frame,
                text=header,
                text_color="#91A09F",
                font=ctk.CTkFont(family="Consolas", size=9, weight="bold")
            ).grid(row=0, column=index, padx=7, pady=10, sticky="ew")
            self.header_frame.grid_columnconfigure(index, weight=self.column_weights[index])

        self.scrollable = ctk.CTkScrollableFrame(
            self.table_frame,
            fg_color="transparent",
            corner_radius=3
        )
        self.scrollable.pack(fill="both", expand=True, padx=9, pady=(0, 9))

        footer = ctk.CTkFrame(results_panel, fg_color="transparent", height=24)
        footer.pack(fill="x", pady=(8, 0))
        footer.pack_propagate(False)
        ctk.CTkLabel(
            footer,
            text="ICMP RTT is pinned to the displayed IP  ·  WEB is checked separately",
            text_color="#65747A",
            font=ctk.CTkFont(family="Consolas", size=9)
        ).pack(side="left")

        self.result_rows = []

    def update_target_count(self, event=None):
        count = sum(
            1 for line in self.text_input.get("1.0", "end").splitlines()
            if line.strip()
        )
        self.target_count_label.configure(text=f"{count:02d}")

    def paste_from_clipboard(self):
        try:
            text = self.clipboard_get()
        except TclError:
            return

        self.text_input.focus_set()
        selection = self.text_input.tag_ranges("sel")
        if selection:
            self.text_input.delete(selection[0], selection[1])
        self.text_input.insert("insert", text)
        self.update_target_count()

    def handle_paste_shortcut(self, event):
        keysym = event.keysym.lower()
        character = (event.char or "").lower()
        if (
            event.keycode == 86
            or keysym in ("v", "cyrillic_em")
            or character in ("v", "м")
        ):
            self.paste_from_clipboard()
            return "break"
        return None

    def show_text_context_menu(self, event):
        self.text_input.focus_set()
        self.text_context_menu.tk_popup(event.x_root, event.y_root)
        return "break"

    @staticmethod
    def parse_target(target):
        target = target.strip()
        if not target:
            raise ValueError("Пустой адрес")

        explicit_scheme = "://" in target
        if explicit_scheme:
            candidate = target
        else:
            try:
                address = ipaddress.ip_address(target)
            except ValueError:
                candidate = "https:" + target if target.startswith("//") else f"https://{target}"
            else:
                host = address.compressed
                authority = f"[{host}]" if address.version == 6 else host
                candidate = f"https://{authority}/"

        try:
            parsed = urlsplit(candidate)
            host = parsed.hostname
            parsed.port
        except ValueError as exc:
            raise ValueError("Некорректный адрес") from exc

        if parsed.scheme.lower() not in ("http", "https") or not host:
            raise ValueError("Укажите домен, IP-адрес или HTTP(S)-ссылку")
        if any(character.isspace() for character in host):
            raise ValueError("Некорректный адрес")
        if not parsed.path:
            candidate = urlunsplit(
                (parsed.scheme, parsed.netloc, "/", parsed.query, parsed.fragment)
            )
            parsed = urlsplit(candidate)

        fallback_url = None
        if not explicit_scheme:
            fallback_url = urlunsplit(
                ("http", parsed.netloc, parsed.path or "/", parsed.query, "")
            )
        return host, candidate, fallback_url

    @staticmethod
    def resolve_host(host):
        try:
            return ipaddress.ip_address(host).compressed
        except ValueError:
            pass

        addresses = socket.getaddrinfo(
            host,
            None,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_DGRAM
        )
        ipv4 = [item[4][0] for item in addresses if item[0] == socket.AF_INET]
        ipv6 = [item[4][0] for item in addresses if item[0] == socket.AF_INET6]
        if ipv4:
            return ipv4[0]
        if ipv6:
            return ipv6[0]
        raise socket.gaierror(f"No IP address found for {host}")

    @classmethod
    def request_web(cls, url):
        request = Request(url, headers={"User-Agent": "PingDesk/1.0"})
        try:
            with urlopen(request, timeout=3) as response:
                status_code = response.getcode()
                final_url = response.geturl()
        except HTTPError as exc:
            status_code = exc.code
            final_url = url
            exc.close()
        except (URLError, TimeoutError, OSError) as exc:
            return "NO RESPONSE", cls.RED, False, str(exc)

        scheme = urlsplit(final_url).scheme.upper()
        status_color = (
            cls.GREEN if status_code < 400
            else cls.AMBER if status_code < 500
            else cls.RED
        )
        return f"{scheme} {status_code}", status_color, True, ""

    @classmethod
    def check_web(cls, url, fallback_url):
        result = cls.request_web(url)
        if not result[2] and fallback_url:
            fallback_result = cls.request_web(fallback_url)
            if fallback_result[2]:
                return fallback_result
            return (
                "NO RESPONSE",
                cls.RED,
                False,
                f"{result[3]}; HTTP fallback: {fallback_result[3]}"
            )
        return result

    def clear_results(self):
        if self._ping_running:
            return
        for row in self.result_rows:
            row.destroy()
        self.result_rows.clear()
        self._results_data.clear()
        self.update_summary()
        self.status_label.configure(text="●  READY", text_color=self.GREEN)

    def update_summary(self):
        checked = len(self._results_data)
        icmp_count = sum(1 for icmp_ok, _ in self._results_data if icmp_ok)
        web_count = sum(1 for _, web_ok in self._results_data if web_ok)
        self.results_summary.configure(
            text=f"{checked:02d} checked   /   {icmp_count:02d} ICMP   /   {web_count:02d} WEB"
        )

    def start_ping(self):
        lines = [
            line.strip()
            for line in self.text_input.get("1.0", "end").splitlines()
            if line.strip()
        ]
        if not lines:
            messagebox.showwarning("Нет целей", "Добавьте IP, домен или URL.")
            return

        targets = []
        for line in lines:
            try:
                targets.append(self.parse_target(line))
            except ValueError as exc:
                messagebox.showwarning("Некорректная цель", f"{line}\n\n{exc}")
                return

        self.clear_results()
        self._ping_running = True
        self._cancel_ping.clear()
        self.ping_button.configure(state="disabled", text="ПРОВЕРКА...")
        self.clear_button.configure(state="disabled")
        self.paste_button.configure(state="disabled")
        self.status_label.configure(text="●  RUNNING", text_color=self.AMBER)
        thread = threading.Thread(target=self.run_ping, args=(targets,), daemon=True)
        thread.start()

    def run_ping(self, targets):
        result_file = Path.home() / "Desktop" / "ping_results.txt"
        try:
            result_file.parent.mkdir(parents=True, exist_ok=True)
            with result_file.open("a", encoding="utf-8") as output:
                output.write(f"\n{'=' * 68}\n")
                output.write(f"Проверка: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
                output.write(f"{'=' * 68}\n")
                completed = 0

                for index, (host, web_url, fallback_url) in enumerate(targets, 1):
                    if self._cancel_ping.is_set():
                        break
                    self._events.put(
                        ("status", f"●  {index:02d}/{len(targets):02d}  {host}")
                    )

                    errors = []
                    try:
                        resolved_ip = self.resolve_host(host)
                    except OSError as exc:
                        resolved_ip = None
                        errors.append(f"DNS: {exc}")

                    times = []
                    if resolved_ip:
                        for _ in range(3):
                            if self._cancel_ping.is_set():
                                break
                            try:
                                delay = ping(resolved_ip, timeout=2, unit="ms")
                                if delay is False:
                                    errors.append("ICMP error")
                                elif delay is not None:
                                    times.append(delay)
                            except Exception as exc:
                                errors.append(f"ICMP: {exc}")

                    if times:
                        min_ping = min(times)
                        avg_ping = statistics.mean(times)
                        max_ping = max(times)
                        icmp_status = "REPLY"
                        icmp_color = self.GREEN
                    elif resolved_ip:
                        min_ping = avg_ping = max_ping = None
                        icmp_status = "NO REPLY"
                        icmp_color = self.RED
                    else:
                        min_ping = avg_ping = max_ping = None
                        icmp_status = "NO DNS"
                        icmp_color = self.RED

                    web_status, web_color, web_responded, web_error = self.check_web(
                        web_url,
                        fallback_url
                    )
                    if web_error:
                        errors.append(f"WEB: {web_error}")

                    self._events.put((
                        "result",
                        index,
                        host,
                        resolved_ip,
                        min_ping,
                        avg_ping,
                        max_ping,
                        web_status,
                        web_color,
                        web_responded,
                        icmp_status,
                        icmp_color,
                        bool(times)
                    ))
                    completed += 1

                    if times:
                        icmp_text = (
                            f"min {min_ping:.2f} / avg {avg_ping:.2f} / "
                            f"max {max_ping:.2f} ms"
                        )
                    else:
                        icmp_text = icmp_status
                    output.write(
                        f"{host:<28} [{resolved_ip or 'DNS FAILED'}] | "
                        f"ICMP {icmp_text} | WEB {web_status}\n"
                    )
                    if errors:
                        output.write(f"  details: {'; '.join(errors)}\n")
                    output.flush()

            self._events.put((
                "done",
                completed,
                result_file,
                self._cancel_ping.is_set()
            ))
        except Exception as exc:
            self._events.put(("error", str(exc), result_file))

    def process_worker_events(self):
        if self._closing:
            return
        try:
            while True:
                event = self._events.get_nowait()
                if event[0] == "status":
                    self.status_label.configure(text=event[1], text_color=self.AMBER)
                elif event[0] == "result":
                    self.add_result_row(*event[1:])
                elif event[0] == "done":
                    self.finish_ping(*event[1:])
                elif event[0] == "error":
                    self.handle_ping_error(*event[1:])
        except queue.Empty:
            pass
        self.after(100, self.process_worker_events)

    def add_result_row(
        self,
        index,
        host,
        resolved_ip,
        min_ping,
        avg_ping,
        max_ping,
        web_status,
        web_color,
        web_responded,
        icmp_status,
        icmp_color,
        icmp_ok
    ):
        row_color = "#172126" if index % 2 == 0 else self.PANEL
        row = ctk.CTkFrame(self.scrollable, fg_color=row_color, corner_radius=3)
        row.pack(fill="x", pady=2)

        ctk.CTkLabel(
            row,
            text=f"{index:02d}",
            text_color=self.MUTED,
            font=ctk.CTkFont(family="Consolas", size=10)
        ).grid(row=0, column=0, padx=7, pady=7, sticky="ew")

        target_cell = ctk.CTkFrame(row, fg_color="transparent")
        target_cell.grid(row=0, column=1, padx=7, pady=5, sticky="ew")
        ctk.CTkLabel(
            target_cell,
            text=host,
            text_color=self.TEXT,
            font=ctk.CTkFont(size=11, weight="bold"),
            anchor="w"
        ).pack(anchor="w")
        ctk.CTkLabel(
            target_cell,
            text=resolved_ip or "DNS FAILED",
            text_color=self.BLUE if resolved_ip else self.RED,
            font=ctk.CTkFont(family="Consolas", size=9),
            anchor="w"
        ).pack(anchor="w", pady=(2, 0))

        ping_values = (min_ping, avg_ping, max_ping)
        display_values = [
            f"{value:.2f}" if value is not None else "—"
            for value in ping_values
        ]
        for index_in_row, value in enumerate(display_values, 2):
            latency = ping_values[index_in_row - 2]
            color = self.get_ping_color(latency) if latency is not None else self.MUTED
            ctk.CTkLabel(
                row,
                text=value,
                text_color=color,
                font=ctk.CTkFont(family="Consolas", size=10, weight="bold")
            ).grid(row=0, column=index_in_row, padx=6, pady=9, sticky="ew")

        self.add_status_cell(row, 5, web_status, web_color)
        self.add_status_cell(row, 6, icmp_status, icmp_color)
        for column, weight in enumerate(self.column_weights):
            row.grid_columnconfigure(column, weight=weight)

        self.result_rows.append(row)
        self._results_data.append((icmp_ok, web_responded))
        self.update_summary()

    @staticmethod
    def add_status_cell(row, column, text, color):
        ctk.CTkLabel(
            row,
            text=text,
            text_color=color,
            fg_color="#202B30",
            corner_radius=3,
            font=ctk.CTkFont(family="Consolas", size=9, weight="bold")
        ).grid(row=0, column=column, padx=5, pady=6, sticky="ew")

    @classmethod
    def get_ping_color(cls, delay):
        if delay <= 50:
            return cls.GREEN
        if delay <= 150:
            return cls.AMBER
        return cls.RED

    def handle_ping_error(self, error, result_file):
        self._ping_running = False
        self.ping_button.configure(state="normal", text="ЗАПУСТИТЬ ПРОВЕРКУ")
        self.clear_button.configure(state="normal")
        self.paste_button.configure(state="normal")
        self.status_label.configure(text="●  ERROR", text_color=self.RED)
        messagebox.showerror(
            "Ошибка проверки",
            f"Не удалось сохранить результаты:\n{result_file}\n\n{error}"
        )

    def finish_ping(self, total, result_file, cancelled):
        self._ping_running = False
        self.ping_button.configure(state="normal", text="ЗАПУСТИТЬ ПРОВЕРКУ")
        self.clear_button.configure(state="normal")
        self.paste_button.configure(state="normal")
        if cancelled:
            self.status_label.configure(text="●  STOPPED", text_color=self.AMBER)
            message = f"Проверка остановлена. Проверено целей: {total}\n{result_file}"
        else:
            self.status_label.configure(text="●  COMPLETE", text_color=self.GREEN)
            message = f"Проверено целей: {total}\nРезультаты: {result_file}"
        messagebox.showinfo("Готово", message)

    def close_app(self):
        if self._ping_running and not messagebox.askyesno(
            "Проверка выполняется",
            "Остановить проверку и закрыть приложение?"
        ):
            return
        self._closing = True
        self._cancel_ping.set()
        self.destroy()


if __name__ == "__main__":
    app = PingApp()
    app.mainloop()
