import os


# Only the non-local gevent deployment needs cooperative monkey-patching.
# Applying it during development or tests can deadlock test discovery and is
# unnecessary when Flask-SocketIO uses the threading async mode.
_early_environment = str(
    os.environ.get('APP_ENV')
    or os.environ.get('FLASK_ENV')
    or os.environ.get('ENV')
    or 'development'
).strip().lower()
if _early_environment not in {'development', 'dev', 'local', 'test', 'testing'}:
    try:
        from gevent import monkey
        monkey.patch_all()
        print("[APP] gevent monkey patched")
    except Exception:
        pass

# Load environment variables from the .env file (python-dotenv). This must run
# before any module reads os.environ (e.g. config.PaymentConfig).
#
# IMPORTANT: the .env file is loaded with an ABSOLUTE path (so the app behaves
# the same regardless of the process working directory). It never overrides
# values injected by the operating system or production service manager.
try:
    from dotenv import load_dotenv
    load_dotenv(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'),
        override=False,
    )
except Exception:
    pass

from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO
from game.manager_redis import GameManager
from controllers.flask_controller import FlaskGameController
from controllers.session_controller import session_bp
from controllers.auth_controller import auth_bp, admin_required
from controllers.tournament_controller import tournament_bp, init_tournament_events
from admin.routes import admin_bp
from user.routes import user_bp
from hybrid.routes import hybrid_bp
from pricing.routes import pricing_bp
from Forms import  *
from database import db, init_db, Tournament, User
from database import Player
from werkzeug.middleware.proxy_fix import ProxyFix
from jinja2 import ChoiceLoader, FileSystemLoader
from config import (
    PaymentConfig,
    LogConfig,
    build_pilot_economy_config,
    build_hybrid_config,
    build_openwa_scaffold_config,
    build_pricing_config,
    build_runtime_security_config,
)
from security import (
    csrf_exempt_endpoint,
    init_security_scaffold,
    machine_client_endpoint,
)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1,x_proto=1)

runtime_security = build_runtime_security_config()
app.config.update(runtime_security)
app.config.update(build_pilot_economy_config())
app.config.update(build_hybrid_config())
app.config.update(build_openwa_scaffold_config())
app.config.update(build_pricing_config())

# allow Flask to load spectator templates from the livescores_fixtures_updates folder
app.jinja_loader = ChoiceLoader([
    app.jinja_loader,
    FileSystemLoader(os.path.join(app.root_path, 'livescores_fixtures_updates')),
])

app.config['TOURNAMENT_TEST_BOTS_ENABLED'] = os.environ.get(
    'TOURNAMENT_TEST_BOTS_ENABLED', 'false'
).lower() in {'1', 'true', 'yes'}

# -----------------------------
# PAYMENT (MojaPOS) CONFIGURATION
# -----------------------------

app.config.from_object(PaymentConfig)
app.config.from_object(LogConfig)

if app.config.get('SESSION_SECRET_GENERATED'):
    print('[SECURITY] FLASK_SECRET_KEY is unset; using a temporary local-only session secret')

# -----------------------------
# BACKEND PRINT LOG CAPTURE
# (every backend print() also goes to logs/print_logs.txt, viewable in the
#  admin dashboard under "Backend Logs")
# -----------------------------

try:
    from services.log_capture import install_print_log_capture
    _print_log_path = install_print_log_capture(
        app.config.get('PRINT_LOG_FILE'),
        app.config.get('PRINT_LOG_MAX_BYTES'),
    )
    print(f"[APP] Backend print log -> {_print_log_path}")
except Exception as exc:
    print(f"[APP] Backend print-log capture disabled: {exc}")

# Startup log: show the effective MojaPOS mode so it is never ambiguous which
# payment path the server is actually using (mock vs real gateway).
if app.config.get('MOJAPOS_MOCK_MODE'):
    print("[APP] MojaPOS mode: MOCK (local wallet debit / sandbox) - real gateway is OFF")
else:
    print("[APP] MojaPOS mode: REAL gateway ENABLED (mock disabled)")

# -----------------------------
# SOCKETIO INITIALIZATION
# -----------------------------

# local should use threading async mode (polling transport — the Werkzeug dev
# server cannot upgrade websockets with the threading driver)
if app.config.get('IS_LOCAL_ENVIRONMENT'):
    socketio = SocketIO(
        app,
        cors_allowed_origins=app.config['SOCKETIO_ALLOWED_ORIGINS'],
        async_mode='threading',
    )
    app.config['SOCKET_TRANSPORTS'] = ['websocket', 'polling']
else:
    socketio = SocketIO(
        app,
        cors_allowed_origins=app.config['SOCKETIO_ALLOWED_ORIGINS'],
        async_mode="gevent",
        message_queue=app.config['REDIS_URL'],
        logger=True,
        engineio_logger=True
    )
    app.config['SOCKET_TRANSPORTS'] = ['websocket', 'polling']

# Optional UI features may publish requester-scoped refresh events without
# importing this module (which would create a circular dependency).
app.extensions['socketio'] = socketio

init_security_scaffold(app, socketio)

# socketio = SocketIO(app, cors_allowed_origins="*",async_mode='threading')

# -----------------------------
# DATABASE INITIALIZATION
# -----------------------------

init_db(app)
with app.app_context():
    from hybrid.settings import apply_persisted_settings
    from hybrid.catalog import ensure_default_caption_templates
    apply_persisted_settings(app)
    from pricing.settings import apply_persisted_pricing_settings
    apply_persisted_pricing_settings(app)
    ensure_default_caption_templates()

# -----------------------------
# REGISTER BLUEPRINTS
# -----------------------------

app.register_blueprint(session_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(tournament_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(user_bp)
app.register_blueprint(hybrid_bp)
app.register_blueprint(pricing_bp)

# Ensure the upload directory exists for user KYC / ID files
try:
    os.makedirs(
        app.config.get('UPLOAD_FOLDER') or os.path.join(app.instance_path, 'uploads'),
        exist_ok=True,
    )
except Exception as exc:
    print(f"[APP] Warning: could not create upload folder: {exc}")

# -----------------------------
# GAME MANAGER (GLOBAL)
# -----------------------------

manager = GameManager(
    redis_url=app.config['REDIS_URL'],
    security_mode=app.config['REDIS_GAME_STATE_SECURITY_MODE'],
    ttl_seconds=app.config['REDIS_GAME_STATE_TTL_SECONDS'],
    max_payload_bytes=app.config['REDIS_GAME_STATE_MAX_BYTES'],
    local_environment=app.config['IS_LOCAL_ENVIRONMENT'],
)
app.extensions['game_manager'] = manager
from hybrid.chat import build_chat_store, init_hybrid_chat_events
app.extensions['hybrid_chat_store'] = build_chat_store(manager)

# -----------------------------
# MULTIPLAYER SETUP
# -----------------------------

from controllers.multiplayer_controller import init_multiplayer_events
init_multiplayer_events(socketio, manager, app)
init_tournament_events(socketio, app)
init_hybrid_chat_events(socketio, app)

# -----------------------------
# BACKGROUND SCHEDULER
# (fires scheduled tournament starts + resolves no-show roll deadlines)
# -----------------------------

def start_background_scheduler(app, socketio):
    import threading
    import time

    def _run():
        with app.app_context():
            while True:
                try:
                    from controllers.tournament_controller import process_scheduled_events
                    process_scheduled_events()
                except Exception as exc:
                    print(f'[SCHEDULER] error: {exc}')
                try:
                    from controllers.multiplayer_controller import process_expired_room_turns
                    process_expired_room_turns(socketio, manager)
                except Exception as exc:
                    print(f'[SCHEDULER] multiplayer turn sweep error: {exc}')
                time.sleep(20)

    threading.Thread(target=_run, daemon=True).start()
    print('[APP] Background scheduler started')


start_background_scheduler(app, socketio)

#-------------------
# Routes Methods
#-------------------
def get_player_promotional_credit_balance():
    # Prefer logged-in DB player
    from database import get_player_by_user_id
    user_id = session.get('user_id')
    if user_id:
        player = get_player_by_user_id(user_id)
        if player:
            balance = (
                player.promotional_credit_balance
                if player.has_active_promotional_credits()
                else 0.0
            )
            print("[APP] player promotional credit balance: ", balance)
            return balance

    # No logged-in user: fall back to a per-browser-session practice player
    # (NOT the old shared demo player -- that meant every guest saw and spent
    # the same balance as every other guest on the server).
    try:
        from models.player import get_or_create_demo_player
        from controllers.session_controller import _get_practice_session_key
        demo = get_or_create_demo_player(_get_practice_session_key())
        # ensure demo has free cash if expired or empty
        if not getattr(demo, 'is_fake_cash_valid', lambda: False)() or getattr(demo, 'fake_balance', 0) <= 0:
            try:
                demo.award_free_cash()
            except Exception:
                pass
        print("[APP] demo player balance:", getattr(demo, 'fake_balance', 0))
        return getattr(demo, 'fake_balance', 0)
    except Exception:
        return 0


def get_player_fake_balance():
    """Deprecated compatibility alias for the legacy game client."""
    return get_player_promotional_credit_balance()

# -----------------------------
# ROUTES
# -----------------------------

@app.route("/")
def index():
    form = GameStartForm()
    return render_template("tournaments.html", form=form, is_admin=_session_is_admin())

@app.route("/get_player_fake_balance")
def get_balance():
    fake_bal = get_player_fake_balance()
    return jsonify({
        "promotional_credit_balance": fake_bal,
        "player_fake_bal": fake_bal,
    })


@app.route('/api/player/promotional-credit-balance')
def get_promotional_credit_balance():
    return jsonify({
        'promotional_credit_balance': get_player_promotional_credit_balance(),
    })

@app.route("/admin")
@admin_required
def admin_page():
    return render_template('admin.html')


@app.route("/admin/test-tournament")
@admin_required
def admin_test_tournament_page():
    """Admin-only test arena UI (create a 1 manual + 3 bot tournament)."""
    return render_template("tournament_test.html")


def _session_is_admin():
    user_id = session.get('user_id')
    if not user_id:
        return False
    user = User.query.get(user_id)
    return bool(user and (user.is_admin or user.is_super_admin))


@app.route("/lobby")
def lobby():
    """Multiplayer lobby - show user balance and available rooms"""
    from database import get_player_by_user_id, Player
    
    user_id = session.get('user_id')
    user_balance = 0
    
    if user_id:
        player = get_player_by_user_id(user_id)
        if player:
            user_balance = (
                player.promotional_credit_balance
                if player.has_active_promotional_credits()
                else 0.0
            )
    
    return render_template("lobby.html", user_balance=user_balance)


@app.route("/game/<room_code>")
def multiplayer_game(room_code):
    """Render requester-oriented matchup and tournament context for a game."""
    from database import GameRoom, TournamentBracket, TournamentMatch

    room = GameRoom.query.filter_by(room_code=room_code).first()
    requester_id = session.get('user_id')
    matchup = {
        'authorized': False,
        'my_name': 'You',
        'opponent_name': 'Opponent',
        'my_avatar_url': None,
        'opponent_avatar_url': None,
        'title': 'Game room',
        'subtitle': 'Multiplayer match',
        'round_name': None,
        'match_number': None,
        'field_size': None,
        'bracket_url': None,
        'room_code': room_code,
    }
    if room and requester_id and room.is_player_in_room(requester_id):
        requester = db.session.get(User, requester_id)
        opponent_id = room.get_opponent_id(requester_id)
        opponent = db.session.get(User, opponent_id) if opponent_id else None
        matchup.update({
            'authorized': True,
            'my_name': requester.username if requester else 'You',
            'opponent_name': opponent.username if opponent else 'Waiting for opponent',
            'my_avatar_url': (
                '/account/uploads/' + requester.profile_image_path
                if requester and requester.profile_image_path else None
            ),
            'opponent_avatar_url': (
                '/api/hybrid/game/{0}/opponent-image'.format(room_code)
                if opponent and opponent.profile_image_path else None
            ),
        })

        tournament = db.session.get(Tournament, room.tournament_id) if room.tournament_id else None
        match = (
            db.session.get(TournamentMatch, room.match_id)
            if room.match_id else
            TournamentMatch.query.filter_by(game_room_id=room.id).first()
        )
        bracket = db.session.get(TournamentBracket, match.bracket_id) if match else None
        if tournament:
            matchup.update({
                'title': tournament.tournament_name,
                'subtitle': '{0} tournament'.format(tournament.tournament_type.title()),
                'round_name': bracket.round_name if bracket else 'Tournament match',
                'match_number': bracket.match_number if bracket else None,
                'field_size': '{0}/{1} players'.format(
                    tournament.locked_player_count or tournament.current_player_count,
                    tournament.max_players,
                ),
                'bracket_url': '/tournaments/{0}/bracket'.format(tournament.id),
            })
    return render_template(
        "game.html",
        form=GameStartForm(),
        room_code=room_code,
        tournament_room_code=room_code,
        matchup=matchup,
    )


@app.route("/tournaments")
def tournaments_page():
    return render_template("tournaments.html", is_admin=_session_is_admin())


@app.route("/tournaments/<int:tournament_id>")
def tournament_waiting_room_page(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    user_id = session.get('user_id')
    user = User.query.get(user_id) if user_id else None
    is_admin = bool(user and (user.is_admin or tournament.creator_id == user_id))
    return render_template(
        "tournament_waiting_room.html",
        tournament_code=tournament.tournament_code,
        tournament_id=tournament.id,
        is_admin=is_admin,
    )


@app.route("/tournaments/<int:tournament_id>/bracket")
def tournament_bracket_page(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    
    if not tournament:
        return jsonify({"Status":f"Tournament with not found"})
    return render_template(
        "tournament_bracket.html",
        tournament_id=tournament.id,
        tournament_code=tournament.tournament_code,
        current_user_id=session.get('user_id'),
    )


@app.route("/spectators/tournaments")
def spectator_tournaments_page():
    return render_template("spectator_tournaments.html")


@app.route("/spectators/tournaments/<int:tournament_id>")
def spectator_tournament_overview_page(tournament_id):
    return render_template("spectator_tournament_overview.html")


@app.route("/spectators/tournaments/<int:tournament_id>/bracket")
def spectator_tournament_bracket_page(tournament_id):
    return render_template("spectator_tournament_bracket.html")


# -----------------------------
# PAYMENT CALLBACK (MojaPOS)
# -----------------------------

from services.payment_service import payment_service
from database import TX_ENTRY_FEE


@app.route('/api/payment/callback', methods=['POST'])
@machine_client_endpoint
@csrf_exempt_endpoint
def payment_callback():
    """Verify and atomically reconcile an enveloped MojaPOS callback."""
    import json
    from services.payment_reconciliation import (
        CallbackContractError,
        audit_reconciliation,
        parse_payment_callback,
        reconcile_payment_callback,
    )

    try:
        maximum = int(app.config.get('MOJAPOS_WEBHOOK_MAX_BYTES', 32768))
        if request.content_length is not None and request.content_length > maximum:
            return jsonify({'error': 'Payment callback is too large'}), 413
        raw_body = request.stream.read(maximum + 1)
        if len(raw_body) > maximum:
            return jsonify({'error': 'Payment callback is too large'}), 413
        try:
            payload = json.loads(raw_body.decode('utf-8'))
        except (UnicodeDecodeError, TypeError, ValueError):
            return jsonify({'error': 'Invalid payment callback'}), 400

        if app.config.get('MOJAPOS_VERIFY_WEBHOOK_SIGNATURE', False):
            signature = request.headers.get('X-Signature')
            if not signature:
                return jsonify({'error': 'Missing signature'}), 400
            if not payment_service.verify_callback_signature(payload, signature):
                print("[PAYMENT] Invalid callback signature - rejected")
                return jsonify({'error': 'Invalid signature'}), 401
        else:
            print('[PAYMENT] Webhook signature verification disabled in local/test mode')
        try:
            callback = parse_payment_callback(payload)
        except CallbackContractError:
            return jsonify({'error': 'Invalid payment callback'}), 400

        result = reconcile_payment_callback(callback)
        audit_reconciliation(result)

        # Notifications and bracket recovery are intentionally post-commit.
        # A delivery issue cannot roll back or duplicate the financial result.
        if (
            result.outcome == 'accepted'
            and result.reason == 'settled'
            and result.transaction_type == TX_ENTRY_FEE
            and result.tournament_id
        ):
            try:
                from controllers.tournament_controller import (
                    _emit_tournament_updated,
                    _recover_full_waiting_tournament,
                )
                tournament = db.session.get(Tournament, result.tournament_id)
                if tournament is not None and not _recover_full_waiting_tournament(tournament):
                    _emit_tournament_updated(tournament)
            except Exception as exc:
                db.session.rollback()
                print(f'[PAYMENT] Post-reconciliation notification error: {type(exc).__name__}')
        return jsonify({'status': 'received'}), 200

    except Exception as exc:
        db.session.rollback()
        print(f"[PAYMENT] Callback processing error: {type(exc).__name__}")
        return jsonify({'error': 'Payment callback processing failed'}), 500


def tournament_id_filter(tournament_code):
    """Return the tournament id for a code, or None."""
    if not tournament_code:
        return None
    t = Tournament.query.filter_by(tournament_code=tournament_code).first()
    return t.id if t else None


# -----------------------------
# GAME LIFECYCLE
# -----------------------------

@app.route("/api/game/create", methods=["POST"])
def create_game():
    mode = request.json.get("mode", "human_vs_ai")
    card_count = request.json.get("card_count", 6)
    game_id, game_details = manager.create_game(mode, card_count=card_count)
    my_player = None
    if game_details:
        players = game_details.get("players")
        if players:
            my_player = players[0]
    if my_player:
        print(f"[APP - CREATE_GAME] My Player: {my_player.name} with {len(my_player.hand)} cards")
        player_name = my_player.name
    else:
        player_name = None

    # return only JSON-serializable data
    return jsonify({
        "game_id": game_id,
        "mode": game_details.get("mode") if game_details else mode,
        "player_index": 0,
        "player_name": player_name,
        "my_player": {
            "name": my_player.name,
            "hand": [str(c) for c in my_player.hand]
        } if my_player else None 
    })


@app.route("/api/game/<game_id>/player_details")
def player_details(game_id):
    engine = manager.get_game(game_id)

    # Determine the requesting user's seat. Multiplayer/tournament games map
    # room.player1 -> engine index 0 and room.player2 -> engine index 1.
    # Single-player (vs AI) games have no room and default to index 0.
    player_index = 0
    user_id = session.get('user_id')
    if user_id is not None:
        try:
            from database import GameRoom
            room = GameRoom.query.filter_by(game_id=game_id).first()
            if room is not None and room.player2_id == user_id:
                player_index = 1
        except Exception:
            pass

    # engine.players is a list of Player objects; convert to JSON-serializable
    # dicts. Only expose the requesting player's full hand — the opponent's
    # hand is masked (live play uses the socket masked state, not this endpoint).
    players = []
    for i, p in enumerate(engine.players):
        players.append({
            "id": i,
            "name": p.name,
            "hand_count": len(p.hand),
            "hand": [str(c) for c in p.hand] if i == player_index else [],
        })

    my_player = players[player_index] if players else None
    print(f"[APP] Player details for game {game_id}: {len(players)} players (my index {player_index})")
    return jsonify({"players": players, "my_player": my_player})


@app.route("/api/game/<game_id>/state")
def game_state(game_id):
    engine = manager.get_game(game_id)
    return jsonify(engine.get_state())


def _make_game_controller(engine, game_id):
    """Build a FlaskGameController for a game.

    Single-player (vs AI) games have no GameRoom and rely on the controller's
    built-in local AI. Multiplayer/tournament games always have a GameRoom, and
    their opponent acts through the socket — the local AI (hard-wired to engine
    player 1) must never be allowed to play for them. Disabling it here is a
    server-side safety net for any client that falls back to these REST
    endpoints (e.g. a tournament page where the room code was not yet known).
    """
    from database import GameRoom
    room = GameRoom.query.filter_by(game_id=game_id).first()
    run_ai = room is None
    return FlaskGameController(engine, run_ai=run_ai)


@app.route("/api/game/<game_id>/start", methods=["POST"])
def start_turn(game_id):
    engine = manager.get_game(game_id)
    controller = _make_game_controller(engine, game_id)

    controller.start_turn()
    # Persist change for Redis-backed manager
    try:
        manager.update_game(game_id, engine)
    except Exception:
        pass

    return jsonify(engine.get_state())


# -----------------------------
# GAME ACTIONS.
# -----------------------------

@app.route("/api/game/<game_id>/attack", methods=["POST"])
def attack(game_id):
    engine = manager.get_game(game_id)
    controller = _make_game_controller(engine, game_id)

    index = int(request.json["index"])
    result = controller.attack(index)
    # Persist change for Redis-backed manager
    try:
        manager.update_game(game_id, engine)
    except Exception:
        pass

    return result


@app.route("/api/game/<game_id>/defend", methods=["POST"])
def defend(game_id):
    engine = manager.get_game(game_id)
    controller = _make_game_controller(engine, game_id)

    payload = request.json or {}
    card_indices = payload.get("card_indices")
    if not card_indices:
        i1 = int(payload.get("i1"))
        i2 = int(payload.get("i2"))
        card_indices = [i1, i2]
        if payload.get("i3") is not None:
            card_indices.append(int(payload.get("i3")))

    result = controller.defend(card_indices)
    # Persist change for Redis-backed manager
    try:
        manager.update_game(game_id, engine)
    except Exception:
        pass

    return result


@app.route("/api/game/<game_id>/draw", methods=["POST"])
def draw(game_id):
    engine = manager.get_game(game_id)
    controller = _make_game_controller(engine, game_id)

    result = controller.draw()
    # Persist change for Redis-backed manager
    try:
        manager.update_game(game_id, engine)
    except Exception:
        pass

    return result


@app.route("/api/game/<game_id>/rule8/drop", methods=["POST"])
def rule8_drop(game_id):
    engine = manager.get_game(game_id)
    controller = _make_game_controller(engine, game_id)

    value = int(request.json["value"])
    result = controller.rule_8_drop(value)
    # Persist change for Redis-backed manager
    try:
        manager.update_game(game_id, engine)
    except Exception:
        pass

    return result


@app.route("/api/game/<game_id>/rule8/crash", methods=["POST"])
def rule8_crash(game_id):
    engine = manager.get_game(game_id)
    controller = _make_game_controller(engine, game_id)

    crash = bool(request.json["crash"])
    result = controller.rule_8_crash(crash)
    # Persist change for Redis-backed manager
    try:
        manager.update_game(game_id, engine)
    except Exception:
        pass

    return result


@app.route("/api/game/<game_id>/leaderboard")
def leaderboard(game_id):
    engine = manager.get_game(game_id)
    controller = _make_game_controller(engine, game_id)

    return controller.leaderboard()


if __name__ == "__main__":
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)
