from sc2 import run_game, maps, Race, Difficulty
from sc2.player import Bot, Computer
from bot import QBot

try:
    run_game(maps.get("Abyssal Reef LE"), [
        Bot(Race.Protoss, QBot()),
        Computer(Race.Zerg, Difficulty.Medium)
    ], realtime=True)
except ValueError:
    print(f"Game ended.")
