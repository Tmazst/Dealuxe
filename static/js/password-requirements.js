/* Live password-strength requirements shared by registration and recovery. */
(function () {
    'use strict';

    function checks(password) {
        return {
            length: password.length >= 8,
            lower: /[a-z]/.test(password),
            upper: /[A-Z]/.test(password),
            number: /[0-9]/.test(password),
            special: /[^A-Za-z0-9\s]/.test(password)
        };
    }

    function setup(container) {
        var input = container.querySelector('[data-password-input]');
        if (!input) return;
        var form = input.closest('form');
        var rules = container.querySelectorAll('[data-password-rule]');

        function update() {
            var result = checks(input.value);
            var valid = true;
            rules.forEach(function (rule) {
                var passed = result[rule.dataset.passwordRule];
                rule.classList.toggle('is-met', passed);
                rule.classList.toggle('is-unmet', !passed);
                rule.querySelector('[data-password-icon]').textContent = passed ? '✓' : '○';
                valid = valid && passed;
            });
            input.setCustomValidity(valid ? '' : 'Please meet all password requirements.');
            return valid;
        }

        input.addEventListener('input', update);
        input.addEventListener('blur', update);
        if (form) {
            form.addEventListener('submit', function (event) {
                if (!update()) {
                    event.preventDefault();
                    input.focus();
                }
            });
        }
        update();
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-password-checker]').forEach(setup);
    });
}());
