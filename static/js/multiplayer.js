// ==============================================
// MULTIPLAYER.JS - SocketIO Client for Lobby
// ==============================================

// Only initialize Socket.IO for lobby page
const socket = io({
    transports: ['websocket', 'polling'],
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionAttempts: 5
});
// expose socket to page-level scripts so multiplayer-client.js can reuse it
window.socket = socket;

let currentUserId = null;
let currentRoomCode = null;

// ==============================================
// CONNECTION EVENTS
// ==============================================

socket.on('connect', () => {
    console.log('✅ Connected to server:', socket.id);
    // Request lobby data (works for both authenticated and guest users)
    socket.emit('get_lobby');
});

socket.on('connected', (data) => {
    console.log('🔌 Connection acknowledged:', data);
    if (data.authenticated) {
        currentUserId = data.user_id;
    }
});

socket.on('disconnect', () => {
    console.log('❌ Disconnected from server');
});

socket.on('error', (data) => {
    console.error('❌ Socket error:', data);
    if (data.message) {
        console.error('Error message:', data.message);
    }
});

// ==============================================
// LOBBY EVENTS
// ==============================================

socket.on('lobby_data', (data) => {
    console.log('📋 Lobby data received:', data);
    updateAvailableRooms(data.available_rooms);
    // updateMyGames is not used in current lobby.html layout
});

socket.on('room_created', (data) => {
    console.log('🎉 Room created:', data);
    const roomCode = data.room ? data.room.room_code : data.room_code;
    alert(`Room ${roomCode} created! Waiting for opponent...`);
    // Refresh lobby
    socket.emit('get_lobby');
});

socket.on('opponent_joined', (data) => {
    console.log('👥 Opponent joined:', data);
    alert(`Opponent ${data.opponent_username} joined! Game starting soon...`);
    // Refresh lobby
    socket.emit('get_lobby');
});

socket.on('game_starting', (data) => {
    console.log('⏳ Game starting in:', data.countdown);
    // Could show a countdown UI here
});

socket.on('game_started', (data) => {
    console.log('🎮 Game started:', data);
    // If we're already on the in-page game UI, do not redirect — the in-page
    // multiplayer client will handle applying the state. Otherwise redirect.
    if (document.getElementById && document.getElementById('player-cards')) {
        console.log('On game page — skipping redirect, in-page client will handle state.');
        return;
    }
    // Redirect to game page for non-embedded lobby flows
    window.location.href = `/game/${data.room_code}`;
});

socket.on('room_joined', (data) => {
    console.log('✅ Joined room:', data);
    currentRoomCode = data.room_code;
    
    if (data.status === 'in_progress') {
        // Game already in progress, redirect
        window.location.href = `/game/${data.room_code}`;
    } else {
        alert(`Joined room ${data.room_code}! Waiting for game to start...`);
        socket.emit('get_lobby');
    }
});

// ==============================================
// FORM HANDLERS
// ==============================================

const createRoomBtn = document.getElementById('create-room-btn');
if (createRoomBtn) {
    createRoomBtn.addEventListener('click', (e) => {
        e.preventDefault();
        
        // Check if user is logged in (defined in lobby.html)
        if (typeof isLoggedIn !== 'undefined' && !isLoggedIn) {
            if (typeof showLoginModal === 'function') {
                showLoginModal();
            } else {
                alert('Please login to create a room');
                window.location.href = '/login';
            }
            return;
        }
        
        const cardCount = 6; // Default card count
        const betAmount = parseFloat(document.getElementById('bet-amount').value) || 0;
        const betType = 'fake'; // Default to fake for now
        
        console.log('🎲 Creating room:', { cardCount, betAmount, betType });
        
        socket.emit('create_room', {
            card_count: cardCount,
            bet_amount: betAmount,
            bet_type: betType
        });
    });
}

// ==============================================
// UI UPDATE FUNCTIONS
// ==============================================

function updateAvailableRooms(rooms) {
    const container = document.getElementById('room-list');
    
    if (!container) {
        console.warn('⚠️ room-list element not found');
        return;
    }
    
    if (!rooms || rooms.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fa-solid fa-inbox"></i>
                <p>No rooms available. Create one to start playing!</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = rooms.map(room => {
        const onlineStatus = room.creator_online ? 'online' : 'offline';
        const timeAgo = formatTimeAgo(room.room_age_hours);
        const betTypeIcon = room.bet_type === 'fake' ? '🎁' : '💰';
        
        return `
        <div class="room-item">
            <div class="room-avatar">
                <i class="fa-solid fa-user"></i>
                <div class="online-indicator ${onlineStatus}"></div>
            </div>
            <div class="room-details-container">
                <div class="room-header">
                    <div>
                        <div class="room-id">
                            <span class="room-code-badge">${room.room_code}</span>
                        </div>
                        <div class="creator-name">
                            <i class="fa-solid fa-crown" style="color: #fbbf24; font-size: 12px;"></i>
                            ${room.created_by_username || 'Unknown'}
                        </div>
                    </div>
                    <div>
                        <span class="room-status status-${room.status}">${room.status}</span>
                    </div>
                </div>
                <div class="room-stats">
                    <div class="stat-item">
                        <i class="fa-solid fa-layer-group stat-icon"></i>
                        <span>${room.card_count} cards</span>
                    </div>
                    <div class="stat-item">
                        <span>${betTypeIcon}</span>
                        <span>${room.bet_amount} SZL</span>
                    </div>
                    <div class="stat-item">
                        <i class="fa-solid fa-tag stat-icon"></i>
                        <span>${room.bet_type}</span>
                    </div>
                    <div class="stat-item room-age">
                        <i class="fa-solid fa-clock"></i>
                        <span>${timeAgo}</span>
                    </div>
                </div>
            </div>
            <button class="join-room-btn" onclick="joinRoom('${room.room_code}')">
                <i class="fa-solid fa-right-to-bracket"></i> Join
            </button>
        </div>
        `;
    }).join('');
}

function formatTimeAgo(hours) {
    if (hours < 0.017) { // less than 1 minute
        return 'Just now';
    } else if (hours < 1) {
        const minutes = Math.floor(hours * 60);
        return `${minutes}m ago`;
    } else {
        const h = Math.floor(hours);
        const m = Math.floor((hours - h) * 60);
        return m > 0 ? `${h}h ${m}m ago` : `${h}h ago`;
    }
}


function updateMyGames(games) {
    const container = document.getElementById('myGames');
    
    if (!games || games.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <p>You have no active games.</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = games.map(game => {
        let statusText = game.status.toUpperCase();
        let buttonText = 'Resume';
        let buttonClass = 'btn-warning';
        
        if (game.status === 'waiting') {
            statusText = 'WAITING FOR OPPONENT';
            buttonText = 'Enter Room';
        } else if (game.status === 'paused') {
            statusText = 'PAUSED';
            buttonText = 'Resume';
        } else if (game.status === 'in_progress') {
            statusText = game.is_my_turn ? 'YOUR TURN' : 'OPPONENT TURN';
            buttonText = 'Continue';
            buttonClass = 'btn-success';
        }
        
        return `
            <div class="room-card">
                <div class="room-info">
                    <div class="room-code">🎮 ${game.room_code}</div>
                    <div class="room-details">
                        vs ${game.opponent_name || 'Waiting...'}
                        <span class="room-status ${game.status}">${statusText}</span>
                    </div>
                </div>
                <button class="btn ${buttonClass}" onclick="rejoinRoom('${game.room_code}')">
                    ${buttonText}
                </button>
            </div>
        `;
    }).join('');
}

// ==============================================
// ACTION FUNCTIONS
// ==============================================

function joinRoom(roomCode) {
    // Check if user is logged in (defined in lobby.html)
    if (typeof isLoggedIn !== 'undefined' && !isLoggedIn) {
        if (typeof showLoginModal === 'function') {
            showLoginModal();
        } else {
            alert('Please login to join a room');
            window.location.href = '/login';
        }
        return;
    }
    
    console.log('🚪 Joining room:', roomCode);
    socket.emit('join_room', { room_code: roomCode });
}

function rejoinRoom(roomCode) {
    console.log('🔄 Rejoining room:', roomCode);
    socket.emit('reconnect_to_room', { room_code: roomCode });
}

// ==============================================
// AUTO-REFRESH LOBBY
// ==============================================

// Refresh lobby every 5 seconds
setInterval(() => {
    socket.emit('get_lobby');
}, 5000);
