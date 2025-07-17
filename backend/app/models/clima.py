from sqlalchemy import Column, String, Float, DateTime, Integer, JSON, Boolean, Text
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from sqlalchemy.sql import func
import enum

from app.models.base import BaseModel

class EstacaoMeteorologica(BaseModel):
    """
    Modelo para estações meteorológicas.
    """
    __tablename__ = "estacoes_meteorologicas"
    
    # Identificação
    codigo_inmet = Column(String(10), unique=True, nullable=False)
    nome = Column(String(255), nullable=False)
    tipo = Column(String(50), nullable=False)  # Automática, Convencional
    
    # Localização
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    altitude = Column(Float, nullable=True)
    localizacao = Column(Geometry('POINT', srid=4326), nullable=True)
    
    # Endereço
    cidade = Column(String(100), nullable=False)
    estado = Column(String(2), nullable=False)
    regiao = Column(String(50), nullable=True)
    
    # Status
    ativa = Column(Boolean, default=True)  # Corrigido de Integer para Boolean
    data_instalacao = Column(DateTime(timezone=True), nullable=True)
    ultima_leitura = Column(DateTime(timezone=True), nullable=True)
    
    # Relacionamentos
    dados_climaticos = relationship("DadoClimatico", back_populates="estacao", cascade="all, delete-orphan")

class DadoClimatico(BaseModel):
    """
    Modelo para dados climáticos coletados.
    """
    __tablename__ = "dados_climaticos"
    
    # Relacionamento
    estacao_id = Column(Integer, ForeignKey("estacoes_meteorologicas.id"), nullable=False)
    estacao = relationship("EstacaoMeteorologica", back_populates="dados_climaticos")
    
    # Timestamp
    data_hora = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Temperatura
    temperatura = Column(Float, nullable=True)  # °C
    temperatura_min = Column(Float, nullable=True)
    temperatura_max = Column(Float, nullable=True)
    sensacao_termica = Column(Float, nullable=True)
    
    # Umidade
    umidade = Column(Float, nullable=True)  # %
    ponto_orvalho = Column(Float, nullable=True)
    
    # Pressão
    pressao = Column(Float, nullable=True)  # hPa
    pressao_nivel_mar = Column(Float, nullable=True)
    
    # Vento
    vento_velocidade = Column(Float, nullable=True)  # m/s
    vento_direcao = Column(Float, nullable=True)  # graus
    vento_rajada = Column(Float, nullable=True)
    
    # Precipitação
    precipitacao_1h = Column(Float, nullable=True)  # mm
    precipitacao_24h = Column(Float, nullable=True)
    precipitacao_acumulada = Column(Float, nullable=True)
    
    # Radiação e visibilidade
    radiacao_solar = Column(Float, nullable=True)  # W/m²
    indice_uv = Column(Float, nullable=True)
    visibilidade = Column(Float, nullable=True)  # km
    
    # Condições
    nebulosidade = Column(Float, nullable=True)  # %
    condicao_tempo = Column(String(100), nullable=True)
    codigo_condicao = Column(String(10), nullable=True)
    
    # Qualidade dos dados
    qualidade = Column(JSON, nullable=True)  # flags de qualidade
    fonte = Column(String(50), default="INMET")

class PrevisaoTempo(BaseModel):
    """
    Modelo para previsões do tempo.
    """
    __tablename__ = "previsoes_tempo"
    
    # Localização
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    cidade = Column(String(100), nullable=True)
    estado = Column(String(2), nullable=True)
    
    # Período da previsão
    data_previsao = Column(DateTime(timezone=True), nullable=False, index=True)
    horizonte_horas = Column(Integer, nullable=False)  # 1, 3, 6, 12, 24, 48, 72...
    
    # Dados previstos
    temperatura = Column(Float, nullable=True)
    temperatura_min = Column(Float, nullable=True)
    temperatura_max = Column(Float, nullable=True)
    umidade = Column(Float, nullable=True)
    
    # Probabilidades
    probabilidade_chuva = Column(Float, nullable=True)  # %
    precipitacao_esperada = Column(Float, nullable=True)  # mm
    
    # Vento
    vento_velocidade = Column(Float, nullable=True)
    vento_direcao = Column(Float, nullable=True)
    
    # Condições
    condicao_tempo = Column(String(100), nullable=True)
    nebulosidade = Column(Float, nullable=True)
    
    # Metadados
    modelo_previsao = Column(String(50), nullable=True)  # GFS, ECMWF, etc
    confiabilidade = Column(Float, nullable=True)  # score de confiança
    criado_em = Column(DateTime(timezone=True), server_default=func.now())  # Adicionado

class EventoClimatico(BaseModel):
    """
    Modelo para eventos climáticos significativos.
    """
    __tablename__ = "eventos_climaticos"
    
    # Tipo e severidade
    tipo = Column(String(50), nullable=False)  # tempestade, seca, onda_calor, etc
    severidade = Column(String(20), nullable=False)  # baixa, media, alta, extrema
    
    # Período
    data_inicio = Column(DateTime(timezone=True), nullable=False)
    data_fim = Column(DateTime(timezone=True), nullable=True)
    ativo = Column(Boolean, default=True)
    
    # Localização (pode ser área ou ponto)
    geometria = Column(Geometry('GEOMETRY', srid=4326), nullable=True)
    cidades_afetadas = Column(JSON, nullable=True)  # lista de cidades
    estados_afetados = Column(JSON, nullable=True)  # lista de estados
    
    # Descrição
    descricao = Column(Text, nullable=True)
    impactos = Column(JSON, nullable=True)
    recomendacoes = Column(JSON, nullable=True)
    
    # Métricas
    metricas = Column(JSON, nullable=True)  # dados específicos do evento
    
    # Fonte
    fonte = Column(String(100), nullable=True)
    url_referencia = Column(String(500), nullable=True)