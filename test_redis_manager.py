"""Opt-in Redis smoke check; automated codec coverage lives under tests/security.

This module performs no work when a test runner imports it. Run it directly
only against an explicitly isolated Redis database or test service.
"""

from game.manager_redis import GameManager


def main():
    manager = GameManager()
    game_id = None
    try:
        game_id, game_data = manager.create_game('human_vs_ai')
        engine = manager.get_game(game_id)
        attack_index = next((
            index for index, card in enumerate(engine.players[0].hand)
            if card.value >= 4
        ), None)
        if attack_index is None:
            deck_index = next(
                index for index, card in enumerate(engine.deck.cards)
                if card.value >= 4
            )
            engine.players[0].hand.append(engine.deck.cards.pop(deck_index))
            attack_index = len(engine.players[0].hand) - 1
        result = engine.attack(0, attack_index)
        if not result.get('ok'):
            raise RuntimeError('Smoke-check attack failed')
        manager.update_game(game_id, engine)
        restored = manager.get_game(game_id)
        if restored.get_state() != engine.get_state():
            raise RuntimeError('Redis game-state round trip did not match')
        print('Safe Redis game-state schema v1 smoke check passed')
    finally:
        if game_id is not None:
            manager.delete_game(game_id)


if __name__ == '__main__':
    main()
