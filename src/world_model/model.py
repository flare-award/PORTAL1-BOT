"""
WorldModel - central 3D scene representation
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import time
from .vector import Vector3, QAngle, Bounds
from .entities import PlayerState, Entity, Cube, Button, Door, Turret, ExitDoor, TriggerVolume
from .surface import Surface, Room
from .portal import Portal

@dataclass
class Goal:
    type: str  # reach_exit, activate_button, get_cube, place_portal, reach_position, etc.
    target_id: Optional[int] = None
    target_position: Optional[Vector3] = None
    description: str = ""
    priority: int = 0
    completed: bool = False

    def to_dict(self):
        return {
            "type": self.type,
            "target_id": self.target_id,
            "target_position": self.target_position.to_tuple() if self.target_position else None,
            "description": self.description,
            "priority": self.priority,
            "completed": self.completed
        }

@dataclass
class Connection:
    id: int
    from_room_id: int
    to_room_id: int
    type: str  # door, portal, corridor, elevator
    position: Vector3
    required_entity_id: Optional[int] = None  # e.g., door id
    traversable: bool = True

@dataclass
class WorldModel:
    player: Optional[PlayerState] = None
    entities: Dict[int, Entity] = field(default_factory=dict)
    surfaces: Dict[int, Surface] = field(default_factory=dict)
    portals: Dict[int, Portal] = field(default_factory=dict)
    doors: Dict[int, Door] = field(default_factory=dict)
    buttons: Dict[int, Button] = field(default_factory=dict)
    cubes: Dict[int, Cube] = field(default_factory=dict)
    turrets: Dict[int, Turret] = field(default_factory=dict)
    triggers: Dict[int, TriggerVolume] = field(default_factory=dict)
    rooms: Dict[int, Room] = field(default_factory=dict)
    connections: Dict[int, Connection] = field(default_factory=dict)
    exits: Dict[int, ExitDoor] = field(default_factory=dict)
    goals: List[Goal] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    map_name: str = ""
    raw_bsp_data: Optional[Any] = None

    def update_timestamp(self):
        self.timestamp = time.time()

    def get_entity(self, entity_id: int) -> Optional[Entity]:
        return self.entities.get(entity_id)

    def get_all_entities_of_type(self, classname_substring: str) -> List[Entity]:
        return [e for e in self.entities.values() if classname_substring.lower() in e.classname.lower()]

    def get_nearest_entity(self, position: Vector3, entity_type: str = None) -> Optional[Entity]:
        candidates = self.entities.values()
        if entity_type:
            candidates = [e for e in candidates if entity_type.lower() in e.classname.lower()]
        if not candidates:
            return None
        return min(candidates, key=lambda e: e.position.distance_to(position))

    def get_nearest_cube(self, from_position: Vector3 = None) -> Optional[Cube]:
        if from_position is None:
            if self.player:
                from_position = self.player.position
            else:
                from_position = Vector3(0,0,0)
        if not self.cubes:
            return None
        return min(self.cubes.values(), key=lambda c: c.position.distance_to(from_position))

    def get_active_portals(self) -> List[Portal]:
        return [p for p in self.portals.values() if p.active]

    def get_portal_pair(self):
        blue = next((p for p in self.portals.values() if p.portal_type == "blue" and p.active), None)
        orange = next((p for p in self.portals.values() if p.portal_type == "orange" and p.active), None)
        return blue, orange

    def add_entity(self, entity: Entity):
        self.entities[entity.id] = entity
        # Also index into typed dicts
        if isinstance(entity, Cube):
            self.cubes[entity.id] = entity
        elif isinstance(entity, Button):
            self.buttons[entity.id] = entity
        elif isinstance(entity, Door):
            self.doors[entity.id] = entity
        elif isinstance(entity, Portal):
            self.portals[entity.id] = entity
        elif isinstance(entity, Turret):
            self.turrets[entity.id] = entity
        elif isinstance(entity, TriggerVolume):
            self.triggers[entity.id] = entity
        elif isinstance(entity, ExitDoor):
            self.exits[entity.id] = entity

    def remove_entity(self, entity_id: int):
        self.entities.pop(entity_id, None)
        self.cubes.pop(entity_id, None)
        self.buttons.pop(entity_id, None)
        self.doors.pop(entity_id, None)
        self.portals.pop(entity_id, None)
        self.turrets.pop(entity_id, None)
        self.triggers.pop(entity_id, None)
        self.exits.pop(entity_id, None)

    def to_dict(self) -> dict:
        return {
            "player": self.player.to_dict() if self.player else None,
            "entities": {k: v.to_dict() for k,v in self.entities.items()},
            "surfaces": {k: v.to_dict() for k,v in self.surfaces.items()},
            "portals": {k: v.to_dict() for k,v in self.portals.items()},
            "doors": {k: v.to_dict() for k,v in self.doors.items()},
            "buttons": {k: v.to_dict() for k,v in self.buttons.items()},
            "cubes": {k: v.to_dict() for k,v in self.cubes.items()},
            "rooms": {k: v.to_dict() for k,v in self.rooms.items()},
            "goals": [g.to_dict() for g in self.goals],
            "map_name": self.map_name,
            "timestamp": self.timestamp
        }

    def summary(self) -> str:
        lines = []
        lines.append(f"=== WorldModel Summary ===")
        lines.append(f"Map: {self.map_name}")
        lines.append(f"Timestamp: {self.timestamp}")
        if self.player:
            lines.append(f"Player: pos={self.player.position}, eye={self.player.eye_position}, grounded={self.player.grounded}, alive={self.player.alive}")
        lines.append(f"Entities: {len(self.entities)} total")
        lines.append(f"  Cubes: {len(self.cubes)}")
        lines.append(f"  Buttons: {len(self.buttons)}")
        lines.append(f"  Doors: {len(self.doors)}")
        lines.append(f"  Portals: {len(self.portals)} (active: {len(self.get_active_portals())})")
        lines.append(f"  Turrets: {len(self.turrets)}")
        lines.append(f"  Surfaces: {len(self.surfaces)}")
        lines.append(f"  Rooms: {len(self.rooms)}")
        lines.append(f"  Goals: {len(self.goals)}")
        for goal in self.goals:
            lines.append(f"    Goal: {goal.type} - {goal.description} - completed={goal.completed}")
        return "\n".join(lines)
