

let gameId = null;
let focusedCardIndex = null;
let selectedCardIndex = null;
let currentState = null;
let gameMode = null
let myPlayer = null;
let contZone = null;

// Request locking to prevent duplicate/concurrent actions
let isRequestInProgress = false;

// Raised card for attack (new click-to-raise mechanism)
let raisedCardIndex = null;

// Defense selection state (when human defends)
let defenseSelected = []; // holds up to two indices
let pendingOpponentAttack = null;
let lastDisplayedAttack = null;
// track each player's max observed hand size to compute progress
let playerMaxSeen = {};

/* -----------------------------
   GAME CREATION
----------------------------- */

async function createGame(mode = "human_vs_ai") {
    const res = await fetch("/api/game/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode })
    });

    const data = await res.json();
    gameId = data.game_id;
    gameMode = data.mode;
    myPlayer = data.my_player;

    console.log("[FRONTEND] Game created:", gameId);
    console.log("My Player Name: ",myPlayer.name, " Hand: ",myPlayer.hand)
    await fetchState();
    await fetchPlayerDetails();
}

/* -----------------------------
    PLAYER DETAILS FETCH
----------------------------- */
async function fetchPlayerDetails() {
    if (!gameId) return null;
    // fetchState();
    try {
        const res = await fetch(`/api/game/${gameId}/player_details`);
        const data = await res.json();
        console.log("[FRONTEND] Player details:", data);

        if (!data || !Array.isArray(data.players) || data.players.length === 0) return null;

        // Try to match by name if we already have myPlayer from createGame
        let found = null;
        if (myPlayer && myPlayer.name) {
            found = data.players.find(p => p.name === myPlayer.name);
        }

        // Fallback: use first player
        if (!found) found = data.players[0];

        myPlayer = found;
        return myPlayer;
    } catch (e) {
        console.error('Failed to fetch player details', e);
        return null;
    }
}

// await fetchPlayerDetails();

/* -----------------------------
   STATE FETCH
----------------------------- */

async function fetchState() {
    if (!gameId) return;
    console.log("Checking Game State");
    const res = await fetch(`/api/game/${gameId}/state`);
    const state = await res.json();

    currentState = state;
    await renderState(state);
    // render any engine UI log messages (state.ui_log may be present)
    if (state.ui_log && Array.isArray(state.ui_log)) renderComments(state.ui_log);
    // refresh leaderboard after we update state
    fetchLeaderboard();
    await updateAgent(state);
}

async function fetchLeaderboard() {
    if (!gameId) return;
    try {
        const res = await fetch(`/api/game/${gameId}/leaderboard`);
        const data = await res.json();
        renderLeaderboard(data);
    } catch (e) {
        console.error('Failed to fetch leaderboard', e);
    }
}

function renderLeaderboard(data) {
    const container = document.getElementById('leaderboard-list');
    if (!container) return;
    container.innerHTML = '';
    const myPlayerScoreB = document.getElementById('card-count-me');
    const myOpponentScoreB = document.getElementById('card-count-opponent');


    data.players.forEach((p,i) => {
        const row = document.createElement('div');
        row.className = 'row';

        if (data.attacker === p.id) row.classList.add('attacker');
        if (data.defender === p.id) row.classList.add('defender');

        const left = document.createElement('div');
        left.className = 'player-left';
        left.innerHTML = `<div class="icon">` + (data.attacker === p.id ? '<i class="fa-solid fa-crosshairs"></i>' : (data.defender === p.id ? '<i class="fa-solid fa-shield-halved"></i>' : '<i class="fa-solid fa-user"></i>')) + `</div><div>${p.name}</div>`;

        const right = document.createElement('div');
        right.innerHTML = `<div class="role-badge">${p.hand_count} cards</div>`;

        if(i === 0){
            myPlayerScoreB.textContent = p.hand_count;
        }else if(i === 1){
            myOpponentScoreB.textContent = p.hand_count;
        };

        row.appendChild(left);
        row.appendChild(right);
        container.appendChild(row);
    });
    // update visual progress bars based on player counts
    updateProgressBars(data);
}

function updateProgressBars(data) {
    if (!data || !Array.isArray(data.players)) return;
    const container = document.getElementById('leader-progess-bars-cont');
    if (!container) return;

    // map players by index for stable ordering
    const players = data.players;
    // update max-seen counts
    players.forEach(p => {
        const key = String(p.id);
        const val = p.hand_count || 0;
        if (!playerMaxSeen[key] || playerMaxSeen[key] < val) playerMaxSeen[key] = val;
    });

    // pick two display containers inside leader-progess-bars-cont
    const userCont = container.querySelector('.user-progress-bar-cont');
    const oppCont = container.querySelector('.opponent-progress-bar-cont');

    // Use first two players if present
    const leftPlayer = players[0] || null;
    const rightPlayer = players[1] || players[0] || null;

    function updateCont(cont, player) {
        if (!cont || !player) return;
        const key = String(player.id);
        const maxSeen = playerMaxSeen[key] || Math.max(1, player.hand_count || 1);
        const current = player.hand_count || 0;
        const percent = Math.round(((maxSeen - current) / Math.max(1, maxSeen)) * 100);

        const fill = cont.querySelector('.user-progress-fill') || cont.querySelector('.user-progress-fill');
        const text = cont.querySelector('.user-progress-text');
        if (fill) {
            fill.style.width = percent + '%';
        }
        if (text) text.textContent = percent + '%';
        // winner = player with fewer cards
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

async function updateAgent(state) {
    const text = document.getElementById('agent-text');
    if (!text) return;

    if (!state) {
        text.innerText = "Waiting for game state...";
        return;
    }

    const phase = state.phase;
    const attacker = state.attacker;
    const defender = state.defender;
    const attackCard = state.attack_card;
    
    console.log("[FRONTEND] updateAgent called with phase:", phase);

    if (phase === 'ATTACK') {
        if (attacker === 0) {
            text.innerText = `It's your turn to attack. Choose a card to attack with (4-13).`;
        } else {
            text.innerText = `Opponent is deciding their attack...`;
        }
    } else if (phase === 'DEFENSE') {
        if (defender === 0) {
            text.innerText = `Defend against ${attackCard}. Choose two cards whose values sum to it, or draw.`;
        } else {
            text.innerText = `Waiting for opponent to defend against ${attackCard}...`;
        }
    } else if (phase === 'RULE_8') {
        text.innerText = `Rule 8: drop a trail value (1-3) if prompted.`;
    } else if (phase === 'GAME_OVER') {
        text.innerText = `Game over. Check results in the leaderboard.`;
        console.log("[FRONTEND] Game over detected, showing modal");
        showGameModal();
    } else {
        text.innerText = `Phase: ${phase}`;
    }
}

/* -----------------------------
   GAME ACTIONS
----------------------------- */

async function startTurn() {
    // clear the visual attack pile when a new turn is started
    const pile = document.getElementById("attack-pile");
    if (pile) pile.innerHTML = '';

    await fetch(`/api/game/${gameId}/start`, { method: "POST" });
    fetchState();
}


async function attack(index) {
    if (!currentState) return;
    if (currentState.phase !== "ATTACK") return;
    if (currentState.attacker !== 0) return;
    
    // Prevent duplicate/concurrent requests
    if (isRequestInProgress) {
        console.log("[FRONTEND] Request already in progress, ignoring attack");
        return;
    }
    
    isRequestInProgress = true;

    const cards = getHandCards();
    const cardEl = cards[index];

    if (cardEl) {
        animateCardToAttackPile(cardEl);
        // play attack sound on user attack
        try { playAttackSound(); } catch (e) {}
    }

    try {
        const res = await fetch(`/api/game/${gameId}/attack`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ index })
        });

        focusedCardIndex = null;
        const data = await res.json();
        const ui = data.ui_state;
        console.log("Attack response ui:", ui);
        
        // Check if attack was successful
        if (data.results && data.results.error) {
            console.error("[FRONTEND] Attack failed:", data.results.error);
            setOpponentStatus(`Error: ${data.results.error}`);
        } else {
            if (ui && ui.defence_cards) animateOpponentDefense(ui.defence_cards);
            else if (ui && ui.defender_drawn_card) {
                setOpponentStatus("Opponent drew a card");
                // show ghost animation for opponent drawing
                try { await animateOpponentDrawGhost(); } catch (e) { /* ignore */ }
            }
        }
        
        if (ui && ui.ui_log) renderComments(ui.ui_log);

        // Delay state refresh until animation finishes
        setTimeout(() => {
            fetchState();
            isRequestInProgress = false;
        }, 450);
    } catch (error) {
        console.error("[FRONTEND] Attack request failed:", error);
        isRequestInProgress = false;
    }
}

//Human input
async function defend(indices) {
    const cards = getHandCards();
    const cardEls = indices.map(i => cards[i]).filter(Boolean);
    console.log("Animating defense cards:", cardEls);
    console.log("Defend indices:", indices);
    const i1 = indices[0];
    const i2 = indices[1];
    const res = await fetch(`/api/game/${gameId}/defend`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ i1, i2 })
    });

    const data = await res.json();
    console.log("Defend response data:", data);
    // If backend returned used_cards (defense success), animate them
    if (data.used_cards) {
        animateOpponentDefense(data.used_cards);
    }

    // Render any ui log included in the response
    if (data.ui_log) renderComments(data.ui_log);

    // Refresh authoritative state after a short delay to allow animations
    setTimeout(fetchState, 500);
}


async function drawCard() {
    // remove any visual pile immediately when player chooses to draw
    const pile = document.getElementById('attack-pile');
    if (pile) pile.innerHTML = '';
    hideAttackConfirmModal();

    const res = await fetch(`/api/game/${gameId}/draw`, { method: "POST" });
    const data = await res.json();
    if (data && data.ui_log) renderComments(data.ui_log);
    // show a small draw animation (ghost flying from draw button to our hand)
    try { await animateDrawGhost(); } catch (e) { /* ignore */ }
    // Give backend AI a short moment to act, then refresh state so opponent attack appears
    setTimeout(() => {
        fetchState();
    }, 900);
}

// Animate a ghost card flying from the draw button into the player's hand area
function animateDrawGhost() {
    return new Promise((resolve) => {
        const btn = document.getElementById('draw-button');
        const hand = document.getElementById('player-cards');
        if (!btn || !hand) return resolve();

        const startRect = btn.getBoundingClientRect();
        const targetRect = hand.getBoundingClientRect();

        // create a neutral ghost card (back side or placeholder)
        const ghost = document.createElement('div');
        ghost.className = 'card ghost entering';
        ghost.innerHTML = `\n            <div class="rank">?</div>\n            <div class="center">♦</div>\n            <div class="suit">?</div>\n        `;
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

// Animate a ghost card flying from bottom-right (opponent deck) to center-top (attack pile)
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

        // Target: top center of screen (where opponent would be)
        const targetX = (window.innerWidth / 2) - 60;
        const targetY = -200; // offscreen top

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

async function rule8Drop(value) {
    await fetch(`/api/game/${gameId}/rule8/drop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value })
    });
    fetchState();
}

async function rule8Crash(crash) {
    await fetch(`/api/game/${gameId}/rule8/crash`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ crash })
    });
    fetchState();
}


function animateOpponentDefense(values) {
    // Create non-animated duplicates and push into the pile box.
    const pile = document.getElementById("attack-pile");
    if (!pile) return;
    const pileRect = pile.getBoundingClientRect();

    // normalize values so we have objects with {rank, suit}
    const cards = values.map(v => {
        if (typeof v === 'string') {
            const s = v.replace(/\s*icon$/i, '').trim();
            const m = s.match(/^([0-9]{1,2}|[AJQK])([a-zA-Z]+)$/i);
            if (m) return { rank: m[1], suit: m[2] };
            const alt = s.match(/^(.+?)([a-zA-Z]+)$/);
            if (alt) return { rank: alt[1], suit: alt[2] };
            return { rank: s, suit: '' };
        } else if (v && typeof v === 'object') {
            return { rank: v.rank, suit: v.suit };
        } else {
            return { rank: String(v), suit: '' };
        }
    });

    // compute size so up to 3 cards fit inside pile horizontally
    const maxCardsAcross = 3;
    const cardMargin = 6; // px
    const cardWidth = Math.max(40, Math.floor((pileRect.width - (cardMargin * (maxCardsAcross + 1))) / maxCardsAcross));
    const cardHeight = Math.max(56, Math.floor(pileRect.height - 8));

    // append each card as a simple static element inside pile
    cards.forEach((card, i) => {
        const el = document.createElement('div');
        el.className = 'card pile-defense entering';
        el.innerHTML = `
            <div class="rank">${card.rank}</div>
            <div class="center">${card.suit}</div>
            <div class="suit">${card.suit}</div>
        `;
        // sizing to fit pile
        el.style.width = cardWidth + 20 + 'px';
        el.style.height = cardHeight + 'px';
        el.style.display = 'inline-block';
        el.style.margin = cardMargin + 'px';
        el.style.verticalAlign = 'top';

        pile.appendChild(el);
        requestAnimationFrame(() => el.classList.remove('entering'));
    });

    setOpponentStatus("Opponent defended, with cards: " + cards.map(v => v.rank + v.suit).join(", "));
}

function setOpponentStatus(text) {
    document.getElementById("agent-text").textContent = text;
}
/* -----------------------------
   RENDERING (TEMP / DEBUG)
----------------------------- */

async function renderState(state) {
    // document.getElementById("state").innerText =
    //     JSON.stringify(state, null, 2);
    let myHand = null;

    // Prefer authoritative player details from server
    const playerDetails = await fetchPlayerDetails();
    if (playerDetails && Array.isArray(playerDetails.hand)) {
        myHand = playerDetails.hand;
    } else {
        // Try to find our index in state.players by name
        if (myPlayer && myPlayer.name && Array.isArray(state.players)) {
            const idx = state.players.findIndex(p => p.name === myPlayer.name);
            if (idx >= 0 && state.hands && state.hands[idx]) {
                myHand = state.hands[idx];
            }
        }
        // Fallback to attacker index or first hand
        if (!myHand) myHand = (state.hands && state.hands[state.attacker]) || (state.hands && state.hands[0]) || [];
    }

    renderCards(myHand);
    updateAttackZone();
    // update tracking badge based on phase and whether it's our turn
    if (state) {
        const phase = state.phase || '';
        // determine if local player is attacker or defender (assume player index 0 for now)
        const localPlayerIndex = 0;
        const isLocalAttacker = state.attacker === localPlayerIndex;
        const isLocalDefender = state.defender === localPlayerIndex;

        if (phase === 'ATTACK' && isLocalAttacker) {
            setTrackingBadge('Attack', 'attack');
            updateHandHighlight('attack');
        } else if (phase === 'DEFENSE' && isLocalDefender) {
            setTrackingBadge('Defend or Draw', 'defend');
            // If the user can defend or draw, show draw steady glow to suggest drawing is available
            updateHandHighlight('draw');
        } else if (phase === 'RULE_8') {
            setTrackingBadge('Rule 8', 'info');
             updateHandHighlight('none');
        } else if (phase === 'GAME_OVER') {
            setTrackingBadge('Game Over', 'info');
            updateHandHighlight('none');
            // Fetch fresh state before showing modal to ensure win type is correct
            console.log("[FRONTEND] Game over detected, fetching final state before modal");
            // await fetchState();
            showGameModal();
            console.log("Game Over");
        } else {
            // opponent's turn or waiting: hide badge or show neutral
            setTrackingBadge('Waiting...', 'info');
            updateHandHighlight('none');
        }
        // If opponent has played an attack card and we're the defender, require user confirmation
        if (state.attack_card && state.attacker !== 0 && state.defender === 0) {
            if (state.attack_card !== lastDisplayedAttack) {
                pendingOpponentAttack = state.attack_card;
                showAttackConfirmModal();
            }
        }
        // Update draw button visibility/state
        updateDrawButton(state);
    }
}

function showGameModal(){
    console.log("[FRONTEND] showGameModal() called");
    if (!currentState) {
        console.log("[FRONTEND] No currentState, aborting modal");
        return;
    }
    
    var gameOverCont = document.querySelector('.game-over-modal-cont');
    var gameOverModal = document.querySelector(".game-over-modal");
    
    if (!gameOverCont || !gameOverModal) {
        console.error("[FRONTEND] Modal elements not found!");
        return;
    }
    
    console.log("[FRONTEND] Modal elements found, populating data...");
    console.log("[FRONTEND] Current state:", currentState);
    console.log("[FRONTEND] UI log:", currentState?.ui_log);
    console.log("[FRONTEND] Game over flag:", currentState?.game_over);
    console.log("[FRONTEND] Winner:", currentState?.winner);
    
    // Populate winner information
    const winnerId = currentState.winner;
    const isPlayerWinner = winnerId === 0;
    const winnerBadge = document.getElementById('winner-badge');
    const winType = document.getElementById('win-type');
    
    if (winnerBadge) {
        winnerBadge.textContent = isPlayerWinner ? 'You Win!' : 'Opponent Wins!';
        winnerBadge.className = isPlayerWinner ? 'winner-badge player-win' : 'winner-badge opponent-win';
    }
    
    // Extract win type from UI log (last message usually contains win type)
    if (winType) {
        if (currentState.ui_log && Array.isArray(currentState.ui_log) && currentState.ui_log.length > 0) {
        const lastLog = currentState.ui_log[currentState.ui_log.length - 1];
        console.log("[FRONTEND] Last UI log message:", lastLog);
        console.log("[FRONTEND] Full UI log:", currentState.ui_log);
        
        // Check in specific order - most specific first
        if (lastLog.includes('CRAZY ESCAPE WIN')) {
            console.log("[FRONTEND] Detected CRAZY ESCAPE WIN");
            winType.textContent = '🤣CRAZY ESCAPE WIN';
            winType.className = 'win-type crazy-win';
        } else if (lastLog.includes('TRAIL WIN')) {
            console.log("[FRONTEND] Detected TRAIL WIN");
            winType.textContent = '👌TRAIL WIN';
            winType.className = 'win-type trail-win';
        } else if (lastLog.includes('ESCAPE WIN')) {
            console.log("[FRONTEND] Detected ESCAPE WIN");
            winType.textContent = '😉ESCAPE WIN';
            winType.className = 'win-type escape-win';
        } else if (lastLog.includes('DEALUXE WIN')) {
            console.log("[FRONTEND] Detected DEALUXE WIN");
            winType.textContent = '😍DEALUXE WIN';
            winType.className = 'win-type dealuxe-win';
        } else {
            console.log("[FRONTEND] No win type detected, using default");
            winType.textContent = 'Victory';
            winType.className = 'win-type';
        }
        } else {
            console.log("[FRONTEND] No UI log available to determine win type");
            winType.textContent = 'Victory';
            winType.className = 'win-type';
        }
    }
    
    // Show final card counts
    const playerCards = document.getElementById('player-final-cards');
    const opponentCards = document.getElementById('opponent-final-cards');
    if (playerCards && currentState.hands && currentState.hands[0]) {
        playerCards.textContent = currentState.hands[0].length;
    }
    if (opponentCards && currentState.hands && currentState.hands[1]) {
        opponentCards.textContent = currentState.hands[1].length;
    }
    
    console.log("[FRONTEND] Showing modal by adding 'show-game-over' class...");
    gameOverCont.classList.add("show-game-over");
    gameOverModal.classList.add("show-game-over");
    console.log("[FRONTEND] Modal should now be visible");
}

// Toggle hand glow based on current user action
function updateHandHighlight(mode){
    const hand = document.getElementById('player-cards');
    if (!hand) return;
    hand.classList.remove('hand-attack','hand-draw');
    if (mode === 'attack') hand.classList.add('hand-attack');
    else if (mode === 'draw') hand.classList.add('hand-draw');
}

function parseCardString(s) {
    if (!s) return { rank: s, suit: '' };
    const str = String(s).replace(/\s*icon$/i, '').trim();
    const m = str.match(/^([0-9]{1,2}|[AJQK])([a-zA-Z]+)$/i);
    if (m) return { rank: m[1], suit: m[2] };
    const alt = str.match(/^(.+?)([a-zA-Z]+)$/);
    if (alt) return { rank: alt[1], suit: alt[2] };
    return { rank: str, suit: '' };
}

function appendOpponentAttack(value) {
    const pile = document.getElementById('attack-pile');
    if (!pile) return;
    const pileRect = pile.getBoundingClientRect();
    const card = parseCardString(value);
    const maxCardsAcross = 3;
    const cardMargin = 6;
    const cardWidth = Math.max(40, Math.floor((pileRect.width - (cardMargin * (maxCardsAcross + 1))) / maxCardsAcross));
    const cardHeight = Math.max(56, Math.floor(pileRect.height - 8));

    // remove previous visuals
    const prevAttack = pile.querySelectorAll('.pile-attack');
    prevAttack.forEach(el => el.remove());
    const prevDefense = pile.querySelectorAll('.pile-defense');
    prevDefense.forEach(el => el.remove());

    const el = document.createElement('div');
    el.className = 'card pile-attack entering';
    el.innerHTML = `\n            <div class="rank">${card.rank}</div>\n            <div class="center">${card.suit}</div>\n            <div class="suit">${card.suit}</div>\n        `;
    el.style.width = cardWidth + 'px';
    el.style.height = cardHeight + 'px';
    el.style.display = 'inline-block';
    el.style.margin = cardMargin + 'px';
    el.style.verticalAlign = 'top';
    pile.appendChild(el);
    requestAnimationFrame(() => el.classList.remove('entering'));
    // play attack sound when the attack card lands in pile
    try { playAttackSound(); } catch (e) {}
    lastDisplayedAttack = value;
}

// Animate a transient ghost card flying from top (opponent) into the attack pile.
function animateOpponentGhost(value) {
    return new Promise((resolve) => {
        const pile = document.getElementById('attack-pile');
        if (!pile) return resolve();
        const pileRect = pile.getBoundingClientRect();

        const startX = window.innerWidth / 2; // from top center (opponent)
        const startY = Math.max(24, pileRect.top - 160);

        const card = parseCardString(value);
        const ghost = document.createElement('div');
        ghost.className = 'card ghost entering';
        ghost.innerHTML = `\n            <div class="rank">${card.rank}</div>\n            <div class="center">${card.suit}</div>\n            <div class="suit">${card.suit}</div>\n        `;
        document.body.appendChild(ghost);

        // place at start
        ghost.style.left = startX - 60 + 'px';
        ghost.style.top = startY + 'px';

        requestAnimationFrame(() => {
            ghost.classList.add('visible');
            ghost.classList.remove('entering');
        });

        // compute target center inside pile
        const targetX = pileRect.left + (pileRect.width / 2) - 60;
        const targetY = pileRect.top + (pileRect.height / 2) - 85;

        // animate via transform
        requestAnimationFrame(() => {
            const dx = targetX - (startX - 60);
            const dy = targetY - startY;
            ghost.style.transform = `translate(${dx}px, ${dy}px) scale(0.92)`;
        });

        // after transition, do a quick fade and remove
        const cleanup = () => {
            ghost.removeEventListener('transitionend', cleanup);
            ghost.classList.add('fade-out');
            setTimeout(() => { try { ghost.remove(); } catch (e) {} resolve(); }, 240);
        };
        ghost.addEventListener('transitionend', cleanup);
        // safety resolve in case transitionend doesn't fire
        setTimeout(() => { if (document.body.contains(ghost)) { cleanup(); } }, 900);
    });
}

function showAttackConfirmModal() {
    // don't recreate if already present
    if (document.getElementById('attack-confirm-modal')) return;
    const pile = document.getElementById('attack-pile');
    const handDiv = document.getElementById('player-cards');
    const modal = document.createElement('div');
    modal.id = 'attack-confirm-modal';
    modal.className = 'attack-confirm-modal';
    modal.innerHTML = `
        
        <div class="attack-confirm-actions gen-flex-col">
            <div class="caption">Allow opponent to play a card</div>
            <button id="attack-confirm-proceed" class="btn"><i class="fa-solid fa-check"></i> Proceed Game</button>
        </div>
    `;
    // position modal over pile
    if (handDiv && handDiv.parentElement) handDiv.appendChild(modal);

    document.getElementById('attack-confirm-proceed').addEventListener('click', async () => {
        hideAttackConfirmModal();
        if (pendingOpponentAttack) {
            // play a ghost animation then append the static pile visual
            await animateOpponentGhost(pendingOpponentAttack);
            // play attack sound on opponent reveal
            try { playAttackSound(); } catch (e) {}
            appendOpponentAttack(pendingOpponentAttack);
            pendingOpponentAttack = null;
        }
    });
    // document.getElementById('attack-confirm-cancel').addEventListener('click', () => {
    //     hideAttackConfirmModal();
    //     // Keep pending until user confirms; optionally clear
    //     pendingOpponentAttack = null;
    // });
}

function hideAttackConfirmModal() {
    const m = document.getElementById('attack-confirm-modal');
    if (m) m.remove();
}

// Play a pleasant bell sound using Web Audio API
function playBellSound() {
    try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        
        // Create oscillators for a bell-like tone (fundamental + harmonics)
        const now = audioContext.currentTime;
        const duration = 0.6;
        
        // Fundamental frequency (like a gentle chime)
        const osc1 = audioContext.createOscillator();
        osc1.frequency.setValueAtTime(800, now);
        osc1.type = 'sine';
        
        // Second harmonic
        const osc2 = audioContext.createOscillator();
        osc2.frequency.setValueAtTime(1200, now);
        osc2.type = 'sine';
        
        // Create gain nodes for volume control and fade out
        const gain1 = audioContext.createGain();
        gain1.gain.setValueAtTime(0.15, now);
        gain1.gain.exponentialRampToValueAtTime(0.01, now + duration);
        
        const gain2 = audioContext.createGain();
        gain2.gain.setValueAtTime(0.08, now);
        gain2.gain.exponentialRampToValueAtTime(0.01, now + duration);
        
        // Connect the audio graph
        osc1.connect(gain1);
        osc2.connect(gain2);
        gain1.connect(audioContext.destination);
        gain2.connect(audioContext.destination);
        
        // Start and stop
        osc1.start(now);
        osc2.start(now);
        osc1.stop(now + duration);
        osc2.stop(now + duration);
    } catch (e) {
        console.warn('Could not play bell sound:', e);
    }
}

// Short percussive "attack" sound using Web Audio API
function playAttackSound() {
    try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const now = audioContext.currentTime;
        const duration = 0.28;

        // Low square wave for punch
        const osc1 = audioContext.createOscillator();
        osc1.type = 'square';
        osc1.frequency.setValueAtTime(220, now);

        const gain1 = audioContext.createGain();
        gain1.gain.setValueAtTime(0.0001, now);
        gain1.gain.exponentialRampToValueAtTime(0.22, now + 0.02);
        gain1.gain.exponentialRampToValueAtTime(0.002, now + duration);

        // Click transient (higher freq triangle)
        const osc2 = audioContext.createOscillator();
        osc2.type = 'triangle';
        osc2.frequency.setValueAtTime(1200, now);

        const gain2 = audioContext.createGain();
        gain2.gain.setValueAtTime(0.0001, now);
        gain2.gain.exponentialRampToValueAtTime(0.12, now + 0.015);
        gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.18);

        osc1.connect(gain1); gain1.connect(audioContext.destination);
        osc2.connect(gain2); gain2.connect(audioContext.destination);

        osc1.start(now); osc2.start(now);
        osc1.stop(now + duration); osc2.stop(now + 0.2);
    } catch (e) {
        console.warn('Could not play attack sound:', e);
    }
}

function renderComments(lines) {
    const container = document.querySelector('.game-comments');
    if (!container) return;
    // Show only the most recent relevant message (not a log dump).
    if (!lines || !Array.isArray(lines) || lines.length === 0) return;
    // pick last message
    const raw = lines[lines.length - 1];
    if (!raw) return;
    // sanitize: hide drawn card identities
    const sanitized = String(raw).replace(/draws\s+[^\s]+/i, 'draws a card');
    // display single message
    container.textContent = sanitized;
    // briefly highlight the comments box to draw attention
    container.classList.add('flash');
    // Play bell sound when animating
    playBellSound();
    setTimeout(() => container.classList.remove('flash'), 900);
}

function setTrackingBadge(text, type="info") {
    const badge = document.querySelector('.tracking-badge');
    if (!badge) return;
    badge.textContent = text;
    badge.classList.remove('attack','defend','draw','info');
    badge.classList.add(type);
}

/* -----------------------------
   INIT
----------------------------- */

window.onload = () => {
    createDrawButton();
    createGame(); // auto-start one game
};

// --- Draw button UI ---
function createDrawButton() {
    if (document.getElementById('draw-button')) return;
    const wrapper = document.createElement('div');
    wrapper.className = 'draw-button-wrapper';

    const label = document.createElement('div');
    label.className = 'draw-label';
    label.textContent = 'Draw Card';
    wrapper.appendChild(label);

    const btn = document.createElement('button');
    btn.id = 'draw-button';
    btn.className = 'draw-button flash';
    btn.setAttribute('aria-label', 'Draw a card');
    btn.innerHTML = '<span class="icon"><i class="fa-solid fa-plus"></i></span>';
    wrapper.appendChild(btn);
    document.body.appendChild(wrapper);

    btn.addEventListener('click', async () => {
        // disable to prevent double clicks
        btn.classList.add('disabled');
        try {
            await drawCard();
        } catch (e) {
            console.error('Draw failed', e);
        } finally {
            // re-enable after short delay
            setTimeout(() => btn.classList.remove('disabled'), 600);
        }
    });
}

function updateDrawButton(state) {
    const btn = document.getElementById('draw-button');
    if (!btn) return;
    // Show only when it's DEFENSE phase and local player is defender (defender === 0)
    const visible = state && state.phase === 'DEFENSE' && state.defender === 0;
    btn.style.display = visible ? 'flex' : 'none';
    if (visible) {
        // flash when available
        btn.classList.add('flash');
    } else {
        btn.classList.remove('flash');
    }
}

/* CARDS RENDERING AND AUTOMATION */
function renderCards(cards) {
    console.log("[UI] Rendering cards:", cards);
    cards = cards.map(cardStr => {
        const rank = cardStr.slice(0, -1);
        const suit = cardStr.slice(-1);
        return { rank, suit };
    });
    const container = document.getElementById("player-cards");
    container.innerHTML = "";

    const overlap = 80; // px (about 80% overlap)

    cards.forEach((card, index) => {
        const div = document.createElement("div");
        div.className = "card";
        div.style.left = `${index * overlap}px`;
        div.style.zIndex = index;

        div.innerHTML = `
            <div class="rank">${card.rank}</div>
            <div class="center">${card.suit}</div>
            <div class="suit">${card.suit}</div>
        `;

        div.addEventListener("click", () => onCardClick(index));

        container.appendChild(div);
    });
}

// Return only the cards currently rendered in the player's hand container
function getHandCards() {
    const container = document.getElementById('player-cards');
    if (!container) return [];
    return Array.from(container.querySelectorAll('.card'));
}

// Interaction logic for card clicks 

function onCardClick(index) {
    const cards = getHandCards();

    // Defense selection flow: when it's DEFENSE phase and human is defender
    if (currentState && currentState.phase === 'DEFENSE' && currentState.defender === 0) {
        // if clicked card is already selected, toggle it off
        const selIndex = defenseSelected.indexOf(index);
        if (selIndex >= 0) {
            // remove selection
            cards[index].classList.remove('defense-first', 'defense-second');
            defenseSelected.splice(selIndex, 1);
            hideDefendButtonIfNeeded();
            return;
        }

        // add selection (max 2)
        if (defenseSelected.length === 0) {
            defenseSelected.push(index);
            cards[index].classList.add('defense-first');
            return;
        }

        if (defenseSelected.length === 1) {
            // prevent selecting the same card twice
            if (defenseSelected[0] === index) return;
            defenseSelected.push(index);
            cards[index].classList.add('defense-second');
            // show confirm button
            showDefendButton();
            return;
        }

        // If already had two selected, reset and start new selection
        clearDefenseSelections();
        defenseSelected.push(index);
        cards[index].classList.add('defense-first');
        return;
    }

    // Attack phase: raise/lower card mechanism
    if (currentState && currentState.phase === 'ATTACK' && currentState.attacker === 0) {
        // If this card is already raised, lower it
        if (raisedCardIndex === index) {
            lowerRaisedCard();
            return;
        }

        // Lower any other raised card first
        if (raisedCardIndex !== null) {
            lowerRaisedCard();
        }

        // Raise this card
        raiseCard(index);
        return;
    }
}

// New raise/lower card mechanism for attacks
function raiseCard(index) {
    const cards = getHandCards();
    if (!cards[index]) return;
    
    raisedCardIndex = index;
    cards[index].classList.add('raised');
    showPushButton();
    
    // Add click listener to document to lower card when clicking elsewhere
    setTimeout(() => {
        document.addEventListener('click', onDocumentClickWhileRaised, true);
    }, 0);
}

function lowerRaisedCard() {
    if (raisedCardIndex === null) return;
    
    const cards = getHandCards();
    if (cards[raisedCardIndex]) {
        cards[raisedCardIndex].classList.remove('raised');
    }
    
    raisedCardIndex = null;
    hidePushButton();
    
    // Remove document click listener
    document.removeEventListener('click', onDocumentClickWhileRaised, true);
}

function onDocumentClickWhileRaised(e) {
    // Don't lower if clicking the raised card itself or the push button
    const cards = getHandCards();
    const pushBtn = document.getElementById('push-attack-btn');
    
    if (raisedCardIndex !== null && cards[raisedCardIndex]) {
        if (cards[raisedCardIndex].contains(e.target)) {
            return; // Clicked the raised card itself
        }
    }
    
    if (pushBtn && pushBtn.contains(e.target)) {
        return; // Clicked the push button
    }
    
    // Clicked elsewhere - lower the card
    lowerRaisedCard();
}

function showPushButton() {
    let btn = document.getElementById('push-attack-btn');
    if (!btn) {
        btn = document.createElement('button');
        btn.id = 'push-attack-btn';
        btn.className = 'btn push-attack-btn';
        btn.innerHTML = '<i class=\"fa-solid fa-arrow-up\"></i> Push to Attack';
        
        const handBox = document.querySelector('.player-cards-box');
        if (handBox) {
            handBox.appendChild(btn);
        } else {
            document.body.appendChild(btn);
        }
        
        btn.addEventListener('click', async () => {
            if (raisedCardIndex === null) return;
            const index = raisedCardIndex;
            lowerRaisedCard(); // Lower before attacking
            await attack(index);
        });
    }
    btn.style.display = 'block';
}

function hidePushButton() {
    const btn = document.getElementById('push-attack-btn');
    if (btn) btn.style.display = 'none';
}

function updateAttackZone() {
    // Deprecated: keeping for compatibility
}

function highlightFocusedCard(index) {
    // Deprecated: keeping for compatibility
}

function showDefendButton() {
    // create or reuse a confirm button that submits the selected defense indices
    let btn = document.getElementById('defend-confirm-btn');
    if (!btn) {
        btn = document.createElement('button');
        btn.id = 'defend-confirm-btn';
        btn.className = 'btn defend-btn';
        btn.textContent = 'Push to Defend';
        // place near agent panel
        const panel = document.getElementById('agent-panel') || document.body;
        panel.appendChild(btn);
        btn.addEventListener('click', async () => {
            // send selected indices to backend
            if (defenseSelected.length !== 2) return;
            // call existing defend() helper
            await defend(defenseSelected.slice());
            // cleanup UI selections
            clearDefenseSelections();
            hideDefendButton();
        });
    }
    btn.style.display = 'inline-block';
}

function hideDefendButton() {
    const btn = document.getElementById('defend-confirm-btn');
    if (btn) btn.style.display = 'none';
}

function hideDefendButtonIfNeeded() {
    if (defenseSelected.length < 2) hideDefendButton();
}

function clearDefenseSelections() {
    const cards = getHandCards();
    defenseSelected.forEach(i => {
        if (cards[i]) cards[i].classList.remove('defense-first', 'defense-second');
    });
    defenseSelected = [];
}

function animateCardToAttackPile(cardEl) {
    const pile = document.getElementById("attack-pile");
    if (!pile) return;
    const pileRect = pile.getBoundingClientRect();

    // compute size so up to 3 cards fit inside pile horizontally
    const maxCardsAcross = 3;
    const cardMargin = 6; // px
    const cardWidth = Math.max(40, Math.floor((pileRect.width - (cardMargin * (maxCardsAcross + 1))) / maxCardsAcross));
    const cardHeight = Math.max(56, Math.floor(pileRect.height - 8));

    // remove previous attacker visual(s)
    // Remove previous attack group (attack + defense) so we always show
    // the current trio only.
    const prevAttack = pile.querySelectorAll('.pile-attack');
    prevAttack.forEach(el => el.remove());
    const prevDefense = pile.querySelectorAll('.pile-defense');
    prevDefense.forEach(el => el.remove());

    // create a new static duplicate for the pile
    const el = document.createElement('div');
    el.className = 'card pile-attack entering';
    el.innerHTML = cardEl.innerHTML;
    el.style.width = cardWidth + 'px';
    el.style.height = cardHeight + 'px';
    el.style.display = 'inline-block';
    el.style.margin = cardMargin + 'px';
    el.style.verticalAlign = 'top';

    pile.appendChild(el);

    // remove the source card from the player's hand immediately so it
    // disappears from the drop zone and the hand UI while we wait for
    // the server/AI to respond. fetchState() will re-render authoritative
    // hand later.
    try {
        const handContainer = document.getElementById('player-cards');
        if (handContainer && handContainer.contains(cardEl)) {
            cardEl.remove();
        }
    } catch (e) {
        console.warn('Failed to remove cardEl from hand:', e);
    }
    // trigger enter animation
    requestAnimationFrame(() => {
        el.classList.remove('entering');
    });
}


function animateDefenseToAttackPile(cardEls) {
    const pile = document.getElementById("attack-pile");
    if (!pile) return;
    const pileRect = pile.getBoundingClientRect();

    const maxCardsAcross = 3;
    const cardMargin = 6;
    const cardWidth = Math.max(40, Math.floor((pileRect.width - (cardMargin * (maxCardsAcross + 1))) / maxCardsAcross));
    const cardHeight = Math.max(56, Math.floor(pileRect.height - 8));

    cardEls.forEach((cardEl, i) => {
        const el = document.createElement('div');
        el.className = 'card pile-defense entering';
        el.innerHTML = cardEl.innerHTML;
        el.style.width = cardWidth + 'px';
        el.style.height = cardHeight + 'px';
        el.style.display = 'inline-block';
        el.style.margin = cardMargin + 'px';
        el.style.verticalAlign = 'top';

        pile.appendChild(el);
        // trigger enter animation
        requestAnimationFrame(() => el.classList.remove('entering'));
    });
}





