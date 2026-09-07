"""
Surface and Room definitions
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from .vector import Vector3, Bounds

@dataclass
class Surface:
    id: int
    position: Vector3  # center
    normal: Vector3
    bounds: Bounds
    portalable: bool = False
    material: str = ""
    plane_dist: float = 0.0
    area: float = 0.0
    vertices: List[Vector3] = field(default_factory=list)  # polygon vertices

    def __post_init__(self):
        if self.area == 0 and self.vertices:
            # approximate area
            if len(self.vertices) >= 3:
                # simple polygon area approx
                self.area = self.bounds.size().x * self.bounds.size().y
        if self.area == 0:
            sz = self.bounds.size()
            self.area = sz.x * sz.y + sz.y * sz.z + sz.x * sz.z

    def is_large_enough_for_portal(self, portal_width=64, portal_height=64) -> bool:
        # Portal needs at least 64x64 flat area
        size = self.bounds.size()
        # Check if surface is roughly axis-aligned and large enough
        # For simplicity, check max two dimensions
        dims = sorted([size.x, size.y, size.z], reverse=True)
        return dims[0] >= portal_width and dims[1] >= portal_height

    def distance_to_point(self, point: Vector3) -> float:
        # distance from point to plane
        return abs((point - self.position).dot(self.normal))

    def to_dict(self):
        return {
            "id": self.id,
            "position": self.position.to_tuple(),
            "normal": self.normal.to_tuple(),
            "bounds": self.bounds.to_dict(),
            "portalable": self.portalable,
            "material": self.material,
            "area": self.area
        }

@dataclass
class Room:
    id: int
    bounds: Bounds
    surfaces: List[int] = field(default_factory=list)  # surface ids
    entity_ids: List[int] = field(default_factory=list)
    connections: List[int] = field(default_factory=list)  # connected room ids
    floor_z: float = 0.0
    ceiling_z: float = 256.0
    is_elevated: bool = False

    def contains(self, point: Vector3) -> bool:
        return self.bounds.contains(point)

    def to_dict(self):
        return {
            "id": self.id,
            "bounds": self.bounds.to_dict(),
            "surfaces": self.surfaces,
            "entities": self.entity_ids,
            "connections": self.connections,
            "floor_z": self.floor_z,
            "ceiling_z": self.ceiling_z
        }

# Portalable materials in Portal 1 (from materials and surfaces.txt)
PORTALABLE_MATERIALS = [
    "concrete/concrete_modular",
    "metal/metal_modular",
    "concrete/concrete_modular_wall",
    "concrete/concrete_modular_floor",
    "concrete/concrete_modular_ceiling",
    "metal/metal_modular_wall",
    "metal/metal_modular_floor",
    "plastic/plastic_modular",
]

NON_PORTALABLE_MATERIALS = [
    "metal/black_wall_metal",
    "metal/black_floor_metal",
    "glass/glass",
    "tools/toolsnodraw",
    "tools/toolsskip",
    "tools/toolsclip",
    "tools/toolsinvisible",
    "nature/blend",
    "metal/metal_grate",
]

def is_material_portalable(material: str) -> bool:
    mat_lower = material.lower()
    for non in NON_PORTALABLE_MATERIALS:
        if non in mat_lower:
            return False
    for portalable in PORTALABLE_MATERIALS:
        if portalable in mat_lower:
            return True
    # Default: if contains concrete or metal_modular and not black, assume portalable
    if "concrete" in mat_lower and "black" not in mat_lower:
        return True
    if "metal_modular" in mat_lower:
        return True
    # Heuristic: many portal 1 surfaces are portalable unless explicitly marked
    # For safety, return False if unknown
    return False
