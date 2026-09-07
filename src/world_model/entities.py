"""
Entity definitions for Portal 1 World Model
Each object exists in world coordinates.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
from .vector import Vector3, QAngle, Bounds

class EntityType(Enum):
    UNKNOWN = "unknown"
    PLAYER = "player"
    CUBE = "cube"
    BUTTON = "button"
    DOOR = "door"
    PORTAL = "portal"
    TURRET = "turret"
    TRIGGER = "trigger"
    SURFACE = "surface"
    EXIT = "exit"
    PHYSICS = "physics_prop"

@dataclass
class Entity:
    id: int
    classname: str
    position: Vector3
    rotation: QAngle = field(default_factory=QAngle)
    velocity: Vector3 = field(default_factory=Vector3)
    bounds: Optional[Bounds] = None
    active: bool = True
    properties: Dict[str, Any] = field(default_factory=dict)

    def distance_to(self, other: Vector3 | Entity) -> float:
        if isinstance(other, Entity):
            return self.position.distance_to(other.position)
        return self.position.distance_to(other)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "classname": self.classname,
            "position": self.position.to_tuple(),
            "rotation": (self.rotation.pitch, self.rotation.yaw, self.rotation.roll),
            "velocity": self.velocity.to_tuple(),
            "bounds": self.bounds.to_dict() if self.bounds else None,
            "active": self.active,
            "properties": self.properties
        }

@dataclass
class PlayerState(Entity):
    eye_position: Vector3 = field(default_factory=Vector3)
    grounded: bool = True
    alive: bool = True
    crouching: bool = False
    holding_object_id: Optional[int] = None
    health: int = 100
    flags: int = 0  # FL_ONGROUND etc

    def __init__(self, id=1, position=None, rotation=None, velocity=None, eye_position=None, **kwargs):
        super().__init__(
            id=id,
            classname="player",
            position=position or Vector3(),
            rotation=rotation or QAngle(),
            velocity=velocity or Vector3(),
            bounds=kwargs.get("bounds"),
            active=True,
            properties=kwargs.get("properties", {})
        )
        self.eye_position = eye_position or (position + Vector3(0,0,64) if position else Vector3(0,0,64))
        self.grounded = kwargs.get("grounded", True)
        self.alive = kwargs.get("alive", True)
        self.crouching = kwargs.get("crouching", False)
        self.holding_object_id = kwargs.get("holding_object_id")
        self.health = kwargs.get("health", 100)
        self.flags = kwargs.get("flags", 0)

@dataclass
class Cube(Entity):
    held: bool = False
    on_button_id: Optional[int] = None
    mass: float = 20.0
    is_companion: bool = False

    def __init__(self, id, position, **kwargs):
        super().__init__(id=id, classname=kwargs.get("classname", "prop_weighted_cube"),
                         position=position,
                         rotation=kwargs.get("rotation", QAngle()),
                         velocity=kwargs.get("velocity", Vector3()),
                         bounds=kwargs.get("bounds"),
                         active=kwargs.get("active", True),
                         properties=kwargs.get("properties", {}))
        self.held = kwargs.get("held", False)
        self.on_button_id = kwargs.get("on_button_id")
        self.mass = kwargs.get("mass", 20.0)
        self.is_companion = kwargs.get("is_companion", False)

@dataclass
class Button(Entity):
    pressed: bool = False
    required_object_type: str = "cube"
    connected_door_ids: List[int] = field(default_factory=list)
    last_pressed_time: float = 0.0

    def __init__(self, id, position, **kwargs):
        super().__init__(id=id, classname=kwargs.get("classname", "prop_button"),
                         position=position,
                         rotation=kwargs.get("rotation", QAngle()),
                         velocity=Vector3(),
                         bounds=kwargs.get("bounds"),
                         active=kwargs.get("active", True),
                         properties=kwargs.get("properties", {}))
        self.pressed = kwargs.get("pressed", False)
        self.required_object_type = kwargs.get("required_object_type", "cube")
        self.connected_door_ids = kwargs.get("connected_door_ids", [])
        self.last_pressed_time = kwargs.get("last_pressed_time", 0.0)

@dataclass
class Door(Entity):
    open: bool = False
    locked: bool = False
    connected_button_ids: List[int] = field(default_factory=list)
    door_state: int = 0  # 0 closed, 1 opening, 2 open, 3 closing
    target_position: Optional[Vector3] = None

    def __init__(self, id, position, **kwargs):
        super().__init__(id=id, classname=kwargs.get("classname", "func_door"),
                         position=position,
                         rotation=kwargs.get("rotation", QAngle()),
                         velocity=Vector3(),
                         bounds=kwargs.get("bounds"),
                         active=kwargs.get("active", True),
                         properties=kwargs.get("properties", {}))
        self.open = kwargs.get("open", False)
        self.locked = kwargs.get("locked", False)
        self.connected_button_ids = kwargs.get("connected_button_ids", [])
        self.door_state = kwargs.get("door_state", 0)
        self.target_position = kwargs.get("target_position")

@dataclass
class Turret(Entity):
    active: bool = True
    firing: bool = False
    health: int = 100
    target_id: Optional[int] = None

    def __init__(self, id, position, **kwargs):
        super().__init__(id=id, classname=kwargs.get("classname", "npc_portal_turret_floor"),
                         position=position,
                         rotation=kwargs.get("rotation", QAngle()),
                         velocity=Vector3(),
                         bounds=kwargs.get("bounds"),
                         active=kwargs.get("active", True),
                         properties=kwargs.get("properties", {}))
        self.firing = kwargs.get("firing", False)
        self.health = kwargs.get("health", 100)
        self.target_id = kwargs.get("target_id")

@dataclass
class ExitDoor(Entity):
    open: bool = False
    behind_door_id: Optional[int] = None

    def __init__(self, id, position, **kwargs):
        super().__init__(id=id, classname=kwargs.get("classname", "info_target"),
                         position=position,
                         rotation=kwargs.get("rotation", QAngle()),
                         velocity=Vector3(),
                         bounds=kwargs.get("bounds"),
                         active=True,
                         properties=kwargs.get("properties", {}))
        self.open = kwargs.get("open", False)
        self.behind_door_id = kwargs.get("behind_door_id")

@dataclass
class TriggerVolume(Entity):
    trigger_type: str = "generic"
    bounds_trigger: Optional[Bounds] = None
    active: bool = True

    def __init__(self, id, position, **kwargs):
        super().__init__(id=id, classname=kwargs.get("classname", "trigger_multiple"),
                         position=position,
                         rotation=QAngle(),
                         velocity=Vector3(),
                         bounds=kwargs.get("bounds"),
                         active=kwargs.get("active", True),
                         properties=kwargs.get("properties", {}))
        self.trigger_type = kwargs.get("trigger_type", "generic")
        self.bounds_trigger = kwargs.get("bounds_trigger", kwargs.get("bounds"))
