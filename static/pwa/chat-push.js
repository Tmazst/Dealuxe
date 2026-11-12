(function () {
    const toggle = document.getElementById('match-chat-push-toggle');
    if (!toggle || !window.isSecureContext || !('serviceWorker' in navigator) ||
        !('PushManager' in window) || !('Notification' in window)) return;

    const status = document.getElementById('match-chat-push-status');
    const endpoint = toggle.dataset.endpoint;
    let publicKey;
    let enabled;

    function updateButton() {
        toggle.textContent = enabled ? 'Turn off chat notifications' : 'Enable chat notifications';
        toggle.hidden = false;
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
        status.textContent = 'Opponent messages can appear in device notifications.';
        updateButton();
    }).catch(() => {});

    toggle.addEventListener('click', async () => {
        toggle.disabled = true;
        status.textContent = '';
        try {
            if (enabled) {
                const response = await fetch(endpoint, {method: 'DELETE'});
                if (!response.ok) throw new Error('Could not turn off notifications.');
                enabled = false;
                status.textContent = 'Chat notifications are off on this device.';
                updateButton();
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
            status.textContent = 'Opponent messages can appear in device notifications.';
            updateButton();
        } catch (error) {
            status.textContent = 'Could not change chat notifications. Please try again.';
        } finally {
            toggle.disabled = false;
        }
    });
}());
