"""Data-vendor abstraction.

Every externally sourced feature maps to a *capability* in the registry; the
active vendor per capability is config-driven so a data source can be swapped
without touching feature code. See registry.py for the feature → vendor map
and upstox.py for the Upstox Analytics API client.
"""
