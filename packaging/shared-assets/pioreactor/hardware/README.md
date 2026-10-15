# Hardware YAML Mods

All hardware configuration lives in your home directory only. There are no package defaults.

Base directory on a device: `/home/pioreactor/.pioreactor/hardware`  
For local dev/tests, set `DOT_PIOREACTOR=/path/to/repo/.pioreactor` so the loader reads from this tree.

## Layering and Gating

- Layering order (later overrides earlier):
  1. `hats/<hat_version>/<mod>.yaml`
  2. `models/<model>/<version>/<mod>.yaml`
- Capability gating: a mod is enabled for a model only if
  `models/<model>/<version>/<mod>.yaml` exists. Hat files alone do not enable it.
- Detection policy: we detect the HAT version only. No runtime I2C probing beyond explicit self-tests.


## Directory Layout (example)

```
~/.pioreactor/hardware/
  hats/
    1.0/
      pwm.yaml
      adc.yaml   # aux/version wiring for HAT 1.0
    1.1/
      pwm.yaml
      adc.yaml   # aux/version wiring for HAT 1.1 (Pico)
      dac.yaml   # HAT-specific DAC address
      temp.yaml  # heating pcb temp sensor address
  models/
    pioreactor_20ml/
      1.0/
        adc.yaml   # model selects optics (pd1/pd2)
      1.1/
        adc.yaml
      1.5/
        adc.yaml
    pioreactor_40ml/
      1.0/
        adc.yaml
      1.5/
        adc.yaml
```

## YAML Schemas (initial)

- `pwm.yaml`
  - `controller`: `rpi_gpio` | `hat_mcu`
  - `heater_pwm_channel`: string channel (e.g., "5")
  - `pwm_to_pin`: map of channel string to BCM pin, e.g. `{ "1": 17, "2": 13, "3": 16, "4": 12, "5": 18 }`
- `adc.yaml`
  - Each of `pd1`, `pd2`, `aux`, `version` has:
    - `driver`: `ads1115` | `ads1114` | `pico`
    - `address`: I2C address (e.g., `0x48` or `44`)
    - `channel`: integer channel (0..3)
- `dac.yaml`
  - `address`: I2C address
- `temp.yaml`
  - `address`: I2C address
- `gpio.yaml` (optional)
  - `pcb_led_pin`: BCM pin for onboard LED
  - `pcb_button_pin`: BCM pin for onboard button
  - `hall_sensor_pin`: BCM pin for hall sensor
  - `sda_pin`: I2C SDA GPIO pin (default 2)
  - `scl_pin`: I2C SCL GPIO pin (default 3)

## Adding an Optional Mod (example: display)

1) Create `models/<model>/<version>/display.yaml` to opt-in:
```
# ~/.pioreactor/hardware/models/pioreactor_xml/2.0/display.yaml
enabled: true
interface: i2c
driver: ssd1306
width: 128
height: 64
rotation: 0
```
2) Provide HAT 2.0 wiring in `hats/2.0/display.yaml`:
```
# ~/.pioreactor/hardware/hats/2.0/display.yaml
address: 0x3C
reset_pin: 22
```
The system will only load `display` when the model file exists. If the model file is absent, hat files are ignored for that mod.

## Notes

- Edit YAMLs directly to customize behavior; changes take effect on next import/use.
- Missing required keys raise clear errors naming the path and key.
- Back-compat constants exposed by the loader: `ADCs`, `PWM_TO_PIN`, `HEATER_PWM_TO_PIN`, `GPIOCHIP`, `TEMP_ADDRESS`, `DAC_ADDRESS`.
