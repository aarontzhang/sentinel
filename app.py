from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
import yfinance as yf
from pygooglenews import GoogleNews
import anthropic
import os
import json
import re
from dateutil import parser as date_parser
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

load_dotenv()

app = Flask(__name__)

# Security Configuration
app.secret_key = os.getenv('SECRET_KEY', os.urandom(32))
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours

# CSRF Protection
csrf = CSRFProtect(app)

# Rate Limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Load stock domain mappings
with open('stock_domains.json', 'r') as f:
    STOCK_DOMAINS = json.load(f)
    print(f"Loaded {len(STOCK_DOMAINS)} stock domains from JSON file")

def get_db():
    conn = sqlite3.connect('watchlist.db')
    conn.row_factory = sqlite3.Row
    return conn

def sanitize_for_ai_prompt(text):
    """Sanitize user input before including in AI prompts to prevent prompt injection"""
    if not text:
        return ""
    # Remove any control characters and limit length
    sanitized = re.sub(r'[\x00-\x1F\x7F]', '', str(text))
    # Remove potential prompt injection patterns
    sanitized = sanitized.replace('\\n', ' ').replace('\\r', ' ')
    # Limit length
    return sanitized[:500]

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('watchlist'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db()
        user = conn.execute(
            'SELECT * FROM users WHERE username = ?', (username,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']

            conn = get_db()
            conn.execute(
                'UPDATE users SET last_login = ? WHERE id = ?',
                (datetime.now(), user['id'])
            )
            conn.commit()
            conn.close()

            return redirect(url_for('watchlist'))

        return render_template('login.html', error='Invalid username or password')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per hour")
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Validate username
        if not re.match(r'^[a-zA-Z0-9_]{3,50}$', username):
            return render_template('register.html',
                error='Username must be 3-50 characters and contain only letters, numbers, and underscores')

        # Validate password
        if len(password) < 8 or len(password) > 128:
            return render_template('register.html',
                error='Password must be between 8 and 128 characters')

        if password != confirm_password:
            return render_template('register.html',
                error='Passwords do not match')

        # Check if username already exists
        conn = get_db()
        existing_user = conn.execute(
            'SELECT id FROM users WHERE username = ?', (username,)
        ).fetchone()

        if existing_user:
            conn.close()
            return render_template('register.html',
                error='Username already exists')

        # Create new user with hashed password
        password_hash = generate_password_hash(password)

        try:
            conn.execute(
                'INSERT INTO users (username, password_hash, last_login) VALUES (?, ?, ?)',
                (username, password_hash, datetime.now())
            )
            conn.commit()

            # Get the new user
            user = conn.execute(
                'SELECT * FROM users WHERE username = ?', (username,)
            ).fetchone()
            conn.close()

            # Log them in
            session['user_id'] = user['id']
            session['username'] = user['username']

            return redirect(url_for('watchlist'))

        except Exception as e:
            conn.close()
            print(f"Error creating user: {str(e)}")
            return render_template('register.html',
                error='An error occurred. Please try again.')

    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/profile')
@login_required
def profile():
    conn = get_db()
    user = conn.execute(
        'SELECT username, password_hash FROM users WHERE id = ?',
        (session['user_id'],)
    ).fetchone()
    conn.close()

    return render_template('profile.html',
                         username=user['username'],
                         password_hash=user['password_hash'])

@app.route('/watchlist')
@login_required
def watchlist():
    conn = get_db()
    stocks = conn.execute(
        'SELECT * FROM watchlist WHERE user_id = ? ORDER BY date_added DESC',
        (session['user_id'],)
    ).fetchall()
    conn.close()

    return render_template('watchlist.html',
                         username=session['username'],
                         stocks=stocks)

@app.route('/add_stock', methods=['POST'])
@login_required
@limiter.limit("30 per hour")
def add_stock():
    ticker = request.form['ticker'].strip().upper()
    company_name = request.form.get('company_name', '').strip()

    # Validate ticker format (alphanumeric, dots, hyphens only, 1-10 chars)
    if not re.match(r'^[A-Z0-9\.\-]{1,10}$', ticker):
        return render_template('watchlist.html',
                             username=session['username'],
                             stocks=get_db().execute(
                                 'SELECT * FROM watchlist WHERE user_id = ? ORDER BY date_added DESC',
                                 (session['user_id'],)
                             ).fetchall(),
                             error=f'Invalid ticker format: {ticker}. Tickers should be 1-10 characters.')

    # Sanitize company name if provided
    if company_name:
        # Remove any HTML/script tags
        company_name = re.sub(r'<[^>]*>', '', company_name)
        company_name = company_name[:200]  # Limit length

    # Validate ticker using yfinance
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # Check if ticker is valid by checking if it has a symbol
        if not info or 'symbol' not in info or info.get('symbol') != ticker:
            return render_template('watchlist.html',
                                 username=session['username'],
                                 stocks=get_db().execute(
                                     'SELECT * FROM watchlist WHERE user_id = ? ORDER BY date_added DESC',
                                     (session['user_id'],)
                                 ).fetchall(),
                                 error=f'Invalid ticker: {ticker}. Please enter a valid stock ticker.')

        # Auto-fill company name if not provided
        if not company_name and 'longName' in info:
            company_name = info['longName']
        elif not company_name:
            company_name = ticker

    except Exception as e:
        print(f"Error validating ticker {ticker}: {str(e)}")
        return render_template('watchlist.html',
                             username=session['username'],
                             stocks=get_db().execute(
                                 'SELECT * FROM watchlist WHERE user_id = ? ORDER BY date_added DESC',
                                 (session['user_id'],)
                             ).fetchall(),
                             error=f'Could not validate ticker: {ticker}')

    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO watchlist (user_id, stock_ticker, company_name) VALUES (?, ?, ?)',
            (session['user_id'], ticker, company_name)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

    return redirect(url_for('watchlist'))

@app.route('/remove_stock/<ticker>', methods=['POST'])
@login_required
@limiter.limit("30 per hour")
def remove_stock(ticker):
    # Validate ticker format for security
    if not re.match(r'^[A-Z0-9\.\-]{1,10}$', ticker):
        return redirect(url_for('watchlist'))

    conn = get_db()
    conn.execute(
        'DELETE FROM watchlist WHERE user_id = ? AND stock_ticker = ?',
        (session['user_id'], ticker)
    )
    conn.commit()
    conn.close()

    return redirect(url_for('watchlist'))

@app.route('/api/company_logo/<ticker>')
@login_required
@limiter.limit("100 per hour")
def get_company_logo(ticker):
    try:
        # Look up domain in static mapping
        domain = STOCK_DOMAINS.get(ticker.upper())
        print(f"Logo lookup for {ticker}: domain = {domain}")

        if domain:
            # Use Brandfetch CDN with client ID - the #1 Clearbit replacement
            # Free tier: 500k requests/month
            logo_url = f"https://cdn.brandfetch.io/{domain}/w/400/h/400?c=1id6x5GqB6-98lGs42x"
            print(f"Returning logo URL: {logo_url}")
            return jsonify({'logo_url': logo_url})

        print(f"No domain found for {ticker}")
        return jsonify({'logo_url': None})

    except Exception as e:
        print(f"Error fetching logo for {ticker}: {str(e)}")
        return jsonify({'logo_url': None})

@app.route('/api/stock_price/<ticker>')
@login_required
@limiter.limit("60 per hour")
def get_stock_price(ticker):
    try:
        stock = yf.Ticker(ticker)

        # Get last 5 days of data to ensure we have at least 2 trading days
        hist = stock.history(period='5d')

        print(f"Fetching {ticker}: got {len(hist)} rows")

        if hist.empty or len(hist) < 1:
            print(f"Empty data for {ticker}")
            return jsonify({'error': 'Rate limited - wait 2 min'}), 429

        # Get current (most recent) price
        current_price = hist['Close'].iloc[-1]

        # Calculate daily change (today vs yesterday)
        if len(hist) >= 2:
            previous_price = hist['Close'].iloc[-2]
            change_percent = ((current_price - previous_price) / previous_price) * 100
        else:
            # Only one day of data, no change
            change_percent = 0

        return jsonify({
            'ticker': ticker,
            'current_price': round(float(current_price), 2),
            'change_percent': round(float(change_percent), 2)
        })

    except Exception as e:
        print(f"Error fetching {ticker}: {str(e)}")
        return jsonify({'error': 'Service unavailable'}), 500

@app.route('/api/stock_news/<ticker>')
@login_required
@limiter.limit("60 per hour")
def get_stock_news(ticker):
    try:
        conn = get_db()
        stock_info = conn.execute(
            'SELECT company_name FROM watchlist WHERE user_id = ? AND stock_ticker = ?',
            (session['user_id'], ticker)
        ).fetchone()
        conn.close()

        if not stock_info:
            return jsonify({'error': 'Stock not in watchlist'}), 404

        company_name = stock_info['company_name']

        gn = GoogleNews()

        search_query = f"{company_name} stock {ticker}"
        # Get articles from last 2 days to ensure we have enough to filter
        search_results = gn.search(search_query, when='2d')

        # Calculate cutoff time (24 hours ago)
        cutoff_time = datetime.now() - timedelta(hours=24)

        articles = []
        if search_results and 'entries' in search_results:
            for entry in search_results['entries']:
                # Parse the RSS published date - this is the ONLY filter we use
                try:
                    published_date = date_parser.parse(entry.get('published', ''))
                    # Make timezone-naive for comparison
                    if published_date.tzinfo is not None:
                        published_date = published_date.replace(tzinfo=None)

                    # Only include articles published in the last 24 hours
                    if published_date < cutoff_time:
                        print(f"Skipping old article for {ticker}: {entry.get('title', '')[:60]}... (published: {published_date})")
                        continue

                except Exception as e:
                    print(f"Error parsing date for {ticker}: {str(e)}")
                    # Skip articles with unparseable dates
                    continue

                article = {
                    'title': entry.get('title', ''),
                    'description': entry.get('summary', ''),
                    'url': entry.get('link', ''),
                    'published': entry.get('published', ''),
                    'source': entry.get('source', {}).get('title', 'Unknown'),
                }

                if hasattr(entry, 'media_content') and entry.media_content:
                    article['image'] = entry.media_content[0].get('url', '')
                    print(f"Found media_content image for {ticker}")
                elif hasattr(entry, 'links'):
                    for link in entry.links:
                        if link.get('type', '').startswith('image/'):
                            article['image'] = link.get('href', '')
                            print(f"Found link image for {ticker}")
                            break

                if 'image' not in article:
                    article['image'] = None

                articles.append(article)

                # Stop once we have 5 recent articles
                if len(articles) >= 5:
                    break

        print(f"News for {ticker}: {len(articles)} articles, {sum(1 for a in articles if a.get('image'))} with images")

        return jsonify({
            'ticker': ticker,
            'company_name': company_name,
            'articles': articles
        })

    except Exception as e:
        print(f"Error fetching news for {ticker}: {str(e)}")
        return jsonify({'error': 'Failed to fetch news'}), 500

@app.route('/api/stock_summary/<ticker>')
@login_required
@limiter.limit("30 per hour")  # Lower limit for AI endpoints
def get_stock_summary(ticker):
    try:
        api_key = os.getenv('CLAUDE_API_KEY')
        print(f"API Key loaded: {api_key[:20] if api_key else 'None'}...")
        if not api_key:
            return jsonify({'error': 'Claude API key not configured'}), 500

        news_response = get_stock_news(ticker)
        news_data = news_response.get_json()

        if 'error' in news_data or not news_data.get('articles'):
            return jsonify({'summary': 'No recent news available for this stock.'})

        articles = news_data['articles']
        company_name = news_data['company_name']

        # Sanitize inputs before sending to AI to prevent prompt injection
        safe_company_name = sanitize_for_ai_prompt(company_name)
        safe_ticker = sanitize_for_ai_prompt(ticker)

        articles_text = "\n\n".join([
            f"- {sanitize_for_ai_prompt(article['title'])}\n  {sanitize_for_ai_prompt(article['description'])}"
            for article in articles
        ])

        client = anthropic.Anthropic(api_key=api_key)

        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": f"""Analyze these news articles about {safe_company_name} ({safe_ticker}) and create a structured summary.

Break down the news into 2-4 distinct topics/categories (e.g., acquisitions, earnings, product launches, stock performance, regulatory news, etc.).

Format each topic as:
[emoji] **Topic Name**
Brief 1-2 sentence summary of that specific topic.

Use relevant emojis like: 📈 (stock up), 📉 (stock down), 💼 (business deals), 🚀 (launches), ⚖️ (legal/regulatory), 💰 (earnings/revenue), 🏢 (company news), etc.

DO NOT include a title or header. Start directly with the first topic.

Keep it concise and scannable.

Articles:
{articles_text}"""
            }]
        )

        summary = message.content[0].text

        return jsonify({
            'ticker': ticker,
            'company_name': company_name,
            'summary': summary,
            'article_count': len(articles)
        })

    except Exception as e:
        print(f"Error generating summary for {ticker}: {str(e)}")
        return jsonify({'error': 'Failed to generate summary'}), 500

@app.route('/api/stock_sentiment/<ticker>')
@login_required
@limiter.limit("30 per hour")  # Lower limit for AI endpoints
def get_stock_sentiment(ticker):
    try:
        api_key = os.getenv('CLAUDE_API_KEY')
        if not api_key:
            return jsonify({'error': 'Claude API key not configured'}), 500

        # Get news data
        news_response = get_stock_news(ticker)
        news_data = news_response.get_json()

        # Get price data
        price_response = get_stock_price(ticker)
        price_data = price_response.get_json()

        # Handle cases where we don't have data
        if 'error' in news_data or not news_data.get('articles'):
            if 'error' in price_data:
                return jsonify({
                    'sentiment': 'neutral',
                    'article_sentiments': [],
                    'price_change': 0,
                    'current_price': 'N/A'
                })
            else:
                # Have price but no news
                price_change = price_data.get('change_percent', 0)
                sentiment = 'bullish' if price_change > 0 else 'bearish' if price_change < 0 else 'neutral'
                return jsonify({
                    'sentiment': sentiment,
                    'article_sentiments': [],
                    'price_change': price_change,
                    'current_price': price_data.get('current_price')
                })

        articles = news_data['articles']
        company_name = news_data['company_name']

        # Get price change info
        price_change = price_data.get('change_percent', 0) if 'error' not in price_data else 0
        current_price = price_data.get('current_price', 'N/A') if 'error' not in price_data else 'N/A'

        # Sanitize inputs before sending to AI to prevent prompt injection
        safe_company_name = sanitize_for_ai_prompt(company_name)
        safe_ticker = sanitize_for_ai_prompt(ticker)

        # Prepare articles with numbering for sentiment analysis
        numbered_articles = "\n".join([
            f"{i+1}. {sanitize_for_ai_prompt(article['title'])}"
            for i, article in enumerate(articles)
        ])

        client = anthropic.Anthropic(api_key=api_key)

        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": f"""Analyze the sentiment of these news headlines about {safe_company_name} ({safe_ticker}) with stock price at ${current_price} ({price_change:+.2f}% daily change).

Headlines:
{numbered_articles}

Provide analysis in this EXACT format:

OVERALL: [bullish/bearish/neutral]
ARTICLES: [For each article, write the number followed by sentiment: "1:bullish 2:bearish 3:neutral" etc., space-separated]

Bullish = positive for stock price, Bearish = negative for stock price, Neutral = no clear impact."""
            }]
        )

        response_text = message.content[0].text.strip()
        print(f"Sentiment response for {ticker}: {response_text}")

        # Parse the response
        overall_sentiment = 'neutral'
        article_sentiments = ['neutral'] * len(articles)

        for line in response_text.split('\n'):
            if line.startswith('OVERALL:'):
                overall_sentiment = line.replace('OVERALL:', '').strip().lower()
            elif line.startswith('ARTICLES:'):
                articles_line = line.replace('ARTICLES:', '').strip()
                # Parse "1:bullish 2:bearish 3:neutral" format
                for pair in articles_line.split():
                    if ':' in pair:
                        try:
                            idx_str, sent = pair.split(':')
                            idx = int(idx_str) - 1  # Convert to 0-indexed
                            if 0 <= idx < len(articles):
                                article_sentiments[idx] = sent.lower()
                        except:
                            pass

        return jsonify({
            'ticker': ticker,
            'company_name': company_name,
            'sentiment': overall_sentiment,
            'article_sentiments': article_sentiments,
            'price_change': price_change,
            'current_price': current_price,
            'article_count': len(articles)
        })

    except Exception as e:
        print(f"Error generating sentiment for {ticker}: {str(e)}")
        return jsonify({'error': 'Failed to generate sentiment analysis'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)

