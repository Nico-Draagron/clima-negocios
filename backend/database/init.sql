-- Criar extensões necessárias
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Criar esquemas
CREATE SCHEMA IF NOT EXISTS clima;
CREATE SCHEMA IF NOT EXISTS vendas;
CREATE SCHEMA IF NOT EXISTS ml;

-- Configurar search_path
ALTER DATABASE climanegocios_db SET search_path TO public, clima, vendas, ml;

-- Criar tipos ENUM se não existirem
DO $$ BEGIN
    CREATE TYPE user_role AS ENUM ('admin', 'manager', 'user', 'viewer');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_gin_users_email ON users USING gin (email gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_gin_vendas_cidade ON vendas USING gin (cidade gin_trgm_ops);

-- Função para atualizar updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';