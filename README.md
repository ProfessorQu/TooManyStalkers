# TooManyStalkers
This is a [Starcraft 2](https://starcraft2.com/en-us/) bot that I made in one week and then refined.

Did you ever think: "I wish there were more Stalkers"? Well, now there's too many!

[The Github repository](https://github.com/ProfessorQu/TooManyStalkers).

I have published the [TooManyStalkers](https://sc2ai.net/bots/294/) bot on [sc2aiarena](https://sc2ai.net).

Made with the [python-sc2 library](https://github.com/BurnySc2/python-sc2), maintained by [BurnsySc2](https://github.com/BurnySc2/)

## Strategy
### Stalker Production
As soon as a Gateway is finished, it will train 1 Zealot. Which will be complete the wall-off.
Also what will happen when a Gateway is finished is that Assimilators will be built to be able to build Stalkers.
After the 1 Zealot it will just train as many Stalkers as it can (once the Cybernetics Core is completed).
And as soon as the Warpgate research is finished it will warp in Stalkers: defensive Stalkers near the main base and offensive Stalkers at the proxy Pylon.
The Nexus' Chronoboost is also preserved to research Warpgates quicker.

### Defense
The bot walls off the entrance to the main base with 2 Gateways and 1 Zealot.
After doing so it will put a maximum of 3 Photon Cannons at the back of the main base.
The for every 6 attacking Stalkers there will be 1 defensive Stalker. Defensive Stalkers chase any opponents away from the main base.
The defensive Stalkers, when they have no target, will also sit at the back of the main base.

### Offense
When the Warpgate research is a quarter done (25%) a Probe will be sent out to build a proxy Pylon.
Then Stalkers will be sent to guard the proxy until it's time to attack.
And it's time to attack every 5 minutes.

### Strenghts
Stalkers are actually pretty good units. If it's the only unit you have then perhaps not, but it's a solid all around unit:
They are quite fast,
And they have ranged attacks, so they can attack air units.

### Weaknesses
Any counter to Stalkers really: because the bot only trains Stalkers (and 1 Zealot) any units that counter it will absolutely destroy the bot's army.
Stalker counters include: Immortals, Marauders, Siege Tanks, Roaches and Hydralisks.
