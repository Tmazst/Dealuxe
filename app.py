try:
    # Optional: if running under gevent, patch the stdlib to be cooperative.
    # Doing this before other imports is safest. Wrapped in try/except so
    # the app still runs when gevent isn't installed locally.
    from gevent import monkey
    monkey.patch_all()
    print("[APP] gevent monkey patched")
except Exception:
    pass

from flask import Flask, render_template, request, jsonify, session

from flask_socketio import SocketIO
from game.manager_redis import GameManager
from controllers.flask_controller import FlaskGameController
from controllers.session_controller import session_bp
from controllers.auth_controller import auth_bp
from Forms import  *
from database import db, init_db
from database import Player
from werkzeug.middleware.proxy_fix import ProxyFix
import os

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1,x_proto=1)

app.config['SECRET_KEY'] = 'fght6hg234g5f6g7h8j9o0p'

# -----------------------------
# SOCKETIO INITIALIZATION
# -----------------------------

# local should use threading async mode
if os.environ.get("ENV") == "development":
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
else:
    socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode="gevent",
        message_queue="redis://127.0.0.1:6379/0",  # hardcoded Redis
        logger=True,
        engineio_logger=True
    )

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

# -----------------------------
# GAME MANAGER (GLOBAL)
# -----------------------------

manager = GameManager()

# -----------------------------
# MULTIPLAYER SETUP
# -----------------------------

from controllers.multiplayer_controller import init_multiplayer_events
init_multiplayer_events(socketio, manager, app)

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

    # No logged-in user: fall back to demo/in-memory player
    try:
        from models.player import get_or_create_demo_player
        demo = get_or_create_demo_player()
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
    return render_template("game.html",form=form)

@app.route("/get_player_fake_balance")
def get_balance():
    fake_bal = get_player_fake_balance()
    return jsonify({"player_fake_bal":fake_bal})

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
    return render_template("game_multiplayer.html", room_code=room_code)


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
    # engine.players is a list of Player objects; convert to JSON-serializable dicts
    players = []
    for i, p in enumerate(engine.players):
        players.append({
            "id": i,
            "name": p.name,
            "hand_count": len(p.hand),
            "hand": [str(c) for c in p.hand]
        })

    print(f"[APP] Player details for game {game_id}: {len(players)} players")
    return jsonify({"players": players,"my_player": players[0] if players else None})


@app.route("/api/game/<game_id>/state")
def game_state(game_id):
    engine = manager.get_game(game_id)
    return jsonify(engine.get_state())


@app.route("/api/game/<game_id>/start", methods=["POST"])
def start_turn(game_id):
    engine = manager.get_game(game_id)
    controller = FlaskGameController(engine)

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
    controller = FlaskGameController(engine)

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
    controller = FlaskGameController(engine)
    
    i1 = int(request.json["i1"])
    i2 = int(request.json["i2"])

    result = controller.defend(i1, i2)
    # Persist change for Redis-backed manager
    try:
        manager.update_game(game_id, engine)
    except Exception:
        pass

    return result


@app.route("/api/game/<game_id>/draw", methods=["POST"])
def draw(game_id):
    engine = manager.get_game(game_id)
    controller = FlaskGameController(engine)

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
    controller = FlaskGameController(engine)

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
    controller = FlaskGameController(engine)

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
    controller = FlaskGameController(engine)

    return controller.leaderboard()


if __name__ == "__main__":
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)
