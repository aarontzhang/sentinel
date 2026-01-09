# Sentinel

A modern, AI-powered stock watchlist application with real-time news summaries and a sleek dark theme interface.

## Features

- **AI-Powered News Summaries**: Automatically generated summaries of the latest stock news using Claude API (Sonnet 4.5)
- **Sentiment Analysis**: Bullish/bearish/neutral sentiment analysis for overall stock and per-article indicators
- **Daily Price Tracking**: Robin Hood-style price display with daily percentage changes
- **Smart Caching**: Session-based caching for instant summary loading
- **Drag-and-Drop Reordering**: Easily reorganize your watchlist with an intuitive modal interface
- **Company Logos**: Automatic company logo fetching from Brandfetch CDN (500k requests/month free tier)
- **Real-Time News**: Fetches latest news articles using Google News RSS feed (last 24 hours)
- **Dark Theme**: Modern, sleek dark interface with Avenir font
- **User Authentication**: Secure registration and login with password hashing
- **Security Features**: Rate limiting, CSRF protection, input validation, and prompt injection prevention
- **Persistent Order**: Stock order saved to browser localStorage
- **Delete Confirmation**: Modal confirmation before removing stocks

## Tech Stack

- **Backend**: Python 3.x + Flask
- **Frontend**: HTML5, CSS3 (Avenir font), Vanilla JavaScript
- **Database**: SQLite
- **Security**: Flask-Limiter (rate limiting), Flask-WTF (CSRF protection), Werkzeug (password hashing)
- **APIs**:
  - Claude API (Anthropic) for AI summaries and sentiment analysis
  - Yahoo Finance (yfinance) for stock prices and validation
  - Google News (pygooglenews) for news articles
  - Brandfetch CDN for company logos

## Prerequisites

- Python 3.8 or higher
- Claude API key (get from [Anthropic Console](https://console.anthropic.com/))

## Setup Instructions

### 1. Clone and Navigate to Project

```bash
cd "Watchlist "
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the project root (see `.env.example` for template):

```bash
CLAUDE_API_KEY=your_claude_api_key_here
SECRET_KEY=your_secret_key_here
```

**Generate a secure SECRET_KEY:**
```bash
python -c "import os; print(os.urandom(32).hex())"
```

**Security Note**: Never commit your `.env` file to version control. It's already in `.gitignore`.

### 4. Initialize Database

```bash
python database.py
```

This creates the SQLite database. The database is empty - you'll create your account on first use.

### 5. Run the Application

```bash
python app.py
```

The app will be available at `http://localhost:5001`

## Project Structure

```
Watchlist/
├── app.py                  # Main Flask application
├── database.py             # Database initialization script
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (create this)
├── watchlist.db           # SQLite database (auto-created)
├── stock_domains.json     # 530+ ticker-to-domain mappings
├── static/
│   ├── css/
│   │   └── style.css      # Dark theme stylesheet (Avenir font)
│   └── js/
│       └── main.js        # Frontend logic (caching, reordering, modals)
└── templates/
    ├── login.html         # Login page with Sentinel branding
    ├── watchlist.html     # Main watchlist page
    └── profile.html       # User profile page
```

## Usage

1. **Sign Up**: Visit `/register` to create a new account with a secure password
2. **Login**: Use your credentials to log in at `/login`
3. **Add Stocks**: Enter a ticker symbol (e.g., AAPL, MSFT, GOOGL) in the search box
4. **View Daily Updates**: See daily price changes, sentiment analysis, and AI-generated news summaries
5. **Reorder Stocks**: Click the three-dot icon to drag and reorder stocks
6. **Remove Stocks**: Click the minus icon on any stock card
7. **Refresh Data**: Click the refresh icon to force-refresh all prices, sentiment, and summaries

## Key Features Explained

### AI Summaries
- Powered by Claude Sonnet 4.5 model
- Categorizes news into distinct topics with relevant emojis
- Automatically refreshes based on last login time
- Cached in sessionStorage for instant reloading

### Smart News Fetching
- Fetches news since your last login (up to 30 days)
- Falls back to 2-day window if no recent articles found
- Displays up to 5 news sources per stock

### Performance Optimizations
- Concurrent API calls with 300ms stagger to avoid rate limiting
- Session-based caching prevents redundant API calls
- Parallel loading of logos and summaries
- LocalStorage persistence for stock order

### Dark Theme
- Pure black background (#000)
- Dark gray cards (#1a1a1a)
- White text throughout
- Avenir font family with fallbacks
- Smooth hover animations

## API Limits

- **Claude API**: Depends on your plan (check Anthropic Console)
- **Brandfetch CDN**: 500,000 requests/month (free tier)
- **Google News RSS**: No official limit, but be respectful
- **yfinance**: No official limit

## Database Schema

### Users Table
- `id`: Primary key
- `username`: Unique username
- `password_hash`: Hashed password (Werkzeug)
- `last_login`: Timestamp of last login

### Watchlist Table
- `id`: Primary key
- `user_id`: Foreign key to users
- `stock_ticker`: Stock symbol (e.g., AAPL)
- `company_name`: Full company name
- `date_added`: Timestamp

## Security Features

### Authentication & Authorization
- **Password Hashing**: Werkzeug PBKDF2 SHA-256 with salt
- **Session Management**: HTTP-only cookies with SameSite protection
- **User Registration**: Username validation (3-50 chars, alphanumeric + underscores)
- **Password Requirements**: Minimum 8 characters, maximum 128 characters

### Rate Limiting
- **Login/Registration**: 10 login attempts per minute, 5 registrations per hour
- **Stock Operations**: 30 additions/removals per hour
- **API Endpoints**: 30-60 requests per hour (AI endpoints have lower limits)
- **Storage**: In-memory rate limiting (upgrade to Redis for production)

### Input Validation & Sanitization
- **Ticker Validation**: Regex validation (1-10 alphanumeric chars, dots, hyphens)
- **SQL Injection Prevention**: Parameterized queries throughout
- **XSS Protection**: HTML tag stripping in user inputs
- **Prompt Injection Prevention**: Input sanitization before AI API calls
- **CSRF Protection**: Token-based CSRF protection on all forms

### Production Deployment Checklist
- [ ] Set `SESSION_COOKIE_SECURE = True` for HTTPS
- [ ] Set `DEBUG = False` in app.py
- [ ] Use environment variables for all secrets
- [ ] Implement Redis for rate limiting persistence
- [ ] Set up proper logging and monitoring
- [ ] Use a production-grade WSGI server (Gunicorn/uWSGI)
- [ ] Add HTTPS/TLS certificates
- [ ] Regular security updates for dependencies

## Development Notes

- Server runs on port 5001 (configurable in app.py)
- Debug mode enabled by default (disable in production)
- Session-based authentication with secure cookies
- Rate limiting uses in-memory storage (consider Redis for production)

## Troubleshooting

**Summaries not loading?**
- Check your Claude API key in `.env`
- Verify API key is valid in Anthropic Console
- Check Flask console for error messages

**Logos not showing?**
- Verify ticker exists in `stock_domains.json`
- Check browser console for 404 errors
- Brandfetch CDN might be rate-limited

**News articles missing?**
- Stock might have limited news coverage
- Try refreshing after a few hours
- Check if ticker is valid with yfinance

## License

This project is for educational and personal use.

## Credits

- **Claude API**: Anthropic
- **Company Logos**: Brandfetch CDN
- **Stock Data**: yfinance
- **News Feed**: Google News RSS (pygooglenews)
