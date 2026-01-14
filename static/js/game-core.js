// ==============================================
// GAME-CORE.JS - Shared Game Logic & UI
// ==============================================
// This file contains all shared functionality used by both 
// single-player and multiplayer modes

// ==============================================
// SHARED STATE & VARIABLES
// ==============================================

let currentState = null;
let previousCardCounts = { me: null, opponent: null };
let playerMaxSeen = {};

// Card selection state
let raisedCardIndex = null;
let defenseSelected = [];
let selectedCardIndex = null;
let selectedCardValue = null;

// Attack/defense animations
let pendingOpponentAttack = null;
let lastDisplayedAttack = null;

// Request locking
let isRequestInProgress = false;

// ==============================================
// CARD RENDERING
// ==============================================

/**
 * Render cards in player's hand with overlap effect
 * @param {Array} cards - Array of card strings like ["K♠", "7♥"]
 */
function renderCards(cards) {
    console.log("[UI] Rendering cards:", cards);
    
    // Parse card strings into {rank, suit} objects
    const parsedCards = cards.map(cardStr => {
        const rank = cardStr.slice(0, -1);
        const suit = cardStr.slice(-1);
        return { rank, suit };
    });
    
    const container = document.getElementById("player-cards");
    if (!container) return;
    
    container.innerHTML = "";
    const overlap = 80; // px overlap between cards

    parsedCards.forEach((card, index) => {
        const div = document.createElement("div");
        div.className = "card player-card";
        div.style.left = `${index * overlap}px`;
        div.style.zIndex = index;
        div.dataset.cardIndex = index;

        div.innerHTML = `
            <div class="rank">${card.rank}</div>
            <div class="center">${card.suit}</div>
            <div class="suit">${card.suit}</div>
        `;

        // Card click handler (will be overridden by mode-specific logic)
        div.addEventListener("click", () => onCardClick(index, card));

        container.appendChild(div);
    });
}

/**
 * Get all card elements currently in hand
 * @returns {Array} Array of card DOM elements
 */
function getHandCards() {
    const container = document.getElementById('player-cards');
    if (!container) return [];
    return Array.from(container.querySelectorAll('.card'));
}

/**
 * Parse card string into {rank, suit} object
 * @param {String} s - Card string like "K♠" or "7Hearts"
 * @returns {Object} {rank, suit}
 */
function parseCardString(s) {
    if (!s) return { rank: s, suit: '' };
    const str = String(s).replace(/\s*icon$/i, '').trim();
    const m = str.match(/^([0-9]{1,2}|[AJQK])([a-zA-Z]+)$/i);
    if (m) return { rank: m[1], suit: m[2] };
    const alt = str.match(/^(.+?)([a-zA-Z]+)$/);
    if (alt) return { rank: alt[1], suit: alt[2] };
    return { rank: str, suit: '' };
}

// ==============================================
// CARD INTERACTION - ATTACK MODE
// ==============================================

/**
 * Raise a card for attack (visual lift effect)
 * @param {Number} index - Index of card in hand
 */
function raiseCard(index) {
    const cards = getHandCards();
    if (!cards[index]) return;
    
    raisedCardIndex = index;
    cards[index].classList.add('raised');
    showPushButton();
    
    // Add click listener to lower card when clicking elsewhere
    setTimeout(() => {
        document.addEventListener('click', onDocumentClickWhileRaised, true);
    }, 0);
}

/**
 * Lower the currently raised card
 */
function lowerRaisedCard() {
    if (raisedCardIndex === null) return;
    
    const cards = getHandCards();
    if (cards[raisedCardIndex]) {
        cards[raisedCardIndex].classList.remove('raised');
    }
    
    raisedCardIndex = null;
    hidePushButton();
    
    document.removeEventListener('click', onDocumentClickWhileRaised, true);
}

/**
 * Handle clicks outside raised card
 */
function onDocumentClickWhileRaised(e) {
    const cards = getHandCards();
    const pushBtn = document.getElementById('push-attack-btn');
    
    if (raisedCardIndex !== null && cards[raisedCardIndex]) {
        if (cards[raisedCardIndex].contains(e.target)) return;
    }
    
    if (pushBtn && pushBtn.contains(e.target)) return;
    
    lowerRaisedCard();
}

/**
 * Show push attack button
 */
function showPushButton() {
    let btn = document.getElementById('push-attack-btn');
    if (!btn) {
        btn = document.createElement('button');
        btn.id = 'push-attack-btn';
        btn.className = 'btn push-attack-btn';
        btn.innerHTML = '<i class="fa-solid fa-arrow-up"></i> Push to Attack';
        
        const handBox = document.querySelector('.player-cards-box');
        if (handBox) {
            handBox.appendChild(btn);
        } else {
            document.body.appendChild(btn);
        }
        
        // Click handler will be added by mode-specific code
        btn.addEventListener('click', onPushAttackClick);
    }
    btn.style.display = 'block';
}

/**
 * Hide push attack button
 */
function hidePushButton() {
    const btn = document.getElementById('push-attack-btn');
    if (btn) btn.style.display = 'none';
}

// ==============================================
// CARD INTERACTION - DEFENSE MODE
// ==============================================

/**
 * Show defend confirmation button
 */
function showDefendButton() {
    let btn = document.getElementById('defend-confirm-btn');
    if (!btn) {
        btn = document.createElement('button');
        btn.id = 'defend-confirm-btn';
        btn.className = 'btn defend-btn';
        btn.innerHTML = '<i class="fa-solid fa-shield"></i> Push to Defend';
        
        const handBox = document.querySelector('.player-cards-box');
        if (handBox) {
            handBox.appendChild(btn);
        } else {
            document.body.appendChild(btn);
        }
        
        // Click handler will be added by mode-specific code
        btn.addEventListener('click', onPushDefendClick);
    }
    btn.style.display = 'block';
}

/**
 * Hide defend button
 */
function hideDefendButton() {
    const btn = document.getElementById('defend-confirm-btn');
    if (btn) btn.style.display = 'none';
}

/**
 * Hide defend button if less than 2 cards selected
 */
function hideDefendButtonIfNeeded() {
    if (defenseSelected.length < 2) hideDefendButton();
}

/**
 * Clear all defense selections
 */
function clearDefenseSelections() {
    const cards = getHandCards();
    defenseSelected.forEach(i => {
        if (cards[i]) cards[i].classList.remove('defense-first', 'defense-second');
    });
    defenseSelected = [];
}

// ==============================================
// ANIMATIONS - GHOST CARDS
// ==============================================

/**
 * Animate ghost card from one position to another
 * @param {HTMLElement} cardEl - Source card element
 * @param {String} targetId - ID of target element
 * @returns {Promise}
 */
function animateCardGhostToPile(cardEl, targetId = 'attack-pile') {
    return new Promise((resolve) => {
        const pile = document.getElementById(targetId);
        if (!pile || !cardEl) return resolve();

        const cardRect = cardEl.getBoundingClientRect();
        const pileRect = pile.getBoundingClientRect();

        const ghost = document.createElement('div');
        ghost.className = 'card ghost player-card entering';
        ghost.innerHTML = cardEl.innerHTML;
        document.body.appendChild(ghost);

        ghost.style.left = cardRect.left + 'px';
        ghost.style.top = cardRect.top + 'px';
        ghost.style.width = cardRect.width + 'px';
        ghost.style.height = cardRect.height + 'px';

        requestAnimationFrame(() => {
            ghost.classList.add('visible');
            ghost.classList.remove('entering');
        });

        const targetX = pileRect.left + (pileRect.width / 2) - (cardRect.width / 2);
        const targetY = pileRect.top + (pileRect.height / 2) - (cardRect.height / 2);

        requestAnimationFrame(() => {
            const dx = targetX - cardRect.left;
            const dy = targetY - cardRect.top;
            ghost.style.transform = `translate(${dx}px, ${dy}px) scale(0.85)`;
        });

        const cleanup = () => {
            ghost.removeEventListener('transitionend', cleanup);
            ghost.classList.add('fade-out');
            setTimeout(() => { 
                try { ghost.remove(); } catch (e) {} 
                resolve(); 
            }, 240);
        };

        ghost.addEventListener('transitionend', cleanup);
        setTimeout(() => { if (document.body.contains(ghost)) { cleanup(); } }, 1000);
    });
}

/**
 * Animate opponent's defense cards flying from top to attack pile
 * @param {Array} values - Array of card values
 */
function animateOpponentDefense(values) {
    const pile = document.getElementById("attack-pile");
    const zone = document.getElementById("attack-zone");
    if (!pile) return;
    const pileRect = pile.getBoundingClientRect();

    const cards = values.map(v => parseCardString(v));

    cards.forEach((card, i) => {
        const ghost = document.createElement("div");
        ghost.className = "card ghost opponent-card entering";
        ghost.innerHTML = `
            <div class="rank">${card.rank}</div>
            <div class="center">${card.suit}</div>
            <div class="suit">${card.suit}</div>
        `;

        document.body.appendChild(ghost);
        ghost.style.position = "fixed";
        ghost.style.left = "50%";
        ghost.style.top = "-200px";
        ghost.style.transform = "translateX(-50%) scale(0.6)";
        ghost.style.zIndex = 1000;
        ghost.style.opacity = "0";

        const offsetX = i === 0 ? -12 : 12;
        const rotate = i === 0 ? -6 : 6;

        setTimeout(() => {
            ghost.classList.remove('entering');
            ghost.classList.add('visible');
            ghost.style.transition = "all 0.6s cubic-bezier(0.34, 1.56, 0.64, 1)";
            ghost.style.left = (pileRect.left + pileRect.width/2 + offsetX) + "px";
            ghost.style.top = (pileRect.top + pileRect.height/2) + "px";
            ghost.style.transform = `translate(-50%, -50%) rotate(${rotate}deg) scale(0.9)`;
            ghost.style.opacity = "1";
        }, i * 100);

        setTimeout(() => {
            if (zone) {
                zone.classList.add('flash');
                setTimeout(() => zone.classList.remove('flash'), 600);
            }
        }, 600 + (i * 100));

        setTimeout(() => {
            ghost.classList.add('fade-out');
            setTimeout(() => ghost.remove(), 400);
        }, 1500 + (i * 100));
    });

    addCardsToAttackPile(cards, 'opponent-card');
    setOpponentStatus("Opponent defended with: " + cards.map(v => v.rank + v.suit).join(", "));
}

/**
 * Animate user's defense cards flying from bottom to attack pile
 * @param {Array} values - Array of card values
 */
function animateUserDefense(values) {
    const pile = document.getElementById("attack-pile");
    const zone = document.getElementById("attack-zone");
    if (!pile) return;
    const pileRect = pile.getBoundingClientRect();

    const cards = values.map(v => parseCardString(v));

    cards.forEach((card, i) => {
        const ghost = document.createElement("div");
        ghost.className = "card ghost player-card entering";
        ghost.innerHTML = `
            <div class="rank">${card.rank}</div>
            <div class="center">${card.suit}</div>
            <div class="suit">${card.suit}</div>
        `;

        document.body.appendChild(ghost);
        ghost.style.position = "fixed";
        ghost.style.left = "50%";
        ghost.style.bottom = "-200px";
        ghost.style.transform = "translateX(-50%) scale(0.6)";
        ghost.style.zIndex = 1000;
        ghost.style.opacity = "0";

        const offsetX = i === 0 ? -12 : 12;
        const rotate = i === 0 ? -6 : 6;

        setTimeout(() => {
            ghost.classList.remove('entering');
            ghost.classList.add('visible');
            ghost.style.transition = "all 0.6s cubic-bezier(0.34, 1.56, 0.64, 1)";
            ghost.style.left = (pileRect.left + pileRect.width/2 + offsetX) + "px";
            ghost.style.top = (pileRect.top + pileRect.height/2) + "px";
            ghost.style.bottom = "auto";
            ghost.style.transform = `translate(-50%, -50%) rotate(${rotate}deg) scale(0.9)`;
            ghost.style.opacity = "1";
        }, i * 100);

        setTimeout(() => {
            if (zone) {
                zone.classList.add('flash');
                setTimeout(() => zone.classList.remove('flash'), 600);
            }
        }, 600 + (i * 100));

        setTimeout(() => {
            ghost.classList.add('fade-out');
            setTimeout(() => ghost.remove(), 400);
        }, 1500 + (i * 100));
    });

    addCardsToAttackPile(cards, 'player-card');
    setOpponentStatus("You defended with: " + cards.map(v => v.rank + v.suit).join(", "));
}

/**
 * Animate opponent's ghost card from top to attack pile
 * @param {String} value - Card value
 * @returns {Promise}
 */
function animateOpponentGhost(value) {
    return new Promise((resolve) => {
        const pile = document.getElementById('attack-pile');
        if (!pile) return resolve();
        const pileRect = pile.getBoundingClientRect();

        const startX = window.innerWidth / 2;
        const startY = Math.max(24, pileRect.top - 160);

        const card = parseCardString(value);
        const ghost = document.createElement('div');
        ghost.className = 'card ghost opponent-card entering';
        ghost.innerHTML = `
            <div class="rank">${card.rank}</div>
            <div class="center">${card.suit}</div>
            <div class="suit">${card.suit}</div>
        `;
        document.body.appendChild(ghost);

        ghost.style.left = startX - 60 + 'px';
        ghost.style.top = startY + 'px';

        requestAnimationFrame(() => {
            ghost.classList.add('visible');
            ghost.classList.remove('entering');
        });

        const targetX = pileRect.left + (pileRect.width / 2) - 60;
        const targetY = pileRect.top + (pileRect.height / 2) - 85;

        requestAnimationFrame(() => {
            const dx = targetX - (startX - 60);
            const dy = targetY - startY;
            ghost.style.transform = `translate(${dx}px, ${dy}px) scale(0.92)`;
        });

        const cleanup = () => {
            ghost.removeEventListener('transitionend', cleanup);
            ghost.classList.add('fade-out');
            setTimeout(() => { try { ghost.remove(); } catch (e) {} resolve(); }, 240);
        };
        ghost.addEventListener('transitionend', cleanup);
        setTimeout(() => { if (document.body.contains(ghost)) { cleanup(); } }, 900);
    });
}

/**
 * Animate draw ghost card from button to hand
 * @returns {Promise}
 */
function animateDrawGhost() {
    return new Promise((resolve) => {
        const btn = document.getElementById('draw-button');
        const hand = document.getElementById('player-cards');
        if (!btn || !hand) return resolve();

        const startRect = btn.getBoundingClientRect();
        const targetRect = hand.getBoundingClientRect();

        const ghost = document.createElement('div');
        ghost.className = 'card ghost entering';
        ghost.innerHTML = `
            <div class="rank">?</div>
            <div class="center">♦</div>
            <div class="suit">?</div>
        `;
        document.body.appendChild(ghost);

        const startX = startRect.left + (startRect.width / 2) - 60;
        const startY = startRect.top + (startRect.height / 2) - 85;
        ghost.style.left = startX + 'px';
        ghost.style.top = startY + 'px';

        requestAnimationFrame(() => {
            ghost.classList.add('visible');
            ghost.classList.remove('entering');
        });

        const targetX = targetRect.left + (targetRect.width / 2) - 60;
        const targetY = targetRect.top + (targetRect.height / 2) - 85;

        requestAnimationFrame(() => {
            const dx = targetX - startX;
            const dy = targetY - startY;
            ghost.style.transform = `translate(${dx}px, ${dy}px) scale(0.98)`;
        });

        const cleanup = () => {
            ghost.removeEventListener('transitionend', cleanup);
            ghost.classList.add('fade-out');
            setTimeout(() => { try { ghost.remove(); } catch (e) {} resolve(); }, 240);
        };

        ghost.addEventListener('transitionend', cleanup);
        setTimeout(() => { if (document.body.contains(ghost)) { cleanup(); } }, 1000);
    });
}

/**
 * Animate opponent drawing a ghost card
 * @returns {Promise}
 */
function animateOpponentDrawGhost() {
    return new Promise((resolve) => {
        const pile = document.getElementById('attack-pile');
        if (!pile) return resolve();

        const pileRect = pile.getBoundingClientRect();
        const startX = window.innerWidth - 120;
        const startY = window.innerHeight - 200;

        const ghost = document.createElement('div');
        ghost.className = 'card ghost entering';
        ghost.innerHTML = `
            <div class="rank">?</div>
            <div class="center">♣</div>
            <div class="suit">?</div>
        `;
        document.body.appendChild(ghost);

        ghost.style.left = startX + 'px';
        ghost.style.top = startY + 'px';

        requestAnimationFrame(() => {
            ghost.classList.add('visible');
            ghost.classList.remove('entering');
        });

        const targetX = (window.innerWidth / 2) - 60;
        const targetY = -200;

        requestAnimationFrame(() => {
            const dx = targetX - startX;
            const dy = targetY - startY;
            ghost.style.transform = `translate(${dx}px, ${dy}px) scale(0.92)`;
        });

        const cleanup = () => {
            ghost.removeEventListener('transitionend', cleanup);
            ghost.classList.add('fade-out');
            setTimeout(() => { try { ghost.remove(); } catch (e) {} resolve(); }, 240);
        };

        ghost.addEventListener('transitionend', cleanup);
        setTimeout(() => { if (document.body.contains(ghost)) { cleanup(); } }, 1000);
    });
}

// ==============================================
// ATTACK PILE MANAGEMENT
// ==============================================

/**
 * Add static cards to attack pile
 * @param {Array} cards - Array of {rank, suit} objects
 * @param {String} cardClass - CSS class ('player-card' or 'opponent-card')
 */
function addCardsToAttackPile(cards, cardClass) {
    const pile = document.getElementById('attack-pile');
    if (!pile) return;
    const pileRect = pile.getBoundingClientRect();

    const maxCardsAcross = 3;
    const cardMargin = 6;
    const cardWidth = Math.max(40, Math.floor((pileRect.width - (cardMargin * (maxCardsAcross + 1))) / maxCardsAcross));
    const cardHeight = Math.max(56, Math.floor(pileRect.height - 8));

    cards.forEach((card, i) => {
        const el = document.createElement('div');
        el.className = `card pile-defense ${cardClass} entering`;
        el.innerHTML = `
            <div class="rank">${card.rank}</div>
            <div class="center">${card.suit}</div>
            <div class="suit">${card.suit}</div>
        `;
        el.style.width = cardWidth + 20 + 'px';
        el.style.height = cardHeight + 'px';
        el.style.display = 'inline-block';
        el.style.margin = cardMargin + 'px';
        el.style.verticalAlign = 'top';

        pile.appendChild(el);
        requestAnimationFrame(() => el.classList.remove('entering'));
    });
}

/**
 * Clear attack pile visual
 */
function clearAttackPile() {
    const pile = document.getElementById('attack-pile');
    if (pile) pile.innerHTML = '';
}

/**
 * Render attack pile from state data
 * @param {Array} attackPile - Array of card strings
 */
function renderAttackPile(attackPile) {
    const zone = document.getElementById('attack-zone');
    if (!zone) return;
    console.debug('renderAttackPile called with:', attackPile);
    
    if (attackPile && attackPile.length > 0) {
        zone.innerHTML = attackPile.map(card => `
            <div class="card-small">${card}</div>
        `).join('');
    } else {
        zone.innerHTML = 'DROP CARD HERE';
    }
}

// ==============================================
// UI UPDATES
// ==============================================

/**
 * Update opponent status message
 * @param {String} text - Status message
 */
function setOpponentStatus(text) {
    const agentText = document.getElementById("agent-text");
    if (agentText) agentText.textContent = text;
}

/**
 * Update agent panel with message and type
 * @param {String} message - Message to display
 * @param {String} type - Type: 'info', 'error', 'warning', 'success'
 */
function updateAgent(message, type = 'info') {
    const text = document.getElementById('agent-text');
    const agentPanel = document.getElementById('agent-panel');
    
    if (text) text.textContent = message;
    
    if (agentPanel) {
        const icon = agentPanel.querySelector('.agent-icon');
        if (icon) {
            if (type === 'error' || type === 'warning') {
                icon.className = 'fa-solid fa-exclamation-triangle agent-icon';
            } else if (type === 'success') {
                icon.className = 'fa-solid fa-check-circle agent-icon';
            } else {
                icon.className = 'fa-solid fa-gamepad agent-icon';
            }
        }
    }
}

/**
 * Set tracking badge text and style
 * @param {String} text - Badge text
 * @param {String} type - Type: 'attack', 'defend', 'draw', 'info'
 */
function setTrackingBadge(text, type = "info") {
    const badge = document.querySelector('.tracking-badge');
    if (!badge) return;
    badge.textContent = text;
    badge.classList.remove('attack', 'defend', 'draw', 'info');
    badge.classList.add(type);
}

/**
 * Update hand highlight based on mode
 * @param {String} mode - 'attack', 'draw', or 'none'
 */
function updateHandHighlight(mode) {
    const hand = document.getElementById('player-cards');
    if (!hand) return;
    hand.classList.remove('hand-attack', 'hand-draw');
    if (mode === 'attack') hand.classList.add('hand-attack');
    else if (mode === 'draw') hand.classList.add('hand-draw');
}

/**
 * Update progress bars based on player data
 * @param {Object} data - Game state with players array
 */
function updateProgressBars(data) {
    if (!data || !Array.isArray(data.players)) return;
    const container = document.getElementById('leader-progess-bars-cont');
    if (!container) return;

    const players = data.players;
    players.forEach(p => {
        const key = String(p.id);
        const val = p.hand_count || 0;
        if (!playerMaxSeen[key] || playerMaxSeen[key] < val) playerMaxSeen[key] = val;
    });

    const userCont = container.querySelector('.user-progress-bar-cont');
    const oppCont = container.querySelector('.opponent-progress-bar-cont');

    const leftPlayer = players[0] || null;
    const rightPlayer = players[1] || players[0] || null;

    function updateCont(cont, player) {
        if (!cont || !player) return;
        const key = String(player.id);
        const maxSeen = playerMaxSeen[key] || Math.max(1, player.hand_count || 1);
        const current = player.hand_count || 0;
        const percent = Math.round(((maxSeen - current) / Math.max(1, maxSeen)) * 100);

        const fill = cont.querySelector('.user-progress-fill');
        const text = cont.querySelector('.user-progress-text');
        if (fill) fill.style.width = percent + '%';
        if (text) text.textContent = percent + '%';
        
        const other = (player === leftPlayer) ? rightPlayer : leftPlayer;
        if (other) {
            if (player.hand_count < other.hand_count) {
                fill && fill.classList.add('winner');
                fill && fill.classList.remove('loser');
                cont.classList.add('winner');
                cont.classList.remove('loser');
            } else {
                fill && fill.classList.remove('winner');
                fill && fill.classList.add('loser');
                cont.classList.remove('winner');
                cont.classList.add('loser');
            }
        }
    }

    updateCont(userCont, leftPlayer);
    updateCont(oppCont, rightPlayer);
}

// ==============================================
// AUDIO - WEB AUDIO API
// ==============================================

/**
 * Play pleasant bell sound
 */
function playBellSound() {
    try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const now = audioContext.currentTime;
        const duration = 0.6;
        
        const osc1 = audioContext.createOscillator();
        osc1.frequency.setValueAtTime(800, now);
        osc1.type = 'sine';
        
        const osc2 = audioContext.createOscillator();
        osc2.frequency.setValueAtTime(1200, now);
        osc2.type = 'sine';
        
        const gain1 = audioContext.createGain();
        gain1.gain.setValueAtTime(0.15, now);
        gain1.gain.exponentialRampToValueAtTime(0.01, now + duration);
        
        const gain2 = audioContext.createGain();
        gain2.gain.setValueAtTime(0.08, now);
        gain2.gain.exponentialRampToValueAtTime(0.01, now + duration);
        
        osc1.connect(gain1);
        osc2.connect(gain2);
        gain1.connect(audioContext.destination);
        gain2.connect(audioContext.destination);
        
        osc1.start(now);
        osc2.start(now);
        osc1.stop(now + duration);
        osc2.stop(now + duration);
    } catch (e) {
        console.warn('Could not play bell sound:', e);
    }
}

/**
 * Play attack sound effect
 */
function playAttackSound() {
    try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const now = audioContext.currentTime;
        const duration = 0.28;

        const osc1 = audioContext.createOscillator();
        osc1.type = 'square';
        osc1.frequency.setValueAtTime(220, now);

        const gain1 = audioContext.createGain();
        gain1.gain.setValueAtTime(0.0001, now);
        gain1.gain.exponentialRampToValueAtTime(0.22, now + 0.02);
        gain1.gain.exponentialRampToValueAtTime(0.002, now + duration);

        const osc2 = audioContext.createOscillator();
        osc2.type = 'triangle';
        osc2.frequency.setValueAtTime(1200, now);

        const gain2 = audioContext.createGain();
        gain2.gain.setValueAtTime(0.0001, now);
        gain2.gain.exponentialRampToValueAtTime(0.12, now + 0.015);
        gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.18);

        osc1.connect(gain1); 
        gain1.connect(audioContext.destination);
        osc2.connect(gain2); 
        gain2.connect(audioContext.destination);

        osc1.start(now); 
        osc2.start(now);
        osc1.stop(now + duration); 
        osc2.stop(now + 0.2);
    } catch (e) {
        console.warn('Could not play attack sound:', e);
    }
}

/**
 * Play game over sound
 * @param {Boolean} isWin - True if player won
 */
function playGameOverSound(isWin) {
    try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const now = audioContext.currentTime;
        
        if (isWin) {
            const notes = [523, 659, 784]; // C5, E5, G5
            notes.forEach((freq, idx) => {
                const osc = audioContext.createOscillator();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(freq, now);
                
                const gain = audioContext.createGain();
                const startTime = now + idx * 0.25;
                gain.gain.setValueAtTime(0.2, startTime);
                gain.gain.exponentialRampToValueAtTime(0.01, startTime + 0.4);
                
                osc.connect(gain);
                gain.connect(audioContext.destination);
                osc.start(startTime);
                osc.stop(startTime + 0.4);
            });
        } else {
            const notes = [349, 293, 246]; // F4, D4, B3
            notes.forEach((freq, idx) => {
                const osc = audioContext.createOscillator();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(freq, now);
                
                const gain = audioContext.createGain();
                const startTime = now + idx * 0.25;
                gain.gain.setValueAtTime(0.2, startTime);
                gain.gain.exponentialRampToValueAtTime(0.01, startTime + 0.5);
                
                osc.connect(gain);
                gain.connect(audioContext.destination);
                osc.start(startTime);
                osc.stop(startTime + 0.5);
            });
        }
    } catch (e) {
        console.warn('Could not play game over sound:', e);
    }
}

// ==============================================
// UI UTILITIES
// ==============================================

/**
 * Render comment/log messages
 * @param {Array} lines - Array of log messages
 */
function renderComments(lines) {
    const container = document.querySelector('.game-comments');
    if (!container) return;
    if (!lines || !Array.isArray(lines) || lines.length === 0) return;
    
    const raw = lines[lines.length - 1];
    if (!raw) return;
    
    const sanitized = String(raw).replace(/draws\s+[^\s]+/i, 'draws a card');
    container.textContent = sanitized;
    container.classList.add('flash');
    playBellSound();
    setTimeout(() => container.classList.remove('flash'), 900);
}

/**
 * Flash attack zone when card is played
 */
function flashAttackZone() {
    const zone = document.getElementById("attack-zone");
    if (zone) {
        zone.classList.add('flash');
        setTimeout(() => zone.classList.remove('flash'), 600);
    }
}

// ==============================================
// PLACEHOLDER HANDLERS (To be overridden)
// ==============================================

/**
 * Card click handler - override in mode-specific files
 * @param {Number} index - Card index
 * @param {Object} card - Card object {rank, suit}
 */
function onCardClick(index, card) {
    console.warn('onCardClick not implemented - override in mode-specific file');
}

/**
 * Push attack button click - override in mode-specific files
 */
function onPushAttackClick() {
    console.warn('onPushAttackClick not implemented - override in mode-specific file');
}

/**
 * Push defend button click - override in mode-specific files
 */
function onPushDefendClick() {
    console.warn('onPushDefendClick not implemented - override in mode-specific file');
}
