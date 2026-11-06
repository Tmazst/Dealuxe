(function () {
    'use strict';

    var originalFetch = window.fetch.bind(window);
    var unsafeMethods = { POST: true, PUT: true, PATCH: true, DELETE: true };
    var refreshing = null;
    var refreshedToken = '';
    var waitingForms = new WeakSet();

    function token() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : refreshedToken;
    }

    function ownForm(form) {
        var method = String(form.getAttribute('method') || 'GET').toUpperCase();
        var target = new URL(form.getAttribute('action') || window.location.href, window.location.href);
        return unsafeMethods[method] && target.origin === window.location.origin;
    }

    function updateForms(value) {
        if (!value) return;
        document.querySelectorAll('form').forEach(function (form) {
            if (!ownForm(form)) return;
            var field = form.querySelector('input[name="csrf_token"]');
            if (!field) {
                field = document.createElement('input');
                field.type = 'hidden'; field.name = 'csrf_token'; form.appendChild(field);
            }
            field.value = value;
        });
    }

    function refreshToken() {
        if (refreshing) return refreshing;
        refreshing = originalFetch('/api/security/csrf-token', {
            credentials:'same-origin', cache:'no-store', headers:{Accept:'application/json'}
        }).then(function (response) {
            if (!response.ok) throw new Error('Security token unavailable');
            return response.json();
        }).then(function (data) {
            if (!data.csrf_token) throw new Error('Security token unavailable');
            refreshedToken = data.csrf_token;
            var meta = document.querySelector('meta[name="csrf-token"]');
            if (meta) meta.setAttribute('content', refreshedToken);
            updateForms(refreshedToken);
        }).finally(function () { refreshing = null; });
        return refreshing;
    }

    window.fetch = async function (input, init) {
        var options = Object.assign({}, init || {});
        var requestMethod = input instanceof Request ? input.method : 'GET';
        var method = String(options.method || requestMethod || 'GET').toUpperCase();
        var requestUrl = input instanceof Request ? input.url : String(input);
        var target = new URL(requestUrl, window.location.href);

        var protectedRequest = unsafeMethods[method] && target.origin === window.location.origin;
        if (protectedRequest) {
            // A returning tab may already be refreshing its expired token.
            if (refreshing) { try { await refreshing; } catch (_) {} }
            var headers = new Headers(
                options.headers || (input instanceof Request ? input.headers : undefined)
            );
            var csrfToken = token();
            if (csrfToken && !headers.has('X-CSRFToken')) {
                headers.set('X-CSRFToken', csrfToken);
            }
            options.headers = headers;
        }
        var response = await originalFetch(input, options);
        // Retry only an explicit pre-action CSRF rejection, never a payment,
        // network failure, or other application error. Streams are not replayed.
        var replayable = !(input instanceof Request) && !(options.body && typeof options.body.getReader === 'function');
        if (protectedRequest && replayable && response.status === 400) {
            var error;
            try { error = await response.clone().json(); } catch (_) { return response; }
            if (error && error.code === 'csrf_rejected') {
                try {
                    await refreshToken();
                    var freshHeaders = new Headers(options.headers);
                    freshHeaders.set('X-CSRFToken', token()); options.headers = freshHeaders;
                    return originalFetch(input, options);
                } catch (_) { return response; }
            }
        }
        return response;
    };

    document.addEventListener('DOMContentLoaded', function () {
        updateForms(token());
    });
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden) refreshToken().catch(function () {});
    });
    window.addEventListener('pageshow', function (event) {
        if (event.persisted) refreshToken().catch(function () {});
    });
    document.addEventListener('submit', function (event) {
        var form = event.target;
        if (!refreshing || !ownForm(form)) return;
        event.preventDefault();
        if (waitingForms.has(form)) return;
        waitingForms.add(form);
        var submitter = event.submitter;
        var resume = function () {
            waitingForms.delete(form);
            form.requestSubmit(submitter && submitter.form === form ? submitter : undefined);
        };
        refreshing.then(resume, resume);
    });
    var lifetime = document.querySelector('meta[name="csrf-token-lifetime"]');
    var seconds = Number(lifetime ? lifetime.getAttribute('content') : 3600) || 3600;
    setInterval(function () {
        if (!document.hidden) refreshToken().catch(function () {});
    }, Math.max(1, Math.min(1800, seconds / 2)) * 1000);
})();
