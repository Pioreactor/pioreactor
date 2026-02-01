// Simple object-based overrides for Start/Update example options.
// Usage: edit the object below to add your own overrides.
// Keys can be either:
//   - 'job_name' to match any automation for that job
//   - 'job_name::automation_name' to target a specific automation
// Values can be:
//   - A plain object of option_name -> value (applies to Start only)
//   - Or an object with { start: {...}, update: {...} }
// Examples:
// {
//   chemostat: { exchange_volume_ml: 1, duration: 20 },
//   // or
//   // chemostat: { start: { exchange_volume_ml: 1, duration: 20 }, update: { duration: 10 } },
//   'od_reading::continuous': { interval: '5m' },
// }
export default function useCapabilityExamplesOverride() {
  // Edit me: provide your preferred defaults here.
  const overrides = {
    'dosing_automation::chemostat': {start: { exchange_volume_ml: 1, duration: 20 }, update: { exchange_volume_ml: 1.5}},
    'dosing_automation::turbidostat': {start: { exchange_volume_ml: 1, biomass_signal: "normalized_od", target_biomass: 3.0}, update: { target_biomass: 5.0}},
    'temperature_automation::thermostat': {start: {target_temperature: 30}, update: {target_temperature: 35}},
    'stirring': {start: {target_rpm: 500}, update: {target_rpm: 350}},
    'led_automation::light_dark_cycle': {start: {light_intensity: 10, light_duration_minutes: 60 * 16, dark_duration_minutes: 60*8}},
    'od_reading': {start: {}, update: {ir_led_intensity: 80}},
    'add_media': {start: {ml: 1}},
    'add_alt_media': {start: {ml: 1}},
    'remove_waste': {start: {duration: 60}},
    'pumps': {start: {media: 1, waste: 2, media_: 1.5, waste_: 2}},
    'circulate_alt_media': {start: {duration: 30}},
    'circulate_media': {start: {duration: 30}},
    'led_intensity': {start: {A: 30, B: 40}},
  };
  return overrides;
}
