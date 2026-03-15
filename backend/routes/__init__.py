"""
Routes package for 5G Network Slicing Backend
==============================================
Contains REST API endpoint modules for slice management and telemetry.
"""

from . import slicing, telemetry

__all__ = ["slicing", "telemetry"]
