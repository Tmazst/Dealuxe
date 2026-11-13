(function () {
    const toggle = document.getElementById('match-chat-push-toggle');
    if (!toggle || !window.isSecureContext || !('serviceWorker' in navigator) ||
        !('PushManager' in window) || !('Notification' in window)) return;

    const status = document.getElementById('match-chat-push-status');
    const endpoint = toggle.dataset.endpoint;
    let publicKey;
    let enabled = false;
    const promptKey = 'match-chat-push-prompt-used';
    const label = toggle.querySelector('span');
    const icon = toggle.querySelector('i');

    function showBell() {
        toggle.classList.remove('hybrid-chat-alert');
        label.hidden = true;
        icon.hidden = false;
        icon.classList.toggle('fa-bell', enabled);
        icon.classList.toggle('fa-bell-slash', !enabled);
        const action = enabled ? 'Turn off chat notifications' : 'Enable chat notifications';
        toggle.setAttribute('aria-label', action);
        toggle.title = action;
    }

    function applicationServerKey(value) {
        const encoded = value.replace(/-/g, '+').replace(/_/g, '/');
        const padded = encoded.padEnd(Math.ceil(encoded.length / 4) * 4, '=');
        return Uint8Array.from(atob(padded), char => char.charCodeAt(0));
    }

    fetch(endpoint, {cache: 'no-store'}).then(response => {
        if (!response.ok) return null;
        return response.json();
    }).then(config => {
        if (!config) return;
        publicKey = applicationServerKey(config.public_key);
        enabled = config.subscribed && Notification.permission === 'granted';
        let promptUsed = false;
        try {
            promptUsed = localStorage.getItem(promptKey) === '1';
        } catch {}
        if (enabled || promptUsed) showBell();
        toggle.hidden = false;
    }).catch(() => {});

    toggle.addEventListener('click', async () => {
        showBell();
        try {
            localStorage.setItem(promptKey, '1');
        } catch {}
        toggle.disabled = true;
        status.textContent = '';
        try {
            if (enabled) {
                const response = await fetch(endpoint, {method: 'DELETE'});
                if (!response.ok) throw new Error('Could not turn off notifications.');
                enabled = false;
                return;
            }

            if (await Notification.requestPermission() !== 'granted') {
                status.textContent = 'Allow notifications in your browser settings to receive match chat alerts.';
                return;
            }
            const registration = await navigator.serviceWorker.ready;
            const existing = await registration.pushManager.getSubscription();
            if (existing) await existing.unsubscribe();
            const subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: publicKey
            });
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(subscription)
            });
            if (!response.ok) throw new Error('Could not enable notifications.');
            enabled = true;
        } catch (error) {
            status.textContent = 'Could not change chat notifications. Please try again.';
        } finally {
            toggle.disabled = false;
            showBell();
        }
    });
}());
