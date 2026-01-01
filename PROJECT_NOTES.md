# AI Stock Watchlist - Project Notes

## Project Overview

An AI-powered stock watchlist MVP that provides intelligent, categorized news summaries for tracked stocks. The app focuses on delivering concise, scannable summaries with source citations, updating dynamically based on how long since the user last checked.

## Current Status: ✅ FULLY FUNCTIONAL MVP

The core MVP is complete and operational. All main features are working as intended.

---

## Tech Stack

- **Backend**: Python 3 + Flask
- **Frontend**: HTML/CSS/JavaScript (vanilla, no frameworks)
- **Database**: SQLite
- **APIs/Libraries**:
  - `yfinance==0.2.33` - Stock data and company info
  - `pygooglenews==0.1.2` - News articles from Google News (free, no API key)
  - `anthropic==0.39.0` - Claude API for AI summaries
  - `python-dotenv==1.0.0` - Environment variable management
  - `Flask==3.0.0` - Web framework
  - `Werkzeug==3.0.1` - WSGI utilities

---

## Project Structure

```
Watchlist/
├── app.py              # Main Flask application with all routes
├── database.py         # Database initialization script
├── requirements.txt    # Python dependencies
├── watchlist.db       # SQLite database (auto-generated)
├── .env               # Environment variables (Claude API key)
├── PROJECT_NOTES.md   # This file
├── static/
│   ├── css/style.css  # All styling
│   └── js/main.js     # Frontend JavaScript (async loading, formatting)
└── templates/
    ├── login.html     # Login page
    └── watchlist.html # Main watchlist page with stock cards
```

---

## ✅ Completed Features

### 1. Core Functionality
- **Authentication**: Login/logout with session management
  - Default user: `demo` / `password123`
  - Last login timestamp tracking (used for news filtering)
- **Watchlist Management**: Add/remove stocks with validation
- **Ticker Validation**: Only allows valid public company stock tickers
- **Auto-fill Company Names**: Automatically fetches company name from ticker

### 2. AI-Powered News Summaries
- **Dynamic News Fetching**:
  - Shows news since last login (1-30 days)
  - Falls back to last 24 hours if checked recently
  - Displays: "Showing the latest news from today" or "Showing news since [date]"
- **Structured AI Summaries**:
  - Claude Sonnet 4.5 generates categorized summaries
  - 2-4 distinct topics per stock (earnings, stock performance, acquisitions, etc.)
  - Each topic has emoji indicator + bold headline + 1-2 sentence summary
  - Example format:
    ```
    📈 Stock Performance
    Shares rose 5% following quarterly earnings beat, outperforming market expectations.

    💰 Earnings Report
    Company reported record revenue of $50B, driven by strong product sales and services growth.
    ```
- **Cost**: ~$0.003 (0.3 cents) per summary - extremely affordable for frequent use

### 3. Source Citations
- **Perplexity-style citations**: Clean, clickable source links below each summary
- Shows up to 5 news sources per stock
- Links open in new tabs
- Format: Simple badges with source names (e.g., "Reuters", "Bloomberg", "CNBC")

### 4. Company Logos
- **Clearbit Logo API**: Fetches real company logos from company websites
- Fallback to ticker badges (e.g., "AP" for Apple) if logo unavailable
- Logos cached by browser for performance
- **Note**: Currently rate-limited by Yahoo Finance (see Known Issues)

### 5. UI/UX
- Clean, modern card-based layout
- Gradient purple background
- Responsive design (works on mobile/tablet/desktop)
- Hover effects on cards and buttons
- Loading states for all async operations
- Error handling with user-friendly messages

---

## 🔧 Technical Implementation Details

### Backend (app.py)

**Key Routes:**
- `/login` - Authentication
- `/watchlist` - Main page (shows stocks, calculates news period)
- `/add_stock` - Validates ticker, auto-fills company name, adds to DB
- `/remove_stock/<ticker>` - Removes stock from watchlist
- `/api/company_logo/<ticker>` - Fetches company logo URL
- `/api/stock_news/<ticker>` - Fetches news articles (dynamic time period)
- `/api/stock_summary/<ticker>` - Generates AI summary from news

**News Fetching Logic:**
```python
# Calculate days since last login
days_since_login = max(1, (now - last_login_dt).days)
days_since_login = min(days_since_login, 30)  # Cap at 30 days

# Fetch news from that time period
search_results = gn.search(search_query, when=f'{days_since_login}d')
```

**AI Summary Generation:**
- Uses Claude Sonnet 4.5 (model: `claude-sonnet-4-5-20250929`)
- 400 token limit for responses
- Structured prompt requesting categorized summaries with emojis
- Explicitly instructs: "DO NOT include a title or header"

### Frontend (main.js)

**Async Loading Pattern:**
```javascript
1. Load company logos (500ms between requests)
2. Wait 500ms
3. Load summaries and sources in parallel:
   - Fetch news articles
   - Display source citations
   - Fetch AI summary
   - Format and display summary (convert markdown to HTML)
4. 1500ms delay between each stock to avoid rate limits
```

**Formatting:**
- Strips markdown headers (`# Title`)
- Converts `**bold**` to `<strong>bold</strong>`
- Preserves line breaks with `white-space: pre-line` CSS

### Database Schema

**users table:**
- `id` - INTEGER PRIMARY KEY
- `username` - TEXT UNIQUE
- `password_hash` - TEXT
- `last_login` - TIMESTAMP (ISO format)

**watchlist table:**
- `id` - INTEGER PRIMARY KEY
- `user_id` - INTEGER (foreign key)
- `stock_ticker` - TEXT
- `company_name` - TEXT
- `date_added` - TIMESTAMP
- UNIQUE constraint on (user_id, stock_ticker)

---

## ⚠️ Known Issues

### 1. Yahoo Finance Rate Limiting (ONGOING)
**Problem:**
- yfinance API has very aggressive rate limits
- Affects: company logo fetching, ticker validation, stock prices
- When hit: Returns empty data or errors
- Error message: "No price data found, symbol may be delisted"

**Workaround:**
- Wait 12-24 hours for rate limit to reset
- Ticker badges show as fallback when logos can't load
- Ticker validation may fail during rate limit (shows error to user)

**Future Solution:**
- Cache company info (name, logo URL, domain) in database
- Only call yfinance once per ticker, store results
- This would eliminate most yfinance API calls

### 2. SSL Certificate Issues (macOS)
**Problem:** Python SSL certificates not installed on some macOS systems

**Solution:**
```bash
python -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host pypi.python.org [package]
```

---

## 🚀 How to Run

### Initial Setup
```bash
cd "/Users/aaronzhang/Desktop/Watchlist "

# Install dependencies
python -m pip install -r requirements.txt

# Initialize database (if not already done)
python database.py

# Create .env file with Claude API key
echo "CLAUDE_API_KEY=your-api-key-here" > .env
```

### Running the App
```bash
python app.py
```

Visit: `http://localhost:5001`
Login: `demo` / `password123`

---

## 📋 MVP Completion Checklist

- [x] User authentication with login/logout
- [x] Add/remove stocks from watchlist
- [x] Ticker validation (only real stocks)
- [x] Auto-fill company names from ticker
- [x] Fetch news articles based on last login time
- [x] Generate AI summaries with Claude API
- [x] Structure summaries into categorized sections with emojis
- [x] Display source citations with clickable links
- [x] Fetch and display company logos
- [x] Responsive UI with clean card layout
- [x] Error handling and loading states
- [x] Dynamic news time period display

**Status: MVP COMPLETE ✅**

---

## 🔮 Future Enhancements (Optional)

### High Priority
1. **Database Caching for Company Info**
   - Cache logo URLs, company names, domains in database
   - Add `company_info` table with: ticker, company_name, logo_url, website, last_updated
   - Only call yfinance once per ticker, then use cached data
   - **Benefit**: Eliminates most yfinance API calls, solves rate limiting

2. **Stock Price Display** (when rate limiting resolved)
   - Re-enable price fetching endpoint
   - Show current price + % change since last login
   - Color-coded green/red for positive/negative changes

### Medium Priority
3. **News Caching**
   - Cache news articles for X minutes to reduce API calls on page refresh
   - Store in database or Redis
   - Invalidate cache after time period expires

4. **Email Notifications**
   - Daily/weekly digest emails with AI summaries
   - Alert for major price movements (>5%)
   - Configurable notification preferences

5. **Portfolio Analytics**
   - Track multiple portfolios
   - Add share counts and purchase prices
   - Calculate total portfolio value and gains/losses

### Low Priority
6. **Chart Visualizations**
   - Stock price charts (line graphs)
   - Historical performance overlays
   - Compare multiple stocks

7. **Multi-user Support**
   - User registration and password reset
   - Separate watchlists per user
   - Admin panel

8. **Advanced Features**
   - Stock screener/discovery
   - Sector categorization
   - Sentiment analysis on news articles
   - Integration with trading platforms

---

## 💰 Cost Analysis

**Current Costs (per session):**
- pygooglenews: **FREE** (no API key needed)
- Clearbit logos: **FREE** (no API key needed)
- yfinance: **FREE** (rate-limited, but free)
- Claude API: **~$0.003 per summary** (0.3 cents)
  - Input: ~500 tokens × $3/million = $0.0015
  - Output: ~100 tokens × $15/million = $0.0015
  - Total: ~$0.003 per stock summary

**Example usage costs:**
- 5 stocks × 1 refresh = $0.015 (1.5 cents)
- 10 stocks × 1 refresh = $0.03 (3 cents)
- 5 stocks × 10 refreshes/day = $0.15 (15 cents/day)
- 5 stocks × 30 days × 3 refreshes/day = $2.25/month

**Verdict**: Extremely affordable for personal use.

---

## 🎨 Design Philosophy

1. **Simplicity First**: No unnecessary features, clean and focused
2. **AI-Powered Insights**: Let AI do the heavy lifting (summarization, categorization)
3. **Scannable Content**: Emojis + headlines + short summaries for quick reading
4. **Progressive Enhancement**: Core features first, enhancements later
5. **Cost-Effective**: Use free APIs where possible, minimal paid API usage
6. **Mobile-Friendly**: Responsive design that works everywhere

---

## 📝 Development Notes

### Session 1: Foundation
- Built Flask app structure
- Implemented authentication and watchlist CRUD
- Created database schema
- Designed card-based UI
- Encountered Yahoo Finance rate limiting

### Session 2: AI Integration (COMPLETED)
- Added pygooglenews for news fetching
- Integrated Claude API for summaries
- Implemented dynamic news filtering (since last login)
- Added structured summaries with emojis and categories
- Added source citations (Perplexity-style)
- Implemented company logo fetching
- Removed stock prices and news images (simplified MVP)
- Added ticker validation
- Refined UI for better scannability

### Key Learnings
- Yahoo Finance rate limiting is aggressive - need caching strategy
- Claude generates excellent categorized summaries with clear instructions
- Structured prompts (emojis + headers) make summaries much more scannable
- pygooglenews is reliable but doesn't provide image URLs consistently
- Cost per summary is negligible (~0.3 cents) - not a concern for personal use

---

## 🐛 Debugging Tips

### If summaries aren't loading:
1. Check terminal for API key loading: `API Key loaded: sk-ant-api03-...`
2. Verify Claude API key in `.env` file
3. Check Claude API model name is correct: `claude-sonnet-4-5-20250929`
4. Look for error messages in terminal

### If news articles are empty:
1. Check if enough time has passed (need articles from last login period)
2. Try searching manually on Google News for the ticker
3. Check terminal: `News for AAPL: X articles, Y with images`

### If logos won't load:
1. Likely Yahoo Finance rate limiting - wait 12-24 hours
2. Check terminal for yfinance errors
3. Fallback ticker badges should still show

### If ticker validation fails:
1. Ensure ticker is valid (try on Yahoo Finance website)
2. Check if Yahoo rate limit is active
3. Add delays between adding multiple stocks

---

## 🔗 Useful Resources

- **Flask Documentation**: https://flask.palletsprojects.com/
- **Claude API Docs**: https://docs.anthropic.com/claude/reference/messages
- **pygooglenews**: https://github.com/kotartemiy/pygooglenews
- **yfinance**: https://github.com/ranaroussi/yfinance
- **Clearbit Logo API**: https://clearbit.com/logo

---

## 📞 Support & Maintenance

**Environment:**
- Python 3.x (developed on macOS)
- Port 5001 (default, can be changed in app.py)
- SQLite database (no separate server needed)

**Common Maintenance Tasks:**
1. Update Claude API key: Edit `.env` file
2. Clear database: Delete `watchlist.db` and run `python database.py`
3. Update dependencies: `pip install -r requirements.txt --upgrade`
4. Check logs: Flask prints to terminal (enable debug mode for verbose logging)

---

## 🎯 Project Goals: Achieved ✅

**Original Goal**: Build an MVP stock watchlist with AI-generated news summaries

**What We Built**:
- ✅ Clean, intuitive UI
- ✅ Smart news filtering (based on last login)
- ✅ Excellent AI summaries (categorized with emojis)
- ✅ Source citations for transparency
- ✅ Ticker validation for data quality
- ✅ Company logos for visual appeal
- ✅ Cost-effective (~0.3 cents per summary)
- ✅ Easy to use and extend

**Outcome**: Fully functional MVP that provides real value for tracking stocks with AI-powered insights!

---

**Last Updated**: December 22, 2024
**Status**: Production-ready MVP ✅
**Next Steps**: Optional enhancements (caching, price display, email notifications)
