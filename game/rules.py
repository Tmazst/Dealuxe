
'''
[**UPDATE 27 December 2025**]
[**THE 4 CONDITIONS OF WINNING THE DEALUXE GAME**]
Note: The DEALUXE WIN, ECSAPE WIN, TRAIL WIN conditions are are under the normal and main; HAND <= 3 rule

1. DEALUXE WIN:
An attacker should always win after a failed defense from the opponent.
e.g. If an attacker's hand has [2,3,8]. When they attack with the [8] they dont automatically
win, the defender has to fail and draw a card first then the attacker wins. The drawing of the
card tells us that the defender did not have defending cards before they draw or they mistakely
draw when they were not supposed to. Drawing of the cards triggers a win for attacker. its a DEALUXE WIN.

2. ESCAPE WIN:
A win for defender should take place immediately when the successfully defended their position.
e.g. attacker played [J], defender's hand[3,8,A]. If defender defends succefully with [3,8] that 
automatically triggers a win (without any drawing of card). its an ESCAPE WIN.

3. CRAZY ESCAPE WIN:
If defender draws a card (failed to defend) while attacker has count=0 (Left with no card after an attack).
It means the attacker was left with an attacking card(4-13) e.g. a [Q],before the latest attack.
But if the defender defended well e.g. with [7,5] the game would proceed normally.

4. TRAIL WIN (RULE #8 WIN):
When the attacker is left with winning cards i.e. any of [A,2,3] but they are more 3 lets with 5 cards [A,2,2,3,A].
The attacker must drop each card until they reach 3. But during trail they attacker should pray that 
defender must not have any of the cards they at a time, if the defender have the card dropped in their HAND, 
they are allowed to crash the trail. The will proceed normally after a successful crash.

Note: DEALUXE WIN, CRAZY ESCAPE WIN, TRAIL WIN are triggered by defender_draw method and ESCAPE WIN is triggered by defence method.
'''

def is_low_only(player):
    return all(card.value in (1, 2, 3) for card in player.hand)

def has_attack_card(player):
    return any(4 <= card.value <= 13 for card in player.hand)

def is_winner(player):
    return len(player.hand) <= 3 and is_low_only(player)

