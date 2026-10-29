CREATE ROLE app_reader LOGIN PASSWORD :'reader_password';
CREATE TABLE inventory (
  hostname text PRIMARY KEY,
  purpose text NOT NULL,
  status text NOT NULL CHECK (status IN ('healthy', 'maintenance'))
);
GRANT CONNECT ON DATABASE ops TO app_reader;
GRANT USAGE ON SCHEMA public TO app_reader;
GRANT SELECT ON inventory TO app_reader;
