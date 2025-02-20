import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from datetime import date, timedelta

start_date = (date.today() - timedelta(days=1825)).strftime("%Y-%m-%d")
end_date = date.today().strftime("%Y-%m-%d")

# Using yfinance to grab historical stock data for Tesla, Apple, Intel, Nvidia, Netflix, Meta, Microsoft, Go Pro, Disney
# and Starbucks
tickers = ["TSLA", "AAPL", "INTC", "NVDA", "NFLX", "META", "MSFT", "GPRO", "DIS", "SBUX"]
data = yf.download(tickers, start=start_date, end=end_date, progress=False)

data.columns = [' '.join(col).strip() for col in data.columns.values]

# Resetting index to bring Date into the Columns
data = data.reset_index()

# Sorting the data by date to ensure chronological order
#data = data.sort_index()

#melting the DataFrame to format it into a long format where each row has a unique combo of Dat, Ticker, and Attributes
data_melted = data.melt(id_vars=['Date'], var_name='Attribute_Ticker', value_name='Value')
data_melted[['Attribute', 'Ticker']] = data_melted['Attribute_Ticker'].str.rsplit(' ', n=1, expand=True)

#pivoting the melted DataFrame to have attributes of Open, High, Low, etc as columns
data_pivoted = data_melted.pivot_table(index=['Date', 'Ticker'], columns='Attribute', values='Value', aggfunc='first')

#resetting to turn multi-index into columns
stock_data = data_pivoted.reset_index()

print(stock_data.head())

sns.set(style="whitegrid")

plt.figure(figsize=(15,6))
for ticker in stock_data['Ticker'].unique():
    subset = stock_data[stock_data['Ticker'] == ticker]
    plt.plot(subset.index, subset['Close'], label=ticker)

plt.title('Close Prices Over Time')
plt.xlabel('Date')
plt.ylabel('Close Price')
plt.legend()
plt.show()

# plotting the trading volume for each ticker over time
plt.figure(figsize=(15, 6))
for ticker in stock_data['Ticker'].unique():
    subset = stock_data[stock_data['Ticker'] == ticker]
    plt.plot(subset.index, subset['Volume'], label=ticker)

plt.title('Trading Volume Over Time')
plt.xlabel('Date')
plt.ylabel('Volume')
plt.legend()
plt.show()






# Checking for missing values
#print(data.isnull().sum())

# Filling missing values (forward-filling the previous day's data)
#data.ffill(inplace=True)

# Drop the rows that are still NaN if they exist after forward filling
#data.dropna(inplace=True)

# Starting analysis of data
# Computing Daily Returns
# Did not work due to "ValueError: Cannot set a DataFrame with multiple columns to the single column Return"
# data['Return'] = data['Close'].pct_change()

# Compute daily returns for all stocks
#returns = data['Close'].pct_change()

#data = pd.concat([data, returns.rename(columns=lambda x: ('Return', x))], axis=1)

# Computing Z-Score for each stock's return
#z_scores = (data['Return'] - data['Return'].mean()) / data['Return'].std()

#z_scores_multi = pd.DataFrame(z_scores.abs() > 0, columns=pd.MultiIndex.from_product([['Return_Anomaly'],
#                                                                                      z_scores.columns]))

#data = pd.concat([data, z_scores_multi], axis=1)

# Iterate over tickers and filter anomalies separately
#for ticker in data['Return'].columns:  # Ensure you are selecting tickers
#    anomalies = data.loc[data[('Return_Anomaly', ticker)] == True, [('Close', ticker), ('Return', ticker),
#                                                                    ('Return_Anomaly', ticker)]]
#    print(f"\nAnomalies for {ticker}:\n", anomalies)

#print("Columns in data:", data.columns)

#ticker = "TSLA"

#plt.figure(figsize=(12,6))
#plt.plot(data.index, data[('Return', ticker)], label=f"{ticker} Daily Returns", color='blue')
#plt.axhline(0, linestyle="dashed", color='gray')  # Add reference line at zero
#plt.title(f"{ticker} Stock Daily Returns Over Time")
#plt.xlabel("Date")
#plt.ylabel("Daily Return")
#plt.legend()
#plt.show()