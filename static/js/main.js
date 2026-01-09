function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Delete Modal Functions
let stockToDelete = null;

function openDeleteModal(ticker, companyName) {
    stockToDelete = ticker;
    const modal = document.getElementById('deleteModal');
    const modalText = document.getElementById('deleteModalText');
    modalText.textContent = `Are you sure you want to remove ${companyName} (${ticker}) from your watchlist?`;
    modal.classList.add('show');
}

function closeDeleteModal() {
    const modal = document.getElementById('deleteModal');
    modal.classList.remove('show');
    stockToDelete = null;
}

function confirmDelete() {
    if (stockToDelete) {
        // Create a form and submit it
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/remove_stock/${stockToDelete}`;

        // Add CSRF token
        const csrfToken = document.querySelector('input[name="csrf_token"]').value;
        const csrfInput = document.createElement('input');
        csrfInput.type = 'hidden';
        csrfInput.name = 'csrf_token';
        csrfInput.value = csrfToken;
        form.appendChild(csrfInput);

        document.body.appendChild(form);
        form.submit();
    }
}

// Drag and Drop for Stock Cards
function initializeDragAndDrop() {
    // No drag and drop on main cards - use reorder modal instead
}

function saveOrder() {
    const stockCards = document.querySelectorAll('.stock-card');
    const order = [];

    stockCards.forEach(card => {
        order.push(card.dataset.ticker);
    });

    localStorage.setItem('stockOrder', JSON.stringify(order));
    console.log('Saved order:', order);
}

function loadOrder() {
    const savedOrder = localStorage.getItem('stockOrder');

    if (savedOrder) {
        const order = JSON.parse(savedOrder);
        const stocksGrid = document.querySelector('.stocks-grid');
        const stockCards = [...document.querySelectorAll('.stock-card')];

        order.forEach(ticker => {
            const card = stockCards.find(c => c.dataset.ticker === ticker);
            if (card) {
                stocksGrid.appendChild(card);
            }
        });
    }
}

async function loadCompanyLogos() {
    const stockCards = document.querySelectorAll('.stock-card');

    for (let i = 0; i < stockCards.length; i++) {
        const card = stockCards[i];
        const ticker = card.dataset.ticker;
        const logoImg = card.querySelector('.logo-img');
        const logoFallback = card.querySelector('.logo-fallback');

        try {
            const response = await fetch(`/api/company_logo/${ticker}`);
            const data = await response.json();

            if (data.logo_url) {
                logoImg.src = data.logo_url;
                logoImg.onload = function() {
                    this.style.display = 'block';
                    logoFallback.style.display = 'none';
                };
                logoImg.onerror = function() {
                    this.style.display = 'none';
                    logoFallback.style.display = 'flex';
                };
            }
        } catch (error) {
            console.error(`Error loading logo for ${ticker}:`, error);
        }

        if (i < stockCards.length - 1) {
            await sleep(500);
        }
    }
}

// Cache management for summaries
function getCachedData(ticker) {
    const cached = sessionStorage.getItem(`stock_${ticker}`);
    if (cached) {
        return JSON.parse(cached);
    }
    return null;
}

function setCachedData(ticker, data) {
    sessionStorage.setItem(`stock_${ticker}`, JSON.stringify(data));
}

function clearAllCache() {
    const keys = Object.keys(sessionStorage);
    keys.forEach(key => {
        if (key.startsWith('stock_')) {
            sessionStorage.removeItem(key);
        }
    });
}

async function loadStockPriceAndSentiment(ticker, card, forceRefresh = false) {
    const priceValue = card.querySelector('.price-value');
    const priceChange = card.querySelector('.price-change');
    const overallSentiment = card.querySelector('.overall-sentiment');

    // Check cache first
    if (!forceRefresh) {
        const cachedData = getCachedData(`${ticker}_price_sentiment`);
        if (cachedData) {
            priceValue.textContent = cachedData.price;
            priceChange.innerHTML = cachedData.changeHTML;
            priceChange.className = cachedData.changeClass;
            overallSentiment.innerHTML = cachedData.sentimentHTML;
            overallSentiment.className = cachedData.sentimentClass;
            // Store article sentiments for later use
            card.dataset.articleSentiments = JSON.stringify(cachedData.articleSentiments || []);
            return;
        }
    }

    try {
        const response = await fetch(`/api/stock_sentiment/${ticker}`);
        const data = await response.json();

        if (data.error) {
            priceValue.textContent = 'N/A';
            priceChange.textContent = '';
            overallSentiment.textContent = '';
            return;
        }

        // Update price with cents (e.g., $150.25)
        const price = data.current_price !== 'N/A' ? `$${data.current_price.toFixed(2)}` : 'N/A';
        priceValue.textContent = price;

        // Update change with arrow and color
        const change = data.price_change;
        const changeClass = change > 0 ? 'price-change positive' : change < 0 ? 'price-change negative' : 'price-change neutral';
        const arrow = change > 0 ? '↑' : change < 0 ? '↓' : '—';
        const changeHTML = `${arrow} ${Math.abs(change).toFixed(2)}%`;

        priceChange.innerHTML = changeHTML;
        priceChange.className = changeClass;

        // Update overall sentiment with arrow and text
        const sentiment = data.sentiment || 'neutral';
        const sentimentClass = `overall-sentiment sentiment-${sentiment}`;
        const sentimentText = sentiment.charAt(0).toUpperCase() + sentiment.slice(1);
        const sentimentArrow = sentiment === 'bullish' ? '↑' : sentiment === 'bearish' ? '↓' : '—';
        const sentimentHTML = `${sentimentArrow} ${sentimentText}`;

        overallSentiment.innerHTML = sentimentHTML;
        overallSentiment.className = sentimentClass;

        // Store article sentiments for use when loading sources
        const articleSentiments = data.article_sentiments || [];
        card.dataset.articleSentiments = JSON.stringify(articleSentiments);

        // Cache the data
        setCachedData(`${ticker}_price_sentiment`, {
            price,
            changeHTML,
            changeClass,
            sentimentHTML,
            sentimentClass,
            articleSentiments
        });

    } catch (error) {
        console.error(`Error fetching data for ${ticker}:`, error);
        priceValue.textContent = 'Error';
        priceChange.textContent = '';
        overallSentiment.textContent = '';
    }
}

async function loadStockNews(forceRefresh = false) {
    const stockCards = document.querySelectorAll('.stock-card');
    const cardsToFetch = [];

    // First pass: Immediately load all cached data (instant, no waiting)
    stockCards.forEach(card => {
        const ticker = card.dataset.ticker;
        const newsElement = card.querySelector('.news-text');
        const sourcesList = card.querySelector('.sources-list');

        if (!forceRefresh) {
            const cachedData = getCachedData(`${ticker}_news`);
            if (cachedData) {
                // Load from cache instantly
                newsElement.innerHTML = cachedData.news;
                sourcesList.innerHTML = cachedData.sources;
                return; // Skip this card, already loaded
            }
        }

        // Mark for fetching
        cardsToFetch.push({ card, ticker, newsElement, sourcesList });
    });

    // Second pass: Fetch all non-cached stocks concurrently
    if (cardsToFetch.length > 0) {
        // Start all fetches concurrently with small staggered delays
        const fetchPromises = cardsToFetch.map(async ({ card, ticker, newsElement, sourcesList }, index) => {
            // Stagger the start times slightly to avoid overwhelming the API
            if (index > 0) {
                await sleep(index * 300); // 300ms stagger between each request start
            }

            newsElement.textContent = 'Generating news summary...';

            try {
                // Fetch news and summary concurrently for this stock
                const [newsResponse, summaryResponse] = await Promise.all([
                    fetch(`/api/stock_news/${ticker}`),
                    fetch(`/api/stock_summary/${ticker}`)
                ]);

                const newsData = await newsResponse.json();
                const summaryData = await summaryResponse.json();

                let sourcesHTML = '';
                if (!newsData.error && newsData.articles && newsData.articles.length > 0) {
                    // Get article sentiments from card dataset (set by loadStockPriceAndSentiment)
                    let articleSentiments = [];
                    try {
                        articleSentiments = JSON.parse(card.dataset.articleSentiments || '[]');
                    } catch (e) {
                        console.error('Error parsing article sentiments:', e);
                    }

                    newsData.articles.slice(0, 5).forEach((article, index) => {
                        const sentiment = articleSentiments[index] || 'neutral';
                        const sentimentClass = `article-sentiment-${sentiment}`;
                        sourcesHTML += `<a href="${article.url}" target="_blank" class="source-link ${sentimentClass}"><span class="article-sentiment-dot"></span>${article.source || `Source ${index + 1}`}</a>`;
                    });
                } else {
                    sourcesHTML = '<span class="no-sources">No sources available</span>';
                }
                sourcesList.innerHTML = sourcesHTML;

                let newsHTML = '';
                if (summaryData.error) {
                    newsHTML = summaryData.error;
                } else {
                    // Remove markdown headers and convert **bold** to HTML
                    newsHTML = summaryData.summary
                        .replace(/^#{1,6}\s+.*$/gm, '') // Remove markdown headers
                        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') // Convert bold
                        .trim();
                }
                newsElement.innerHTML = newsHTML;

                // Cache the data
                setCachedData(`${ticker}_news`, {
                    news: newsHTML,
                    sources: sourcesHTML
                });
            } catch (error) {
                console.error(`Error fetching data for ${ticker}:`, error);
                newsElement.textContent = 'Failed to generate news summary';
                sourcesList.innerHTML = '<span class="no-sources">Failed to load sources</span>';
            }
        });

        // Wait for all fetches to complete
        await Promise.all(fetchPromises);
    }
}

async function loadAllStockData(forceRefresh = false) {
    const stockCards = document.querySelectorAll('.stock-card');

    // Load price and sentiment data for all stocks concurrently with stagger
    const priceAndSentimentPromises = Array.from(stockCards).map(async (card, index) => {
        if (index > 0) {
            await sleep(index * 300);
        }
        const ticker = card.dataset.ticker;
        await loadStockPriceAndSentiment(ticker, card, forceRefresh);
    });

    // Load news and price/sentiment in parallel
    await Promise.all([
        loadStockNews(forceRefresh),
        ...priceAndSentimentPromises
    ]);
}

// Refresh summaries - can be called manually or on initial load
async function refreshSummaries(forceRefresh = true) {
    const refreshBtn = document.querySelector('.refresh-btn');

    // Add loading state to refresh button
    if (refreshBtn) {
        refreshBtn.disabled = true;
        refreshBtn.innerHTML = '<div class="spinner spinner-sm"></div>';
    }

    // Add loading class to all stock cards and show skeleton loaders
    document.querySelectorAll('.stock-card').forEach(card => {
        card.classList.add('loading');

        // Show skeleton loaders in news section
        const newsText = card.querySelector('.news-text');
        const sourcesList = card.querySelector('.sources-list');

        if (newsText) {
            newsText.innerHTML = `
                <div class="skeleton skeleton-text"></div>
                <div class="skeleton skeleton-text"></div>
                <div class="skeleton skeleton-text"></div>
            `;
        }

        if (sourcesList) {
            sourcesList.innerHTML = `
                <div class="skeleton skeleton-source"></div>
                <div class="skeleton skeleton-source"></div>
                <div class="skeleton skeleton-source"></div>
            `;
        }
    });

    // Clear cache and force refresh when button is clicked
    if (forceRefresh) {
        clearAllCache();
    }

    await loadAllStockData(forceRefresh);

    // Remove loading states
    document.querySelectorAll('.stock-card').forEach(card => {
        card.classList.remove('loading');
    });

    // Restore refresh button
    if (refreshBtn) {
        refreshBtn.disabled = false;
        refreshBtn.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/>
            </svg>
        `;
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    // Load saved stock order first
    loadOrder();

    // Initialize drag and drop
    initializeDragAndDrop();

    // Initialize pull-to-refresh for mobile
    initPullToRefresh();

    // Load company logos
    loadCompanyLogos();
    await sleep(500);

    // Load all stock data (sentiment, summaries, etc.) from cache or fetch if not cached
    await loadAllStockData(false);
});

// Reorder Modal Functions
function openReorderModal() {
    const modal = document.getElementById('reorderModal');
    const reorderList = document.getElementById('reorderList');

    // Clear existing items
    reorderList.innerHTML = '';

    // Get all stock cards in current order
    const stockCards = document.querySelectorAll('.stock-card');

    // Populate modal with simplified stock items
    stockCards.forEach(card => {
        const ticker = card.dataset.ticker;
        const companyName = card.dataset.company;

        // Create reorder item
        const item = document.createElement('div');
        item.className = 'reorder-item';
        item.dataset.ticker = ticker;
        item.draggable = true;

        // Add drag handle
        const handle = document.createElement('div');
        handle.className = 'reorder-item-handle';
        handle.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="5" cy="5" r="1.5"/>
                <circle cx="11" cy="5" r="1.5"/>
                <circle cx="5" cy="11" r="1.5"/>
                <circle cx="11" cy="11" r="1.5"/>
            </svg>
        `;

        // Add info
        const info = document.createElement('div');
        info.className = 'reorder-item-info';
        info.innerHTML = `
            <h4>${companyName}</h4>
            <p>${ticker}</p>
        `;

        item.appendChild(handle);
        item.appendChild(info);

        reorderList.appendChild(item);
    });

    // Initialize drag and drop for modal items
    initializeModalDragAndDrop();

    // Show modal
    modal.classList.add('show');
}

function closeReorderModal() {
    const modal = document.getElementById('reorderModal');
    modal.classList.remove('show');
}

function saveReorderAndClose() {
    const reorderItems = document.querySelectorAll('.reorder-item');
    const newOrder = [];

    // Get new order from modal
    reorderItems.forEach(item => {
        newOrder.push(item.dataset.ticker);
    });

    // Apply new order to main page
    const stocksGrid = document.querySelector('.stocks-grid');
    const stockCards = [...document.querySelectorAll('.stock-card')];

    newOrder.forEach(ticker => {
        const card = stockCards.find(c => c.dataset.ticker === ticker);
        if (card) {
            stocksGrid.appendChild(card);
        }
    });

    // Save to localStorage
    saveOrder();

    // Close modal
    closeReorderModal();
}

function initializeModalDragAndDrop() {
    const reorderItems = document.querySelectorAll('.reorder-item');
    let draggedElement = null;

    reorderItems.forEach(item => {
        item.addEventListener('dragstart', function(e) {
            draggedElement = this;
            this.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
        });

        item.addEventListener('dragend', function(e) {
            this.classList.remove('dragging');
            // Remove all drag-over classes
            document.querySelectorAll('.reorder-item').forEach(i => i.classList.remove('drag-over'));
        });

        item.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';

            if (draggedElement !== this) {
                this.classList.add('drag-over');
            }
        });

        item.addEventListener('dragleave', function(e) {
            this.classList.remove('drag-over');
        });

        item.addEventListener('drop', function(e) {
            e.preventDefault();

            if (draggedElement !== this) {
                const allItems = [...document.querySelectorAll('.reorder-item')];
                const draggedIndex = allItems.indexOf(draggedElement);
                const targetIndex = allItems.indexOf(this);

                const reorderList = document.getElementById('reorderList');

                if (draggedIndex < targetIndex) {
                    reorderList.insertBefore(draggedElement, this.nextSibling);
                } else {
                    reorderList.insertBefore(draggedElement, this);
                }
            }

            this.classList.remove('drag-over');
        });
    });
}

// Check if device is mobile
function isMobileDevice() {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent)
           || window.innerWidth <= 768;
}

// Haptic feedback for mobile devices
function triggerHapticFeedback(type = 'light') {
    if (navigator.vibrate) {
        const patterns = {
            light: 10,
            medium: 20,
            heavy: 30
        };
        navigator.vibrate(patterns[type] || patterns.light);
    }
}

// Initialize haptic feedback on buttons for mobile
function initializeHapticFeedback() {
    if (!isMobileDevice()) return;

    const buttons = document.querySelectorAll('button, .btn-primary, .btn-secondary, .btn-danger, .source-link, .reorder-btn, .refresh-btn');
    buttons.forEach(btn => {
        btn.addEventListener('touchstart', () => {
            triggerHapticFeedback('light');
        }, { passive: true });
    });
}

// Pull-to-Refresh Implementation
let pullToRefreshEnabled = false;
let startY = 0;
let currentY = 0;
let isPulling = false;
let refreshTriggered = false;

function initPullToRefresh() {
    if (!isMobileDevice()) return;

    pullToRefreshEnabled = true;

    // Create pull-to-refresh element
    const pullToRefreshEl = document.createElement('div');
    pullToRefreshEl.className = 'pull-to-refresh';
    pullToRefreshEl.id = 'pullToRefresh';
    pullToRefreshEl.innerHTML = `
        <div class="pull-to-refresh-content">
            <svg class="pull-to-refresh-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/>
            </svg>
            <span class="pull-to-refresh-text">Pull to refresh</span>
        </div>
    `;
    document.body.appendChild(pullToRefreshEl);

    // Touch start
    document.addEventListener('touchstart', (e) => {
        if (window.scrollY === 0 && pullToRefreshEnabled && !refreshTriggered) {
            startY = e.touches[0].pageY;
            isPulling = false;
        }
    }, { passive: true });

    // Touch move
    document.addEventListener('touchmove', (e) => {
        if (!pullToRefreshEnabled || refreshTriggered) return;

        currentY = e.touches[0].pageY;
        const pullDistance = currentY - startY;

        if (window.scrollY === 0 && pullDistance > 0) {
            isPulling = true;

            const pullThreshold = 80;
            const maxPull = 120;
            const scaledPull = Math.min(pullDistance * 0.5, maxPull);

            if (scaledPull > 10) {
                e.preventDefault();
                pullToRefreshEl.style.transform = `translateY(${scaledPull - 60}px)`;

                if (pullDistance > pullThreshold) {
                    pullToRefreshEl.classList.add('pulling');
                    pullToRefreshEl.querySelector('.pull-to-refresh-text').textContent = 'Release to refresh';
                } else {
                    pullToRefreshEl.classList.remove('pulling');
                    pullToRefreshEl.querySelector('.pull-to-refresh-text').textContent = 'Pull to refresh';
                }
            }
        }
    }, { passive: false });

    // Touch end
    document.addEventListener('touchend', async (e) => {
        if (!isPulling || !pullToRefreshEnabled || refreshTriggered) {
            isPulling = false;
            return;
        }

        const pullDistance = currentY - startY;
        const pullThreshold = 80;

        if (pullDistance > pullThreshold) {
            // Trigger refresh
            refreshTriggered = true;
            pullToRefreshEl.classList.add('refreshing', 'visible');
            pullToRefreshEl.classList.remove('pulling');
            pullToRefreshEl.style.transform = 'translateY(0)';
            pullToRefreshEl.querySelector('.pull-to-refresh-text').textContent = 'Refreshing...';

            // Call refresh function
            await refreshSummaries(true);

            // Hide pull-to-refresh with delay
            setTimeout(() => {
                pullToRefreshEl.classList.remove('visible', 'refreshing');
                pullToRefreshEl.style.transform = 'translateY(-100%)';
                refreshTriggered = false;
            }, 500);
        } else {
            // Reset
            pullToRefreshEl.style.transform = 'translateY(-100%)';
            pullToRefreshEl.classList.remove('pulling');
        }

        isPulling = false;
        startY = 0;
        currentY = 0;
    }, { passive: true });
}

// Call haptic initialization on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    initializeHapticFeedback();
});
