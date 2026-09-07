"""
SAR Provider - uses SourceAutoRecord plugin to get live game state
SAR is a speedrun plugin for Portal 1/2 that provides extensive debugging commands.

Commands used:
- getpos -> player position
- sar_find_ents <filter> -> entity list
- sar_find_ent <index> -> entity details
- ent_text <entity> -> entity properties
- cl_showpos 1 -> HUD (but we parse console)
- sar_hud_player_info
- sar_dump_server_datamap

This provider can work in two modes:
1. Reading console.log file (Portal 1 writes to portal/console.log if con_logfile 1)
2. Via RCON / TCP if custom SAR extension provides HTTP/JSON endpoint
3. Mock parsing of SAR output (for implementation we parse text output)

For this implementation, we provide a parser for SAR output and a method to
inject mock data, plus a real implementation that would read from game via file/pipe.
"""
from __future__ import annotations
import re
import time
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from ..provider import GameStateProvider, HitResult, TraceResult
from ...world_model.vector import Vector3, QAngle, Bounds
from ...world_model.entities import PlayerState, Entity, Cube, Button, Door, Turret, ExitDoor
from ...world_model.surface import Surface
from ...world_model.portal import Portal

# Regex patterns for parsing SAR / console output
GETPOS_PATTERN = re.compile(r'setpos\s+([-\d\.]+)\s+([-\d\.]+)\s+([-\d\.]+);\s*setang\s+([-\d\.]+)\s+([-\d\.]+)\s+([-\d\.]+)')
CL_SHOWPOS_PATTERN = re.compile(r'pos:\s*([-\d\.]+)\s+([-\d\.]+)\s+([-\d\.]+).*ang:\s*([-\d\.]+)\s+([-\d\.]+)\s+([-\d\.]+).*vel:\s*([-\d\.]+)\s+([-\d\.]+)\s+([-\d\.]+)', re.IGNORECASE)
SAR_FIND_ENTS_LINE = re.compile(r'#\s*(\d+):\s*([^\s]+)\s*-\s*pos:\s*([-\d\.]+)\s+([-\d\.]+)\s+([-\d\.]+).*ang:\s*([-\d\.]+)\s+([-\d\.]+)\s+([-\d\.]+)', re.IGNORECASE)
# Alternative format: "  123: prop_weighted_cube (0.00, 0.00, 0.00)"
SIMPLE_ENT_PATTERN = re.compile(r'(\d+):\s*([a-zA-Z0-9_]+).*?\(?\s*([-\d\.]+)[,\s]+([-\d\.]+)[,\s]+([-\d\.]+)')

ENT_TEXT_POS = re.compile(r'm_vecOrigin:\s*([-\d\.]+)\s+([-\d\.]+)\s+([-\d\.]+)', re.IGNORECASE)
ENT_TEXT_ANG = re.compile(r'm_angRotation:\s*([-\d\.]+)\s+([-\d\.]+)\s+([-\d\.]+)', re.IGNORECASE)
ENT_TEXT_VEL = re.compile(r'm_vecVelocity.*?:\s*([-\d\.]+)\s+([-\d\.]+)\s+([-\d\.]+)', re.IGNORECASE)

class SARProvider(GameStateProvider):
    """
    Provides game state via SAR plugin output.
    In real usage, would interface with game process.
    For this project, we implement parsers and allow mock injection.
    """

    def __init__(self, console_log_path: Optional[Path] = None, bsp_provider: Optional[GameStateProvider] = None):
        self.console_log_path = Path(console_log_path) if console_log_path else None
        self.bsp_provider = bsp_provider  # For static geometry fallback
        self._player_state: Optional[PlayerState] = None
        self._entities: Dict[int, Entity] = {}
        self._surfaces: List[Surface] = []
        self._portals: Dict[int, Portal] = {}
        self._last_update = 0.0
        # For testing, allow manual injection
        self._mock_mode = False

    def set_mock_data(self, player: PlayerState, entities: List[Entity], surfaces: List[Surface], portals: List[Portal]):
        """Inject mock data for testing"""
        self._player_state = player
        self._entities = {e.id: e for e in entities}
        self._portals = {p.id: p for p in portals}
        self._surfaces = surfaces
        self._mock_mode = True

    def parse_getpos(self, text: str) -> Optional[PlayerState]:
        """
        Parse output of 'getpos' console command:
        setpos 0.00 0.00 64.00;setang 0.00 90.00 0.00
        """
        m = GETPOS_PATTERN.search(text)
        if not m:
            return None
        x,y,z, pitch,yaw,roll = map(float, m.groups())
        pos = Vector3(x,y,z)
        ang = QAngle(pitch,yaw,roll)
        eye = pos + Vector3(0,0,64)
        return PlayerState(id=1, position=pos, rotation=ang, eye_position=eye, grounded=True, alive=True)

    def parse_cl_showpos(self, text: str) -> Optional[PlayerState]:
        """
        Parse cl_showpos HUD line
        """
        m = CL_SHOWPOS_PATTERN.search(text)
        if not m:
            return None
        x,y,z, pitch,yaw,roll, vx,vy,vz = map(float, m.groups())
        pos = Vector3(x,y,z)
        ang = QAngle(pitch,yaw,roll)
        vel = Vector3(vx,vy,vz)
        eye = pos + Vector3(0,0,64)
        return PlayerState(id=1, position=pos, rotation=ang, velocity=vel, eye_position=eye, grounded=True, alive=True)

    def parse_sar_find_ents(self, text: str) -> List[Entity]:
        """
        Parse output of 'sar_find_ents' command
        Example:
        #  123: prop_weighted_cube - pos: 100 200 300 ang: 0 90 0
        """
        entities = []
        for line in text.splitlines():
            m = SAR_FIND_ENTS_LINE.search(line)
            if m:
                idx = int(m.group(1))
                classname = m.group(2)
                x,y,z = float(m.group(3)), float(m.group(4)), float(m.group(5))
                pitch,yaw,roll = float(m.group(6)), float(m.group(7)), float(m.group(8))
                pos = Vector3(x,y,z)
                ang = QAngle(pitch,yaw,roll)
                bounds = Bounds(pos - Vector3(16,16,16), pos + Vector3(16,16,16))
                ent = self._create_typed_entity(idx, classname, pos, ang, bounds)
                entities.append(ent)
                continue
            # Try simple pattern
            m2 = SIMPLE_ENT_PATTERN.search(line)
            if m2:
                idx = int(m2.group(1))
                classname = m2.group(2)
                try:
                    x,y,z = float(m2.group(3)), float(m2.group(4)), float(m2.group(5))
                    pos = Vector3(x,y,z)
                    ang = QAngle(0,0,0)
                    bounds = Bounds(pos - Vector3(16,16,16), pos + Vector3(16,16,16))
                    ent = self._create_typed_entity(idx, classname, pos, ang, bounds)
                    entities.append(ent)
                except:
                    pass
        return entities

    def _create_typed_entity(self, idx: int, classname: str, pos: Vector3, ang: QAngle, bounds: Bounds) -> Entity:
        if "cube" in classname or "prop_physics" in classname:
            return Cube(id=idx, position=pos, rotation=ang, bounds=bounds, classname=classname)
        elif "button" in classname:
            return Button(id=idx, position=pos, rotation=ang, bounds=bounds, classname=classname)
        elif "door" in classname:
            return Door(id=idx, position=pos, rotation=ang, bounds=bounds, classname=classname)
        elif "turret" in classname:
            return Turret(id=idx, position=pos, rotation=ang, bounds=bounds, classname=classname)
        elif "prop_portal" in classname:
            # Determine type by model or by checking if portal 2? SAR might give m_bIsPortal2
            ptype = "blue" if idx % 2 == 0 else "orange"  # heuristic, real would parse m_bIsPortal2
            return Portal(id=idx, position=pos, rotation=ang, bounds=bounds, portal_type=ptype, active=True)
        else:
            return Entity(id=idx, classname=classname, position=pos, rotation=ang, bounds=bounds)

    def parse_ent_text(self, text: str, entity_id: int, classname: str) -> Entity:
        """
        Parse 'ent_text <id>' output which dumps datamap fields
        """
        pos = Vector3(0,0,0)
        ang = QAngle(0,0,0)
        vel = Vector3(0,0,0)
        m = ENT_TEXT_POS.search(text)
        if m:
            pos = Vector3(float(m.group(1)), float(m.group(2)), float(m.group(3)))
        m = ENT_TEXT_ANG.search(text)
        if m:
            ang = QAngle(float(m.group(1)), float(m.group(2)), float(m.group(3)))
        m = ENT_TEXT_VEL.search(text)
        if m:
            vel = Vector3(float(m.group(1)), float(m.group(2)), float(m.group(3)))

        bounds = Bounds(pos - Vector3(16,16,16), pos + Vector3(16,16,16))
        return self._create_typed_entity(entity_id, classname, pos, ang, bounds)

    def get_player_state(self) -> PlayerState:
        if self._mock_mode and self._player_state:
            return self._player_state

        # Try to read from console.log if available
        if self.console_log_path and self.console_log_path.exists():
            try:
                content = self.console_log_path.read_text(encoding='utf-8', errors='ignore')[-10000:]
                # Find last getpos
                # Look for setpos lines
                matches = list(GETPOS_PATTERN.finditer(content))
                if matches:
                    last = matches[-1]
                    x,y,z,pitch,yaw,roll = map(float, last.groups())
                    pos = Vector3(x,y,z)
                    ang = QAngle(pitch,yaw,roll)
                    return PlayerState(id=1, position=pos, rotation=ang, eye_position=pos+Vector3(0,0,64))

                # Try cl_showpos
                matches = list(CL_SHOWPOS_PATTERN.finditer(content))
                if matches:
                    last = matches[-1]
                    x,y,z,pitch,yaw,roll,vx,vy,vz = map(float, last.groups())
                    pos = Vector3(x,y,z)
                    ang = QAngle(pitch,yaw,roll)
                    vel = Vector3(vx,vy,vz)
                    return PlayerState(id=1, position=pos, rotation=ang, velocity=vel, eye_position=pos+Vector3(0,0,64))
            except Exception as e:
                print(f"[SARProvider] Failed to read console.log: {e}")

        # Fallback to mock or default
        if self._player_state:
            return self._player_state

        # Default if no game running
        return PlayerState(id=1, position=Vector3(0,0,0), rotation=QAngle(0,0,0), eye_position=Vector3(0,0,64))

    def get_entities(self) -> List[Entity]:
        if self._mock_mode:
            return list(self._entities.values())
        if self._entities:
            return list(self._entities.values())
        # If we have BSP provider, use its entities as fallback for static
        if self.bsp_provider:
            return self.bsp_provider.get_entities()
        return []

    def get_world_geometry(self) -> List[Surface]:
        if self._mock_mode and self._surfaces:
            return self._surfaces
        if self.bsp_provider:
            return self.bsp_provider.get_world_geometry()
        return self._surfaces

    def get_portals(self) -> List[Portal]:
        if self._mock_mode:
            return list(self._portals.values())
        # Filter entities that are portals
        portals = [e for e in self.get_entities() if isinstance(e, Portal)]
        # Also from _portals dict
        for p in self._portals.values():
            if p.id not in [e.id for e in portals]:
                portals.append(p)
        return portals

    def raycast(self, origin: Vector3, direction: Vector3, max_distance: float = 8192.0, ignore_entity_id: Optional[int] = None) -> HitResult:
        # If BSP provider available, delegate
        if self.bsp_provider:
            return self.bsp_provider.raycast(origin, direction, max_distance, ignore_entity_id)

        # Simple fallback: check entities
        dir_norm = direction.normalized()
        closest_dist = max_distance
        closest_hit = None

        for ent in self.get_entities():
            if ent.id == ignore_entity_id:
                continue
            if not ent.bounds:
                continue
            # Ray-AABB
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

    def update_from_sar_dump(self, dump_text: str):
        """
        Update internal state from a SAR dump file that might contain JSON
        Expected format: {"player": {...}, "entities": [...]}
        """
        try:
            data = json.loads(dump_text)
            if "player" in data:
                p = data["player"]
                pos = Vector3(*p.get("pos", [0,0,0]))
                ang = QAngle(*p.get("ang", [0,0,0]))
                vel = Vector3(*p.get("vel", [0,0,0]))
                self._player_state = PlayerState(id=1, position=pos, rotation=ang, velocity=vel, eye_position=pos+Vector3(0,0,64))
            if "entities" in data:
                self._entities = {}
                for ent_data in data["entities"]:
                    idx = ent_data.get("index", 0)
                    classname = ent_data.get("classname", "unknown")
                    pos_arr = ent_data.get("origin", [0,0,0])
                    ang_arr = ent_data.get("angles", [0,0,0])
                    pos = Vector3(*pos_arr)
                    ang = QAngle(*ang_arr)
                    bounds = Bounds(pos - Vector3(16,16,16), pos + Vector3(16,16,16))
                    ent = self._create_typed_entity(idx, classname, pos, ang, bounds)
                    self._entities[idx] = ent
        except Exception as e:
            print(f"[SARProvider] Failed to parse dump: {e}")
            # Try text parsing
            entities = self.parse_sar_find_ents(dump_text)
            for ent in entities:
                self._entities[ent.id] = ent

    def connect(self) -> bool:
        # In real implementation, would try to connect to game
        # For now, just check if mock or BSP available
        return True
