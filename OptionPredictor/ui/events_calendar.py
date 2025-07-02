# ui/events_calendar.py
# ------------------------------------------------------------
# Offline macro-events calendar for the remainder of 2025.
# ------------------------------------------------------------
import datetime as dt, re, webbrowser
import tkinter as tk
from tkinter import ttk
from tkcalendar import Calendar
from typing import List, Tuple, Dict

# ── colours ─────────────────────────────────────────────────
COLORS = {
    "cpi_real":    "#e67e22",
    "ppi_real":    "#d4ac0d",
    "nfp_real":    "#c0392b",
    "retail_real": "#27ae60",
    "gdp_real":    "#6c3483",
    "fomc_real":   "#8e44ad",
}
TAG_ID = {k: f"{k}Tag" for k in COLORS}

# (date, label, tag, time, url, note)
Event = Tuple[str, str, str, str, str, str]

# ── full static schedule (Jan-Dec 2025) ─────────────────────
PREGENERATED_EVENTS: List[Event] = [
    # ---------- CPI (BLS 08:30 ET) ----------
    ("2025-01-15", "CPI release", "cpi_real", "08:30",
     "https://www.bls.gov/cpi/",  "Key inflation gauge; watch rates / breakevens"),
    ("2025-02-12", "CPI release", "cpi_real", "08:30",
     "https://www.bls.gov/cpi/",  ""),
    ("2025-03-12", "CPI release", "cpi_real", "08:30",
     "https://www.bls.gov/cpi/",  ""),
    ("2025-04-10", "CPI release", "cpi_real", "08:30",
     "https://www.bls.gov/cpi/",  ""),
    ("2025-05-13", "CPI release", "cpi_real", "08:30",
     "https://www.bls.gov/cpi/",  ""),
    ("2025-06-11", "CPI release", "cpi_real", "08:30",
     "https://www.bls.gov/cpi/",  ""),
    ("2025-07-15", "CPI release", "cpi_real", "08:30",
     "https://www.bls.gov/cpi/",  ""),
    ("2025-08-12", "CPI release", "cpi_real", "08:30",
     "https://www.bls.gov/cpi/",  ""),
    ("2025-09-11", "CPI release", "cpi_real", "08:30",
     "https://www.bls.gov/cpi/",  ""),
    ("2025-10-15", "CPI release", "cpi_real", "08:30",
     "https://www.bls.gov/cpi/",  ""),
    ("2025-11-13", "CPI release", "cpi_real", "08:30",
     "https://www.bls.gov/cpi/",  ""),
    ("2025-12-11", "CPI release", "cpi_real", "08:30",
     "https://www.bls.gov/cpi/",  ""),

    # ---------- PPI (BLS 08:30 ET) ----------
    ("2025-01-16", "PPI release", "ppi_real", "08:30",
     "https://www.bls.gov/ppi/", "Wholesale inflation; feeds margin outlook"),
    ("2025-02-13", "PPI release", "ppi_real", "08:30",
     "https://www.bls.gov/ppi/", ""),
    ("2025-03-13", "PPI release", "ppi_real", "08:30",
     "https://www.bls.gov/ppi/", ""),
    ("2025-04-11", "PPI release", "ppi_real", "08:30",
     "https://www.bls.gov/ppi/", ""),
    ("2025-05-15", "PPI release", "ppi_real", "08:30",
     "https://www.bls.gov/ppi/", ""),
    ("2025-06-12", "PPI release", "ppi_real", "08:30",
     "https://www.bls.gov/ppi/", ""),
    ("2025-07-16", "PPI release", "ppi_real", "08:30",
     "https://www.bls.gov/ppi/", ""),
    ("2025-08-14", "PPI release", "ppi_real", "08:30",
     "https://www.bls.gov/ppi/", ""),
    ("2025-09-10", "PPI release", "ppi_real", "08:30",
     "https://www.bls.gov/ppi/", ""),
    ("2025-10-16", "PPI release", "ppi_real", "08:30",
     "https://www.bls.gov/ppi/", ""),
    ("2025-11-13", "PPI release", "ppi_real", "08:30",
     "https://www.bls.gov/ppi/", ""),
    ("2025-12-11", "PPI release", "ppi_real", "08:30",
     "https://www.bls.gov/ppi/", ""),

    # ---------- Non-farm Payrolls (BLS 08:30) ----------
    ("2025-01-10", "Non-farm Payrolls", "nfp_real", "08:30",
     "https://www.bls.gov/ces/", "Biggest single-day vol driver; watch USD & yields"),
    ("2025-02-07", "Non-farm Payrolls", "nfp_real", "08:30",
     "https://www.bls.gov/ces/", ""),
    ("2025-03-07", "Non-farm Payrolls", "nfp_real", "08:30",
     "https://www.bls.gov/ces/", ""),
    ("2025-04-04", "Non-farm Payrolls", "nfp_real", "08:30",
     "https://www.bls.gov/ces/", ""),
    ("2025-05-02", "Non-farm Payrolls", "nfp_real", "08:30",
     "https://www.bls.gov/ces/", ""),
    ("2025-06-06", "Non-farm Payrolls", "nfp_real", "08:30",
     "https://www.bls.gov/ces/", ""),
    ("2025-07-03", "Non-farm Payrolls", "nfp_real", "08:30",
     "https://www.bls.gov/ces/", ""),
    ("2025-08-01", "Non-farm Payrolls", "nfp_real", "08:30",
     "https://www.bls.gov/ces/", ""),
    ("2025-09-05", "Non-farm Payrolls", "nfp_real", "08:30",
     "https://www.bls.gov/ces/", ""),
    ("2025-10-03", "Non-farm Payrolls", "nfp_real", "08:30",
     "https://www.bls.gov/ces/", ""),
    ("2025-11-07", "Non-farm Payrolls", "nfp_real", "08:30",
     "https://www.bls.gov/ces/", ""),
    ("2025-12-05", "Non-farm Payrolls", "nfp_real", "08:30",
     "https://www.bls.gov/ces/", ""),

    # ---------- Retail Sales (Census 08:30) ----------
    ("2025-01-16", "Retail Sales", "retail_real", "08:30",
     "https://www.census.gov/retail/", "Strong proxy for consumer demand"),
    ("2025-02-14", "Retail Sales", "retail_real", "08:30",
     "https://www.census.gov/retail/", ""),
    ("2025-03-17", "Retail Sales", "retail_real", "08:30",
     "https://www.census.gov/retail/", ""),
    ("2025-04-16", "Retail Sales", "retail_real", "08:30",
     "https://www.census.gov/retail/", ""),
    ("2025-05-15", "Retail Sales", "retail_real", "08:30",
     "https://www.census.gov/retail/", ""),
    ("2025-06-16", "Retail Sales", "retail_real", "08:30",
     "https://www.census.gov/retail/", ""),
    ("2025-07-16", "Retail Sales", "retail_real", "08:30",
     "https://www.census.gov/retail/", ""),
    ("2025-08-15", "Retail Sales", "retail_real", "08:30",
     "https://www.census.gov/retail/", ""),
    ("2025-09-12", "Retail Sales", "retail_real", "08:30",
     "https://www.census.gov/retail/", ""),
    ("2025-10-16", "Retail Sales", "retail_real", "08:30",
     "https://www.census.gov/retail/", ""),
    ("2025-11-14", "Retail Sales", "retail_real", "08:30",
     "https://www.census.gov/retail/", ""),
    ("2025-12-16", "Retail Sales", "retail_real", "08:30",
     "https://www.census.gov/retail/", ""),

    # ---------- GDP (BEA 08:30) ----------
    ("2025-01-30", "GDP 2nd est  Q4-24", "gdp_real", "08:30",
     "https://www.bea.gov/news/schedule", ""),
    ("2025-02-27", "GDP 3rd est  Q4-24", "gdp_real", "08:30",
     "https://www.bea.gov/news/schedule", ""),
    ("2025-04-30", "GDP Advance Q1-25", "gdp_real", "08:30",
     "https://www.bea.gov/news/schedule", ""),
    ("2025-05-29", "GDP 2nd est  Q1-25", "gdp_real", "08:30",
     "https://www.bea.gov/news/schedule", ""),
    ("2025-06-26", "GDP 3rd est  Q1-25", "gdp_real", "08:30",
     "https://www.bea.gov/news/schedule", ""),
    ("2025-07-30", "GDP Advance Q2-25", "gdp_real", "08:30",
     "https://www.bea.gov/news/schedule", ""),
    ("2025-08-28", "GDP 2nd est  Q2-25", "gdp_real", "08:30",
     "https://www.bea.gov/news/schedule", ""),
    ("2025-09-25", "GDP 3rd est  Q2-25", "gdp_real", "08:30",
     "https://www.bea.gov/news/schedule", ""),
    ("2025-10-30", "GDP Advance Q3-25", "gdp_real", "08:30",
     "https://www.bea.gov/news/schedule", ""),
    ("2025-11-26", "GDP 2nd est  Q3-25", "gdp_real", "08:30",
     "https://www.bea.gov/news/schedule", ""),
    ("2025-12-19", "GDP 3rd est  Q3-25", "gdp_real", "08:30",
     "https://www.bea.gov/news/schedule", ""),

    # ---------- FOMC two-day meetings (14:00 statement) ----------
    ("2025-01-28", "FOMC meeting (Day 1)", "fomc_real", "—",
     "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", ""),
    ("2025-01-29", "FOMC policy statement", "fomc_real", "14:00",
     "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", ""),
    ("2025-03-18", "FOMC meeting (Day 1)", "fomc_real", "—",
     "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", ""),
    ("2025-03-19", "FOMC policy statement", "fomc_real", "14:00",
     "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", ""),
    ("2025-05-06", "FOMC meeting (Day 1)", "fomc_real", "—",
     "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", ""),
    ("2025-05-07", "FOMC policy statement", "fomc_real", "14:00",
     "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", ""),
    ("2025-06-17", "FOMC meeting (Day 1)", "fomc_real", "—",
     "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", ""),
    ("2025-06-18", "FOMC policy statement", "fomc_real", "14:00",
     "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", ""),
    ("2025-07-29", "FOMC meeting (Day 1)", "fomc_real", "—",
     "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", ""),
    ("2025-07-30", "FOMC policy statement", "fomc_real", "14:00",
     "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", ""),
    ("2025-09-16", "FOMC meeting (Day 1)", "fomc_real", "—",
     "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", ""),
    ("2025-09-17", "FOMC policy statement", "fomc_real", "14:00",
     "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", ""),
    ("2025-10-28", "FOMC meeting (Day 1)", "fomc_real", "—",
     "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", ""),
    ("2025-10-29", "FOMC policy statement", "fomc_real", "14:00",
     "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", ""),
    ("2025-12-09", "FOMC meeting (Day 1)", "fomc_real", "—",
     "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", ""),
    ("2025-12-10", "FOMC policy statement", "fomc_real", "14:00",
     "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", ""),
]

# index: date → list
EVENTS_BY_DATE: Dict[dt.date, List[Event]] = {}
for row in PREGENERATED_EVENTS:
    d = dt.datetime.strptime(row[0], "%Y-%m-%d").date()
    EVENTS_BY_DATE.setdefault(d, []).append(row)

# ─────────────────────────────────────────────────────────────
class EventsCalendar(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("2025 Macro-Events Calendar")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._paint_events()

    # ---------- UI -----------------------------------------------------
    def _build_ui(self):
        outer = ttk.Frame(self, padding=8)
        outer.grid(sticky="nsew")
        self.columnconfigure(0, weight=1); self.rowconfigure(1, weight=1)

        self.cal = Calendar(outer, selectmode="day", date_pattern="yyyy-mm-dd",
                            headersbackground="#2c3e50", headersforeground="white")
        self.cal.grid(row=0, column=0, sticky="ew")
        self.cal.bind("<<CalendarSelected>>", self._on_select)

        # details pane
        lf = ttk.LabelFrame(outer, text="Event details")
        lf.grid(row=1, column=0, sticky="nsew", pady=(8,0))
        self.details = tk.Text(lf, width=60, height=12, wrap="word", state="disabled",
                               font=("Segoe UI", 9))
        self.details.pack(fill="both", expand=True)

        self.details.tag_config("link", foreground="#3498db", underline=True)      
        self.details.tag_bind("link", "<Enter>", lambda e: self.details.config(cursor="hand2")) 
        self.details.tag_bind("link", "<Leave>", lambda e: self.details.config(cursor=""))       


    # ---------- paint calendar ----------------------------------------
    def _paint_events(self):
        for d_str, label, tag, *_ in PREGENERATED_EVENTS:
            d = dt.datetime.strptime(d_str, "%Y-%m-%d").date()
            self.cal.calevent_create(d, label, TAG_ID[tag])
        for tag, color in COLORS.items():
            self.cal.tag_config(TAG_ID[tag], background=color, foreground="white")

    # ── date click ---------------------------------------------------------
    def _on_select(self, _):
        """Populate details pane and make each URL itself clickable."""
        try:
            selected = dt.datetime.strptime(self.cal.get_date(), "%Y-%m-%d").date()
        except ValueError:
            return

        rows = EVENTS_BY_DATE.get(selected, [])

        self.details.configure(state="normal")
        self.details.delete("1.0", "end")

        if not rows:
            self.details.insert("1.0", "No scheduled events.")
            self.details.configure(state="disabled")
            return

        for _d, label, _tag, et_time, url, note in rows:
            # header line
            self.details.insert("end", f"{et_time} ET · {label}\n", ("bold",))

            # Source line — tag **only** the URL substring
            self.details.insert("end", "   Source: ")
            self.details.insert("end", url, ("link",))   # tag applied here
            self.details.insert("end", "\n")

            if note:
                self.details.insert("end", f"   Note: {note}\n")
            self.details.insert("end", "\n")

        # styling & mouse bindings (safe to call every time)
        self.details.tag_config("bold", font=("Segoe UI", 9, "bold"))
        self.details.tag_config("link", foreground="#3498db", underline=True)
        self.details.tag_bind("link", "<Enter>",
                              lambda e: self.details.config(cursor="hand2"))
        self.details.tag_bind("link", "<Leave>",
                              lambda e: self.details.config(cursor=""))
        self.details.tag_bind("link", "<Button-1>", self._open_clicked_link)
        self.details.tag_bind("link", "<Button-3>", self._open_clicked_link)


        self.details.configure(state="disabled")

    # ---------- open link from click ---------------------------------
    def _open_clicked_link(self, event):
        """Open the URL that was actually clicked (works for any tag range)."""
        widget = event.widget                            # == self.details
        idx = widget.index(f"@{event.x},{event.y}")      # text index of click
        # Find the *link*-tag range that covers or precedes idx
        start, end = widget.tag_prevrange("link", idx + "+1c")
        if start and end:
            url = widget.get(start, end)
            if url.startswith("http"):
                webbrowser.open_new_tab(url)

