from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class EstacaoMeteorologica(Base):
    __tablename__ = "estacoes"
    id = Column(Integer, primary_key=True)
    codigo_inmet = Column(String, unique=True, index=True)
    nome = Column(String)
    estado = Column(String)
    cidade = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    ativa = Column(Integer, default=1)

class DadoClimatico(Base):
    __tablename__ = "dados_climaticos"
    id = Column(Integer, primary_key=True)
    estacao_id = Column(Integer, ForeignKey("estacoes.id"))
    data = Column(DateTime)
    temperatura = Column(Float)
    precipitacao = Column(Float)
    umidade = Column(Float)
