

let gameId = null;
let focusedCardIndex = null;
let selectedCardIndex = null;
let currentState = null;
let gameMode = null


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

    console.log("[FRONTEND] Game created:", gameId);
    await fetchState();
}

/* -----------------------------
   STATE FETCH
----------------------------- */

async function fetchState() {
    if (!gameId) return;

    const res = await fetch(`/api/game/${gameId}/state`);
    const state = await res.json();

    currentState = state;
    renderState(state);
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
    await fetch(`/api/game/${gameId}/start`, { method: "POST" });
    fetchState();
}


async function attack(index) {
    if (!currentState) return;
    if (currentState.phase !== "ATTACK") return;
    if (currentState.attacker !== 0) return;

    const cards = document.querySelectorAll(".card");
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
    const cards = document.querySelectorAll(".card");
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
    const pile = document.getElementById("attack-pile");
    const pileRect = pile.getBoundingClientRect();

    values.forEach((card, i) => {
        const ghost = document.createElement("div");
        ghost.className = "card";

        ghost.innerHTML = `
            <div class="rank">${card.rank}</div>
            <div class="center">${card.suit}</div>
            <div class="suit">${card.suit}</div>
        `;

        document.body.appendChild(ghost);

        ghost.style.position = "fixed";
        ghost.style.left = "50%";
        ghost.style.top = "-200px"; // off-screen
        ghost.style.transform = "translateX(-50%)";
        ghost.style.zIndex = 1000;

        const offsetX = i === 0 ? -12 : 12;
        const rotate = i === 0 ? -6 : 6;

        requestAnimationFrame(() => {
            ghost.style.transition = "all 0.45s ease";
            ghost.style.left = pileRect.left + offsetX + "px";
            ghost.style.top = pileRect.top + "px";
            ghost.style.transform = `rotate(${rotate}deg) scale(0.9)`;
        });

        setTimeout(() => ghost.remove(), 500);
        setOpponentStatus("Opponent defended, with cards: " + values.map(v => v.rank + v.suit).join(", "));
    });
}

function setOpponentStatus(text) {
    document.getElementById("agent-text").textContent = text;
}
/* -----------------------------
   RENDERING (TEMP / DEBUG)
----------------------------- */

function renderState(state) {
    // document.getElementById("state").innerText =
    //     JSON.stringify(state, null, 2);
    const myHand = state.hands[state.attacker];
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

// Interaction logic for card clicks 

function onCardClick(index) {
    const cards = document.querySelectorAll(".card");

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
    const cards = document.querySelectorAll(".card");
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

    const cardRect = cardEl.getBoundingClientRect();
    const pileRect = pile.getBoundingClientRect();

    const clone = cardEl.cloneNode(true);
    document.body.appendChild(clone);

    clone.style.position = "fixed";
    clone.style.left = cardRect.left + "px";
    clone.style.top = cardRect.top + "px";
    clone.style.width = cardRect.width + "px";
    clone.style.height = cardRect.height + "px";
    clone.style.margin = "0";
    clone.style.zIndex = 1000;

    requestAnimationFrame(() => {
        clone.style.transition = "all 0.4s ease";
        clone.style.left = pileRect.left + "px";
        clone.style.top = pileRect.top + "px";
        clone.style.transform = "scale(0.9)";
    });

    setTimeout(() => {
        clone.remove();
    }, 450);
}


function animateDefenseToAttackPile(cardEls) {
    const pile = document.getElementById("attack-pile");
    const pileRect = pile.getBoundingClientRect();

    cardEls.forEach((cardEl, i) => {
        const rect = cardEl.getBoundingClientRect();
        const clone = cardEl.cloneNode(true);

        document.body.appendChild(clone);

        clone.style.position = "fixed";
        clone.style.left = rect.left + "px";
        clone.style.top = rect.top + "px";
        clone.style.width = rect.width + "px";
        clone.style.height = rect.height + "px";
        clone.style.margin = "0";
        clone.style.zIndex = 1000;
        clone.classList.add("defense-card");

        const offsetX = i === 0 ? -10 : 10;
        const rotate = i === 0 ? -6 : 6;

        requestAnimationFrame(() => {
            clone.style.transition = "all 0.45s ease";
            clone.style.left = pileRect.left + offsetX + "px";
            clone.style.top = pileRect.top + "px";
            clone.style.transform = `rotate(${rotate}deg) scale(0.9)`;
        });

        setTimeout(() => clone.remove(), 500);
    });
}





