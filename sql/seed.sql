PRAGMA journal_mode=WAL;


INSERT INTO experiments (timestamp, experiment, description) VALUES (STRFTIME('%Y-%m-%d   %H:%M', 'NOW','localtime'), 'Demo experiment', 'This is just a demo experiment. Feel free to click around. When you are ready, click the "Start new Experiment" above.');
