PRAGMA journal_mode = WAL;
PRAGMA synchronous = 1; -- aka NORMAL, recommended when using WAL
PRAGMA temp_store = 2;  -- stop writing small files to disk, use mem
PRAGMA busy_timeout = 15000;
PRAGMA foreign_keys = ON;
PRAGMA auto_vacuum = INCREMENTAL;
PRAGMA cache_size = -4000;
