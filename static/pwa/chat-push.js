(function () {
    const toggle = document.getElementById('match-chat-push-toggle');
    const status = document.getElementById('match-chat-push-status');
    if (!toggle) return;

    const endpoint = toggle.dataset.endpoint;
    const supported = window.isSecureContext && 'serviceWorker' in navigator &&
        'PushManager' in window && 'Notification' in window && window.crypto && window.crypto.subtle;
    let registration;
    let publicKey;
    let registered = false;
    let active = false;

    function render(message) {
        toggle.textContent = registered ? 'Turn off notifications' : 'Enable notifications';
        toggle.hidden = !registered && (!supported || !publicKey);
        status.textContent = message || (active ? 'Notifications are on for this device.' :
            (registered ? 'Turn notifications off and back on to reconnect this device.' :
                'Notifications are off for this device.'));
    }

    function decodeKey(value) {
        const encoded = value.replace(/-/g, '+').replace(/_/g, '/');
        return Uint8Array.from(atob(encoded.padEnd(Math.ceil(encoded.length / 4) * 4, '=')),
            char => char.charCodeAt(0));
    }

    async function endpointHash(subscription) {
        const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(subscription.endpoint));
        return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
    }

    function matchesKey(subscription) {
        const key = new Uint8Array(subscription.options.applicationServerKey);
        return key.length === publicKey.length && key.every((byte, index) => byte === publicKey[index]);
    }

    async function initialise() {
        const response = await fetch(endpoint, {cache: 'no-store'});
        if (!response.ok) throw new Error();
        const config = await response.json();
        registered = config.subscribed;

        if (!supported) return render('Push is unavailable in this browser. On iPhone or iPad, open uMshova from the Home Screen.');
        if (!config.public_key) return render('Push notifications are currently unavailable.');
        registration = await navigator.serviceWorker.register(toggle.dataset.worker);
        publicKey = decodeKey(config.public_key);
        const subscription = await registration.pushManager.getSubscription();
        active = registered && Notification.permission === 'granted' && subscription &&
            matchesKey(subscription) && config.endpoint_hash === await endpointHash(subscription);
        render(Notification.permission === 'denied' ? 'Notifications are blocked in your browser settings.' : '');
    }

    initialise().catch(() => render('Could not check notifications. Reload this page to try again.'));

    toggle.addEventListener('click', async () => {
        toggle.disabled = true;
        try {
            if (registered) {
                const response = await fetch(endpoint, {method: 'DELETE'});
                if (!response.ok) throw new Error();
                registered = false;
                active = false;
                render();
                return;
            }

            if (await Notification.requestPermission() !== 'granted') {
                render('Allow notifications in your browser settings to finish enabling them.');
                return;
            }
            registration = await navigator.serviceWorker.ready;
            let subscription = await registration.pushManager.getSubscription();
            if (subscription && !matchesKey(subscription)) {
                await subscription.unsubscribe();
                subscription = null;
            }
            if (!subscription) {
                subscription = await registration.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: publicKey
                });
            }
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(subscription)
            });
            if (!response.ok) throw new Error();
            registered = true;
            active = true;
            render();
        } catch (error) {
            render('Could not change notifications. Please try again.');
        } finally {
            toggle.disabled = false;
        }
    });
}());
