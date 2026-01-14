(function(){
// Multiplayer client helper to integrate Socket.IO lobby with in-page game.html UI
'use strict';

// Reuse existing socket if available, otherwise create one
var socket = window.socket || (window.io ? io({ transports: ['websocket','polling'] }) : null);
if (!socket) {
    console.warn('Socket.IO not available for multiplayer-client.js');
};

// Track max observed hand counts for progress bars
window.currentMultiplayerProgress = window.currentMultiplayerProgress || { meMax: 0, oppMax: 0 };

function updateMultiplayerProgressBars(state, player_index) {
    if (!state || !Array.isArray(state.players)) return;
    var me = state.players[player_index] || {};
    var opp = state.players[player_index === 0 ? 1 : 0] || {};
    var meCount = Array.isArray(me.hand) ? me.hand.length : (me.hand_count || 0);
    var oppCount = Array.isArray(opp.hand) ? opp.hand.length : (opp.hand_count || 0);

    // Update maxes
    if (meCount > window.currentMultiplayerProgress.meMax) window.currentMultiplayerProgress.meMax = meCount;
    if (oppCount > window.currentMultiplayerProgress.oppMax) window.currentMultiplayerProgress.oppMax = oppCount;
    var meMax = Math.max(1, window.currentMultiplayerProgress.meMax);
    var oppMax = Math.max(1, window.currentMultiplayerProgress.oppMax);

    var cont = document.getElementById('leader-progess-bars-cont');
    if (!cont) return;
    var userCont = cont.querySelector('.user-progress-bar-cont');
    var oppCont = cont.querySelector('.opponent-progress-bar-cont');

    function setBar(container, current, max, isWinner) {
        if (!container) return;
        var fill = container.querySelector('.user-progress-fill');
        var text = container.querySelector('.user-progress-text');
        var pct = Math.round(((max - current) / max) * 100);
        if (fill) {
            fill.style.width = pct + '%';
            fill.classList.toggle('winner', !!isWinner);
            fill.classList.toggle('loser', !isWinner);
        }
        if (text) text.textContent = pct + '%';
        container.classList.toggle('winner', !!isWinner);
        container.classList.toggle('loser', !isWinner);
    }

    var mePct = Math.round(((meMax - meCount) / meMax) * 100);
    var oppPct = Math.round(((oppMax - oppCount) / oppMax) * 100);
    var meIsLeader = mePct >= oppPct; // green goes to highest percentage
    setBar(userCont, meCount, meMax, meIsLeader);
    setBar(oppCont, oppCount, oppMax, !meIsLeader);
}

function updateTurnIndicator(state, player_index) {
    try {
        var el = document.getElementById('turn-indicator');
        if (!el) return;
        var phase = state && state.phase;
        var attacker = state && state.attacker;
        var defender = state && state.defender;
        var isMyTurn = (phase === 'DEFENSE') ? (defender === player_index) : (attacker === player_index);
        var oppName = (typeof window.opponentName === 'string' && window.opponentName.length > 0) ? window.opponentName : 'Opponent';
        var myName = (document.querySelector('header .controls span.btn-glass') || {}).textContent || 'You';
        var name = isMyTurn ? myName : oppName;
        var icon = isMyTurn ? '🟦' : '🟫';
        // Show concise text
        el.textContent = icon + ' Turn: ' + name.trim();
        el.classList.add('visible');
    } catch (e) {}
}

window.multiplayerCreateRoom = function(options) {
    if (!socket) return;
    var payload = {
        card_count: options && options.card_count ? options.card_count : 6,
        bet_amount: options && typeof options.bet_amount === 'number' ? options.bet_amount : (options && options.bet ? options.bet : 0),
        bet_type: options && options.bet_type ? options.bet_type : 'fake'
    };
    console.log('multiplayerCreateRoom ->', payload);
    socket.emit('create_room', payload);
};

// Helper to detect if we're on the game page (rendered game UI)
function isGamePage() {
    return !!document.getElementById('player-cards');
};

// Minimal state applier: sets counts and dumps state for debugging
function applyStateToUI(state, player_index) {
    try {
        var myCountEl = document.getElementById('card-count-me');
        var oppCountEl = document.getElementById('card-count-opponent');
        if (myCountEl && oppCountEl && state && state.players) {
            var me = state.players[player_index];
            var opp = state.players[player_index === 0 ? 1 : 0];
            var myCount = Array.isArray(me.hand) ? me.hand.length : (me.hand_count || 0);
            var oppCount = Array.isArray(opp.hand) ? opp.hand.length : (opp.hand_count || 0);
            myCountEl.textContent = myCount;
            oppCountEl.textContent = oppCount;
        }
        var statePre = document.getElementById('state');
        if (statePre) {
            statePre.textContent = JSON.stringify(state, null, 2);
        }
    } catch (e) {
        console.error('Error applying state to UI', e);
    }
}

// Generate and render a multiplayer comment snippet regardless of engine ui_log
function renderMultiplayerCommentFromPayload(payload) {
    try {
        var gs = payload && payload.game_state ? payload.game_state : (payload && payload.state ? payload.state : {});
        var action = payload && payload.action ? payload.action : null;
        var actorIndex = (typeof payload.actor_index === 'number') ? payload.actor_index : null;
        var localIndex = (window.currentMultiplayer && typeof window.currentMultiplayer.player_index === 'number')
            ? window.currentMultiplayer.player_index
            : (typeof payload.player_index === 'number' ? payload.player_index : 0);
        // Resolve human-friendly names
        function getLocalUsername() {
            try {
                var el = document.querySelector('header .controls span.btn-glass');
                var txt = el && el.textContent ? el.textContent.trim() : null;
                if (txt && txt.length > 0) return txt;
            } catch (e) {}
            return 'You';
        }
        function resolveNames(locIdx) {
            var meName = getLocalUsername();
            var oppName = (typeof window.opponentName === 'string' && window.opponentName.length > 0) ? window.opponentName : 'Opponent';
            return (locIdx === 0) ? {0: meName, 1: oppName} : {0: oppName, 1: meName};
        }
        var names = resolveNames(localIndex);
        var actorName = (actorIndex !== null && names.hasOwnProperty(actorIndex)) ? names[actorIndex] : null;
        var otherIndex = (actorIndex === 0 ? 1 : (actorIndex === 1 ? 0 : (localIndex === 0 ? 1 : 0)));
        var otherName = names[otherIndex];
        function currentTurnName() {
            try {
                if (!gs) return null;
                var phase = gs.phase;
                if (phase === 'DEFENSE') return names[gs.defender];
                return names[gs.attacker];
            } catch (e) { return null; }
        }

        // Build neutral message (perspective label is added by renderComments via context)
        var msg = null;
        if (action === 'attack') {
            var atk = (gs && (gs.attack_card || (Array.isArray(gs.attack_pile) && gs.attack_pile[gs.attack_pile.length-1]))) || null;
            msg = '⚔️ ' + (actorName ? (actorName + ' attacked') : 'Attacked') + (atk ? (" with '" + atk + "'") : '');
            var tn = currentTurnName(); if (tn) msg += `. ${tn} to defend.`;
        } else if (action === 'defend') {
            var r = payload && payload.result ? payload.result : null;
            var dc = (r && Array.isArray(r.defence_cards)) ? r.defence_cards : ((r && Array.isArray(r.used_cards)) ? r.used_cards : []);
            var atkCard = gs && gs.attack_card ? gs.attack_card : null;
            var defenceStr = (dc && dc.length) ? (" '" + dc.join("' + '") + "'") : '';
            msg = '🛡️ ' + (actorName ? (actorName + ' defended') : 'Defended') + (defenceStr ? (' with' + defenceStr) : '') + (atkCard ? (` against ${otherName}'s '${atkCard}'`) : '');
            var tn2 = currentTurnName(); if (tn2) msg += `. It's ${tn2}'s turn.`;
        } else if (action === 'draw') {
            var atk2 = gs && gs.attack_card ? gs.attack_card : null;
            msg = '😬 ' + (actorName ? (actorName + ' failed to defend') : 'Failed to defend') + (atk2 ? (` against ${otherName}'s '${atk2}'`) : '') + ' and draws a card.';
            var tn3 = currentTurnName(); if (tn3) msg += ` It's ${tn3}'s turn again.`;
        } else if (action === 'rule8_drop') {
            msg = '🧊 ' + (actorName ? (actorName + ' drops a trail card') : 'Drops a trail card');
        } else if (action === 'rule8_crash') {
            msg = '💥 ' + (actorName ? (actorName + ' crashes the trail') : 'Crashes the trail');
        } else if (action === 'start') {
            // initial frame
            var turnPhase = gs && gs.phase ? gs.phase : null;
            var tn4 = currentTurnName();
            msg = '🎮 ' + (turnPhase ? ('Phase: ' + turnPhase) : 'Game started') + (tn4 ? (` — ${tn4} to play`) : '');
        }

        if (!msg) {
            // Fallback on phase change
            var phase = gs && gs.phase ? gs.phase : null;
            if (phase === 'ATTACK') msg = '🎯 Attacker is choosing a card';
            else if (phase === 'DEFENSE') msg = '🛡️ Defender is responding';
            else if (phase === 'RULE_8') msg = '🧊 Trailing in progress';
            else if (phase === 'GAME_OVER') msg = '🏆 Game over';
        }

        if (msg && typeof renderComments === 'function') {
            renderComments([msg], { actor_index: actorIndex, player_index: localIndex });
        }
    } catch (e) {
        try { console.warn('[multiplayer-client] renderMultiplayerCommentFromPayload failed', e); } catch (_e) {}
    }
}

// Handle game_started: if on game page, initialize without redirect
if (socket) {
    socket.on('game_started', function(data) {
        console.log('[multiplayer-client] game_started', data);
        // If the server intends to redirect to /game/<room_code> we will instead initialize in-page
        if (isGamePage()) {
            window.currentMultiplayer = {
                game_id: data.game_id,
                room_code: data.room_code,
                player_index: data.your_player_index,
                your_turn: data.your_turn,
                turn_deadline: data.turn_deadline
            };
            if (typeof setLocalPlayerIndex === 'function') setLocalPlayerIndex(data.your_player_index);
            // Apply masked state provided by server
            applyStateToUI(data.state, data.your_player_index);
                // Ensure draw button exists for multiplayer clients
                if (typeof createDrawButton === 'function') createDrawButton();
            // Populate global game variables so existing UI logic (renderState, attack/defend flows)
            // works unchanged for multiplayer.
            try {
                // Assign to the global identifiers used by game.js (these are declared with let)
                try { gameId = data.game_id; } catch (e) { window.gameId = data.game_id; }
                try { currentState = data.state; } catch (e) { window.currentState = data.state; }
                try { sessionStorage.setItem('game_id', data.game_id); } catch (e) {}
                if (typeof renderState === 'function') renderState(data.state);
            } catch (e) {
                console.error('[multiplayer-client] failed to set global game state', e);
            }
            try {
                // If server provided full hand for this player, render cards
                var me = data.state.players[data.your_player_index];
                if (me && Array.isArray(me.hand) && typeof renderCards === 'function') {
                    renderCards(me.hand);
                }

                // Build a minimal state for agent and UI helpers
                var mini = {
                    phase: data.state.phase,
                    attacker: data.state.attacker,
                    defender: data.state.defender,
                    attack_card: data.state.attack_card,
                    ui_log: data.state.ui_log || []
                };
                if (typeof updateAgent === 'function') updateAgent(mini);
                if (typeof renderComments === 'function') renderComments(mini.ui_log, { actor_index: null, player_index: data.your_player_index });
                if (typeof updateDrawButton === 'function') updateDrawButton(mini);
            } catch (e) { console.error('[multiplayer-client] error applying full UI update', e); }
            // Hard-coded multiplayer commentary snippet on start
            renderMultiplayerCommentFromPayload({ state: data.state, player_index: data.your_player_index, action: 'start' });
            // Close lobby modal if open
            if (typeof closeLobbyModal === 'function') closeLobbyModal();
            // Focus UI or show message
            if (data.your_turn) {
                // Optionally notify player
                console.log('It is your turn');
            }
            // Update mode label for multiplayer
            try {
                var modeVal = document.querySelector('.mode-caption-cont .mode-value');
                if (modeVal) modeVal.textContent = 'Multiplayer';
            } catch (e) {}
            // Update progress bars for multiplayer
            try { updateMultiplayerProgressBars(data.state, data.your_player_index); } catch (e) {}
            // Update turn indicator
            try { updateTurnIndicator(data.state, data.your_player_index); } catch (e) {}
        } else {
            // Not on game page - fallback to redirect behavior
            try { window.location.href = '/game/' + data.room_code; } catch (e) { console.error(e); }
        }
    });

    socket.on('game_update', function(payload) {
        // payload: { game_state, player_index, is_my_turn, action, result, turn_deadline }
        console.log('[multiplayer-client] game_update', payload);
        if (isGamePage()) {
            // Capture previous state before applying update to decide animations
            var prevState = null;
            try { prevState = (typeof currentState !== 'undefined') ? currentState : window.currentState; } catch (e) {}

            applyStateToUI(payload.game_state, payload.player_index);
            try {
                var me = payload.game_state.players[payload.player_index];
                // Render actual cards for this player when provided
                if (me && Array.isArray(me.hand) && typeof renderCards === 'function') {
                    renderCards(me.hand);
                }

                var mini = {
                    phase: payload.game_state.phase,
                    attacker: payload.game_state.attacker,
                    defender: payload.game_state.defender,
                    attack_card: payload.game_state.attack_card,
                    ui_log: payload.game_state.ui_log || []
                };
                if (typeof updateAgent === 'function') updateAgent(mini);
                if (typeof renderComments === 'function') renderComments(mini.ui_log, { actor_index: payload.actor_index, player_index: payload.player_index });
                if (typeof updateDrawButton === 'function') updateDrawButton(mini);

                // Animate defense cards landing in the attack pile when a defend action occurs
                try {
                    var action = payload && payload.action;
                    var result = payload && payload.result;
                    var actorIndex = (typeof payload.actor_index === 'number') ? payload.actor_index : null;
                    var defenceCards = null;
                    if (result) {
                        // result may be a Flask Response-JSON already parsed by server emit
                        defenceCards = result.defence_cards || result.used_cards || null;
                    }
                    if (action === 'defend' && Array.isArray(defenceCards) && defenceCards.length > 0) {
                        // Prefer authoritative actorIndex if provided by server
                        var localIndex = (window.currentMultiplayer && typeof window.currentMultiplayer.player_index === 'number')
                            ? window.currentMultiplayer.player_index
                            : payload.player_index;

                        var localWasDefender = false;
                        if (actorIndex !== null) {
                            localWasDefender = (actorIndex === localIndex);
                        } else {
                            // Legacy inference using prevState
                            localWasDefender = !!(prevState && prevState.phase === 'DEFENSE' && prevState.defender === localIndex);
                            if (!localWasDefender) {
                                // Fallback heuristic: check hand count drop
                                var prevMe = null, nowMe = null;
                                try {
                                    if (prevState && Array.isArray(prevState.players)) prevMe = prevState.players[localIndex];
                                    if (payload.game_state && Array.isArray(payload.game_state.players)) nowMe = payload.game_state.players[localIndex];
                                    var prevCount = (prevMe && Array.isArray(prevMe.hand)) ? prevMe.hand.length : (prevMe ? prevMe.hand_count : null);
                                    var nowCount = (nowMe && Array.isArray(nowMe.hand)) ? nowMe.hand.length : (nowMe ? nowMe.hand_count : null);
                                    if (typeof prevCount === 'number' && typeof nowCount === 'number' && (prevCount - nowCount) >= 2) localWasDefender = true;
                                } catch (e) { /* ignore */ }
                            }
                        }

                        if (localWasDefender && typeof animateUserDefense === 'function') {
                            animateUserDefense(defenceCards);
                        } else if (typeof animateOpponentDefense === 'function') {
                            animateOpponentDefense(defenceCards);
                        }
                    }
                } catch (animErr) {
                    console.warn('[multiplayer-client] defence animation skipped:', animErr);
                }
                // Ensure a multiplayer comment appears even if ui_log is empty
                renderMultiplayerCommentFromPayload(payload);
            } catch (e) { console.error('[multiplayer-client] error applying game_update UI', e); }
            // Ensure global state mirrors server update so UI handlers see authoritative state
            try {
                try { currentState = payload.game_state; } catch (e) { window.currentState = payload.game_state; }
                if (payload.game_id) try { gameId = payload.game_id; } catch (e) { window.gameId = payload.game_id; }
                if (typeof renderState === 'function') renderState(payload.game_state);
            } catch (e) { /* non-fatal */ }
            window.currentMultiplayer = window.currentMultiplayer || {};
            window.currentMultiplayer.your_turn = payload.is_my_turn;
            window.currentMultiplayer.turn_deadline = payload.turn_deadline;
            if (typeof setLocalPlayerIndex === 'function') setLocalPlayerIndex(payload.player_index);
            // Update progress bars and turn indicator
            try { updateMultiplayerProgressBars(payload.game_state, payload.player_index); } catch (e) {}
            try { updateTurnIndicator(payload.game_state, payload.player_index); } catch (e) {}
        }
    });

    socket.on('opponent_disconnected', function(data) {
        console.warn('[multiplayer-client] opponent_disconnected', data);
        if (isGamePage()) {
            // Show a temporary notice
            var agentText = document.getElementById('agent-text');
            if (agentText) agentText.textContent = 'Opponent disconnected - waiting for reconnection...';
        }
    });

    socket.on('opponent_reconnected', function(data) {
        console.log('[multiplayer-client] opponent_reconnected', data);
        if (isGamePage()) {
            var agentText = document.getElementById('agent-text');
            if (agentText) agentText.textContent = 'Opponent reconnected - game resumed';
        }
    });

    // Capture opponent name for in-page commentary
    socket.on('opponent_joined', function(data){
        if (data && typeof data.opponent_username === 'string') {
            window.opponentName = data.opponent_username;
        }
    });

    // Show game-over modal on both clients simultaneously (multiplayer)
    socket.on('game_over', function(data) {
        console.log('[multiplayer-client] game_over', data);
        if (!isGamePage()) return;
        try {
            // persist prize pool for modal display logic
            if (typeof sessionStorage !== 'undefined' && data && typeof data.prize_pool !== 'undefined') {
                sessionStorage.setItem('prize_pool', String(data.prize_pool || 0));
            }
        } catch (e) {}

        try {
            // Update global state and render final frame
            var finalState = data && data.state ? data.state : null;
            if (finalState) {
                try { currentState = finalState; } catch (e) { window.currentState = finalState; }
                if (typeof renderState === 'function') renderState(finalState);
                // render comments from final ui_log
                if (finalState.ui_log && typeof renderComments === 'function') renderComments(finalState.ui_log, { actor_index: null, player_index: (window.currentMultiplayer && window.currentMultiplayer.player_index) });
                // Also render a multiplayer summary line
                renderMultiplayerCommentFromPayload({ game_state: finalState, player_index: (window.currentMultiplayer && window.currentMultiplayer.player_index), action: 'game_over' });
            }
        } catch (e) {
            console.warn('[multiplayer-client] error applying game_over state', e);
        }
    });

    // Receive personal balance after game over and update modal
    socket.on('game_over_personal', function(payload){
        try {
            if (!isGamePage()) return;
            var nb = payload && payload.your_new_balance;
            if (!nb) return;
            var finalBalanceEl = document.getElementById('final-balance');
            if (finalBalanceEl) {
                var val = (typeof nb.fake === 'number') ? nb.fake : (typeof nb.real === 'number' ? nb.real : null);
                if (val !== null) {
                    finalBalanceEl.textContent = val.toFixed(2) + ' SZL';
                }
            }
        } catch (e) {
            try { console.warn('[multiplayer-client] game_over_personal handler failed', e); } catch(_e){}
        }
    });
}

// Expose helper to request rejoin
window.multiplayerRejoin = function(room_code) {
    if (!socket) return;
    socket.emit('reconnect_to_room', { room_code: room_code });
};

})();
