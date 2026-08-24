PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS experiment_chart_preferences (
    experiment TEXT NOT NULL PRIMARY KEY,
    overview_chart_keys TEXT,
    pioreactor_chart_keys TEXT,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);
