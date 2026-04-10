# engine/__init__.py
"""MATLAB Engine interface — three-layer architecture for Simulink co-simulation.

Heavy imports (MatlabSession, SimulinkBridge) are lazy to avoid blocking
when ``import matlab.engine`` hangs due to zombie MATLAB processes.
Use ``from engine.matlab_session import MatlabSession`` directly.
"""

from engine.exceptions import MatlabCallError, SimulinkError

__all__ = [
    "MatlabCallError",
    "SimulinkError",
    "MatlabSession",
    "BridgeConfig",
    "SimulinkBridge",
]


def __getattr__(name: str):
    if name == "MatlabSession":
        from engine.matlab_session import MatlabSession
        return MatlabSession
    if name == "BridgeConfig":
        from engine.simulink_bridge import BridgeConfig
        return BridgeConfig
    if name == "SimulinkBridge":
        from engine.simulink_bridge import SimulinkBridge
        return SimulinkBridge
    raise AttributeError(f"module 'engine' has no attribute {name!r}")
