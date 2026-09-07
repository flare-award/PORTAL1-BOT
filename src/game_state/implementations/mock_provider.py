"""
Mock Provider - for testing without running Portal 1
Generates synthetic but realistic game states for unit tests and development.
"""
from __future__ import annotations
from typing import List, Optional
import math
import random

from ..provider import GameStateProvider, HitResult, TraceResult
from ...world_model.vector import Vector3, QAngle, Bounds
from ...world_model.entities import PlayerState, Entity, Cube, Button, Door, Turret, ExitDoor, TriggerVolume
from ...world_model.surface import Surface
from ...world_model.portal import Portal

class MockProvider(GameStateProvider):
    """
    Generates a simple test chamber:
    - Room 512x512x256
    - Floor at z=0, ceiling at z=256
    - 4 walls
    - 1 cube at (100,100,20)
    - 1 button at (200,200,0)
    - 1 door at (256, 512, 0) leading to exit
    - Exit at (256, 600, 0)
    - 1 portalable wall at x=512
    - 1 elevated platform at (400,400,128) with cube
    """

    def __init__(self, seed: int = 42):
        self.seed = seed
        random.seed(seed)
        self._player = PlayerState(
            id=1,
            position=Vector3(0, 0, 20),
            rotation=QAngle(0, 0, 0),
            velocity=Vector3(0,0,0),
            eye_position=Vector3(0,0,84),
            grounded=True,
            alive=True
        )
        self._entities: List[Entity] = []
        self._surfaces: List[Surface] = []
        self._portals: List[Portal] = []
        self._build_test_chamber()

    def _build_test_chamber(self):
        # Surfaces
        # Floor
        floor_bounds = Bounds(Vector3(-256,-256,0), Vector3(256,256,0))
        floor = Surface(
            id=0,
            position=Vector3(0,0,0),
            normal=Vector3(0,0,1),
            bounds=floor_bounds,
            portalable=False,
            material="concrete/concrete_modular_floor",
            area=512*512
        )
        self._surfaces.append(floor)

        # Ceiling
        ceil_bounds = Bounds(Vector3(-256,-256,256), Vector3(256,256,256))
        ceiling = Surface(
            id=1,
            position=Vector3(0,0,256),
            normal=Vector3(0,0,-1),
            bounds=ceil_bounds,
            portalable=False,
            material="concrete/concrete_modular_ceiling",
            area=512*512
        )
        self._surfaces.append(ceiling)

        # Walls - 4 walls, 2 portalable
        # Wall at x=256 (east) - portalable
        wall_east_bounds = Bounds(Vector3(256,-256,0), Vector3(260,256,256))
        wall_east = Surface(
            id=2,
            position=Vector3(256,0,128),
            normal=Vector3(-1,0,0),
            bounds=wall_east_bounds,
            portalable=True,
            material="concrete/concrete_modular_wall",
            area=512*256
        )
        self._surfaces.append(wall_east)

        # Wall at x=-256 (west) - portalable
        wall_west_bounds = Bounds(Vector3(-260,-256,0), Vector3(-256,256,256))
        wall_west = Surface(
            id=3,
            position=Vector3(-256,0,128),
            normal=Vector3(1,0,0),
            bounds=wall_west_bounds,
            portalable=True,
            material="concrete/concrete_modular_wall",
            area=512*256
        )
        self._surfaces.append(wall_west)

        # Wall at y=256 (north) - non-portalable (has door)
        wall_north_bounds = Bounds(Vector3(-256,256,0), Vector3(256,260,256))
        wall_north = Surface(
            id=4,
            position=Vector3(0,256,128),
            normal=Vector3(0,-1,0),
            bounds=wall_north_bounds,
            portalable=False,
            material="metal/black_wall_metal",
            area=512*256
        )
        self._surfaces.append(wall_north)

        # Wall at y=-256 (south) - portalable
        wall_south_bounds = Bounds(Vector3(-256,-260,0), Vector3(256,-256,256))
        wall_south = Surface(
            id=5,
            position=Vector3(0,-256,128),
            normal=Vector3(0,1,0),
            bounds=wall_south_bounds,
            portalable=True,
            material="metal/metal_modular_wall",
            area=512*256
        )
        self._surfaces.append(wall_south)

        # Elevated platform at (400,400,128) - actually within room? Let's place at (150,150,64) for test
        plat_bounds = Bounds(Vector3(100,100,64), Vector3(200,200,70))
        platform = Surface(
            id=6,
            position=Vector3(150,150,67),
            normal=Vector3(0,0,1),
            bounds=plat_bounds,
            portalable=False,
            material="metal/metal_modular_floor",
            area=100*100
        )
        self._surfaces.append(platform)

        # Entities
        # Cube
        cube_bounds = Bounds(Vector3(100-16,100-16,20-16), Vector3(100+16,100+16,20+16))
        cube = Cube(id=10, position=Vector3(100,100,20), rotation=QAngle(0,0,0), bounds=cube_bounds, classname="prop_weighted_cube")
        self._entities.append(cube)

        # Button
        button_bounds = Bounds(Vector3(200-32,200-32,0), Vector3(200+32,200+32,10))
        button = Button(id=11, position=Vector3(200,200,0), rotation=QAngle(0,0,0), bounds=button_bounds, classname="prop_button", pressed=False, connected_door_ids=[12])
        self._entities.append(button)

        # Door
        door_bounds = Bounds(Vector3(-32,256-16,0), Vector3(32,256+16,128))
        door = Door(id=12, position=Vector3(0,256,0), rotation=QAngle(0,0,0), bounds=door_bounds, classname="func_door", open=False, connected_button_ids=[11], door_state=0)
        self._entities.append(door)

        # Exit
        exit_bounds = Bounds(Vector3(-32,600-16,0), Vector3(32,600+16,128))
        exit_door = ExitDoor(id=13, position=Vector3(0,600,0), rotation=QAngle(0,0,0), bounds=exit_bounds, classname="info_target", open=False, behind_door_id=12)
        self._entities.append(exit_door)

        # Second cube on elevated platform (requires portal)
        cube2_bounds = Bounds(Vector3(150-16,150-16,67+16), Vector3(150+16,150+16,67+16+32))
        cube2 = Cube(id=14, position=Vector3(150,150,83), rotation=QAngle(0,0,0), bounds=cube2_bounds, classname="prop_weighted_cube")
        self._entities.append(cube2)

        # Turret for hazard test
        turret_bounds = Bounds(Vector3(-100-16,200-16,0), Vector3(-100+16,200+16,64))
        turret = Turret(id=15, position=Vector3(-100,200,0), rotation=QAngle(0,90,0), bounds=turret_bounds, classname="npc_portal_turret_floor", active=True)
        self._entities.append(turret)

    def get_player_state(self) -> PlayerState:
        return self._player

    def set_player_position(self, pos: Vector3, ang: Optional[QAngle] = None):
        self._player.position = pos
        self._player.eye_position = pos + Vector3(0,0,64)
        if ang:
            self._player.rotation = ang

    def get_entities(self) -> List[Entity]:
        return self._entities

    def get_world_geometry(self) -> List[Surface]:
        return self._surfaces

    def get_portals(self) -> List[Portal]:
        return self._portals

    def place_portal(self, portal_type: str, position: Vector3, normal: Vector3) -> Portal:
        # Remove existing portal of same type
        self._portals = [p for p in self._portals if p.portal_type != portal_type]
        portal_id = 100 if portal_type == "blue" else 101
        # Calculate basis
        forward = normal * -1
        # Find right and up
        if abs(normal.z) < 0.9:
            up = Vector3(0,0,1)
        else:
            up = Vector3(1,0,0)
        right = forward.cross(up).normalized()
        up = right.cross(forward).normalized()

        portal = Portal(
            id=portal_id,
            position=position,
            portal_type=portal_type,
            normal=normal,
            forward=forward,
            right=right,
            up=up,
            active=True,
            width=64,
            height=96
        )
        # Link if both exist
        for other in self._portals:
            if other.portal_type != portal_type:
                portal.linked_portal_id = other.id
                other.linked_portal_id = portal.id

        self._portals.append(portal)
        return portal

    def raycast(self, origin: Vector3, direction: Vector3, max_distance: float = 8192.0, ignore_entity_id: Optional[int] = None) -> HitResult:
        dir_norm = direction.normalized()
        closest_dist = max_distance
        closest_hit = None

        # Check surfaces
        for surf in self._surfaces:
            denom = dir_norm.dot(surf.normal)
            if abs(denom) < 1e-6:
                continue
            t = (surf.position - origin).dot(surf.normal) / denom
            if t < 0 or t > closest_dist:
                continue
            hit_pos = origin + dir_norm * t
            # Check bounds with some tolerance
            if not surf.bounds.contains(hit_pos):
                # Check if within 10 units of bounds (for simplified test)
                expanded = surf.bounds.expand(10)
                if not expanded.contains(hit_pos):
                    continue
            closest_dist = t
            closest_hit = HitResult(
                hit=True,
                position=hit_pos,
                normal=surf.normal,
                surface_id=surf.id,
                distance=t,
                material=surf.material,
                fraction=t/max_distance if max_distance>0 else 1.0
            )

        # Check entities
        for ent in self._entities:
            if ent.id == ignore_entity_id:
                continue
            if not ent.bounds:
                continue
            # Ray-AABB slab
            tmin = 0.0
            tmax = max_distance
            for axis in ['x','y','z']:
                o = getattr(origin, axis)
                d = getattr(dir_norm, axis)
                mn = getattr(ent.bounds.mins, axis)
                mx = getattr(ent.bounds.maxs, axis)
                if abs(d) < 1e-6:
                    if o < mn or o > mx:
                        tmin = max_distance+1
                        break
                else:
                    t1 = (mn - o) / d
                    t2 = (mx - o) / d
                    if t1 > t2:
                        t1,t2 = t2,t1
                    tmin = max(tmin, t1)
                    tmax = min(tmax, t2)
                    if tmin > tmax:
                        break
            if tmin <= tmax and 0 <= tmin <= closest_dist:
                closest_dist = tmin
                closest_hit = HitResult(
                    hit=True,
                    position=origin + dir_norm * tmin,
                    normal=Vector3(0,0,1),
                    entity_id=ent.id,
                    distance=tmin,
                    fraction=tmin/max_distance if max_distance>0 else 1.0
                )

        if closest_hit:
            return closest_hit

        return HitResult(
            hit=False,
            position=origin + dir_norm * max_distance,
            normal=Vector3(0,0,0),
            distance=max_distance,
            fraction=1.0
        )

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

    def simulate_button_press(self, button_id: int, pressed: bool):
        for ent in self._entities:
            if ent.id == button_id and isinstance(ent, Button):
                ent.pressed = pressed
                # Open/close linked doors
                for door_id in ent.connected_door_ids:
                    for d in self._entities:
                        if d.id == door_id and isinstance(d, Door):
                            d.open = pressed
                            d.door_state = 2 if pressed else 0
