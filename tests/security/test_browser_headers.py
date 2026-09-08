import json
import os
from pathlib import Path
import re
import tempfile
import unittest

from flask import Flask, make_response

from config import build_runtime_security_config
from security import init_security_scaffold


class BrowserSecurityHeaderTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix='dealuxe-browser-security-')
        self.audit_path = os.path.join(self.temp_dir.name, 'security.jsonl')

    def tearDown(self):
        self.temp_dir.cleanup()

    def _app(self, **overrides):
        environ = {
            'ENV': 'test',
            'FLASK_SECRET_KEY': 'browser-security-test-secret',
            'REQUEST_SECURITY_MODE': 'off',
            'CSRF_SECURITY_MODE': 'off',
            'SESSION_ROTATION_MODE': 'off',
            'RATE_LIMIT_MODE': 'off',
            'SECURITY_AUDIT_MODE': 'monitor',
            'SECURITY_AUDIT_FILE': self.audit_path,
            'BROWSER_SECURITY_HEADERS_MODE': 'pilot',
            'CSP_SECURITY_MODE': 'monitor',
            **overrides,
        }
        app = Flask(__name__, static_folder=None)
        app.config.update(build_runtime_security_config(environ))
        init_security_scaffold(app)

        @app.get('/')
        def index():
            return '<!doctype html><title>Safe</title>'

        return app

    def _records(self):
        if not os.path.exists(self.audit_path):
            return []
        with open(self.audit_path, 'r', encoding='utf-8') as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def test_pilot_headers_and_report_only_csp_are_enabled_by_default(self):
        response = self._app().test_client().get('/')

        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response.headers['X-Frame-Options'], 'SAMEORIGIN')
        self.assertEqual(
            response.headers['Referrer-Policy'],
            'strict-origin-when-cross-origin',
        )
        self.assertIn('camera=()', response.headers['Permissions-Policy'])
        self.assertEqual(response.headers['X-XSS-Protection'], '0')
        self.assertNotIn('Strict-Transport-Security', response.headers)
        self.assertNotIn('Content-Security-Policy', response.headers)
        policy = response.headers['Content-Security-Policy-Report-Only']
        self.assertIn("default-src 'self'", policy)
        self.assertIn("object-src 'none'", policy)
        self.assertIn("frame-ancestors 'self'", policy)
        self.assertIn('https://code.jquery.com', policy)
        self.assertIn('https://fonts.googleapis.com', policy)
        self.assertIn('report-to csp-endpoint', policy)
        self.assertEqual(
            response.headers['Reporting-Endpoints'],
            'csp-endpoint="/api/security/csp-report"',
        )

    def test_policy_covers_every_external_origin_used_by_templates(self):
        policy = self._app().test_client().get('/').headers[
            'Content-Security-Policy-Report-Only'
        ]
        project_root = Path(__file__).resolve().parents[2]
        template_origins = set()
        for directory in (
            'templates', 'admin/templates', 'user/templates',
            'hybrid/templates', 'pricing/templates',
            'livescores_fixtures_updates',
        ):
            for template in (project_root / directory).glob('*.html'):
                template_origins.update(re.findall(
                    r'https://[A-Za-z0-9.-]+',
                    template.read_text(encoding='utf-8'),
                ))

        self.assertEqual(
            template_origins,
            {
                'https://cdnjs.cloudflare.com',
                'https://code.jquery.com',
                'https://fonts.googleapis.com',
            },
        )
        for origin in template_origins:
            self.assertIn(origin, policy)

    def test_off_modes_remove_application_headers_and_report_route(self):
        app = self._app(
            BROWSER_SECURITY_HEADERS_MODE='off',
            CSP_SECURITY_MODE='off',
        )
        response = app.test_client().get('/')

        for header in (
            'X-Content-Type-Options',
            'X-Frame-Options',
            'Referrer-Policy',
            'Permissions-Policy',
            'Strict-Transport-Security',
            'Content-Security-Policy',
            'Content-Security-Policy-Report-Only',
            'Reporting-Endpoints',
        ):
            self.assertNotIn(header, response.headers)
        self.assertEqual(
            app.test_client().post('/api/security/csp-report').status_code,
            404,
        )

    def test_enforce_uses_active_csp_and_https_only_hsts(self):
        app = self._app(
            BROWSER_SECURITY_HEADERS_MODE='enforce',
            BROWSER_HSTS_INCLUDE_SUBDOMAINS='true',
            CSP_SECURITY_MODE='enforce',
        )
        client = app.test_client()

        insecure = client.get('/', base_url='http://localhost')
        secure = client.get('/', base_url='https://localhost')

        self.assertNotIn('Strict-Transport-Security', insecure.headers)
        self.assertEqual(
            secure.headers['Strict-Transport-Security'],
            'max-age=31536000; includeSubDomains',
        )
        self.assertIn('Content-Security-Policy', secure.headers)
        self.assertNotIn('Content-Security-Policy-Report-Only', secure.headers)

    def test_individual_switches_do_not_disable_remaining_headers(self):
        app = self._app(
            BROWSER_X_FRAME_OPTIONS_ENABLED='false',
            BROWSER_X_CONTENT_TYPE_OPTIONS_ENABLED='false',
            BROWSER_REFERRER_POLICY_ENABLED='false',
            BROWSER_PERMISSIONS_POLICY_ENABLED='false',
        )
        response = app.test_client().get('/')

        self.assertNotIn('X-Frame-Options', response.headers)
        self.assertNotIn('X-Content-Type-Options', response.headers)
        self.assertNotIn('Referrer-Policy', response.headers)
        self.assertNotIn('Permissions-Policy', response.headers)
        self.assertIn('Content-Security-Policy-Report-Only', response.headers)

    def test_route_owned_header_is_not_overwritten(self):
        app = self._app()

        @app.get('/embedded-policy')
        def embedded_policy():
            response = make_response('ok')
            response.headers['X-Frame-Options'] = 'DENY'
            return response

        response = app.test_client().get('/embedded-policy')

        self.assertEqual(response.headers['X-Frame-Options'], 'DENY')

    def test_inline_compatibility_switches_can_prepare_a_stricter_policy(self):
        response = self._app(
            CSP_SECURITY_MODE='enforce',
            CSP_ALLOW_INLINE_SCRIPTS='false',
            CSP_ALLOW_INLINE_STYLES='false',
        ).test_client().get('/')

        self.assertNotIn(
            "'unsafe-inline'",
            response.headers['Content-Security-Policy'],
        )

    def test_reporting_switch_removes_sink_and_reporting_directives_only(self):
        app = self._app(CSP_REPORTING_ENABLED='false')
        client = app.test_client()
        response = client.get('/')
        policy = response.headers['Content-Security-Policy-Report-Only']

        self.assertNotIn('report-uri', policy)
        self.assertNotIn('report-to', policy)
        self.assertNotIn('Reporting-Endpoints', response.headers)
        self.assertEqual(client.post('/api/security/csp-report').status_code, 404)

    def test_csp_report_bypasses_provenance_and_csrf_but_logs_no_urls(self):
        app = self._app(
            REQUEST_SECURITY_MODE='enforce',
            REQUEST_SECURITY_TRUSTED_ORIGINS='http://localhost',
            CSRF_SECURITY_MODE='enforce',
        )
        payload = {
            'csp-report': {
                'document-uri': 'https://app.example/account?token=private-token',
                'blocked-uri': 'https://attacker.example/user@example.test',
                'source-file': 'https://app.example/private-script.js',
                'script-sample': 'password=private-password',
                'effective-directive': 'script-src-elem',
                'disposition': 'report',
            }
        }

        response = app.test_client().post(
            '/api/security/csp-report',
            data=json.dumps(payload),
            content_type='application/csp-report',
        )
        rendered = json.dumps(self._records())

        self.assertEqual(response.status_code, 204)
        self.assertIn('csp_violation', rendered)
        self.assertIn('script-src-elem', rendered)
        for private_value in (
            'app.example',
            'attacker.example',
            'user@example.test',
            'private-token',
            'private-password',
        ):
            self.assertNotIn(private_value, rendered)

    def test_invalid_and_oversized_csp_reports_fail_safely(self):
        app = self._app(CSP_MAX_REPORT_BYTES='128')
        client = app.test_client()

        invalid = client.post(
            '/api/security/csp-report',
            data='{not-json',
            content_type='application/csp-report',
        )
        oversized = client.post(
            '/api/security/csp-report',
            data='x' * 129,
            content_type='application/csp-report',
        )

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(oversized.status_code, 413)

    def test_csp_report_sink_uses_its_own_rate_limit(self):
        app = self._app(
            RATE_LIMIT_MODE='enforce',
            RATE_LIMIT_CSP_REPORT_ATTEMPTS='1',
            RATE_LIMIT_CSP_REPORT_WINDOW_SECONDS='60',
        )
        client = app.test_client()
        payload = json.dumps({
            'csp-report': {'effective-directive': 'script-src-elem'}
        })

        first = client.post(
            '/api/security/csp-report',
            data=payload,
            content_type='application/csp-report',
        )
        second = client.post(
            '/api/security/csp-report',
            data=payload,
            content_type='application/csp-report',
        )

        self.assertEqual(first.status_code, 204)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.get_json()['code'], 'rate_limited')


if __name__ == '__main__':
    unittest.main()
