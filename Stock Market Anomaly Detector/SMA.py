import yfinance as yf
import pandas as pd

# Using yfinance to grab hostorical stock data for Tesla, Apple, Intel, Nvidia, Netflix, Meta, Microsoft, Go Pro, Disney, and Starbucks
tickers = "TSLA", "AAPL", "INTC", "NVDA", "NFLX", "META", "MSFT", "GPRO", "DIS", "SBUX"
data = yf.download(tickers, start="2023-01-01", end="2024-01-01", interval="1d")

# Check the first few rows
#print(data.head())

# Converting the index to datetime, in case it wasn't already done
data.index = pd.to_datetime(data.index)

# Sorting the data by date to ensure chronological order
data = data.sort_index()

# Checking for missing values
#print(data.isnull().sum())

# Filling missing values (forward-filling the previous day's data)
data.ffill(inplace = True)

# Drop the rows that are still NaN if they exist after forward filling
data.dropna(inplace = True)

# Starting analysis of data
# Computing Daily Returns
# Did not work due to "ValueError: Cannot set a DataFrame with multiple columns to the single column Return"
# data['Return'] = data['Close'].pct_change()

# Compute daily returns for all stocks
returns = data['Close'].pct_change()

data = pd.concat([data, returns.rename(columns=lambda x: ('Return', x))], axis=1)

