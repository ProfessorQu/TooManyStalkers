import random

import sc2
from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId
from sc2.ids.buff_id import BuffId

from sc2.unit import Unit
from sc2.units import Units


class TooManyStalkersBot(sc2.BotAI):
    def __init__(self):
        super().__init__()

        self.MAX_WORKERS = 80

        self.proxy: Unit = None
        self.proxy_built = False

        self.is_attacking = False

    async def on_step(self, iteration):
        """What to do every step

        Args:
            iteration (int): the current iteration (aka the current step)
        """
        # Distribute Probes
        await self.distribute_workers()

        await self.manage_bases()
        await self.expand()

        await self.build_pylons()
        await self.collect_gas()

        await self.build_unit_structures()
        await self.train_units()
        await self.attack()

        await self.build_proxy()

        await self.build_research_structures()
        await self.research()

    async def manage_bases(self):
        # Train Probes as long as they don't go over 80
        for nexus in self.townhalls.ready:
            await self.chronoboost(nexus)
            if nexus.is_idle:
                if self.workers.amount < self.MAX_WORKERS:
                    if self.can_afford(UnitTypeId.PROBE):
                        nexus.train(UnitTypeId.PROBE)
                    else:
                        break

    async def build_pylons(self):
        # Build Pylons if there is no more supply left
        if (
            self.supply_left <= 5
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
        # Build Assimilators if we have a Gateway
        if self.structures(UnitTypeId.GATEWAY).ready.exists:
            # Collect Vespene Gas
            for nexus in self.townhalls.ready:
                vespenenes: Units = self.vespene_geyser.closer_than(10, nexus)
                for vespene in vespenenes:
                    if (
                        await self.can_place_single(
                            UnitTypeId.ASSIMILATOR, vespene.position)
                        and not self.already_pending(UnitTypeId.ASSIMILATOR)
                        and self.can_afford(UnitTypeId.ASSIMILATOR)
                    ):
                        await self.build(UnitTypeId.ASSIMILATOR, vespene)

    async def expand(self):
        # Expand if self.max_nexuses allows it
        if (
            self.townhalls.amount < self.max_nexuses
            and self.can_afford(UnitTypeId.NEXUS)
        ):
            await self.expand_now()

    async def build_unit_structures(self):
        # If we have a Pylon, build a Gateway
        if self.structures(UnitTypeId.PYLON).ready.exists:
            # Make sure that we don't build anything near the proxy Pylon
            pylon: Unit = self.structures(UnitTypeId.PYLON).ready.random
            while pylon == self.proxy:
                pylon = self.structures(UnitTypeId.PYLON).ready.random

            # If we don't have a Gateway
            if (
                self.structures(UnitTypeId.GATEWAY).amount < 2
                and self.can_afford(UnitTypeId.GATEWAY)
            ):
                # Build a Gateway
                await self.build(UnitTypeId.GATEWAY, near=pylon)
            # If we do have a Gateway

            if (
                self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) == 1
                and self.structures.of_type(
                    {UnitTypeId.GATEWAY, UnitTypeId.WARPGATE}).amount
                < self.max_gateways
                and self.can_afford(UnitTypeId.GATEWAY)
            ):
                await self.build(UnitTypeId.GATEWAY, near=pylon)

    async def train_units(self):
        if self.can_afford(UnitTypeId.STALKER):
            if (
                self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) == 1
                and self.proxy is not None
            ):
                for warpgate in self.structures(UnitTypeId.WARPGATE):
                    abilities = await self.get_available_abilities(warpgate)

                    if AbilityId.WARPGATETRAIN_STALKER in abilities:
                        pos = self.proxy.position
                        placement = await self.find_placement(
                            AbilityId.WARPGATETRAIN_STALKER, pos,
                            placement_step=1)

                        if placement is None:
                            print("Not able to place")
                            return

                        warpgate.warp_in(UnitTypeId.STALKER, placement)
            else:
                for gateway in self.structures(UnitTypeId.GATEWAY)\
                        .filter(lambda gw: gw.is_idle):
                    gateway(AbilityId.RALLY_BUILDING,
                            self.main_base_ramp.barracks_in_middle)

                    if self.can_afford(UnitTypeId.STALKER):
                        gateway.train(UnitTypeId.STALKER)

    async def attack(self):
        if (
            self.proxy is not None
            and self.units(UnitTypeId.STALKER).amount > 4
        ):
            for stalker in self.units(UnitTypeId.STALKER).filter(
                    lambda stalker: stalker.is_idle):
                stalker.attack(self.proxy.position.towards(
                    self.enemy_start_locations[0], 5))

        if self.units(UnitTypeId.STALKER).amount > 10:
            self.is_attacking = True

            for stalker in self.units(UnitTypeId.STALKER):
                stalker.attack(self.enemy_start_locations[0])

            if self.is_attacking:
                for stalker in self.units(UnitTypeId.STALKER).filter(
                        lambda stalker: stalker.is_idle):
                    stalker.attack(self.find_target())

    async def build_proxy(self):
        if (
            self.structures(UnitTypeId.CYBERNETICSCORE).ready.exists
            and self.proxy is None
            and not self.proxy_built
        ):
            if (
                self.can_afford(UnitTypeId.PYLON)
                and not self.already_pending(UnitTypeId.PYLON)
            ):
                pos = self.enemy_start_locations[0].towards(
                    self.game_info.map_center, random.randint(40, 50)) \
                    .offset((random.randint(0, 5), random.randint(0, 5)))

                await self.build(UnitTypeId.PYLON, near=pos)

                self.proxy_built = True

    async def build_research_structures(self):
        if self.structures(UnitTypeId.PYLON).ready.exists:
            pylon: Unit = self.structures(UnitTypeId.PYLON).ready.random
            if (
                self.structures(UnitTypeId.GATEWAY).ready.exists
                and not self.structures(
                    UnitTypeId.CYBERNETICSCORE).ready.exists
                and not self.already_pending(UnitTypeId.CYBERNETICSCORE)
            ):
                await self.build(UnitTypeId.CYBERNETICSCORE, near=pylon)

            if (
                not self.structures(UnitTypeId.FORGE).ready.exists
                and not self.already_pending(UnitTypeId.FORGE)
                and self.already_pending(UnitTypeId.CYBERNETICSCORE)
            ):
                await self.build(UnitTypeId.FORGE, near=pylon)

    async def research(self):
        # If there is a Cybernetics Core, research Warpgate
        if self.structures(UnitTypeId.CYBERNETICSCORE).ready.exists:
            # Research Warpgate
            ccore: Unit = self.structures(
                UnitTypeId.CYBERNETICSCORE).ready.first
            ccore.research(UpgradeId.WARPGATERESEARCH)

        # If there is a Forge and Warpgate is done,
        # Upgrade Weapons, Armor and Shields
        if (
            self.structures(UnitTypeId.FORGE).ready.exists
            and self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) == 1
        ):
            forge: Unit = self.structures(UnitTypeId.FORGE).ready.first
            # Upgrade Weapons
            if (
                self.can_afford(UpgradeId.PROTOSSGROUNDWEAPONSLEVEL1)
                and not self.already_pending_upgrade(
                    UpgradeId.PROTOSSGROUNDARMORSLEVEL1)
            ):
                forge.research(UpgradeId.PROTOSSGROUNDWEAPONSLEVEL1)

            # Upgrade Armor
            elif (
                self.can_afford(UpgradeId.PROTOSSGROUNDARMORSLEVEL1)
                and not self.already_pending_upgrade(
                    UpgradeId.PROTOSSGROUNDARMORSLEVEL1)
            ):
                forge.research(UpgradeId.PROTOSSGROUNDWEAPONSLEVEL1)

            # Upgrade Shields
            elif (
                self.can_afford(UpgradeId.PROTOSSSHIELDSLEVEL1)
                and not self.already_pending_upgrade(
                    UpgradeId.PROTOSSSHIELDSLEVEL1)
            ):
                forge.research(UpgradeId.PROTOSSSHIELDSLEVEL1)

    async def chronoboost(self, nexus):
        if nexus.energy >= 50:
            if self.structures(UnitTypeId.CYBERNETICSCORE).ready.exists:
                ccore = self.structures(
                    UnitTypeId.CYBERNETICSCORE).ready.first

                if (
                    not ccore.is_idle
                    and not ccore.has_buff(BuffId.CHRONOBOOSTENERGYCOST)
                ):
                    nexus(AbilityId.EFFECT_CHRONOBOOSTENERGYCOST, ccore)
                    return

            if self.structures(UnitTypeId.TWILIGHTCOUNCIL).ready.exists:
                tcouncil = self.structures(
                    UnitTypeId.TWILIGHTCOUNCIL).ready.first

                if (
                    not tcouncil.is_idle
                    and not tcouncil.has_buff(BuffId.CHRONOBOOSTENERGYCOST)
                ):
                    nexus(AbilityId.EFFECT_CHRONOBOOSTENERGYCOST, tcouncil)
                    return

            if self.structures(UnitTypeId.FORGE).ready.exists:
                forge = self.structures(
                    UnitTypeId.FORGE).ready.first

                if (
                    not forge.is_idle
                    and not forge.has_buff(BuffId.CHRONOBOOSTENERGYCOST)
                ):
                    nexus(AbilityId.EFFECT_CHRONOBOOSTENERGYCOST, forge)
                    return

            for gw in (self.structures(UnitTypeId.GATEWAY).ready |
                       self.structures(UnitTypeId.WARPGATE).ready):
                if (
                    not gw.is_idle
                    and not gw.has_buff(BuffId.CHRONOBOOSTENERGYCOST)
                ):
                    nexus(AbilityId.EFFECT_CHRONOBOOSTENERGYCOST, gw)
                    return

            if not nexus.has_buff(BuffId.CHRONOBOOSTENERGYCOST):
                nexus(AbilityId.EFFECT_CHRONOBOOSTENERGYCOST, nexus)

    async def on_building_construction_complete(self, unit: Unit):
        if (
            unit.type_id == UnitTypeId.PYLON
            and unit.distance_to(self.enemy_start_locations[0]) < 50
            and self.proxy is None
        ):
            self.proxy = unit

    async def on_unit_destroyed(self, unit: Unit):
        if (
            unit == self.proxy
        ):
            self.proxy = None
            self.proxy_built = False

    def find_target(self):
        if self.enemy_units.amount > 0:
            return self.enemy_units.random
        elif self.enemy_structures.amount > 0:
            return self.enemy_structures.random
        else:
            return self.enemy_start_locations[0]

    @property
    def max_nexuses(self) -> int:
        """Return the maximum Nexuses

        Returns:
            int: the amount of maximum Nexuses allowed at the time
        """
        return int(self.time / 180) + 1

    @property
    def max_gateways(self) -> int:
        """Returns the maximum Gateways

        Returns:
            int: the amount of maximum Gateways allowed at the time
        """
        return int(self.time / 30) + 1

    @property
    def max_stalkers(self) -> int:
        """Returns the maximum Stalkers

        Returns:
            int: the amount of maximum Stalkers allowed at the time
        """
        return 1000000
