# update.sql


CREATE INDEX IF NOT EXISTS stirring_rates_ix
ON stirring_rates (experiment, pioreactor_unit);

CREATE INDEX IF NOT EXISTS pwm_dcs_ix
ON pwm_dcs (experiment, pioreactor_unit);
