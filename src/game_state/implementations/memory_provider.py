"""
Memory Provider - reads Portal 1 process memory to get entity list and player state.

This is the most complex but most powerful method if SAR is not available.
Requires finding offsets via Cheat Engine.

Typical approach:
1. Find portal.exe / hl2.exe process
2. Get base address of client.dll and server.dll and engine.dll
3. Find LocalPlayer pointer: client.dll + offset
4. Find EntityList: client.dll + offset
5. Iterate entities

Offsets are version-dependent. For Portal 1 (build 5135) example offsets (need to be found via CE):
- LocalPlayer: client.dll + 0x4C6708 (example, not accurate)
- EntityList: client.dll + 0x4D3904
- Entity size: 0x10 (pointer array)
- m_vecOrigin: 0x138 (from datamap)
- m_angRotation: 0x128
- m_vecVelocity: 0xE4

We provide a framework that can be configured with offsets.

For this project, we implement the interface with pymem if available, otherwise mock.
"""
from __future__ import annotations
import struct
from pathlib import Path
from typing import List, Optional, Dict, Tuple
import os

try:
    import pymem
    import pymem.process
    HAS_PYMEM = True
except ImportError:
    HAS_PYMEM = False

from ..provider import GameStateProvider, HitResult, TraceResult
from ...world_model.vector import Vector3, QAngle, Bounds
from ...world_model.entities import PlayerState, Entity, Cube, Button, Door, Turret
from ...world_model.surface import Surface
from ...world_model.portal import Portal
from .sar_provider import SARProvider

# Example offsets - these need to be found for specific Portal 1 version
# Using Source SDK 2007 typical offsets
DEFAULT_OFFSETS = {
    "local_player": 0x4C6708,  # client.dll + offset -> pointer to local player
    "entity_list": 0x4D3904,   # client.dll + offset -> entity list base
    "entity_list_entry_size": 0x10,
    "max_entities": 2048,
    # Entity offsets (from C_BaseEntity)
    "m_vecOrigin": 0x138,
    "m_angRotation": 0x128,
    "m_vecVelocity": 0xE4,
    "m_iHealth": 0x90,
    "m_lifeState": 0x8E,
    "m_fFlags": 0x350,
    "m_Collision_mins": 0x1D0,
    "m_Collision_maxs": 0x1DC,
    # Player specific
    "m_vecViewOffset": 0x104,
    "m_hActiveWeapon": 0xDB0,
}

class MemoryProvider(SARProvider):
    """
    Reads game memory directly.
    Requires pymem and correct offsets.
    """

    def __init__(self, process_name: str = "portal.exe", offsets: Optional[Dict[str,int]] = None, bsp_provider: Optional[GameStateProvider] = None):
        super().__init__(bsp_provider=bsp_provider)
        self.process_name = process_name
        self.offsets = offsets or DEFAULT_OFFSETS.copy()
        self.pm = None
        self.client_base = 0
        self.engine_base = 0
        self.server_base = 0
        self.connected = False

    def connect(self) -> bool:
        if not HAS_PYMEM:
            print("[MemoryProvider] pymem not installed, cannot connect to game process. Using mock mode.")
            return False

        try:
            self.pm = pymem.Pymem(self.process_name)
            # Get module bases
            client_module = pymem.process.module_from_name(self.pm.process_handle, "client.dll")
            self.client_base = client_module.lpBaseOfDll
            try:
                engine_module = pymem.process.module_from_name(self.pm.process_handle, "engine.dll")
                self.engine_base = engine_module.lpBaseOfDll
            except:
                pass
            try:
                server_module = pymem.process.module_from_name(self.pm.process_handle, "server.dll")
                self.server_base = server_module.lpBaseOfDll
            except:
                pass

            print(f"[MemoryProvider] Connected to {self.process_name}")
            print(f"  client.dll base: {hex(self.client_base)}")
            print(f"  engine.dll base: {hex(self.engine_base)}")
            print(f"  server.dll base: {hex(self.server_base)}")
            self.connected = True
            return True
        except Exception as e:
            print(f"[MemoryProvider] Failed to connect: {e}")
            self.connected = False
            return False

    def disconnect(self):
        if self.pm:
            try:
                self.pm.close_process()
            except:
                pass
        self.connected = False

    def _read_vec3(self, address: int) -> Vector3:
        if not self.pm:
            return Vector3(0,0,0)
        try:
            data = self.pm.read_bytes(address, 12)
            x,y,z = struct.unpack('fff', data)
            return Vector3(x,y,z)
        except:
            return Vector3(0,0,0)

    def _read_qangle(self, address: int) -> QAngle:
        if not self.pm:
            return QAngle(0,0,0)
        try:
            data = self.pm.read_bytes(address, 12)
            pitch,yaw,roll = struct.unpack('fff', data)
            return QAngle(pitch,yaw,roll)
        except:
            return QAngle(0,0,0)

    def _read_int(self, address: int) -> int:
        if not self.pm:
            return 0
        try:
            return self.pm.read_int(address)
        except:
            return 0

    def _read_float(self, address: int) -> float:
        if not self.pm:
            return 0.0
        try:
            return self.pm.read_float(address)
        except:
            return 0.0

    def get_player_state(self) -> PlayerState:
        if self._mock_mode and self._player_state:
            return self._player_state

        if not self.connected or not self.pm:
            # Fallback to parent
            return super().get_player_state()

        try:
            # Read local player pointer
            local_player_ptr_addr = self.client_base + self.offsets["local_player"]
            local_player_addr = self.pm.read_int(local_player_ptr_addr)
            if local_player_addr == 0:
                print("[MemoryProvider] LocalPlayer is null")
                return super().get_player_state()

            origin = self._read_vec3(local_player_addr + self.offsets["m_vecOrigin"])
            angles = self._read_qangle(local_player_addr + self.offsets["m_angRotation"])
            velocity = self._read_vec3(local_player_addr + self.offsets["m_vecVelocity"])
            view_offset = self._read_vec3(local_player_addr + self.offsets["m_vecViewOffset"])
            flags = self._read_int(local_player_addr + self.offsets["m_fFlags"])
            grounded = (flags & 1) != 0

            eye_pos = origin + view_offset

            return PlayerState(
                id=1,
                position=origin,
                rotation=angles,
                velocity=velocity,
                eye_position=eye_pos,
                grounded=grounded,
                alive=True,
                flags=flags
            )
        except Exception as e:
            print(f"[MemoryProvider] Failed to read player: {e}")
            return super().get_player_state()

    def get_entities(self) -> List[Entity]:
        if self._mock_mode:
            return list(self._entities.values())

        if not self.connected or not self.pm:
            return super().get_entities()

        entities = []
        try:
            entity_list_base = self.client_base + self.offsets["entity_list"]
            for i in range(self.offsets["max_entities"]):
                entry_addr = entity_list_base + i * self.offsets["entity_list_entry_size"]
                try:
                    ent_ptr = self.pm.read_int(entry_addr)
                    if ent_ptr == 0:
                        continue
                    # Read origin to check if valid
                    origin = self._read_vec3(ent_ptr + self.offsets["m_vecOrigin"])
                    # Filter out invalid (0,0,0) or far away?
                    if origin.length_sqr() < 0.1 and i != 0:
                        # Might be unused
                        pass

                    # For classname, we would need to read from server.dll or use datamap
                    # Simplified: we don't have classname from memory without more offsets
                    # So we create generic entity and try to guess type by position?
                    # In real implementation, you'd need to find m_iClassname or use client class
                    # For now, placeholder
                    angles = self._read_qangle(ent_ptr + self.offsets["m_angRotation"])
                    bounds_mins = self._read_vec3(ent_ptr + self.offsets["m_Collision_mins"])
                    bounds_maxs = self._read_vec3(ent_ptr + self.offsets["m_Collision_maxs"])
                    bounds = Bounds(origin + bounds_mins, origin + bounds_maxs)

                    # Guess classname based on bounds size?
                    ent = Entity(id=i, classname=f"entity_{i}", position=origin, rotation=angles, bounds=bounds)
                    entities.append(ent)
                except:
                    continue
        except Exception as e:
            print(f"[MemoryProvider] Failed to read entities: {e}")

        return entities if entities else super().get_entities()

    @staticmethod
    def find_offsets_guide() -> str:
        """
        Returns guide on how to find offsets for Portal 1 using Cheat Engine
        """
        return """
        How to find Portal 1 memory offsets (Cheat Engine method):

        1. Player position:
           - In game, note your position via getpos or cl_showpos 1
           - In Cheat Engine, search for float value of X coordinate
           - Move in game, search for changed value
           - Repeat for Y,Z until you have few addresses
           - The address that holds all 3 as consecutive floats is m_vecOrigin
           - Find what accesses this address -> find base pointer
           - Pointer scan for client.dll + offset

        2. Entity List:
           - Find a cube's position via ent_text prop_weighted_cube
           - Search for its X in CE
           - Find what accesses -> look for array indexing like [eax+edx*4] or similar
           - The base of that array is entity list
           - In Source Engine, entity list is usually an array of pointers (CEntInfo)
           - Each entry is 0x10 bytes: pointer to entity, serial number, etc.

        3. Using SAR to get datamap offsets:
           - In game console: sar_dump_server_datamap prop_weighted_cube
           - This dumps all SendProp offsets including m_vecOrigin
           - Use those offsets directly

        4. Verify offsets:
           - Restart game, check if pointers still valid
           - If not, need multi-level pointer

        Tools:
        - Cheat Engine 7.5+
        - GH Entity List Finder (https://github.com/guided-hacking/GH-Entity-List-Finder)
        - SAR: sar_find_client_class, sar_find_server_class, sar_find_client_offset, sar_find_server_offset
          These commands directly give you offsets!

        Example SAR usage:
        ] sar_find_client_offset CBaseEntity m_vecOrigin
        -> offset 0x138

        This is the recommended way to get offsets without CE.
        """

    def dump_offsets(self):
        print("Current offsets:")
        for k,v in self.offsets.items():
            print(f"  {k}: {hex(v)}")
