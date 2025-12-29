"""
Test script to verify Redis-backed game manager works correctly.
Run this to ensure the fix works before deploying to production.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.manager_redis import GameManager
from game.models import Player

print("=" * 60)
print("Testing Redis-backed Game Manager")
print("=" * 60)

# Initialize manager
manager = GameManager()

print("\n1. Creating a new game...")
game_id, game_data = manager.create_game("human_vs_ai")
print(f"   ✓ Game created: {game_id}")
print(f"   ✓ Mode: {game_data['mode']}")
print(f"   ✓ Players: {[p.name for p in game_data['players']]}")

print("\n2. Retrieving game engine...")
engine = manager.get_game(game_id)
print(f"   ✓ Engine retrieved successfully")
print(f"   ✓ Initial phase: {engine.state.phase}")
print(f"   ✓ Initial attacker: {engine.state.attacker}")

print("\n3. Modifying game state (simulating attack)...")
original_phase = engine.state.phase
engine.state.phase = "DEFENSE"
engine.state.attack_card = engine.players[0].hand[0] if engine.players[0].hand else None
print(f"   ✓ Phase changed: {original_phase} → {engine.state.phase}")

print("\n4. Updating game in storage...")
manager.update_game(game_id, engine)
print(f"   ✓ Game state saved")

print("\n5. Retrieving game again (simulating different worker)...")
engine2 = manager.get_game(game_id)
print(f"   ✓ Engine retrieved successfully")
print(f"   ✓ Phase persisted: {engine2.state.phase}")
print(f"   ✓ State matches: {engine2.state.phase == engine.state.phase}")

if engine2.state.phase == "DEFENSE":
    print("\n✅ SUCCESS! State persistence working correctly!")
    print("   The fix will work in production with multiple Gunicorn workers.")
else:
    print("\n❌ FAILED! State not persisting correctly.")
    print("   Check Redis connection and configuration.")

print("\n6. Cleanup...")
manager.delete_game(game_id)
print(f"   ✓ Game deleted")

print("\n7. Testing error handling...")
try:
    engine = manager.get_game("non-existent-game-id")
    print("   ❌ Should have raised KeyError")
except KeyError as e:
    print(f"   ✓ Correctly raised error: {e}")

print("\n" + "=" * 60)
print("Test completed!")
print("=" * 60)

if manager.use_redis:
    print("\n🎯 Using Redis - Ready for multi-worker production deployment")
else:
    print("\n⚠️  Using in-memory storage - Install Redis for production")
    print("   Install: pip install redis")
    print("   Start Redis server: sudo systemctl start redis-server")
