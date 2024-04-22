import os
from telegram import Update, Bot
from telegram.ext import Application, CallbackContext, CommandHandler
from datetime import datetime, time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
chat_id = os.getenv('TELEGRAM_CHAT_ID')

def fetch_latest_data(db_path='trading_decisions.sqlite'):
    # Connect to the SQLite database
    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # SQL query to fetch the last row based on the highest timestamp
    query = """
    SELECT timestamp, decision, percentage, reason, btc_balance, krw_balance, btc_avg_buy_price, btc_krw_price
    FROM trading_decisions
    ORDER BY timestamp DESC
    LIMIT 2
    """
    cursor.execute(query)
    data = cursor.fetchone()
    conn.close()

    # Format the data into a string
    columns = ['timestamp', 'decision', 'percentage', 'reason', 'btc_balance', 'krw_balance', 'btc_avg_buy_price', 'btc_krw_price']
    formatted_data = "\n".join(f"{col}: {val}" for col, val in zip(columns, data))
    return formatted_data

def send_message(update: Update, context: CallbackContext):
    bot: Bot = context.bot
    message = fetch_latest_data()
    bot.send_message(chat_id=chat_id, text=message)

def main():
    application = Application.builder().token(bot_token).build()

    # Schedule messages to be sent three times a day
    times = ['00:03', '08:03', '20:49']
    for time_str in times:
        scheduled_time = datetime.strptime(time_str, '%H:%M').time()
        application.job_queue.run_daily(send_message, time=scheduled_time, days=(0, 1, 2, 3, 4, 5, 6))

    application.run_polling()

if __name__ == '__main__':
    main()
