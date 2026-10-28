# Quarantine

Rejected records are preserved in the SQLite `rejected_records` table with the
raw line, source location, reason, run ID, and rejection timestamp. The database
is the authoritative quarantine store; this directory is reserved for optional
future exports and is intentionally empty in the sample repository.
