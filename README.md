# EufyLife BLE — Home Assistant Custom Integration

A Home Assistant custom integration for **Eufy Smart Scale** devices via Bluetooth Low Energy.

Supports multiple user profiles on the same scale — each person's body composition stats are tracked independently, automatically identified by weight range.

---

## Supported Devices

| Model | Weight | Body Composition | Heart Rate |
|-------|--------|-----------------|------------|
| eufy T9140 | ✅ | ❌ | ❌ |
| eufy T9146 | ✅ | ❌ | ❌ |
| eufy T9147 | ✅ | ❌ | ❌ |
| eufy T9148 | ✅ | ✅ | ❌ |
| eufy T9149 | ✅ | ✅ | ✅ |
| eufy T9150 | ✅ | ✅ | ✅ |

---

## Features

- **Real-time weight** and **final weight** sensors
- **Impedance** (raw BIA value)
- **Heart rate** (T9149, T9150)
- **Body composition** per profile (9 metrics):
  - Body fat %, Muscle mass, Bone mass, Water %, Visceral fat
  - BMI, Basal metabolic rate, Metabolic age, Protein %
- **Multi-profile support** — up to N named profiles, each with its own set of sensors
- **Auto-routing by weight range** — measurements are automatically assigned to the matching profile
- **Unit selection** — height in cm or ft/in, weight in kg or lbs (converted transparently; all calculations use metric internally)

---

## Installation

### HACS (recommended)

1. In HACS → **Custom repositories** → add this repo URL → category **Integration**
2. Search for *EufyLife BLE* and install
3. Restart Home Assistant

### Manual

1. Copy `custom_components/eufylife_ble/` into your HA `config/custom_components/` folder
2. Restart Home Assistant

---

## Configuration

The integration is discovered automatically when a supported scale is nearby.

After adding the device, open **Settings → Devices → EufyLife → Configure** to manage profiles:

1. **Add a new profile** (3 steps)
   - Step 1: Name, Age, Sex, height unit (cm / ft & in), weight unit (lbs / kg)
   - Step 2: Height in the chosen unit
   - Step 3: Weight range — the scale only calculates body composition for this profile when the measured weight falls within the range
2. **Edit / Delete a profile** — select from the list; changing units auto-converts values
3. **Save and close**

Each profile creates its own set of sensors named `Body fat - Alice`, `Muscle mass - Bob`, etc.

---

## Body Composition Formulas

Formulas use **Bioelectrical Impedance Analysis (BIA)** calibrated against the EufyLife official app. The core metric is **Lean Body Mass** computed as:

```
LBM = A × (height² / impedance) + B × weight − C × age + D
```

with sex-specific coefficients, from which all other metrics are derived.

> **Note:** Impedance byte positions were determined by reverse engineering. Body composition values should be close to the official app but may differ slightly. Heart rate and impedance support for T9148/T9149 is still being validated.

---

## Credits

- BLE client library: [eufylife-ble-client](https://github.com/bdr99/eufylife-ble-client) by [@bdr99](https://github.com/bdr99)
- Body composition formulas adapted from [ha-miscale2](https://github.com/dckiller51/ha-miscale2)
- Multi-profile & impedance extensions by [@lyntoo](https://github.com/lyntoo)
