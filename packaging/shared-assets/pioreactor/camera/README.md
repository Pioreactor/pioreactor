# Camera capture profiles

Install these assets under `$DOT_PIOREACTOR/camera/`.

`viewing.conf` contains the native `rpicam-still --config` image settings used by
default for snapshots, focus previews, and the persistent camera process.
The profile selects its tuning JSON, sensor mode, resolution, and image processing.

For a different purpose, pass `capture_profile=Path(...)` to
`get_rpicam_still_arguments()`. A custom profile can set `tuning-file` to an
relative or absolute path to its own tuning JSON; Pioreactor does not override
that setting. Run the command with `cwd` set to the profile's directory, as the
built-in capture paths do. Native config files do not expand environment variables.

The hook only builds command arguments. Existing capture entry points and the
persistent camera process continue to use the default viewing profile. Restart
Huey after editing the profile if the persistent camera process is enabled.
