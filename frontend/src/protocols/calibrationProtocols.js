export const CALIBRATION_PROTOCOLS = [
  {
    id: "pump_duration_media",
    device: "media_pump",
    protocolName: "duration_based",
    title: "Duration-based pump calibration",
    description:
      "Build a duration-to-volume curve for the media pump using a simple multi-step flow.",
    requirements: [
      "Place the outflow tube into a measuring container or scale.",
      "Have clean water available for priming and tests.",
    ],
  },
  {
    id: "pump_duration_alt_media",
    device: "alt_media_pump",
    protocolName: "duration_based",
    title: "Duration-based pump calibration",
    description:
      "Build a duration-to-volume curve for the alt media pump using a simple multi-step flow.",
    requirements: [
      "Place the outflow tube into a measuring container or scale.",
      "Have clean water available for priming and tests.",
    ],
  },
  {
    id: "pump_duration_waste",
    device: "waste_pump",
    protocolName: "duration_based",
    title: "Duration-based pump calibration",
    description:
      "Build a duration-to-volume curve for the waste pump using a simple multi-step flow.",
    requirements: [
      "Place the outflow tube into a measuring container or scale.",
      "Have clean water available for priming and tests.",
    ],
  },
  {
    id: "stirring_dc_based",
    device: "stirring",
    protocolName: "dc_based",
    title: "Stirring DC-based calibration",
    description: "Maps duty cycle to RPM for the current stirrer configuration.",
    requirements: [
      "Stirring must be off before starting.",
      "Insert a vial with a stir bar and the liquid volume you plan to use (water is fine).",
    ],
  },
  {
    id: "od_reference_standard",
    device: "od",
    protocolName: "od_reference_standard",
    title: "Optics Calibration Jig",
    description:
      "Uses the Optics Calibration Jig to calibrate OD channels to a standard value (AU).",
    requirements: [
      "OD reading must be off before starting.",
      "Insert the Optics Calibration Jig.",
      "Set ir_led_intensity in [od_reading.config] to a numeric value.",
    ],
  },
  {
    id: "od_standards",
    device: "od",
    protocolName: "standards",
    title: "OD standards calibration",
    description:
      "Calibrate OD channels using a series of OD600 standards and a blank.",
    requirements: [
      "OD reading and stirring must be off before starting.",
      "Have OD600 standards ready (including a blank).",
      "Each vial should include a stir bar.",
    ],
  },
];
