import sys

import sc2
from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId
from sc2.ids.buff_id import BuffId

from sc2.unit import Unit
from sc2.units import Units
from sc2.position import Point2, Point3

from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO")

# All townhalls to check if the enemy's main base is destroyed
TOWNHALLS = {
    UnitTypeId.COMMANDCENTER, UnitTypeId.COMMANDCENTERFLYING,
    UnitTypeId.ORBITALCOMMAND, UnitTypeId.ORBITALCOMMANDFLYING,
    UnitTypeId.PLANETARYFORTRESS, UnitTypeId.HATCHERY,
    UnitTypeId.LAIR, UnitTypeId.HIVE, UnitTypeId.NEXUS
}


# The bot class
class TooManyStalkersBot(sc2.BotAI):
    def __init__(self):
        """Inititialize variables
        """
        super().__init__()

        # The maximum amount of workers
        self.MAX_WORKERS = 80
        # The maximum amount of Nexuses
        self.MAX_NEXUSES = 3
        # The upgrades that will be researched
        self.UPGRADES = ["PROTOSSGROUNDWEAPONSLEVEL",
                         "PROTOSSGROUNDWEAPONSLEVEL",
                         "PROTOSSSHIELDSLEVEL"]

        # If the enemy was greeted and our main base
        self.greeted = False
        self.main: Unit = None

        # The Proxy and the Proxy position
        self.proxy: Unit = None
        self.proxy_position: Point3 = Point3()
        # How many attempts must be made to rebuild the Proxy Pylon
        self.MAX_PROXY_ATTEMPTS = 3
        # How many attempts have been made thusfar
        self.proxy_attempts = 0

        # How many times we've expanded
        self.expand_amount: int = 0

        # The defending Stalkers, the wall-off unit, and the position to defend
        self.bases_defenders: dict = {}
        self.wall_unit: Unit = None

        # The attacking Stalkers, how many attacks have happend
        self.attackers: Units = Units([], self)
        self.attack_amount: int = 0
        # If the enemy's main base is destroyed
        self.enemy_main_destroyed_triggerd = False

        # How many attacking Stalker there must be for every defending Stalker
        self.attack_defend_ratio = 6/1

        # If we should debug and if we should debug once (testing only)
        self.DEBUG = False
        self.debug_once = True

    async def on_before_start(self):
        """Before the game starts
        """
        # Calculate the Proxy location
        self.proxy_position = self.get_proxy_location()
        logger.info(f"Proxy position: {self.proxy_position}")

        # Get the main base
        self.main = self.townhalls.first

    async def on_step(self, iteration: int):
        """What to do each step

        Args:
            iteration (int): what number step it currently is
        """

        # Greet the opponent
        if iteration > 5 and not self.greeted:
            logger.info("Greeted the enemy")
            self.greeted = True
            await self.chat_send(f"Hello {self.opponent_id}, GL HF")

        # Debug and draw on screen
        await self.debug()
        await self.debug_draw()

        # (Built-in) Distribute workers
        await self.distribute_workers()

        # Manage the main base
        await self.manage_bases()

        # Build Pylons and
        await self.build_pylons()
        # Build a Proxy Pylon
        await self.build_proxy()

        # Collect Vespene Gas
        await self.collect_gas()

        # Build Photon Cannons to protect the main base
        await self.build_cannons()

        # Build Gateways/Warpgates, train/warp units, attack
        await self.build_unit_structures()
        await self.train_units()

        # Build research buildings and research
        await self.build_research_structures()
        await self.research()

        await self.expand()

        await self.attack()

    async def debug(self):
        """Spawn 5 Stalkers if self.DEBUG is true
        """
        if self.DEBUG and self.debug_once:
            logger.info("Created 5 Stalkers")
            await self._client.debug_create_unit(
                [[UnitTypeId.STALKER, 5, self.main.position, 1]])
            self.debug_once = False

    async def debug_draw(self):
        """Draw text and spheres for debugging purposes
        """
        # Draw spheres at the Proxy and the defense position
        self._client.debug_sphere_out(
            self.proxy_position, 2, color=(255, 0, 0))

        # If there are attackers, put text on their position
        if self.attackers:
            for stalker in self.units.tags_in(self.attackers):
                self._client.debug_text_world("Attacker",
                                              stalker,
                                              color=(255, 255, 0))

        for base_defenders in self.bases_defenders.values():
            # If there are defenders, put text on their position
            if base_defenders:
                for stalker in self.units.tags_in(base_defenders):
                    self._client.debug_text_world("Defender",
                                                  stalker,
                                                  color=(255, 0, 255))

        # If there is a wall-unit, put text on their position
        if self.wall_unit:
            wall_unit = self.units.tags_in([self.wall_unit.tag])
            if len(wall_unit) > 0:
                self.wall_unit = wall_unit[0]
                self._client.debug_text_world("Wall-off",
                                              self.wall_unit,
                                              color=(255, 255, 255))

        if self.main:
            main = self.structures.tags_in([self.main.tag])
            if len(main) > 0:
                self.main = main[0]
                self._client.debug_sphere_out(
                    self.main.position3d, 4, color=(40, 240, 250))

    async def manage_bases(self):
        """Handle the Chronoboost for each Nexus and produce workers
        """
        # Loop over all the Nexuses
        for nexus in self.townhalls:
            # Handle Chronoboost
            await self.chronoboost(nexus)

            # Train Probes
            if (
                nexus.is_idle
                and self.workers.amount < self.MAX_WORKERS
                and self.can_afford(UnitTypeId.PROBE)
            ):
                nexus.train(UnitTypeId.PROBE)

    async def build_pylons(self):
        """Build Pylons if the supply is too low
        """
        # If the Pylon for the wall-off wasn't built, build it
        wall_pylon = self.main_base_ramp.protoss_wall_pylon
        if (
            await self.can_place_single(UnitTypeId.PYLON, wall_pylon)
            and self.can_afford(UnitTypeId.PYLON)
        ):
            await self.build(UnitTypeId.PYLON, wall_pylon)

        # If there is 8 supply or less left, build a Pylon
        if (
            self.supply_left <= 8
            and self.supply_cap < 200
            and self.townhalls.ready.exists
            and not self.already_pending(UnitTypeId.PYLON)
            and self.can_afford(UnitTypeId.PYLON)
        ):
            position = self.townhalls.ready.random.position.towards(
                self.game_info.map_center, 10
            )
            await self.build(UnitTypeId.PYLON, near=position)

    async def build_proxy(self):
        """Builds a Proxy Pylon if the Warpgate research is a quarter done
        """

        # Build a Proxy Pylon once the Warpgate Research is for 25% done
        if (
            self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) > 0.25
            and self.proxy is None
            and self.proxy_attempts < self.MAX_PROXY_ATTEMPTS
            and self.can_afford(UnitTypeId.PYLON)
            and not self.already_pending(UnitTypeId.PYLON)
        ):
            # If this is first attempt at Proxy, use calculated position
            if self.proxy_attempts == 0:
                pos = self.proxy_position
            # If this isn't the first attempt, calculate new location
            elif self.proxy_attempts > 0:
                pos = self.get_proxy_location()
                logger.info("Proxy position changed to: "
                            f"{self.proxy_position}")

            # Build a Proxy Pylon
            logger.info(f"Building a proxy at {self.proxy_position}")
            await self.build(UnitTypeId.PYLON, pos)
            # Increment the Proxy attempts
            self.proxy_attempts += 1

    async def collect_gas(self):
        """Collect Vespene Gas after a Gateway was build
        """
        # Only collect Gas when a Gateway was built
        if self.structures(UnitTypeId.GATEWAY).exists:
            # Loop over all the Nexuses
            for nexus in self.townhalls.ready:
                # Get all the Vespene Geysers
                vespenenes: Units = self.vespene_geyser.closer_than(10, nexus)

                # Loop over all the Vespene Geysers
                for vespene in vespenenes:
                    # Build an Assimilator on top of the Vespene Geysers
                    if (
                        await self.can_place_single(
                            UnitTypeId.ASSIMILATOR, vespene.position)
                        and not self.already_pending(UnitTypeId.ASSIMILATOR)
                        and self.can_afford(UnitTypeId.ASSIMILATOR)
                    ):
                        await self.build(UnitTypeId.ASSIMILATOR, vespene)

    async def build_unit_structures(self):
        """Build Gateways
        """
        # Build Gateways only when there is a Pylon
        if self.structures(UnitTypeId.PYLON).ready.exists:
            # Get the placement positions for a wall
            wall_buildings = self.main_base_ramp.protoss_wall_buildings
            # See if it can place a building on the position and build it
            for wall_building in wall_buildings:
                if (
                    await self.can_place_single(UnitTypeId.GATEWAY,
                                                wall_building)
                    and self.can_afford(UnitTypeId.GATEWAY)
                ):
                    await self.build(UnitTypeId.GATEWAY, wall_building)

            # Build Gateways by Pylons that aren't the Proxy or the Cannon
            pylon: Unit = self.structures(UnitTypeId.PYLON).ready.random
            while pylon == self.proxy:
                pylon = self.structures(UnitTypeId.PYLON).ready.random

            # Build Gateways once the Warpgate Research is done
            if (
                self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) == 1
                and self.structures(UnitTypeId.FORGE).exists
                and self.structures(
                    UnitTypeId.WARPGATE).amount < self.max_gateways
                and self.can_afford(UnitTypeId.GATEWAY)
            ):
                await self.build(UnitTypeId.GATEWAY, near=pylon)

    async def train_units(self):
        """Train Stalkers from Gateways and warp them in with Warpgates
        """
        # Build a Wall-off unit if there is not one
        if (
            self.wall_unit is None
            and self.can_afford(UnitTypeId.ZEALOT)
            and not self.already_pending(UnitTypeId.ZEALOT)
        ):
            # If we have Warpgates
            if (
                self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) == 1
                and self.structures(UnitTypeId.WARPGATE).ready.exists
            ):
                # Select a random Warpgate
                warpgate = self.structures(UnitTypeId.WARPGATE).ready.random

                # Get the available abilities of the Warpgate
                abilities = await self.get_available_abilities(warpgate)
                # Warp a Zealot if we can warp
                if AbilityId.WARPGATETRAIN_ZEALOT in abilities:
                    # Select a random Pylon that isn't the Proxy or cannon
                    pylon = self.structures(UnitTypeId.PYLON).ready.random
                    while pylon == self.proxy:
                        pylon = self.structures(UnitTypeId.PYLON).ready.random

                    # Get the position of the Pylon
                    pos = pylon.position
                    # Find a placement for the Zealot
                    placement = await self.find_placement(
                        AbilityId.WARPGATETRAIN_STALKER, pos,
                        placement_step=3)

                    # Warp in the Zealot
                    if placement:
                        warpgate.warp_in(UnitTypeId.STALKER, placement)
            # If we don't have Warpgates, just train a Zealot
            elif self.structures(UnitTypeId.GATEWAY).ready.exists:
                gateway = self.structures(UnitTypeId.GATEWAY).ready.first
                gateway.train(UnitTypeId.ZEALOT)

        # If we have Warpgates, warp in Stalkers
        if (
            self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) == 1
            and self.structures(UnitTypeId.WARPGATE).ready.exists
        ):
            # Loop over all the Warpgates and warp in Stalkers
            for warpgate in self.structures(UnitTypeId.WARPGATE):
                # If we can't afford a Stalker, return
                if not self.can_afford(UnitTypeId.STALKER):
                    return
                # Get the available abilities of the Warpgate
                abilities = await self.get_available_abilities(warpgate)
                # Warp a Stalker if we can
                if AbilityId.WARPGATETRAIN_STALKER in abilities:
                    # Select a random Pylon
                    pylon = self.structures(UnitTypeId.PYLON).ready.random

                    # If next Stalker is an attacker, warp it to the Proxy
                    if self.next_stalker_is_attacker():
                        # Warp the Stalker to the proxy if the Proxy exists
                        if self.proxy is not None:
                            pylon = self.proxy
                    # If next Stalker is a defender, warp it to the base
                    elif self.next_stalker_is_defender():
                        # Make sure the random Pylon is not the Proxy
                        while pylon == self.proxy:
                            pylon = self.structures(
                                UnitTypeId.PYLON).ready.random

                    # Get the position of the Pylon
                    pos = pylon.position

                    # Find a placement for the Stalker
                    placement = await self.find_placement(
                        AbilityId.WARPGATETRAIN_STALKER, pos,
                        placement_step=3)

                    # Warp in the Stalker
                    if placement:
                        warpgate.warp_in(UnitTypeId.STALKER, placement)
        # If we don't have Warpgates, just train Stalkers
        elif self.structures(UnitTypeId.GATEWAY).ready.exists:
            # Get all the idle Gateways
            gateways = self.structures(UnitTypeId.GATEWAY)
            gateways = gateways.filter(lambda gw: gw.is_idle)

            # Train Stalkers
            for gateway in gateways:
                # If we can't afford a Stalker, return
                if not self.can_afford(UnitTypeId.STALKER):
                    return

                # Train a Stalker
                gateway.train(UnitTypeId.STALKER)

    async def build_cannons(self):
        """Build Photon Cannons to defend
        """
        for nexus in self.townhalls:
            cannons = self.structures(
                UnitTypeId.PHOTONCANNON).closer_than(15, nexus)

            if cannons.amount < 2:
                pos = nexus.position.towards(self.enemy_start_locations[0], 10)
                await self.build(UnitTypeId.PHOTONCANNON, pos)

    async def build_research_structures(self):
        """Build structures to research from
        """

        # None of the structures can be build if we don't have Pylons
        if self.structures(UnitTypeId.PYLON).ready.exists:
            # Build Research buildings by Pylon that aren't the Proxy or Cannon
            pylon: Unit = self.structures(UnitTypeId.PYLON).ready.random
            while pylon == self.proxy:
                pylon = self.structures(UnitTypeId.PYLON).ready.random

            # If we have a Gateway, build a Cybernetics Core
            if (
                self.structures(UnitTypeId.GATEWAY).ready.exists
                and self.structures(UnitTypeId.CYBERNETICSCORE).amount == 0
                and self.can_afford(UnitTypeId.CYBERNETICSCORE)
            ):
                await self.build(UnitTypeId.CYBERNETICSCORE, near=pylon)

            # If we have a Cybernetics Core, build a Forge
            if (
                self.structures(UnitTypeId.CYBERNETICSCORE).exists
                and self.structures(UnitTypeId.FORGE) == 0
                and self.can_afford(UnitTypeId.FORGE)
            ):
                await self.build(UnitTypeId.FORGE, near=pylon)

            # If the Forge is at it's last upgrade, build a Twilight Council
            if (
                self.already_pending_upgrade(
                    UpgradeId.PROTOSSGROUNDWEAPONSLEVEL1) > 0
                and self.structures(UnitTypeId.TWILIGHTCOUNCIL) == 0
                and self.can_afford(UnitTypeId.TWILIGHTCOUNCIL)
            ):
                await self.build(UnitTypeId.TWILIGHTCOUNCIL, near=pylon)

    async def research(self):
        """Research Warpgates, Weapons, Armor and Shields
        """

        # If we have a Cybernetics Core, research Warpgates
        if self.structures(UnitTypeId.CYBERNETICSCORE).ready.exists:
            # Select a Cybernetics Core and research Warpgate
            ccore = self.structures(UnitTypeId.CYBERNETICSCORE).ready.first

            ccore.research(UpgradeId.WARPGATERESEARCH)

        # If we have a Forge and Warpgates are researching, research upgrades
        if (
            self.structures(UnitTypeId.FORGE).ready.exists
            and self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) > 0
        ):
            # Select a Forge and upgrade
            forge = self.structures(UnitTypeId.FORGE).ready.first

            # Go over all the upgrades
            for i, upgrade in enumerate(self.UPGRADES, 1):
                # Get the upgrade
                current_upgrade = getattr(UpgradeId, f"{upgrade}{i}")
                # If we can afford the upgrade and it's not already pending
                if (
                    self.can_afford(current_upgrade)
                    and not self.already_pending_upgrade(current_upgrade)
                ):
                    # If it's the first upgrade, no Twilight Council is needed
                    if i == 1:
                        forge.research(current_upgrade)
                    # If it's not the first upgrade, Twiligth Council is needed
                    elif self.structures(UnitTypeId.TWILIGHTCOUNCIL).ready:
                        forge.research(current_upgrade)

    async def chronoboost(self, nexus):
        """Handle the Chronoboost of a specific nexus

        Args:
            nexus (Unit): the nexus which will use the Chronoboost
        """

        # If we have enough energy for Chronoboost
        if nexus.energy >= 50:
            # If we have a Cybernetics Core
            if self.structures(UnitTypeId.CYBERNETICSCORE).ready.exists:
                # Select the Cybernetics Core
                ccore = self.structures(UnitTypeId.CYBERNETICSCORE).ready.first

                # If Cybenetics Core isn't idle and doesn't have Chronoboost
                if (
                    not ccore.is_idle
                    and not ccore.has_buff(BuffId.CHRONOBOOSTENERGYCOST)
                ):
                    # Chronoboost the Cybernetics Core
                    nexus(AbilityId.EFFECT_CHRONOBOOSTENERGYCOST, ccore)
                    return

            # If Warpgate is done or is no Cybernetics Core, Chronoboost others
            if (
                self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) == 1
                or not self.structures(UnitTypeId.CYBERNETICSCORE)
            ):
                # If we have a Forge and it's researching, Chronoboost it
                if self.structures(UnitTypeId.FORGE).ready.exists:
                    # Select the Forge
                    forge = self.structures(UnitTypeId.FORGE).ready.first

                    # If Forge isn't idle and doesn't have Chronoboost
                    if (
                        not forge.is_idle
                        and not forge.has_buff(BuffId.CHRONOBOOSTENERGYCOST)
                    ):
                        # Chronoboost the Forge
                        nexus(AbilityId.EFFECT_CHRONOBOOSTENERGYCOST, forge)
                        return

                # If we have a Gateway/Warpgate and isn't idle, Chronoboost it
                for gw in (self.structures(UnitTypeId.GATEWAY).ready |
                           self.structures(UnitTypeId.WARPGATE).ready):
                    # If Gateway/Warpgate isn't idle and has not Chronoboost
                    if (
                        not gw.is_idle
                        and not gw.has_buff(BuffId.CHRONOBOOSTENERGYCOST)
                    ):
                        # Chronoboost Gateway/Warpgate
                        nexus(AbilityId.EFFECT_CHRONOBOOSTENERGYCOST, gw)
                        return

                # If all else fails, Chronoboost yourself
                if (
                    not nexus.has_buff(BuffId.CHRONOBOOSTENERGYCOST)
                    and not self.already_pending(UnitTypeId.CYBERNETICSCORE)
                ):
                    # Chronoboost self
                    nexus(AbilityId.EFFECT_CHRONOBOOSTENERGYCOST, nexus)

    async def expand(self):
        if (
            self.time // 120 > self.expand_amount
            and self.can_afford(UnitTypeId.NEXUS)
            and self.already_pending(UnitTypeId.NEXUS) == 0
            and self.townhalls.amount < self.MAX_NEXUSES
        ):
            logger.info("Expanding")
            self.expand_amount = self.time // 120
            await self.expand_now()

    async def attack(self):
        """Attack and defend
        """

        # If there is a Wall-off unit, place it in the right place
        if self.wall_unit is not None:
            # Get the correct position
            pos = self.main_base_ramp.protoss_wall_warpin

            # If it is not on the position, go to it
            if self.wall_unit.distance_to(pos) > 0:
                self.wall_unit.move(pos)

        for nexus_id in self.bases_defenders.keys():
            # Get the Nexus
            nexus = self.structures.tags_in([nexus_id])
            if len(nexus) > 0:
                nexus = nexus[0]

            if nexus:
                # Get the attacking enemies
                enemies: Units = (
                    self.enemy_units.closer_than(30, nexus) |
                    self.enemy_structures.closer_than(30, nexus)
                )

                # If there are attacking enemies, attack them
                if enemies.exists:
                    # Get the center position
                    target = enemies.center
                    base_defenders = self.bases_defenders[nexus_id]

                    logger.info(f"Enemies detected, attacking {target}")

                    # Send the defenders to attack the Stalkers
                    for stalker in self.units.tags_in(base_defenders):
                        stalker.attack(target)
                else:
                    base_defenders = self.bases_defenders[nexus_id]

                    for stalker in self.units.tags_in(base_defenders):
                        pos = self.find_defend_position(stalker)
                        stalker.attack(pos)

        # If there are attackers, attack
        if self.attackers:
            # If the enemy's main base is destroyed, attack everything
            if await self.enemy_main_destroyed():
                # Find the target
                target: Point2 = self.find_target()
                logger.info(f"Attacking {target.name}")
                # Get the Stalkers
                stalkers = self.units.tags_in(self.attackers)
                stalkers = stalkers.filter(lambda s: s.is_idle)

                # Attack the target
                for stalker in stalkers:
                    stalker.attack(target.position)
            # If we can attack (every 5 minutes)
            elif (
                self.time // 300 > self.attack_amount
            ):
                # Set attack amount equal to the times 5 minutes have passed
                self.attack_amount = int(self.time // 300)
                # Get the enemy's main base
                target: Point2 = self.enemy_start_locations[0]

                # Log and chat the attack
                logger.info(f"Attack {self.attack_amount}, attacking {target}")
                await self.chat_send(f"Starting attack {self.attack_amount}")

                # Attack the enemy's main base
                for stalker in self.units.tags_in(self.attackers):
                    stalker.attack(target)
            # If enemy main not destroyed and can't attack, go to gather point
            else:
                # Get the gather position
                pos = self.proxy_position
                pos = pos.towards(self.enemy_start_locations[0], 10)

                # Get all the attacking Stalkers
                stalkers = self.units.tags_in(self.attackers)
                stalkers = stalkers.filter(lambda s: s.is_idle)

                # Go to the gather point
                for stalker in stalkers:
                    stalker.attack(pos)

    async def on_unit_created(self, unit: Unit):
        """Gets called when a unit is created

        Args:
            unit (Unit): the unit that is created
        """

        logger.info(f"Unit {unit.name} trained at {unit.position}")

        # If the created Unit is a Zealot, it't the wall-off unit
        if (
            unit.type_id == UnitTypeId.ZEALOT
            and self.wall_unit is None
        ):
            self.wall_unit = unit

        # If the created Unit is a Stalker, figure out what it should be
        if unit.type_id == UnitTypeId.STALKER:
            # Get the tag of the unit
            tag = unit.tag

            # If the next Stalker should be an attacker, add it to attackers
            if self.next_stalker_is_attacker():
                self.attackers.append(tag)
            # If the next Stalker should be a defender, add it to defenders
            elif self.next_stalker_is_defender():
                # Set some variables
                min_stalkers_amount = 1000
                base_min_stalkers = 0

                # Loop over all the base defenders
                for base_defenders in self.bases_defenders.values():
                    stalkers = self.units.tags_in(base_defenders)

                    # Get the least amount of Stalkers and the base
                    if stalkers.amount < min_stalkers_amount:
                        min_stalkers_amount = stalkers.amount

                        keys = list(self.bases_defenders.keys())
                        values = list(self.bases_defenders.values())

                        base_min_stalkers = keys[values.index(base_defenders)]

                # Add the Stalkers to the base with the least Stalkers
                stalkers_at_base = self.bases_defenders[base_min_stalkers]
                stalkers_at_base.append(tag)

            # If the unit is in attackers, set pos to the Proxy location
            if tag in self.attackers:
                pos = self.proxy_position
                pos = pos.towards(self.enemy_start_locations[0], 10)

                logger.info(f"Stalker added as attacker, attack/defend ratio: "
                            f"{self.attackers.amount}/{self.get_defenders()}")

            # If the unit is the wall-off, set the pos to the ramp
            elif tag == self.wall_unit.tag:
                pos = self.main_base_ramp.protoss_wall_warpin
                logger.info(f"Zealot added as wall-off, attack/defend ratio: "
                            f"{self.attackers.amount}/{self.get_defenders()}")

            # If the unit is a defender, set pos to defend location
            else:
                # Loop over all the defenders
                for base_defenders in self.bases_defenders.values():
                    # If the tag is in one of the defenders
                    if tag in self.bases_defenders:
                        pos = self.find_defend_position(unit)

                        # Log
                        logger.info(f"Stalker added as defender, "
                                    f"attack/defend ratio: "
                                    f"{self.attackers.amount}/"
                                    f"{self.get_defenders()}")
                        break

                pos = self.main.position

            # Attack the pos
            unit.attack(pos)

    async def on_building_construction_started(self, unit: Unit):
        """Gets called when a building is started building

        Args:
            unit (Unit): the building that is started building
        """
        logger.info(f"Structure {unit.name} "
                    f"started building at {unit.position}")

        # If the unit is a Pylon, it's either the Proxy or Cannon
        if (
            unit.type_id == UnitTypeId.PYLON
            and unit.distance_to(self.enemy_start_locations[0]) < 80
            and self.proxy is None
        ):
            self.proxy = unit
            self.proxy_position = unit.position3d

        # If the structure is a Gateway, set the rally point
        elif unit.type_id == UnitTypeId.GATEWAY:
            # Calculate the offset
            x = (self._game_info.map_center.x - unit.position.x) // 10
            y = -4 if unit.position.y < self._game_info.map_center.y else 4
            offset = (x, y)

            # Offset the position by the offset
            pos = self.main_base_ramp.barracks_in_middle.offset(offset)

            # Rally the Gateway
            unit(AbilityId.RALLY_BUILDING, pos)

    async def on_building_construction_complete(self, unit: Unit):
        # Assign an empty Units object to each Nexus
        if unit.type_id == UnitTypeId.NEXUS:
            self.bases_defenders[unit.tag] = Units([], self)

    async def on_unit_destroyed(self, unit_tag: int):
        """When the building gets destroyed, check if it is the Proxy

        Args:
            unit (Unit): the building that was destroyed
        """

        # If the destroyed unit is Proxy, log to console
        if self.proxy is None:
            logger.info(f"Proxy {unit_tag} was destroyed")

        # If destroyed unit is attacker, log to console
        if unit_tag in self.attackers:
            logger.info(f"Attack Stalker {unit_tag} was killed")
            self.attackers.remove(unit_tag)

        # If destroyed units is defender, log to console
        for base_defenders in self.bases_defenders.values():
            if unit_tag == base_defenders:
                logger.info(f"Defense Stalker {unit_tag} was killed")
                base_defenders.remove(unit_tag)

        # If destroyed unit is wall-off unit, log to console
        if unit_tag == self.wall_unit.tag:
            logger.info(f"Wall-off Zealot {unit_tag} was killed")

    def get_proxy_location(self) -> Point3:
        """Returns the new Proxy location

        Returns:
            Point3: the Proxy location
        """
        # Calculate the Proxy Pylon's position
        proxy_position = self.enemy_start_locations[0]
        proxy_position = proxy_position.towards(self.game_info.map_center, 60)

        # Calculate the heigth
        (x, y) = proxy_position
        z = self.get_terrain_z_height(proxy_position)

        # Return the 3d coordinates
        return Point3((x, y, z))

    def find_target(self):
        """Find a target to attack

        Returns:
            Unit: the unit to attack
        """

        # Returns enemy structures
        if self.enemy_structures.amount > 0:
            return self.enemy_structures.random
        # Else return enemy units
        elif self.enemy_units.amount > 0:
            return self.enemy_units.random
        # Else return the start location
        else:
            return self.enemy_start_locations[0]

    def next_stalker_is_attacker(self) -> bool:
        """Returns True if the next Stalker should be an attacker

        Returns:
            bool: is the next Stalker an attacker
        """
        defenders = self.get_defenders() != 0

        # If there are defenders and attackers, calculate the ratio
        if defenders and self.attackers:
            # For each defender there are {attack_defend_ratio} attackers
            defenders_amount = self.get_defenders() * self.attack_defend_ratio
            attackers_amount = self.attackers.amount

            # If the defender amount is greater, next should be attacker
            if defenders_amount > attackers_amount:
                return True
            # If the attacker amount is greater, next should be defender
            elif defenders_amount < attackers_amount:
                return False
            # If they are even, next should be an attacker
            else:
                return True
        # If there is one defender but no attackers. next should be attacker
        elif defenders:
            return True
        # If there is one attacker but no defender, next should be defender
        elif self.attackers:
            return False
        # If there are not attackers and no defenders, next should be attacker
        else:
            return True

    def next_stalker_is_defender(self) -> bool:
        """Returns True if the next Stalker should be a defender

        Returns:
            bool: is the next Stalker a defender
        """
        # Returns the opposite of the stalker should be defender
        return not self.next_stalker_is_attacker()

    def get_defenders(self):
        defenders = 0

        for base_defenders in self.bases_defenders.values():
            defenders += base_defenders.amount

        return defenders

    def find_defend_position(self, stalker: Unit) -> Point2:
        # Loop over all the defenders
        for base_defenders in self.bases_defenders.values():
            for base_defender in base_defenders:
                # If the tag is in one of the defenders
                if stalker.tag == base_defender:
                    # Get the base
                    keys = list(self.bases_defenders.keys())
                    values = list(self.bases_defenders.values())

                    base = keys[values.index(base_defenders)]
                    base = self.townhalls.tags_in([base])
                    if len(base) > 0:
                        base = base[0].position

                    pos = base.towards(self.enemy_start_locations[0], -10)

                    return pos

        raise TypeError(f"Stalker {stalker} is not a defender")

    async def enemy_main_destroyed(self) -> bool:
        """Returns True if the enemy's main base is destroyed

        Returns:
            bool: is the enemy's main base destroyed
        """
        # If enemy main was already destroyed, assume it will stay destroyed
        if self.enemy_main_destroyed_triggerd:
            return True

        # If units are close enough to see if the main is destroyed, check it
        if (
            self.units.closer_than(10, self.enemy_start_locations[0]).exists
        ):
            # Count the amount of townhalls that are not there
            townhalls = 0
            for townhall in TOWNHALLS:
                if (
                    not self.enemy_structures(townhall).closer_than(
                        5, self.enemy_start_locations[0])
                ):
                    townhalls += 1

            # If amount of townhalls not there == amount possible townhalls
            if townhalls == len(TOWNHALLS):
                # Do some logging
                await self.chat_send("Your main base is destroyed, "
                                     "what are you going to do now?")
                logger.info(f"Townhall: {townhall} is destroyed")
                # Set the enemy main to destroyed
                self.enemy_main_destroyed_triggerd = True
                # Return True
                return True

            # If amount of townhalls not there != amount possible townhalls
            return False

        # If there aren't any units close enough to the enemy base
        return False

    @ property
    def max_gateways(self) -> int:
        """The max Gateways allowed

        Returns:
            int: the amount of Gateways that are allowed
        """

        # Calculate the maximum amount of Gateways (+1 every 30 seconds)
        return self.time // 30 + 1
