# Dealuxe Production Fixes - Complete Guide

## Issues Fixed

### 1. ✅ Balance Calculation Accuracy (CRITICAL FIX)
**Problem:** Winnings were being double-counted when session endpoint was called multiple times.

**Root Cause:** Backend was awarding winnings every time `/api/session/complete` was called, without checking if the session was already completed.

**Scenario That Caused Error:**
- Player wins game → Balance: 543 + 1000 = 1543 ✓
- Frontend calls `/api/session/complete` (first time) → Winnings awarded: 1000
- Response returns: new_balance = 1543
- Frontend somehow calls again → Winnings awarded AGAIN: 1000
- Response returns: new_balance = 2543 ✗

**Solution:** 
- Backend now tracks if session is already completed
- Only awards winnings on FIRST completion
- Prevents double-awarding even if endpoint is called multiple times
- Frontend simply displays the balance returned by backend (NO calculations)

### 2. ✅ Game State Persistence (Multi-Worker)
**Problem:** Game state was not persisting between HTTP requests because Gunicorn runs multiple worker processes, each with its own memory.

**Solution:** Use Redis-based session storage for shared state across workers.

---

## Deployment Steps for VPS

### Step 1: Install Redis
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install redis-server -y

# Start and enable Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Verify it's running
redis-cli ping
# Should return: PONG
```

### Step 2: Upload Updated Files
From your Windows workspace, upload these files to `/var/www/dealuxe-2/Dealuxe/`:

**Backend files:**
- `controllers/session_controller.py` - Fixed balance awarding (CRITICAL)
- `game/manager.py` or `game/manager_redis.py` - If using Redis
- `app.py` - Updated with manager calls

**Frontend files:**
- `static/js/game.js` - Simplified balance display
- `static/js/game-start.js` - Removed balance storage
- `templates/game.html` - Game over modal

### Step 3: Install Dependencies
```bash
cd /var/www/dealuxe-2/Dealuxe
source venv/bin/activate

# Install redis client (if not already installed)
pip install redis

# Or reinstall all requirements
pip install -r requirements.txt
```

### Step 4: Restart Gunicorn
```bash
# If using systemd service
sudo systemctl restart gunicorn

# OR find and restart manually
sudo pkill gunicorn
# Then start your gunicorn command again
```

### Step 5: Verify Deployment
```bash
# Check Redis connection
redis-cli ping

# Monitor Gunicorn logs
sudo journalctl -u gunicorn -f
# OR
sudo tail -f /var/log/your-app.log

# Look for these messages:
# [SESSION] Player X won Y in session Z (First completion - awards winnings)
# [SESSION] Session already completed - returning balance (Subsequent calls - no award)
```

---

## Configuration

### Redis Connection (Optional)
If Redis is on a different host or port, set environment variables:

```bash
export REDIS_HOST=localhost
export REDIS_PORT=6379
export REDIS_PASSWORD=your_password  # If required
```

Add to your systemd service file `/etc/systemd/system/gunicorn.service`:
```ini
[Service]
Environment="REDIS_HOST=localhost"
Environment="REDIS_PORT=6379"
```

### Single-Worker Mode (If Redis Unavailable)
Run Gunicorn with only 1 worker (not recommended for production):
```bash
gunicorn --workers 1 --bind 0.0.0.0:8000 app:app
```

---

## Testing the Fixes

### Test 1: Balance Accuracy (PRIMARY TEST)
1. Start with known balance (e.g., 1000 SZL)
2. Bet 500 SZL → Balance should be 500 SZL
3. Win game with 1000 SZL prize → Balance should be 1500 SZL
4. Check server logs show correct amounts
5. ✅ Final balance in UI should match backend (NOT doubled)

### Test 2: No Double-Awarding
```bash
# Monitor logs while playing
sudo journalctl -u gunicorn -f

# You should see:
# [SESSION] Player 1 won 1000 in session X  (First call - awards winnings)
# [SESSION] Session already completed - returning balance (Second call - no award)
```

### Test 3: Multi-Worker State (With Redis)
```bash
# Start Gunicorn with multiple workers
gunicorn --workers 4 --bind 0.0.0.0:8000 app:app

# Create a game and make moves
# Should work seamlessly across all workers
```

---

## Monitoring

### Check Redis Health
```bash
# Connection test
redis-cli ping

# View all game keys
redis-cli keys "game:*"

# Check specific game state
redis-cli get "game:your-game-id"

# Monitor memory usage
redis-cli info memory

# Real-time command monitor
redis-cli monitor
```

### Check Player Balances
```bash
# In your app or using a script
from models.player import get_player
player = get_player(1)
print(f"Real: {player.real_balance}, Fake: {player.fake_balance}")
```

---

## Security

### Secure Redis (Production)
If Redis is internet-facing, protect it:

```bash
# Edit Redis config
sudo nano /etc/redis/redis.conf

# Set these:
requirepass your_strong_password_here
bind 127.0.0.1  # Only localhost
```

Then set environment variable:
```bash
export REDIS_PASSWORD=your_strong_password_here
```

### Firewall (iptables)
```bash
# Only allow localhost to Redis
sudo iptables -A INPUT -p tcp --dport 6379 -s 127.0.0.1 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 6379 -j DROP
```

---

## Troubleshooting

### Session Complete Called Multiple Times (FIXED)
**Symptom:** Balance doubled in logs - saw 1543 then 2543
**Solution:** Already fixed! Backend now checks `was_already_completed` and skips awarding winnings on subsequent calls

### Redis Connection Error
```bash
# Check if Redis is running
sudo systemctl status redis-server

# Start if stopped
sudo systemctl start redis-server

# Test connection
redis-cli ping
```

### Wrong Balance Displayed
1. Check backend logs for award amount
2. Verify Redis is storing correct data
3. Clear browser cache and sessionStorage
4. Reload page

### Game State Lost Between Requests
1. Check Redis is running: `redis-cli ping`
2. Verify game keys exist: `redis-cli keys "game:*"`
3. Check Gunicorn logs for errors
4. Restart Redis: `sudo systemctl restart redis-server`

---

## Files Modified

| File | Changes |
|------|---------|
| `controllers/session_controller.py` | ✅ Added session completion check to prevent double-awarding (CRITICAL) |
| `static/js/game.js` | ✅ Removed all frontend balance calculations - only displays backend value |
| `static/js/game-start.js` | ✅ Removed initial_balance storage |
| `game/manager.py` or `manager_redis.py` | Game state persistence (if using Redis) |
| `app.py` | Manager integration (if using Redis) |

---

## Performance Notes

- **Redis Memory:** Game states are stored in Redis; memory usage depends on number of concurrent games
- **Request Latency:** Redis queries add ~1-2ms latency (negligible)
- **Scaling:** Can handle thousands of concurrent games with proper Redis configuration

---

## Fallback Behavior

If Redis is unavailable:
- ✅ Development on Windows continues to work (in-memory)
- ✅ Single-worker deployment works (in-memory per worker)
- ❌ Multi-worker deployment requires Redis

**Recommendation:** Always use Redis in production with multiple Gunicorn workers.
