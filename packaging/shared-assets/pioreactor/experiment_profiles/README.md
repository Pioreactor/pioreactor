# Example experiment profiles

These profiles are installed on leaders and can be opened from **Experiment
profiles** in the UI. Review the YAML and the experiment's assigned Pioreactors
before running a profile. A `common` block targets every active Pioreactor
assigned to that experiment. To target one unit, replace `common:` with:

```yaml
pioreactors:
  your-unit-name:
    jobs:
      # Move the job definitions here.
```

## Flush

`flush.yaml` replaces the former circulation actions with discrete, calibrated
doses. By default it adds 1 mL of media at the beginning of each minute and
runs waste for a calibrated displacement of 2 mL at 30 seconds. It repeats ten
times, adding 10 mL total, and sends stop commands to both pump jobs at ten
minutes. This dilutes or exchanges the existing liquid; it does not guarantee
complete replacement or sterilization.

Before running:

- Set active calibrations for the media and waste pumps and prime their tubing.
- Stop dosing automations and other pump actions or profiles using these pumps.
- Start at the intended efflux-tube liquid level and leave room for a full
  media dose below the vessel's maximum safe fill volume. Waste cannot create
  headroom below the efflux-tube level.
- Check that each media and waste dose finishes comfortably within its
  30-second window on every selected unit. Increase `every` and the waste
  action's `t` together if the pumps need longer.
- Verify that waste actually drains the added media and monitor liquid level.
  The profile schedules commands; it does not confirm successful drainage
  before allowing the next addition. Stop the profile if a pump fails.

Edit `media_ml` and `waste_ml` to change the doses. Keep waste displacement
larger than the media dose to allow for air in the efflux tubing. Pumped waste
volume is estimated from calibration and can include time drawing air; it is
not a measurement of collected liquid. Both pump actions emit the normal dosing
events, including media usage and waste estimates.

To change the number of cycles, change both `max_time` values and both final
stop times together. `max_time / every` should be a whole number of cycles.
To flush through the alternative-media pump, change the `add_media` job key
to `add_alt_media` and activate that pump's calibration instead.

Stopping the profile early requests cancellation of its started jobs through
the cluster. Each dose also has its own finite local runtime, so it does not
depend on a later stop command to finish. Stopping early can leave a media dose
without its following waste dose; check the level before resuming other work.

Existing profiles and scripts using `circulate_media` or `circulate_alt_media`
must be edited; they are not automatically converted. Copy this example and
adjust it for the vessel, pumps, and desired amount of exchange.
