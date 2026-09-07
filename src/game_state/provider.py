"""
GameStateProvider - abstract interface for extracting structured data from Portal 1
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from ..world_model.vector import Vector3, QAngle, Bounds
from ..world_model.entities import PlayerState, Entity
from ..world_model.surface import Surface
from ..world_model.portal import Portal
from ..world_model.model import WorldModel

@dataclass
class HitResult:
    hit: bool
    position: Vector3
    normal: Vector3
    entity_id: Optional[int] = None
    surface_id: Optional[int] = None
    distance: float = 0.0
    material: str = ""
    fraction: float = 1.0  # 0..1 how far along ray

    def to_dict(self):
        return {
            "hit": self.hit,
            "position": self.position.to_tuple(),
            "normal": self.normal.to_tuple(),
            "entity_id": self.entity_id,
            "surface_id": self.surface_id,
            "distance": self.distance,
            "material": self.material,
            "fraction": self.fraction
        }

@dataclass
class TraceResult:
    hit: bool
    start: Vector3
    end: Vector3
    hit_position: Vector3
    hit_normal: Vector3
    hit_entity_id: Optional[int] = None
    fraction: float = 1.0
    all_solid: bool = False
    start_solid: bool = False

class GameStateProvider(ABC):
    """
    Abstract provider that gives structured 3D world info.
    Implementations: BSPProvider, SARProvider, ConsoleProvider, MemoryProvider, MockProvider
    """

    @abstractmethod
    def get_player_state(self) -> PlayerState:
        pass

    @abstractmethod
    def get_entities(self) -> List[Entity]:
        pass

    @abstractmethod
    def get_world_geometry(self) -> List[Surface]:
        pass

    @abstractmethod
    def get_portals(self) -> List[Portal]:
        pass

    @abstractmethod
    def raycast(self, origin: Vector3, direction: Vector3, max_distance: float = 8192.0, ignore_entity_id: Optional[int] = None) -> HitResult:
        pass

    @abstractmethod
    def trace(self, from_pos: Vector3, to_pos: Vector3, ignore_entity_id: Optional[int] = None) -> TraceResult:
        pass

    def is_path_clear(self, from_pos: Vector3, to_pos: Vector3) -> bool:
        result = self.trace(from_pos, to_pos)
        return not result.hit or result.fraction >= 0.99

    def get_surface_at(self, point: Vector3) -> Optional[Surface]:
        # Raycast down to find surface under point
        hit = self.raycast(point + Vector3(0,0,10), Vector3(0,0,-1), max_distance=100)
        if hit.hit and hit.surface_id is not None:
            # Need to fetch surfaces - implemented in subclass or via world geometry
            for surf in self.get_world_geometry():
                if surf.id == hit.surface_id:
                    return surf
        return None

    def can_place_portal(self, point: Vector3, normal: Vector3, portal_type: str = "blue") -> Tuple[bool, str]:
        """
        Check if portal can be placed at point with normal.
        Returns (can_place, reason)
        """
        # Basic checks - to be overridden
        # 1. Surface must be portalable
        # 2. Surface must be large enough
        # 3. No entity blocking
        # 4. Normal must be roughly axis-aligned? Actually any flat surface works
        surfaces = self.get_world_geometry()
        # Find closest surface
        closest = None
        min_dist = float('inf')
        for surf in surfaces:
            dist = surf.position.distance_to(point)
            if dist < min_dist:
                # Check normal alignment
                if surf.normal.dot(normal) > 0.9:  # same direction
                    min_dist = dist
                    closest = surf

        if closest is None:
            return False, "No surface found"

        if not closest.portalable:
            return False, f"Surface {closest.id} not portalable (material={closest.material})"

        if not closest.is_large_enough_for_portal():
            return False, f"Surface {closest.id} too small"

        # Check if blocked
        # Raycast from point slightly off surface outward to check clearance
        check_origin = point + normal * 2
        hit = self.raycast(check_origin, normal * -1, max_distance=10)
        # If hit is very close and not the same surface, blocked
        # For now assume ok

        return True, "OK"

    def get_world_model(self) -> WorldModel:
        """
        Build full WorldModel from current state
        """
        model = WorldModel()
        try:
            model.player = self.get_player_state()
        except Exception as e:
            print(f"[Provider] Failed to get player state: {e}")

        try:
            entities = self.get_entities()
            for ent in entities:
                model.add_entity(ent)
        except Exception as e:
            print(f"[Provider] Failed to get entities: {e}")

        try:
            surfaces = self.get_world_geometry()
            for surf in surfaces:
                model.surfaces[surf.id] = surf
        except Exception as e:
            print(f"[Provider] Failed to get world geometry: {e}")

        try:
            portals = self.get_portals()
            for portal in portals:
                model.add_entity(portal)
        except Exception as e:
            print(f"[Provider] Failed to get portals: {e}")

        model.update_timestamp()
        return model

    def connect(self) -> bool:
        """Optional: connect to game process"""
        return True

    def disconnect(self):
        pass
