#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=reader_password="$SUPPORT_READER_PASSWORD" <<'SQL'
CREATE TABLE support_requests (
    id SERIAL PRIMARY KEY,
    customer_name VARCHAR(100),
    email VARCHAR(255),
    category VARCHAR(100),
    priority VARCHAR(50),
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO support_requests (customer_name, email, category, priority, status) VALUES
    ('John Smith', 'john@example.com', 'Login Issue', 'High', 'Open'),
    ('Sarah Cohen', 'sarah@example.com', 'Billing', 'Medium', 'In Progress'),
    ('David Levi', 'david@example.com', 'Technical Support', 'Low', 'Closed'),
    ('Emma Johnson', 'emma@example.com', 'Account Access', 'High', 'Open'),
    ('Michael Brown', 'michael@example.com', 'Subscription', 'Medium', 'Open');
CREATE ROLE support_reader LOGIN PASSWORD :'reader_password';
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE support_demo TO support_reader;
GRANT USAGE ON SCHEMA public TO support_reader;
GRANT SELECT ON support_requests TO support_reader;
ALTER ROLE support_reader SET default_transaction_read_only = on;
SQL
