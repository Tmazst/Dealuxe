(function () {
    'use strict';

    const priorities = {
        commentary: 10,
        profile: 20,
        status: 30,
        gameplay: 40,
        safety: 50
    };
    const messages = new Map();

    function renderMessage() {
        const target = document.getElementById('agent-text');
        if (!target || messages.size === 0) return;
        const selected = Array.from(messages.values()).sort(function (a, b) {
            return b.priority - a.priority || b.updatedAt - a.updatedAt;
        })[0];
        target.textContent = selected.text;
    }

    function setMessage(channel, message, options) {
        const text = String(message || '').trim();
        if (!text) return;
        const settings = options || {};
        const priority = Number.isFinite(settings.priority)
            ? settings.priority
            : (priorities[channel] || priorities.commentary);
        messages.set(channel, {text: text, priority: priority, updatedAt: Date.now()});
        renderMessage();
        if (settings.ttl) {
            window.setTimeout(function () {
                clearMessage(channel);
            }, settings.ttl);
        }
    }

    function clearMessage(channel) {
        messages.delete(channel);
        renderMessage();
    }

    function clearOpponentContext() {
        const container = document.getElementById('hybrid-profile');
        if (container) container.hidden = true;
        [
            'hybrid-profile-name',
            'hybrid-profile-meta',
            'hybrid-profile-caption',
            'hybrid-profile-email',
            'hybrid-profile-phone'
        ].forEach(function (id) {
            const element = document.getElementById(id);
            if (element) element.textContent = '';
        });
        const image = document.getElementById('hybrid-profile-image');
        const placeholder = document.getElementById('hybrid-profile-placeholder');
        const icon = image && image.parentElement;
        if (image) {
            image.onload = null;
            image.onerror = null;
            image.removeAttribute('src');
            image.hidden = true;
        }
        if (placeholder) placeholder.hidden = false;
        if (icon) icon.classList.remove('has-profile');
    }

    function showContext(context) {
        const sharing = document.getElementById('hybrid-profile-sharing');
        const sharingToggle = document.getElementById('hybrid-profile-sharing-toggle');
        if (sharing && context) {
            sharing.hidden = false;
            if (sharingToggle && Object.prototype.hasOwnProperty.call(context, 'own_profile_visible')) {
                sharingToggle.checked = context.own_profile_visible !== false;
            }
        }
        const container = document.getElementById('hybrid-profile');
        if (!container || !context || !context.available || !context.opponent) {
            clearOpponentContext();
            return;
        }
        const opponent = context.opponent;
        document.getElementById('hybrid-profile-name').textContent = opponent.username || 'Opponent';
        document.getElementById('hybrid-profile-meta').textContent = [
            opponent.intent,
            opponent.category,
            opponent.subcategory
        ].filter(Boolean).join(' · ');
        document.getElementById('hybrid-profile-caption').textContent = opponent.caption || '';
        document.getElementById('hybrid-profile-email').textContent = opponent.email || 'Email not provided';
        document.getElementById('hybrid-profile-phone').textContent = opponent.phone || 'Contact not provided';
        const image = document.getElementById('hybrid-profile-image');
        const placeholder = document.getElementById('hybrid-profile-placeholder');
        const icon = image && image.parentElement;
        if (image && placeholder && opponent.profile_image_url) {
            function showPlaceholder() {
                image.hidden = true;
                placeholder.hidden = false;
                if (icon) icon.classList.remove('has-profile');
            }
            function showImage() {
                image.hidden = false;
                placeholder.hidden = true;
                if (icon) icon.classList.add('has-profile');
            }
            image.onload = showImage;
            image.onerror = showPlaceholder;
            showPlaceholder();
            image.src = opponent.profile_image_url;
            if (image.complete && image.naturalWidth > 0) showImage();
        } else if (image && placeholder) {
            image.removeAttribute('src');
            image.hidden = true;
            placeholder.hidden = false;
            if (icon) icon.classList.remove('has-profile');
        }
        container.hidden = false;
    }

    function loadContext() {
        const roomCode = document.body.dataset.tournamentRoom;
        if (!roomCode) return;
        window.fetch(
                '/api/hybrid/game/' + encodeURIComponent(roomCode) + '/context',
                {headers: {'Accept': 'application/json'}}
            )
            .then(function (response) {
                if (!response.ok) {
                    showContext({available: false, reason: 'context_unavailable'});
                    return null;
                }
                return response.json();
            })
            .then(function (payload) {
                if (payload) showContext(payload.context);
            })
            .catch(function () {
            // Hybrid context is optional; gameplay must continue unchanged.
            });
    }

    function bindProfileToggle() {
        const button = document.getElementById('hybrid-profile-toggle');
        const details = document.getElementById('hybrid-profile-details');
        if (!button || !details) return;
        button.addEventListener('click', function () {
            const shouldShow = details.hidden;
            details.hidden = !shouldShow;
            button.setAttribute('aria-expanded', String(shouldShow));
            button.textContent = shouldShow ? 'Collapse' : 'Expand';
        });
    }

    function bindSharingToggle() {
        const toggle = document.getElementById('hybrid-profile-sharing-toggle');
        const status = document.getElementById('hybrid-profile-sharing-status');
        const roomCode = document.body.dataset.tournamentRoom;
        if (!toggle || !status || !roomCode) return;
        toggle.addEventListener('change', function () {
            const requested = toggle.checked;
            toggle.disabled = true;
            status.textContent = 'Saving…';
            window.fetch(
                    '/api/hybrid/game/' + encodeURIComponent(roomCode) + '/preferences',
                    {
                        method: 'PUT',
                        headers: {'Accept': 'application/json', 'Content-Type': 'application/json'},
                        body: JSON.stringify({profile_visible: requested})
                    }
                )
                .then(function (response) {
                    if (!response.ok) throw new Error('Preference update failed');
                    return response;
                })
                .then(function () {
                status.textContent = requested ? 'Visible to opponent' : 'Hidden from opponent';
                requestChatContext();
                })
                .catch(function () {
                    toggle.checked = !requested;
                    status.textContent = 'Could not save';
                })
                .then(function () {
                toggle.disabled = false;
                window.setTimeout(function () { status.textContent = ''; }, 3000);
                });
        });
    }

    function bindVisibilityRefresh() {
        const roomCode = chatRoomCode();
        if (!roomCode || !window.socket) return;
        window.socket.on('hybrid_profile_visibility_changed', function (payload) {
            if (!payload || payload.room_code !== roomCode) return;
            loadContext();
            requestChatContext();
        });
    }

    function chatRoomCode() {
        return document.body.dataset.tournamentRoom || '';
    }

    function setChatEnabled(enabled, statusText) {
        const container = document.getElementById('hybrid-chat');
        const input = document.getElementById('hybrid-chat-input');
        const button = document.getElementById('hybrid-chat-send');
        const status = document.getElementById('hybrid-chat-status');
        if (!container) return;
        container.hidden = false;
        if (input) input.disabled = !enabled;
        if (button) button.disabled = !enabled;
        if (status) status.textContent = statusText || '';
    }

    function renderChatMessage(payload) {
        if (!payload || payload.room_code !== chatRoomCode()) return;
        const latest = document.getElementById('hybrid-chat-latest');
        if (!latest) return;
        latest.textContent = (payload.sender === 'you' ? 'You: ' : 'Opponent: ') + payload.message;
    }

    function requestChatContext() {
        const roomCode = chatRoomCode();
        if (!roomCode || !window.socket) return;
        window.socket.emit('hybrid_chat_context', {room_code: roomCode});
    }

    function bindChat() {
        const form = document.getElementById('hybrid-chat-form');
        const input = document.getElementById('hybrid-chat-input');
        const status = document.getElementById('hybrid-chat-status');
        const roomCode = chatRoomCode();
        if (!form || !input || !roomCode || !window.socket) return;

        window.socket.on('connect', requestChatContext);
        window.socket.on('hybrid_chat_context', function (payload) {
            if (!payload || payload.room_code !== roomCode) return;
            if (!payload.available) {
                setChatEnabled(false, 'Chat is off unless both players allow it.');
                return;
            }
            setChatEnabled(true, 'Messages expire after 24 hours.');
            renderChatMessage(payload.latest);
        });
        window.socket.on('hybrid_chat_message', function (payload) {
            renderChatMessage(payload);
            setChatEnabled(true, 'Delivered');
        });
        window.socket.on('hybrid_chat_error', function (payload) {
            setChatEnabled(payload && payload.code !== 'rate_limited', (payload && payload.message) || 'Message could not be sent');
            if (payload && payload.code === 'rate_limited') {
                window.setTimeout(function () {
                    setChatEnabled(true, 'Messages expire after 24 hours.');
                }, 3000);
            }
        });

        form.addEventListener('submit', function (event) {
            event.preventDefault();
            const message = input.value.trim();
            if (!message) return;
            setChatEnabled(false, 'Sending…');
            window.socket.emit('hybrid_chat_send', {
                room_code: roomCode,
                message: message,
                client_message_id: 'web_' + Date.now() + '_' + Math.random().toString(36).slice(2, 12)
            });
            input.value = '';
        });
        requestChatContext();
    }

    window.hybridPanel = {
        clearMessage: clearMessage,
        setMessage: setMessage,
        showContext: showContext
    };

    document.addEventListener('DOMContentLoaded', function () {
        setMessage('commentary', "Welcome! I'll guide you through the game.");
        bindProfileToggle();
        bindSharingToggle();
        bindChat();
        bindVisibilityRefresh();
        loadContext();
        window.setInterval(loadContext, 15000);
        window.addEventListener('focus', loadContext);
    });
}());
