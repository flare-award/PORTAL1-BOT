"""
Aggregated Provider - combines BSP (static) + SAR/Memory (dynamic) to give full world model
"""
from __future__ import annotations
from typing import List, Optional
from ..provider import GameStateProvider, HitResult, TraceResult
from ...world_model.vector import Vector3, QAngle
from ...world_model.entities import PlayerState, Entity
from ...world_model.surface import Surface
from ...world_model.portal import Portal
from .bsp_provider import BSPProvider
from .sar_provider import SARProvider
from .mock_provider import MockProvider

class AggregatedProvider(GameStateProvider):
    """
    Combines multiple providers:
    - BSPProvider for static geometry (walls, floors, portalable surfaces)
    - SARProvider or MemoryProvider for dynamic entities and player
    - MockProvider for testing fallback

    This is the recommended provider for the full bot.
    """

    def __init__(self,
                 bsp_provider: Optional[BSPProvider] = None,
                 dynamic_provider: Optional[GameStateProvider] = None):
        self.bsp_provider = bsp_provider
        self.dynamic_provider = dynamic_provider
        # If no providers given, use mock for development
        if not self.bsp_provider and not self.dynamic_provider:
            print("[AggregatedProvider] No providers given, using MockProvider for both")
            mock = MockProvider()
            self.bsp_provider = mock
            self.dynamic_provider = mock

    def get_player_state(self) -> PlayerState:
        if self.dynamic_provider:
            try:
                return self.dynamic_provider.get_player_state()
            except Exception as e:
                print(f"[Aggregated] dynamic provider failed for player: {e}")
        if self.bsp_provider:
            try:
                return self.bsp_provider.get_player_state()
            except:
                pass
        # Fallback
        return PlayerState(id=1, position=Vector3(0,0,0), rotation=QAngle(0,0,0), eye_position=Vector3(0,0,64))

    def get_entities(self) -> List[Entity]:
        entities = []
        # Static from BSP
        if self.bsp_provider:
            try:
                entities.extend(self.bsp_provider.get_entities())
            except Exception as e:
                print(f"[Aggregated] BSP provider failed for entities: {e}")

        # Dynamic from SAR/Memory - override static if same id
        if self.dynamic_provider:
            try:
                dynamic_entities = self.dynamic_provider.get_entities()
                # Merge: dynamic overrides static by id
                static_by_id = {e.id: e for e in entities}
                for dyn in dynamic_entities:
                    static_by_id[dyn.id] = dyn
                entities = list(static_by_id.values())
            except Exception as e:
                print(f"[Aggregated] dynamic provider failed for entities: {e}")

        return entities

    def get_world_geometry(self) -> List[Surface]:
        if self.bsp_provider:
            try:
                return self.bsp_provider.get_world_geometry()
            except Exception as e:
                print(f"[Aggregated] BSP provider failed for geometry: {e}")
        if self.dynamic_provider:
            try:
                return self.dynamic_provider.get_world_geometry()
            except:
                pass
        return []

    def get_portals(self) -> List[Portal]:
        portals = []
        if self.dynamic_provider:
            try:
                portals.extend(self.dynamic_provider.get_portals())
            except Exception as e:
                print(f"[Aggregated] dynamic provider failed for portals: {e}")
        if self.bsp_provider:
            try:
                portals.extend(self.bsp_provider.get_portals())
            except:
                pass
        # Deduplicate by id
        by_id = {}
        for p in portals:
            by_id[p.id] = p
        return list(by_id.values())

    def raycast(self, origin: Vector3, direction: Vector3, max_distance: float = 8192.0, ignore_entity_id: Optional[int] = None) -> HitResult:
        # Prefer BSP for raycast (has geometry)
        if self.bsp_provider:
            try:
                return self.bsp_provider.raycast(origin, direction, max_distance, ignore_entity_id)
            except Exception as e:
                print(f"[Aggregated] BSP raycast failed: {e}")
        if self.dynamic_provider:
            try:
                return self.dynamic_provider.raycast(origin, direction, max_distance, ignore_entity_id)
            except:
                pass
        # Fallback: no hit
        from ...world_model.vector import Vector3 as V3
        return HitResult(hit=False, position=origin + direction.normalized()*max_distance, normal=V3(0,0,0), distance=max_distance, fraction=1.0)

    def trace(self, from_pos: Vector3, to_pos: Vector3, ignore_entity_id: Optional[int] = None) -> TraceResult:
        direction = to_pos - from_pos
        dist = direction.length()
        if dist < 1e-6:
            return TraceResult(hit=False, start=from_pos, end=to_pos, hit_position=to_pos, hit_normal=Vector3(0,0,0), fraction=1.0)
        hit = self.raycast(from_pos, direction, max_distance=dist, ignore_entity_id=ignore_entity_id)
        return TraceResult(
            hit=hit.hit,
            start=from_pos,
            end=to_pos,
            hit_position=hit.position if hit.hit else to_pos,
            hit_normal=hit.normal,
            hit_entity_id=hit.entity_id,
            fraction=hit.fraction
        )

    def get_world_model(self):
        # Override to properly merge
        from ...world_model.model import WorldModel
        model = WorldModel()
        model.player = self.get_player_state()
        for ent in self.get_entities():
            model.add_entity(ent)
        for surf in self.get_world_geometry():
            model.surfaces[surf.id] = surf
        for portal in self.get_portals():
            model.add_entity(portal)
        model.update_timestamp()
        return model
