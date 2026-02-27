"""Models for the EufyLife integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .extended_client import EufyLifeBLEDeviceExtended

type EufyLifeConfigEntry = ConfigEntry[EufyLifeData]


@dataclass
class EufyLifeData:
    """Data for the EufyLife integration."""

    address: str
    model: str
    client: EufyLifeBLEDeviceExtended
