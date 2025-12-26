from flask import Flask, render_template, request, jsonify

from game.manager import GameManager
from controllers.flask_controller import FlaskGameController

app = Flask(__name__)

# -----------------------------
# GAME MANAGER (GLOBAL)
# -----------------------------

manager = GameManager()

# -----------------------------
# ROUTES
# -----------------------------

@app.route("/")
def index():
    return render_template("game.html")


# -----------------------------
# GAME LIFECYCLE
# -----------------------------

@app.route("/api/game/create", methods=["POST"])
def create_game():
    mode = request.json.get("mode", "human_vs_ai")
    game_id, game_details = manager.create_game(mode)
    my_player = None
    if game_details:
        players = game_details.get("players")
        if players:
            my_player = players[0]
    if my_player:
        print(f"[APP - CREATE_GAME] My Player: {my_player.name}")
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

    print(f"[APP] Player details for game {game_id}: {players}")
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

    return result


@app.route("/api/game/<game_id>/defend", methods=["POST"])
def defend(game_id):
    engine = manager.get_game(game_id)
    controller = FlaskGameController(engine)
    
    i1 = int(request.json["i1"])
    i2 = int(request.json["i2"])

    return controller.defend(i1, i2)


@app.route("/api/game/<game_id>/draw", methods=["POST"])
def draw(game_id):
    engine = manager.get_game(game_id)
    controller = FlaskGameController(engine)

    return controller.draw()


@app.route("/api/game/<game_id>/rule8/drop", methods=["POST"])
def rule8_drop(game_id):
    engine = manager.get_game(game_id)
    controller = FlaskGameController(engine)

    value = int(request.json["value"])
    return controller.rule_8_drop(value)


@app.route("/api/game/<game_id>/rule8/crash", methods=["POST"])
def rule8_crash(game_id):
    engine = manager.get_game(game_id)
    controller = FlaskGameController(engine)

    crash = bool(request.json["crash"])
    return controller.rule_8_crash(crash)


@app.route("/api/game/<game_id>/leaderboard")
def leaderboard(game_id):
    engine = manager.get_game(game_id)
    controller = FlaskGameController(engine)

    return controller.leaderboard()


if __name__ == "__main__":
    app.run(debug=True)
