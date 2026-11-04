import unittest

from game.engine import CardGameEngine
from game.models import Card, Player


def card(value, suit):
    ranks = {1: 'A', 2: '2', 3: '3', 4: '4', 8: '8'}
    return Card(ranks[value], suit, value)


class RuleEightTransitionTests(unittest.TestCase):
    def make_engine(self):
        return CardGameEngine([Player('attacker'), Player('defender')], cards_per_player=0)

    def test_failed_defense_enters_trail_when_attacker_has_four_low_cards(self):
        engine = self.make_engine()
        attacker, defender = engine.players
        attacker.hand = [
            card(2, '♥'), card(1, '♦'), card(1, '♣'), card(1, '♠'), card(8, '♥'),
        ]
        defender.hand = [card(4, '♦')]

        self.assertTrue(engine.attack(0, 4)['ok'])
        result = engine.defender_draw(1)

        self.assertEqual([item.value for item in attacker.hand], [2, 1, 1, 1])
        self.assertEqual(result['next_phase'], 'RULE_8')
        self.assertEqual(engine.state.phase, 'RULE_8')
        self.assertFalse(engine.state.game_over)

    def test_successful_defense_enters_trail_for_the_new_attacker(self):
        engine = self.make_engine()
        attacker, defender = engine.players
        attacker.hand = [card(4, '♥'), card(8, '♣')]
        defender.hand = [
            card(2, '♥'), card(2, '♦'), card(1, '♥'),
            card(1, '♦'), card(1, '♣'), card(2, '♣'),
        ]

        self.assertTrue(engine.attack(0, 0)['ok'])
        result = engine.defend(1, [0, 1])

        self.assertTrue(result['ok'])
        self.assertEqual(engine.state.attacker, 1)
        self.assertEqual([item.value for item in defender.hand], [1, 1, 1, 2])
        self.assertEqual(engine.state.phase, 'RULE_8')

    def test_reconcile_does_not_change_cards_outside_the_exact_trail_state(self):
        engine = self.make_engine()
        attacker = engine.players[0]
        attacker.hand = [card(2, '♥'), card(1, '♦'), card(1, '♣'), card(1, '♠')]
        engine.state.phase = 'DEFENSE'
        engine.state.attack_card = card(8, '♦')

        self.assertFalse(engine.reconcile_rule_8())
        self.assertEqual(engine.state.phase, 'DEFENSE')
        self.assertEqual([item.value for item in attacker.hand], [2, 1, 1, 1])


if __name__ == '__main__':
    unittest.main()
