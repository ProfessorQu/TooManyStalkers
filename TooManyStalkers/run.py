import sc2
import sys
from __init__ import run_ladder_game
from sc2 import Race, Difficulty
from sc2.player import Bot, Computer, Human, AIBuild
"""
Difficulty:
VeryEasy,
Easy,
Medium,
MediumHard,
Hard,
Harder,
VeryHard,
CheatVision,
CheatMoney,
CheatInsane

Player:
Participant,
Computer,
Observer

AIBuild:
RandomBuild,
Rush,
Timing,
Power,
Macro,
Air
"""

import argparse

# Load bot
from bot import TooManyStalkersBot

bot = Bot(Race.Protoss, TooManyStalkersBot())
computer = Computer(Race.Zerg, Difficulty.Medium, AIBuild.Power)
human = Human(Race.Zerg)

# Start game
if __name__ == "__main__":
    if "--LadderServer" in sys.argv:
        # Ladder game started by LadderManager
        print("Starting ladder game...")
        result, opponentid = run_ladder_game(bot)
        print(result, " against opponent ", opponentid)
    else:
        # Parse arguments
        parser = argparse.ArgumentParser()
        parser.add_argument('--RealTime', action='store_true',
                            help='Real time flag')
        args = parser.parse_args()

        # Set some variables
        realtime = args.RealTime
        speed = "normal" if realtime else "fast"

        # Local game
        print(f"Starting local game at {speed} speed...")
        sc2.run_game(sc2.maps.get("DeathAura506"),
                     [bot, computer], realtime=realtime)
