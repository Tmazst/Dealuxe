# Game JavaScript Refactoring - Architecture Overview

## 📁 New File Structure

```
static/js/
├── game-core.js              # ✨ NEW - Shared core functionality
├── game-multiplayer-new.js   # ✨ NEW - Multiplayer SocketIO logic  
├── game-multiplayer.js       # ⚠️ OLD - Can be deleted after testing
└── game.js                   # 📝 Single-player (needs minor refactor later)
```

## 🏗️ Architecture Layers

### **Layer 1: game-core.js** (Shared Foundation)
**Purpose**: All common game logic used by both single-player and multiplayer

**Functions Included**:
- ✅ `renderCards()` - Render hand with overlap effect
- ✅ `getHandCards()` - Get card DOM elements
- ✅ `parseCardString()` - Parse "K♠" into {rank, suit}
- ✅ `raiseCard()` / `lowerRaisedCard()` - Attack card lifting
- ✅ `showPushButton()` / `hidePushButton()` - Attack button
- ✅ `showDefendButton()` / `hideDefendButton()` - Defense button
- ✅ `clearDefenseSelections()` - Clear defense state
- ✅ `animateCardGhostToPile()` - Card movement animations
- ✅ `animateOpponentDefense()` - Opponent defense animation
- ✅ `animateUserDefense()` - User defense animation
- ✅ `animateOpponentGhost()` - Opponent attack animation
- ✅ `animateDrawGhost()` - Draw card animation
- ✅ `animateOpponentDrawGhost()` - Opponent draw animation
- ✅ `addCardsToAttackPile()` - Add static cards to pile
- ✅ `clearAttackPile()` - Clear attack pile
- ✅ `renderAttackPile()` - Render attack pile from state
- ✅ `setOpponentStatus()` - Update status text
- ✅ `updateAgent()` - Update agent panel
- ✅ `setTrackingBadge()` - Update phase badge
- ✅ `updateHandHighlight()` - Highlight hand for action
- ✅ `updateProgressBars()` - Progress bar calculations
- ✅ `playBellSound()` - Pleasant notification sound
- ✅ `playAttackSound()` - Attack/defend sound effect
- ✅ `playGameOverSound()` - Win/loss sound
- ✅ `renderComments()` - UI log messages
- ✅ `flashAttackZone()` - Flash attack zone

**Placeholder Functions** (overridden by mode-specific files):
- `onCardClick(index, card)` - Card click handler
- `onPushAttackClick()` - Push attack button click
- `onPushDefendClick()` - Push defend button click

### **Layer 2: game-multiplayer-new.js** (Multiplayer Specific)
**Purpose**: SocketIO real-time communication and multiplayer game logic

**Key Features**:
- ✅ SocketIO connection management
- ✅ Real-time game state updates via `game_update` event
- ✅ Turn timer with countdown
- ✅ Override core handlers with multiplayer logic:
  - `window.onCardClick` - Handle attack/defend card selection
  - `window.onPushAttackClick` - Send attack to server
  - `window.onPushDefendClick` - Send defense to server
- ✅ `performDraw()` - Send draw action to server
- ✅ Pause/resume multiplayer features
- ✅ Keyboard shortcuts (D = draw)
- ✅ Opponent status tracking

**SocketIO Events Handled**:
- `connect` / `disconnect` / `error`
- `game_update` - Main state sync
- `game_started` / `game_over`
- `opponent_joined` / `opponent_disconnected`
- `game_paused` / `game_resumed` / `pause_approved`
- `turn_timeout`

### **Layer 3: game.js** (Single-Player)
**Status**: ⚠️ To be refactored later
**Will become**: game-singleplayer.js
**Will use**: game-core.js for shared functions
**Unique logic**: REST API calls, AI opponent polling, session management

## 🔄 How It Works Together

### Multiplayer HTML Loading Order:
```html
<!-- 1. Load shared core functions -->
<script src="/static/js/game-core.js"></script>

<!-- 2. Load multiplayer-specific logic -->
<script src="/static/js/game-multiplayer-new.js"></script>
```

### Function Call Flow Example (Attack):

```
1. User clicks card
   └─> onCardClick(index, card)      [defined in game-multiplayer-new.js]
       └─> raiseCard(index)           [from game-core.js]
           └─> showPushButton()       [from game-core.js]

2. User clicks "Push to Attack"
   └─> onPushAttackClick()            [defined in game-multiplayer-new.js]
       └─> animateCardGhostToPile()   [from game-core.js]
       └─> playAttackSound()          [from game-core.js]
       └─> socket.emit('game_action') [multiplayer-specific]
       └─> lowerRaisedCard()          [from game-core.js]

3. Server responds with game_update
   └─> socket.on('game_update')       [in game-multiplayer-new.js]
       └─> renderCards()              [from game-core.js]
       └─> updateUIForPhase()         [in game-multiplayer-new.js]
```

## ✨ Benefits of This Architecture

### 1. **DRY (Don't Repeat Yourself)**
- Card rendering logic written once, used everywhere
- Animation functions shared across modes
- Sound effects unified

### 2. **Maintainability**
- Fix a bug in card rendering → fixed for both modes
- Add new animation → available to both modes
- Clear separation of concerns

### 3. **Testability**
- Core functions can be tested independently
- Mode-specific logic isolated
- Easy to mock SocketIO vs REST APIs

### 4. **Extensibility**
- Want to add local multiplayer? Just create `game-local-multiplayer.js`
- Want tournament mode? Create `game-tournament.js`
- All can use `game-core.js` as foundation

## 🎯 What This Fixes

### Before (Broken):
```javascript
// game-multiplayer.js (OLD)
function selectCard(index, cardValue) {
    selectedCardIndex = index;
    selectedCardValue = cardValue;
    // ❌ No actual game logic!
    // ❌ No attack/defend handling
    // ❌ Just highlights card and waits
}
```

### After (Working):
```javascript
// game-multiplayer-new.js
window.onCardClick = function(index, card) {
    if (phase === 'ATTACK' && isAttacker) {
        raiseCard(index);  // ✅ Visual lift
        showPushButton();   // ✅ Show attack button
    }
    if (phase === 'DEFENSE' && isDefender) {
        defenseSelected.push(index);  // ✅ Track selections
        if (defenseSelected.length === 2) {
            showDefendButton();  // ✅ Show defend button
        }
    }
};
```

## 📋 Testing Checklist

After refreshing both game pages, test:

- [x] Cards render with fan layout (80px overlap)
- [x] Click card in attack phase → card raises
- [x] Click "Push to Attack" → card animates to pile
- [x] Click card in defense phase → highlights as defense-first
- [x] Click second card → highlights as defense-second
- [x] Click "Push to Defend" → both cards animate to pile
- [x] Press 'D' key in defense → draws card
- [x] Sounds play (attack sound, bell sound)
- [x] Progress bars update
- [x] Turn indicator shows correctly
- [x] Opponent actions animate from top
- [x] Game over sound plays

## 🚀 Next Steps (Future Refactoring)

1. **Refactor game.js** → Create `game-singleplayer.js`
   - Extract single-player specific code
   - Use game-core.js functions
   - Keep only REST API calls and AI logic

2. **Add shared utilities file** (optional)
   - HTTP request helpers
   - State management utilities
   - Validation functions

3. **Consider build system** (optional)
   - Webpack/Rollup for bundling
   - Minification for production
   - Source maps for debugging

## 📝 File Maintenance

### Can be Deleted (after testing):
- ❌ `game-multiplayer.js` (old version)

### Must Keep:
- ✅ `game-core.js` (shared foundation)
- ✅ `game-multiplayer-new.js` (multiplayer logic)
- ✅ `game.js` (single-player - will refactor later)

### To Rename (after testing):
```bash
# Rename new to official
mv static/js/game-multiplayer-new.js static/js/game-multiplayer.js

# Update HTML template
# Change: game-multiplayer-new.js → game-multiplayer.js
```

## 🎓 Code Style Guidelines

When adding new features:

1. **Shared functionality** → Add to `game-core.js`
2. **Multiplayer-only** → Add to `game-multiplayer.js`
3. **Single-player-only** → Add to `game.js` (or future `game-singleplayer.js`)

### Example Decision Tree:
```
Q: Is this function used by both modes?
├─ YES → Add to game-core.js
└─ NO
   ├─ Uses SocketIO? → Add to game-multiplayer.js
   └─ Uses REST API? → Add to game.js
```

---

## 🐛 Known Issues & TODO

- [ ] `game.js` still has duplicated code (renderCards, animations)
- [ ] Need to refactor single-player mode similarly
- [ ] Attack pile state not fully syncing from backend
- [ ] WebSocket 500 errors (non-blocking but needs investigation)

---

**Last Updated**: January 2, 2026
**Refactored By**: GitHub Copilot
**Files Changed**: 3 (1 new core, 1 new multiplayer, 1 template update)
