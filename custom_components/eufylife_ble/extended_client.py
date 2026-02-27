"""Extended EufyLife BLE client with impedance extraction.

Subclasses EufyLifeBLEDevice to extract bioelectrical impedance data
that the upstream library ignores:

- T9150 (P3): impedance from advertisement data body-comp packets
  (data[10] & 0x20), bytes 17-18 as uint16 LE / 10 = Ohms.
- T9148/T9149 (P2/P2 Pro): impedance from GATT notification bytes 8-10
  as a 24-bit value (code commented out in upstream client.py line 355).

BETA WARNING: Impedance byte positions and scaling factors are based on
reverse engineering (PR #11 for T9150, commented code for T9148). These
need empirical validation.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from bleak.backends.scanner import AdvertisementData
from eufylife_ble_client import EufyLifeBLEDevice
from eufylife_ble_client.models import EufyLifeBLEState

_LOGGER = logging.getLogger(__name__)

# T9150 body-comp packet status values (from reverse engineering + empirical)
# Bit 5 (0x20) indicates body composition data is present
# Combined with weight status bits:
# 0x25 = body-comp + weight measuring
# 0x65 = body-comp + weight stabilized (impedance measuring)
# 0xA5 = body-comp + weight final + impedance final + HR
_T9150_BODY_COMP_FLAG = 0x20
_T9150_FINAL_FLAG = 0x80


class EufyLifeBLEDeviceExtended(EufyLifeBLEDevice):
    """Extended EufyLife BLE device with impedance support."""

    def __init__(self, model: str) -> None:
        """Initialize the extended device."""
        super().__init__(model=model)
        self._impedance: float | None = None
        self._impedance_final: float | None = None
        self._heart_rate_extended: int | None = None
        self._extended_callbacks: list[Callable[[], None]] = []

    @property
    def impedance(self) -> float | None:
        """Return the current impedance value in Ohms."""
        return self._impedance

    @property
    def impedance_final(self) -> float | None:
        """Return the final impedance value in Ohms."""
        return self._impedance_final

    @property
    def heart_rate_extended(self) -> int | None:
        """Return heart rate from extended data (T9150)."""
        return self._heart_rate_extended

    @property
    def supports_body_composition(self) -> bool:
        """Return whether the device supports body composition measurements."""
        return self._model_id in ["eufy T9148", "eufy T9149", "eufy T9150"]

    @property
    def supports_heart_rate(self) -> bool:
        """Return whether the device supports heart rate measurements."""
        # T9150 also supports heart rate via body-comp packets
        return self._model_id in ["eufy T9149", "eufy T9150"]

    def register_extended_callback(
        self, callback: Callable[[], None]
    ) -> Callable[[], None]:
        """Register a callback for extended data updates (impedance, etc.)."""

        def unregister_callback() -> None:
            self._extended_callbacks.remove(callback)

        self._extended_callbacks.append(callback)
        return unregister_callback

    def _fire_extended_callbacks(self) -> None:
        """Fire extended callbacks."""
        for cb in self._extended_callbacks:
            cb()

    def update_state_from_advertisement_data(
        self, advertisement_data: AdvertisementData
    ) -> None:
        """Update state from advertisement data, with body-comp support for T9150."""
        if self._model_id == "eufy T9150":
            self._handle_t9150_advertisement(advertisement_data)
        else:
            super().update_state_from_advertisement_data(advertisement_data)

    def _handle_t9150_advertisement(
        self, advertisement_data: AdvertisementData
    ) -> None:
        """Handle T9150 advertisement data including body composition packets."""
        manufacturer_data = advertisement_data.manufacturer_data
        if not manufacturer_data:
            return

        values = list(manufacturer_data.values())

        # T9150 can have multiple advertisement packets
        # Process body-comp packets AND standard weight packets
        body_comp_data = None
        weight_data = None

        for data in values:
            if len(data) >= 19 and (data[10] & _T9150_BODY_COMP_FLAG):
                body_comp_data = data
            elif len(data) >= 18 and data[10] in [0x01, 0x05]:
                weight_data = data

        # Handle body composition packet (includes weight + impedance + HR)
        if body_comp_data is not None:
            self._handle_t9150_body_comp_packet(body_comp_data)
        elif weight_data is not None:
            # Standard weight-only packet (no body-comp data)
            self._handle_advertisement_weight_update_t9130_t9150(weight_data)

    def _handle_t9150_body_comp_packet(self, data: bytearray) -> None:
        """Extract impedance, heart rate, and weight from T9150 body-comp packet.

        Packet format (from empirical data):
        - data[10]: status byte (0x25=measuring, 0x65=stabilizing, 0xA5=final)
        - data[12:14]: weight (uint16 LE, /100 = kg)
        - data[15]: heart rate (0 = not available)
        - data[17:19]: impedance (uint16 LE, /10 = Ohms)
        """
        status = data[10]
        _LOGGER.debug(
            "T9150 body-comp packet: status=0x%02X, len=%d, hex=%s",
            status,
            len(data),
            data.hex(),
        )

        # Extract heart rate from byte 15
        hr = data[15]
        if hr > 0:
            self._heart_rate_extended = hr
            _LOGGER.debug("T9150 heart rate: %d bpm", hr)

        # Extract impedance from bytes 17-18 (uint16 LE)
        if len(data) >= 19:
            raw_impedance = data[17] | (data[18] << 8)
            if raw_impedance > 0:
                impedance_ohms = raw_impedance / 10.0
                self._impedance = impedance_ohms
                _LOGGER.debug(
                    "T9150 impedance: raw=%d, ohms=%.1f", raw_impedance, impedance_ohms
                )

                is_final = bool(status & _T9150_FINAL_FLAG)
                if is_final:
                    self._impedance_final = impedance_ohms
                    _LOGGER.debug(
                        "T9150 final impedance: %.1f Ohms", impedance_ohms
                    )

                self._fire_extended_callbacks()

        # Extract weight and update state from body-comp packet
        weight_kg = ((data[13] << 8) | data[12]) / 100
        is_final = bool(status & _T9150_FINAL_FLAG)
        final_weight_kg = weight_kg if is_final else None
        heart_rate = self._heart_rate_extended

        self._set_state_and_fire_callbacks(
            EufyLifeBLEState(weight_kg, final_weight_kg, heart_rate, False)
        )

    def _handle_weight_update_t9148_t9149(self, data: bytearray) -> None:
        """Handle T9148/T9149 GATT notification with impedance extraction.

        Overrides parent to extract impedance from bytes 8-10 (24-bit value)
        which the upstream library has commented out (client.py line 355).
        """
        if len(data) != 16 or data[0] != 0xCF or data[2] != 0x00:
            return

        weight_kg = ((data[7] << 8) | data[6]) / 100
        is_final = data[12] == 0x00
        final_weight_kg = weight_kg if is_final else None

        # Extract impedance from bytes 8-10 (24-bit, commented out in upstream)
        raw_impedance = (data[10] << 16) | (data[9] << 8) | data[8]
        if raw_impedance > 0:
            self._impedance = float(raw_impedance)
            _LOGGER.debug(
                "T9148/T9149 impedance: raw=%d", raw_impedance
            )

            if is_final:
                self._impedance_final = float(raw_impedance)
                _LOGGER.debug(
                    "T9148/T9149 final impedance: %d", raw_impedance
                )

            self._fire_extended_callbacks()

        self._set_state_and_fire_callbacks(
            EufyLifeBLEState(weight_kg, final_weight_kg, None, False)
        )
