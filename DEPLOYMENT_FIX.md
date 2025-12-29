# Fix for Production AssertionError - Multi-Worker State Management

## Problem
The game state was not persisting between HTTP requests because Gunicorn runs multiple worker processes, each with its own memory. Game created in Worker 1 couldn't be accessed by Worker 2.

## Solution
Implemented Redis-based session storage that all workers can access.

---

## Deployment Steps for VPS

### 1. Install Redis on Your VPS

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install redis-server -y

# Start Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Verify Redis is running
redis-cli ping
# Should return: PONG
```

### 2. Update Your Application Code

The following files have been modified:
- ✅ `game/manager_redis.py` - New Redis-backed manager
- ✅ `app.py` - Added `manager.update_game()` calls after state changes
- ✅ `requirements.txt` - Added `redis` package

### 3. Backup and Replace manager.py

```bash
# On your VPS
cd /var/www/dealuxe-2/Dealuxe

# Backup original manager
cp game/manager.py game/manager_backup.py

# Replace with Redis version
cp game/manager_redis.py game/manager.py
```

### 4. Install Redis Python Package

```bash
# Activate your virtualenv
source venv/bin/activate

# Install redis
pip install redis

# Or reinstall all requirements
pip install -r requirements.txt
```

### 5. Update app.py

Upload the updated `app.py` from this workspace to your VPS, replacing the existing one.

### 6. Restart Gunicorn

```bash
# Find your gunicorn process
ps aux | grep gunicorn

# Restart the service (adjust service name as needed)
sudo systemctl restart gunicorn
# OR
sudo systemctl restart dealuxe
# OR manually kill and restart
sudo pkill gunicorn
# Then start your gunicorn command again
```

### 7. Verify It Works

```bash
# Check Redis is accessible
redis-cli ping

# Check your app logs
sudo journalctl -u gunicorn -f
# OR
sudo tail -f /var/log/your-app-name.log

# You should see: "[MANAGER] Connected to Redis at localhost:6379"
```

---

## Configuration (Optional)

### Environment Variables

Set these if Redis is on a different host or requires auth:

```bash
export REDIS_HOST=localhost
export REDIS_PORT=6379
export REDIS_PASSWORD=your_password  # If Redis has password
```

Add to your systemd service file or `.env`:
```ini
Environment="REDIS_HOST=localhost"
Environment="REDIS_PORT=6379"
```

---

## Fallback Behavior

The new manager automatically falls back to in-memory storage if Redis is unavailable. This means:
- ✅ Development on Windows works without Redis
- ✅ Production requires Redis for multi-worker support
- ✅ No crashes if Redis temporarily goes down

---

## Testing

1. Create a game and note the game_id
2. Make an attack
3. Check logs - you should see:
   ```
   [MANAGER] Created game <uuid> in Redis (human_vs_ai)
   ```
   
4. No more AssertionError!

---

## Alternative Solution (If Redis is Not Available)

If you cannot install Redis, you can run Gunicorn with a single worker:

```bash
gunicorn --workers 1 --bind 0.0.0.0:8000 app:app
```

**Note:** This limits your app to handle one request at a time. Not recommended for production with multiple users.

---

## Monitoring Redis

```bash
# Check Redis memory usage
redis-cli info memory

# List all game keys
redis-cli keys "game:*"

# Check a specific game
redis-cli get "game:<game-id>"
```

---

## Security Note

If your Redis instance is exposed to the internet, secure it:

```bash
# Edit Redis config
sudo nano /etc/redis/redis.conf

# Set a password
requirepass your_strong_password_here

# Bind only to localhost
bind 127.0.0.1

# Restart Redis
sudo systemctl restart redis-server
```

Then set the environment variable:
```bash
export REDIS_PASSWORD=your_strong_password_here
```
