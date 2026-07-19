# docker/postgres

Reserved for future PostgreSQL customization, e.g.:

- custom `init.sql` scripts mounted into `/docker-entrypoint-initdb.d`
- `postgresql.conf` / `pg_hba.conf` overrides

Not used yet — the `postgres` service currently runs the stock
`postgres` image configured entirely through environment variables.
