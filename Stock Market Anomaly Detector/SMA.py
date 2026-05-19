"""
Stock Market Anomaly Detector
─────────────────────────────
Pulls historical OHLCV data from one or more free finance providers, computes
two complementary anomaly signals (rolling Z-score on daily returns, and
rolling Z-score on price deviation from its moving average), and presents
the results in a tabbed Tk UI with CSV export.

Run:
    python SMA.py
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Sequence

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg,
    NavigationToolbar2Tk,
)

try:
    from tkcalendar import DateEntry
except ImportError as exc:
    raise SystemExit(
        "Missing dependency 'tkcalendar'. Install with: pip install tkcalendar"
    ) from exc


# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("sma")


# ─── Constants ────────────────────────────────────────────────────────────────

DEFAULT_TICKERS: tuple[str, ...] = (
    "TSLA", "AAPL", "INTC", "NVDA", "NFLX", "META", "MSFT", "GPRO", "DIS", "SBUX",
)
RETURN_WINDOW = 30
PRICE_WINDOW = 20
ANOMALY_THRESHOLD = 2.0

EXPORT_COLUMNS = [
    "Date", "Ticker", "Source", "Open", "High", "Low", "Close", "Volume",
    "MA", "Return", "Return_Z", "Price_Z",
    "Return_Anomaly", "Price_Anomaly",
]


# ─── Data sources ─────────────────────────────────────────────────────────────

class StockDataSource(ABC):
    """Strategy interface for any provider that returns historical OHLCV data."""

    name: str = "unknown"

    @abstractmethod
    def fetch(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        """Return DataFrame indexed by Date with Open/High/Low/Close/Volume."""

    def fetch_all(
        self, tickers: Iterable[str], start: date, end: date,
    ) -> pd.DataFrame:
        """Fetch every ticker in parallel and concat into long-format frame."""
        frames: list[pd.DataFrame] = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(self._fetch_safe, t, start, end): t for t in tickers}
            for fut in as_completed(futures):
                ticker = futures[fut]
                df = fut.result()
                if df is None or df.empty:
                    continue
                df = df.copy()
                df["Ticker"] = ticker
                df["Source"] = self.name
                df.index.name = "Date"
                frames.append(df.reset_index())
        if not frames:
            return pd.DataFrame(
                columns=["Date", "Ticker", "Source", "Open", "High", "Low", "Close", "Volume"],
            )
        return pd.concat(frames, ignore_index=True)

    def _fetch_safe(self, ticker: str, start: date, end: date) -> pd.DataFrame | None:
        try:
            return self.fetch(ticker, start, end)
        except Exception as exc:
            log.warning("source=%s ticker=%s failed: %s", self.name, ticker, exc)
            return None


class YFinanceSource(StockDataSource):
    """Yahoo Finance via the yfinance package (no API key)."""

    name = "yfinance"

    def fetch(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        import yfinance as yf

        df = yf.download(
            ticker, start=start, end=end,
            progress=False, auto_adjust=True,
        )
        if df.empty:
            return df
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df[["Open", "High", "Low", "Close", "Volume"]]


class StooqSource(StockDataSource):
    """Stooq daily CSV endpoint (no API key, US symbols use .US suffix)."""

    name = "stooq"

    def fetch(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        sym = f"{ticker.lower()}.us"
        url = (
            f"https://stooq.com/q/d/l/?s={sym}"
            f"&d1={start:%Y%m%d}&d2={end:%Y%m%d}&i=d"
        )
        df = pd.read_csv(url)
        if df.empty or "Date" not in df.columns:
            return pd.DataFrame()
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        return df[["Open", "High", "Low", "Close", "Volume"]]


SOURCES: dict[str, type[StockDataSource]] = {
    "yfinance": YFinanceSource,
    "stooq": StooqSource,
}


def fetch_data(
    source_keys: Sequence[str], tickers: Sequence[str],
    start: date, end: date,
) -> pd.DataFrame:
    """Pull from one or more sources and concat (long format, with Source column)."""
    parts: list[pd.DataFrame] = []
    for key in source_keys:
        cls = SOURCES.get(key)
        if cls is None:
            log.warning("unknown source: %s", key)
            continue
        log.info("fetching %d tickers from %s ...", len(tickers), key)
        df = cls().fetch_all(tickers, start, end)
        log.info("source=%s returned %d rows", key, len(df))
        if not df.empty:
            parts.append(df)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


# ─── Anomaly detection ────────────────────────────────────────────────────────

def compute_anomalies(stock_data: pd.DataFrame) -> pd.DataFrame:
    """Add Return, Return_Z, MA, Price_Z, Return_Anomaly, Price_Anomaly columns."""
    df = (
        stock_data
        .sort_values(["Source", "Ticker", "Date"])
        .reset_index(drop=True)
        .copy()
    )
    grouped = df.groupby(["Source", "Ticker"], sort=False)

    df["Return"] = grouped["Close"].pct_change()
    df["Return_Z"] = grouped["Return"].transform(
        lambda r: (r - r.rolling(RETURN_WINDOW, min_periods=10).mean())
                  / r.rolling(RETURN_WINDOW, min_periods=10).std()
    )
    df["MA"] = grouped["Close"].transform(
        lambda p: p.rolling(PRICE_WINDOW, min_periods=5).mean()
    )
    df["Price_Z"] = grouped["Close"].transform(
        lambda p: (p - p.rolling(PRICE_WINDOW, min_periods=5).mean())
                  / p.rolling(PRICE_WINDOW, min_periods=5).std()
    )
    df["Return_Anomaly"] = df["Return_Z"].abs() > ANOMALY_THRESHOLD
    df["Price_Anomaly"] = df["Price_Z"].abs() > ANOMALY_THRESHOLD
    return df


# ─── Figure builders ──────────────────────────────────────────────────────────

sns.set_theme(style="whitegrid")


def build_lineplot_figure(
    df: pd.DataFrame, y_col: str, title: str, ylabel: str,
) -> Figure:
    fig = Figure(figsize=(14, 6))
    ax = fig.add_subplot(111)
    multi_source = df["Source"].nunique() > 1
    for (source, ticker), sub in df.groupby(["Source", "Ticker"]):
        label = f"{ticker} [{source}]" if multi_source else ticker
        ax.plot(sub["Date"], sub[y_col], label=label, linewidth=1)
    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel(ylabel)
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    fig.tight_layout()
    return fig


def build_anomaly_grid_figure(
    df: pd.DataFrame, z_col: str, title: str,
    plot_threshold: float = 1.5, marker_cap: float = 8,
) -> Figure:
    pairs = (
        df[["Source", "Ticker"]]
        .drop_duplicates()
        .sort_values(["Ticker", "Source"])
        .to_records(index=False)
    )
    n = len(pairs)
    cols = 5
    rows = max(1, (n + cols - 1) // cols)
    fig = Figure(figsize=(18, max(4, 4 * rows)))
    axes = fig.subplots(rows, cols, squeeze=False).flatten()

    abs_z = df[z_col].abs().dropna()
    vmax = max(
        float(np.nanpercentile(abs_z, 99.5)) if not abs_z.empty else plot_threshold,
        plot_threshold,
    )
    multi_source = df["Source"].nunique() > 1
    scatter = None
    for ax, (source, ticker) in zip(axes, pairs):
        sub = df[(df["Source"] == source) & (df["Ticker"] == ticker)]
        ax.plot(sub["Date"], sub["Close"], color="lightgray", linewidth=1, zorder=1)
        flagged = sub[sub[z_col].abs() > plot_threshold].dropna(subset=[z_col])
        if not flagged.empty:
            sizes = (flagged[z_col].abs().clip(upper=marker_cap) ** 2) * 6
            scatter = ax.scatter(
                flagged["Date"], flagged["Close"],
                c=flagged[z_col], cmap="RdBu_r",
                vmin=-vmax, vmax=vmax,
                s=sizes, edgecolor="k", linewidth=0.3, alpha=0.85, zorder=2,
            )
        label = f"{ticker} [{source}]" if multi_source else ticker
        ax.set_title(label, fontsize=10)
        ax.tick_params(axis="x", rotation=30, labelsize=8)
        ax.tick_params(axis="y", labelsize=8)
    for ax in axes[n:]:
        ax.set_visible(False)

    fig.suptitle(title, fontsize=13)
    fig.tight_layout(rect=[0, 0, 0.95, 0.96])
    if scatter is not None:
        cbar_ax = fig.add_axes([0.96, 0.15, 0.015, 0.7])
        cbar = fig.colorbar(scatter, cax=cbar_ax)
        cbar.set_label(f"{z_col} (− = drop, + = spike)", fontsize=9)
    return fig


# ─── Tk app ───────────────────────────────────────────────────────────────────

@dataclass
class AppState:
    df: pd.DataFrame = field(default_factory=pd.DataFrame)


class AnomalyApp:
    """Single-window app with config panel, tabbed plots, and CSV export."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Stock Market Anomaly Detector")
        self.root.geometry("1500x900")
        self.state = AppState()

        self._build_config_panel()
        self._build_action_bar()
        self._build_notebook()
        self._build_status_bar()

    # ── UI construction ──────────────────────────────────────────────────

    def _build_config_panel(self) -> None:
        frame = ttk.LabelFrame(self.root, text="Configuration", padding=8)
        frame.pack(side="top", fill="x", padx=8, pady=(8, 0))

        ttk.Label(frame, text="Sources:").grid(row=0, column=0, sticky="w")
        self.source_vars = {
            name: tk.BooleanVar(value=(name == "yfinance")) for name in SOURCES
        }
        col = 1
        for name, var in self.source_vars.items():
            ttk.Checkbutton(frame, text=name, variable=var).grid(row=0, column=col, padx=4)
            col += 1

        default_start = date.today() - timedelta(days=1825)
        ttk.Label(frame, text="Start:").grid(row=0, column=col, padx=(16, 4))
        self.start_picker = DateEntry(
            frame, width=12, date_pattern="yyyy-mm-dd",
            year=default_start.year, month=default_start.month, day=default_start.day,
        )
        self.start_picker.grid(row=0, column=col + 1)

        today = date.today()
        ttk.Label(frame, text="End:").grid(row=0, column=col + 2, padx=(16, 4))
        self.end_picker = DateEntry(
            frame, width=12, date_pattern="yyyy-mm-dd",
            year=today.year, month=today.month, day=today.day,
        )
        self.end_picker.grid(row=0, column=col + 3)

        ttk.Label(frame, text="Tickers:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.tickers_entry = ttk.Entry(frame)
        self.tickers_entry.insert(0, ", ".join(DEFAULT_TICKERS))
        self.tickers_entry.grid(
            row=1, column=1, columnspan=col + 1,
            sticky="we", pady=(8, 0), padx=(4, 0),
        )
        frame.columnconfigure(col + 1, weight=1)

        self.load_btn = ttk.Button(frame, text="Load Data", command=self.on_load_clicked)
        self.load_btn.grid(row=1, column=col + 2, columnspan=2, sticky="we", pady=(8, 0), padx=(16, 0))

    def _build_action_bar(self) -> None:
        bar = ttk.Frame(self.root, padding=(8, 4))
        bar.pack(side="top", fill="x")
        self.anomalies_only_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            bar, text="Anomalies only", variable=self.anomalies_only_var,
        ).pack(side="right", padx=(0, 8))
        self.export_btn = ttk.Button(
            bar, text="Export to CSV →",
            command=self.on_export_clicked, state="disabled",
        )
        self.export_btn.pack(side="right")

    def _build_notebook(self) -> None:
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill="both", padx=8, pady=4)
        placeholder = ttk.Frame(self.notebook)
        ttk.Label(
            placeholder,
            text="Choose your sources, date range, and tickers above,\n"
                 "then click \"Load Data\" to fetch and visualize.",
            font=("Segoe UI", 12),
            justify="center",
        ).pack(expand=True)
        self.notebook.add(placeholder, text="Welcome")

    def _build_status_bar(self) -> None:
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(
            self.root, textvariable=self.status_var,
            anchor="w", relief="sunken", padding=4,
        ).pack(side="bottom", fill="x")

    # ── Event handlers ───────────────────────────────────────────────────

    def on_load_clicked(self) -> None:
        sources = [n for n, v in self.source_vars.items() if v.get()]
        if not sources:
            messagebox.showerror("No source selected", "Pick at least one data source.")
            return

        tickers_raw = self.tickers_entry.get().strip()
        tickers = [
            t.strip().upper()
            for t in tickers_raw.replace(";", ",").split(",")
            if t.strip()
        ]
        if not tickers:
            messagebox.showerror("No tickers", "Enter at least one ticker.")
            return

        start = self.start_picker.get_date()
        end = self.end_picker.get_date()
        if start >= end:
            messagebox.showerror("Bad date range", "Start date must be before end date.")
            return

        self.load_btn.configure(state="disabled")
        self.export_btn.configure(state="disabled")
        self._set_status(
            f"Loading {len(tickers)} ticker(s) from {sources} "
            f"({start} → {end}) ..."
        )
        threading.Thread(
            target=self._load_worker,
            args=(sources, tickers, start, end),
            daemon=True,
        ).start()

    def _load_worker(
        self, sources: list[str], tickers: list[str], start: date, end: date,
    ) -> None:
        try:
            raw = fetch_data(sources, tickers, start, end)
            if raw.empty:
                self._set_status("No data returned from any source.", error=True)
                return
            enriched = compute_anomalies(raw)
            self.state.df = enriched
            self.root.after(0, lambda: self._refresh_tabs(enriched, sources, tickers))
        except Exception as exc:
            log.exception("load failed")
            self._set_status(f"Load failed: {exc}", error=True)
        finally:
            self.root.after(0, lambda: self.load_btn.configure(state="normal"))

    def _set_status(self, msg: str, *, error: bool = False) -> None:
        self.root.after(0, lambda: self.status_var.set(msg))
        if error:
            self.root.after(0, lambda: messagebox.showerror("Error", msg))

    def _refresh_tabs(
        self, df: pd.DataFrame, sources: list[str], tickers: list[str],
    ) -> None:
        for tab in self.notebook.tabs():
            self.notebook.forget(tab)

        figures = [
            ("Close Prices", build_lineplot_figure(
                df, "Close", "Close Prices Over Time", "Close Price")),
            ("Volume", build_lineplot_figure(
                df, "Volume", "Trading Volume Over Time", "Volume")),
            ("Return Anomalies", build_anomaly_grid_figure(
                df, "Return_Z",
                f"Return Anomalies (rolling {RETURN_WINDOW}-day Z-score on daily return)",
            )),
            ("Price Anomalies", build_anomaly_grid_figure(
                df, "Price_Z",
                f"Price-Level Anomalies (rolling {PRICE_WINDOW}-day Z-score on price vs. MA)",
            )),
        ]
        for name, fig in figures:
            tab = ttk.Frame(self.notebook)
            self.notebook.add(tab, text=name)
            canvas = FigureCanvasTkAgg(fig, master=tab)
            canvas.draw()
            NavigationToolbar2Tk(canvas, tab).update()
            canvas.get_tk_widget().pack(expand=True, fill="both")

        self.export_btn.configure(state="normal")
        n_anom = int((df["Return_Anomaly"] | df["Price_Anomaly"]).sum())
        self.status_var.set(
            f"Loaded {len(df):,} rows · {len(tickers)} ticker(s) × {len(sources)} source(s) · "
            f"{n_anom:,} anomalies (|Z| > {ANOMALY_THRESHOLD})"
        )

    def on_export_clicked(self) -> None:
        df = self.state.df
        if df.empty:
            messagebox.showwarning("No data", "Load data first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="stock_anomalies.csv",
            title="Save anomalies CSV",
        )
        if not path:
            return
        cols = [c for c in EXPORT_COLUMNS if c in df.columns]
        out = df[cols].sort_values(["Date", "Ticker", "Source"])
        if self.anomalies_only_var.get():
            out = out[out["Return_Anomaly"] | out["Price_Anomaly"]]
        out.to_csv(path, index=False)
        messagebox.showinfo(
            "Export complete",
            f"Saved {len(out):,} rows to:\n{path}\n\n"
            f"Anomalies-only mode: {'on' if self.anomalies_only_var.get() else 'off'}"
        )


def main() -> None:
    root = tk.Tk()
    AnomalyApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
