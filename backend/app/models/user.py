from sqlalchemy import Column, String, Boolean, DateTime, Enum, JSON, Integer
from sqlalchemy.orm import relationship
import enum
from typing import Optional
from datetime import datetime

from app.models.base import BaseModel  # Importar BaseModel

class UserRole(str, enum.Enum):
    """Enum para roles de usuário."""
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"
    VIEWER = "viewer"

class User(BaseModel):  # Herdar de BaseModel, não Base
    """
    Modelo de usuário do sistema.
    """
    __tablename__ = "users"
    
    # Informações básicas
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    
    # Status e permissões
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)
    
    # Informações da empresa
    company_name = Column(String(255), nullable=True)
    company_sector = Column(String(100), nullable=True)
    company_size = Column(String(50), nullable=True)
    
    # Configurações e preferências
    preferences = Column(JSON, default=dict, nullable=False)
    notification_settings = Column(JSON, default=dict, nullable=False)
    
    # Dados de autenticação
    last_login = Column(DateTime(timezone=True), nullable=True)
    password_changed_at = Column(DateTime(timezone=True), nullable=True)
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    
    # Tokens
    email_verification_token = Column(String(255), nullable=True)
    password_reset_token = Column(String(255), nullable=True)
    password_reset_expires = Column(DateTime(timezone=True), nullable=True)
    
    # API Keys
    api_key = Column(String(255), unique=True, nullable=True)
    api_key_created_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relacionamentos
    vendas = relationship("Venda", back_populates="user", cascade="all, delete-orphan")
    predicoes = relationship("Predicao", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"
    
    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN
    
    @property
    def is_manager(self) -> bool:
        return self.role in [UserRole.ADMIN, UserRole.MANAGER]
    
    @property
    def can_write(self) -> bool:
        return self.role in [UserRole.ADMIN, UserRole.MANAGER, UserRole.USER]
    
    def check_password_needs_update(self) -> bool:
        """Verifica se a senha precisa ser atualizada (mais de 90 dias)."""
        if not self.password_changed_at:
            return True
        
        days_since_change = (datetime.utcnow() - self.password_changed_at).days
        return days_since_change > 90