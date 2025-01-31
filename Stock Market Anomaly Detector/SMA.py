import yfinance as yf
import pandas as pd

# Using yfinance to grab hostorical stock data for Tesla, Apple, Intel, Nvidia, Netflix, Meta, Microsoft, Go Pro, Disney, and Starbucks
tickers = "TSLA", "AAPL", "INTC", "NVDA", "NFLX", "META", "MSFT", "GPRO", "DIS", "SBUX"
data = yf.download(tickers, start="2023-01-01", end="2024-01-01", interval="1d")

#check the first few rows
print(data.head())