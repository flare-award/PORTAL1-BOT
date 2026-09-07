"""
Raycast / Trace system - spatial analysis using 3D world model
Provides API:
- Raycast(origin, direction)
- Trace(from, to)
- IsPathClear(from, to)
- GetSurface(point)
- CanPlacePortal(point, normal)
"""
from __future__ import annotations
from typing import List, Optional, Tuple
import math

from ..world_model.vector import Vector3, QAngle, Bounds
from ..world_model.surface import Surface
from ..game_state.provider import GameStateProvider, HitResult, TraceResult

class SpatialRaycaster:
    """
    Implements raycasting against world model.
    Can use BSP geometry + entity AABBs, or delegate to GameStateProvider.
    """

    def __init__(self, provider: GameStateProvider):
        self.provider = provider

    def raycast(self, origin: Vector3, direction: Vector3, max_dist: float = 8192.0, ignore_entity_id: Optional[int] = None) -> HitResult:
        return self.provider.raycast(origin, direction, max_dist, ignore_entity_id)

    def trace(self, from_pos: Vector3, to_pos: Vector3, ignore_entity_id: Optional[int] = None) -> TraceResult:
        return self.provider.trace(from_pos, to_pos, ignore_entity_id)

    def is_path_clear(self, from_pos: Vector3, to_pos: Vector3, ignore_entity_id: Optional[int] = None) -> bool:
        result = self.trace(from_pos, to_pos, ignore_entity_id)
        return not result.hit or result.fraction >= 0.99

    def get_surface_at_point(self, point: Vector3, max_dist: float = 100.0) -> Optional[Surface]:
        # Raycast down to find surface
        hit = self.raycast(point + Vector3(0,0,10), Vector3(0,0,-1), max_dist)
        if hit.hit and hit.surface_id is not None:
            for surf in self.provider.get_world_geometry():
                if surf.id == hit.surface_id:
                    return surf
        return None

    def get_surface_in_direction(self, origin: Vector3, direction: Vector3, max_dist: float = 8192.0) -> Optional[Tuple[Surface, HitResult]]:
        hit = self.raycast(origin, direction, max_dist)
        if hit.hit and hit.surface_id is not None:
            for surf in self.provider.get_world_geometry():
                if surf.id == hit.surface_id:
                    return surf, hit
        return None

    def can_place_portal(self, point: Vector3, normal: Vector3, portal_type: str = "blue") -> Tuple[bool, str]:
        return self.provider.can_place_portal(point, normal, portal_type)

    def what_is_in_front(self, player_pos: Vector3, player_ang: QAngle, distance: float = 500.0) -> HitResult:
        forward = player_ang.to_forward_vector()
        return self.raycast(player_pos, forward, distance)

    def find_obstacle_between(self, a: Vector3, b: Vector3) -> Optional[HitResult]:
        result = self.trace(a, b)
        if result.hit:
            # Return hit result
            return HitResult(
                hit=True,
                position=result.hit_position,
                normal=result.hit_normal,
                entity_id=result.hit_entity_id,
                distance=(result.hit_position - a).length(),
                fraction=result.fraction
            )
        return None

    def is_visible(self, from_pos: Vector3, to_pos: Vector3) -> bool:
        return self.is_path_clear(from_pos, to_pos)

    def get_visible_surfaces(self, from_pos: Vector3, max_dist: float = 1000.0, fov_deg: float = 90.0, forward: Optional[Vector3] = None) -> List[Surface]:
        """
        Get surfaces visible from position within FOV
        Simplified: raycast to each surface center and check if path clear and within FOV
        """
        visible = []
        surfaces = self.provider.get_world_geometry()
        for surf in surfaces:
            # Distance check
            dist = from_pos.distance_to(surf.position)
            if dist > max_dist:
                continue
            # FOV check if forward provided
            if forward:
                to_surf = (surf.position - from_pos).normalized()
                dot = forward.dot(to_surf)
                # FOV deg to dot threshold: cos(fov/2)
                threshold = math.cos(math.radians(fov_deg / 2))
                if dot < threshold:
                    continue
            # Visibility check
            if self.is_path_clear(from_pos, surf.position):
                visible.append(surf)
        return visible

    def find_portal_placement_candidates(self, near_position: Vector3, max_dist: float = 1000.0, required_normal: Optional[Vector3] = None) -> List[Surface]:
        """
        Find surfaces where portal can be placed, sorted by score
        """
        from ..world_model.portal import PortalPlacementCandidate

        candidates = []
        surfaces = self.provider.get_world_geometry()
        for surf in surfaces:
            if not surf.portalable:
                continue
            dist = near_position.distance_to(surf.position)
            if dist > max_dist:
                continue
            if required_normal:
                # Check normal alignment
                if surf.normal.dot(required_normal) < 0.7:
                    continue
            if not surf.is_large_enough_for_portal():
                continue
            # Score: closer is better, larger area is better
            score = 1000.0 / (dist + 1.0) + surf.area * 0.01
            # Bonus if facing near_position
            to_surf = (surf.position - near_position).normalized()
            facing = -surf.normal.dot(to_surf)  # if surf faces player, dot ~1
            score += facing * 10

            candidates.append((surf, score))

        # Sort by score descending
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [surf for surf, score in candidates]
