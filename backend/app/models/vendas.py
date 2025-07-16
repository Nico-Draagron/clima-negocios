from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
import enum

Base = declarative_base()

class CategoriaVenda(enum.Enum):
    PRODUTO = "produto"
    SERVICO = "servico"

class CanalVenda(enum.Enum):
    ONLINE = "online"
    LOJA_FISICA = "loja_fisica"

class Venda(Base):
    __tablename__ = "vendas"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    categoria = Column(Enum(CategoriaVenda))
    canal = Column(Enum(CanalVenda))
    produto = Column(String)
    valor_total = Column(Float)
    ticket_medio = Column(Float)
    data_venda = Column(DateTime)
