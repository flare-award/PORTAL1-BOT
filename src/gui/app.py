"""
GUI Application - Debug interface with 3D view
Provides START/PAUSE/STOP and displays:
- Current Goal, Plan, Action, Player Pos/Rot, Visible Entities, World Model, Path, Portal Connections
- 3D debug view showing Player, Walls, Cubes, Buttons, Doors, Portals, Navigation Graph, Current Path
Implementation: FastAPI + WebSocket + Three.js frontend
"""
from __future__ import annotations
import asyncio
import json
import time
from pathlib import Path
from typing import Optional

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

# Fallback simple HTTP server if FastAPI not available
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading

class DebugGUI:
    def __init__(self, agent=None, host="0.0.0.0", port=8000):
        self.agent = agent
        self.host = host
        self.port = port
        self.running = False
        self.app = None
        if HAS_FASTAPI:
            self._setup_fastapi()

    def _setup_fastapi(self):
        self.app = FastAPI(title="Portal 1 Bot Debug GUI")

        # Serve static files
        static_dir = Path(__file__).parent / "static"
        static_dir.mkdir(exist_ok=True)

        # Create HTML template
        self._create_frontend_files()

        @self.app.get("/", response_class=HTMLResponse)
        async def get_index():
            html_path = Path(__file__).parent / "templates" / "index.html"
            if html_path.exists():
                return html_path.read_text()
            return "<h1>Portal 1 Bot Debug GUI</h1><p>Frontend not found</p>"

        @self.app.get("/api/state")
        async def get_state():
            if self.agent:
                return self.agent.get_debug_info()
            return {"error": "No agent"}

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            try:
                while True:
                    if self.agent:
                        state = self.agent.get_debug_info()
                        await websocket.send_text(json.dumps(state))
                    await asyncio.sleep(0.1)
            except WebSocketDisconnect:
                pass
            except Exception as e:
                print(f"[GUI] WebSocket error: {e}")

        @self.app.post("/api/control/{action}")
        async def control(action: str):
            if not self.agent:
                return {"error": "No agent"}
            if action == "start":
                # Start agent in background thread
                import threading
                thread = threading.Thread(target=self.agent.run, kwargs={"max_iterations": 100}, daemon=True)
                thread.start()
                return {"status": "started"}
            elif action == "pause":
                self.agent.stop()
                return {"status": "paused"}
            elif action == "stop":
                self.agent.stop()
                return {"status": "stopped"}
            else:
                return {"error": f"Unknown action {action}"}

    def _create_frontend_files(self):
        templates_dir = Path(__file__).parent / "templates"
        templates_dir.mkdir(exist_ok=True)
        static_dir = Path(__file__).parent / "static"
        static_dir.mkdir(exist_ok=True)

        # Create index.html with Three.js 3D view
        html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>Portal 1 Bot - Debug GUI</title>
    <style>
        body { margin: 0; font-family: monospace; background: #1a1a1a; color: #eee; }
        #header { padding: 10px; background: #333; display: flex; gap: 10px; align-items: center; }
        button { padding: 8px 16px; background: #007acc; color: white; border: none; cursor: pointer; border-radius: 4px; }
        button:hover { background: #005a9e; }
        #container { display: flex; height: calc(100vh - 50px); }
        #sidebar { width: 400px; background: #2a2a2a; padding: 10px; overflow-y: auto; }
        #canvas-container { flex: 1; position: relative; }
        #canvas { width: 100%; height: 100%; display: block; }
        .section { margin-bottom: 20px; border: 1px solid #444; padding: 10px; border-radius: 4px; }
        .section h3 { margin-top: 0; color: #4ec9b0; }
        pre { background: #1e1e1e; padding: 10px; overflow-x: auto; font-size: 12px; }
        #log { height: 150px; overflow-y: auto; background: #000; padding: 5px; font-size: 11px; }
    </style>
    <script src="https://unpkg.com/three@0.160.0/build/three.min.js"></script>
    <script src="https://unpkg.com/three@0.160.0/examples/js/controls/OrbitControls.js"></script>
</head>
<body>
    <div id="header">
        <h2 style="margin:0">Portal 1 Bot Debug</h2>
        <button onclick="control('start')">START</button>
        <button onclick="control('pause')">PAUSE</button>
        <button onclick="control('stop')">STOP</button>
        <span id="status">Disconnected</span>
    </div>
    <div id="container">
        <div id="sidebar">
            <div class="section">
                <h3>Current Goal</h3>
                <pre id="goal">-</pre>
            </div>
            <div class="section">
                <h3>Current Plan</h3>
                <pre id="plan">-</pre>
            </div>
            <div class="section">
                <h3>Current Action</h3>
                <pre id="action">-</pre>
            </div>
            <div class="section">
                <h3>Player</h3>
                <pre id="player">-</pre>
            </div>
            <div class="section">
                <h3>World Model</h3>
                <pre id="world">-</pre>
            </div>
            <div class="section">
                <h3>Nav Graph</h3>
                <pre id="nav">-</pre>
            </div>
            <div class="section">
                <h3>Log</h3>
                <div id="log"></div>
            </div>
        </div>
        <div id="canvas-container">
            <canvas id="canvas"></canvas>
        </div>
    </div>

    <script>
        // Three.js setup
        const canvas = document.getElementById('canvas');
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x1a1a1a);
        const camera = new THREE.PerspectiveCamera(75, canvas.clientWidth / canvas.clientHeight, 0.1, 10000);
        camera.position.set(500, -500, 300);
        const renderer = new THREE.WebGLRenderer({canvas: canvas, antialias: true});
        renderer.setSize(canvas.clientWidth, canvas.clientHeight);

        const controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.target.set(0,0,0);
        controls.update();

        // Grid
        const grid = new THREE.GridHelper(1000, 20, 0x444444, 0x222222);
        grid.rotation.x = Math.PI/2;
        scene.add(grid);

        // Lights
        const ambient = new THREE.AmbientLight(0xffffff, 0.6);
        scene.add(ambient);
        const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
        dirLight.position.set(100, 100, 200);
        scene.add(dirLight);

        // Object groups
        const groups = {
            player: new THREE.Group(),
            walls: new THREE.Group(),
            cubes: new THREE.Group(),
            buttons: new THREE.Group(),
            doors: new THREE.Group(),
            portals: new THREE.Group(),
            navNodes: new THREE.Group(),
            navEdges: new THREE.Group(),
            path: new THREE.Group()
        };
        for (let g in groups) scene.add(groups[g]);

        // Materials
        const materials = {
            player: new THREE.MeshBasicMaterial({color: 0x00ff00}),
            wall: new THREE.MeshBasicMaterial({color: 0x888888, wireframe: false, transparent: true, opacity: 0.3}),
            wallPortalable: new THREE.MeshBasicMaterial({color: 0x4488ff, transparent: true, opacity: 0.4}),
            cube: new THREE.MeshBasicMaterial({color: 0xffaa00}),
            button: new THREE.MeshBasicMaterial({color: 0xff0000}),
            buttonPressed: new THREE.MeshBasicMaterial({color: 0x00ff00}),
            door: new THREE.MeshBasicMaterial({color: 0x8B4513}),
            doorOpen: new THREE.MeshBasicMaterial({color: 0x00ff00, transparent: true, opacity: 0.3}),
            portalBlue: new THREE.MeshBasicMaterial({color: 0x0088ff, transparent: true, opacity: 0.6}),
            portalOrange: new THREE.MeshBasicMaterial({color: 0xff8800, transparent: true, opacity: 0.6}),
            navNode: new THREE.MeshBasicMaterial({color: 0xffffff}),
            navEdge: new THREE.LineBasicMaterial({color: 0x4444ff}),
            path: new THREE.LineBasicMaterial({color: 0xffff00, linewidth: 2})
        };

        function clearGroup(group) {
            while(group.children.length > 0) group.remove(group.children[0]);
        }

        function createBox(pos, size, material) {
            const geom = new THREE.BoxGeometry(size[0], size[1], size[2]);
            const mesh = new THREE.Mesh(geom, material);
            mesh.position.set(pos[0], pos[1], pos[2]);
            return mesh;
        }

        function updateScene(state) {
            if (!state.world_model) return;

            const wm = state.world_model;

            // Player
            clearGroup(groups.player);
            if (wm.player) {
                const p = wm.player.position;
                if (p) {
                    const mesh = createBox(p, [20,20,60], materials.player);
                    groups.player.add(mesh);
                    // Eye direction
                    const eye = wm.player.eye_position || p;
                    const dirGeom = new THREE.BufferGeometry().setFromPoints([
                        new THREE.Vector3(p[0], p[1], p[2]),
                        new THREE.Vector3(eye[0], eye[1], eye[2] || p[2]+64)
                    ]);
                    const line = new THREE.Line(dirGeom, new THREE.LineBasicMaterial({color: 0x00ff00}));
                    groups.player.add(line);
                }
            }

            // Surfaces / Walls
            clearGroup(groups.walls);
            if (wm.surfaces) {
                for (let id in wm.surfaces) {
                    const surf = wm.surfaces[id];
                    const pos = surf.position;
                    const bounds = surf.bounds;
                    if (!pos || !bounds) continue;
                    const size = [
                        Math.abs(bounds.maxs[0]-bounds.mins[0]) || 10,
                        Math.abs(bounds.maxs[1]-bounds.mins[1]) || 10,
                        Math.abs(bounds.maxs[2]-bounds.mins[2]) || 10
                    ];
                    // Clamp size for visibility
                    size[0] = Math.min(size[0], 200);
                    size[1] = Math.min(size[1], 200);
                    size[2] = Math.min(size[2], 200);
                    if (size[0]<1) size[0]=100;
                    if (size[1]<1) size[1]=100;
                    if (size[2]<1) size[2]=5;
                    const mat = surf.portalable ? materials.wallPortalable : materials.wall;
                    const mesh = createBox(pos, size, mat);
                    groups.walls.add(mesh);
                }
            }

            // Cubes
            clearGroup(groups.cubes);
            if (wm.cubes) {
                for (let id in wm.cubes) {
                    const cube = wm.cubes[id];
                    const mesh = createBox(cube.position, [32,32,32], materials.cube);
                    groups.cubes.add(mesh);
                }
            }

            // Buttons
            clearGroup(groups.buttons);
            if (wm.buttons) {
                for (let id in wm.buttons) {
                    const btn = wm.buttons[id];
                    const mat = btn.pressed ? materials.buttonPressed : materials.button;
                    const mesh = createBox(btn.position, [64,64,10], mat);
                    groups.buttons.add(mesh);
                }
            }

            // Doors
            clearGroup(groups.doors);
            if (wm.doors) {
                for (let id in wm.doors) {
                    const door = wm.doors[id];
                    const mat = door.open ? materials.doorOpen : materials.door;
                    const mesh = createBox(door.position, [60,20,120], mat);
                    groups.doors.add(mesh);
                }
            }

            // Portals
            clearGroup(groups.portals);
            if (wm.portals) {
                for (let id in wm.portals) {
                    const portal = wm.portals[id];
                    const mat = portal.portal_type === 'blue' ? materials.portalBlue : materials.portalOrange;
                    const mesh = createBox(portal.position, [5,64,96], mat);
                    groups.portals.add(mesh);
                    // Linked line
                    if (portal.linked_portal_id && wm.portals[portal.linked_portal_id]) {
                        const linked = wm.portals[portal.linked_portal_id];
                        const geom = new THREE.BufferGeometry().setFromPoints([
                            new THREE.Vector3(portal.position[0], portal.position[1], portal.position[2]),
                            new THREE.Vector3(linked.position[0], linked.position[1], linked.position[2])
                        ]);
                        const line = new THREE.Line(geom, new THREE.LineBasicMaterial({color: 0xffffff, transparent: true, opacity: 0.5}));
                        groups.portals.add(line);
                    }
                }
            }

            // Nav Graph
            clearGroup(groups.navNodes);
            clearGroup(groups.navEdges);
            if (state.nav_graph) {
                const nav = state.nav_graph;
                // Nodes
                for (let id in nav.nodes) {
                    const node = nav.nodes[id];
                    const mesh = createBox(node.position, [8,8,8], materials.navNode);
                    groups.navNodes.add(mesh);
                }
                // Edges
                for (let edge of nav.edges) {
                    const fromNode = nav.nodes[edge.from];
                    const toNode = nav.nodes[edge.to];
                    if (!fromNode || !toNode) continue;
                    const geom = new THREE.BufferGeometry().setFromPoints([
                        new THREE.Vector3(fromNode.position[0], fromNode.position[1], fromNode.position[2]),
                        new THREE.Vector3(toNode.position[0], toNode.position[1], toNode.position[2])
                    ]);
                    const mat = edge.type === 'portal' ? new THREE.LineBasicMaterial({color: 0x00ffff}) : materials.navEdge;
                    const line = new THREE.Line(geom, mat);
                    groups.navEdges.add(line);
                }
            }

            // Current Path
            clearGroup(groups.path);
            if (state.current_plan && state.current_plan.length>0) {
                const points = [];
                if (wm.player && wm.player.position) points.push(new THREE.Vector3(wm.player.position[0], wm.player.position[1], wm.player.position[2]));
                for (let action of state.current_plan) {
                    if (action.target_position) {
                        points.push(new THREE.Vector3(action.target_position[0], action.target_position[1], action.target_position[2]));
                    }
                }
                if (points.length>1) {
                    const geom = new THREE.BufferGeometry().setFromPoints(points);
                    const line = new THREE.Line(geom, materials.path);
                    groups.path.add(line);
                }
            }
        }

        function updateSidebar(state) {
            document.getElementById('goal').textContent = JSON.stringify(state.current_goal, null, 2);
            document.getElementById('plan').textContent = JSON.stringify(state.current_plan, null, 2);
            document.getElementById('action').textContent = JSON.stringify(state.current_action, null, 2);
            document.getElementById('player').textContent = JSON.stringify({
                position: state.player_position,
                rotation: state.player_rotation
            }, null, 2);
            if (state.world_model) {
                const wmSummary = {
                    map: state.world_model.map_name,
                    entities: Object.keys(state.world_model.entities||{}).length,
                    cubes: Object.keys(state.world_model.cubes||{}).length,
                    buttons: Object.keys(state.world_model.buttons||{}).length,
                    doors: Object.keys(state.world_model.doors||{}).length,
                    portals: Object.keys(state.world_model.portals||{}).length,
                    surfaces: Object.keys(state.world_model.surfaces||{}).length,
                    goals: state.world_model.goals?.length
                };
                document.getElementById('world').textContent = JSON.stringify(wmSummary, null, 2);
            }
            if (state.nav_graph) {
                document.getElementById('nav').textContent = `Nodes: ${Object.keys(state.nav_graph.nodes).length}, Edges: ${state.nav_graph.edges.length}`;
            }
        }

        function animate() {
            requestAnimationFrame(animate);
            controls.update();
            renderer.render(scene, camera);
        }
        animate();

        window.addEventListener('resize', () => {
            camera.aspect = canvas.clientWidth / canvas.clientHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(canvas.clientWidth, canvas.clientHeight);
        });

        // WebSocket
        let ws = null;
        function connectWS() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(protocol + '//' + window.location.host + '/ws');
            ws.onopen = () => {
                document.getElementById('status').textContent = 'Connected';
                log('WebSocket connected');
            };
            ws.onclose = () => {
                document.getElementById('status').textContent = 'Disconnected';
                log('WebSocket disconnected, retrying in 2s');
                setTimeout(connectWS, 2000);
            };
            ws.onmessage = (event) => {
                try {
                    const state = JSON.parse(event.data);
                    updateScene(state);
                    updateSidebar(state);
                } catch(e) {
                    console.error('Failed to parse WS message', e);
                }
            };
        }

        function log(msg) {
            const el = document.getElementById('log');
            const line = document.createElement('div');
            line.textContent = new Date().toLocaleTimeString() + ' ' + msg;
            el.appendChild(line);
            el.scrollTop = el.scrollHeight;
        }

        function control(action) {
            fetch('/api/control/' + action, {method: 'POST'})
                .then(r=>r.json())
                .then(data=>log('Control ' + action + ': ' + JSON.stringify(data)))
                .catch(e=>log('Control error: ' + e));
        }

        // Initial fetch
        fetch('/api/state').then(r=>r.json()).then(state=>{
            updateScene(state);
            updateSidebar(state);
        });

        connectWS();
    </script>
</body>
</html>
        """
        html_path = Path(__file__).parent / "templates" / "index.html"
        html_path.write_text(html_content)

    def run(self):
        if not HAS_FASTAPI:
            print("[GUI] FastAPI not available, cannot run web GUI")
            return

        print(f"[GUI] Starting debug GUI at http://{self.host}:{self.port}")
        print(f"[GUI] 3D view will show Player, Walls, Cubes, Buttons, Doors, Portals, Nav Graph, Path")
        uvicorn.run(self.app, host=self.host, port=self.port, log_level="info")

    def run_in_thread(self):
        if not HAS_FASTAPI:
            print("[GUI] FastAPI not available")
            return None
        import threading
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        return thread
