from game.engine import CardGameEngine
from game.models import Player
from controllers.cli_controller import CLIController

players = [Player("Player 0"), Player("Player 1")]
engine = CardGameEngine(players)

cli = CLIController(engine)
cli.run()
