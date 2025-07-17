#!/usr/bin/env python3
"""Script para criar usuário admin."""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User, UserRole

def create_admin():
    db = SessionLocal()
    try:
        # Verifica se já existe admin
        admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
        if admin:
            print("Admin já existe!")
            return
        
        # Cria admin
        admin = User(
            email="admin@climanegocios.com",
            username="admin",
            full_name="Administrador",
            hashed_password=get_password_hash("admin123!@#"),
            is_active=True,
            is_verified=True,
            role=UserRole.ADMIN
        )
        
        db.add(admin)
        db.commit()
        
        print("Admin criado com sucesso!")
        print("Email: admin@climanegocios.com")
        print("Senha: admin123!@#")
        print("⚠️  ALTERE A SENHA NO PRIMEIRO LOGIN!")
        
    finally:
        db.close()

if __name__ == "__main__":
    create_admin()