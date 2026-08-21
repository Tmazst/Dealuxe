try:
    # Optional: if running under gevent, patch the stdlib to be cooperative.
    # Doing this before other imports is safest. Wrapped in try/except so
    # the app still runs when gevent isn't installed locally.
    from gevent import monkey
    monkey.patch_all()
    print("[APP] gevent monkey patched")
except Exception:
    pass

# Load environment variables from the .env file (python-dotenv). This must run
# before any module reads os.environ (e.g. config.PaymentConfig).
#
# IMPORTANT: the .env file is loaded with an ABSOLUTE path (so the app behaves
# the same regardless of the process working directory) and with override=True
# (so values in .env are authoritative). Without override, a stale process- or
# OS-level variable would silently beat .env -- e.g. an old
# `MOJAPOS_MOCK_MODE=true` kept the entire payment system on the mock/sandbox
# path even after .env was switched to false.
import os

try:
    from dotenv import load_dotenv
    load_dotenv(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'),
        override=True,
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
from Forms import  *
from database import db, init_db, Tournament, User
from database import Player
from werkzeug.middleware.proxy_fix import ProxyFix
from jinja2 import ChoiceLoader, FileSystemLoader
from config import PaymentConfig
import os

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1,x_proto=1)

# allow Flask to load spectator templates from the livescores_fixtures_updates folder
app.jinja_loader = ChoiceLoader([
    app.jinja_loader,
    FileSystemLoader(os.path.join(app.root_path, 'livescores_fixtures_updates')),
])

app.config['SECRET_KEY'] = 'fght6hg234g5f6g7h8j9o0p'
app.config['TOURNAMENT_TEST_BOTS_ENABLED'] = os.environ.get(
    'TOURNAMENT_TEST_BOTS_ENABLED', 'false'
).lower() in {'1', 'true', 'yes'}

# -----------------------------
# PAYMENT (MojaPOS) CONFIGURATION
# -----------------------------

app.config.from_object(PaymentConfig)

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
if os.environ.get("ENV") == "development":
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
    app.config['SOCKET_TRANSPORTS'] = ['websocket', 'polling']
else:
    socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode="gevent",
        message_queue="redis://127.0.0.1:6379/0",  # hardcoded Redis
        logger=True,
        engineio_logger=True
    )
    app.config['SOCKET_TRANSPORTS'] = ['websocket', 'polling']

# socketio = SocketIO(app, cors_allowed_origins="*",async_mode='threading')

# -----------------------------
# DATABASE INITIALIZATION
# -----------------------------

init_db(app)

# -----------------------------
# REGISTER BLUEPRINTS
# -----------------------------

app.register_blueprint(session_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(tournament_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(user_bp)

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

manager = GameManager()
app.extensions['game_manager'] = manager

# -----------------------------
# MULTIPLAYER SETUP
# -----------------------------

from controllers.multiplayer_controller import init_multiplayer_events
init_multiplayer_events(socketio, manager, app)
init_tournament_events(socketio, app)

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
def get_player_fake_balance():
    # Prefer logged-in DB player
    from database import get_player_by_user_id, db as _db
    user_id = session.get('user_id')
    if user_id:
        player = get_player_by_user_id(user_id)
        if player:
            if not player.is_fake_cash_valid() or player.fake_balance <= 0:
                player.award_free_cash()
                _db.session.commit()
            print("[APP] player current balance: ", player.fake_balance)
            return player.fake_balance

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
    return jsonify({"player_fake_bal":fake_bal})

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
            # Auto-award free cash if needed
            if not player.is_fake_cash_valid() or player.fake_balance <= 0:
                player.award_free_cash()
                db.session.commit()
            user_balance = player.fake_balance
    
    return render_template("lobby.html", user_balance=user_balance)


@app.route("/game/<room_code>")
def multiplayer_game(room_code):
    return render_template(
        "game.html",
        form=GameStartForm(),
        room_code=room_code,
        tournament_room_code=room_code,
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
from database import (
    Tournament,
    TournamentParticipant,
    TournamentPrizePool,
    Player,
    WithdrawalRequest,
    Transaction,
)


@app.route('/api/payment/callback', methods=['POST'])
def payment_callback():
    """
    Receive and verify a callback/webhook from MojaPOS.

    Real MojaPOS payload uses camelCase:
    {
        'transactionId': '52346890-...',      # gateway transaction id
        'status': 'PENDING'|'COMPLETED'|'FAILED',
        'amount': 1.0,
        'currency': 'SZL',
        'providerReference': 'b0b88df5-...',
        'metadata': {
            'externalId': '...',              # OUR reference (external_ref_id)
            'transaction_type': 'tournament_entry'|'prize_payout'|'wallet_topup',
            ...
        }
    }

    Headers: X-Signature (HMAC-SHA256) -- confirm exact webhook auth with MojaPOS.
    """
    try:
        payload = request.get_json(silent=True) or {}
        signature = request.headers.get('X-Signature')

        if not payload or not signature:
            return jsonify({'error': 'Missing payload or signature'}), 400

        # if not payment_service.verify_callback_signature(payload, signature): Temporal closed. YET to confirm if mojapos have the signature 
        #     print("[PAYMENT] Invalid callback signature - rejected")
        #     return jsonify({'error': 'Invalid signature'}), 401

        mojapos_txn_id = payload.get('transactionId') or payload.get('transaction_id')
        status = str(payload.get('status') or '').lower()
        metadata = payload.get('metadata') or {}
        transaction_type = metadata.get('transaction_type')

        # Idempotency: skip if this external transaction was already processed.
        if mojapos_txn_id:
            already = Transaction.query.filter_by(
                    description=mojapos_txn_id).first()
            if already:
                return jsonify({'status': 'received'}), 200

        # Route to the correct handler.
        if transaction_type == 'tournament_entry':
            _handle_entry_fee_callback(payload)
        elif transaction_type == 'prize_payout':
            _handle_prize_payout_callback(payload)
        elif transaction_type == 'wallet_topup':
            _handle_wallet_topup_callback(payload)
        else:
            print(f"[PAYMENT] Unknown transaction type: {transaction_type}")
            return jsonify({'error': 'Unknown transaction type'}), 400

        return jsonify({'status': 'received'}), 200

    except Exception as e:
        print(f"[PAYMENT] Callback processing error: {str(e)}")
        return jsonify({'error': str(e)}), 500


def _handle_entry_fee_callback(payload):
    """Process a completed/failed tournament-entry payment callback."""
    from datetime import datetime as _dt
    status = str(payload.get('status') or '').lower()
    metadata = payload.get('metadata') or {}

    external_ref_id = metadata.get('externalId') or metadata.get('external_ref_id')
    legacy_txn_id = int(metadata.get('transaction_id')) if metadata.get('transaction_id') else None

    # Map back to the pending transaction. New payments are matched by the
    # strong external reference (metadata.externalId = the id sent to the
    # gateway); legacy in-flight payments carry the integer transaction_id.
    transaction = None
    if external_ref_id:
        transaction = Transaction.query.filter_by(external_ref_id=external_ref_id).first()
    elif legacy_txn_id:
        transaction = Transaction.query.get(legacy_txn_id)

    if transaction is None:
        print(f"[PAYMENT] Transaction not found for externalId={external_ref_id or legacy_txn_id}")
        return

    # The real payload only echoes metadata.externalId, so the user and the
    # tournament are derived from the transaction row (player_id/tournament_id);
    # metadata values remain as a fallback for legacy callbacks.
    user_id = None
    try:
        user_id = int(metadata.get('user_id'))
    except (TypeError, ValueError):
        user_id = None
    if user_id is None and transaction.player_id:
        player = Player.query.get(transaction.player_id)
        user_id = player.user_id if player else None
    if user_id is None:
        print("[PAYMENT] Entry callback: could not resolve user_id")
        return

    tournament = None
    if transaction.tournament_id:
        tournament = Tournament.query.get(transaction.tournament_id)
    if tournament is None and metadata.get('tournament_code'):
        tournament = Tournament.query.filter_by(
            tournament_code=metadata['tournament_code']).first()

    # Record the external transaction id for idempotency.
    transaction.description = (
        payload.get('transactionId') or payload.get('transaction_id') or transaction.description
    )

    if status == 'completed':
        if tournament:
            participant = TournamentParticipant.query.filter_by(
                tournament_id=tournament.id,
                user_id=user_id,
            ).first()
            if participant:
                participant.payment_status = 'completed'
                participant.payment_completed_at = _dt.utcnow()
                participant.transaction_id = payload.get('transactionId') or payload.get('transaction_id')
                # Our reference travels as metadata.externalId; fall back to the
                # legacy top-level `reference` field for older callbacks.
                participant.external_payment_id = (
                    metadata.get('externalId')
                    or metadata.get('external_ref_id')
                    or payload.get('reference')
                    or metadata.get('reference')
                )
                participant.status = 'registered'

                tournament.current_player_count += 1
                tournament.prize_pool_amount += tournament.entry_fee

                from controllers.tournament_controller import (
                    _emit_tournament_updated,
                    _perform_tournament_lock,
                    _tournament_room,
                )
                if socketio:
                    socketio.emit('participant_joined', {
                        'user_id': user_id,
                        'username': (User.query.get(user_id).username
                                     if User.query.get(user_id) else 'Player'),
                        'current_players': tournament.current_player_count,
                    }, room=_tournament_room(tournament.id))

                if (tournament.is_auto_lock
                        and tournament.current_player_count >= tournament.max_players):
                    # Full auto-lock bracket: lock, build the bracket, announce.
                    _perform_tournament_lock(tournament)
                else:
                    _emit_tournament_updated(tournament)
    else:
        # Refund the prepaid amount on failure.
        player = Player.query.filter_by(user_id=user_id).first()
        if player is not None and transaction.amount > 0:
            player.real_balance += transaction.amount
        participant = None
        if tournament is not None:
            participant = TournamentParticipant.query.filter_by(
                tournament_id=tournament.id,
                user_id=user_id,
            ).first()
        if participant:
            participant.payment_status = 'failed'

    db.session.commit()


def _handle_prize_payout_callback(payload):
    """Process a prize-payout callback (mark withdrawal complete/failed)."""
    from datetime import datetime as _dt
    status = str(payload.get('status') or '').lower()
    metadata = payload.get('metadata') or {}

    try:
        withdrawal_request_id = int(metadata.get('withdrawal_request_id'))
    except (TypeError, ValueError):
        print("[PAYMENT] Payout callback missing withdrawal_request_id")
        return

    withdrawal = WithdrawalRequest.query.get(withdrawal_request_id)
    if withdrawal is None:
        print(f"[PAYMENT] Withdrawal {withdrawal_request_id} not found")
        return

    withdrawal.transaction_id = payload.get('transactionId') or payload.get('transaction_id')
    if status == 'completed':
        withdrawal.status = 'completed'

        prize_pool = TournamentPrizePool.query.filter_by(
            tournament_id=withdrawal.tournament_id,
            user_id=withdrawal.user_id,
        ).first()
        if prize_pool:
            prize_pool.status = 'withdrawn'
            prize_pool.withdrawal_date = _dt.utcnow()
    else:
        withdrawal.status = 'failed'

    db.session.commit()


def _handle_wallet_topup_callback(payload):
    """Process a wallet-topup callback (credit the player's wallet).

    Real payloads only echo ``metadata.externalId`` (our external_ref_id), so the
    user is resolved from the transaction row. Payments are idempotent -- a
    retried or duplicate callback can never credit the wallet twice. Legacy
    callbacks without an external_ref_id keep the old user_id-only credit
    behaviour but are still logged for audit.
    """
    status = str(payload.get('status') or '').lower()
    amount = payload.get('amount') or 0
    metadata = payload.get('metadata') or {}
    external_ref_id = metadata.get('externalId') or metadata.get('external_ref_id')

    if status != 'completed':
        db.session.commit()
        return

    transaction = None
    if external_ref_id:
        transaction = Transaction.query.filter_by(external_ref_id=external_ref_id).first()
        if transaction is None:
            print(f"[PAYMENT] Topup callback: no pending transaction for externalId={external_ref_id} - ignoring")
            db.session.commit()
            return
        if transaction.status == 'completed':
            print(f"[PAYMENT] Topup callback: externalId={external_ref_id} already processed - ignoring duplicate")
            db.session.commit()
            return
        if transaction.status == 'failed':
            print(f"[PAYMENT] Topup callback: externalId={external_ref_id} marked failed - ignoring")
            db.session.commit()
            return

    # Resolve the user: metadata for legacy callbacks, otherwise from the
    # transaction row (player_id -> user_id).
    user_id = None
    try:
        user_id = int(metadata.get('user_id'))
    except (TypeError, ValueError):
        user_id = None
    if user_id is None and transaction is not None and transaction.player_id:
        player_row = Player.query.get(transaction.player_id)
        user_id = player_row.user_id if player_row else None
    if user_id is None:
        print("[PAYMENT] Topup callback: could not resolve user_id")
        db.session.commit()
        return

    player = Player.query.filter_by(user_id=user_id).first()
    if player is not None and amount > 0:
        balance_before = player.real_balance
        player.real_balance += amount

        if transaction is not None:
            transaction.status = 'completed'
            transaction.balance_before = balance_before
            transaction.balance_after = player.real_balance
            transaction.description = (
                payload.get('transactionId') or payload.get('transaction_id') or transaction.description
            )
        else:
            # Legacy callback without a transaction record -- log it for audit.
            from database import log_transaction, TX_WALLET_TOPUP
            log_transaction(
                player_id=player.id,
                transaction_type=TX_WALLET_TOPUP,
                amount=amount,
                balance_type='real',
                balance_before=balance_before,
                balance_after=player.real_balance,
                description='Wallet top-up (gateway callback, legacy)',
            )

    db.session.commit()


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
