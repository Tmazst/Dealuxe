def is_low_only(player):
    return all(card.value in (1, 2, 3) for card in player.hand)

def has_attack_card(player):
    return any(4 <= card.value <= 13 for card in player.hand)

def is_winner(player):
    return len(player.hand) <= 3 and is_low_only(player)
