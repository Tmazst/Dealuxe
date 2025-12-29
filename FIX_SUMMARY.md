# Production Bug Fix Summary

## The Problem

**Error:** `AssertionError` at line 105 in `engine.py`
```python
assert self.state.phase == "ATTACK"
```

**Why it happened:**
- Works fine on Windows (single Flask process)
- Crashes on VPS with Gunicorn (multiple worker processes)
- Each Gunicorn worker has its own memory/state
- Request 1 (create game) → handled by Worker A
- Request 2 (attack) → handled by Worker B (doesn't have the game state!)

## The Root Cause

**Multi-Worker State Isolation**

```
Worker 1: manager.games = {game_id: engine_instance_A}
Worker 2: manager.games = {game_id: ???}  ← Different memory space!
Worker 3: manager.games = {game_id: ???}  ← Different memory space!
```

When Worker 2 handles the attack request, it can't find the game, so it either:
1. Raises KeyError, or
2. Creates a fresh engine with default state (phase="ATTACK" initially)
3. But if ANY previous action changed the phase, that's lost

## The Solution

### 1. **Redis-Based Session Storage** (Primary Fix)

Created `game/manager_redis.py` that stores game state in Redis (shared memory all workers can access):

```
Worker 1 → Redis → {game_id: serialized_engine}
Worker 2 → Redis → Reads same game_id
Worker 3 → Redis → Reads same game_id
```

**Key changes:**
- `manager.create_game()` → stores in Redis
- `manager.get_game()` → retrieves from Redis
- `manager.update_game()` → saves changes back to Redis (CRITICAL!)

### 2. **Update app.py Routes**

Added `manager.update_game(game_id, engine)` after every state-changing operation:

```python
@app.route("/api/game/<game_id>/attack", methods=["POST"])
def attack(game_id):
    engine = manager.get_game(game_id)
    controller = FlaskGameController(engine)
    index = int(request.json["index"])
    result = controller.attack(index)
    
    # THIS IS CRITICAL! Save state back to Redis
    manager.update_game(game_id, engine)
    
    return result
```

### 3. **Better Error Handling**

Replaced `assert` with proper error returns:

```python
# Before (crashes app):
assert self.state.phase == "ATTACK"

# After (returns error to user):
if self.state.phase != "ATTACK":
    return {"error": f"Cannot attack during {self.state.phase} phase"}
```

---

## Files Modified

1. ✅ `game/manager_redis.py` - New Redis-backed manager
2. ✅ `app.py` - Added `update_game()` calls
3. ✅ `game/engine.py` - Better error handling
4. ✅ `requirements.txt` - Added `redis`
5. ✅ `DEPLOYMENT_FIX.md` - Deployment instructions
6. ✅ `test_redis_manager.py` - Test script

---

## What You Need to Do on VPS

1. **Install Redis:**
   ```bash
   sudo apt install redis-server -y
   sudo systemctl start redis-server
   ```

2. **Replace files:**
   ```bash
   cd /var/www/dealuxe-2/Dealuxe
   
   # Backup original
   cp game/manager.py game/manager_backup.py
   
   # Upload new files from Windows workspace:
   # - game/manager_redis.py → rename to game/manager.py
   # - app.py (updated version)
   # - game/engine.py (updated version)
   ```

3. **Install Redis package:**
   ```bash
   source venv/bin/activate
   pip install redis
   ```

4. **Restart Gunicorn:**
   ```bash
   sudo systemctl restart gunicorn
   ```

---

## Verification

After deployment, check logs:
```bash
sudo journalctl -u gunicorn -f
```

You should see:
```
[MANAGER] Connected to Redis at localhost:6379
[MANAGER] Created game <uuid> in Redis (human_vs_ai)
```

**No more AssertionError!**

---

## Why This Fixes It

**Before:**
- Game state lived only in the worker that created it
- Other workers couldn't access it → stale/wrong state → assertion fails

**After:**
- Game state lives in Redis (shared storage)
- All workers read from and write to the same Redis instance
- State changes are persisted and visible to all workers
- Even if Worker 1 creates the game, Worker 2 can handle the attack correctly

---

## Alternative (Quick Fix Without Redis)

If you can't install Redis right now, run Gunicorn with 1 worker:

```bash
gunicorn --workers 1 --bind 0.0.0.0:8000 app:app
```

⚠️ This limits concurrent request handling but fixes the state issue.

---

## Additional Safety

The improved error handling means even if something goes wrong with state, you'll get a proper error message like:

```json
{
  "error": "Cannot attack during DEFENSE phase. Expected ATTACK phase.",
  "current_phase": "DEFENSE"
}
```

Instead of the app crashing with `AssertionError`.
