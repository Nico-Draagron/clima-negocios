#!/usr/bin/env python3
"""Script para popular banco com dados de teste."""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
import random
from faker import Faker
from app.core.database import SessionLocal
from app.models.user import User, UserRole
from app.models.vendas import Venda, CategoriaVenda, CanalVenda
from app.models.clima import EstacaoMeteorologica

fake = Faker('pt_BR')

def seed_users(db, count=10):
    """Cria usuários de teste."""
    users = []
    for i in range(count):
        user = User(
            email=f"user{i}@example.com",
            username=f"user{i}",
            full_name=fake.name(),
            hashed_password="$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW",  # secret
            is_active=True,
            is_verified=True,
            role=random.choice([UserRole.USER, UserRole.VIEWER]),
            company_name=fake.company(),
            company_sector=random.choice(['Varejo', 'Serviços', 'Indústria', 'Agronegócio'])
        )
        db.add(user)
        users.append(user)
    
    db.commit()
    return users

def seed_estacoes(db):
    """Cria estações meteorológicas."""
    estacoes_data = [
        {"codigo": "A801", "nome": "PORTO ALEGRE", "lat": -30.05, "lon": -51.17, "cidade": "Porto Alegre", "estado": "RS"},
        {"codigo": "A802", "nome": "SANTA MARIA", "lat": -29.72, "lon": -53.72, "cidade": "Santa Maria", "estado": "RS"},
        {"codigo": "A803", "nome": "CAXIAS DO SUL", "lat": -29.16, "lon": -51.20, "cidade": "Caxias do Sul", "estado": "RS"},
    ]
    
    estacoes = []
    for data in estacoes_data:
        estacao = EstacaoMeteorologica(
            codigo_inmet=data["codigo"],
            nome=data["nome"],
            tipo="Automática",
            latitude=data["lat"],
            longitude=data["lon"],
            cidade=data["cidade"],
            estado=data["estado"],
            ativa=True
        )
        db.add(estacao)
        estacoes.append(estacao)
    
    db.commit()
    return estacoes

def seed_vendas(db, users, days=90):
    """Cria vendas de teste."""
    categorias = list(CategoriaVenda)
    canais = list(CanalVenda)
    
    for user in users[:5]:  # Apenas primeiros 5 usuários
        for d in range(days):
            date = datetime.now() - timedelta(days=d)
            
            # 1-5 vendas por dia
            for _ in range(random.randint(1, 5)):
                valor = random.uniform(100, 5000)
                itens = random.randint(1, 20)
                
                venda = Venda(
                    user_id=user.id,
                    data_venda=date,
                    ano=date.year,
                    mes=date.month,
                    dia=date.day,
                    dia_semana=date.weekday(),
                    hora=random.randint(8, 20),
                    valor_total=valor,
                    quantidade_itens=itens,
                    ticket_medio=valor/itens,
                    categoria=random.choice(categorias),
                    canal=random.choice(canais),
                    cidade="Porto Alegre",
                    estado="RS",
                    temperatura=random.uniform(15, 35),
                    umidade=random.uniform(40, 90),
                    precipitacao=random.uniform(0, 50) if random.random() > 0.7 else 0
                )
                db.add(venda)
    
    db.commit()

def main():
    """Executa seed do banco."""
    db = SessionLocal()
    try:
        print("🌱 Iniciando seed do banco de dados...")
        
        print("👥 Criando usuários...")
        users = seed_users(db)
        
        print("🌡️ Criando estações meteorológicas...")
        estacoes = seed_estacoes(db)
        
        print("💰 Criando vendas...")
        seed_vendas(db, users)
        
        print("✅ Seed concluído com sucesso!")
        
    except Exception as e:
        print(f"❌ Erro durante seed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()