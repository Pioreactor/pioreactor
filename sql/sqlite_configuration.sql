PRAGMA journal_mode=WAL;
PRAGMA synchronous = 1; -- recommended when using WAL
PRAGMA temp_store = 2;  -- stop writing small files to disk, use mem
