import os
from dotenv import load_dotenv
load_dotenv()
import pyupbit
import pandas as pd
import pandas_ta as ta
import json
from openai import OpenAI
import schedule
import time
import requests
from datetime import datetime
import sqlite3

# Setup
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
upbit = pyupbit.Upbit(os.getenv("UPBIT_ACCESS_KEY"), os.getenv("UPBIT_SECRET_KEY"))

def initialize_db(db_path='trading_decisions.sqlite'):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME,
                decision TEXT,
                percentage REAL,
                reason TEXT,
                btc_balance REAL,
                krw_balance REAL,
                btc_avg_buy_price REAL,
                btc_krw_price REAL
            );
        ''')
        conn.commit()

def save_decision_to_db(decision, current_status):
    db_path = 'trading_decisions.sqlite'
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
    
        # Parsing current_status from JSON to Python dict
        status_dict = json.loads(current_status)
        current_price = pyupbit.get_orderbook(ticker="KRW-BTC")['orderbook_units'][0]["ask_price"]
        
        # Preparing data for insertion
        data_to_insert = (
            decision.get('decision'),
            decision.get('percentage', 100),  # Defaulting to 100 if not provided
            decision.get('reason', ''),  # Defaulting to an empty string if not provided
            status_dict.get('btc_balance'),
            status_dict.get('krw_balance'),
            status_dict.get('btc_avg_buy_price'),
            current_price
        )
        
        # Inserting data into the database
        cursor.execute('''
            INSERT INTO decisions (timestamp, decision, percentage, reason, btc_balance, krw_balance, btc_avg_buy_price, btc_krw_price)
            VALUES (datetime('now', 'localtime'), ?, ?, ?, ?, ?, ?, ?)
        ''', data_to_insert)
    
        conn.commit()

def fetch_last_decisions(db_path='trading_decisions.sqlite', num_decisions=10):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT timestamp, decision, percentage, reason, btc_balance, krw_balance, btc_avg_buy_price
            FROM decisions
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (num_decisions,))
        decisions = cursor.fetchall()

        if decisions:
            formatted_decisions = []
            for decision in decisions:
                # Converting timestamp to milliseconds since the Unix epoch
                ts = datetime.strptime(decision[0], "%Y-%m-%d %H:%M:%S")
                ts_millis = int(ts.timestamp() * 1000)
                
                formatted_decision = {
                    "timestamp": ts_millis,
                    "decision": decision[1],
                    "percentage": decision[2],
                    "reason": decision[3],
                    "btc_balance": decision[4],
                    "krw_balance": decision[5],
                    "btc_avg_buy_price": decision[6]
                }
                formatted_decisions.append(str(formatted_decision))
            return "\n".join(formatted_decisions)
        else:
            return "No decisions found."

def get_current_status():
    orderbook = pyupbit.get_orderbook(ticker="KRW-BTC")
    print("Orderbook type:", type(orderbook))
    print("Orderbook content:", orderbook)
    current_time = orderbook['timestamp']
    btc_balance = 0
    krw_balance = 0
    btc_avg_buy_price = 0
    balances = upbit.get_balances()
    for b in balances:
        if b['currency'] == "BTC":
            btc_balance = b['balance']
            btc_avg_buy_price = b['avg_buy_price']
        if b['currency'] == "KRW":
            krw_balance = b['balance']

    current_status = {'current_time': current_time, 'orderbook': orderbook, 'btc_balance': btc_balance, 'krw_balance': krw_balance, 'btc_avg_buy_price': btc_avg_buy_price}
    return json.dumps(current_status)

def fetch_and_prepare_data():
   try:
       # Fetch data
       df_daily = pyupbit.get_ohlcv("KRW-BTC", "day", count=30)
       print("Daily data type:", type(df_daily))
       print("Daily data head:", df_daily.head() if df_daily is not None else "None")
       
       df_hourly = pyupbit.get_ohlcv("KRW-BTC", interval="minute60", count=24)
       print("Hourly data type:", type(df_hourly))
       print("Hourly data head:", df_hourly.head() if df_hourly is not None else "None")

       # Define a helper function to add indicators
       def add_indicators(df):
           # Moving Averages
           df['SMA_10'] = ta.sma(df['close'], length=10)
           df['EMA_10'] = ta.ema(df['close'], length=10)

           # RSI
           df['RSI_14'] = ta.rsi(df['close'], length=14)

           # Stochastic Oscillator
           stoch = ta.stoch(df['high'], df['low'], df['close'], k=14, d=3, smooth_k=3)
           df = df.join(stoch)

           # MACD
           ema_fast = df['close'].ewm(span=12, adjust=False).mean()
           ema_slow = df['close'].ewm(span=26, adjust=False).mean()
           df['MACD'] = ema_fast - ema_slow
           df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
           df['MACD_Histogram'] = df['MACD'] - df['Signal_Line']

           # Bollinger Bands
           df['Middle_Band'] = df['close'].rolling(window=20).mean()
           std_dev = df['close'].rolling(window=20).std()
           df['Upper_Band'] = df['Middle_Band'] + (std_dev * 2)
           df['Lower_Band'] = df['Middle_Band'] - (std_dev * 2)

           return df

       # Add indicators to both dataframes
       df_daily = add_indicators(df_daily)
       df_hourly = add_indicators(df_hourly)

       combined_df = pd.concat([df_daily, df_hourly], keys=['daily', 'hourly'])
       print("Combined data type:", type(combined_df))
       print("Combined data shape:", combined_df.shape)
       
       combined_data = combined_df.to_json(orient='split')
       print("JSON data type:", type(combined_data))
       print("JSON data preview:", combined_data[:200])  # 처음 200자만 출력

       return json.dumps(combined_data)
   except Exception as e:
       print(f"Error in fetch_and_prepare_data: {e}")
       return json.dumps({})

def get_news_data():
    url = "https://serpapi.com/search.json?engine=google_news&q=btc&api_key=" + os.getenv("SERPAPI_API_KEY")
    result = "No news data available."

    try:
        response = requests.get(url)
        news_results = response.json()['news_results']

        simplified_news = []
        
        for news_item in news_results:
            if 'stories' in news_item:
                for story in news_item['stories']:
                    timestamp = int(datetime.strptime(story['date'], '%m/%d/%Y, %H:%M %p, %z %Z').timestamp() * 1000)
                    simplified_news.append((story['title'], story.get('source', {}).get('name', 'Unknown source'), timestamp))
            else:
                if news_item.get('date'):
                    timestamp = int(datetime.strptime(news_item['date'], '%m/%d/%Y, %H:%M %p, %z %Z').timestamp() * 1000)
                    simplified_news.append((news_item['title'], news_item.get('source', {}).get('name', 'Unknown source'), timestamp))
                else:
                    simplified_news.append((news_item['title'], news_item.get('source', {}).get('name', 'Unknown source'), 'No timestamp provided'))
        result = str(simplified_news)
    except Exception as e:
        print(f"Error fetching news data: {e}")

    return result

def fetch_fear_and_greed_index(limit=1, date_format=''):
    base_url = "https://api.alternative.me/fng/"
    params = {
        'limit': limit,
        'format': 'json',
        'date_format': date_format
    }
    response = requests.get(base_url, params=params)
    myData = response.json()['data']
    resStr = ""
    for data in myData:
        resStr += str(data)
    return resStr

def get_instructions(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            instructions = file.read()
        return instructions
    except FileNotFoundError:
        print(f"File not found: {file_path}")
    except Exception as e:
        print(f"An error occurred while reading the file {file_path}: {e}")

def analyze_data_with_gpt4(news_data, data_json, last_decisions, fear_and_greed, current_status):
    instructions_path = "instructions_v4.md"
    try:
        instructions = get_instructions(instructions_path)
        if not instructions:
            print("No instructions found.")
            return None
        
        print("Sending request to GPT-4...")
        response = client.chat.completions.create(
            model="gpt-4-turbo",  # Changed from "chatgpt-4o-latest" to "gpt-4"
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": news_data},
                {"role": "user", "content": data_json},
                {"role": "user", "content": last_decisions},
                {"role": "user", "content": fear_and_greed},
                {"role": "user", "content": current_status}
            ],
            response_format={"type":"json_object"}
        )
        print("Received response from GPT-4")
        advice = response.choices[0].message.content
        print(f"GPT-4 advice: {advice}")
        return advice
    except openai.error.APIError as e:
        print(f"OpenAI API returned an API Error: {e}")
    except openai.error.APIConnectionError as e:
        print(f"Failed to connect to OpenAI API: {e}")
    except openai.error.RateLimitError as e:
        print(f"OpenAI API request exceeded rate limit: {e}")
    except Exception as e:
        print(f"Unexpected error in analyzing data with GPT-4: {e}")
    return None

def execute_buy(percentage):
    print("Attempting to buy BTC with a percentage of KRW balance...")
    try:
        krw_balance = upbit.get_balance("KRW")
        amount_to_invest = krw_balance * (percentage / 100)
        if amount_to_invest > 5000:  # Ensure the order is above the minimum threshold
            result = upbit.buy_market_order("KRW-BTC", amount_to_invest * 0.9995)  # Adjust for fees
            print("Buy order successful:", result)
    except Exception as e:
        print(f"Failed to execute buy order: {e}")

def execute_sell(percentage):
    print("Attempting to sell a percentage of BTC...")
    try:
        btc_balance = upbit.get_balance("BTC")
        amount_to_sell = btc_balance * (percentage / 100)
        current_price = pyupbit.get_orderbook(ticker="KRW-BTC")['orderbook_units'][0]["ask_price"]
        if current_price * amount_to_sell > 5000:  # Ensure the order is above the minimum threshold
            result = upbit.sell_market_order("KRW-BTC", amount_to_sell)
            print("Sell order successful:", result)
    except Exception as e:
        print(f"Failed to execute sell order: {e}")

def make_decision_and_execute():
    print("Making decision and executing...")
    try:
        news_data = get_news_data()
        data_json = fetch_and_prepare_data()
        last_decisions = fetch_last_decisions()
        fear_and_greed = fetch_fear_and_greed_index(limit=30)
        current_status = get_current_status()
    except Exception as e:
        print(f"Error in gathering data: {e}")
        return

    max_retries = 5
    retry_delay_seconds = 5
    decision = None
    for attempt in range(max_retries):
        try:
            advice = analyze_data_with_gpt4(news_data, data_json, last_decisions, fear_and_greed, current_status)
            print(f"Raw advice from GPT-4: {advice}")
            if advice:
                decision = json.loads(advice)
                break
            else:
                print("Received empty advice from GPT-4")
        except json.JSONDecodeError as e:
            print(f"JSON parsing failed: {e}. Raw advice: {advice}")
        if attempt < max_retries - 1:  # Don't sleep after the last attempt
            print(f"Retrying in {retry_delay_seconds} seconds...")
            time.sleep(retry_delay_seconds)
        print(f"Attempt {attempt + 2} of {max_retries}")

    if not decision:
        print("Failed to make a decision after maximum retries.")
        return

    try:
        percentage = decision.get('percentage', 100)

        if decision.get('decision') == "buy":
            execute_buy(percentage)
        elif decision.get('decision') == "sell":
            execute_sell(percentage)

        print(f"Decision made: {decision}")
        save_decision_to_db(decision, current_status)
    except Exception as e:
        print(f"Failed to execute the decision or save to DB: {e}")

if __name__ == "__main__":
    initialize_db()
    
    # Schedule the task to run at 00:01
    schedule.every().day.at("00:01").do(make_decision_and_execute)

    # Schedule the task to run at 08:01
    schedule.every().day.at("08:01").do(make_decision_and_execute)

    # Schedule the task to run at 16:01
    schedule.every().day.at("22:12").do(make_decision_and_execute)

    while True:
        schedule.run_pending()
        time.sleep(1)
