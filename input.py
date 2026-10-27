import hashlib
import hmac
import os
import sqlite3
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

DB_NAME = "rent_control.db"
BG = "#F5F6F8"
BLUE = "#1A73E8"
TEXT = "#111827"
MUTED = "#6B7280"
WHITE = "#FFFFFF"
RED = "#DC2626"
GREEN = "#059669"


def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password, salt=None):
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return salt.hex() + "$" + digest.hex()


def verify_password(password, stored):
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 200_000
        ).hex()
        return hmac.compare_digest(candidate, digest_hex)
    except (ValueError, TypeError):
        return False


def init_db():
    with get_db_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS Пользователи (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Логин TEXT NOT NULL UNIQUE,
            ХешПароля TEXT NOT NULL,
            Роль TEXT NOT NULL DEFAULT 'Диспетчер'
        );
        CREATE TABLE IF NOT EXISTS Оборудование (
            КодОборудования INTEGER PRIMARY KEY AUTOINCREMENT,
            Название TEXT NOT NULL UNIQUE,
            СтатусДоступности TEXT NOT NULL DEFAULT 'Свободно',
            Износ REAL NOT NULL DEFAULT 0,
            ПоследнееТО TEXT
        );
        CREATE TABLE IF NOT EXISTS Заказчики (
            КодЗаказчика INTEGER PRIMARY KEY AUTOINCREMENT,
            НазваниеОрганизации TEXT NOT NULL UNIQUE,
            СтатусБлагонадежности TEXT NOT NULL DEFAULT 'Проверен',
            Примечание TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS Заказы_Аренда (
            НомерДокумента INTEGER PRIMARY KEY AUTOINCREMENT,
            ДатаСоставления TEXT NOT NULL,
            КодОборудования INTEGER NOT NULL,
            КодЗаказчика INTEGER NOT NULL,
            ВремяНачала TEXT NOT NULL,
            ВремяОкончания TEXT NOT NULL,
            СуммаАренды REAL NOT NULL DEFAULT 0,
            Предоплата REAL NOT NULL DEFAULT 0,
            СуммаДолга REAL NOT NULL DEFAULT 0,
            Статус TEXT NOT NULL DEFAULT 'В аренде',
            ДатаВозврата TEXT,
            Штраф REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (КодОборудования) REFERENCES Оборудование(КодОборудования),
            FOREIGN KEY (КодЗаказчика) REFERENCES Заказчики(КодЗаказчика)
        );
        CREATE TABLE IF NOT EXISTS Запчасти (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            КодОборудования INTEGER,
            Название TEXT NOT NULL,
            Количество INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (КодОборудования) REFERENCES Оборудование(КодОборудования)
        );
        CREATE TABLE IF NOT EXISTS Расходы (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Дата TEXT NOT NULL,
            Категория TEXT NOT NULL,
            Описание TEXT NOT NULL,
            Сумма REAL NOT NULL
        );
        """)
        # Seed demo data only when tables are empty.
        if conn.execute("SELECT COUNT(*) FROM Оборудование").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO Оборудование (Название, СтатусДоступности, Износ, ПоследнееТО) VALUES (?, ?, ?, ?)",
                [
                    ("Перфоратор Bosch 2-26", "Свободно", 12, "2026-09-12"),
                    ("Виброплита Зубр 120", "Свободно", 8, "2026-09-18"),
                    ("Бетономешалка Б1", "Свободно", 5, "2026-08-30"),
                ],
            )
        if conn.execute("SELECT COUNT(*) FROM Заказчики").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO Заказчики (НазваниеОрганизации, СтатусБлагонадежности, Примечание) VALUES (?, ?, ?)",
                [
                    ("ООО Строитель-М", "Проверен", "Надёжный партнёр"),
                    ("ИП Петров В.А.", "ЗАБЛОКИРОВАН", "Просрочка и повреждение оборудования"),
                ],
            )
        if conn.execute("SELECT COUNT(*) FROM Запчасти").fetchone()[0] == 0:
            equipment = {r["Название"]: r["КодОборудования"] for r in conn.execute("SELECT * FROM Оборудование")}
            conn.executemany(
                "INSERT INTO Запчасти (КодОборудования, Название, Количество) VALUES (?, ?, ?)",
                [
                    (equipment.get("Перфоратор Bosch 2-26"), "Угольные щётки", 15),
                    (equipment.get("Перфоратор Bosch 2-26"), "Патрон SDS-Plus", 3),
                    (equipment.get("Виброплита Зубр 120"), "Ремень привода А-730", 5),
                ],
            )
        if conn.execute("SELECT COUNT(*) FROM Пользователи").fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO Пользователи (Логин, ХешПароля, Роль) VALUES (?, ?, ?)",
                ("admin", hash_password("admin123"), "Директор"),
            )
        conn.commit()


class DispetcherProkatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Диспетчер-Прокат")
        self.root.geometry("1024x650") 
        self.root.configure(bg=BG)
        self.user = None
        self.current_screen = None
        self.tree = None

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", font=("Arial", 10), rowheight=30,
                        background=WHITE, fieldbackground=WHITE, foreground=TEXT)
        style.configure("Treeview.Heading", font=("Arial", 10, "bold"),
                        background="#E9EDF2", relief="flat")
        style.map("Treeview", background=[("selected", "#DCEAFE")],
                  foreground=[("selected", TEXT)])
        self.show_screen_auth()

    def clear_screen(self):
        if self.current_screen is not None:
            self.current_screen.destroy()
        self.current_screen = None
        self.tree = None

    def make_screen(self):
        self.clear_screen()
        self.current_screen = tk.Frame(self.root, bg=BG)
        self.current_screen.pack(fill=tk.BOTH, expand=True)
        return self.current_screen

    def show_screen_auth(self):
        screen = self.make_screen()
        card = tk.Frame(screen, bg=WHITE, highlightthickness=1,
                        highlightbackground="#E5E7EB", padx=42, pady=35)
        card.place(relx=0.5, rely=0.5, anchor=tk.CENTER, width=430, height=440)
        tk.Label(card, text="Диспетчер-Прокат", font=("Arial", 22, "bold"),
                 fg=BLUE, bg=WHITE).pack(pady=(8, 12))
        tk.Label(card, text="Войдите в систему управления арендой",
                 font=("Arial", 10), fg=MUTED, bg=WHITE).pack(pady=(0, 22))

        tk.Label(card, text="Логин", bg=WHITE, fg=TEXT, anchor="w").pack(fill=tk.X)
        login = ttk.Entry(card, font=("Arial", 12))
        login.pack(fill=tk.X, ipady=5, pady=(4, 14))
        tk.Label(card, text="Пароль", bg=WHITE, fg=TEXT, anchor="w").pack(fill=tk.X)
        password = ttk.Entry(card, font=("Arial", 12), show="*")
        password.pack(fill=tk.X, ipady=5, pady=(4, 20))

        def do_login(event=None):
            username, secret = login.get().strip(), password.get()
            if not username or not secret:
                messagebox.showwarning("Авторизация", "Введите логин и пароль.")
                return
            with get_db_connection() as conn:
                row = conn.execute("SELECT * FROM Пользователи WHERE Логин=?", (username,)).fetchone()
            if row and verify_password(secret, row["ХешПароля"]):
                self.user = {"login": row["Логин"], "role": row["Роль"]}
                self.show_screen_journal()
            else:
                messagebox.showerror("Ошибка входа", "Неверный логин или пароль.")

        ttk.Button(card, text="Войти", command=do_login).pack(fill=tk.X, ipady=5)
        ttk.Button(card, text="Зарегистрироваться", command=self.show_screen_register).pack(fill=tk.X, ipady=4, pady=(10, 0))
        tk.Label(card, text="Первый вход: admin / admin123",
                 bg=WHITE, fg=MUTED, font=("Arial", 9)).pack(pady=(16, 0))
        login.focus_set()
        self.root.bind("<Return>", do_login)

    def show_screen_register(self):
        screen = self.make_screen()
        card = tk.Frame(screen, bg=WHITE, padx=40, pady=30,
                        highlightthickness=1, highlightbackground="#E5E7EB")
        card.place(relx=.5, rely=.5, anchor=tk.CENTER, width=440, height=470)
        tk.Label(card, text="Создание аккаунта", font=("Arial", 20, "bold"),
                 bg=WHITE, fg=TEXT).pack(pady=(0, 22))
        entries = {}
        for label, key, masked in [("Логин", "login", False), ("Пароль", "password", True),
                                   ("Повторите пароль", "repeat", True)]:
            tk.Label(card, text=label, bg=WHITE, fg=MUTED, anchor="w").pack(fill=tk.X)
            entry = ttk.Entry(card, show="*" if masked else "", font=("Arial", 12))
            entry.pack(fill=tk.X, ipady=5, pady=(4, 13))
            entries[key] = entry

        def register():
            username = entries["login"].get().strip()
            pw, repeat = entries["password"].get(), entries["repeat"].get()
            if len(username) < 3:
                messagebox.showwarning("Регистрация", "Логин должен содержать не менее 3 символов.")
                return
            if len(pw) < 8:
                messagebox.showwarning("Регистрация", "Пароль должен содержать не менее 8 символов.")
                return
            if pw != repeat:
                messagebox.showwarning("Регистрация", "Пароли не совпадают.")
                return
            try:
                with get_db_connection() as conn:
                    conn.execute("INSERT INTO Пользователи (Логин, ХешПароля, Роль) VALUES (?, ?, 'Диспетчер')",
                                 (username, hash_password(pw)))
                messagebox.showinfo("Регистрация", "Аккаунт создан. Теперь войдите в систему.")
                self.show_screen_auth()
            except sqlite3.IntegrityError:
                messagebox.showerror("Регистрация", "Такой логин уже существует.")

        ttk.Button(card, text="Создать аккаунт", command=register).pack(fill=tk.X, ipady=5, pady=(8, 6))
        ttk.Button(card, text="Назад ко входу", command=self.show_screen_auth).pack(fill=tk.X, ipady=4)

    def render_header_and_sidebar(self, active=0):
        header = tk.Frame(self.current_screen, bg=WHITE, height=62,
                          highlightthickness=1, highlightbackground="#E5E7EB")
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="Диспетчер-Прокат", font=("Arial", 16, "bold"),
                 fg=BLUE, bg=WHITE).pack(side=tk.LEFT, padx=22)
        tk.Label(header, text=datetime.now().strftime("%d.%m.%Y"),
                 font=("Arial", 10), fg=MUTED, bg=WHITE).pack(side=tk.LEFT, padx=10)
        username = self.user["login"] if self.user else "Пользователь"
        role = self.user["role"] if self.user else ""
        tk.Label(header, text=f"{username} · {role}", font=("Arial", 10),
                 fg=TEXT, bg=WHITE).pack(side=tk.RIGHT, padx=22)

        main = tk.Frame(self.current_screen, bg=BG)
        main.pack(fill=tk.BOTH, expand=True)
        sidebar = tk.Frame(main, bg=WHITE, width=225,
                           highlightthickness=1, highlightbackground="#E5E7EB")
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="МЕНЮ СИСТЕМЫ", font=("Arial", 9, "bold"),
                 fg=MUTED, bg=WHITE).pack(anchor="w", padx=18, pady=(22, 10))
        items = [
            ("📋  Журнал заказов", self.show_screen_journal),
            ("🛠  Склад техники", self.show_screen_warehouse),
            ("👥  База клиентов", self.show_screen_blacklist),
            ("🔩  Запчасти", self.show_screen_spare_parts),
            ("📊  Панель директора", self.show_screen_director),
        ]
        for i, (label, command) in enumerate(items):
            tk.Button(sidebar, text=label, command=command, anchor="w",
                      font=("Arial", 10, "bold" if i == active else "normal"),
                      bg="#E8F0FE" if i == active else WHITE,
                      fg=BLUE if i == active else TEXT, relief="flat",
                      padx=14, pady=10, cursor="hand2").pack(fill=tk.X, padx=9, pady=2)
        tk.Button(sidebar, text="🚪  Выйти", command=self.logout, anchor="w",
                  font=("Arial", 10), bg=WHITE, fg=RED, relief="flat",
                  padx=14, pady=10).pack(side=tk.BOTTOM, fill=tk.X, padx=9, pady=12)
        content = tk.Frame(main, bg=BG, padx=24, pady=20)
        content.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        return content

    def logout(self):
        self.user = None
        self.root.unbind("<Return>")
        self.show_screen_auth()

    def page_title(self, parent, title, subtitle=None):
        tk.Label(parent, text=title, font=("Arial", 18, "bold"),
                 fg=TEXT, bg=BG).pack(anchor="w", pady=(0, 4))
        if subtitle:
            tk.Label(parent, text=subtitle, font=("Arial", 10),
                     fg=MUTED, bg=BG).pack(anchor="w", pady=(0, 15))

    def make_tree(self, parent, columns, headings, widths=None, height=15):
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill=tk.BOTH, expand=True)
        tree = ttk.Treeview(frame, columns=columns, show="headings",
                            height=height, selectmode="browse")
        for i, col in enumerate(columns):
            tree.heading(col, text=headings[i])
            tree.column(col, width=(widths[i] if widths else 140),
                        anchor=tk.W if i else tk.CENTER)
        yscroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        xscroll = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    def show_screen_journal(self, filter_status="Все"):
        self.root.unbind("<Return>")
        self.make_screen()
        content = self.render_header_and_sidebar(0)
        self.page_title(content, "Журнал заказов", "Контроль аренды, сроков возврата и задолженности")
        filters = tk.Frame(content, bg=BG)
        filters.pack(fill=tk.X, pady=(0, 12))
        tk.Label(filters, text="Фильтр:", bg=BG, fg=MUTED).pack(side=tk.LEFT, padx=(0, 8))
        for label, value in [("Все", "Все"), ("В аренде", "В аренде"), ("Просрочено", "Просрочено"), ("Закрыто", "Закрыто")]:
            tk.Button(filters, text=label, command=lambda v=value: self.show_screen_journal(v),
                      bg=BLUE if filter_status == value else WHITE,
                      fg=WHITE if filter_status == value else TEXT,
                      relief="flat", padx=12, pady=5).pack(side=tk.LEFT, padx=3)
        cols = ("id", "tool", "client", "start", "end", "debt", "status")
        self.tree = self.make_tree(content, cols,
            ("№ документа", "Оборудование", "Заказчик", "Начало", "Окончание", "Долг, руб.", "Статус"),
            (95, 210, 180, 145, 145, 105, 120))
        self.tree.tag_configure("expired", background="#FEE2E2", foreground="#991B1B")
        self.tree.tag_configure("closed", foreground=MUTED)
        self.tree.bind("<Double-1>", self.on_table_row_click)
        actions = tk.Frame(content, bg=BG)
        actions.pack(fill=tk.X, pady=(12, 0))
        tk.Button(actions, text="＋ Оформить прокат", command=self.show_screen_new_order,
                  bg=BLUE, fg=WHITE, relief="flat", padx=14, pady=8).pack(side=tk.LEFT)
        tk.Button(actions, text="↩ Принять возврат выбранного заказа",
                  command=self.open_selected_return, bg=WHITE, fg=TEXT,
                  relief="flat", padx=14, pady=8).pack(side=tk.LEFT, padx=8)
        self.load_data(filter_status)

    def load_data(self, filter_status="Все"):
        if not self.tree:
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        with get_db_connection() as conn:
            rows = conn.execute("""
                SELECT z.*, o.Название AS Оборудование, c.НазваниеОрганизации AS Клиент
                FROM Заказы_Аренда z
                JOIN Оборудование o ON o.КодОборудования=z.КодОборудования
                JOIN Заказчики c ON c.КодЗаказчика=z.КодЗаказчика
                ORDER BY z.НомерДокумента DESC
            """).fetchall()
        now = datetime.now()
        for row in rows:
            expired = False
            if row["Статус"] == "В аренде":
                try:
                    expired = now > datetime.strptime(row["ВремяОкончания"], "%Y-%m-%d %H:%M")
                except ValueError:
                    pass
            shown_status = "⚠ ПРОСРОЧЕНО" if expired else row["Статус"]
            if filter_status == "В аренде" and row["Статус"] != "В аренде":
                continue
            if filter_status == "Просрочено" and not expired:
                continue
            if filter_status == "Закрыто" and row["Статус"] != "Закрыто":
                continue
            tags = ("expired",) if expired else (("closed",) if row["Статус"] == "Закрыто" else ())
            self.tree.insert("", tk.END, iid=str(row["НомерДокумента"]),
                values=(f"№ {row['НомерДокумента']:04d}", row["Оборудование"], row["Клиент"],
                        row["ВремяНачала"], row["ВремяОкончания"],
                        f"{row['СуммаДолга']:.2f}", shown_status), tags=tags)

    def on_table_row_click(self, event=None):
        self.open_selected_return()

    def open_selected_return(self):
        if not self.tree or not self.tree.selection():
            messagebox.showinfo("Возврат", "Выберите заказ в журнале.")
            return
        selected = self.tree.selection()[0]
        try:
            order_id = int(selected)
        except ValueError:
            messagebox.showerror("Возврат", "Не удалось определить номер заказа.")
            return
        with get_db_connection() as conn:
            row = conn.execute("""
                SELECT z.*, o.Название AS Оборудование, c.НазваниеОрганизации AS Клиент
                FROM Заказы_Аренда z JOIN Оборудование o ON o.КодОборудования=z.КодОборудования
                JOIN Заказчики c ON c.КодЗаказчика=z.КодЗаказчика WHERE z.НомерДокумента=?
            """, (order_id,)).fetchone()
        if not row:
            return
        if row["Статус"] == "Закрыто":
            messagebox.showinfo("Возврат", "Этот заказ уже закрыт.")
            return
        self.show_screen_return_order(order_id)

    def show_screen_new_order(self):
        self.make_screen()
        content = self.render_header_and_sidebar(0)
        self.page_title(content, "Оформление нового проката", "Заполните параметры аренды")
        card = tk.Frame(content, bg=WHITE, padx=25, pady=22,
                        highlightthickness=1, highlightbackground="#E5E7EB")
        card.pack(fill=tk.BOTH, expand=True)
        with get_db_connection() as conn:
            equipment = conn.execute("SELECT * FROM Оборудование WHERE СтатусДоступности='Свободно' ORDER BY Название").fetchall()
            clients = conn.execute("SELECT * FROM Заказчики ORDER BY НазваниеОрганизации").fetchall()
        if not equipment:
            tk.Label(card, text="Нет свободного оборудования. Сначала оформите возврат.",
                     bg=WHITE, fg=RED, font=("Arial", 12, "bold")).pack(anchor="w", pady=10)
        fields = {}
        labels = [
            ("Оборудование", "equipment"),
            ("Заказчик", "client"),
            ("Начало аренды (ГГГГ-ММ-ДД ЧЧ:ММ)", "start"),
            ("Окончание аренды (ГГГГ-ММ-ДД ЧЧ:ММ)", "end"),
            ("Стоимость аренды, руб.", "price"),
            ("Предоплата, руб.", "prepay"),
        ]
        for label, key in labels:
            tk.Label(card, text=label, bg=WHITE, fg=MUTED, font=("Arial", 10, "bold")).pack(anchor="w", pady=(7, 3))
            if key == "equipment":
                values = [f"{r['КодОборудования']} | {r['Название']}" for r in equipment]
                widget = ttk.Combobox(card, values=values, state="readonly")
                if values:
                    widget.current(0)
            elif key == "client":
                values = [f"{r['КодЗаказчика']} | {r['НазваниеОрганизации']} [{r['СтатусБлагонадежности']}]" for r in clients]
                widget = ttk.Combobox(card, values=values, state="readonly")
                if values:
                    widget.current(0)
            else:
                widget = ttk.Entry(card)
                if key == "start":
                    widget.insert(0, datetime.now().strftime("%Y-%m-%d %H:%M"))
                elif key == "end":
                    widget.insert(0, (datetime.now()).strftime("%Y-%m-%d") + " 18:00")
                elif key == "price":
                    widget.insert(0, "1000")
                elif key == "prepay":
                    widget.insert(0, "0")
            widget.pack(fill=tk.X, ipady=3)
            fields[key] = widget

        def save():
            try:
                if not equipment:
                    raise ValueError("Нет свободного оборудования.")
                equip_text = fields["equipment"].get()
                client_text = fields["client"].get()
                if not equip_text or not client_text:
                    raise ValueError("Выберите оборудование и заказчика.")
                equipment_id = int(equip_text.split("|", 1)[0].strip())
                client_id = int(client_text.split("|", 1)[0].strip())
                start = datetime.strptime(fields["start"].get().strip(), "%Y-%m-%d %H:%M")
                end = datetime.strptime(fields["end"].get().strip(), "%Y-%m-%d %H:%M")
                price = float(fields["price"].get().replace(",", "."))
                prepay = float(fields["prepay"].get().replace(",", "."))
                if end <= start:
                    raise ValueError("Время окончания должно быть позже начала.")
                if price < 0 or prepay < 0 or prepay > price:
                    raise ValueError("Проверьте стоимость и предоплату. Предоплата не может превышать стоимость.")
                with get_db_connection() as conn:
                    client = conn.execute("SELECT * FROM Заказчики WHERE КодЗаказчика=?", (client_id,)).fetchone()
                    tool = conn.execute("SELECT * FROM Оборудование WHERE КодОборудования=?", (equipment_id,)).fetchone()
                    if not tool or tool["СтатусДоступности"] != "Свободно":
                        raise ValueError("Оборудование уже недоступно.")
                    if not client or "БЛОКИРОВАН" in client["СтатусБлагонадежности"].upper():
                        raise ValueError("Заказчик заблокирован и не может оформить аренду.")
                    overlap = conn.execute("""
                        SELECT COUNT(*) FROM Заказы_Аренда
                        WHERE КодОборудования=? AND Статус='В аренде'
                        AND ВремяНачала < ? AND ВремяОкончания > ?
                    """, (equipment_id, end.strftime("%Y-%m-%d %H:%M"),
                          start.strftime("%Y-%m-%d %H:%M"))).fetchone()[0]
                    if overlap:
                        raise ValueError("На это время уже есть активная аренда.")
                    conn.execute("""
                        INSERT INTO Заказы_Аренда
                        (ДатаСоставления, КодОборудования, КодЗаказчика, ВремяНачала,
                         ВремяОкончания, СуммаАренды, Предоплата, СуммаДолга, Статус)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'В аренде')
                    """, (datetime.now().strftime("%Y-%m-%d"), equipment_id, client_id,
                          start.strftime("%Y-%m-%d %H:%M"), end.strftime("%Y-%m-%d %H:%M"),
                          price, prepay, price - prepay))
                    conn.execute("UPDATE Оборудование SET СтатусДоступности='В аренде' WHERE КодОборудования=?", (equipment_id,))
                messagebox.showinfo("Заказ создан", "Аренда сохранена в базе данных.")
                self.show_screen_journal()
            except ValueError as exc:
                messagebox.showwarning("Проверьте данные", str(exc))
            except sqlite3.Error as exc:
                messagebox.showerror("Ошибка базы данных", str(exc))

        buttons = tk.Frame(card, bg=WHITE)
        buttons.pack(anchor="w", pady=18)
        tk.Button(buttons, text="💾 Сохранить заказ", command=save, bg=BLUE, fg=WHITE,
                  relief="flat", padx=18, pady=8).pack(side=tk.LEFT)
        tk.Button(buttons, text="Отмена", command=self.show_screen_journal, bg="#E5E7EB",
                  fg=TEXT, relief="flat", padx=18, pady=8).pack(side=tk.LEFT, padx=8)

    def show_screen_return_order(self, order_id):
        self.make_screen()
        content = self.render_header_and_sidebar(0)
        self.page_title(content, "Приём оборудования", "Проверьте состояние и закройте заказ")
        with get_db_connection() as conn:
            row = conn.execute("""
                SELECT z.*, o.Название AS Оборудование, o.КодОборудования,
                       c.НазваниеОрганизации AS Клиент
                FROM Заказы_Аренда z JOIN Оборудование o ON o.КодОборудования=z.КодОборудования
                JOIN Заказчики c ON c.КодЗаказчика=z.КодЗаказчика
                WHERE z.НомерДокумента=?
            """, (order_id,)).fetchone()
        if not row:
            messagebox.showerror("Ошибка", "Заказ не найден.")
            self.show_screen_journal()
            return
        card = tk.Frame(content, bg=WHITE, padx=25, pady=22,
                        highlightthickness=1, highlightbackground="#E5E7EB")
        card.pack(fill=tk.BOTH, expand=True)
        for label, value in [
            ("Номер заказа", f"№ {order_id:04d}"),
            ("Оборудование", row["Оборудование"]),
            ("Заказчик", row["Клиент"]),
            ("Окончание аренды", row["ВремяОкончания"]),
            ("Текущий долг", f"{row['СуммаДолга']:.2f} руб."),
        ]:
            tk.Label(card, text=f"{label}: {value}", bg=WHITE, fg=TEXT,
                     font=("Arial", 11, "bold" if label == "Текущий долг" else "normal")).pack(anchor="w", pady=4)
        tk.Label(card, text="Фактический износ оборудования (%)", bg=WHITE,
                 fg=MUTED, font=("Arial", 10, "bold")).pack(anchor="w", pady=(20, 3))
        wear_entry = ttk.Entry(card)
        wear_entry.insert(0, "0")
        wear_entry.pack(fill=tk.X, ipady=4)
        tk.Label(card, text="Дополнительные расходы / штраф, руб.", bg=WHITE,
                 fg=MUTED, font=("Arial", 10, "bold")).pack(anchor="w", pady=(12, 3))
        penalty_entry = ttk.Entry(card)
        penalty_entry.insert(0, "0")
        penalty_entry.pack(fill=tk.X, ipady=4)
        total_label = tk.Label(card, text="", bg=WHITE, fg=TEXT, font=("Arial", 12, "bold"))
        total_label.pack(anchor="w", pady=15)

        def update_total(*_):
            try:
                total = float(row["СуммаДолга"]) + float(penalty_entry.get().replace(",", "."))
                total_label.config(text=f"Итог к оплате: {total:.2f} руб.")
            except ValueError:
                total_label.config(text="Проверьте сумму штрафа.")

        penalty_entry.bind("<KeyRelease>", update_total)
        update_total()

        def close_order():
            try:
                wear = float(wear_entry.get().replace(",", "."))
                penalty = float(penalty_entry.get().replace(",", "."))
                if not 0 <= wear <= 100:
                    raise ValueError("Износ должен быть от 0 до 100%.")
                if penalty < 0:
                    raise ValueError("Штраф не может быть отрицательным.")
                with get_db_connection() as conn:
                    current = conn.execute("SELECT Статус FROM Заказы_Аренда WHERE НомерДокумента=?", (order_id,)).fetchone()
                    if not current or current["Статус"] != "В аренде":
                        raise ValueError("Заказ уже закрыт или не найден.")
                    conn.execute("""
                        UPDATE Заказы_Аренда
                        SET Статус='Закрыто', ДатаВозврата=?, Штраф=?,
                            СуммаДолга=СуммаДолга+?
                        WHERE НомерДокумента=?
                    """, (datetime.now().strftime("%Y-%m-%d %H:%M"), penalty, penalty, order_id))
                    conn.execute("UPDATE Оборудование SET СтатусДоступности='Свободно', Износ=? , ПоследнееТО=? WHERE КодОборудования=?",
                                 (wear, datetime.now().strftime("%Y-%m-%d"), row["КодОборудования"]))
                messagebox.showinfo("Возврат оформлен", f"Заказ №{order_id} закрыт. Итог к оплате: {float(row['СуммаДолга']) + penalty:.2f} руб.")
                self.show_screen_journal()
            except ValueError as exc:
                messagebox.showwarning("Проверьте данные", str(exc))
            except sqlite3.Error as exc:
                messagebox.showerror("Ошибка базы данных", str(exc))

        tk.Button(card, text="Провести оплату и закрыть заказ", command=close_order,
                  bg=GREEN, fg=WHITE, relief="flat", padx=18, pady=9).pack(anchor="w", pady=(6, 0))

    def show_screen_warehouse(self):
        self.make_screen()
        content = self.render_header_and_sidebar(1)
        
        # 1. Заголовок страницы
        tk.Label(content, text="Склад техники", font=("Arial", 18, "bold"), fg=TEXT, bg=BG).pack(anchor="w", pady=(0, 4))
        tk.Label(content, text="Состояние оборудования, износ и обслуживание", font=("Arial", 10), fg=MUTED, bg=BG).pack(anchor="w", pady=(0, 10))

        # 2. Кнопки (Сразу под заголовком, чтобы не скрывались)
        buttons_frame = tk.Frame(content, bg=BG)
        buttons_frame.pack(fill=tk.X, pady=(0, 15))

        def add_equipment():
            win = tk.Toplevel(self.root)
            win.title("Добавить оборудование")
            win.configure(bg=WHITE)
            win.geometry("440x220")
            win.resizable(False, False)
            win.transient(self.root)
            win.grab_set()

            tk.Label(win, text="Название оборудования", bg=WHITE, fg=MUTED, anchor="w").pack(fill=tk.X, padx=20, pady=(18, 3))
            name_entry = ttk.Entry(win, font=("Arial", 12))
            name_entry.pack(fill=tk.X, padx=20, ipady=4)

            def save_equipment():
                value = name_entry.get().strip()
                if not value:
                    messagebox.showwarning("Склад", "Введите название оборудования.", parent=win)
                    return
                try:
                    with get_db_connection() as conn:
                        conn.execute("INSERT INTO Оборудование (Название, СтатусДоступности) VALUES (?, 'Свободно')", (value,))
                    win.destroy()
                    messagebox.showinfo("Склад", "Оборудование добавлено.")
                    self.show_screen_warehouse()
                except sqlite3.IntegrityError:
                    messagebox.showerror("Склад", "Такое оборудование уже есть.", parent=win)

            btn_frame = tk.Frame(win, bg=WHITE)
            btn_frame.pack(fill=tk.X, padx=20, pady=16)
            tk.Button(btn_frame, text="💾 Сохранить", command=save_equipment, bg=BLUE, fg=WHITE, relief="flat", padx=16, pady=7).pack(side=tk.LEFT)
            tk.Button(btn_frame, text="Отмена", command=win.destroy, bg="#E5E7EB", fg=TEXT, relief="flat", padx=16, pady=7).pack(side=tk.LEFT, padx=8)
            
            # УБРАЛ bind("<Return>") чтобы не было случайных срабатываний, 
            # работает только по клику на кнопку
            name_entry.focus_set()

        def delete_equipment():
            if not tree.selection():
                messagebox.showinfo("Удаление", "Выберите оборудование в таблице.")
                return
            eq_id = int(tree.selection()[0])
            values = tree.item(tree.selection()[0], "values")
            name = values[1] if len(values) > 1 else f"ID {eq_id}"

            with get_db_connection() as conn:
                # Проверяем, не в аренде ли оборудование
                status = conn.execute("SELECT СтатусДоступности FROM Оборудование WHERE КодОборудования=?", (eq_id,)).fetchone()
                if status and status["СтатусДоступности"] == "В аренде":
                    messagebox.showwarning("Удаление", f"Нельзя удалить «{name}»: оборудование сейчас в аренде.")
                    return
                
                # Проверяем историю заказов
                orders_count = conn.execute("SELECT COUNT(*) FROM Заказы_Аренда WHERE КодОборудования=?", (eq_id,)).fetchone()[0]
                if orders_count > 0:
                    messagebox.showwarning("Удаление", f"Нельзя удалить «{name}»: у оборудования есть история заказов ({orders_count} шт).")
                    return

            if not messagebox.askyesno("Удаление", f"Удалить оборудование «{name}»?\nДействие необратимо."):
                return
            try:
                with get_db_connection() as conn:
                    conn.execute("DELETE FROM Оборудование WHERE КодОборудования=?", (eq_id,))
                messagebox.showinfo("Удаление", f"Оборудование «{name}» удалено.")
                self.show_screen_warehouse()
            except sqlite3.Error as exc:
                messagebox.showerror("Ошибка базы данных", str(exc))

        tk.Button(buttons_frame, text="＋ Добавить оборудование", command=add_equipment, bg=BLUE, fg=WHITE, relief="flat", padx=16, pady=8).pack(side=tk.LEFT)
        tk.Button(buttons_frame, text="🗑 Удалить выбранное оборудование", command=delete_equipment, bg=RED, fg=WHITE, relief="flat", padx=16, pady=8).pack(side=tk.LEFT, padx=8)

        # 3. Таблица (занимает оставшееся место)
        table_frame = tk.Frame(content, bg=BG)
        table_frame.pack(fill=tk.BOTH, expand=True)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        cols = ("id", "name", "status", "wear", "service")
        tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse", height=10)
        
        headings = ("Инв. номер", "Наименование", "Статус", "Износ", "Последнее ТО")
        widths = (100, 300, 150, 100, 150)
        
        for i, col in enumerate(cols):
            tree.heading(col, text=headings[i])
            tree.column(col, width=widths[i], anchor=tk.W if i else tk.CENTER)
            
        yscroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=tree.yview)
        xscroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        
        # Загрузка данных
        with get_db_connection() as conn:
            rows = conn.execute("SELECT * FROM Оборудование ORDER BY КодОборудования").fetchall()
        for r in rows:
            tree.insert("", tk.END,
                iid=str(r["КодОборудования"]),
                values=(f"EQ-{r['КодОборудования']:03d}", r["Название"],
                        r["СтатусДоступности"], f"{r['Износ']:.1f}%", r["ПоследнееТО"] or "—"))

    def show_screen_blacklist(self):
        self.make_screen()
        content = self.render_header_and_sidebar(2)

        tk.Label(content, text="База клиентов", font=("Arial", 18, "bold"), fg=TEXT, bg=BG).pack(anchor="w", pady=(0, 4))
        tk.Label(content, text="Реестр заказчиков и статусов благонадёжности", font=("Arial", 10), fg=MUTED, bg=BG).pack(anchor="w", pady=(0, 10))

        buttons_frame = tk.Frame(content, bg=BG)
        buttons_frame.pack(fill=tk.X, pady=(0, 15))

        def add_client():
            win = tk.Toplevel(self.root)
            win.title("Добавить клиента")
            win.configure(bg=WHITE)
            win.geometry("440x320")
            win.resizable(False, False)
            win.transient(self.root)
            win.grab_set()

            tk.Label(win, text="Название организации / ФИО", bg=WHITE, fg=MUTED, anchor="w").pack(fill=tk.X, padx=20, pady=(18, 3))
            name_entry = ttk.Entry(win, font=("Arial", 12))
            name_entry.pack(fill=tk.X, padx=20, ipady=4)

            tk.Label(win, text="Статус благонадёжности", bg=WHITE, fg=MUTED, anchor="w").pack(fill=tk.X, padx=20, pady=(12, 3))
            status_box = ttk.Combobox(win, values=("Проверен", "На проверке", "ЗАБЛОКИРОВАН"), state="readonly", font=("Arial", 11))
            status_box.current(0)
            status_box.pack(fill=tk.X, padx=20, ipady=3)

            tk.Label(win, text="Примечание", bg=WHITE, fg=MUTED, anchor="w").pack(fill=tk.X, padx=20, pady=(12, 3))
            note_entry = ttk.Entry(win, font=("Arial", 12))
            note_entry.pack(fill=tk.X, padx=20, ipady=4)

            def save_client():
                value = name_entry.get().strip()
                if not value:
                    messagebox.showwarning("Клиенты", "Введите название клиента.", parent=win)
                    return
                try:
                    with get_db_connection() as conn:
                        conn.execute(
                            "INSERT INTO Заказчики (НазваниеОрганизации, СтатусБлагонадежности, Примечание) VALUES (?, ?, ?)",
                            (value, status_box.get(), note_entry.get().strip()))
                    win.destroy()
                    messagebox.showinfo("Клиенты", "Клиент добавлен.")
                    self.show_screen_blacklist()
                except sqlite3.IntegrityError:
                    messagebox.showerror("Клиенты", "Такой клиент уже существует.", parent=win)

            btn_frame = tk.Frame(win, bg=WHITE)
            btn_frame.pack(fill=tk.X, padx=20, pady=16)
            tk.Button(btn_frame, text="💾 Сохранить", command=save_client, bg=BLUE, fg=WHITE, relief="flat", padx=16, pady=7).pack(side=tk.LEFT)
            tk.Button(btn_frame, text="Отмена", command=win.destroy, bg="#E5E7EB", fg=TEXT, relief="flat", padx=16, pady=7).pack(side=tk.LEFT, padx=8)
            
            # УБРАЛ bind("<Return>") 
            name_entry.focus_set()

        def delete_client():
            if not tree.selection():
                messagebox.showinfo("Удаление", "Выберите клиента в таблице.")
                return
            client_id = int(tree.selection()[0])
            values = tree.item(tree.selection()[0], "values")
            name = values[1] if len(values) > 1 else f"ID {client_id}"

            with get_db_connection() as conn:
                orders_count = conn.execute("SELECT COUNT(*) FROM Заказы_Аренда WHERE КодЗаказчика=?", (client_id,)).fetchone()[0]

            if orders_count > 0:
                messagebox.showwarning("Удаление", f"Нельзя удалить «{name}»: у клиента {orders_count} заказ(ов) в истории.\nСначала удалите связанные заказы или отметьте клиента как ЗАБЛОКИРОВАННЫЙ.")
                return

            if not messagebox.askyesno("Удаление", f"Удалить клиента «{name}»?\nДействие необратимо."):
                return
            try:
                with get_db_connection() as conn:
                    conn.execute("DELETE FROM Заказчики WHERE КодЗаказчика=?", (client_id,))
                messagebox.showinfo("Удаление", f"Клиент «{name}» удалён.")
                self.show_screen_blacklist()
            except sqlite3.Error as exc:
                messagebox.showerror("Ошибка базы данных", str(exc))

        tk.Button(buttons_frame, text="＋ Добавить клиента", command=add_client, bg=BLUE, fg=WHITE, relief="flat", padx=16, pady=8).pack(side=tk.LEFT)
        tk.Button(buttons_frame, text="🗑 Удалить выбранного клиента", command=delete_client, bg=RED, fg=WHITE, relief="flat", padx=16, pady=8).pack(side=tk.LEFT, padx=8)

        table_frame = tk.Frame(content, bg=BG)
        table_frame.pack(fill=tk.BOTH, expand=True)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        cols = ("id", "name", "status", "orders", "debt", "note")
        tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse", height=10)
        
        headings = ("ID", "Организация / ФИО", "Статус", "Всего заказов", "Долг, руб.", "Примечание")
        widths = (60, 230, 150, 120, 120, 260)
        
        for i, col in enumerate(cols):
            tree.heading(col, text=headings[i])
            tree.column(col, width=widths[i], anchor=tk.W if i else tk.CENTER)
            
        yscroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=tree.yview)
        xscroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        
        tree.tag_configure("blocked", background="#FEE2E2", foreground="#991B1B")

        with get_db_connection() as conn:
            rows = conn.execute("""
                SELECT c.*, COUNT(z.НомерДокумента) AS КолЗаказов,
                       COALESCE(SUM(CASE WHEN z.Статус='В аренде' THEN z.СуммаДолга ELSE 0 END),0) AS Долг
                FROM Заказчики c LEFT JOIN Заказы_Аренда z ON z.КодЗаказчика=c.КодЗаказчика
                GROUP BY c.КодЗаказчика ORDER BY c.НазваниеОрганизации
            """).fetchall()
        for r in rows:
            blocked = "БЛОКИРОВАН" in r["СтатусБлагонадежности"].upper()
            tree.insert("", tk.END,
                iid=str(r["КодЗаказчика"]),
                values=(r["КодЗаказчика"], r["НазваниеОрганизации"],
                        r["СтатусБлагонадежности"], r["КолЗаказов"],
                        f"{r['Долг']:.2f}", r["Примечание"] or "—"),
                tags=("blocked",) if blocked else ())

    def show_screen_spare_parts(self):
        self.make_screen()
        content = self.render_header_and_sidebar(3)
        self.page_title(content, "Справочник запчастей", "Совместимые комплектующие и остатки")
        cols = ("equipment", "part", "stock")
        tree = self.make_tree(content, cols, ("Модель оборудования", "Название запчасти", "Количество"),
                              (320, 320, 120))
        with get_db_connection() as conn:
            rows = conn.execute("""
                SELECT o.Название AS Оборудование, p.Название, p.Количество
                FROM Запчасти p LEFT JOIN Оборудование o ON o.КодОборудования=p.КодОборудования
                ORDER BY o.Название, p.Название
            """).fetchall()
        for r in rows:
            tree.insert("", tk.END, values=(r["Оборудование"] or "Общее", r["Название"], r["Количество"]))
        form = tk.Frame(content, bg=BG)
        form.pack(fill=tk.X, pady=12)
        part = ttk.Entry(form, width=32)
        part.pack(side=tk.LEFT, padx=(0, 8), ipady=4)
        part.insert(0, "Название запчасти")
        qty = ttk.Entry(form, width=10)
        qty.pack(side=tk.LEFT, padx=(0, 8), ipady=4)
        qty.insert(0, "1")
        def add_part():
            try:
                name, amount = part.get().strip(), int(qty.get())
                if not name or name == "Название запчасти" or amount < 0:
                    raise ValueError
                with get_db_connection() as conn:
                    conn.execute("INSERT INTO Запчасти (Название, Количество) VALUES (?, ?)", (name, amount))
                self.show_screen_spare_parts()
            except ValueError:
                messagebox.showwarning("Запчасти", "Введите название и целое неотрицательное количество.")
        tk.Button(form, text="＋ Добавить запчасть", command=add_part, bg=BLUE,
                  fg=WHITE, relief="flat", padx=12, pady=7).pack(side=tk.LEFT)

    def show_screen_director(self):
        self.make_screen()
        content = self.render_header_and_sidebar(4)
        self.page_title(content, "Панель директора", "Сводные показатели по аренде и затратам")
        with get_db_connection() as conn:
            totals = conn.execute("""
                SELECT COALESCE(SUM(СуммаАренды),0) AS Доход,
                       COALESCE(SUM(Предоплата),0) AS Предоплаты,
                       COALESCE(SUM(СуммаДолга),0) AS Долг,
                       SUM(CASE WHEN Статус='В аренде' THEN 1 ELSE 0 END) AS Активные,
                       SUM(CASE WHEN Статус='Закрыто' THEN 1 ELSE 0 END) AS Закрытые
                FROM Заказы_Аренда
            """).fetchone()
            costs = conn.execute("SELECT COALESCE(SUM(Сумма),0) FROM Расходы").fetchone()[0]
            equipment_count = conn.execute("SELECT COUNT(*) FROM Оборудование").fetchone()[0]
            client_count = conn.execute("SELECT COUNT(*) FROM Заказчики").fetchone()[0]
            expense_rows = conn.execute("SELECT * FROM Расходы ORDER BY ID DESC").fetchall()
        income = float(totals["Предоплаты"] or 0)
        profit = income - float(costs)
        cards = tk.Frame(content, bg=BG)
        cards.pack(fill=tk.X, pady=(0, 18))
        data = [
            ("ПОЛУЧЕНО ОПЛАТ", f"{income:,.2f} руб.".replace(",", " "), "#D1FAE5", "#065F46"),
            ("РАСХОДЫ", f"{costs:,.2f} руб.".replace(",", " "), "#FEE2E2", "#991B1B"),
            ("РАЗНИЦА", f"{profit:,.2f} руб.".replace(",", " "), "#DBEAFE", "#1D4ED8"),
            ("АКТИВНЫЕ ЗАКАЗЫ", str(totals["Активные"] or 0), "#F3E8FF", "#6B21A8"),
        ]
        for title, value, bg, fg in data:
            box = tk.Frame(cards, bg=bg, padx=16, pady=16)
            box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
            tk.Label(box, text=title, bg=bg, fg=fg, font=("Arial", 9, "bold")).pack(anchor="w")
            tk.Label(box, text=value, bg=bg, fg=fg, font=("Arial", 16, "bold")).pack(anchor="w", pady=(8, 0))
        summary = tk.Frame(content, bg=WHITE, padx=18, pady=16)
        summary.pack(fill=tk.X, pady=(0, 16))
        tk.Label(summary, text=f"Оборудования: {equipment_count}    Клиентов: {client_count}    "
                 f"Закрытых заказов: {totals['Закрытые'] or 0}    Текущий долг по активным заказам: {float(totals['Долг'] or 0):.2f} руб.",
                 bg=WHITE, fg=TEXT, font=("Arial", 11)).pack(anchor="w")
        tk.Label(content, text="Расходы", bg=BG, fg=TEXT, font=("Arial", 13, "bold")).pack(anchor="w", pady=(0, 7))
        tree = self.make_tree(content, ("date", "category", "description", "sum"),
                              ("Дата", "Категория", "Описание", "Сумма, руб."),
                              (130, 150, 400, 130), height=6)
        for r in expense_rows:
            tree.insert("", tk.END, values=(r["Дата"], r["Категория"], r["Описание"], f"{r['Сумма']:.2f}"))
        form = tk.Frame(content, bg=BG)
        form.pack(fill=tk.X, pady=10)
        category = ttk.Combobox(form, values=("ГСМ", "ТО", "Запчасти", "Прочее"), state="readonly", width=12)
        category.current(0)
        category.pack(side=tk.LEFT, padx=(0, 7), ipady=3)
        description = ttk.Entry(form, width=35)
        description.pack(side=tk.LEFT, padx=(0, 7), ipady=4)
        description.insert(0, "Описание расхода")
        amount = ttk.Entry(form, width=12)
        amount.pack(side=tk.LEFT, padx=(0, 7), ipady=4)
        amount.insert(0, "0")
        def add_expense():
            try:
                desc = description.get().strip()
                value = float(amount.get().replace(",", "."))
                if not desc or desc == "Описание расхода" or value <= 0:
                    raise ValueError
                with get_db_connection() as conn:
                    conn.execute("INSERT INTO Расходы (Дата, Категория, Описание, Сумма) VALUES (?, ?, ?, ?)",
                                 (datetime.now().strftime("%Y-%m-%d"), category.get(), desc, value))
                self.show_screen_director()
            except ValueError:
                messagebox.showwarning("Расходы", "Введите описание и сумму больше нуля.")
        tk.Button(form, text="＋ Добавить расход", command=add_expense, bg=BLUE,
                  fg=WHITE, relief="flat", padx=12, pady=7).pack(side=tk.LEFT)

    def check_time_trigger(self):
        try:
            if self.tree and self.current_screen and self.root.winfo_exists():
                pass
        finally:
            if self.root.winfo_exists():
                self.root.after(1000, self.check_time_trigger)


if __name__ == "__main__":
    init_db()
    root = tk.Tk()
    app = DispetcherProkatApp(root)
    root.mainloop()