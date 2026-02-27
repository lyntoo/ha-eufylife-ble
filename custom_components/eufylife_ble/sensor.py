"""Support for EufyLife sensors."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from eufylife_ble_client import MODEL_TO_NAME

from homeassistant.components.bluetooth import async_address_present
from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfMass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from .body_metrics import BodyCompositionResult, BodyMetricsCalculator, UserProfile
from .const import (
    CONF_PROFILE_NAME,
    CONF_PROFILES,
    CONF_USER_AGE,
    CONF_USER_HEIGHT,
    CONF_USER_SEX,
    CONF_WEIGHT_MAX,
    CONF_WEIGHT_MIN,
    CONF_WEIGHT_UNIT,
    DEFAULT_WEIGHT_MAX,
    DEFAULT_WEIGHT_MIN,
    KG_TO_LBS,
    WEIGHT_UNIT_KG,
    WEIGHT_UNIT_LBS,
)
from .models import EufyLifeConfigEntry, EufyLifeData

_LOGGER = logging.getLogger(__name__)

IGNORED_STATES = {STATE_UNAVAILABLE, STATE_UNKNOWN}


@dataclass(frozen=True)
class ProfileConfig:
    """A named user profile with a weight range for auto-matching measurements."""

    profile_id: str
    name: str
    profile: UserProfile
    weight_min: float
    weight_max: float
    weight_unit: str = WEIGHT_UNIT_KG  # unit of weight_min / weight_max


def _get_profiles(entry: EufyLifeConfigEntry) -> list[ProfileConfig]:
    """Return all configured profiles from config entry options."""
    profiles_data: dict = entry.options.get(CONF_PROFILES, {})
    result: list[ProfileConfig] = []

    for profile_id, data in profiles_data.items():
        if CONF_PROFILE_NAME not in data or CONF_USER_AGE not in data:
            continue
        try:
            result.append(
                ProfileConfig(
                    profile_id=profile_id,
                    name=data[CONF_PROFILE_NAME],
                    profile=UserProfile(
                        age=int(data[CONF_USER_AGE]),
                        height=float(data[CONF_USER_HEIGHT]),
                        sex=data[CONF_USER_SEX],
                    ),
                    weight_min=float(data.get(CONF_WEIGHT_MIN, DEFAULT_WEIGHT_MIN)),
                    weight_max=float(data.get(CONF_WEIGHT_MAX, DEFAULT_WEIGHT_MAX)),
                    # Profiles created before unit support default to kg
                    weight_unit=data.get(CONF_WEIGHT_UNIT, WEIGHT_UNIT_KG),
                )
            )
        except (KeyError, ValueError, TypeError):
            _LOGGER.warning("Skipping malformed profile %s", profile_id)

    return result


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EufyLifeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the EufyLife sensors."""
    data = entry.runtime_data

    entities: list[SensorEntity] = [
        EufyLifeWeightSensorEntity(data),
        EufyLifeRealTimeWeightSensorEntity(data),
    ]

    if data.client.supports_heart_rate:
        entities.append(EufyLifeHeartRateSensorEntity(data))

    # Add impedance sensor for scales that support body composition
    if data.client.supports_body_composition:
        entities.append(EufyLifeImpedanceSensorEntity(data))

    # Add one set of body composition sensors per configured profile
    profiles = _get_profiles(entry)
    if profiles and data.client.supports_body_composition:
        for pc in profiles:
            entities.extend([
                EufyLifeBodyFatSensorEntity(data, pc),
                EufyLifeMuscleMassSensorEntity(data, pc),
                EufyLifeBoneMassSensorEntity(data, pc),
                EufyLifeWaterPercentageSensorEntity(data, pc),
                EufyLifeVisceralFatSensorEntity(data, pc),
                EufyLifeBMISensorEntity(data, pc),
                EufyLifeBMRSensorEntity(data, pc),
                EufyLifeMetabolicAgeSensorEntity(data, pc),
                EufyLifeProteinPercentageSensorEntity(data, pc),
            ])

    async_add_entities(entities)


class EufyLifeSensorEntity(SensorEntity):
    """Representation of an EufyLife sensor."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, data: EufyLifeData) -> None:
        """Initialize the weight sensor entity."""
        self._data = data

        self._attr_device_info = DeviceInfo(
            name=MODEL_TO_NAME[data.model],
            connections={(dr.CONNECTION_BLUETOOTH, data.address)},
        )

    @property
    def available(self) -> bool:
        """Determine if the entity is available."""
        if self._data.client.advertisement_data_contains_state:
            return async_address_present(self.hass, self._data.address)
        return self._data.client.is_connected

    @callback
    def _handle_state_update(self, *args: Any) -> None:
        """Handle state update."""
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register callback."""
        self.async_on_remove(
            self._data.client.register_callback(self._handle_state_update)
        )


class EufyLifeRealTimeWeightSensorEntity(EufyLifeSensorEntity):
    """Representation of an EufyLife real-time weight sensor."""

    _attr_translation_key = "real_time_weight"
    _attr_name = "Real-time weight"
    _attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
    _attr_device_class = SensorDeviceClass.WEIGHT

    def __init__(self, data: EufyLifeData) -> None:
        """Initialize the real-time weight sensor entity."""
        super().__init__(data)
        self._attr_unique_id = f"{data.address}_real_time_weight"

    @property
    def native_value(self) -> float | None:
        """Return the native value of the sensor."""
        if self._data.client.state is not None:
            return self._data.client.state.weight_kg
        return None

    @property
    def suggested_unit_of_measurement(self) -> str | None:
        """Return the suggested unit of measurement."""
        if self.hass.config.units is US_CUSTOMARY_SYSTEM:
            return UnitOfMass.POUNDS
        return UnitOfMass.KILOGRAMS


class EufyLifeWeightSensorEntity(RestoreSensor, EufyLifeSensorEntity):
    """Representation of an EufyLife weight sensor."""

    _attr_translation_key = "weight"
    _attr_name = "Weight"
    _attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
    _attr_device_class = SensorDeviceClass.WEIGHT

    def __init__(self, data: EufyLifeData) -> None:
        """Initialize the weight sensor entity."""
        super().__init__(data)
        self._attr_unique_id = f"{data.address}_weight"

    @property
    def available(self) -> bool:
        """Determine if the entity is available."""
        return True

    @property
    def suggested_unit_of_measurement(self) -> str | None:
        """Return the suggested unit of measurement."""
        if self.hass.config.units is US_CUSTOMARY_SYSTEM:
            return UnitOfMass.POUNDS
        return UnitOfMass.KILOGRAMS

    @callback
    def _handle_state_update(self, *args: Any) -> None:
        """Handle state update."""
        state = self._data.client.state
        if state is not None and state.final_weight_kg is not None:
            self._attr_native_value = state.final_weight_kg
        super()._handle_state_update(args)

    async def async_added_to_hass(self) -> None:
        """Register callback."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        last_sensor_data = await self.async_get_last_sensor_data()
        if not last_state or not last_sensor_data or last_state.state in IGNORED_STATES:
            return
        self._attr_native_value = last_sensor_data.native_value


class EufyLifeHeartRateSensorEntity(RestoreSensor, EufyLifeSensorEntity):
    """Representation of an EufyLife heart rate sensor."""

    _attr_translation_key = "heart_rate"
    _attr_name = "Heart rate"
    _attr_native_unit_of_measurement = "bpm"

    def __init__(self, data: EufyLifeData) -> None:
        """Initialize the heart rate sensor entity."""
        super().__init__(data)
        self._attr_unique_id = f"{data.address}_heart_rate"

    @property
    def available(self) -> bool:
        """Determine if the entity is available."""
        return True

    @callback
    def _handle_state_update(self, *args: Any) -> None:
        """Handle state update."""
        state = self._data.client.state
        if state is not None and state.heart_rate is not None:
            self._attr_native_value = state.heart_rate
        # Also check extended heart rate (T9150)
        hr_ext = self._data.client.heart_rate_extended
        if hr_ext is not None:
            self._attr_native_value = hr_ext
        super()._handle_state_update(args)

    async def async_added_to_hass(self) -> None:
        """Register callback."""
        await super().async_added_to_hass()
        # Also register for extended callbacks (T9150 heart rate)
        self.async_on_remove(
            self._data.client.register_extended_callback(
                lambda: self.async_write_ha_state()
            )
        )
        last_state = await self.async_get_last_state()
        last_sensor_data = await self.async_get_last_sensor_data()
        if not last_state or not last_sensor_data or last_state.state in IGNORED_STATES:
            return
        self._attr_native_value = last_sensor_data.native_value


class EufyLifeImpedanceSensorEntity(RestoreSensor, EufyLifeSensorEntity):
    """Representation of an EufyLife impedance sensor."""

    _attr_translation_key = "impedance"
    _attr_name = "Impedance"
    _attr_native_unit_of_measurement = "Ohm"

    def __init__(self, data: EufyLifeData) -> None:
        """Initialize the impedance sensor entity."""
        super().__init__(data)
        self._attr_unique_id = f"{data.address}_impedance"

    @property
    def available(self) -> bool:
        """Determine if the entity is available."""
        return True

    @callback
    def _handle_extended_update(self) -> None:
        """Handle extended data update."""
        impedance = self._data.client.impedance_final
        if impedance is not None:
            self._attr_native_value = impedance
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register callback."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._data.client.register_extended_callback(
                self._handle_extended_update
            )
        )
        last_state = await self.async_get_last_state()
        last_sensor_data = await self.async_get_last_sensor_data()
        if not last_state or not last_sensor_data or last_state.state in IGNORED_STATES:
            return
        self._attr_native_value = last_sensor_data.native_value


class EufyLifeBodyCompositionSensorEntity(RestoreSensor, EufyLifeSensorEntity):
    """Base class for profile-specific body composition sensors.

    Only recalculates when both final weight and final impedance are available
    AND the weight falls within the profile's configured weight range.
    """

    def __init__(self, data: EufyLifeData, profile_config: ProfileConfig) -> None:
        """Initialize the body composition sensor entity."""
        super().__init__(data)
        self._profile_config = profile_config
        self._last_result: BodyCompositionResult | None = None

    @property
    def available(self) -> bool:
        """Determine if the entity is available."""
        return True

    def _extract_value(self, result: BodyCompositionResult) -> float | int | str | None:
        """Extract this sensor's specific value from the result. Override in subclass."""
        raise NotImplementedError

    @callback
    def _handle_extended_update(self) -> None:
        """Recalculate body composition if weight matches this profile's range."""
        client = self._data.client
        impedance_final = client.impedance_final
        state = client.state

        if (
            impedance_final is None
            or state is None
            or state.final_weight_kg is None
        ):
            return

        weight_kg = state.final_weight_kg

        # Convert the scale reading to the profile's configured unit for comparison
        if self._profile_config.weight_unit == WEIGHT_UNIT_LBS:
            measured = weight_kg * KG_TO_LBS
        else:
            measured = weight_kg

        # Only update if the measured weight falls within this profile's range
        if not (
            self._profile_config.weight_min <= measured <= self._profile_config.weight_max
        ):
            return

        try:
            calculator = BodyMetricsCalculator(
                weight=weight_kg,
                impedance=impedance_final,
                profile=self._profile_config.profile,
            )
            result = calculator.calculate_all()
            self._last_result = result
            value = self._extract_value(result)
            if value is not None:
                self._attr_native_value = value
                self.async_write_ha_state()
        except Exception:
            _LOGGER.exception(
                "Error calculating body composition for profile %s",
                self._profile_config.name,
            )

    async def async_added_to_hass(self) -> None:
        """Register callback."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._data.client.register_extended_callback(
                self._handle_extended_update
            )
        )
        # Also recalculate on standard state updates (weight changes)
        self.async_on_remove(
            self._data.client.register_callback(
                lambda *args: self._handle_extended_update()
            )
        )
        last_state = await self.async_get_last_state()
        last_sensor_data = await self.async_get_last_sensor_data()
        if not last_state or not last_sensor_data or last_state.state in IGNORED_STATES:
            return
        self._attr_native_value = last_sensor_data.native_value


class EufyLifeBodyFatSensorEntity(EufyLifeBodyCompositionSensorEntity):
    """Representation of an EufyLife body fat percentage sensor."""

    _attr_native_unit_of_measurement = "%"

    def __init__(self, data: EufyLifeData, profile_config: ProfileConfig) -> None:
        """Initialize the body fat sensor entity."""
        super().__init__(data, profile_config)
        self._attr_unique_id = f"{data.address}_body_fat_{profile_config.profile_id}"
        self._attr_name = f"Body fat - {profile_config.name}"

    def _extract_value(self, result: BodyCompositionResult) -> float | None:
        return result.body_fat


class EufyLifeMuscleMassSensorEntity(EufyLifeBodyCompositionSensorEntity):
    """Representation of an EufyLife muscle mass sensor."""

    _attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
    _attr_device_class = SensorDeviceClass.WEIGHT

    def __init__(self, data: EufyLifeData, profile_config: ProfileConfig) -> None:
        """Initialize the muscle mass sensor entity."""
        super().__init__(data, profile_config)
        self._attr_unique_id = f"{data.address}_muscle_mass_{profile_config.profile_id}"
        self._attr_name = f"Muscle mass - {profile_config.name}"

    def _extract_value(self, result: BodyCompositionResult) -> float | None:
        return result.muscle_mass


class EufyLifeBoneMassSensorEntity(EufyLifeBodyCompositionSensorEntity):
    """Representation of an EufyLife bone mass sensor."""

    _attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
    _attr_device_class = SensorDeviceClass.WEIGHT

    def __init__(self, data: EufyLifeData, profile_config: ProfileConfig) -> None:
        """Initialize the bone mass sensor entity."""
        super().__init__(data, profile_config)
        self._attr_unique_id = f"{data.address}_bone_mass_{profile_config.profile_id}"
        self._attr_name = f"Bone mass - {profile_config.name}"

    def _extract_value(self, result: BodyCompositionResult) -> float | None:
        return result.bone_mass


class EufyLifeWaterPercentageSensorEntity(EufyLifeBodyCompositionSensorEntity):
    """Representation of an EufyLife water percentage sensor."""

    _attr_native_unit_of_measurement = "%"

    def __init__(self, data: EufyLifeData, profile_config: ProfileConfig) -> None:
        """Initialize the water percentage sensor entity."""
        super().__init__(data, profile_config)
        self._attr_unique_id = f"{data.address}_water_pct_{profile_config.profile_id}"
        self._attr_name = f"Water percentage - {profile_config.name}"

    def _extract_value(self, result: BodyCompositionResult) -> float | None:
        return result.water_percentage


class EufyLifeVisceralFatSensorEntity(EufyLifeBodyCompositionSensorEntity):
    """Representation of an EufyLife visceral fat sensor."""

    def __init__(self, data: EufyLifeData, profile_config: ProfileConfig) -> None:
        """Initialize the visceral fat sensor entity."""
        super().__init__(data, profile_config)
        self._attr_unique_id = f"{data.address}_visceral_fat_{profile_config.profile_id}"
        self._attr_name = f"Visceral fat - {profile_config.name}"

    def _extract_value(self, result: BodyCompositionResult) -> float | None:
        return result.visceral_fat


class EufyLifeBMISensorEntity(EufyLifeBodyCompositionSensorEntity):
    """Representation of an EufyLife BMI sensor."""

    def __init__(self, data: EufyLifeData, profile_config: ProfileConfig) -> None:
        """Initialize the BMI sensor entity."""
        super().__init__(data, profile_config)
        self._attr_unique_id = f"{data.address}_bmi_{profile_config.profile_id}"
        self._attr_name = f"BMI - {profile_config.name}"

    def _extract_value(self, result: BodyCompositionResult) -> float | None:
        return result.bmi


class EufyLifeBMRSensorEntity(EufyLifeBodyCompositionSensorEntity):
    """Representation of an EufyLife BMR sensor."""

    _attr_native_unit_of_measurement = "kcal"

    def __init__(self, data: EufyLifeData, profile_config: ProfileConfig) -> None:
        """Initialize the BMR sensor entity."""
        super().__init__(data, profile_config)
        self._attr_unique_id = f"{data.address}_bmr_{profile_config.profile_id}"
        self._attr_name = f"Basal metabolic rate - {profile_config.name}"

    def _extract_value(self, result: BodyCompositionResult) -> float | None:
        return result.bmr


class EufyLifeMetabolicAgeSensorEntity(EufyLifeBodyCompositionSensorEntity):
    """Representation of an EufyLife metabolic age sensor."""

    _attr_native_unit_of_measurement = "yr"

    def __init__(self, data: EufyLifeData, profile_config: ProfileConfig) -> None:
        """Initialize the metabolic age sensor entity."""
        super().__init__(data, profile_config)
        self._attr_unique_id = f"{data.address}_metabolic_age_{profile_config.profile_id}"
        self._attr_name = f"Metabolic age - {profile_config.name}"

    def _extract_value(self, result: BodyCompositionResult) -> int | None:
        return result.metabolic_age


class EufyLifeProteinPercentageSensorEntity(EufyLifeBodyCompositionSensorEntity):
    """Representation of an EufyLife protein percentage sensor."""

    _attr_native_unit_of_measurement = "%"

    def __init__(self, data: EufyLifeData, profile_config: ProfileConfig) -> None:
        """Initialize the protein percentage sensor entity."""
        super().__init__(data, profile_config)
        self._attr_unique_id = f"{data.address}_protein_pct_{profile_config.profile_id}"
        self._attr_name = f"Protein percentage - {profile_config.name}"

    def _extract_value(self, result: BodyCompositionResult) -> float | None:
        return result.protein_percentage
