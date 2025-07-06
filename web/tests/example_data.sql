INSERT INTO experiments (experiment, created_at, description, media_used, organism_used) VALUES
('exp0', '2023-09-01T12:00:00Z', 'Demo experiment', '', ''),
('exp1', '2023-10-01T12:00:00Z', 'First experiment', 'LB broth', 'E. coli'),
('exp2', '2023-10-02T15:00:00Z', 'Second experiment', 'Minimal media', 'Yeast'),
('exp3', '2023-10-03T09:00:00Z', 'Third experiment', 'Rich media', 'Bacteria');

INSERT INTO workers (pioreactor_unit, added_at, is_active, model_name, model_version) VALUES
('unit1', '2023-10-01T10:00:00Z', 1, "pioreactor_20ml", "1.1"),
('unit2', '2023-10-01T11:00:00Z', 1, "pioreactor_40ml", "1.0"),
('unit3', '2023-10-02T10:00:00Z', 1, "pioreactor_40ml", "1.0"),
('unit4', '2023-10-03T08:00:00Z', 0, "pioreactor_40ml", "1.0");

INSERT INTO experiment_worker_assignments (pioreactor_unit, experiment, assigned_at) VALUES
('unit1', 'exp1', '2023-10-01T12:00:00Z'),
('unit2', 'exp1', '2023-10-01T13:00:00Z'),
('unit3', 'exp2', '2023-10-02T15:30:00Z'),
('unit4', 'exp3', '2023-10-03T09:30:00Z');

INSERT INTO pioreactor_unit_labels (experiment, pioreactor_unit, label, created_at) VALUES
('exp1', 'unit1', 'Reactor 1', '2023-10-01T12:00:00Z'),
('exp1', 'unit2', 'Reactor 2', '2023-10-01T12:00:00Z'),
('exp2', 'unit3', 'Reactor 3', '2023-10-02T15:00:00Z'),
('exp3', 'unit4', 'Reactor 4', '2023-10-03T09:00:00Z');

INSERT INTO logs (experiment, pioreactor_unit, timestamp, message, source, level, task) VALUES
('exp1', 'unit1', '2023-10-01T12:10:00Z', 'Started mixing', 'mixer', 'INFO', 'stirring'),
('exp1', 'unit2', '2023-10-01T12:15:00Z', 'OD reading taken', 'sensor', 'INFO', 'od_reading'),
('exp2', 'unit3', '2023-10-02T15:45:00Z', 'Temperature set', 'heater', 'INFO', 'temperature_automation');


INSERT INTO od_readings (experiment, pioreactor_unit, timestamp, od_reading, angle, channel) VALUES
('exp1', 'unit1', '2023-10-01T12:15:00Z', 0.5, "90", "1"),
('exp1', 'unit1', '2023-10-01T12:15:05Z', 0.5, "90", "1"),
('exp1', 'unit1', '2023-10-01T12:15:10Z', 0.5, "90", "1"),
('exp1', 'unit2', '2023-10-01T12:15:00Z', 0.6, "90", "1"),
('exp1', 'unit2', '2023-10-01T12:15:05Z', 0.6, "90", "1"),
('exp1', 'unit2', '2023-10-01T12:15:10Z', 0.6, "90", "1");

INSERT INTO growth_rates (experiment, pioreactor_unit, timestamp, rate) VALUES
('exp1', 'unit1', '2023-10-01T13:00:00Z', 0.01),
('exp1', 'unit1', '2023-10-01T13:05:00Z', 0.02),
('exp1', 'unit2', '2023-10-01T13:00:00Z', 0.00),
('exp1', 'unit2', '2023-10-01T13:05:00Z', 0.00);
