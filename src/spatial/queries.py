"""
Spatial Reasoning - answers questions about 3D world from WorldModel
- What is left/right/front/behind player?
- Where is nearest cube?
- Is there obstacle between?
- Can pass to area?
- Can place portal?
- etc.
"""
from __future__ import annotations
from typing import List, Optional, Tuple
import math

from ..world_model.vector import Vector3, QAngle
from ..world_model.model import WorldModel
from ..world_model.entities import Entity, Cube, Button, Door
from ..world_model.surface import Surface
from ..world_model.portal import Portal
from .raycast import SpatialRaycaster

class SpatialQuerySystem:
    def __init__(self, world_model: WorldModel, raycaster: SpatialRaycaster):
        self.world_model = world_model
        self.raycaster = raycaster

    def update_world_model(self, world_model: WorldModel):
        self.world_model = world_model

    # --- Directional queries ---

    def _get_player_basis(self):
        if not self.world_model.player:
            return Vector3(1,0,0), Vector3(0,1,0), Vector3(0,0,1)
        ang = self.world_model.player.rotation
        forward = ang.to_forward_vector()
        right = ang.to_right_vector()
        up = Vector3(0,0,1)  # simplified up
        return forward, right, up

    def what_is_in_front(self, distance: float = 500.0):
        if not self.world_model.player:
            return None
        forward, _, _ = self._get_player_basis()
        origin = self.world_model.player.eye_position
        hit = self.raycaster.raycast(origin, forward, distance)
        return hit

    def what_is_behind(self, distance: float = 500.0):
        if not self.world_model.player:
            return None
        forward, _, _ = self._get_player_basis()
        origin = self.world_model.player.eye_position
        hit = self.raycaster.raycast(origin, forward * -1, distance)
        return hit

    def what_is_left(self, distance: float = 500.0):
        if not self.world_model.player:
            return None
        _, right, _ = self._get_player_basis()
        origin = self.world_model.player.eye_position
        hit = self.raycaster.raycast(origin, right * -1, distance)
        return hit

    def what_is_right(self, distance: float = 500.0):
        if not self.world_model.player:
            return None
        _, right, _ = self._get_player_basis()
        origin = self.world_model.player.eye_position
        hit = self.raycaster.raycast(origin, right, distance)
        return hit

    def what_is_below(self, distance: float = 500.0):
        if not self.world_model.player:
            return None
        origin = self.world_model.player.position
        hit = self.raycaster.raycast(origin, Vector3(0,0,-1), distance)
        return hit

    def what_is_above(self, distance: float = 500.0):
        if not self.world_model.player:
            return None
        origin = self.world_model.player.eye_position
        hit = self.raycaster.raycast(origin, Vector3(0,0,1), distance)
        return hit

    # --- Entity queries ---

    def get_nearest_cube(self) -> Optional[Cube]:
        if not self.world_model.player:
            return None
        return self.world_model.get_nearest_cube(self.world_model.player.position)

    def get_nearest_button(self) -> Optional[Button]:
        if not self.world_model.player:
            return None
        if not self.world_model.buttons:
            return None
        return min(self.world_model.buttons.values(), key=lambda b: b.position.distance_to(self.world_model.player.position))

    def get_nearest_door(self) -> Optional[Door]:
        if not self.world_model.player:
            return None
        if not self.world_model.doors:
            return None
        return min(self.world_model.doors.values(), key=lambda d: d.position.distance_to(self.world_model.player.position))

    def get_entities_in_radius(self, center: Vector3, radius: float, classname_filter: Optional[str] = None) -> List[Entity]:
        result = []
        for ent in self.world_model.entities.values():
            if ent.position.distance_to(center) <= radius:
                if classname_filter and classname_filter.lower() not in ent.classname.lower():
                    continue
                result.append(ent)
        return result

    def get_entities_in_front(self, fov_deg: float = 60.0, max_dist: float = 1000.0) -> List[Entity]:
        if not self.world_model.player:
            return []
        forward, _, _ = self._get_player_basis()
        origin = self.world_model.player.eye_position
        result = []
        for ent in self.world_model.entities.values():
            to_ent = ent.position - origin
            dist = to_ent.length()
            if dist > max_dist or dist < 1e-3:
                continue
            dir_norm = to_ent.normalized()
            dot = forward.dot(dir_norm)
            threshold = math.cos(math.radians(fov_deg/2))
            if dot >= threshold:
                # Check visibility
                if self.raycaster.is_path_clear(origin, ent.position):
                    result.append(ent)
        # Sort by distance
        result.sort(key=lambda e: e.position.distance_to(origin))
        return result

    # --- Obstacle / path queries ---

    def is_obstacle_between(self, a: Vector3, b: Vector3) -> bool:
        return not self.raycaster.is_path_clear(a, b)

    def get_obstacle_between(self, a: Vector3, b: Vector3):
        return self.raycaster.find_obstacle_between(a, b)

    def can_move_to(self, target: Vector3) -> bool:
        if not self.world_model.player:
            return False
        return self.raycaster.is_path_clear(self.world_model.player.position, target)

    def can_reach(self, target: Vector3, max_step_height: float = 32.0, max_drop: float = 256.0) -> bool:
        # Simplified reachability: check path clear and height difference
        if not self.world_model.player:
            return False
        from_pos = self.world_model.player.position
        # Check horizontal path clear at current height + some up
        # First check direct path at slightly elevated height to avoid floor
        check_from = from_pos + Vector3(0,0,10)
        check_to = target + Vector3(0,0,10)
        if not self.raycaster.is_path_clear(check_from, check_to):
            return False
        # Check height difference
        height_diff = target.z - from_pos.z
        if height_diff > max_step_height:
            # Need to check if there's a way up (portal, stairs, etc.)
            # For now, require portal or jump
            # Check if we have active portals that could help
            # Simplified: if height diff too high, not reachable by walking
            return False
        if height_diff < -max_drop:
            # Too big drop, might be dangerous
            return False
        return True

    # --- Portal queries ---

    def can_place_portal_at(self, point: Vector3, normal: Vector3, portal_type: str = "blue") -> Tuple[bool, str]:
        return self.raycaster.can_place_portal(point, normal, portal_type)

    def find_best_portal_surface(self, near: Vector3, desired_exit_near: Optional[Vector3] = None) -> Optional[Surface]:
        candidates = self.raycaster.find_portal_placement_candidates(near, max_dist=1000.0)
        if not candidates:
            return None
        if desired_exit_near:
            # Prefer surfaces that would give good exit towards desired_exit_near?
            # For now just return closest portalable
            pass
        return candidates[0] if candidates else None

    def get_portalable_surfaces_in_view(self, max_dist: float = 1000.0) -> List[Surface]:
        if not self.world_model.player:
            return []
        forward, _, _ = self._get_player_basis()
        origin = self.world_model.player.eye_position
        return self.raycaster.get_visible_surfaces(origin, max_dist, fov_deg=90.0, forward=forward)

    def predict_portal_exit(self, entry_pos: Vector3, entry_portal: Portal, exit_portal: Portal) -> Vector3:
        return entry_portal.transform_position_to_linked(entry_pos, exit_portal)

    # --- Height / distance ---

    def get_distance(self, a: Vector3 | Entity, b: Vector3 | Entity) -> float:
        pos_a = a.position if isinstance(a, Entity) else a
        pos_b = b.position if isinstance(b, Entity) else b
        return pos_a.distance_to(pos_b)

    def get_height_difference(self, a: Vector3 | Entity, b: Vector3 | Entity) -> float:
        pos_a = a.position if isinstance(a, Entity) else a
        pos_b = b.position if isinstance(b, Entity) else b
        return pos_b.z - pos_a.z

    def is_above(self, a: Vector3 | Entity, b: Vector3 | Entity) -> bool:
        return self.get_height_difference(a,b) > 0

    def is_below(self, a: Vector3 | Entity, b: Vector3 | Entity) -> bool:
        return self.get_height_difference(a,b) < 0

    # --- Physical transport ---

    def can_physically_transport_cube(self, cube: Cube, target: Vector3) -> Tuple[bool, str]:
        # Check if path exists for carrying cube
        # Cube needs clearance
        # Simplified: check IsPathClear from cube to target at cube carry height
        carry_height = target + Vector3(0,0,20)
        cube_pos = cube.position + Vector3(0,0,20)
        if not self.raycaster.is_path_clear(cube_pos, carry_height):
            # Find obstacle
            obstacle = self.raycaster.find_obstacle_between(cube_pos, carry_height)
            if obstacle:
                return False, f"Obstacle at {obstacle.position}, entity {obstacle.entity_id}"
            return False, "Path blocked"
        return True, "OK"

    def is_cube_on_button(self, cube: Cube, button: Button, threshold: float = 50.0) -> bool:
        dist = cube.position.distance_to(button.position)
        # Check if cube is roughly above button and low height diff
        height_diff = abs(cube.position.z - button.position.z)
        return dist < threshold and height_diff < 30.0
