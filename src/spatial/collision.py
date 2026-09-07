"""
Collision detection utilities
"""
from __future__ import annotations
from typing import List, Optional
from ..world_model.vector import Vector3, Bounds
from ..world_model.entities import Entity

def check_aabb_collision(a: Bounds, b: Bounds) -> bool:
    return a.intersects(b)

def check_point_in_bounds(point: Vector3, bounds: Bounds) -> bool:
    return bounds.contains(point)

def check_sphere_collision(center_a: Vector3, radius_a: float, center_b: Vector3, radius_b: float) -> bool:
    return center_a.distance_to(center_b) <= (radius_a + radius_b)

def get_colliding_entities(position: Vector3, radius: float, entities: List[Entity], ignore_id: Optional[int] = None) -> List[Entity]:
    result = []
    for ent in entities:
        if ent.id == ignore_id:
            continue
        if not ent.bounds:
            # Use distance check
            if ent.position.distance_to(position) <= radius:
                result.append(ent)
        else:
            # Check if sphere intersects AABB
            # Closest point on AABB to sphere center
            closest = Vector3(
                max(ent.bounds.mins.x, min(position.x, ent.bounds.maxs.x)),
                max(ent.bounds.mins.y, min(position.y, ent.bounds.maxs.y)),
                max(ent.bounds.mins.z, min(position.z, ent.bounds.maxs.z))
            )
            if closest.distance_to(position) <= radius:
                result.append(ent)
    return result

def is_position_free(position: Vector3, radius: float, entities: List[Entity], ignore_id: Optional[int] = None) -> bool:
    return len(get_colliding_entities(position, radius, entities, ignore_id)) == 0
