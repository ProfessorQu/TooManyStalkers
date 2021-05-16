import random

import sc2
from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId
from sc2.ids.buff_id import BuffId

from sc2.unit import Unit
from sc2.units import Units
from sc2.position import Point2, Point3

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

        self.attack_amount = 0

        self.defenders: Units = None
        self.attackers: Units = None
        self.defend_attack_ratio = 1/3
        self.defend_position: Point2 = Point2()

    async def on_before_start(self):
        proxy_distance = random.randint(60, 70)
        proxy_offset = (random.randint(-10, 10), random.randint(-10, 10))

        self.proxy_position = self.enemy_start_locations[0]
        self.proxy_position.towards(
            self.game_info.map_center, proxy_distance)
        self.proxy_position.offset(proxy_offset)

        defend_distance = random.randint(10, 30)
        defend_offset_x = random.randint(0, 10)
        defend_offset_y = random.randint(0, 10)

        if self.townhalls.first.position.x < self.game_info.map_center.x:
            x_multiplier = 1
        else:
            x_multiplier = -1

        if self.townhalls.first.position.y < self.game_info.map_center.y:
            y_multiplier = 1
        else:
            y_multiplier = -1

        defend_offset = (defend_offset_x * x_multiplier,
                         defend_offset_y * y_multiplier)

        self.defend_position = self.townhalls.first.position
        self.defend_position.towards(
            self.game_info.map_center, defend_distance)

        self.defend_position.offset(defend_offset)

    async def on_step(self, iteration: int):
        """What to do each step

        Args:
            iteration (int): what number step it currently is
        """
        # Send a spirit-breaking message
        if iteration > 5 and not self.greeted:
            logger.info("Greeted the enemy")
            self.greeted = True
            await self.chat_send(f"Hello {self.opponent_id}, GL HF")

        self.debug_draw()

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

    def debug_draw(self):
        self._client.debug_box2_out(
            Point3((self.defend_position.x, self.defend_position.y, 0.5)),
            half_vertex_length=2, color=(255, 255, 0))

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
                await self.build(UnitTypeId.GATEWAY, near=pylon)

            # When the Warpgate finishes, build more Gateways
            if (
                self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) == 1
                and self.structures.of_type(
                    {UnitTypeId.GATEWAY, UnitTypeId.WARPGATE}).amount
                < self.max_gateways
                and self.can_afford(UnitTypeId.GATEWAY)
            ):
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
                            pos = self.structures(
                                UnitTypeId.PYLON).ready.random.position

                        placement = await self.find_placement(
                            AbilityId.WARPGATETRAIN_STALKER, pos,
                            placement_step=3)

                        # If there is not placement position
                        if placement is None:
                            return

                        # Warp
                        warpgate.warp_in(UnitTypeId.STALKER, placement)
            # If we don't have Warpgates
            else:
                # Go over all Gateways
                for gateway in self.structures(UnitTypeId.GATEWAY)\
                        .filter(lambda gw: gw.is_idle):

                    # Train a Stalker
                    gateway.train(UnitTypeId.STALKER)

    async def attack(self):
        """Attack and defend
        """

        if self.defenders:
            enemies_amount = 0
            attacking_enemies: Units = None
            for nexus in self.townhalls:
                enemies: Units = (self.enemy_units.closer_than(30, nexus) |
                                  self.enemy_structures.closer_than(30, nexus))
                if enemies.amount > enemies_amount:
                    enemies_amount = enemies.amount
                    attacking_enemies = enemies

            if attacking_enemies:
                target = enemies.center
                logger.info(f"Enemies detected, attacking {target}")
                for stalker in self.defenders:
                    stalker.attack(target)
            else:
                for stalker in self.defenders.further_than(
                        20, self.defend_position):
                    stalker.attack(self.defend_position)

        if self.attackers:
            # If the enemy's main base is destroyed
            if self.enemy_main_destroyed():
                # Kill everything
                target: Unit = self.find_target()
                logger.info(f"Attacking {target.name} at {target.position}")
                for stalker in self.attackers:
                    stalker.attack(target.position)
            # If the enemy's main base is not destoryed, and we can attack
            elif (
                self.time // 300 > self.attack_amount
            ):
                self.attack_amount = self.time // 300
                target: Point2 = self.enemy_start_locations[0]
                logger.info(f"Attack {self.attack_amount}, attacking {target}")
                # Attack
                await self.chat_send(
                    f"Starting attack {self.attack_amount}...")
                for stalker in self.attackers:
                    stalker.attack(target)
            else:
                pos = self.proxy_position.towards(
                    self.enemy_start_locations[0], 5)
                for stalker in self.attackers:
                    stalker.attack(pos)

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
                    pos = self.enemy_start_locations[0]
                    pos.towards(self.game_info.map_center,
                                random.randint(60, 70))
                    pos.offset((random.randint(-10, 10),
                               random.randint(-10, 10)))
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

    async def on_unit_created(self, unit: Unit):
        """Gets called when a unit is created

        Args:
            unit (Unit): the unit that is created
        """
        # Log to console
        logger.info(f"Unit {unit.name} trained at {unit.position}")

        if unit.type_id == UnitTypeId.STALKER:
            if self.defenders and self.attackers:
                defenders_amount = self.defenders.amount \
                    * self.defend_attack_ratio
                attackers_amount = self.attackers.amount

                if defenders_amount > attackers_amount:
                    self.attackers.append(unit)
                elif defenders_amount < attackers_amount:
                    self.defenders.append(unit)
                else:
                    self.attackers.append(unit)
            elif self.defenders:
                self.attackers.append(unit)
            elif self.attackers:
                self.defenders.append(unit)

    async def on_building_construction_started(self, unit: Unit):
        """Gets called when a building is started building

        Args:
            unit (Unit): the building that is started building
        """
        logger.info(f"Structure {unit.name} built at {unit.position}")
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
            Unit: the unit to attack
        """
        # If there are enemy units, return their position
        if self.enemy_units.amount > 0:
            return self.enemy_units.random
        # If there are enemy structures, return their position
        elif self.enemy_structures.amount > 0:
            return self.enemy_structures.random
        # Else just return the enemy start location
        else:
            return self.enemy_start_locations[0]

    async def enemy_main_destroyed(self) -> bool:
        """Returns if the enemy's main base is destroyed

        Returns:
            bool: is the enemy's main base destroyed
        """
        for townhall in self.TOWNHALLS:
            if (
                not self.enemy_structures(townhall).closer_than(
                    5, self.enemy_start_locations[0])
                and self.units.closer_than(10, self.enemy_start_locations[0])
            ):
                return True

        return False

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
