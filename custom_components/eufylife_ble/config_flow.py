"""Config flow for the EufyLife integration."""

from __future__ import annotations

import re
from typing import Any

from eufylife_ble_client import MODEL_TO_NAME
import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithConfigEntry,
)
from homeassistant.const import CONF_ADDRESS, CONF_MODEL
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    SelectOptionDict,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_HEIGHT_FT,
    CONF_HEIGHT_IN,
    CONF_HEIGHT_UNIT,
    CONF_PROFILE_NAME,
    CONF_PROFILES,
    CONF_USER_AGE,
    CONF_USER_HEIGHT,
    CONF_USER_SEX,
    CONF_WEIGHT_MAX,
    CONF_WEIGHT_MIN,
    CONF_WEIGHT_UNIT,
    DEFAULT_HEIGHT_UNIT,
    DEFAULT_USER_AGE,
    DEFAULT_USER_HEIGHT,
    DEFAULT_USER_SEX,
    DEFAULT_WEIGHT_MAX,
    DEFAULT_WEIGHT_MIN,
    DEFAULT_WEIGHT_UNIT,
    DOMAIN,
    HEIGHT_UNIT_CM,
    HEIGHT_UNIT_FTIN,
    KG_TO_LBS,
    SEX_FEMALE,
    SEX_MALE,
    WEIGHT_UNIT_KG,
    WEIGHT_UNIT_LBS,
)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Convert a display name to a slug safe for use as a profile ID."""
    slug = re.sub(r"\s+", "_", name.lower().strip())
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    return slug or "profile"


def _cm_to_ftin(height_cm: float) -> tuple[int, float]:
    """Convert centimetres to (feet, inches)."""
    total_inches = height_cm / 2.54
    ft = int(total_inches // 12)
    inches = round(total_inches % 12, 1)
    return ft, inches


def _ftin_to_cm(feet: int, inches: float) -> float:
    """Convert feet + inches to centimetres."""
    return round(feet * 30.48 + inches * 2.54, 1)


def _height_defaults(height_cm: float, height_unit: str) -> dict[str, Any]:
    """Return pre-fill values for the height step depending on unit."""
    if height_unit == HEIGHT_UNIT_FTIN:
        ft, inches = _cm_to_ftin(height_cm)
        return {CONF_HEIGHT_FT: ft, CONF_HEIGHT_IN: inches}
    return {CONF_USER_HEIGHT: round(height_cm, 1)}


# ---------------------------------------------------------------------------
# Schema builders
# ---------------------------------------------------------------------------

def _profile_basic_schema(
    defaults: dict[str, Any], include_delete: bool = False
) -> vol.Schema:
    """Step 1: name, age, sex, height unit, weight unit."""
    fields: dict = {
        vol.Required(
            CONF_PROFILE_NAME,
            default=defaults.get(CONF_PROFILE_NAME, ""),
        ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
        vol.Required(
            CONF_USER_AGE,
            default=defaults.get(CONF_USER_AGE, DEFAULT_USER_AGE),
        ): NumberSelector(
            NumberSelectorConfig(
                min=1, max=99, step=1,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="years",
            )
        ),
        vol.Required(
            CONF_USER_SEX,
            default=defaults.get(CONF_USER_SEX, DEFAULT_USER_SEX),
        ): SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value=SEX_MALE, label="Male"),
                    SelectOptionDict(value=SEX_FEMALE, label="Female"),
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(
            CONF_HEIGHT_UNIT,
            default=defaults.get(CONF_HEIGHT_UNIT, DEFAULT_HEIGHT_UNIT),
        ): SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value=HEIGHT_UNIT_CM, label="cm"),
                    SelectOptionDict(value=HEIGHT_UNIT_FTIN, label="ft & in"),
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(
            CONF_WEIGHT_UNIT,
            default=defaults.get(CONF_WEIGHT_UNIT, DEFAULT_WEIGHT_UNIT),
        ): SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value=WEIGHT_UNIT_LBS, label="lbs"),
                    SelectOptionDict(value=WEIGHT_UNIT_KG, label="kg"),
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
    }
    if include_delete:
        fields[vol.Required("delete_profile", default=False)] = BooleanSelector()
    return vol.Schema(fields)


def _profile_height_schema(
    defaults: dict[str, Any], height_unit: str
) -> vol.Schema:
    """Step 2: height entry — cm or feet + inches, depending on chosen unit."""
    if height_unit == HEIGHT_UNIT_FTIN:
        return vol.Schema(
            {
                vol.Required(
                    CONF_HEIGHT_FT,
                    default=defaults.get(CONF_HEIGHT_FT, 5),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1, max=8, step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="ft",
                    )
                ),
                vol.Required(
                    CONF_HEIGHT_IN,
                    default=defaults.get(CONF_HEIGHT_IN, 7.0),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0, max=11, step=0.5,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="in",
                    )
                ),
            }
        )
    # cm
    return vol.Schema(
        {
            vol.Required(
                CONF_USER_HEIGHT,
                default=defaults.get(CONF_USER_HEIGHT, DEFAULT_USER_HEIGHT),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=50, max=250, step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="cm",
                )
            ),
        }
    )


def _profile_range_schema(
    defaults: dict[str, Any], unit: str
) -> vol.Schema:
    """Step 3: weight range, labeled in the chosen unit."""
    unit_label = WEIGHT_UNIT_LBS if unit == WEIGHT_UNIT_LBS else WEIGHT_UNIT_KG
    max_val = 700.0 if unit == WEIGHT_UNIT_LBS else 300.0

    return vol.Schema(
        {
            vol.Required(
                CONF_WEIGHT_MIN,
                default=defaults.get(CONF_WEIGHT_MIN, DEFAULT_WEIGHT_MIN),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0.0, max=max_val, step=0.5,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement=unit_label,
                )
            ),
            vol.Required(
                CONF_WEIGHT_MAX,
                default=defaults.get(CONF_WEIGHT_MAX, DEFAULT_WEIGHT_MAX),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0.0, max=max_val, step=0.5,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement=unit_label,
                )
            ),
        }
    )


def _extract_height_cm(user_input: dict[str, Any], height_unit: str) -> float:
    """Return height in cm from the user's input on the height step."""
    if height_unit == HEIGHT_UNIT_FTIN:
        return _ftin_to_cm(
            int(user_input[CONF_HEIGHT_FT]),
            float(user_input[CONF_HEIGHT_IN]),
        )
    return float(user_input[CONF_USER_HEIGHT])


# ---------------------------------------------------------------------------
# Config flow (device discovery)
# ---------------------------------------------------------------------------

class EufyLifeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EufyLife."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, str] = {}

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return EufyLifeOptionsFlowHandler(config_entry)

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle the bluetooth discovery step."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        if discovery_info.name not in MODEL_TO_NAME:
            return self.async_abort(reason="not_supported")
        self._discovery_info = discovery_info
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery."""
        assert self._discovery_info is not None
        discovery_info = self._discovery_info
        model_name = MODEL_TO_NAME.get(discovery_info.name)
        assert model_name is not None
        if user_input is not None:
            return self.async_create_entry(
                title=model_name, data={CONF_MODEL: discovery_info.name}
            )
        self._set_confirm_only()
        placeholders = {"name": model_name}
        self.context["title_placeholders"] = placeholders
        return self.async_show_form(
            step_id="bluetooth_confirm", description_placeholders=placeholders
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step to pick discovered device."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            model = self._discovered_devices[address]
            return self.async_create_entry(
                title=MODEL_TO_NAME[model], data={CONF_MODEL: model}
            )
        current_addresses = self._async_current_ids(include_ignore=False)
        for discovery_info in async_discovered_service_info(self.hass, False):
            address = discovery_info.address
            if (
                address in current_addresses
                or address in self._discovered_devices
                or discovery_info.name not in MODEL_TO_NAME
            ):
                continue
            self._discovered_devices[address] = discovery_info.name
        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_ADDRESS): vol.In(self._discovered_devices)}
            ),
        )


# ---------------------------------------------------------------------------
# Options flow (profile management)
# ---------------------------------------------------------------------------

class EufyLifeOptionsFlowHandler(OptionsFlowWithConfigEntry):
    """Handle EufyLife options — multi-profile configuration."""

    def __init__(self, config_entry) -> None:
        """Initialize options flow and load existing profiles."""
        super().__init__(config_entry)
        self._profiles: dict[str, dict] = dict(
            self.options.get(CONF_PROFILES, {})
        )
        self._editing_profile_id: str | None = None
        # Temporary storage shared across the multi-step add / edit flow
        self._pending: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Main menu (select-based, labels embedded inline)
    # ------------------------------------------------------------------

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show main action selector.  Auto-migrates old single-profile options."""
        # Silently migrate legacy single-profile options
        if not self._profiles and CONF_USER_AGE in self.options:
            self._profiles["default"] = {
                CONF_PROFILE_NAME: "Default",
                CONF_USER_AGE: int(self.options[CONF_USER_AGE]),
                CONF_USER_HEIGHT: float(
                    self.options.get(CONF_USER_HEIGHT, DEFAULT_USER_HEIGHT)
                ),
                CONF_USER_SEX: self.options.get(CONF_USER_SEX, DEFAULT_USER_SEX),
                CONF_HEIGHT_UNIT: HEIGHT_UNIT_CM,
                CONF_WEIGHT_UNIT: DEFAULT_WEIGHT_UNIT,
                CONF_WEIGHT_MIN: DEFAULT_WEIGHT_MIN,
                CONF_WEIGHT_MAX: DEFAULT_WEIGHT_MAX,
            }

        if user_input is not None:
            action = user_input.get("action")
            if action == "add_profile":
                return await self.async_step_add_profile()
            if action == "manage_profiles":
                return await self.async_step_manage_profiles()
            return await self.async_step_finish()

        options: list[SelectOptionDict] = [
            SelectOptionDict(value="add_profile", label="➕  Add a new profile"),
        ]
        if self._profiles:
            names = ", ".join(v[CONF_PROFILE_NAME] for v in self._profiles.values())
            options.append(
                SelectOptionDict(
                    value="manage_profiles",
                    label=f"✏️  Edit / Delete a profile  ({names})",
                )
            )
        options.append(
            SelectOptionDict(value="finish", label="💾  Save and close")
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    # ------------------------------------------------------------------
    # ADD — step 1: basic info (name, age, sex, height unit, weight unit)
    # ------------------------------------------------------------------

    async def async_step_add_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add profile — step 1/3: basic info."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input.get(CONF_PROFILE_NAME, "").strip()
            if not name:
                errors[CONF_PROFILE_NAME] = "name_required"
            else:
                self._pending = {**user_input, CONF_PROFILE_NAME: name}
                return await self.async_step_add_profile_height()

        return self.async_show_form(
            step_id="add_profile",
            data_schema=_profile_basic_schema({}),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # ADD — step 2: height (cm or ft+in)
    # ------------------------------------------------------------------

    async def async_step_add_profile_height(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add profile — step 2/3: height in chosen unit."""
        height_unit = self._pending.get(CONF_HEIGHT_UNIT, HEIGHT_UNIT_CM)

        if user_input is not None:
            self._pending[CONF_USER_HEIGHT] = _extract_height_cm(
                user_input, height_unit
            )
            return await self.async_step_add_profile_range()

        defaults = _height_defaults(DEFAULT_USER_HEIGHT, height_unit)
        return self.async_show_form(
            step_id="add_profile_height",
            data_schema=_profile_height_schema(defaults, height_unit),
        )

    # ------------------------------------------------------------------
    # ADD — step 3: weight range
    # ------------------------------------------------------------------

    async def async_step_add_profile_range(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add profile — step 3/3: weight range."""
        weight_unit = self._pending.get(CONF_WEIGHT_UNIT, DEFAULT_WEIGHT_UNIT)

        if user_input is not None:
            base_id = _slugify(self._pending[CONF_PROFILE_NAME])
            profile_id = base_id
            counter = 2
            while profile_id in self._profiles:
                profile_id = f"{base_id}_{counter}"
                counter += 1
            self._profiles[profile_id] = {
                **self._pending,
                CONF_WEIGHT_MIN: float(user_input[CONF_WEIGHT_MIN]),
                CONF_WEIGHT_MAX: float(user_input[CONF_WEIGHT_MAX]),
            }
            self._pending = {}
            return await self.async_step_init()

        return self.async_show_form(
            step_id="add_profile_range",
            data_schema=_profile_range_schema(
                {CONF_WEIGHT_MIN: DEFAULT_WEIGHT_MIN, CONF_WEIGHT_MAX: DEFAULT_WEIGHT_MAX},
                weight_unit,
            ),
        )

    # ------------------------------------------------------------------
    # MANAGE: pick an existing profile
    # ------------------------------------------------------------------

    async def async_step_manage_profiles(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select an existing profile to edit or delete."""
        if user_input is not None:
            self._editing_profile_id = user_input["profile_id"]
            return await self.async_step_edit_profile()

        profile_options = [
            SelectOptionDict(value=k, label=v[CONF_PROFILE_NAME])
            for k, v in self._profiles.items()
        ]
        return self.async_show_form(
            step_id="manage_profiles",
            data_schema=vol.Schema(
                {
                    vol.Required("profile_id"): SelectSelector(
                        SelectSelectorConfig(
                            options=profile_options,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    # ------------------------------------------------------------------
    # EDIT — step 1: basic info (+ delete toggle)
    # ------------------------------------------------------------------

    async def async_step_edit_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit profile — step 1/3: basic info and unit choices."""
        assert self._editing_profile_id is not None
        current = self._profiles[self._editing_profile_id]
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input.get("delete_profile"):
                del self._profiles[self._editing_profile_id]
                self._editing_profile_id = None
                return await self.async_step_init()

            name = user_input.get(CONF_PROFILE_NAME, "").strip()
            if not name:
                errors[CONF_PROFILE_NAME] = "name_required"
            else:
                # Auto-convert weight range when weight unit changes
                old_wu = current.get(CONF_WEIGHT_UNIT, WEIGHT_UNIT_KG)
                new_wu = user_input[CONF_WEIGHT_UNIT]
                old_min = float(current.get(CONF_WEIGHT_MIN, DEFAULT_WEIGHT_MIN))
                old_max = float(current.get(CONF_WEIGHT_MAX, DEFAULT_WEIGHT_MAX))

                if old_wu != new_wu:
                    factor = (
                        KG_TO_LBS
                        if (old_wu == WEIGHT_UNIT_KG and new_wu == WEIGHT_UNIT_LBS)
                        else (1.0 / KG_TO_LBS)
                    )
                    converted_min = round(old_min * factor, 1)
                    converted_max = round(old_max * factor, 1)
                else:
                    converted_min, converted_max = old_min, old_max

                self._pending = {
                    **{k: v for k, v in user_input.items() if k != "delete_profile"},
                    CONF_PROFILE_NAME: name,
                    # Keep current height (cm) — will be updated in next step
                    CONF_USER_HEIGHT: float(
                        current.get(CONF_USER_HEIGHT, DEFAULT_USER_HEIGHT)
                    ),
                    CONF_WEIGHT_MIN: converted_min,
                    CONF_WEIGHT_MAX: converted_max,
                }
                return await self.async_step_edit_profile_height()

        return self.async_show_form(
            step_id="edit_profile",
            data_schema=_profile_basic_schema(current, include_delete=True),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # EDIT — step 2: height (cm or ft+in, auto-converted if unit changed)
    # ------------------------------------------------------------------

    async def async_step_edit_profile_height(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit profile — step 2/3: height."""
        height_unit = self._pending.get(CONF_HEIGHT_UNIT, HEIGHT_UNIT_CM)
        stored_cm = float(self._pending.get(CONF_USER_HEIGHT, DEFAULT_USER_HEIGHT))

        if user_input is not None:
            self._pending[CONF_USER_HEIGHT] = _extract_height_cm(
                user_input, height_unit
            )
            return await self.async_step_edit_profile_range()

        defaults = _height_defaults(stored_cm, height_unit)
        return self.async_show_form(
            step_id="edit_profile_height",
            data_schema=_profile_height_schema(defaults, height_unit),
        )

    # ------------------------------------------------------------------
    # EDIT — step 3: weight range (auto-converted if unit changed)
    # ------------------------------------------------------------------

    async def async_step_edit_profile_range(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit profile — step 3/3: weight range."""
        weight_unit = self._pending.get(CONF_WEIGHT_UNIT, WEIGHT_UNIT_KG)

        if user_input is not None:
            self._profiles[self._editing_profile_id] = {
                **self._pending,
                CONF_WEIGHT_MIN: float(user_input[CONF_WEIGHT_MIN]),
                CONF_WEIGHT_MAX: float(user_input[CONF_WEIGHT_MAX]),
            }
            self._editing_profile_id = None
            self._pending = {}
            return await self.async_step_init()

        range_defaults = {
            CONF_WEIGHT_MIN: self._pending.get(CONF_WEIGHT_MIN, DEFAULT_WEIGHT_MIN),
            CONF_WEIGHT_MAX: self._pending.get(CONF_WEIGHT_MAX, DEFAULT_WEIGHT_MAX),
        }
        return self.async_show_form(
            step_id="edit_profile_range",
            data_schema=_profile_range_schema(range_defaults, weight_unit),
        )

    # ------------------------------------------------------------------
    # Save and close
    # ------------------------------------------------------------------

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Persist all profiles and close the options flow."""
        return self.async_create_entry(
            title="",
            data={CONF_PROFILES: self._profiles},
        )
