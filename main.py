"""
Portal 1 Bot - Main entry point
Demonstrates full architecture: GameState -> WorldModel -> Spatial -> Nav -> Planner -> Action
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.game_state.implementations.mock_provider import MockProvider
from src.game_state.implementations.aggregated_provider import AggregatedProvider
from src.game_state.implementations.bsp_provider import BSPProvider
from src.game_state.implementations.sar_provider import SARProvider
from src.action.controller import MockInputController, PynputInputController
from src.agent import PortalAgent
from src.gui.app import DebugGUI

def main():
    print("="*60)
    print("Portal 1 Bot - 3D World Model Approach")
    print("="*60)
    print()
    print("This bot perceives Portal 1 not as image, but as 3D scene")
    print("with objects, coordinates, geometry, collisions and relationships")
    print()
    print("Architecture:")
    print("  PORTAL 1 -> GAME STATE EXTRACTION -> 3D WORLD MODEL -> PERCEPTION")
    print("  -> GOAL PLANNER -> ACTION PLANNER -> INPUT CONTROLLER -> PORTAL 1")
    print()
    print("Computer Vision is NOT central component")
    print()

    # Choose provider
    # For development without game, use MockProvider
    # For real game, use AggregatedProvider with BSPProvider + SARProvider

    print("Initializing providers...")
    mock_provider = MockProvider()
    print(f"MockProvider: {len(mock_provider.get_entities())} entities, {len(mock_provider.get_world_geometry())} surfaces")

    # Example: if BSP file exists, use it
    # bsp_path = Path("portal/maps/testchmb_a_00.bsp")
    # if bsp_path.exists():
    #     bsp_provider = BSPProvider()
    #     bsp_provider.load_bsp(bsp_path)
    #     sar_provider = SARProvider()
    #     provider = AggregatedProvider(bsp_provider, sar_provider)
    # else:
    #     provider = mock_provider

    provider = mock_provider

    # Input controller
    # Use Mock for testing, Pynput for real game
    try:
        input_controller = PynputInputController()
        if input_controller.keyboard is None:
            print("Pynput not available, using MockInputController")
            input_controller = MockInputController()
    except:
        input_controller = MockInputController()

    # Create agent
    agent = PortalAgent(provider, input_controller, debug=True)

    # Check if GUI requested
    if "--gui" in sys.argv:
        print("\nStarting GUI...")
        gui = DebugGUI(agent, host="0.0.0.0", port=8000)
        # Run agent in background thread
        import threading
        agent_thread = threading.Thread(target=agent.run, kwargs={"max_iterations": 100}, daemon=True)
        agent_thread.start()
        # Run GUI in main thread
        gui.run()
    elif "--test" in sys.argv:
        print("\nRunning diagnostic tests...")
        from src.tests.test_runner import run_all_tests
        run_all_tests()
    else:
        print("\nRunning agent for 10 iterations...")
        print("Use --gui for debug GUI with 3D view")
        print("Use --test for diagnostic tests")
        print()
        agent.run(max_iterations=10)

if __name__ == "__main__":
    main()
