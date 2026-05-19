# Stock Market Anomaly Detector

A self-contained desktop application that pulls historical equity data from
multiple free providers, flags statistically anomalous price events, and
presents the results through a tabbed interface with CSV export.

## Overview

The detector combines two independent anomaly signals so that distinct types
of unusual market behaviour are caught by separate criteria:

| Signal              | Question it answers                              | Computation                                                                  |
| ------------------- | ------------------------------------------------ | ---------------------------------------------------------------------------- |
| **Return anomaly**  | Was today's *move* unusually large?              | Rolling 30-day Z-score of daily percent return                               |
| **Price anomaly**   | Is the *price level* unusually far from trend?   | Rolling 20-day Z-score of `Close − MA`, where MA is the 20-day moving mean   |

Both signals are computed per `(Source, Ticker)`, so each instrument is its
own statistical baseline and different data providers can be cross-validated
against one another.

## Features

- **Pluggable data layer.** Strategy-pattern interface over Yahoo Finance
  (via `yfinance`) and Stooq's daily CSV endpoint — both free and key-less.
  A new provider is a one-method subclass plus a one-line registration.
- **Configurable at launch.** A calendar widget controls the date range,
  checkboxes select which providers to query, and a single text field
  controls the ticker list. Nothing about the load is hard-coded.
- **Parallel fetching.** Per-ticker downloads run on a `ThreadPoolExecutor`;
  per-ticker failures are logged and the load continues with whatever
  succeeded.
- **Non-blocking UI.** Network and computation run on a daemon thread and
  marshal results back to the Tk event loop via `root.after`, so the window
  stays responsive even when pulling years of history for a dozen symbols.
- **Intensity-encoded anomaly grids.** Each ticker gets its own subplot;
  flagged days are scatter-plotted on the close-price line, coloured on a
  diverging `RdBu_r` map (deep blue = sharp drop, deep red = sharp spike)
  and sized in proportion to `|Z|`.
- **CSV export.** Either the full enriched dataset or anomalies-only, with
  every intermediate column needed to reproduce the flags downstream.

## Installation

Requires Python 3.10 or newer.

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows
# source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
```

## Usage

```bash
python SMA.py
```

1. Tick the source(s) to pull from.
2. Pick a start and end date with the calendar widgets.
3. Edit the comma-separated ticker list if the default set of ten US
   large-caps is not what you want.
4. Click **Load Data**. A status line at the bottom of the window reports
   the row and anomaly counts when the load completes.
5. Switch between **Close Prices**, **Volume**, **Return Anomalies**, and
   **Price Anomalies** using the tabs at the top of the figure area. Each
   tab embeds Matplotlib's navigation toolbar (pan / zoom / save image).
6. Click **Export to CSV →** to save the table. Tick **Anomalies only**
   beforehand if you only want flagged rows in the output.

## Configuration

Detection parameters live at the top of `SMA.py`:

```python
RETURN_WINDOW = 30        # rolling window (trading days) for the return Z-score
PRICE_WINDOW = 20         # rolling window (trading days) for the price Z-score
ANOMALY_THRESHOLD = 2.0   # |Z| > this is flagged as an anomaly in the CSV export
```

The grid-plot rendering threshold (the `|Z|` value below which a dot is
hidden so the chart stays readable) is a separate keyword argument to
`build_anomaly_grid_figure` and defaults to `1.5`.

## Architecture

```
SMA.py
├── StockDataSource (ABC)        ── strategy interface for any provider
│   ├── YFinanceSource           ──   Yahoo Finance backend
│   └── StooqSource              ──   Stooq daily-CSV backend
├── fetch_data()                 ── orchestrates multi-source pulls
├── compute_anomalies()          ── adds Return / Z-score / MA / flag columns
├── build_lineplot_figure()      ── Figure used by the Close and Volume tabs
├── build_anomaly_grid_figure()  ── 2 × 5 grid Figure used by both anomaly tabs
└── AnomalyApp                   ── Tk shell: config panel, tabs, status bar
```

## Adding a data source

Subclass `StockDataSource`, implement `fetch`, and register the class:

```python
class TiingoSource(StockDataSource):
    name = "tiingo"
    def fetch(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        ...  # return a DataFrame indexed by Date with Open/High/Low/Close/Volume

SOURCES["tiingo"] = TiingoSource
```

The new source then appears as a checkbox in the configuration panel; no UI
changes required.

## Export schema

The CSV produced by **Export to CSV** has the following columns:

| Column                       | Type   | Notes                                       |
| ---------------------------- | ------ | ------------------------------------------- |
| `Date`                       | date   | Trading day                                 |
| `Ticker`                     | str    | Symbol                                      |
| `Source`                     | str    | `yfinance` or `stooq`                       |
| `Open` / `High` / `Low` / `Close` | float | OHLC                                  |
| `Volume`                     | int    | Shares traded                               |
| `MA`                         | float  | 20-day moving average of `Close`            |
| `Return`                     | float  | Daily percent change in `Close`             |
| `Return_Z`                   | float  | Rolling 30-day Z-score of `Return`          |
| `Price_Z`                    | float  | Rolling 20-day Z-score of `Close − MA`      |
| `Return_Anomaly`             | bool   | `abs(Return_Z) > ANOMALY_THRESHOLD`         |
| `Price_Anomaly`              | bool   | `abs(Price_Z) > ANOMALY_THRESHOLD`          |

## Methodology notes

- The first `RETURN_WINDOW` − 1 rows per `(Source, Ticker)` have `NaN`
  Z-scores by construction. They never trigger an anomaly flag.
- Rolling Z-scores are intentionally preferred over a single full-history
  Z-score: an instrument that has structurally changed volatility (e.g. a
  former growth stock that has matured) would otherwise have its modern
  behaviour benchmarked against a wholly different earlier regime.
- The two signals are complementary, not redundant. A single sharp daily
  move shows up in `Return_Z` and typically clears `Price_Z` quickly. A
  sustained breakout above the 20-day mean shows up persistently in
  `Price_Z` while `Return_Z` may not flag any single day.

## License

MIT — see [`LICENSE`](../LICENSE) in the repository root.
