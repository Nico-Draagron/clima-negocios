from sqlalchemy import Column, String, Float, DateTime, Integer, JSON, ForeignKey, Enum, Boolean
from sqlalchemy.orm import relationship
from decimal import Decimal
import enum

from app.models.base import BaseModel

class CategoriaVenda(str, enum.Enum):
    """Categorias de produtos/serviços."""
    BEBIDAS = "bebidas"
    ALIMENTOS = "alimentos"
    VESTUARIO = "vestuario"
    SERVICOS = "servicos"
    ENERGIA = "energia"
    TURISMO = "turismo"
    AGRICULTURA = "agricultura"
    CONSTRUCAO = "construcao"
    OUTROS = "outros"

class CanalVenda(str, enum.Enum):
    """Canais de venda."""
    LOJA_FISICA = "loja_fisica"
    ECOMMERCE = "ecommerce"
    DELIVERY = "delivery"
    ATACADO = "atacado"
    B2B = "b2b"

class Venda(BaseModel):
    """
    Modelo para registro de vendas.
    """
    __tablename__ = "vendas"
    
    # Relacionamento com usuário/empresa
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="vendas")
    
    # Dados temporais
    data_venda = Column(DateTime(timezone=True), nullable=False, index=True)
    ano = Column(Integer, nullable=False)
    mes = Column(Integer, nullable=False)
    dia = Column(Integer, nullable=False)
    dia_semana = Column(Integer, nullable=False)  # 0 = segunda, 6 = domingo
    hora = Column(Integer, nullable=True)
    
    # Valores
    valor_total = Column(Float, nullable=False)
    quantidade_itens = Column(Integer, nullable=False)
    ticket_medio = Column(Float, nullable=True)
    desconto_total = Column(Float, default=0.0)
    
    # Categorização
    categoria = Column(Enum(CategoriaVenda), nullable=False)
    subcategoria = Column(String(100), nullable=True)
    canal = Column(Enum(CanalVenda), nullable=False)
    
    # Localização
    loja_id = Column(String(50), nullable=True)
    cidade = Column(String(100), nullable=True)
    estado = Column(String(2), nullable=True)
    regiao = Column(String(50), nullable=True)
    
    # Dados climáticos no momento da venda
    temperatura = Column(Float, nullable=True)
    umidade = Column(Float, nullable=True)
    precipitacao = Column(Float, nullable=True)
    condicao_tempo = Column(String(50), nullable=True)
    
    # Métricas derivadas
    variacao_dia_anterior = Column(Float, nullable=True)  # %
    variacao_semana_anterior = Column(Float, nullable=True)  # %
    variacao_ano_anterior = Column(Float, nullable=True)  # %
    
    # Flags
    feriado = Column(Boolean, default=False)
    fim_semana = Column(Boolean, default=False)
    evento_especial = Column(String(100), nullable=True)
    
    # Metadados
    fonte_dados = Column(String(50), nullable=True)
    processado = Column(Boolean, default=False)
    anomalia = Column(Boolean, default=False)
    
    # Relacionamentos
    produtos = relationship("ProdutoVenda", back_populates="venda", cascade="all, delete-orphan")

class MetaVenda(BaseModel):
    """
    Modelo para metas de vendas.
    """
    __tablename__ = "metas_vendas"
    
    # Relacionamento
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Período
    ano = Column(Integer, nullable=False)
    mes = Column(Integer, nullable=True)  # null = meta anual
    
    # Valores
    valor_meta = Column(Float, nullable=False)
    categoria = Column(Enum(CategoriaVenda), nullable=True)  # null = todas
    
    # Realizado
    valor_realizado = Column(Float, default=0.0)
    percentual_atingido = Column(Float, default=0.0)
    
    # Status
    ativa = Column(Boolean, default=True)

class ProdutoVenda(BaseModel):
    """
    Modelo para produtos vendidos (análise detalhada).
    """
    __tablename__ = "produtos_vendas"
    
    # Relacionamento com venda
    venda_id = Column(Integer, ForeignKey("vendas.id"), nullable=False)
    venda = relationship("Venda", back_populates="produtos")
    
    # Dados do produto
    codigo_produto = Column(String(50), nullable=False)
    nome_produto = Column(String(255), nullable=False)
    categoria_produto = Column(String(100), nullable=True)
    
    # Valores
    quantidade = Column(Integer, nullable=False)
    preco_unitario = Column(Float, nullable=False)
    valor_total = Column(Float, nullable=False)
    desconto = Column(Float, default=0.0)
    
    # Características
    sazonal = Column(Boolean, default=False)
    sensivel_clima = Column(Boolean, default=False)
    elasticidade_temperatura = Column(Float, nullable=True)