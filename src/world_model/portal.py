"""
Portal system - spatial modeling of portals
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import math
from .vector import Vector3, QAngle, Bounds
from .entities import Entity

@dataclass
class Portal(Entity):
    portal_type: str = "blue"  # blue or orange
    normal: Vector3 = field(default_factory=lambda: Vector3(0,0,1))
    forward: Vector3 = field(default_factory=lambda: Vector3(1,0,0))
    right: Vector3 = field(default_factory=lambda: Vector3(0,1,0))
    up: Vector3 = field(default_factory=lambda: Vector3(0,0,1))
    linked_portal_id: Optional[int] = None
    surface_id: Optional[int] = None
    active: bool = False
    width: float = 64.0
    height: float = 96.0

    def __init__(self, id, position, portal_type="blue", **kwargs):
        super().__init__(id=id, classname="prop_portal",
                         position=position,
                         rotation=kwargs.get("rotation", QAngle()),
                         velocity=Vector3(),
                         bounds=kwargs.get("bounds"),
                         active=kwargs.get("active", False),
                         properties=kwargs.get("properties", {}))
        self.portal_type = portal_type
        self.normal = kwargs.get("normal", Vector3(0,0,1))
        self.forward = kwargs.get("forward", self.normal * -1)
        self.right = kwargs.get("right", Vector3(0,1,0))
        self.up = kwargs.get("up", Vector3(0,0,1))
        self.linked_portal_id = kwargs.get("linked_portal_id")
        self.surface_id = kwargs.get("surface_id")
        self.active = kwargs.get("active", False)
        self.width = kwargs.get("width", 64.0)
        self.height = kwargs.get("height", 96.0)

    def get_transform_matrix(self):
        """
        Returns transform that converts world to portal local space
        For portal transformation we need basis vectors
        """
        # Portal's coordinate system: forward = -normal (direction out of portal)
        # right, up are portal's local X,Y
        # World to local: dot with basis
        return {
            "origin": self.position,
            "forward": self.forward,
            "right": self.right,
            "up": self.up
        }

    def world_to_local(self, world_pos: Vector3) -> Vector3:
        # Translate to portal origin, then project onto portal basis
        delta = world_pos - self.position
        return Vector3(
            delta.dot(self.right),
            delta.dot(self.up),
            delta.dot(self.forward)
        )

    def local_to_world(self, local_pos: Vector3) -> Vector3:
        # local x=right, y=up, z=forward
        return self.position + self.right * local_pos.x + self.up * local_pos.y + self.forward * local_pos.z

    def transform_position_to_linked(self, pos: Vector3, linked: Portal) -> Vector3:
        """
        Transform position from entry portal to exit portal
        Position A -> Portal A -> Portal B -> Position B
        """
        local = self.world_to_local(pos)
        # In portal traversal, forward is flipped, and right may be flipped depending on orientation
        # Simplified: mirror forward, keep right/up but account for portal rotation difference
        # For Portal 1, portals maintain orientation: entering one exits with same relative orientation
        # but forward is inverted

        # Flip forward (z) because you go through
        local_mirrored = Vector3(local.x, local.y, -local.z)

        # Now convert to linked portal's world space
        # Need to account for linked portal's rotation relative to this portal
        # Simplified version: use linked's basis directly
        world_exit = linked.local_to_world(local_mirrored)
        return world_exit

    def transform_direction_to_linked(self, direction: Vector3, linked: Portal) -> Vector3:
        """
        Transform direction vector (velocity, look direction) through portals
        """
        # Decompose direction into portal basis
        local_dir = Vector3(
            direction.dot(self.right),
            direction.dot(self.up),
            direction.dot(self.forward)
        )
        # Flip forward
        local_dir_flipped = Vector3(local_dir.x, local_dir.y, -local_dir.z)

        # Recompose in linked portal basis
        world_dir = linked.right * local_dir_flipped.x + linked.up * local_dir_flipped.y + linked.forward * local_dir_flipped.z
        return world_dir.normalized()

    def can_link_to(self, other: Portal) -> bool:
        if not self.active or not other.active:
            return False
        if self.portal_type == other.portal_type:
            return False
        if self.id == other.id:
            return False
        return True

    def get_exit_velocity(self, entry_velocity: Vector3, linked: Portal) -> Vector3:
        speed = entry_velocity.length()
        transformed_dir = self.transform_direction_to_linked(entry_velocity.normalized(), linked)
        return transformed_dir * speed

    def to_dict(self):
        base = super().to_dict()
        base.update({
            "portal_type": self.portal_type,
            "normal": self.normal.to_tuple(),
            "linked_portal_id": self.linked_portal_id,
            "surface_id": self.surface_id,
            "active": self.active
        })
        return base

@dataclass
class PortalPair:
    blue: Optional[Portal] = None
    orange: Optional[Portal] = None

    def is_linked(self) -> bool:
        return self.blue is not None and self.orange is not None and self.blue.active and self.orange.active

    def get_other(self, portal: Portal) -> Optional[Portal]:
        if portal.portal_type == "blue":
            return self.orange
        else:
            return self.blue

@dataclass
class PortalPlacementCandidate:
    surface_id: int
    position: Vector3
    normal: Vector3
    score: float = 0.0
    reason: str = ""

    def to_dict(self):
        return {
            "surface_id": self.surface_id,
            "position": self.position.to_tuple(),
            "normal": self.normal.to_tuple(),
            "score": self.score,
            "reason": self.reason
        }
