CREATE TRIGGER IF NOT EXISTS update_pioreactor_unit_activity_data_from_od_readings AFTER INSERT ON od_readings
BEGIN
    INSERT INTO pioreactor_unit_activity_data(pioreactor_unit,experiment,timestamp,od_reading) VALUES (new.pioreactor_unit, new.experiment, new.timestamp, new.od_reading)
    ON CONFLICT(experiment, pioreactor_unit, timestamp) DO UPDATE SET od_reading=excluded.od_reading;
END;

CREATE TRIGGER IF NOT EXISTS update_pioreactor_unit_activity_data_from_od_readings_fused AFTER INSERT ON od_readings_fused
BEGIN
    INSERT INTO pioreactor_unit_activity_data(pioreactor_unit,experiment,timestamp,od_fused) VALUES (new.pioreactor_unit, new.experiment, new.timestamp, new.od_reading)
    ON CONFLICT(experiment, pioreactor_unit, timestamp) DO UPDATE SET od_fused=excluded.od_fused;
END;


CREATE TRIGGER IF NOT EXISTS update_pioreactor_unit_activity_data_from_od_readings_filtered AFTER INSERT ON od_readings_filtered
BEGIN
    INSERT INTO pioreactor_unit_activity_data(pioreactor_unit,experiment,timestamp,normalized_od_reading) VALUES (new.pioreactor_unit, new.experiment, new.timestamp, new.normalized_od_reading)
    ON CONFLICT(experiment, pioreactor_unit, timestamp) DO UPDATE SET normalized_od_reading=excluded.normalized_od_reading;
END;


CREATE TRIGGER IF NOT EXISTS update_pioreactor_unit_activity_data_from_growth_rates AFTER INSERT ON growth_rates
BEGIN
    INSERT INTO pioreactor_unit_activity_data(pioreactor_unit,experiment,timestamp,growth_rate) VALUES (new.pioreactor_unit, new.experiment, new.timestamp, new.rate)
    ON CONFLICT(experiment, pioreactor_unit, timestamp) DO UPDATE SET growth_rate=excluded.growth_rate;
END;


CREATE TRIGGER IF NOT EXISTS update_pioreactor_unit_activity_data_from_temperature_readings AFTER INSERT ON temperature_readings
BEGIN
    INSERT INTO pioreactor_unit_activity_data(pioreactor_unit,experiment,timestamp,temperature_c) VALUES (new.pioreactor_unit, new.experiment, new.timestamp, new.temperature_c)
    ON CONFLICT(experiment, pioreactor_unit, timestamp) DO UPDATE SET temperature_c=excluded.temperature_c;
END;


CREATE TRIGGER IF NOT EXISTS update_pioreactor_unit_activity_data_from_stirring_rates AFTER INSERT ON stirring_rates
BEGIN
    INSERT INTO pioreactor_unit_activity_data(pioreactor_unit,experiment,timestamp,measured_rpm) VALUES (new.pioreactor_unit, new.experiment, new.timestamp, new.measured_rpm)
    ON CONFLICT(experiment, pioreactor_unit, timestamp) DO UPDATE SET measured_rpm=excluded.measured_rpm;
END;


CREATE TRIGGER IF NOT EXISTS update_pioreactor_unit_activity_data_from_led_change_events AFTER INSERT ON led_change_events
BEGIN
    INSERT INTO pioreactor_unit_activity_data(pioreactor_unit, experiment, timestamp, led_A_intensity_update, led_B_intensity_update, led_C_intensity_update, led_D_intensity_update) VALUES (
        new.pioreactor_unit, new.experiment, new.timestamp,
        CASE WHEN new.channel = "A" THEN new.intensity END,
        CASE WHEN new.channel = "B" THEN new.intensity END,
        CASE WHEN new.channel = "C" THEN new.intensity END,
        CASE WHEN new.channel = "D" THEN new.intensity END
    )
    ON CONFLICT(experiment, pioreactor_unit, timestamp) DO UPDATE SET
        led_A_intensity_update=COALESCE(excluded.led_A_intensity_update, pioreactor_unit_activity_data.led_A_intensity_update),
        led_B_intensity_update=COALESCE(excluded.led_B_intensity_update, pioreactor_unit_activity_data.led_B_intensity_update),
        led_C_intensity_update=COALESCE(excluded.led_C_intensity_update, pioreactor_unit_activity_data.led_C_intensity_update),
        led_D_intensity_update=COALESCE(excluded.led_D_intensity_update, pioreactor_unit_activity_data.led_D_intensity_update)
    ;
END;


CREATE TRIGGER IF NOT EXISTS update_pioreactor_unit_activity_data_from_dosing_events AFTER INSERT ON dosing_events
BEGIN
    INSERT INTO pioreactor_unit_activity_data(pioreactor_unit, experiment, timestamp, add_media_ml, remove_waste_ml, add_alt_media_ml) VALUES (
        new.pioreactor_unit, new.experiment, new.timestamp,
        CASE WHEN new.event = "add_media" THEN new.volume_change_ml END,
        CASE WHEN new.event = "remove_waste" THEN new.volume_change_ml END,
        CASE WHEN new.event = "add_alt_media" THEN new.volume_change_ml END
    )
    ON CONFLICT(experiment, pioreactor_unit, timestamp) DO UPDATE SET
        add_media_ml=COALESCE(excluded.add_media_ml, pioreactor_unit_activity_data.add_media_ml),
        remove_waste_ml=COALESCE(excluded.remove_waste_ml, pioreactor_unit_activity_data.remove_waste_ml),
        add_alt_media_ml=COALESCE(excluded.add_alt_media_ml, pioreactor_unit_activity_data.add_alt_media_ml)
    ;
END;


CREATE TRIGGER IF NOT EXISTS insert_experiment_worker_assignments_history
AFTER INSERT
ON experiment_worker_assignments
FOR EACH ROW
BEGIN
    INSERT INTO experiment_worker_assignments_history (
        pioreactor_unit,
        experiment,
        assigned_at
    )
    VALUES (
        NEW.pioreactor_unit,
        NEW.experiment,
        NEW.assigned_at
    );
END;

CREATE TRIGGER IF NOT EXISTS delete_experiment_worker_assignments_history
AFTER DELETE
ON experiment_worker_assignments
FOR EACH ROW
BEGIN
    UPDATE experiment_worker_assignments_history
       SET unassigned_at = STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')
     WHERE pioreactor_unit = OLD.pioreactor_unit
       AND experiment = OLD.experiment
       AND assigned_at = OLD.assigned_at
       AND unassigned_at IS NULL;
END;
