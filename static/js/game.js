

let gameId = null;
let focusedCardIndex = null;
let selectedCardIndex = null;
let currentState = null;
let gameMode = null
let myPlayer = null;

let dragCard = null;
let dragIndex = null;
let dragStartX = 0;
let dragStartY = 0;
let isDragging = false;
let dragCardStartX = 0;
let dragCardStartY = 0;

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

    const res = await fetch(`/api/game/${gameId}/state`);
    const state = await res.json();

    currentState = state;
    await renderState(state);
    // refresh leaderboard after we update state
    fetchLeaderboard();
    updateAgent(state);
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

    data.players.forEach(p => {
        const row = document.createElement('div');
        row.className = 'row';

        if (data.attacker === p.id) row.classList.add('attacker');
        if (data.defender === p.id) row.classList.add('defender');

        const left = document.createElement('div');
        left.className = 'player-left';
        left.innerHTML = `<div class="icon">` + (data.attacker === p.id ? '<i class="fa-solid fa-crosshairs"></i>' : (data.defender === p.id ? '<i class="fa-solid fa-shield-halved"></i>' : '<i class="fa-solid fa-user"></i>')) + `</div><div>${p.name}</div>`;

        const right = document.createElement('div');
        right.innerHTML = `<div class="role-badge">${p.hand_count} cards</div>`;

        row.appendChild(left);
        row.appendChild(right);
        container.appendChild(row);
    });
}

function updateAgent(state) {
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

    const cards = getHandCards();
    const cardEl = cards[index];

    if (cardEl) {
        animateCardToAttackPile(cardEl);
    }

    const res = await fetch(`/api/game/${gameId}/attack`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ index })
    });

    focusedCardIndex = null;
    const data = await res.json();
    const state = data.ui_state;
    console.log("Attack response state:", state);
    if (state && state.defence_cards) animateOpponentDefense(state.defence_cards);
    else if (state && state.defender_drawn_card) setOpponentStatus("Opponent drew a card");

    // Delay state refresh until animation finishes
    setTimeout(fetchState, 450);


}

//Human input
async function defend(indices) {
    const cards = getHandCards();
    const cardEls = indices.map(i => cards[i]).filter(Boolean);

    const res = await fetch(`/api/game/${gameId}/defend`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ indices })
    });

    const data = await res.json();

    if (data.success && cardEls.length === 2) {
        // animateDefenseToAttackPile(cardEls);
        animateOpponentDefense(data.used_cards);
        setTimeout(fetchState, 500);
    } else {
        fetchState();
    }
}


async function drawCard() {
    await fetch(`/api/game/${gameId}/draw`, { method: "POST" });
    fetchState();
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
}

/* -----------------------------
   INIT
----------------------------- */

window.onload = () => {
    createGame(); // auto-start one game
};

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

        div.addEventListener("click", () => onCardClick(index)); //when focused card is clicked again, it gets selected
        div.addEventListener("pointerdown", (e) => onPointerDown(e, index, div)); //drag and drop

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

    // No card focused yet
    if (focusedCardIndex === null) {
        cards[index].classList.add("focused");
        focusedCardIndex = index;
        updateAttackZone();
        return;
    }

    // Same card clicked again → select
    if (focusedCardIndex === index) {
        cards[index].classList.remove("focused");
        cards[index].classList.add("selected");

        selectedCardIndex = index;
        focusedCardIndex = null;
        updateAttackZone();

        console.log("[UI] Card selected:", index);

        // This is where we will trigger ATTACK later
        return;
    }

    // Different card clicked → switch focus
    cards[focusedCardIndex].classList.remove("focused");
    cards[index].classList.add("focused");
    focusedCardIndex = index;
    updateAttackZone();
}

function updateAttackZone() {
    const zone = document.getElementById("attack-zone");

    const shouldShow =
        currentState &&
        currentState.phase === "ATTACK" &&
        currentState.attacker === 0 &&
        focusedCardIndex !== null;

    zone.classList.toggle("active", shouldShow);
}

function highlightFocusedCard(index) {
    const cards = getHandCards();
    cards.forEach(c => c.classList.remove("focused"));
    if (cards[index]) cards[index].classList.add("focused");
    updateAttackZone();
}

function onPointerDown(e, index, cardEl) {
    if (!currentState) return;
    if (currentState.phase !== "ATTACK") return;
    if (currentState.attacker !== 0) return;

    e.preventDefault();

    // Auto-focus if not focused
    if (focusedCardIndex !== index) {
        focusedCardIndex = index;
        // renderCards(currentState.hands[0]);
        highlightFocusedCard(index);
    }

    dragCard = cardEl;
    dragIndex = index;
    isDragging = true;

    const rect = cardEl.getBoundingClientRect();
    dragStartX = e.clientX - rect.left;
    dragStartY = e.clientY - rect.top;
    // Keep the card's starting viewport position for correct transform math
    dragCardStartX = rect.left;
    dragCardStartY = rect.top;

    cardEl.classList.add("dragging");

    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
}

function onPointerMove(e) {
    if (!isDragging || !dragCard) return;

    // Compute translation relative to the card's original position
    const x = e.clientX - dragStartX - dragCardStartX;
    const y = e.clientY - dragStartY - dragCardStartY;

    dragCard.style.transform = `translate(${x}px, ${y}px) scale(1.05)`;

    updateAttackZoneHover(e.clientX, e.clientY);
}

function updateAttackZoneHover(x, y) {
    const zone = document.getElementById("attack-zone");
    const rect = zone.getBoundingClientRect();

    const inside =
        x >= rect.left &&
        x <= rect.right &&
        y >= rect.top &&
        y <= rect.bottom;

    zone.classList.toggle("hover", inside);
}

function onPointerUp(e) {
    document.removeEventListener("pointermove", onPointerMove);
    document.removeEventListener("pointerup", onPointerUp);

    if (!isDragging || !dragCard) return;

    const zone = document.getElementById("attack-zone");
    const rect = zone.getBoundingClientRect();

    const inside =
        e.clientX >= rect.left &&
        e.clientX <= rect.right &&
        e.clientY >= rect.top &&
        e.clientY <= rect.bottom;

    dragCard.classList.remove("dragging");
    zone.classList.remove("hover");

    if (inside) {
        attack(dragIndex);
    } else {
        resetDraggedCard();
    }

    cleanupDrag();
}

function resetDraggedCard() {
    if (!dragCard) return;
    dragCard.style.transform = "";
}

function cleanupDrag() {
    dragCard = null;
    dragIndex = null;
    isDragging = false;
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





