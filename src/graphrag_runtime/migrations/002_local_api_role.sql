-- Development-only role used by compose.yaml. Production should provision the
-- equivalent role and password through its secret manager/IaC.
\getenv graphrag_api_database_password GRAPHRAG_API_DATABASE_PASSWORD
\if :{?graphrag_api_database_password}
SELECT format('CREATE ROLE graphrag_api_role LOGIN PASSWORD %L', :'graphrag_api_database_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'graphrag_api_role') \gexec
SELECT format('ALTER ROLE graphrag_api_role PASSWORD %L', :'graphrag_api_database_password') \gexec
\else
\quit
\endif

ALTER ROLE graphrag_api_role NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION
    CONNECTION LIMIT 20;
REVOKE ALL ON DATABASE graphrag FROM PUBLIC;
GRANT CONNECT ON DATABASE graphrag TO graphrag_api_role;
GRANT USAGE ON SCHEMA graphrag_api TO graphrag_api_role;
GRANT EXECUTE ON FUNCTION graphrag_api.runtime_health() TO graphrag_api_role;
GRANT EXECUTE ON FUNCTION graphrag_api.hybrid_search(text,vector,integer,text[],text,double precision,double precision) TO graphrag_api_role;
GRANT EXECUTE ON FUNCTION graphrag_api.graph_neighbors(text,text,integer,integer,text[]) TO graphrag_api_role;
GRANT EXECUTE ON FUNCTION graphrag_api.route_tools(text,integer) TO graphrag_api_role;

ALTER ROLE graphrag_api_role SET default_transaction_read_only = on;
ALTER ROLE graphrag_api_role SET statement_timeout = '5s';
ALTER ROLE graphrag_api_role SET idle_in_transaction_session_timeout = '10s';
ALTER ROLE graphrag_api_role SET search_path = pg_catalog, graphrag_api;
