import sc2
from sc2.ids.unit_typeid import UnitTypeId


class QBot(sc2.BotAI):
    async def on_step(self, iteration):
        await self.distribute_workers()

        for nexus in self.townhalls.ready:
            if nexus.is_idle and self.workers.amount < 80:
                if self.can_afford(UnitTypeId.PROBE):
                    nexus.train(UnitTypeId.PROBE)
                else:
                    break

        if self.supply_left < 5 and self.supply_cap < 200 and not self.already_pending(UnitTypeId.PYLON):
            nexuses = self.townhalls.ready

            if nexuses.ready.exists:
                if self.can_afford(UnitTypeId.PYLON):
                    await self.build(UnitTypeId.PYLON, near=nexuses.ready.random)

        if self.townhalls.amount < self.max_nexuses and self.can_afford(UnitTypeId.NEXUS):
            await self.expand_now()

        if self.structures(UnitTypeId.PYLON).ready.exists:
            pylon = self.structures(UnitTypeId.PYLON).ready.random

            if self.structures(UnitTypeId.GATEWAY).ready.exists:
                if not self.structures(UnitTypeId.CYBERNETICSCORE).ready.exists:
                    if self.can_afford(UnitTypeId.CYBERNETICSCORE) and not self.already_pending(UnitTypeId.CYBERNETICSCORE):
                        await self.build(UnitTypeId.CYBERNETICSCORE, near=pylon)
                elif self.structures(UnitTypeId.GATEWAY) < self.max_gateways:
                    if self.can_afford(UnitTypeId.GATEWAY) and not self.already_pending(UnitTypeId.GATEWAY):
                        await self.build(UnitTypeId.GATEWAY, near=pylon)
            else:
                if self.can_afford(UnitTypeId.GATEWAY) and not self.already_pending(UnitTypeId.GATEWAY):
                    await self.build(UnitTypeId.GATEWAY, near=pylon)

        if self.structures(UnitTypeId.GATEWAY).ready.exists:
            for nexus in self.townhalls.ready:
                vespenes = self.vespene_geyser.closer_than(10, nexus)
                for vespene in vespenes:
                    worker = self.select_build_worker(vespene)
                    if await self.can_place_single(UnitTypeId.ASSIMILATOR, vespene.position) \
                        and self.can_afford(UnitTypeId.ASSIMILATOR) and worker is not None:
                        
                        worker.build(UnitTypeId.ASSIMILATOR, vespene)
            
        if self.structures(UnitTypeId.GATEWAY).ready.exists and self.structures(UnitTypeId.CYBERNETICSCORE).ready.exists:
            for gw in self.structures(UnitTypeId.GATEWAY).ready:
                if gw.is_idle and self.can_afford(UnitTypeId.STALKER) and self.units(UnitTypeId.STALKER) < self.max_stalkers and elf.supply_left > 0:
                    gw.train(UnitTypeId.STALKER)
    
    @property
    def max_nexuses(self):
        return 3

    @property
    def max_gateways(self):
        return 5

    @property
    def max_stalkers(self):
        return 1000000

    