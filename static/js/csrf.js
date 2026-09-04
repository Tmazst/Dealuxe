(function () {
    'use strict';

    var originalFetch = window.fetch.bind(window);
    var unsafeMethods = { POST: true, PUT: true, PATCH: true, DELETE: true };

    function token() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    window.fetch = function (input, init) {
        var options = Object.assign({}, init || {});
        var requestMethod = input instanceof Request ? input.method : 'GET';
        var method = String(options.method || requestMethod || 'GET').toUpperCase();
        var requestUrl = input instanceof Request ? input.url : String(input);
        var target = new URL(requestUrl, window.location.href);

        if (unsafeMethods[method] && target.origin === window.location.origin) {
            var headers = new Headers(
                options.headers || (input instanceof Request ? input.headers : undefined)
            );
            var csrfToken = token();
            if (csrfToken && !headers.has('X-CSRFToken')) {
                headers.set('X-CSRFToken', csrfToken);
            }
            options.headers = headers;
        }
        return originalFetch(input, options);
    };

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('form').forEach(function (form) {
            var method = String(form.getAttribute('method') || 'GET').toUpperCase();
            if (!unsafeMethods[method] || form.querySelector('input[name="csrf_token"]')) {
                return;
            }
            var csrfToken = token();
            if (!csrfToken) return;
            var field = document.createElement('input');
            field.type = 'hidden';
            field.name = 'csrf_token';
            field.value = csrfToken;
            form.appendChild(field);
        });
    });
})();
