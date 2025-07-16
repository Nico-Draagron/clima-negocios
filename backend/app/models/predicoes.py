from sqlalchemy import Column, Integer, String, DateTime, Float, Enum, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
import enum

Base = declarative_base()

class TipoPredicao(enum.Enum):
    VENDAS = "vendas"
    CLIMA = "clima"

class StatusPredicao(enum.Enum):
    PENDENTE = "pendente"
    CONCLUIDA = "concluida"
    FALHA = "falha"

class Predicao(Base):
    __tablename__ = "predicoes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    tipo = Column(Enum(TipoPredicao))
    status = Column(Enum(StatusPredicao))
    modelo = Column(String)
    resultado = Column(String)
    data_predicao = Column(DateTime)
