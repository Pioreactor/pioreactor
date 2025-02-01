# update.sql


CREATE INDEX IF NOT EXISTS stirring_rates_ix
ON stirring_rates (experiment, pioreactor_unit);
