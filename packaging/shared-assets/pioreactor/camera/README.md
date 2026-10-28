# Camera capture profiles

Install these assets under `$DOT_PIOREACTOR/camera/`.

`viewing.conf` contains the native `rpicam-still --config` image settings used by
default for snapshots, focus previews, and the persistent camera process.
The profile selects sensor mode, resolution, and image processing. Python selects
the platform-specific tuning JSON for the default OV5647 camera.

For a different purpose, pass `capture_profile=Path(...)` to
`get_rpicam_still_arguments()`. A custom profile can set `tuning-file` to a
relative or absolute path to its own tuning JSON; Pioreactor does not override
that setting. Run the command with `cwd` set to the profile's directory, as the
built-in capture paths do. Native config files do not expand environment variables.

The hook only builds command arguments. Existing capture entry points and the
persistent camera process continue to use the default viewing profile. Restart
Huey after editing the profile if the persistent camera process is enabled.

## Platform-specific tuning

The runtime selects `ov5647_noir_200ms_pisp.json` on Raspberry Pi 5 and Compute
Module 5, and `ov5647_noir_200ms.json` on earlier Pis. Both files are installed
on disk; capture does not read or modify them to select the platform.

For the default profile, the command-line tuning selection overrides any old
`tuning-file` entry in `viewing.conf`, so existing profiles need no migration.
To use custom tuning, pass an explicit capture profile; its settings are used
as supplied and must match the camera platform.

The PiSP asset comes from `/usr/share/libcamera/ipa/rpi/pisp/ov5647_noir.json`
in Raspberry Pi OS `libcamera-ipa` version `0.7.2+rpt20260817-1`. Its only tuning
change is the normal exposure mode in AGC channel 0: the shutter and gain curves
match our VC4 asset, allowing exposure up to 200 ms. The remaining PiSP algorithms
and AGC channels are preserved. See the accompanying license files.

CustoPiZer copies this directory into fresh images. Keep the PiSP JSON and license
in `core/update_scripts/upcoming/` identical to these assets while preparing the
release; its migration installs them without changing existing profiles.
