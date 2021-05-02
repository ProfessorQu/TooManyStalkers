import sc2
from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId


class QBot(sc2.BotAI):
    async def on_step(self, iteration: int):
        await self.distribute_workers()
        await self.build_workers()
        await self.build_pylons()
        await self.expand()
    
    async def build_workers(self):
        for nexus in self.townhalls.ready:
            if nexus.is_idle:
                if self.can_afford(UnitTypeId.PROBE):
                    nexus.train(UnitTypeId.PROBE)
                else:
                    break
    
    async def build_pylons(self):
        if self.supply_left < 5 and not self.already_pending(UnitTypeId.PYLON):
            nexuses = self.townhalls.ready

            if nexuses.exists:
                if self.can_afford(UnitTypeId.PYLON):
                    await self.build(UnitTypeId.PYLON, near=nexuses.first)
    
    async def expand(self):
        print(self.units(UnitTypeId.NEXUS))
        
        if self.townhalls.amount < 2 and self.can_afford(UnitTypeId.NEXUS):
            await self.expand_now()