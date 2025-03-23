PRAGMA busy_timeout = 15000;
PRAGMA synchronous = 1; -- aka NORMAL, recommended when using WAL
PRAGMA temp_store = 2;  -- stop writing small files to disk, use mem
PRAGMA foreign_keys = ON;
PRAGMA auto_vacuum = INCREMENTAL;

ALTER TABLE workers ADD COLUMN model_version TEXT;
ALTER TABLE workers ADD COLUMN model_name TEXT;
