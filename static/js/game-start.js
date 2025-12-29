/**
 * Game Start Modal JavaScript
 * Handles form validation, bet type switching, and session creation
 */

// Game start form state
let gameStartForm = {
    opponentType: 'ai',
    cardCount: 6,
    betType: 'fake',
    betAmount: 0
};

// Store current balance globally
let currentBalance = 0;

// Initialize game start modal
function initGameStartModal() {
    const modal = document.querySelector('.game-start-modal');
    if (!modal) return;

    // Get form elements
    const opponentSelect = document.getElementById('choose_opponent');
    const cardCountSelect = document.getElementById('cards_number');
    const betTypeRadios = document.querySelectorAll('input[name="bet_or_free"]');
    const realBetField = document.querySelector('.real-bet-field');
    const fakeBetField = document.querySelector('.fake-bet-field');
    const startButton = document.querySelector('.game_start_btn');

    // Disable "Live Game" option (not implemented yet)
    if (opponentSelect) {
        const liveOption = opponentSelect.querySelector('option[value="Live_Game"]');
        if (liveOption) {
            liveOption.disabled = true;
            liveOption.textContent = 'Live Game (Coming Soon)';
            liveOption.style.color = '#999';
        }
    }

    // Handle bet type radio change
    if (betTypeRadios.length > 0) {
        betTypeRadios.forEach(radio => {
            radio.addEventListener('change', (e) => {
                gameStartForm.betType = e.target.value;
                toggleBetFields(e.target.value);
            });
            
            // Auto-select fake bet and disable real bet
            if (radio.value === 'fake') {
                radio.checked = true;
            } else if (radio.value === 'bet') {
                radio.disabled = true;
            }
        });

        // Set initial state
        const checkedRadio = document.querySelector('input[name="bet_or_free"]:checked');
        if (checkedRadio) {
            toggleBetFields(checkedRadio.value);
        } else {
            // Default to fake if nothing checked
            toggleBetFields('fake');
        }
    }

    // Handle opponent type change
    if (opponentSelect) {
        opponentSelect.addEventListener('change', (e) => {
            gameStartForm.opponentType = e.target.value;
            updateBetTypeAvailability(e.target.value);
        });
    }

    // Handle card count change
    if (cardCountSelect) {
        cardCountSelect.addEventListener('change', (e) => {
            gameStartForm.cardCount = parseInt(e.target.value);
        });
    }

    // Handle start button click
    if (startButton) {
        startButton.addEventListener('click', handleGameStart);
    }

    // Handle bet amount input for real-time balance display
    const fakeBetInput = document.getElementById('freegame_fake_bet');
    if (fakeBetInput) {
        fakeBetInput.addEventListener('input', updateBalanceDisplay);
    }

    // Fetch and display player balance
    fetchPlayerBalance();

    // Play modal open sound
    playModalOpenSound();

    console.log('[GAME-START] Modal initialized');
}

// Fetch player balance from API
async function fetchPlayerBalance() {
    try {
        const response = await fetch('/api/player/balance');
        const data = await response.json();

        if (data.success) {
            currentBalance = data.balance.fake;
            displayPlayerBalance(data.balance);
            updateBetBalanceDisplay(currentBalance, 0);
        }
    } catch (error) {
        console.error('[GAME-START] Error fetching balance:', error);
    }
}

// Display player balance in modal
function displayPlayerBalance(balance) {
    // Find or create balance display element
    let balanceDisplay = document.querySelector('.player-balance-display');
    
    if (!balanceDisplay) {
        balanceDisplay = document.createElement('div');
        balanceDisplay.className = 'player-balance-display';
        
        const modal = document.querySelector('.game-start-modal');
        if (modal) {
            // Insert at the top of the modal
            modal.insertBefore(balanceDisplay, modal.firstChild);
        }
    }

    // Format balance display
    const freeExpired = balance.free_cash_expired;
    const fakeBalance = freeExpired ? 0 : balance.fake;
    
    balanceDisplay.innerHTML = `
        <div class="balance-row">
            <span class="balance-label">Awarded Money:</span>
            <span class="balance-value ${freeExpired ? 'expired' : ''}">${fakeBalance.toFixed(2)} SZL</span>
        </div>
        <div class="balance-disclaimer">
            Please note: This is not real money
        </div>
        ${freeExpired ? '<div class="balance-note">Free cash expired. Click to claim new free cash!</div>' : ''}
    `;

    console.log('[GAME-START] Balance displayed:', balance);
}

// Toggle bet amount fields based on bet type
function toggleBetFields(betType) {
    const realBetField = document.querySelector('.real-bet-field');
    const fakeBetField = document.querySelector('.fake-bet-field');

    if (betType === 'bet') {
        // Real money bet
        if (realBetField) realBetField.style.display = 'block';
        if (fakeBetField) fakeBetField.style.display = 'none';
    } else {
        // Fake money bet
        if (realBetField) realBetField.style.display = 'none';
        if (fakeBetField) fakeBetField.style.display = 'block';
    }
}

// Update bet type availability based on opponent
function updateBetTypeAvailability(opponentType) {
    const betRadio = document.querySelector('input[name="bet_or_free"][value="bet"]');
    const freeRadio = document.querySelector('input[name="bet_or_free"][value="free"]');

    if (opponentType === 'ai') {
        // AI opponent: auto-select fake money
        if (freeRadio) {
            freeRadio.checked = true;
            freeRadio.dispatchEvent(new Event('change'));
        }
        // Disable real money option for AI
        if (betRadio) {
            betRadio.disabled = true;
        }
    } else {
        // Human opponent: enable both
        if (betRadio) {
            betRadio.disabled = false;
        }
    }
}

// Handle game start button click
async function handleGameStart(e) {
    e.preventDefault();

    console.log('[GAME-START] Starting game with:', gameStartForm);

    // Validate form
    const validation = validateGameStartForm();
    if (!validation.valid) {
        alert(validation.error);
        return;
    }

    // Get bet amount
    const betAmount = getBetAmount();
    if (betAmount === null) {
        alert('Please enter a valid bet amount');
        return;
    }

    gameStartForm.betAmount = betAmount;

    try {
        // Create session via API
        const response = await fetch('/api/session/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                opponent_type: gameStartForm.opponentType,
                card_count: gameStartForm.cardCount,
                bet_type: gameStartForm.betType,
                bet_amount: gameStartForm.betAmount
            })
        });

        const data = await response.json();

        if (!data.success) {
            alert(data.error || 'Failed to create game session');
            return;
        }

        console.log('[GAME-START] Session created:', data);

        // Store session info in sessionStorage for later use
        sessionStorage.setItem('session_id', data.session_id);
        sessionStorage.setItem('game_id', data.game_id);
        sessionStorage.setItem('prize_pool', data.prize_pool);
        sessionStorage.setItem('card_count', gameStartForm.cardCount);

        // Update header brand with prize pool
        updateHeaderBrand(data.prize_pool);

        // Hide modal
        hideGameStartModal();

        // Create game via existing endpoint
        await createGameWithSession(data.game_id);

        console.log('[GAME-START] Game started successfully');
        
    } catch (error) {
        console.error('[GAME-START] Error:', error);
        alert('Failed to start game. Please try again.');
    }
}

// Create game using existing game.js logic
async function createGameWithSession(gameId) {
    try {
        // Call existing createGame function if it exists
        if (typeof createGame === 'function') {
            await createGame();
        } else {
            console.warn('[GAME-START] createGame function not found, game may need manual initialization');
        }
    } catch (error) {
        console.error('[GAME-START] Error creating game:', error);
    }
}

// Validate game start form
function validateGameStartForm() {
    if (!gameStartForm.opponentType) {
        return { valid: false, error: 'Please select an opponent type' };
    }

    if (!gameStartForm.cardCount) {
        return { valid: false, error: 'Please select number of cards' };
    }

    if (!gameStartForm.betType) {
        return { valid: false, error: 'Please select bet type' };
    }

    return { valid: true };
}

// Get bet amount from appropriate field
function getBetAmount() {
    if (gameStartForm.betType === 'bet') {
        const input = document.getElementById('bet_amount');
        if (!input) return null;
        const value = parseFloat(input.value);
        return isNaN(value) ? null : value;
    } else {
        const input = document.getElementById('freegame_fake_bet');
        if (!input) return null;
        const value = parseFloat(input.value);
        return isNaN(value) ? null : value;
    }
}

// Hide game start modal
function hideGameStartModal() {
    const modal = document.querySelector('.game-start-modal-cont');
    if (modal) {
        modal.style.display = 'none';
    }
}

// Show game start modal (for testing)
function showGameStartModal() {
    const modal = document.querySelector('.game-start-modal-cont');
    if (modal) {
        modal.style.display = 'flex';
    }
}

// Ensure modal is visible on page load
function ensureModalVisible() {
    const modal = document.querySelector('.game-start-modal-cont');
    if (modal && !modal.style.display) {
        modal.style.display = 'flex';
    }
}

// Update header brand with prize pool
function updateHeaderBrand(prizePool) {
    const brandElement = document.querySelector('.site-header .brand');
    if (brandElement) {
        brandElement.textContent = `🎁${prizePool.toFixed(2)} SZL`;
    }
}

// Update bet balance display (current and after bet)
function updateBetBalanceDisplay(currentBal, betAmount) {
    const currentBalanceEl = document.getElementById('current-balance-value');
    const afterBetEl = document.getElementById('after-bet-value');
    
    if (currentBalanceEl) {
        currentBalanceEl.textContent = `${currentBal.toFixed(2)} SZL`;
    }
    
    if (afterBetEl) {
        const remaining = currentBal - betAmount;
        afterBetEl.textContent = `${remaining.toFixed(2)} SZL`;
        
        // Color code based on validity
        if (remaining < 0) {
            afterBetEl.style.color = '#ef4444'; // Red for insufficient
        } else if (remaining < currentBal * 0.2) {
            afterBetEl.style.color = '#f59e0b'; // Orange for low
        } else {
            afterBetEl.style.color = '#10b981'; // Green for good
        }
    }
}

// Handle bet amount input change
function updateBalanceDisplay() {
    const betInput = document.getElementById('freegame_fake_bet');
    if (!betInput) return;
    
    const betAmount = parseFloat(betInput.value) || 0;
    updateBetBalanceDisplay(currentBalance, betAmount);
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        ensureModalVisible();
        initGameStartModal();
    });
} else {
    ensureModalVisible();
    initGameStartModal();
}

console.log('[GAME-START] Script loaded');
