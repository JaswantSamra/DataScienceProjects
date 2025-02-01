import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

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

# Computing Z-Score for each stock's return
z_scores = (data['Return'] - data['Return'].mean()) / data['Return'].std()

z_scores_multi = pd.DataFrame(z_scores.abs() > 0, columns=pd.MultiIndex.from_product([['Return_Anomaly'], z_scores.columns]))

data = pd.concat([data, z_scores_multi], axis=1)

# Iterate over tickers and filter anomalies separately
for ticker in data['Return'].columns:  # Ensure you are selecting tickers
    anomalies = data.loc[data[('Return_Anomaly', ticker)] == True, [('Close', ticker), ('Return', ticker), ('Return_Anomaly', ticker)]]
    print(f"\nAnomalies for {ticker}:\n", anomalies)

#print("Columns in data:", data.columns)



# Choose a stock (e.g., TSLA)
ticker = "TSLA"

plt.figure(figsize=(12,6))
plt.plot(data.index, data[('Return', ticker)], label=f"{ticker} Daily Returns", color='blue')
plt.axhline(0, linestyle="dashed", color='gray')  # Add reference line at zero
plt.title(f"{ticker} Stock Daily Returns Over Time")
plt.xlabel("Date")
plt.ylabel("Daily Return")
plt.legend()
plt.show()