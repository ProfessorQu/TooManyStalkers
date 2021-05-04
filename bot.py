import sc2
from sc2.ids.unit_typeid import UnitTypeId


class QBot(sc2.BotAI):
    def __init__(self):
        self.MAX_WORKERS = 80
        self.MAX_SUPPLY = 200

    async def on_step(self, iteration):
        """What to do every step

        Args:
            iteration (int): the current iteration (aka the current step)
        """
        # Distribute Probes
        await self.distribute_workers()

        # Train Probes as long as they don't go over 80
        for nexus in self.townhalls.ready:
            if nexus.is_idle and self.workers.amount < self.MAX_WORKERS:
                if self.can_afford(UnitTypeId.PROBE):
                    nexus.train(UnitTypeId.PROBE)
                else:
                    break

        # Build Pylons if there is no more supply left
        if self.supply_left < 5 and self.supply_cap < self.MAX_SUPPLY and not self.already_pending(UnitTypeId.PYLON):
            if self.townhalls.ready.exists:
                if self.can_afford(UnitTypeId.PYLON):
                    position = self.townhalls.ready.random.position.towards(self.game_info.map_center, 5)
                    await self.build(UnitTypeId.PYLON, near=position)

        # Expand if self.max_nexuses allows it
        if self.townhalls.amount < self.max_nexuses and self.can_afford(UnitTypeId.NEXUS):
            await self.expand_now()

        # If a Pylon exists
        if self.structures(UnitTypeId.PYLON).ready.exists:
            pylon = self.structures(UnitTypeId.PYLON).ready.random

            # If we have a Gateway
            if self.structures(UnitTypeId.GATEWAY).ready.exists:
                # If there isn't a Cybernetics Core
                if not self.structures(UnitTypeId.CYBERNETICSCORE).ready.exists:
                    # If we can afford a Cybernetics Core
                    if self.can_afford(UnitTypeId.CYBERNETICSCORE) and not self.already_pending(UnitTypeId.CYBERNETICSCORE):
                        # Build a Cybernetics Core
                        await self.build(UnitTypeId.CYBERNETICSCORE, near=pylon)
                # Else build another Gateway if self.max_gateways allows it
                elif self.structures(UnitTypeId.GATEWAY).amount < self.max_gateways:
                    # If we can afford a Gateway
                    if self.can_afford(UnitTypeId.GATEWAY) and not self.already_pending(UnitTypeId.GATEWAY):
                        # Build a Gateway
                        await self.build(UnitTypeId.GATEWAY, near=pylon)
            # If we don't have a gateway
            else:
                if self.can_afford(UnitTypeId.GATEWAY) and not self.already_pending(UnitTypeId.GATEWAY):
                    await self.build(UnitTypeId.GATEWAY, near=pylon)

        # If we have a Gateway
        if self.structures(UnitTypeId.GATEWAY).ready.exists:
            # Build Assimilators near the Nexuses
            for nexus in self.townhalls.ready:
                vespenes = self.vespene_geyser.closer_than(10, nexus)
                for vespene in vespenes:
                    if await self.can_place_single(UnitTypeId.ASSIMILATOR, vespene.position) \
                        and self.can_afford(UnitTypeId.ASSIMILATOR):
                        
                        await self.build(UnitTypeId.ASSIMILATOR, vespene)
            
        # If a Gateway and Cybernetics Core exists, build Stalkers
        if self.structures(UnitTypeId.GATEWAY).ready.exists and self.structures(UnitTypeId.CYBERNETICSCORE).ready.exists:
            # Loop over al the Gateways
            for gw in self.structures(UnitTypeId.GATEWAY).ready:
                # If the Gateway isn't training anything and we can afford a Stalker
                if gw.is_idle and self.can_afford(UnitTypeId.STALKER) and self.units(UnitTypeId.STALKER).amount < self.max_stalkers and self.supply_left > 0:
                    # Build Stalker
                    gw.train(UnitTypeId.STALKER)
        
        # Attack if there are 15+ Stalkers
        if self.units(UnitTypeId.STALKER).idle.amount > 15:
            for stalker in self.units(UnitTypeId.STALKER).idle:
                stalker.attack(self.find_target())
        
        # Attack units if there are 3+ Stalkers and not 15+ Stalkers
        elif self.units(UnitTypeId.STALKER).idle.amount > 3:
            if self.enemy_units.amount > 0:
                for stalker in self.units(UnitTypeId.STALKER).idle:
                    stalker.attack(self.enemy_units.random)
    
    def find_target(self):
        """Finds a target

        Returns:
            Units: the units/structures to target
        """
        # If there are enemy units, attack them
        if self.enemy_units.amount > 0:
            return self.enemy_units.random
        # If there are enemy structures, but no enemy units, attack them
        elif self.enemy_structures.amount > 0:
            return self.enemy_structures.random
        # If there are no enemy units or structures, attack the enemy start location
        else:
            return self.enemy_start_locations[0]

    @property
    def max_nexuses(self) -> float:
        """Return the maximum Nexuses

        Returns:
            float: the amount of maximum Nexuses allowed at the time
        """
        return (self.time / 60) + 1

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

    