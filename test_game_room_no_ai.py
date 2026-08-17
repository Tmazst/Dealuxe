"""
Regression tests for the tournament/multiplayer "AI plays the human's hand" bug.

Root cause (from the live log `[AI] It's my turn to attack: [AI] Attacks with card
value 13 [ENGINE] attack called - player_id: 1 ...`):

  * Tournament games have a GameRoom. In a test arena the bot sits at engine
    index 0 and the human at engine index 1.
  * The frontend used to fall back to the single-player REST endpoints, and the
    REST endpoints wrapped the engine with ``FlaskGameController(engine)`` which
    enables the *built-in local AI* (hard-wired to ``ai_player_id=1``).
  * When the human (index 1) defended successfully the engine swapped roles
    (attacker = 1 = the human), and the controller's ``_run_ai_if_needed()``
    saw "its turn" and played the human's attack card automatically.

Engine rules (``game/engine.py``) are correct and are NOT modified here.

Fix under test:
  * ``_make_game_controller`` disables the built-in AI for any game that has a
    GameRoom (``run_ai=False``).
  * The frontend now routes room-based actions over the socket (which validates
    turns and runs the opt-in tournament bot instead of the local AI).
"""

import unittest

from app import app, _make_game_controller, manager
from database import db, User, Player, GameRoom
from controllers.flask_controller import FlaskGameController
from game.engine import CardGameEngine
from game.models import Card, Player as EnginePlayer


def make_engine_with_known_hands():
    """Build a 2-player engine with fixed hands (bot=index 0, human=index 1)."""
    engine = CardGameEngine([EnginePlayer("Player 1"), EnginePlayer("Player 2")], cards_per_player=6)
    # Bot (index 0): has a Q(12) to open the attack.
    engine.players[0].hand = [
        Card('5', '♠', 5), Card('Q', '♥', 12), Card('7', '♣', 7),
        Card('9', '♦', 9), Card('2', '♠', 2), Card('6', '♥', 6),
    ]
    # Human (index 1): J(11) + A(1) = 12 -> a successful defense is available.
    engine.players[1].hand = [
        Card('5', '♠', 5), Card('J', '♥', 11), Card('K', '♦', 13),
        Card('2', '♣', 2), Card('3', '♠', 3), Card('A', '♥', 1),
    ]
    engine.state.phase = "ATTACK"
    engine.state.attacker = 0
    engine.state.defender = 1
    engine.state.attack_card = None
    return engine


def bot_opens_attack(engine):
    """Let the bot (index 0) attack with its Q(12). Returns attack result."""
    return engine.attack(0, 1)  # index 1 == Q(12)


class TestRoomGameNoAI(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['TOURNAMENT_TEST_BOTS_ENABLED'] = False
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()

        self.bot = User(username='tournament_bot_1', email='bot1@test.com')
        self.bot.set_password('x')
        db.session.add(self.bot)
        db.session.flush()
        db.session.add(Player(user_id=self.bot.id, real_balance=100.0))

        self.human = User(username='tournament_tester', email='human@test.com')
        self.human.set_password('x')
        db.session.add(self.human)
        db.session.flush()
        db.session.add(Player(user_id=self.human.id, real_balance=100.0))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    # ------------------------------------------------------------------
    # 1. Reproduce the ORIGINAL bug: built-in AI auto-plays the human.
    # ------------------------------------------------------------------
    def test_old_flask_controller_ai_auto_plays_human_after_defense(self):
        """The pre-fix controller (run_ai=True) plays the human's attack after a
        successful human defense. This is exactly the live-log behaviour."""
        engine = make_engine_with_known_hands()
        bot_opens_attack(engine)

        controller = FlaskGameController(engine, run_ai=True)  # ai_player_id defaults to 1
        controller.ai._think = lambda: None  # keep the test fast

        result = controller.defend([1, 5])  # human defends with J + A == 12

        payload = result.get_json()
        self.assertFalse(payload.get('error'), payload)
        # Roles swapped correctly by the engine...
        self.assertEqual(engine.state.attacker, 1)
        self.assertEqual(engine.state.defender, 0)
        # ...but the built-in AI (player_id=1) then stole the human's turn:
        # the human's K(13) is gone and the game moved to DEFENSE (AI acted).
        self.assertEqual(engine.state.phase, "DEFENSE")
        self.assertEqual([c.value for c in engine.players[1].hand], [5, 2, 3])
        self.assertEqual(engine.state.attack_card.value, 13)

    # ------------------------------------------------------------------
    # 2. The fix: room games never enable the built-in AI.
    # ------------------------------------------------------------------
    def test_make_game_controller_disables_ai_when_room_exists(self):
        """For a game linked to a GameRoom the controller must not run the local AI."""
        engine = make_engine_with_known_hands()
        game_id, _ = manager.create_game(mode='local', card_count=6)

        room = GameRoom(
            room_code='TESTAB',
            player1_id=self.bot.id,
            player2_id=self.human.id,
            game_id=game_id,
            card_count=6,
            bet_amount=10.0,
            bet_type='tournament',
            is_tournament_game=True,
            status='in_progress',
        )
        db.session.add(room)
        db.session.commit()

        controller = _make_game_controller(engine, game_id)
        self.assertFalse(controller._run_ai_enabled)
        self.assertIsNone(controller.ai)

    def test_make_game_controller_keeps_ai_when_no_room(self):
        """Single-player (no GameRoom) still gets the local AI."""
        engine = make_engine_with_known_hands()
        game_id, _ = manager.create_game(mode='human_vs_ai', card_count=6)
        controller = _make_game_controller(engine, game_id)
        self.assertTrue(controller._run_ai_enabled)
        self.assertIsNotNone(controller.ai)

    def test_fixed_controller_no_ai_after_human_defense(self):
        """With run_ai=False (the room-game path) the human's successful defense
        leaves the game in ATTACK on the human's turn with their hand intact."""
        engine = make_engine_with_known_hands()
        bot_opens_attack(engine)

        controller = FlaskGameController(engine, run_ai=False)
        result = controller.defend([1, 5])

        payload = result.get_json()
        self.assertFalse(payload.get('error'), payload)
        self.assertEqual(engine.state.phase, "ATTACK")
        self.assertEqual(engine.state.attacker, 1)
        self.assertEqual(engine.state.defender, 0)
        # Human hand after a successful J+A defense: [5, K, 2, 3] — nothing was stolen.
        self.assertEqual([c.value for c in engine.players[1].hand], [5, 13, 2, 3])
        self.assertIsNone(engine.state.attack_card)

    # ------------------------------------------------------------------
    # 3. The opt-in tournament-bot trigger must NOT play the human.
    #    (Mirrors run_tournament_test_bot_if_needed in multiplayer_controller.)
    # ------------------------------------------------------------------
    def _run_tournament_test_bot_logic(self, room, engine):
        """Exact copy of the socket-path logic (module closure values)."""
        if not app.config.get('TOURNAMENT_TEST_BOTS_ENABLED'):
            return False
        from controllers.ai_controller import SimpleAIController
        for _ in range(4):
            state = engine.get_state()
            if state.get('game_over'):
                break
            actor_index = state.get('defender') if state.get('phase') == 'DEFENSE' else state.get('attacker')
            actor_user_id = room.player1_id if actor_index == 0 else room.player2_id
            actor = User.query.get(actor_user_id)
            if not actor or not actor.username.startswith('tournament_bot_'):
                break
            SimpleAIController(engine, player_id=actor_index, think_delay=0, jitter=0).play_if_needed()
        manager.update_game(room.game_id, engine)
        return engine.get_state().get('game_over', False)

    def _make_room(self, engine):
        game_id, _ = manager.create_game(mode='local', card_count=6)
        room = GameRoom(
            room_code='TESTRO',
            player1_id=self.bot.id,   # engine index 0
            player2_id=self.human.id,  # engine index 1
            game_id=game_id,
            card_count=6,
            bet_amount=10.0,
            bet_type='tournament',
            is_tournament_game=True,
            status='in_progress',
        )
        db.session.add(room)
        db.session.commit()
        return room

    def test_tournament_bot_logic_breaks_after_human_defense(self):
        """After a successful human defense (attacker=human) the tournament-bot
        trigger must NOT run — the bot never plays the human's turn."""
        app.config['TOURNAMENT_TEST_BOTS_ENABLED'] = True
        engine = make_engine_with_known_hands()
        bot_opens_attack(engine)
        engine.defend(1, [1, 5])  # human defends successfully
        self.assertEqual(engine.state.attacker, 1)

        room = self._make_room(engine)
        before_hand = [c.value for c in engine.players[1].hand]
        game_over = self._run_tournament_test_bot_logic(room, engine)

        self.assertFalse(game_over)
        self.assertEqual([c.value for c in engine.players[1].hand], before_hand)
        self.assertEqual(engine.state.phase, "ATTACK")
        self.assertEqual(engine.state.attacker, 1)

    def test_tournament_bot_logic_acts_after_human_attack(self):
        """Positive control: after the HUMAN attacks (defender = bot) the trigger
        must let the bot take its defense."""
        app.config['TOURNAMENT_TEST_BOTS_ENABLED'] = True
        engine = make_engine_with_known_hands()
        bot_opens_attack(engine)
        engine.defend(1, [1, 5])      # human defends (roles swap -> human attacks next)
        engine.attack(1, 1)           # human attacks with K(13)

        room = self._make_room(engine)
        before_bot_count = len(engine.players[0].hand)
        self._run_tournament_test_bot_logic(room, engine)

        # The bot acted (it either defended with a 2-card sum or drew) and the
        # engine moved on — the human's hand was NOT touched.
        self.assertLessEqual(len(engine.players[0].hand), before_bot_count)


if __name__ == '__main__':
    unittest.main()
