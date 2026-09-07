"""
BSP Provider - parses Portal 1 .bsp files to get static world geometry
Works offline without running game. Gives walls, floors, ceilings, portalable surfaces.

BSP format: https://developer.valvesoftware.com/wiki/Source_BSP_File_Format
We parse at least:
- Lump 0: Entities (text)
- Lump 1: Planes
- Lump 3: Vertexes
- Lump 7: Faces
- Lump 6: Texinfo
- Lump 2: Texdata + 43 TexdataStringData
"""
from __future__ import annotations
import struct
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import os

from ..provider import GameStateProvider, HitResult, TraceResult
from ...world_model.vector import Vector3, QAngle, Bounds
from ...world_model.entities import PlayerState, Entity, Cube, Button, Door, Turret, ExitDoor, TriggerVolume
from ...world_model.surface import Surface, is_material_portalable
from ...world_model.portal import Portal

# BSP Header structures
# dheader_t: ident (4), version (4), lumps[64] (each 16 bytes: offset, length, version, fourCC), mapRevision (4)
HEADER_LUMPS = 64
LUMP_ENTITIES = 0
LUMP_PLANES = 1
LUMP_TEXDATA = 2
LUMP_VERTEXES = 3
LUMP_NODES = 5
LUMP_TEXINFO = 6
LUMP_FACES = 7
LUMP_LEAFS = 10
LUMP_EDGES = 12
LUMP_SURFEDGES = 13
LUMP_MODELS = 14
LUMP_BRUSHES = 18
LUMP_BRUSHSIDES = 19
LUMP_TEXDATA_STRING_DATA = 43
LUMP_TEXDATA_STRING_TABLE = 44

def parse_entities_lump(data: bytes) -> List[Dict[str, str]]:
    """
    Entities lump is a null-terminated string with keyvalues in Valve format:
    {
    "classname" "worldspawn"
    "mapversion" "400"
    }
    {
    "origin" "0 0 0"
    "classname" "prop_weighted_cube"
    ...
    }
    """
    text = data.decode('utf-8', errors='ignore')
    # Remove null terminator
    text = text.strip('\x00')
    entities = []
    # Regex to find { ... } blocks
    # Each block contains "key" "value" pairs
    pattern = re.compile(r'\{([^}]*)\}', re.DOTALL)
    kv_pattern = re.compile(r'"([^"]+)"\s+"([^"]*)"')
    for match in pattern.finditer(text):
        block = match.group(1)
        ent = {}
        for kv_match in kv_pattern.finditer(block):
            key = kv_match.group(1)
            value = kv_match.group(2)
            ent[key] = value
        if ent:
            entities.append(ent)
    return entities

def parse_vector(s: str) -> Vector3:
    try:
        parts = s.strip().split()
        if len(parts) >= 3:
            return Vector3(float(parts[0]), float(parts[1]), float(parts[2]))
    except:
        pass
    return Vector3(0,0,0)

def parse_angle(s: str) -> QAngle:
    try:
        parts = s.strip().split()
        if len(parts) >= 3:
            return QAngle(float(parts[0]), float(parts[1]), float(parts[2]))
    except:
        pass
    return QAngle(0,0,0)

class BSPFile:
    def __init__(self, path: Path):
        self.path = path
        self.lumps = []
        self.entities_raw: List[Dict[str,str]] = []
        self.planes: List[Tuple[Vector3, float]] = []  # normal, dist
        self.vertexes: List[Vector3] = []
        self.faces: List[dict] = []
        self.texinfo: List[dict] = []
        self.texdata: List[dict] = []
        self.texdata_string_table: List[int] = []
        self.texdata_string_data: bytes = b""
        self.materials: List[str] = []

    def load(self):
        with open(self.path, 'rb') as f:
            # Header
            ident = struct.unpack('i', f.read(4))[0]
            # VBSP = 0x50534256 little endian
            if ident != 0x50534256:
                raise ValueError(f"Not a VBSP file: ident={hex(ident)}")
            version = struct.unpack('i', f.read(4))[0]
            # Lumps
            lumps = []
            for _ in range(HEADER_LUMPS):
                offset, length, ver, fourcc = struct.unpack('iiii', f.read(16))
                lumps.append((offset, length, ver, fourcc))
            map_rev = struct.unpack('i', f.read(4))[0]
            self.lumps = lumps

            # Read each lump we need
            # Entities
            off, length, _, _ = lumps[LUMP_ENTITIES]
            if length > 0:
                f.seek(off)
                data = f.read(length)
                self.entities_raw = parse_entities_lump(data)

            # Planes: struct dplane_t { Vector normal; float dist; int type; }
            off, length, _, _ = lumps[LUMP_PLANES]
            if length > 0:
                f.seek(off)
                count = length // 20  # 3*4 +4+4
                for _ in range(count):
                    nx, ny, nz, dist, typ = struct.unpack('ffffi', f.read(20))
                    self.planes.append((Vector3(nx,ny,nz), dist))

            # Vertexes: Vector
            off, length, _, _ = lumps[LUMP_VERTEXES]
            if length > 0:
                f.seek(off)
                count = length // 12
                for _ in range(count):
                    x,y,z = struct.unpack('fff', f.read(12))
                    self.vertexes.append(Vector3(x,y,z))

            # TexdataStringData
            off, length, _, _ = lumps[LUMP_TEXDATA_STRING_DATA]
            if length > 0:
                f.seek(off)
                self.texdata_string_data = f.read(length)

            # TexdataStringTable: array of ints offsets into string data
            off, length, _, _ = lumps[LUMP_TEXDATA_STRING_TABLE]
            if length > 0:
                f.seek(off)
                count = length // 4
                for _ in range(count):
                    idx = struct.unpack('i', f.read(4))[0]
                    self.texdata_string_table.append(idx)

            # Resolve materials
            self.materials = []
            for offset in self.texdata_string_table:
                # read null-terminated string from texdata_string_data at offset
                if offset < len(self.texdata_string_data):
                    end = self.texdata_string_data.find(b'\x00', offset)
                    if end != -1:
                        mat = self.texdata_string_data[offset:end].decode('utf-8', errors='ignore')
                        self.materials.append(mat)
                    else:
                        self.materials.append("")

            # Texdata: struct dtexdata_t { Vector reflectivity; int nameStringTableID; int width,height; int view_width,view_height; }
            # Actually 32 bytes
            off, length, _, _ = lumps[LUMP_TEXDATA]
            if length > 0:
                f.seek(off)
                count = length // 32
                for _ in range(count):
                    # reflectivity 3 floats, then 5 ints
                    data = f.read(32)
                    if len(data) < 32:
                        break
                    # unpack
                    # We only need nameStringTableID which is at offset 12
                    # struct: float x,y,z, int nameID, int width,height,view_width,view_height
                    rx, ry, rz, name_id, w, h, vw, vh = struct.unpack('fffiiiii', data)
                    self.texdata.append({"name_id": name_id, "width": w, "height": h})

            # Texinfo: struct texinfo_t { float textureVecs[2][4]; float lightmapVecs[2][4]; int flags; int texdata; }
            # 72 bytes
            off, length, _, _ = lumps[LUMP_TEXINFO]
            if length > 0:
                f.seek(off)
                count = length // 72
                for _ in range(count):
                    data = f.read(72)
                    if len(data) < 72:
                        break
                    # 8 floats for textureVecs, 8 for lightmapVecs, then 2 ints
                    # We'll parse only texdata index
                    # Last 8 bytes: flags, texdata
                    flags, texdata_idx = struct.unpack('ii', data[64:72])
                    # textureVecs for normal calculation?
                    # For simplicity, extract normal from textureVecs? Actually plane normal is from plane
                    self.texinfo.append({"flags": flags, "texdata": texdata_idx})

            # Faces: dface_t 56 bytes
            # struct: int planenum, side, onNode, firstedge, numedges, texinfo, dispinfo, surfaceFogVolumeID, styles[4], lightofs, area, LightmapTextureMinsInLuxels[2], LightmapTextureSizeInLuxels[2], origFace, numPrims, firstPrimID, smoothingGroups
            off, length, _, _ = lumps[LUMP_FACES]
            if length > 0:
                f.seek(off)
                count = length // 56
                for _ in range(count):
                    data = f.read(56)
                    if len(data) < 56:
                        break
                    # unpack first fields
                    planenum, side, onNode, firstedge, numedges, texinfo_idx, dispinfo, surfaceFogVolumeID = struct.unpack('iiiiiiii', data[0:32])
                    # styles 4 bytes
                    # lightofs int
                    # area float
                    # etc.
                    lightofs = struct.unpack('i', data[36:40])[0]
                    area = struct.unpack('f', data[40:44])[0]
                    # origFace etc not needed
                    self.faces.append({
                        "planenum": planenum,
                        "side": side,
                        "firstedge": firstedge,
                        "numedges": numedges,
                        "texinfo": texinfo_idx,
                        "area": area
                    })

class BSPProvider(GameStateProvider):
    """
    Provides static world geometry from BSP files.
    Can also provide entity spawn positions from entities lump.
    Does NOT provide live player state or dynamic entities - use AggregatedProvider for that.
    """

    def __init__(self, bsp_path: Optional[Path] = None, map_name: str = "testchmb_a_00"):
        self.bsp_path = Path(bsp_path) if bsp_path else None
        self.map_name = map_name
        self.bsp_file: Optional[BSPFile] = None
        self.surfaces: List[Surface] = []
        self.spawn_entities: List[Entity] = []
        self._loaded = False

    def load_bsp(self, path: Path):
        self.bsp_path = path
        self.bsp_file = BSPFile(path)
        self.bsp_file.load()
        self._parse_surfaces()
        self._parse_entities()
        self._loaded = True
        print(f"[BSPProvider] Loaded {path} - {len(self.surfaces)} surfaces, {len(self.spawn_entities)} spawn entities")

    def _parse_surfaces(self):
        self.surfaces = []
        if not self.bsp_file:
            return
        # For each face, create a Surface
        for idx, face in enumerate(self.bsp_file.faces):
            planenum = face["planenum"]
            if planenum < 0 or planenum >= len(self.bsp_file.planes):
                continue
            normal, dist = self.bsp_file.planes[planenum]
            if face["side"] != 0:
                normal = normal * -1
                dist = -dist

            # Get material
            texinfo_idx = face["texinfo"]
            material = "unknown"
            portalable = False
            if texinfo_idx >= 0 and texinfo_idx < len(self.bsp_file.texinfo):
                texinfo = self.bsp_file.texinfo[texinfo_idx]
                texdata_idx = texinfo["texdata"]
                if texdata_idx >= 0 and texdata_idx < len(self.bsp_file.texdata):
                    texdata = self.bsp_file.texdata[texdata_idx]
                    name_id = texdata["name_id"]
                    if name_id >= 0 and name_id < len(self.bsp_file.materials):
                        material = self.bsp_file.materials[name_id]
                        portalable = is_material_portalable(material)

            # Position = normal * dist (point on plane)
            pos = normal * dist

            # Bounds: we don't have vertices without edges lumps, so approximate from plane and area
            # Use a default bounds around pos
            # For better bounds, we would need to parse edges and surfedges
            # Here we approximate with 128x128 square on plane
            # Determine two perpendicular vectors to normal
            # Find a vector not parallel to normal
            if abs(normal.x) < 0.9:
                arbitrary = Vector3(1,0,0)
            else:
                arbitrary = Vector3(0,1,0)
            right = normal.cross(arbitrary).normalized()
            up = normal.cross(right).normalized()
            # Create bounds 128x128
            half = 64.0
            # Four corners
            c1 = pos + right * half + up * half
            c2 = pos + right * half - up * half
            c3 = pos - right * half + up * half
            c4 = pos - right * half - up * half
            mins = Vector3(
                min(c1.x, c2.x, c3.x, c4.x),
                min(c1.y, c2.y, c3.y, c4.y),
                min(c1.z, c2.z, c3.z, c4.z)
            )
            maxs = Vector3(
                max(c1.x, c2.x, c3.x, c4.x),
                max(c1.y, c2.y, c3.y, c4.y),
                max(c1.z, c2.z, c3.z, c4.z)
            )
            bounds = Bounds(mins, maxs)

            surf = Surface(
                id=idx,
                position=pos,
                normal=normal,
                bounds=bounds,
                portalable=portalable,
                material=material,
                plane_dist=dist,
                area=face.get("area", 0.0),
                vertices=[c1,c2,c3,c4]
            )
            self.surfaces.append(surf)

    def _parse_entities(self):
        self.spawn_entities = []
        if not self.bsp_file:
            return
        for idx, ent_dict in enumerate(self.bsp_file.entities_raw):
            classname = ent_dict.get("classname", "unknown")
            origin_str = ent_dict.get("origin", "0 0 0")
            angles_str = ent_dict.get("angles", "0 0 0")
            pos = parse_vector(origin_str)
            ang = parse_angle(angles_str)

            # Create appropriate entity type
            entity: Entity
            bounds = Bounds(pos - Vector3(16,16,16), pos + Vector3(16,16,16))
            if "cube" in classname or "prop_physics" in classname:
                entity = Cube(id=idx, position=pos, rotation=ang, bounds=bounds, classname=classname, properties=ent_dict)
            elif "button" in classname:
                entity = Button(id=idx, position=pos, rotation=ang, bounds=bounds, classname=classname, properties=ent_dict)
            elif "door" in classname:
                entity = Door(id=idx, position=pos, rotation=ang, bounds=bounds, classname=classname, properties=ent_dict)
            elif "turret" in classname:
                entity = Turret(id=idx, position=pos, rotation=ang, bounds=bounds, classname=classname, properties=ent_dict)
            elif "portal" in classname and "prop_portal" in classname:
                entity = Portal(id=idx, position=pos, rotation=ang, bounds=bounds, active=False, properties=ent_dict)
            elif "trigger" in classname:
                entity = TriggerVolume(id=idx, position=pos, classname=classname, bounds=bounds, properties=ent_dict, trigger_type=classname)
            else:
                entity = Entity(id=idx, classname=classname, position=pos, rotation=ang, bounds=bounds, properties=ent_dict)

            self.spawn_entities.append(entity)

    def get_player_state(self) -> PlayerState:
        # From BSP, find info_player_start
        for ent in self.spawn_entities:
            if ent.classname == "info_player_start":
                pos = ent.position
                eye = pos + Vector3(0,0,64)
                return PlayerState(id=1, position=pos, rotation=ent.rotation, eye_position=eye, grounded=True, alive=True)
        # Default
        return PlayerState(id=1, position=Vector3(0,0,0), rotation=QAngle(0,0,0), eye_position=Vector3(0,0,64))

    def get_entities(self) -> List[Entity]:
        return self.spawn_entities

    def get_world_geometry(self) -> List[Surface]:
        return self.surfaces

    def get_portals(self) -> List[Portal]:
        return [e for e in self.spawn_entities if isinstance(e, Portal)]

    def raycast(self, origin: Vector3, direction: Vector3, max_distance: float = 8192.0, ignore_entity_id: Optional[int] = None) -> HitResult:
        """
        Simple raycast against surfaces (planes) and entity AABBs
        """
        dir_norm = direction.normalized()
        closest_hit: Optional[HitResult] = None
        closest_dist = max_distance

        # Check surfaces (plane intersection)
        for surf in self.surfaces:
            # Ray-plane intersection: (P0 - origin) dot normal / (dir dot normal)
            denom = dir_norm.dot(surf.normal)
            if abs(denom) < 1e-6:
                continue  # parallel
            # For portal placement, we only care about front faces (normal facing ray)
            # But for general raycast, check both
            t = (surf.position - origin).dot(surf.normal) / denom
            if t < 0 or t > closest_dist:
                continue
            hit_pos = origin + dir_norm * t
            # Check if hit_pos within surface bounds (AABB check)
            if not surf.bounds.contains(hit_pos):
                # For plane surfaces, bounds check may be too strict due to approximation
                # Also check distance to center
                if hit_pos.distance_to(surf.position) > 200:
                    continue
            # Hit
            closest_dist = t
            closest_hit = HitResult(
                hit=True,
                position=hit_pos,
                normal=surf.normal,
                surface_id=surf.id,
                distance=t,
                material=surf.material,
                fraction=t / max_distance if max_distance > 0 else 1.0
            )

        # Check entity AABBs (slab method)
        for ent in self.spawn_entities:
            if ent.id == ignore_entity_id:
                continue
            if not ent.bounds:
                continue
            # Ray-AABB intersection
            tmin = 0.0
            tmax = max_distance
            # For each axis
            for axis in ['x','y','z']:
                origin_comp = getattr(origin, axis)
                dir_comp = getattr(dir_norm, axis)
                min_comp = getattr(ent.bounds.mins, axis)
                max_comp = getattr(ent.bounds.maxs, axis)
                if abs(dir_comp) < 1e-6:
                    if origin_comp < min_comp or origin_comp > max_comp:
                        tmin = max_distance + 1
                        break
                else:
                    t1 = (min_comp - origin_comp) / dir_comp
                    t2 = (max_comp - origin_comp) / dir_comp
                    if t1 > t2:
                        t1, t2 = t2, t1
                    if t1 > tmin:
                        tmin = t1
                    if t2 < tmax:
                        tmax = t2
                    if tmin > tmax:
                        break
            if tmin <= tmax and 0 <= tmin <= closest_dist:
                hit_pos = origin + dir_norm * tmin
                closest_dist = tmin
                closest_hit = HitResult(
                    hit=True,
                    position=hit_pos,
                    normal=Vector3(0,0,1),  # approximate
                    entity_id=ent.id,
                    distance=tmin,
                    fraction=tmin / max_distance if max_distance > 0 else 1.0
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

    def find_portalable_surfaces(self, near_position: Optional[Vector3] = None, max_dist: float = 1000.0) -> List[Surface]:
        portalable = [s for s in self.surfaces if s.portalable]
        if near_position:
            portalable.sort(key=lambda s: s.position.distance_to(near_position))
            portalable = [s for s in portalable if s.position.distance_to(near_position) <= max_dist]
        return portalable
