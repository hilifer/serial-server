"""
Shared global state between server.py and meter_api.py.

Avoids the __main__ vs module import issue: when running `python server.py`,
the module is loaded as __main__, but `from server import serial_managers`
re-imports it as a separate 'server' module with its own empty dict.

By putting shared state here, both sides import the same object.
"""

from serial_manager import SerialManager

# port name -> SerialManager, populated by server.main()
serial_managers: dict[str, SerialManager] = {}
