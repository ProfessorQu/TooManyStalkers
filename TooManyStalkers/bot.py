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
        self.UPGRADES = ["PROTOSSGROUNDWEAPONSLEVEL",
                         "PROTOSSGROUNDWEAPONSLEVEL",
                         "PROTOSSSHIELDSLEVEL"]

        self.TOWNHALLS = {
            UnitTypeId.COMMANDCENTER, UnitTypeId.COMMANDCENTERFLYING,
            UnitTypeId.ORBITALCOMMAND, UnitTypeId.ORBITALCOMMANDFLYING,
            UnitTypeId.PLANETARYFORTRESS, UnitTypeId.HATCHERY,
            UnitTypeId.LAIR, UnitTypeId.HIVE, UnitTypeId.NEXUS
        }

        self.proxy: Unit = None
        self.proxy_built = False

        self.ded = False

    async def on_step(self, iteration):
        if iteration == 0:
            await self.chat_send(
                f"Hello {self.opponent_id}, my records indicate "
                "that I have won 420% of matches against you (flex), "
                "also: GLHF")

        if iteration % 500 == 0:
            await self.chat_send(
                random.choice(["(poo)", "(happy)"]))

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
        for nexus in self.townhalls.ready:
            await self.chronoboost(nexus)
            if nexus.is_idle:
                if self.workers.amount < self.MAX_WORKERS:
                    if self.can_afford(UnitTypeId.PROBE):
                        nexus.train(UnitTypeId.PROBE)
                    else:
                        break

    async def build_pylons(self):
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
        if self.structures(UnitTypeId.GATEWAY):
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
        if (
            self.townhalls.amount < self.max_nexuses
            and self.can_afford(UnitTypeId.NEXUS)
        ):
            await self.expand_now()

    async def build_unit_structures(self):
        if self.structures(UnitTypeId.PYLON).ready.exists:
            pylon: Unit = self.structures(UnitTypeId.PYLON).ready.random
            while pylon == self.proxy:
                pylon = self.structures(UnitTypeId.PYLON).ready.random

            if (
                self.structures(UnitTypeId.GATEWAY).amount < 2
                and self.can_afford(UnitTypeId.GATEWAY)
            ):
                await self.build(UnitTypeId.GATEWAY, near=pylon)

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
                and self.proxy_built
            ):
                for warpgate in self.structures(UnitTypeId.WARPGATE):
                    abilities = await self.get_available_abilities(warpgate)

                    if AbilityId.WARPGATETRAIN_STALKER in abilities:
                        pos = self.proxy.position
                        placement = await self.find_placement(
                            AbilityId.WARPGATETRAIN_STALKER, pos,
                            placement_step=3)

                        if placement is None:
                            print("Not able to place")
                            return

                        warpgate.warp_in(UnitTypeId.STALKER, placement)
            else:
                for gateway in self.structures(UnitTypeId.GATEWAY)\
                        .filter(lambda gw: gw.is_idle):

                    if self.can_afford(UnitTypeId.STALKER):
                        gateway.train(UnitTypeId.STALKER)

    async def attack(self):
        if self.ded:
            target = self.find_target()
            for stalker in self.units(UnitTypeId.STALKER):
                stalker.attack(target)

        elif (
            self.proxy is not None
            and self.proxy_built
            and not self.can_attack
        ):
            if self.time // 300 > 0:
                if (
                    not self.enemy_structures.of_type(
                        self.TOWNHALLS).closer_than(
                        3, self.enemy_start_locations[0]).exists
                    and self.units(UnitTypeId.STALKER).closer_than(
                        10, self.enemy_start_locations[0])
                ):
                    if not self.ded:
                        await self.chat_send("Ur dead GG (flex)")
                        self.ded = True
                else:
                    for stalker in self.units(UnitTypeId.STALKER).filter(
                            lambda stalker: stalker.is_idle):
                        stalker.attack(self.proxy.position.towards(
                            self.enemy_start_locations[0], 10))

            else:
                for stalker in self.units(UnitTypeId.STALKER).filter(
                        lambda stalker: stalker.is_idle):
                    stalker.attack(self.proxy.position.towards(
                        self.enemy_start_locations[0], 10))
        elif (
            self.proxy is not None
            and self.proxy_built
            and self.can_attack
        ):
            await self.chat_send(
                f"Initiating attack number {int(self.time // 300)}... GG WP")
            for stalker in self.units(UnitTypeId.STALKER):
                stalker.attack(self.find_target())

    async def build_proxy(self):
        if (
            self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) > 0.25
            and self.proxy is None
            and not self.proxy_built
        ):
            if (
                self.can_afford(UnitTypeId.PYLON)
                and not self.already_pending(UnitTypeId.PYLON)
            ):
                pos = self.enemy_start_locations[0].towards(
                    self.game_info.map_center, random.randint(60, 70)).offset(
                        (random.randint(-10, 10), random.randint(-10, 10)))

                await self.build(UnitTypeId.PYLON, near=pos)
                self.proxy_built = True

    async def build_research_structures(self):
        if self.structures(UnitTypeId.PYLON).ready.exists:
            pylon: Unit = self.structures(UnitTypeId.PYLON).ready.random

            while pylon == self.proxy:
                pylon = self.structures(UnitTypeId.PYLON).ready.random

            if (
                self.structures(UnitTypeId.GATEWAY).ready.exists
                and not self.structures(
                    UnitTypeId.CYBERNETICSCORE)
                and self.can_afford(UnitTypeId.CYBERNETICSCORE)
            ):
                await self.build(UnitTypeId.CYBERNETICSCORE, near=pylon)

            if (
                self.structures(UnitTypeId.CYBERNETICSCORE)
                and not self.structures(UnitTypeId.FORGE)
                and self.can_afford(UnitTypeId.FORGE)
            ):
                await self.build(UnitTypeId.FORGE, near=pylon)

            if (
                self.already_pending_upgrade(
                    UpgradeId.PROTOSSSHIELDSLEVEL1) > 0
                and not self.structures(UnitTypeId.TWILIGHTCOUNCIL)
                and self.can_afford(UnitTypeId.TWILIGHTCOUNCIL)
            ):
                await self.build(UnitTypeId.TWILIGHTCOUNCIL, near=pylon)

    async def research(self):
        if self.structures(UnitTypeId.CYBERNETICSCORE).ready.exists:
            ccore: Unit = self.structures(
                UnitTypeId.CYBERNETICSCORE).ready.first
            ccore.research(UpgradeId.WARPGATERESEARCH)

        if (
            self.structures(UnitTypeId.FORGE).ready.exists
            and self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) > 0
        ):
            forge: Unit = self.structures(UnitTypeId.FORGE).ready.first
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

            if (
                self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) == 1
                or not self.structures(UnitTypeId.CYBERNETICSCORE)
            ):
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

                if (
                    not nexus.has_buff(BuffId.CHRONOBOOSTENERGYCOST)
                    and not self.already_pending(UnitTypeId.CYBERNETICSCORE)
                ):
                    nexus(AbilityId.EFFECT_CHRONOBOOSTENERGYCOST, nexus)

    async def on_building_construction_complete(self, unit: Unit):
        if (
            unit.type_id == UnitTypeId.PYLON
            and unit.distance_to(self.enemy_start_locations[0]) < 80
            and self.proxy is None
        ):
            self.proxy = unit

        elif unit.type_id == UnitTypeId.GATEWAY:
            unit(AbilityId.RALLY_BUILDING,
                 self.main_base_ramp.barracks_in_middle)

    async def on_unit_destroyed(self, unit: Unit):
        if unit == self.proxy:
            self.proxy = None
            self.proxy_built = False

    def find_target(self):
        if self.enemy_units.amount > 0:
            return self.enemy_units.random.position
        elif self.enemy_structures.amount > 0:
            return self.enemy_structures.random.position
        else:
            return self.enemy_start_locations[0]

    @ property
    def can_attack(self) -> bool:
        return self.time % 300 == 0

    @ property
    def max_nexuses(self) -> int:
        return self.time // 180 + 1

    @ property
    def max_gateways(self) -> int:
        return self.time // 30 + 1
