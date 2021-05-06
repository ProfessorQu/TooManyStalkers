import sc2
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId
from sc2.ids.ability_id import AbilityId

from sc2.position import Point2, Point3
from sc2.unit import Unit
from sc2.units import Units


class TooManyStalkersBot(sc2.BotAI):
    def __init__(self):
        self.MAX_WORKERS = 80

    async def on_step(self, iteration):
        """What to do every step

        Args:
            iteration (int): the current iteration (aka the current step)
        """
        # Distribute Probes
        await self.distribute_workers()

        # Train Probes as long as they don't go over 80
        for nexus in self.townhalls.ready.filter(lambda nexus: nexus.is_idle):
            if self.workers.amount < self.MAX_WORKERS:
                if self.can_afford(UnitTypeId.PROBE):
                    nexus.train(UnitTypeId.PROBE)
                else:
                    break

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

        # Expand if self.max_nexuses allows it
        if (
            self.townhalls.amount < self.max_nexuses
            and self.can_afford(UnitTypeId.NEXUS)
        ):
            await self.expand_now()

        # If we have a Pylone
        if self.structures(UnitTypeId.PYLON).ready.exists:
            pylon: Unit = self.structures(UnitTypeId.PYLON).ready.random
            # If we don't have a Gateway
            if (
                self.structures(UnitTypeId.GATEWAY) +
                self.already_pending(UnitTypeId.GATEWAY) == 0
            ):
                # Build a Gateway
                await self.build(UnitTypeId.GATEWAY, near=pylon)
            else:
                if (
                    not self.structures(UnitTypeId.CYBERNETICSCORE)
                    and not self.already_pending(UnitTypeId.CYBERNETICSCORE)
                ):
                    await self.build(UnitTypeId.CYBERNETICSCORE, near=pylon)

                if (
                    not self.structures(UnitTypeId.FORGE)
                    and not self.already_pending(UnitTypeId.CYBERNETICSCORE)
                ):
                    await self.build(UnitTypeId.FORGE, near=pylon)

        # If there is a Cybernetics Core
        if self.structures(UnitTypeId.CYBERNETICSCORE).ready.exists:
            # Research Warpgates
            ccore: Unit = self.structures(
                UnitTypeId.CYBERNETICSCORE).ready.first
            ccore.research(UpgradeId.WARPGATERESEARCH)

        # If there is a Forge
        if (
            self.structures(UnitTypeId.FORGE).ready.exists
            and self.already_pending_upgrade(UpgradeId.WARPGATERESEARCH) == 1
        ):
            forge: Unit = self.structures(UnitTypeId.FORGE).ready.first
            # Upgrade Weapons, Armor and Shields
            if (
                self.can_afford(UpgradeId.PROTOSSGROUNDWEAPONSLEVEL1)
                and not self.already_pending_upgrade(
                    UpgradeId.PROTOSSGROUNDARMORSLEVEL1)
            ):
                forge.research(UpgradeId.PROTOSSGROUNDWEAPONSLEVEL1)

            elif (
                self.can_afford(UpgradeId.PROTOSSGROUNDARMORSLEVEL1)
                and not self.already_pending_upgrade(
                    UpgradeId.PROTOSSGROUNDARMORSLEVEL1)
            ):
                forge.research(UpgradeId.PROTOSSGROUNDWEAPONSLEVEL1)

            elif (
                self.can_afford(UpgradeId.PROTOSSSHIELDSLEVEL1)
                and not self.already_pending_upgrade(
                    UpgradeId.PROTOSSSHIELDSLEVEL1)
            ):
                forge.research(UpgradeId.PROTOSSSHIELDSLEVEL1)

        # If we have a Gateway
        if self.structures(UnitTypeId.GATEWAY).ready.exists:
            # Collect Vespene Gas
            for nexus in self.townhalls.ready:
                vespenenes: Units = self.vespene_geyser.closer_than(10, nexus)
                for vespene in vespenenes:
                    if (
                        await self.can_place_single(
                            UnitTypeId.ASSIMILATOR, vespene.position)
                        and self.can_afford(UnitTypeId.ASSIMILATOR)
                    ):
                        await self.build(UnitTypeId.ASSIMILATOR, vespene)

        # # If a Pylon exists
        # if self.structures(UnitTypeId.PYLON).ready.exists:
        # pylon = self.structures(UnitTypeId.PYLON).ready.random

        # # If we have a Gateway
        # if self.structures(UnitTypeId.GATEWAY).ready.exists:
        # # If there isn't a Cybernetics Core
        # if not self.structures(UnitTypeId.CYBERNETICSCORE).ready.exists:
        # # If we can afford a Cybernetics Core
        # # Build a Cybernetics Core
        # await self.build(UnitTypeId.CYBERNETICSCORE, near=pylon)
        # # Else build another Gateway if self.max_gateways allows it
        # elif self.structures(UnitTypeId.GATEWAY).amount < self.max_gateways:
        # # If we can afford a Gateway
        # # Build a Gateway
        # await self.build(UnitTypeId.GATEWAY, near=pylon)
        # # If we don't have a gateway
        # else:
        # await self.build(UnitTypeId.GATEWAY, near=pylon)

        # # If we have a Gateway
        # if self.structures(UnitTypeId.GATEWAY).ready.exists:
        # # Build Assimilators near the Nexuses
        # for nexus in self.townhalls.ready:
        # vespenes = self.vespene_geyser.closer_than(10, nexus)
        # for vespene in vespenes:
        # and self.can_afford(UnitTypeId.ASSIMILATOR):

        # await self.build(UnitTypeId.ASSIMILATOR, vespene)

        # # If a Gateway and Cybernetics Core exists, build Stalkers
        # # Loop over al the Gateways
        # for gw in self.structures(UnitTypeId.GATEWAY).ready:
        # # If the Gateway isn't training anything and we can afford a Stalker
        # # Build Stalker
        # gw.train(UnitTypeId.STALKER)

        # # Attack if there are 15+ Stalkers
        # if self.units(UnitTypeId.STALKER).idle.amount > 15:
        # for stalker in self.units(UnitTypeId.STALKER).idle:
        # stalker.attack(self.find_target())

        # # Attack units if there are 3+ Stalkers and not 15+ Stalkers
        # elif self.units(UnitTypeId.STALKER).idle.amount > 3:
        # if self.enemy_units.amount > 0:
        # for stalker in self.units(UnitTypeId.STALKER).idle:
        # stalker.attack(self.enemy_units.random)

    @property
    def max_nexuses(self) -> float:
        """Return the maximum Nexuses

        Returns:
            float: the amount of maximum Nexuses allowed at the time
        """
        return (self.time / 120) + 1

    @property
    def max_gateways(self) -> float:
        """Returns the maximum Gateways

        Returns:
            float: the amount of maximum Gateways allowed at the time
        """
        return (self.time / 30) + 1

    @property
    def max_stalkers(self) -> float:
        """Returns the maximum Stalkers

        Returns:
            float: the amount of maximum Stalkers allowed at the time
        """
        return 1000000
