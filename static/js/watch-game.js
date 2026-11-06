(() => {
    'use strict';
    const root = document.getElementById('spectator-game');
    if (!root) return;
    const code = root.dataset.roomCode;
    const endpoint = `/api/watch/${encodeURIComponent(code)}`;
    const status = document.getElementById('connection-status');
    const notice = document.getElementById('watch-notice');
    let version = 0, state = null, pending = false, socket = null, stopped = false;
    let lastReceived = 0;
    let receivedInitial = false, suppressNextLive = true;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    function message(text) { notice.textContent = text; notice.hidden = !text; }
    function connection(text, live = false) { status.textContent = text; status.classList.toggle('live', live); }
    function showCards(cards, container, {key = '', animate = false, direction = 'attack', emptyText = 'Waiting for a public move'} = {}) {
        const fingerprint = JSON.stringify([key, cards, emptyText]);
        if (container.dataset.cardsKey === fingerprint) return;
        container.dataset.cardsKey = fingerprint;
        const previous = container.watchCards;
        const appendOnly = previous && previous.key === key && previous.cards.length > 0
            && cards.length >= previous.cards.length && previous.cards.every((card, index) => cards[index] === card);
        const start = appendOnly ? previous.cards.length : 0;
        if (!appendOnly) container.replaceChildren();
        container.watchCards = {key, cards:cards.slice()};
        cards.slice(start).forEach((value, index) => {
            const card = document.createElement('div');
            if (value === null) {
                card.className = 'drawn-public-back'; card.textContent = '◆';
                card.setAttribute('aria-label', 'A hidden card was drawn');
            } else {
            const label = String(value);
            card.className = 'played-card' + (/[♥♦]/.test(label) ? ' red' : '');
            card.setAttribute('aria-label', `Public card ${label}`);
            const small = document.createElement('small'); small.textContent = label;
            const center = document.createElement('b'); center.textContent = label;
            card.append(small, center, small.cloneNode(true));
            }
            if (animate && !reducedMotion.matches && !document.hidden) {
                const animation = direction === 'attack' ? 'card-enter-attack' : 'card-enter-defense';
                card.classList.add(animation);
                card.style.setProperty('--card-delay', `${Math.min(index, 2) * 45}ms`);
                card.addEventListener('animationend', () => card.classList.remove(animation), {once:true});
            }
            container.append(card);
        });
        if (!cards.length) { const empty = document.createElement('span'); empty.className = 'empty-table'; empty.textContent = emptyText; container.append(empty); }
    }
    function cardValue(card) {
        const rank = String(card).replace(/[♥♦♣♠]/g, '');
        const value = {A:1, J:11, Q:12, K:13}[rank] ?? Number(rank);
        return Number.isInteger(value) && value >= 1 && value <= 13 ? value : null;
    }
    function setText(node, text) { if (node.textContent !== text) node.textContent = text; }
    function renderExchange(payload, animate) {
        const exchange = payload.exchange;
        const attack = document.getElementById('public-cards');
        const defense = document.getElementById('exchange-defense');
        const defenseCards = document.getElementById('defense-cards');
        const outcome = document.getElementById('exchange-outcome');
        const explanation = document.getElementById('exchange-explanation');
        const pileLabel = document.getElementById('pile-label');
        if (!exchange) {
            defense.hidden = outcome.hidden = explanation.hidden = true;
            const cards = payload.attack_card ? [payload.attack_card] : (payload.last_play || []);
            pileLabel.textContent = payload.attack_card ? 'PUBLIC TABLE' : cards.length ? 'LAST PUBLIC PLAY' : 'PUBLIC TABLE';
            showCards(cards, attack, {animate, emptyText:payload.status === 'completed' ? 'No public moves were recorded for this match' : 'Waiting for a public move'});
            return;
        }
        const attacker = payload.players[exchange.attacker_index]?.name || 'Attacker';
        const defender = payload.players[exchange.defender_index]?.name || 'Defender';
        outcome.hidden = explanation.hidden = false;
        outcome.className = 'exchange-outcome';
        if (exchange.kind === 'trail') {
            pileLabel.textContent = `RULE 8 · ${attacker}’s public trail`;
            showCards(exchange.trail_cards || [], attack, {key:exchange.id, animate, direction:exchange.attacker_index === 1 ? 'defense' : 'attack'});
            defense.hidden = true;
            setText(outcome, exchange.outcome === 'crashed' ? 'Trail crashed' : exchange.outcome === 'continued' ? 'Trail continues' : 'Trail card played');
            setText(explanation, exchange.outcome === 'crashed' ? 'The trail was interrupted. Any card drawn stays hidden.' : 'These cards were played publicly. Cards still held by either player stay hidden.');
            return;
        }
        pileLabel.textContent = `ATTACK · ${attacker}`;
        showCards([exchange.attack_card], attack, {key:exchange.id, animate, direction:exchange.attacker_index === 1 ? 'defense' : 'attack'});
        defense.hidden = false;
        document.getElementById('defense-label').textContent = `DEFENSE · ${defender}`;
        if (exchange.outcome === 'defended') {
            const cards = exchange.defense_cards || [];
            showCards(cards, defenseCards, {key:exchange.id, animate, direction:exchange.defender_index === 0 ? 'attack' : 'defense'});
            const values = cards.map(cardValue);
            const equation = values.length && values.every(value => value !== null) ? `${values.join(' + ')} = ${exchange.target_value}` : '';
            setText(outcome, equation ? `Successful defense: ${equation}` : 'Successful defense');
            outcome.classList.add('success');
            setText(explanation, `${defender} matched the attack${payload.status === 'completed' ? '.' : '. This exchange stays visible until the next attack.'}`);
        } else if (exchange.outcome === 'drew') {
            showCards([null], defenseCards, {key:exchange.id, animate, direction:exchange.defender_index === 0 ? 'attack' : 'defense'});
            setText(outcome, `No defense — ${defender} drew a card`);
            setText(explanation, `The drawn card stays hidden.${payload.status === 'completed' ? '' : ` ${attacker} keeps the attack.`}`);
        } else {
            showCards([], defenseCards, {key:exchange.id, emptyText:payload.status === 'completed' ? 'Match finished' : 'Waiting for the defense'});
            setText(outcome, payload.status === 'completed' ? 'Final public attack' : `Attack value: ${exchange.target_value}`);
            setText(explanation, 'A defense needs two or three cards whose values add up to the attack. A = 1, J = 11, Q = 12, K = 13.');
        }
    }
    function render(payload, animateLive = false) {
        if (!payload || payload.room_code !== code || !Array.isArray(payload.players) || payload.players.length !== 2 || payload.version < version) return;
        state = payload; version = payload.version; lastReceived = Date.now();
        document.getElementById('tournament-name').textContent = (payload.is_promotional ? 'PROMOTIONAL · ' : '') + payload.tournament_name;
        document.getElementById('match-title').textContent = `${payload.players[0].name} vs ${payload.players[1].name}`;
        document.title = `${payload.players[0].name} vs ${payload.players[1].name} · Watch | uMshova Dealuxe`;
        document.getElementById('match-round').textContent = `${payload.round_name} · Match ${payload.match_number}`;
        payload.players.forEach((player, index) => {
            const node = document.getElementById(`player-${index}`);
            node.querySelector('.player-name').textContent = player.name;
            node.querySelector('.avatar').textContent = Array.from(player.name)[0] || '?';
            node.querySelector('.card-count').textContent = player.hand_count == null ? 'Count unavailable' : `${player.hand_count} card${player.hand_count === 1 ? '' : 's'}`;
            const hand = document.getElementById(`hand-${index}`);
            hand.setAttribute('aria-label', `${player.name}: ${player.hand_count == null ? 'unknown number of' : player.hand_count} cards, all hidden`);
            if (hand.dataset.count === String(player.hand_count)) return;
            hand.dataset.count = String(player.hand_count); hand.replaceChildren();
            for (let n = 0; n < Math.min(player.hand_count || 0, 12); n++) { const back = document.createElement('span'); back.className = 'card-back'; back.textContent = '◆'; back.setAttribute('aria-hidden', 'true'); hand.append(back); }
            if (player.hand_count > 12) { const extra = document.createElement('span'); extra.className = 'extra-cards'; extra.textContent = `+${player.hand_count - 12}`; hand.append(extra); }
        });
        renderExchange(payload, animateLive && receivedInitial);
        receivedInitial = true;
        document.getElementById('match-completed').hidden = payload.status !== 'completed';
        if (payload.status === 'completed') {
            setText(document.getElementById('finished-title'), payload.winner_index == null
                ? 'Keep the action going' : `${payload.players[payload.winner_index].name} takes the win!`);
        }
        const turn = document.getElementById('turn-status');
        if (payload.status === 'completed') {
            turn.textContent = payload.winner_index == null ? 'Match finished' : `${payload.players[payload.winner_index].name} wins`;
            connection('Finished'); message('Match finished. Both hands remain hidden.');
        } else if (!payload.available) {
            turn.textContent = 'Live state temporarily unavailable'; connection('Reconnecting…'); message('Waiting for the game service. Updates will resume automatically.');
        } else if (payload.status === 'paused') {
            turn.textContent = 'Match paused'; connection('Paused'); message('The players have paused this match. Updates will resume when they continue.');
        } else {
            const actor = payload.phase === 'DEFENSE' ? payload.defender : payload.attacker;
            const name = payload.players[actor]?.name;
            turn.textContent = name ? `${name} ${payload.phase === 'DEFENSE' ? 'is defending' : payload.phase === 'RULE_8' ? 'is trailing · Rule 8' : 'is attacking'}` : 'Waiting for the next turn';
            connection('Live', true); message('');
        }
        const moves = document.getElementById('public-moves');
        const movesKey = JSON.stringify(payload.events || []);
        if (moves.dataset.eventsKey !== movesKey) {
        moves.dataset.eventsKey = movesKey; moves.replaceChildren();
        (payload.events || []).slice().reverse().forEach(event => {
            const li = document.createElement('li'); li.textContent = event.text;
            const time = document.createElement('time'); time.dateTime = event.at;
            time.textContent = new Date(event.at).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'});
            li.append(time); moves.append(li);
        });
        if (!moves.children.length) { const li = document.createElement('li'); li.textContent = 'Public moves will appear here.'; moves.append(li); }
        }
        tick();
    }
    function tick() {
        const timer = document.getElementById('turn-timer');
        if (!state?.turn_deadline || state.status !== 'in_progress' || !state.available) { timer.textContent = ''; return; }
        const remaining = Math.max(0, Math.ceil((Date.parse(state.turn_deadline) - Date.now()) / 1000));
        timer.textContent = remaining ? `Turn ends in ${String(Math.floor(remaining / 60)).padStart(2, '0')}:${String(remaining % 60).padStart(2, '0')}` : 'Waiting for the next move';
    }
    async function refresh() {
        if (pending || stopped || document.hidden) return;
        pending = true;
        try {
            const response = await fetch(endpoint, {headers:{Accept:'application/json'}, cache:'no-store'});
            if (response.status === 404) { stopped = true; socket?.disconnect(); connection('Unavailable'); message('This match is no longer available to watch. Please return to the bracket.'); return; }
            if (!response.ok) throw new Error('State unavailable');
            render(await response.json());
        } catch (_) { connection('Reconnecting…'); message('Connection interrupted. Showing the last confirmed public state while we reconnect.'); }
        finally { pending = false; }
    }
    if (typeof io === 'function') {
        socket = io({transports:JSON.parse(root.dataset.transports)});
        socket.on('connect', () => { suppressNextLive = true; if (!stopped) { socket.emit('watch_game', {room_code:code}); refresh(); } });
        socket.on('spectator_update', payload => { render(payload, !suppressNextLive); suppressNextLive = false; });
        socket.on('disconnect', () => { if (state?.status !== 'completed' && !stopped) connection('Reconnecting…'); });
        socket.on('spectator_error', payload => { connection('Reconnecting…'); message(payload.message || 'Live updates are temporarily unavailable'); });
        socket.on('connect_error', () => { if (state?.status !== 'completed') connection('Checking for updates…'); });
    }
    refresh();
    const polling = setInterval(() => { if (state?.status !== 'completed') refresh(); }, 15000);
    const clock = setInterval(() => { tick(); if (state?.status === 'in_progress' && Date.now() - lastReceived > 45000) connection('Checking for updates…'); }, 1000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
    window.addEventListener('pagehide', event => { if (!event.persisted) { clearInterval(polling); clearInterval(clock); } socket?.emit('leave_watch_game'); socket?.disconnect(); });
    window.addEventListener('pageshow', event => { if (event.persisted && !stopped) { socket?.connect(); refresh(); } });
})();
