"""
Input Controller - translates abstract actions to actual keyboard/mouse inputs
Supports:
- pynput for cross-platform
- Direct Windows SendInput via ctypes
- Mock for testing

Actions:
W/A/S/D, SPACE, CTRL, mouse movement, mouse buttons, E
"""
from __future__ import annotations
from typing import Optional, Tuple
import time
import math

from ..world_model.vector import Vector3, QAngle

class InputController:
    """
    Abstract input controller
    """

    def press_key(self, key: str, duration: float = 0.1):
        raise NotImplementedError

    def hold_key(self, key: str):
        raise NotImplementedError

    def release_key(self, key: str):
        raise NotImplementedError

    def move_mouse(self, dx: float, dy: float):
        raise NotImplementedError

    def set_mouse_position(self, x: int, y: int):
        raise NotImplementedError

    def mouse_click(self, button: str = "left"):
        raise NotImplementedError

    def look_at(self, current_angles: QAngle, target_position: Vector3, current_position: Vector3, eye_position: Vector3, sensitivity: float = 0.1):
        """
        Calculate mouse movement needed to look at target_position from current_position
        """
        # Vector from eye to target
        to_target = target_position - eye_position
        dist = to_target.length()
        if dist < 1e-6:
            return

        # Desired angles
        # yaw = atan2(y, x)
        # pitch = -asin(z / dist)  (Source pitch is negative when looking up? Actually -90 up, 90 down)
        desired_yaw = math.degrees(math.atan2(to_target.y, to_target.x))
        desired_pitch = math.degrees(math.asin(-to_target.z / dist))  # negative because Source

        # Current angles
        current_yaw = current_angles.yaw
        current_pitch = current_angles.pitch

        # Delta, handle yaw wrapping
        delta_yaw = desired_yaw - current_yaw
        # Normalize to -180..180
        while delta_yaw > 180:
            delta_yaw -= 360
        while delta_yaw < -180:
            delta_yaw += 360

        delta_pitch = desired_pitch - current_pitch

        # Convert to mouse movement
        # Mouse sensitivity: typical Source sensitivity 3.0 means 1 degree ~ ? pixels
        # For simplicity: mouse dx = delta_yaw / sensitivity, dy = delta_pitch / sensitivity
        # Actually Source: m_yaw 0.022, m_pitch 0.022, sensitivity scales
        # We'll use: dx = delta_yaw / 0.022 / sensitivity? Simplified.
        # Let's assume 1 pixel ~ 0.1 degree at sensitivity 1
        mouse_dx = delta_yaw / 0.1
        mouse_dy = delta_pitch / 0.1

        self.move_mouse(mouse_dx, mouse_dy)
        return delta_yaw, delta_pitch

    def move_towards(self, direction: Vector3, duration: float = 0.1):
        """
        Move in direction relative to player view
        direction is world space, need to convert to WASD
        For simplicity, we assume we already look towards movement direction
        So just press W
        """
        # In real implementation, you'd need to determine which keys to press based on
        # player's orientation vs desired direction
        # Simplified: press W
        self.press_key('w', duration)

class MockInputController(InputController):
    """
    Mock controller for testing - logs actions instead of executing
    """

    def __init__(self):
        self.log = []
        self.pressed_keys = set()
        self.mouse_pos = (0,0)

    def press_key(self, key: str, duration: float = 0.1):
        self.log.append(f"Press {key} for {duration}s")
        print(f"[MockInput] Press {key} for {duration}s")

    def hold_key(self, key: str):
        self.pressed_keys.add(key)
        self.log.append(f"Hold {key}")
        print(f"[MockInput] Hold {key}")

    def release_key(self, key: str):
        self.pressed_keys.discard(key)
        self.log.append(f"Release {key}")
        print(f"[MockInput] Release {key}")

    def move_mouse(self, dx: float, dy: float):
        self.log.append(f"Mouse move {dx:.1f}, {dy:.1f}")
        print(f"[MockInput] Mouse move {dx:.1f}, {dy:.1f}")

    def set_mouse_position(self, x: int, y: int):
        self.mouse_pos = (x,y)
        self.log.append(f"Mouse set {x}, {y}")

    def mouse_click(self, button: str = "left"):
        self.log.append(f"Mouse click {button}")
        print(f"[MockInput] Mouse click {button}")

class PynputInputController(InputController):
    """
    Uses pynput library for real input control
    Requires: pip install pynput
    """

    def __init__(self):
        self.keyboard = None
        self.mouse = None
        self._init_pynput()

    def _init_pynput(self):
        try:
            from pynput.keyboard import Controller as KeyboardController, Key
            from pynput.mouse import Controller as MouseController, Button
            self.keyboard = KeyboardController()
            self.mouse = MouseController()
            self.Key = Key
            self.Button = Button
            print("[PynputInput] Initialized")
        except ImportError:
            print("[PynputInput] pynput not installed, falling back to mock")
            self.keyboard = None
            self.mouse = None
        except Exception as e:
            print(f"[PynputInput] Failed to init: {e}")
            self.keyboard = None
            self.mouse = None

    def press_key(self, key: str, duration: float = 0.1):
        if not self.keyboard:
            print(f"[PynputInput] Would press {key} for {duration}s")
            time.sleep(duration)
            return
        try:
            from pynput.keyboard import Key
            # Map key string to pynput key
            key_map = {
                'w': 'w',
                'a': 'a',
                's': 's',
                'd': 'd',
                'space': Key.space,
                'ctrl': Key.ctrl,
                'shift': Key.shift,
                'e': 'e',
                'q': 'q'
            }
            k = key_map.get(key.lower(), key.lower())
            self.keyboard.press(k)
            time.sleep(duration)
            self.keyboard.release(k)
        except Exception as e:
            print(f"[PynputInput] press_key error: {e}")

    def hold_key(self, key: str):
        if not self.keyboard:
            return
        try:
            from pynput.keyboard import Key
            key_map = {
                'w': 'w', 'a': 'a', 's': 's', 'd': 'd',
                'space': Key.space, 'ctrl': Key.ctrl, 'shift': Key.shift,
                'e': 'e'
            }
            k = key_map.get(key.lower(), key.lower())
            self.keyboard.press(k)
        except Exception as e:
            print(f"[PynputInput] hold_key error: {e}")

    def release_key(self, key: str):
        if not self.keyboard:
            return
        try:
            from pynput.keyboard import Key
            key_map = {
                'w': 'w', 'a': 'a', 's': 's', 'd': 'd',
                'space': Key.space, 'ctrl': Key.ctrl, 'shift': Key.shift,
                'e': 'e'
            }
            k = key_map.get(key.lower(), key.lower())
            self.keyboard.release(k)
        except Exception as e:
            print(f"[PynputInput] release_key error: {e}")

    def move_mouse(self, dx: float, dy: float):
        if not self.mouse:
            print(f"[PynputInput] Would move mouse {dx}, {dy}")
            return
        try:
            # pynput mouse move is relative? Actually controller.move is relative
            self.mouse.move(dx, dy)
        except Exception as e:
            print(f"[PynputInput] move_mouse error: {e}")

    def set_mouse_position(self, x: int, y: int):
        if not self.mouse:
            return
        try:
            self.mouse.position = (x,y)
        except Exception as e:
            print(f"[PynputInput] set_mouse_position error: {e}")

    def mouse_click(self, button: str = "left"):
        if not self.mouse:
            print(f"[PynputInput] Would click {button}")
            return
        try:
            from pynput.mouse import Button
            btn = Button.left if button == "left" else Button.right
            self.mouse.click(btn, 1)
        except Exception as e:
            print(f"[PynputInput] mouse_click error: {e}")
