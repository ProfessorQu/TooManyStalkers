import random

import sc2
from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId
from sc2.ids.buff_id import BuffId

from sc2.unit import Unit
from sc2.units import Units
from sc2.position import Point2

from loguru import logger


class TooManyStalkersBot(sc2.BotAI):
    def __init__(self):
        """Inititialize variables
        """
        super().__init__()

        self.MAX_WORKERS = 80
        self.UPGRADES = ["PROTOSSGROUNDWEAPONSLEVEL",
                         "PROTOSSGROUNDWEAPONSLEVEL",
                         "PROTOSSSHIELDSLEVEL"]

        self.TOWNHALLS = {
            UnitTypeId.COMMANDCENTER, UnitTypeId.COMMANDCENTERFLYING,
            UnitTypeId.ORBITALCOMMAND, UnitTypeId.ORBITALCOMMANDFLYING,
            UnitTypeId.PLANETARYFORTRESS, UnitTypeId.HATCHERY,
            UnitTypeId.LAIR, UnitTypeId.HIVE, UnitTypeId.NEXUS
        }

        self.greeted = False

        self.MAX_PROXY_ATTEMPTS = 3
        self.proxy: Unit = None
        self.proxy_position: Point2 = Point2()
        self.proxy_attempts = 0

        self.enemy_main_destroyed = False

        self.attack_amount = 0

    async def on_before_start(self):
        self.proxy_position = self.enemy_start_locations[0].towards(self.game_info.map_center, random.randint(60, 70)).offset((random.randint(-10, 10), random.randint(-10, 10)))

    async def on_step(self, iteration: int):
        """What to do each step

        Args:
            iteration (int): what number step it currently is
        """
        # Send a spirit-breaking message
        if iteration > 0 and not self.greeted:
            logger.info("Greeted the enemy")
            self.greeted = True
            await self.chat_send(f"Hello {self.opponent_id}, GL HF")

        # Distribute Probes
        await self.distribute_workers()

        # Manage bases and expand
        await self.manage_bases()
        await self.expand()

        # Build Pylons and collect Gas
        await self.build_pylons()
        await self.collect_gas()

        # Build Gateways, train Stalkers, attack
        await self.build_unit_structures()
        await self.train_units()
        await self.attack()

        # Build a proxy Pylon
        await self.build_proxy()

        # Build research structures and then research from those structures
        await self.build_research_structures()
        await self.research()

    async def manage_bases(self):
        """Handle the Chronoboost for each nexus and produce workers
        """
        # Handle every Nexus
        for nexus in self.townhalls.ready:
            # Handle Chronoboost
            await self.chronoboost(nexus)
            # Train Probes
            if nexus.is_idle:
                if self.workers.amount < self.MAX_WORKERS:
                    if self.can_afford(UnitTypeId.PROBE):
                        logger.info(f"Unit Nexus trained Probe at location {nexus.position}")
                        nexus.train(UnitTypeId.PROBE)
                    else:
                        break

    async def build_pylons(self):
        """Build pylons if the supply is too low
        """
        # If there is less than 8 supply remaining, build a Pylon
        if (
            self.supply_left <= 8
            and self.supply_cap < 200
            and not self.already_pending(UnitTypeId.PYLON)
        ):

            if (
                self.townhalls.ready.exists
                and self.can_afford(UnitTypeId.PYLON)
            ):
                position = self.townhalls.ready.random.position.towards(
                    self.game_info.map_center, 10
                )
                logger.info(f"Building a Pylon near {position}")
                await self.build(UnitTypeId.PYLON, near=position)

    async def collect_gas(self):
        """Collect Vespene Gas
        """
        # If a Gateway exists, collect Gas
        if self.structures(UnitTypeId.GATEWAY):
            # Collect Gas at each Nexus
            for nexus in self.townhalls.ready:
                # Get all Vespene Geysers
                vespenenes: Units = self.vespene_geyser.closer_than(10, nexus)
                for vespene in vespenenes:
                    # Build an Assimilator if it can
                    if (
                        await self.can_place_single(
                            UnitTypeId.ASSIMILATOR, vespene.position)
                        and not self.already_pending(UnitTypeId.ASSIMILATOR)
                        and self.can_afford(UnitTypeId.ASSIMILATOR)
                    ):
                        logger.info(f"Building an Assimilator at {vespene.position}")
                        await self.build(UnitTypeId.ASSIMILATOR, vespene)

    async def expand(self):
        """Expand if allowed
        """
        # If we can build another Nexus
        if (
            self.townhalls.amount < self.max_nexuses
            and self.can_afford(UnitTypeId.NEXUS)
        ):
            logger.info("Expanding")
            # Use the built-in expand_now method
            await self.expand_now()

    async def build_unit_structures(self):
        """Build Gateways
        """
        # If we have a Pylon
        if self.structures(UnitTypeId.PYLON).ready.exists:
            # Select a random Pylon, which is not the proxy Pylon
            pylon: Unit = self.structures(UnitTypeId.PYLON).ready.random
            while pylon == self.proxy:
                pylon = self.structures(UnitTypeId.PYLON).ready.random

            # Build 2 Gateways initially
            if (
                self.structures(UnitTypeId.GATEWAY).amount < 2
                and self.can_afford(UnitTypeId.GATEWAY)
            ):
                logger.info(f"Building a Gateway near {pylon.position}")
                await self.build(UnitTypeId.GATEWAY, near=pylon)

            # When the Warpgate finishes, build more Gateways
            if (
                self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) == 1
                and self.structures.of_type(
                    {UnitTypeId.GATEWAY, UnitTypeId.WARPGATE}).amount
                < self.max_gateways
                and self.can_afford(UnitTypeId.GATEWAY)
            ):
                logger.info(f"Building a Gateway near {pylon.position}")
                await self.build(UnitTypeId.GATEWAY, near=pylon)

    async def train_units(self):
        """Train Stalkers from Gateways and warp them in with Warpgates
        """
        # If we can afford a Stalker, train or warp them in
        if self.can_afford(UnitTypeId.STALKER):
            # If we have Warpgates, warp them
            if (
                self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) == 1
            ):
                # Go over all Waprgates
                for warpgate in self.structures(UnitTypeId.WARPGATE):
                    # Check if it can warp in Stalkers
                    abilities = await self.get_available_abilities(warpgate)

                    if AbilityId.WARPGATETRAIN_STALKER in abilities:
                        # If there is a proxy, warp them there
                        if self.proxy is not None:
                            pos = self.proxy.position
                        # If there is not a proxy, warp them there
                        else:
                            pos = self.structures(UnitTypeId.PYLON).ready.random.position

                        placement = await self.find_placement(
                            AbilityId.WARPGATETRAIN_STALKER, pos,
                            placement_step=3)

                        # If there is not placement position
                        if placement is None:
                            return

                        # Warp
                        logger.info(f"Warping in a Stalker at {placement.position}")
                        warpgate.warp_in(UnitTypeId.STALKER, placement)
            # If we don't have Warpgates
            else:
                # Go over all Gateways
                for gateway in self.structures(UnitTypeId.GATEWAY)\
                        .filter(lambda gw: gw.is_idle):

                    logger.info(f"Trainig a Stalker at {gateway.position}")
                    # Train a Stalker
                    gateway.train(UnitTypeId.STALKER)

    async def attack(self):
        """Attack the enemy
        """
        # If the enemy's main base is destroyed
        if self.enemy_main_destroyed:
            # Kill everything
            target = self.find_target()
            logger.info(f"Attacking {target} with all Stalkers")
            for stalker in self.units(UnitTypeId.STALKER):
                stalker.attack(target)

        # Else if the enemy's main base is not destroyed, but you can't attack
        elif (
            not self.time // 300 > self.attack_amount
        ):
            self.attack_amount = self.time // 300
            # If there already was an attack
            if self.time // 300 > 0:
                # If the enemy's main base is dead
                if (
                    not self.enemy_structures.of_type(
                        self.TOWNHALLS).closer_than(
                        3, self.enemy_start_locations[0]).exists
                    and self.units(UnitTypeId.STALKER).closer_than(
                        10, self.enemy_start_locations[0])
                ):
                    if not self.enemy_main_destroyed:
                        logger.info(f"Enemy main base destroyed")
                        await self.chat_send("There goes your main. (smile)")
                        # Activate "enemy_main_destroyed" mode
                        self.enemy_main_destroyed = True
                else:
                    pos = self.proxy_position.towards(self.enemy_start_locations[0], 10)
                    logger.info(f"Moving Stalkers to {pos}")
                    # Move Stalkers away so new Stalkers can warp in
                    for stalker in self.units(UnitTypeId.STALKER).filter(
                            lambda stalker: stalker.is_idle):
                        stalker.attack(pos)
            # If there wasn't an attack before
            else:
                pos = self.proxy_position.towards(self.enemy_start_locations[0], 10)
                logger.info(f"Moving Stalkers to {pos}")
                # Move Stalkers away so new Stalkers can warp in
                for stalker in self.units(UnitTypeId.STALKER).filter(
                        lambda stalker: stalker.is_idle):
                    stalker.attack(pos)
        # If we can attack
        elif (
            self.time // 300 > self.attack_amount
        ):
            target = self.find_target()
            logger.info(f"Attacking {target}")
            # Attack
            await self.chat_send(f"Initiating attack {int(self.time // 300)}...")
            for stalker in self.units(UnitTypeId.STALKER):
                stalker.attack(target)

    async def build_proxy(self):
        """Builds a proxy Pylon if the Warpgate research is a quarter done
        """
        # If the Warpgate research is 25% done
        if (
            self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) > 0.25
            and self.proxy is None
            and self.proxy_attempts < self.MAX_PROXY_ATTEMPTS
        ):
            # If we can build a Pylon
            if (
                self.can_afford(UnitTypeId.PYLON)
                and not self.already_pending(UnitTypeId.PYLON)
            ):
                # Build a Pylon at a random position towards the enemy base
                if self.proxy_attempts == 0:
                    pos = self.proxy_position
                elif self.proxy_attempts > 0:
                    pos = self.enemy_start_locations[0].towards(
                        self.game_info.map_center, random.randint(60, 70)).offset(
                            (random.randint(-10, 10), random.randint(-10, 10)))
                    self.proxy_position = pos

                await self.build(UnitTypeId.PYLON, near=pos)
                self.proxy_attempts += 1

    async def build_research_structures(self):
        """Build structures to research from
        """
        # If a Pylon exists
        if self.structures(UnitTypeId.PYLON).ready.exists:
            # Select a random one that is not the proxy Pylon
            pylon: Unit = self.structures(UnitTypeId.PYLON).ready.random
            while pylon == self.proxy:
                pylon = self.structures(UnitTypeId.PYLON).ready.random

            # Build a Cybernetics Core if the bot can
            if (
                self.structures(UnitTypeId.GATEWAY).ready.exists
                and not self.structures(
                    UnitTypeId.CYBERNETICSCORE)
                and self.can_afford(UnitTypeId.CYBERNETICSCORE)
            ):
                await self.build(UnitTypeId.CYBERNETICSCORE, near=pylon)

            # Build a Forge after the Cybernetics Core
            if (
                self.structures(UnitTypeId.CYBERNETICSCORE)
                and not self.structures(UnitTypeId.FORGE)
                and self.can_afford(UnitTypeId.FORGE)
            ):
                await self.build(UnitTypeId.FORGE, near=pylon)

            # If the Shields upgrade is researching, build a Twilight Council
            if (
                self.already_pending_upgrade(
                    UpgradeId.PROTOSSSHIELDSLEVEL1) > 0
                and not self.structures(UnitTypeId.TWILIGHTCOUNCIL)
                and self.can_afford(UnitTypeId.TWILIGHTCOUNCIL)
            ):
                await self.build(UnitTypeId.TWILIGHTCOUNCIL, near=pylon)

    async def research(self):
        """Research Warpgates, Weapons, Armor and Shields
        """
        # Research Warpgate
        if self.structures(UnitTypeId.CYBERNETICSCORE).ready.exists:
            # Select a Cybernetics Core
            ccore: Unit = self.structures(
                UnitTypeId.CYBERNETICSCORE).ready.first
            # Research Warpgate
            ccore.research(UpgradeId.WARPGATERESEARCH)

        # Upgrade Weapons, Armor and Shields from the Forge
        if (
            self.structures(UnitTypeId.FORGE).ready.exists
            and self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) > 0
        ):
            # Select a Forge
            forge: Unit = self.structures(UnitTypeId.FORGE).ready.first
            # Upgrade Weapons, the Armor and then Shields
            for i, upgrade in enumerate(self.UPGRADES, 1):
                current_upgrade = getattr(UpgradeId, f"{upgrade}{i}")
                if i == 1:
                    if (
                        self.can_afford(current_upgrade)
                        and not self.already_pending_upgrade(current_upgrade)
                    ):
                        forge.research(current_upgrade)
                elif self.structures(UnitTypeId.TWILIGHTCOUNCIL).ready.exists:
                    if (
                        self.can_afford(current_upgrade)
                        and not self.already_pending_upgrade(current_upgrade)
                    ):
                        forge.research(current_upgrade)

    async def chronoboost(self, nexus):
        """Handle the Chronoboost of a specific nexus

        Args:
            nexus (Unit): the nexus which will use the Chronoboost
        """
        # If the Nexus has enough energy for Chronoboost
        if nexus.energy >= 50:
            # If there is a Cybernetics Core that's not idle, Chronoboost it
            if self.structures(UnitTypeId.CYBERNETICSCORE).ready.exists:
                ccore = self.structures(
                    UnitTypeId.CYBERNETICSCORE).ready.first

                if (
                    not ccore.is_idle
                    and not ccore.has_buff(BuffId.CHRONOBOOSTENERGYCOST)
                ):
                    nexus(AbilityId.EFFECT_CHRONOBOOSTENERGYCOST, ccore)
                    return

            # If Warpgate Research is done or there isn't a Cybernetics Core,
            # Chronoboost the other research buildings

            # Between the Cybernetics Core being built and Warpgate being done,
            # All energy will go to Warpgate
            if (
                self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) == 1
                or not self.structures(UnitTypeId.CYBERNETICSCORE)
            ):
                # If a Forge exists and is not idle, Chronoboost it
                if self.structures(UnitTypeId.FORGE).ready.exists:
                    forge = self.structures(
                        UnitTypeId.FORGE).ready.first

                    if (
                        not forge.is_idle
                        and not forge.has_buff(BuffId.CHRONOBOOSTENERGYCOST)
                    ):
                        nexus(AbilityId.EFFECT_CHRONOBOOSTENERGYCOST, forge)
                        return

                # If a Gateway/Warpgate exists and is not idle, Chronoboost it
                for gw in (self.structures(UnitTypeId.GATEWAY).ready |
                           self.structures(UnitTypeId.WARPGATE).ready):
                    if (
                        not gw.is_idle
                        and not gw.has_buff(BuffId.CHRONOBOOSTENERGYCOST)
                    ):
                        nexus(AbilityId.EFFECT_CHRONOBOOSTENERGYCOST, gw)
                        return

                # If all above fail, Chronoboost yourself
                if (
                    not nexus.has_buff(BuffId.CHRONOBOOSTENERGYCOST)
                    and not self.already_pending(UnitTypeId.CYBERNETICSCORE)
                ):
                    nexus(AbilityId.EFFECT_CHRONOBOOSTENERGYCOST, nexus)

    async def on_building_construction_started(self, unit: Unit):
        """When the construction of a building gets completed, check if it is the proxy

        Args:
            unit (Unit): the building that was completed
        """
        # If the structure is a Pylon and in a certain range of the enemy base,
        # It's the proxy Pylon
        if (
            unit.type_id == UnitTypeId.PYLON
            and unit.distance_to(self.enemy_start_locations[0]) < 80
            and self.proxy is None
        ):
            self.proxy = unit

        # If the structure is a Gateway, rally the units to the ramp
        elif unit.type_id == UnitTypeId.GATEWAY:
            unit(AbilityId.RALLY_BUILDING,
                 self.main_base_ramp.barracks_in_middle)

    async def on_unit_destroyed(self, unit: Unit):
        """When the building gets destroyed, Check if it is the proxy

        Args:
            unit (Unit): the building that was destroyed
        """
        # If the unit destroyed is the proxy, set it to None
        if unit == self.proxy:
            self.proxy = None

    def find_target(self):
        """Find a target to attack

        Returns:
            Point2: the location to attack
        """
        # If there are enemy units, return their position
        if self.enemy_units.amount > 0:
            return self.enemy_units.random.position
        # If there are enemy structures, return their position
        elif self.enemy_structures.amount > 0:
            return self.enemy_structures.random.position
        # Else just return the enemy start location
        else:
            return self.enemy_start_locations[0]

    @ property
    def max_nexuses(self) -> int:
        """The max Nexuses allowed

        Returns:
            int: the amount of Nexuses that are allowed
        """
        # A new Nexus is allowed every 3 minutes
        return self.time // 180 + 1

    @ property
    def max_gateways(self) -> int:
        """The max Gateways allowed

        Returns:
            int: the amount of Gateways that are allowed
        """
        # A new Gateway is allowed every 30 seconds
        return self.time // 30 + 1
