from flask import Flask, render_template, request
import sqlite3
import math

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('/home/ubuntu/cryptoauto/trading_decisions.sqlite')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get total number of decisions
    cur.execute("SELECT COUNT(*) FROM decisions")
    total_decisions = cur.fetchone()[0]
    
    # Calculate total pages
    decisions_per_page = 10
    total_pages = math.ceil(total_decisions / decisions_per_page)
    
    # Get current page from query parameter, default to 1
    page = request.args.get('page', 1, type=int)
    
    # Calculate offset
    offset = (page - 1) * decisions_per_page
    
    # Get decisions for current page
    cur.execute("SELECT * FROM decisions ORDER BY timestamp DESC LIMIT ? OFFSET ?", 
                (decisions_per_page, offset))
    decisions = cur.fetchall()
    
    conn.close()
    
    return render_template('index.html', decisions=decisions, page=page, total_pages=total_pages)

if __name__ == '__main__':
    app.run(debug=True)
