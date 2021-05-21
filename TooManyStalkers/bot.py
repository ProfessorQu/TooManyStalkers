import random
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

TOWNHALLS = {
    UnitTypeId.COMMANDCENTER, UnitTypeId.COMMANDCENTERFLYING,
    UnitTypeId.ORBITALCOMMAND, UnitTypeId.ORBITALCOMMANDFLYING,
    UnitTypeId.PLANETARYFORTRESS, UnitTypeId.HATCHERY,
    UnitTypeId.LAIR, UnitTypeId.HIVE, UnitTypeId.NEXUS
}


class TooManyStalkersBot(sc2.BotAI):
    def __init__(self):
        """Inititialize variables
        """
        super().__init__()

        self.MAX_WORKERS = 80
        self.UPGRADES = ["PROTOSSGROUNDWEAPONSLEVEL",
                         "PROTOSSGROUNDWEAPONSLEVEL",
                         "PROTOSSSHIELDSLEVEL"]

        self.greeted = False

        self.main: Unit = None

        self.MAX_PROXY_ATTEMPTS = 3
        self.proxy: Unit = None
        self.proxy_position: Point3 = Point3()
        self.proxy_attempts = 0

        self.attack_amount = 0
        self.enemy_main_destroyed_triggerd = False

        self.defenders: Units = Units([], self)
        self.attackers: Units = Units([], self)
        self.attack_defend_ratio = 4/1

        self.wall_unit: Unit = None

        self.defend_position: Point3 = Point3()
        self.cannon_pylon: Unit = None
        self.MAX_PHOTON_CANNONS = 3

        self.DEBUG = False
        self.debug_once = True

    async def on_before_start(self):
        self.proxy_position = self.get_proxy_location()
        logger.info(f"Proxy position: {self.proxy_position}")

        defend_distance = -10
        defend_position = self.townhalls.first.position
        defend_position = defend_position.towards(
            self.game_info.map_center, defend_distance)

        (x, y) = defend_position
        z = self.get_terrain_z_height(defend_position)

        self.defend_position = Point3((x, y, z))
        logger.info(f"Defend position: {self.defend_position}")

        self.main = self.townhalls.first

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

        await self.debug()
        await self.debug_draw()

        # Distribute Probes
        await self.distribute_workers()

        # Manage bases and expand
        await self.manage_bases()
        await self.expand()

        # Build Pylons and collect Gas
        await self.build_pylons()
        await self.collect_gas()

        await self.build_cannons()

        # Build Gateways, train Stalkers, attack
        await self.build_unit_structures()
        await self.train_units()
        await self.attack()

        # Build a proxy Pylon
        await self.build_proxy()

        # Build research structures and then research from those structures
        await self.build_research_structures()
        await self.research()

    async def debug_draw(self):
        self._client.debug_sphere_out(
            self.defend_position, 1, color=(0, 255, 0))
        self._client.debug_sphere_out(
            self.proxy_position, 1, color=(255, 0, 0))

        if self.cannon_pylon:
            self._client.debug_sphere_out(
                self.cannon_pylon.position3d, 1, color=(255, 255, 255))

        if self.attackers:
            for stalker in self.units.tags_in(self.attackers):
                self._client.debug_text_world("Attacker",
                                              stalker,
                                              color=(255, 255, 0))

        if self.defenders:
            for stalker in self.units.tags_in(self.defenders):
                self._client.debug_text_world("Defender",
                                              stalker,
                                              color=(255, 0, 255))

        if self.wall_unit:
            self.wall_unit = self.units.tags_in([self.wall_unit.tag])[0]
            self._client.debug_text_world("Wall-off",
                                          self.wall_unit,
                                          color=(255, 255, 255))

    async def debug(self):
        if self.DEBUG and self.debug_once:
            logger.info("Created 5 Stalkers")
            await self._client.debug_create_unit(
                [[UnitTypeId.STALKER, 5, self.main.position, 1]])
            self.debug_once = False

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
        wall_pylon = self.main_base_ramp.protoss_wall_pylon
        if (
            await self.can_place_single(UnitTypeId.PYLON, wall_pylon)
            and self.can_afford(UnitTypeId.PYLON)
        ):
            await self.build(UnitTypeId.PYLON,
                             near=wall_pylon, placement_step=3)

        cannon_pylon_pos = self.defend_position.towards(
            self.enemy_start_locations[0], -2)
        if (
            await self.can_place_single(UnitTypeId.PYLON, cannon_pylon_pos)
            and self.can_afford(UnitTypeId.PYLON)
        ):
            await self.build(UnitTypeId.PYLON,
                             near=cannon_pylon_pos, placement_step=3)

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
                await self.build(UnitTypeId.PYLON,
                                 near=position, placement_step=3)

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
                        await self.build(UnitTypeId.ASSIMILATOR,
                                         near=vespene, placement_step=3)

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
        wall_buildings = self.main_base_ramp.protoss_wall_buildings
        # If we have a Pylon
        if self.structures(UnitTypeId.PYLON).ready.exists:
            for wall_building in wall_buildings:
                if (
                    await self.can_place_single(
                        UnitTypeId.GATEWAY, wall_building)
                    and self.can_afford(UnitTypeId.GATEWAY)
                ):
                    await self.build(UnitTypeId.GATEWAY,
                                     near=wall_building, placement_step=3)

            # Select a random Pylon, which is not the proxy Pylon
            pylon: Unit = self.structures(UnitTypeId.PYLON).ready.random
            while pylon == self.proxy or pylon == self.cannon_pylon:
                pylon = self.structures(UnitTypeId.PYLON).ready.random

            # Build 2 Gateways initially
            if (
                self.structures(UnitTypeId.GATEWAY).amount < 2
                and self.can_afford(UnitTypeId.GATEWAY)
            ):
                await self.build(UnitTypeId.GATEWAY,
                                 near=pylon, placement_step=3)

            # When the Warpgate finishes, build more Gateways
            if (
                self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) == 1
                and self.structures.of_type(
                    {UnitTypeId.GATEWAY, UnitTypeId.WARPGATE}).amount
                < self.max_gateways
                and self.can_afford(UnitTypeId.GATEWAY)
            ):
                await self.build(UnitTypeId.GATEWAY,
                                 near=pylon, placement_step=3)

    async def train_units(self):
        """Train Stalkers from Gateways and warp them in with Warpgates
        """
        if (
            self.wall_unit is None
            and self.can_afford(UnitTypeId.ZEALOT)
            and self.structures(UnitTypeId.GATEWAY).ready.exists
            and not self.already_pending(UnitTypeId.ZEALOT)
        ):
            if self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) == 1:
                warpgate = self.structures(UnitTypeId.WARPGATE).ready.first

                abilities = await self.get_available_abilities(warpgate)

                if AbilityId.WARPGATETRAIN_ZEALOT in abilities:
                    pylon = self.structures(UnitTypeId.PYLON).ready.random

                    while pylon == self.proxy or pylon == self.cannon_pylon:
                        pylon = self.structures(UnitTypeId.PYLON).ready.random

                    pos = pylon.position

                    placement = await self.find_placement(
                        AbilityId.WARPGATETRAIN_STALKER, pos,
                        placement_step=3)

                    if placement:
                        warpgate.warp_in(UnitTypeId.STALKER, placement)
            else:
                gateway = self.structures(UnitTypeId.GATEWAY).ready.first
                gateway.train(UnitTypeId.ZEALOT)

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
                        if self.next_stalker_is_attacker():
                            # If there is a proxy, warp them there
                            if self.proxy is not None:
                                pos = self.proxy.position
                            # If there is not a proxy, warp them there
                            else:
                                pos = self.structures(
                                    UnitTypeId.PYLON).ready.random.position
                        elif self.next_stalker_is_defender():
                            pylon = self.structures(
                                UnitTypeId.PYLON).ready.random

                            while (
                                pylon == self.proxy
                                or pylon == self.cannon_pylon
                            ):
                                pylon = self.structures(
                                    UnitTypeId.PYLON).ready.random

                            pos = pylon.position

                        placement = await self.find_placement(
                            AbilityId.WARPGATETRAIN_STALKER, pos,
                            placement_step=3)

                        # If there is not placement position
                        if placement:
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

        if self.wall_unit is not None:
            pos = self.main_base_ramp.protoss_wall_warpin
            if self.wall_unit.distance_to(pos) > 0:
                self.wall_unit.move(pos)

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
                for stalker in self.units.tags_in(self.defenders):
                    stalker.attack(target)
            else:
                for stalker in self.units.tags_in(self.defenders):
                    stalker.attack(self.defend_position)

        if self.attackers:
            # If the enemy's main base is destroyed
            if await self.enemy_main_destroyed():
                # Kill everything
                target: Point2 = self.find_target()
                logger.info(f"Attacking {target.name}")
                for stalker in self.units.tags_in(self.attackers).filter(
                        lambda s: s.is_idle):
                    stalker.attack(target.position)
            # If the enemy's main base is not destoryed, and we can attack
            elif (
                self.time // 300 > self.attack_amount
            ):
                self.attack_amount = self.time // 300
                target: Point2 = self.enemy_start_locations[0]
                logger.info(
                    f"Attack {int(self.attack_amount)}, attacking {target}")
                # Attack
                await self.chat_send(
                    f"Starting attack {int(self.attack_amount)}...")
                for stalker in self.units.tags_in(self.attackers):
                    stalker.attack(target)
            else:
                pos = self.proxy_position.towards(
                    self.enemy_start_locations[0], 10)
                for stalker in self.units.tags_in(self.attackers).filter(
                        lambda s: s.is_idle):
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
                    pos = self.get_proxy_location()
                    logger.info(
                        f"Proxy position changed to: {self.proxy_position}")

                logger.info(f"Building a proxy at {self.proxy_position}")
                await self.build(UnitTypeId.PYLON,
                                 near=pos, placement_step=3)
                self.proxy_attempts += 1

    async def build_cannons(self):
        if (
            self.structures(UnitTypeId.FORGE).ready.exists
            and self.structures(
                UnitTypeId.PHOTONCANNON).amount < self.MAX_PHOTON_CANNONS
            and self.cannon_pylon is not None
            and self.can_afford(UnitTypeId.PHOTONCANNON)
            and self.already_pending(UnitTypeId.PHOTONCANNON) == 0
        ):
            await self.build(UnitTypeId.PHOTONCANNON, near=self.cannon_pylon)

    async def build_research_structures(self):
        """Build structures to research from
        """
        # If a Pylon exists
        if self.structures(UnitTypeId.PYLON).ready.exists:
            # Select a random one that is not the proxy Pylon
            pylon: Unit = self.structures(UnitTypeId.PYLON).ready.random
            while pylon == self.proxy or pylon == self.cannon_pylon:
                pylon = self.structures(UnitTypeId.PYLON).ready.random

            # Build a Cybernetics Core if the bot can
            if (
                self.structures(UnitTypeId.GATEWAY).ready.exists
                and not self.structures(
                    UnitTypeId.CYBERNETICSCORE)
                and self.can_afford(UnitTypeId.CYBERNETICSCORE)
            ):
                await self.build(UnitTypeId.CYBERNETICSCORE,
                                 near=pylon, placement_step=3)

            # Build a Forge after the Cybernetics Core
            if (
                self.structures(UnitTypeId.CYBERNETICSCORE)
                and not self.structures(UnitTypeId.FORGE)
                and self.can_afford(UnitTypeId.FORGE)
            ):
                await self.build(UnitTypeId.FORGE,
                                 near=pylon, placement_step=3)

            # If the Shields upgrade is researching, build a Twilight Council
            if (
                self.already_pending_upgrade(
                    UpgradeId.PROTOSSSHIELDSLEVEL1) > 0
                and not self.structures(UnitTypeId.TWILIGHTCOUNCIL)
                and self.can_afford(UnitTypeId.TWILIGHTCOUNCIL)
            ):
                await self.build(UnitTypeId.TWILIGHTCOUNCIL,
                                 near=pylon, placement_step=3)

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

        if (
            unit.type_id == UnitTypeId.ZEALOT
            and self.wall_unit is None
        ):
            self.wall_unit = unit

        if unit.type_id == UnitTypeId.STALKER:
            tag = unit.tag

            if self.next_stalker_is_attacker():
                self.attackers.append(tag)
            elif self.next_stalker_is_defender():
                self.defenders.append(tag)

            if tag in self.attackers:
                pos = self.proxy_position.towards(
                    self.enemy_start_locations[0], 10)
                logger.info(f"Stalker added as attacker, attack/defend ratio: "
                            f"{self.attackers.amount}/{self.defenders.amount}")
            elif tag in self.defenders:
                pos = self.defend_position
                logger.info(f"Stalker added as defender, attack/defend ratio: "
                            f"{self.attackers.amount}/{self.defenders.amount}")
            elif tag == self.wall_unit.tag:
                pos = self.main_base_ramp.protoss_wall_warpin
                logger.info(f"Zealot added as wall-off, attack/defend ratio: "
                            f"{self.attackers.amount}/{self.defenders.amount}")

            unit.attack(pos)

    async def on_building_construction_started(self, unit: Unit):
        """Gets called when a building is started building

        Args:
            unit (Unit): the building that is started building
        """
        logger.info(
            f"Structure {unit.name} started building at {unit.position}")
        # If the structure is a Pylon and in a certain range of the enemy base,
        # It's the proxy Pylon
        if (
            unit.type_id == UnitTypeId.PYLON
        ):
            if (
                unit.distance_to(self.enemy_start_locations[0]) < 80
                and self.proxy is None
            ):

                self.proxy = unit
                self.proxy_position = unit.position3d
            elif (
                unit.distance_to(self.defend_position) < 3
                and self.cannon_pylon is None
            ):
                self.cannon_pylon = unit

        # If the structure is a Gateway, rally the units to the ramp
        elif unit.type_id == UnitTypeId.GATEWAY:
            x = (self._game_info.map_center.x -
                 unit.position.x) // 10
            y = -4 if unit.position.y < self._game_info.map_center.y else 4
            center_pos = (x, y)

            pos = self.main_base_ramp.barracks_in_middle.offset(center_pos)
            unit(AbilityId.RALLY_BUILDING, pos)

    async def on_unit_destroyed(self, unit_tag: int):
        """When the building gets destroyed, check if it is the proxy

        Args:
            unit (Unit): the building that was destroyed
        """
        # If the unit destroyed is the proxy, set it to None
        if self.proxy is None:
            logger.info(f"Proxy {unit_tag} was destroyed")

        if unit_tag in self.attackers:
            logger.info(f"Attack Stalker {unit_tag} was killed")
            self.attackers.remove(unit_tag)

        if unit_tag in self.defenders:
            logger.info(f"Defense Stalker {unit_tag} was killed")
            self.defenders.remove(unit_tag)

    def get_proxy_location(self) -> Point3:
        """Returns the new proxy location

        Returns:
            Point3: the proxy location
        """
        proxy_distance = random.randint(60, 70)
        proxy_offset = (random.randint(-10, 10), random.randint(-10, 10))

        proxy_position = self.enemy_start_locations[0]
        proxy_position = proxy_position.towards(
            self.game_info.map_center, proxy_distance)
        proxy_position.offset(proxy_offset)

        (x, y) = proxy_position
        z = self.get_terrain_z_height(proxy_position)

        return Point3((x, y, z))

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

    def next_stalker_is_attacker(self) -> bool:
        """Returns True if the next Stalker should be an attacker

        Returns:
            bool: is the next Stalker an attacker
        """
        if self.defenders and self.attackers:
            defenders_amount = self.defenders.amount * self.attack_defend_ratio
            attackers_amount = self.attackers.amount
            if defenders_amount > attackers_amount:
                return True
            elif defenders_amount < attackers_amount:
                return False
            else:
                return True

        elif self.defenders:
            return True
        elif self.attackers:
            return False
        else:
            return True

    def next_stalker_is_defender(self) -> bool:
        """Returns True if the next Stalker should be a defender

        Returns:
            bool: is the next Stalker a defender
        """
        return not self.next_stalker_is_attacker()

    async def enemy_main_destroyed(self) -> bool:
        """Returns True if the enemy's main base is destroyed

        Returns:
            bool: is the enemy's main base destroyed
        """
        if self.enemy_main_destroyed_triggerd:
            return True

        if (
            self.units.closer_than(10, self.enemy_start_locations[0])
        ):
            townhalls = 0
            for townhall in TOWNHALLS:
                if (
                    not self.enemy_structures(townhall).closer_than(
                        5, self.enemy_start_locations[0])
                ):
                    townhalls += 1

            if townhalls == len(TOWNHALLS):
                await self.chat_send("Your main base is destroyed, "
                                     "what are you going to do now?")
                logger.info(f"Townhall: {townhall} is destroyed")
                self.enemy_main_destroyed_triggerd = True
                return True

            return False

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
