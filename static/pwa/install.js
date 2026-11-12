const workerUrl = document.currentScript.dataset.worker;
if ('serviceWorker' in navigator && window.isSecureContext) {
    navigator.serviceWorker.register(workerUrl).catch(error => {
        console.warn('uMshova offline setup failed', error);
    });
}

const installButton = document.getElementById('pwa-install');
const installDialog = document.getElementById('pwa-install-dialog');
const isInstalled = () => matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;

if (installButton && installDialog && !isInstalled()) {
    const instructions = document.getElementById('pwa-install-help');
    const confirmButton = document.getElementById('pwa-install-confirm');
    const isAppleMobile = /iPhone|iPad|iPod/.test(navigator.userAgent) ||
        (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    const popupKey = 'umshova-install-popup-shown';
    let installPrompt;
    installButton.hidden = !isAppleMobile;

    window.addEventListener('beforeinstallprompt', event => {
        event.preventDefault();
        if (isInstalled()) return;
        installPrompt = event;
        installButton.hidden = false;
        if (typeof installDialog.showModal !== 'function') return;
        try {
            if (sessionStorage.getItem(popupKey)) return;
            sessionStorage.setItem(popupKey, '1');
        } catch (error) {
            // The manual install button remains available when storage is blocked.
            return;
        }
        if (!installDialog.open) installDialog.showModal();
    });

    const requestInstall = () => {
        if (!installPrompt || isInstalled()) return;
        const prompt = installPrompt;
        installPrompt = undefined;
        installButton.hidden = !isAppleMobile;
        if (installDialog.open) installDialog.close();
        prompt.prompt().catch(error => {
            console.warn('uMshova install prompt failed', error);
        });
    };

    installButton.addEventListener('click', () => {
        if (isInstalled()) return;
        if (typeof installDialog.showModal !== 'function') {
            requestInstall();
            return;
        }
        if (!installPrompt && isAppleMobile) {
            instructions.textContent = 'In Safari, tap Share, then Add to Home Screen.';
        }
        confirmButton.hidden = !installPrompt;
        if (!installDialog.open) installDialog.showModal();
    });
    confirmButton.addEventListener('click', requestInstall);

    window.addEventListener('appinstalled', () => {
        installPrompt = undefined;
        installButton.hidden = true;
        if (installDialog.open) installDialog.close();
    });
}
