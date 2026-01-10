from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
from datetime import datetime, timedelta

# Database configuration - detect environment
DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL:
    import psycopg2
    from psycopg2.extras import RealDictCursor
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
import yfinance as yf
import feedparser
import requests
import anthropic
import os
import json
import re
from dateutil import parser as date_parser
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()

app = Flask(__name__)

# Security Configuration
app.secret_key = os.getenv('SECRET_KEY', os.urandom(32))
# Auto-detect production environment (Vercel or DATABASE_URL set)
IS_PRODUCTION = os.getenv('VERCEL') == '1' or DATABASE_URL is not None
app.config['SESSION_COOKIE_SECURE'] = IS_PRODUCTION  # True in production (HTTPS)
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
    """Get database connection - PostgreSQL in production, SQLite in development"""
    if DATABASE_URL:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    else:
        conn = sqlite3.connect('watchlist.db')
        conn.row_factory = sqlite3.Row
    return conn

def convert_sql_placeholders(sql):
    """Convert SQL placeholders from ? to %s for PostgreSQL"""
    if DATABASE_URL:
        return sql.replace('?', '%s')
    return sql

def search_google_news(query, when='2d'):
    """Search Google News RSS feed - replacement for pygooglenews"""
    try:
        # Google News RSS feed URL
        base_url = 'https://news.google.com/rss/search'
        params = {
            'q': query,
            'hl': 'en-US',
            'gl': 'US',
            'ceid': 'US:en'
        }

        # Add time filter
        if when:
            params['when'] = when

        # Construct URL
        url = f"{base_url}?{'&'.join(f'{k}={requests.utils.quote(str(v))}' for k, v in params.items())}"

        # Fetch and parse RSS feed
        feed = feedparser.parse(url)
        return feed
    except Exception as e:
        print(f"Error fetching Google News: {str(e)}")
        return {'entries': []}

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
            convert_sql_placeholders('SELECT * FROM users WHERE username = ?'), (username,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['password'] = password  # Store for profile view only

            conn = get_db()
            conn.execute(
                convert_sql_placeholders('UPDATE users SET last_login = ? WHERE id = ?'),
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
            convert_sql_placeholders('SELECT id FROM users WHERE username = ?'), (username,)
        ).fetchone()

        if existing_user:
            conn.close()
            return render_template('register.html',
                error='Username already exists')

        # Create new user with hashed password
        password_hash = generate_password_hash(password)

        try:
            conn.execute(
                convert_sql_placeholders('INSERT INTO users (username, password_hash, last_login) VALUES (?, ?, ?)'),
                (username, password_hash, datetime.now())
            )
            conn.commit()

            # Get the new user
            user = conn.execute(
                convert_sql_placeholders('SELECT * FROM users WHERE username = ?'), (username,)
            ).fetchone()
            conn.close()

            # Log them in
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['password'] = password  # Store for profile view only

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
        convert_sql_placeholders('SELECT username, password_hash FROM users WHERE id = ?'),
        (session['user_id'],)
    ).fetchone()
    conn.close()

    return render_template('profile.html',
                         username=user['username'],
                         password_hash=user['password_hash'])

@app.route('/api/get_password')
@login_required
def get_password():
    """Securely retrieve password from session (for profile view only)"""
    password = session.get('password')
    if password:
        return jsonify({'success': True, 'password': password})
    else:
        return jsonify({'success': False, 'message': 'Password not available in session'})

@app.route('/watchlist')
@login_required
def watchlist():
    conn = get_db()
    stocks = conn.execute(
        convert_sql_placeholders('SELECT * FROM watchlist WHERE user_id = ? ORDER BY date_added DESC'),
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
                                 convert_sql_placeholders('SELECT * FROM watchlist WHERE user_id = ? ORDER BY date_added DESC'),
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
                                     convert_sql_placeholders('SELECT * FROM watchlist WHERE user_id = ? ORDER BY date_added DESC'),
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
                                 convert_sql_placeholders('SELECT * FROM watchlist WHERE user_id = ? ORDER BY date_added DESC'),
                                 (session['user_id'],)
                             ).fetchall(),
                             error=f'Could not validate ticker: {ticker}')

    conn = get_db()
    try:
        conn.execute(
            convert_sql_placeholders('INSERT INTO watchlist (user_id, stock_ticker, company_name) VALUES (?, ?, ?)'),
            (session['user_id'], ticker, company_name)
        )
        conn.commit()
    except (sqlite3.IntegrityError if not DATABASE_URL else psycopg2.IntegrityError):
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
        convert_sql_placeholders('DELETE FROM watchlist WHERE user_id = ? AND stock_ticker = ?'),
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
            convert_sql_placeholders('SELECT company_name FROM watchlist WHERE user_id = ? AND stock_ticker = ?'),
            (session['user_id'], ticker)
        ).fetchone()
        conn.close()

        if not stock_info:
            return jsonify({'error': 'Stock not in watchlist'}), 404

        company_name = stock_info['company_name']

        search_query = f"{company_name} stock {ticker}"
        # Get articles from last 2 days to ensure we have enough to filter
        search_results = search_google_news(search_query, when='2d')

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

                # Stop once we have 3 recent articles
                if len(articles) >= 3:
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

@app.route('/api/stock_article_summaries/<ticker>')
@login_required
@limiter.limit("20 per hour")  # Lower limit due to multiple AI calls
def get_article_summaries(ticker):
    """Generate individual headline and detailed summaries for each article"""
    try:
        api_key = os.getenv('CLAUDE_API_KEY')
        if not api_key:
            return jsonify({'error': 'Claude API key not configured'}), 500

        # Get news and price data
        news_response = get_stock_news(ticker)
        news_data = news_response.get_json()

        price_response = get_stock_price(ticker)
        price_data = price_response.get_json()

        if 'error' in news_data or not news_data.get('articles'):
            return jsonify({'summaries': []})

        articles = news_data['articles']
        company_name = news_data['company_name']
        price_change = price_data.get('change_percent', 0) if 'error' not in price_data else 0

        client = anthropic.Anthropic(api_key=api_key)

        # Function to generate summary for a single article
        def generate_article_summary(article):
            safe_title = sanitize_for_ai_prompt(article['title'])
            safe_description = sanitize_for_ai_prompt(article['description'])

            # Generate 1-sentence news summary
            headline_message = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=40,
                messages=[{
                    "role": "user",
                    "content": f"""Summarize this news article in exactly 1 concise sentence.

Article: {safe_title}
Description: {safe_description}

Write a single sentence summary of what happened. Keep it under 15 words."""
                }]
            )

            headline = headline_message.content[0].text.strip()

            return {
                'headline': headline,
                'url': article['url'],
                'source': article['source'],
                'title': article['title'],
                'description': article['description']
            }

        # Generate all summaries in parallel for speed
        summaries = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_article = {executor.submit(generate_article_summary, article): article for article in articles}
            for future in as_completed(future_to_article):
                try:
                    summary = future.result()
                    summaries.append(summary)
                except Exception as e:
                    article = future_to_article[future]
                    print(f"Error generating summary for article: {str(e)}")
                    summaries.append({
                        'headline': 'Error generating summary',
                        'url': article['url'],
                        'source': article['source'],
                        'title': article['title'],
                        'description': article['description']
                    })

        return jsonify({
            'ticker': ticker,
            'company_name': company_name,
            'summaries': summaries
        })

    except Exception as e:
        print(f"Error generating article summaries for {ticker}: {str(e)}")
        return jsonify({'error': 'Failed to generate article summaries'}), 500

@app.route('/api/stock_article_detail', methods=['POST'])
@login_required
@csrf.exempt
@limiter.limit("30 per hour")
def get_article_detail():
    """Generate detailed summary for a single article on-demand"""
    try:
        api_key = os.getenv('CLAUDE_API_KEY')
        if not api_key:
            return jsonify({'error': 'Claude API key not configured'}), 500

        data = request.get_json()
        ticker = data.get('ticker')
        company_name = data.get('company_name')
        title = data.get('title')
        description = data.get('description')
        price_change = data.get('price_change', 0)

        safe_title = sanitize_for_ai_prompt(title)
        safe_description = sanitize_for_ai_prompt(description)
        safe_company = sanitize_for_ai_prompt(company_name)
        safe_ticker = sanitize_for_ai_prompt(ticker)

        client = anthropic.Anthropic(api_key=api_key)

        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=150,
            messages=[{
                "role": "user",
                "content": f"""Analyze how this news affects {safe_company} ({safe_ticker}) stock.

Article: {safe_title}
Description: {safe_description}
Current stock change: {price_change:+.2f}%

Write EXACTLY 3-5 sentences in plain text explaining the stock price impact.
DO NOT use any markdown formatting, headers (#), bullet points, or bold text.
Just write clear, conversational sentences. Emojis are fine.
Focus on: what happened, why it matters, and potential price impact."""
            }]
        )

        detail = message.content[0].text.strip()

        return jsonify({
            'detail': detail
        })

    except Exception as e:
        print(f"Error generating article detail: {str(e)}")
        return jsonify({'error': 'Failed to generate article detail'}), 500

@app.route('/api/stock_daily_summary/<ticker>')
@login_required
@limiter.limit("30 per hour")
def get_daily_summary(ticker):
    """Generate one-sentence summary of why stock moved today"""
    try:
        api_key = os.getenv('CLAUDE_API_KEY')
        if not api_key:
            return jsonify({'error': 'Claude API key not configured'}), 500

        # Get price and sentiment data
        price_response = get_stock_price(ticker)
        price_data = price_response.get_json()

        sentiment_response = get_stock_sentiment(ticker)
        sentiment_data = sentiment_response.get_json()

        if 'error' in price_data:
            return jsonify({'daily_summary': 'Market data unavailable'})

        price_change = price_data.get('change_percent', 0)
        current_price = price_data.get('current_price', 'N/A')
        overall_sentiment = sentiment_data.get('sentiment', 'neutral')
        company_name = sentiment_data.get('company_name', ticker)

        # Get article headlines for context
        news_response = get_stock_news(ticker)
        news_data = news_response.get_json()
        articles = news_data.get('articles', [])

        headlines = "\n".join([
            f"- {sanitize_for_ai_prompt(article['title'])}"
            for article in articles[:3]  # Just top 3 for context
        ])

        client = anthropic.Anthropic(api_key=api_key)

        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=60,
            messages=[{
                "role": "user",
                "content": f"""Write ONE short sentence explaining why {sanitize_for_ai_prompt(company_name)} moved {price_change:+.2f}% today.

Price: ${current_price} ({price_change:+.2f}%)
Sentiment: {overall_sentiment}

Headlines:
{headlines if headlines else 'No recent news'}

Write a single, plain sentence (no formatting). Keep it under 12 words."""
            }]
        )

        daily_summary = message.content[0].text.strip()

        return jsonify({
            'ticker': ticker,
            'daily_summary': daily_summary
        })

    except Exception as e:
        print(f"Error generating daily summary for {ticker}: {str(e)}")
        return jsonify({'error': 'Failed to generate daily summary'}), 500

if __name__ == '__main__':
    # Only run in debug mode locally, not in production
    debug_mode = not IS_PRODUCTION
    app.run(debug=debug_mode, port=5001)

