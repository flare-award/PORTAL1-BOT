"""
3D Math primitives for Portal 1 Bot
World coordinates: Source Engine uses X forward, Y left, Z up? Actually Source: X east, Y north, Z up.
We use standard right-handed with Z up to match Source.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Tuple

@dataclass
class Vector3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, other: Vector3) -> Vector3:
        return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vector3) -> Vector3:
        return Vector3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Vector3:
        return Vector3(self.x * scalar, self.y * scalar, self.z * scalar)

    def __truediv__(self, scalar: float) -> Vector3:
        return Vector3(self.x / scalar, self.y / scalar, self.z / scalar)

    def dot(self, other: Vector3) -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: Vector3) -> Vector3:
        return Vector3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x
        )

    def length(self) -> float:
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)

    def length_sqr(self) -> float:
        return self.x**2 + self.y**2 + self.z**2

    def normalized(self) -> Vector3:
        l = self.length()
        if l < 1e-8:
            return Vector3(0,0,0)
        return self / l

    def distance_to(self, other: Vector3) -> float:
        return (self - other).length()

    def to_tuple(self) -> Tuple[float,float,float]:
        return (self.x, self.y, self.z)

    @staticmethod
    def from_tuple(t: Tuple[float,float,float]) -> Vector3:
        return Vector3(t[0], t[1], t[2])

    def __repr__(self):
        return f"Vector3({self.x:.2f}, {self.y:.2f}, {self.z:.2f})"

@dataclass
class QAngle:
    pitch: float = 0.0  # x
    yaw: float = 0.0    # y
    roll: float = 0.0   # z

    def to_forward_vector(self) -> Vector3:
        # Source engine angles to forward
        pitch_rad = math.radians(self.pitch)
        yaw_rad = math.radians(self.yaw)
        cp = math.cos(pitch_rad)
        sp = math.sin(pitch_rad)
        cy = math.cos(yaw_rad)
        sy = math.sin(yaw_rad)
        # Source: forward = cp*cy, cp*sy, -sp
        return Vector3(cp * cy, cp * sy, -sp).normalized()

    def to_right_vector(self) -> Vector3:
        # Right vector from angles
        pitch_rad = math.radians(self.pitch)
        yaw_rad = math.radians(self.yaw)
        roll_rad = math.radians(self.roll)
        # Simplified: yaw only for right on ground plane
        # Right = -sin(yaw), cos(yaw), 0
        return Vector3(-math.sin(math.radians(self.yaw)), math.cos(math.radians(self.yaw)), 0).normalized()

    def to_up_vector(self) -> Vector3:
        fwd = self.to_forward_vector()
        right = self.to_right_vector()
        # up = right cross forward? Actually Source: up = ?
        # Approximate
        return right.cross(fwd).normalized()

    def __repr__(self):
        return f"QAngle(p={self.pitch:.1f}, y={self.yaw:.1f}, r={self.roll:.1f})"

@dataclass
class Bounds:
    mins: Vector3
    maxs: Vector3

    def center(self) -> Vector3:
        return (self.mins + self.maxs) * 0.5

    def size(self) -> Vector3:
        return self.maxs - self.mins

    def contains(self, point: Vector3) -> bool:
        return (self.mins.x <= point.x <= self.maxs.x and
                self.mins.y <= point.y <= self.maxs.y and
                self.mins.z <= point.z <= self.maxs.z)

    def intersects(self, other: Bounds) -> bool:
        return not (self.maxs.x < other.mins.x or self.mins.x > other.maxs.x or
                    self.maxs.y < other.mins.y or self.mins.y > other.maxs.y or
                    self.maxs.z < other.mins.z or self.mins.z > other.maxs.z)

    def expand(self, amount: float) -> Bounds:
        v = Vector3(amount, amount, amount)
        return Bounds(self.mins - v, self.maxs + v)

    def to_dict(self):
        return {"mins": self.mins.to_tuple(), "maxs": self.maxs.to_tuple()}

    @staticmethod
    def from_center_radius(center: Vector3, radius: float) -> Bounds:
        r = Vector3(radius, radius, radius)
        return Bounds(center - r, center + r)

    def __repr__(self):
        return f"Bounds(mins={self.mins}, maxs={self.maxs})"
