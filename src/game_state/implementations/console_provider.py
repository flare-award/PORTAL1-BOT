"""
Console Provider - parses Portal 1 console output and uses console commands
to get game state. Works by reading console.log or via RCON.

Console commands useful:
- getpos
- cl_showpos 1
- cl_showents
- report_entities
- ent_text <entity>
- ent_bbox <entity>
- status
- ent_info <classname>
- find_ent <name>
- cl_pdump <index>

This is the simplest method that doesn't require memory hacking.
"""
from __future__ import annotations
import re
import time
from pathlib import Path
from typing import List, Optional, Dict

from ..provider import GameStateProvider, HitResult, TraceResult
from ...world_model.vector import Vector3, QAngle, Bounds
from ...world_model.entities import PlayerState, Entity, Cube, Button, Door, Turret
from ...world_model.surface import Surface
from ...world_model.portal import Portal
from .sar_provider import SARProvider

class ConsoleProvider(SARProvider):
    """
    Extends SARProvider with more console parsing logic.
    Inherits raycast/trace from BSP if available, otherwise simple.
    """

    def __init__(self, console_log_path: Optional[Path] = None, bsp_provider: Optional[GameStateProvider] = None):
        super().__init__(console_log_path=console_log_path, bsp_provider=bsp_provider)
        self.command_history: List[str] = []

    def send_command(self, cmd: str) -> str:
        """
        In real implementation, would send command to game console via:
        - Writing to portal/cfg/autoexec.cfg and exec?
        - RCON
        - Using engine's ConCommand?
        For now, we just log it.
        """
        self.command_history.append(cmd)
        print(f"[ConsoleProvider] Would send command: {cmd}")
        # In real game, you'd need to inject via memory or use a plugin
        # For this project, we simulate
        return ""

    def request_player_position(self):
        self.send_command("getpos")
        self.send_command("cl_showpos 1")

    def request_entity_list(self):
        self.send_command("cl_showents")
        self.send_command("report_entities")
        self.send_command("sar_find_ents \"\"")  # if SAR loaded

    def request_entity_details(self, entity_id: int):
        self.send_command(f"ent_text {entity_id}")
        self.send_command(f"ent_bbox {entity_id}")

    def parse_status(self, text: str) -> Optional[Dict]:
        """
        Parse 'status' command output:
        hostname: ...
        version: ...
        map: testchmb_a_00
        players: 1 ...
        # 1 "Player" ...
        """
        map_match = re.search(r'map:\s*([a-zA-Z0-9_]+)', text, re.IGNORECASE)
        if map_match:
            return {"map": map_match.group(1)}
        return None

    def parse_cl_showents(self, text: str) -> List[Entity]:
        """
        Parse cl_showents output which is like:
        Entities: ...
        0: worldspawn
        1: player
        2: prop_weighted_cube
        ...
        This gives only classname and index, no position - need ent_text for pos
        """
        entities = []
        pattern = re.compile(r'^\s*(\d+):\s*([a-zA-Z0-9_]+)', re.MULTILINE)
        for m in pattern.finditer(text):
            idx = int(m.group(1))
            classname = m.group(2)
            # No pos, use placeholder
            pos = Vector3(0,0,0)
            bounds = Bounds(pos - Vector3(16,16,16), pos + Vector3(16,16,16))
            ent = self._create_typed_entity(idx, classname, pos, QAngle(), bounds)
            entities.append(ent)
        return entities
