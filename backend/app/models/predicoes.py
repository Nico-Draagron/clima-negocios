from sqlalchemy import Column, String, Float, DateTime, Integer, JSON, ForeignKey, Enum, Text, Boolean
from sqlalchemy.orm import relationship
import enum
from datetime import datetime

from app.models.base import BaseModel

class TipoPredicao(str, enum.Enum):
    """Tipos de predição disponíveis."""
    VENDAS_DIARIA = "vendas_diaria"
    VENDAS_SEMANAL = "vendas_semanal"
    VENDAS_MENSAL = "vendas_mensal"
    DEMANDA_PRODUTO = "demanda_produto"
    FLUXO_CLIENTES = "fluxo_clientes"
    CONSUMO_ENERGIA = "consumo_energia"
    PRECO_DINAMICO = "preco_dinamico"

class StatusPredicao(str, enum.Enum):
    """Status da predição."""
    PENDENTE = "pendente"
    PROCESSANDO = "processando"
    CONCLUIDA = "concluida"
    ERRO = "erro"
    CANCELADA = "cancelada"

class Predicao(BaseModel):
    """
    Modelo para predições geradas pelo sistema.
    """
    __tablename__ = "predicoes"
    
    # Relacionamento
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="predicoes")
    
    # Tipo e status
    tipo = Column(Enum(TipoPredicao), nullable=False)
    status = Column(Enum(StatusPredicao), default=StatusPredicao.PENDENTE)
    
    # Período da predição
    data_inicio = Column(DateTime(timezone=True), nullable=False)
    data_fim = Column(DateTime(timezone=True), nullable=False)
    horizonte_dias = Column(Integer, nullable=False)
    
    # Parâmetros de entrada
    parametros = Column(JSON, nullable=False)
    filtros = Column(JSON, nullable=True)
    
    # Resultados
    resultado = Column(JSON, nullable=True)
    metricas = Column(JSON, nullable=True)
    confianca = Column(Float, nullable=True)  # 0-100%
    
    # Modelo utilizado
    modelo_nome = Column(String(100), nullable=True)
    modelo_versao = Column(String(50), nullable=True)
    modelo_parametros = Column(JSON, nullable=True)
    
    # Performance
    tempo_processamento = Column(Float, nullable=True)  # segundos
    recursos_utilizados = Column(JSON, nullable=True)
    
    # Validação
    validado = Column(Boolean, default=False)
    erro_medio = Column(Float, nullable=True)
    r2_score = Column(Float, nullable=True)
    
    # Logs e debugging
    log_processamento = Column(Text, nullable=True)
    erro_mensagem = Column(Text, nullable=True)
    
    # Timestamps específicos
    iniciado_em = Column(DateTime(timezone=True), nullable=True)
    concluido_em = Column(DateTime(timezone=True), nullable=True)
    
    # Relacionamentos
    historico = relationship("HistoricoPredicao", back_populates="predicao", cascade="all, delete-orphan")

class ModeloML(BaseModel):
    """
    Modelo para gerenciar modelos de ML treinados.
    """
    __tablename__ = "modelos_ml"
    
    # Identificação
    nome = Column(String(100), unique=True, nullable=False)
    versao = Column(String(50), nullable=False)
    tipo = Column(String(50), nullable=False)  # regressao, classificacao, series_temporais
    
    # Descrição
    descricao = Column(Text, nullable=True)
    algoritmo = Column(String(100), nullable=False)  # random_forest, lstm, xgboost, etc
    
    # Arquivos
    caminho_modelo = Column(String(500), nullable=False)
    caminho_scaler = Column(String(500), nullable=True)
    caminho_encoder = Column(String(500), nullable=True)
    
    # Features
    features_entrada = Column(JSON, nullable=False)
    features_importancia = Column(JSON, nullable=True)
    
    # Métricas de treinamento
    metricas_treino = Column(JSON, nullable=False)
    metricas_validacao = Column(JSON, nullable=True)
    dataset_info = Column(JSON, nullable=True)
    
    # Configurações
    hiperparametros = Column(JSON, nullable=False)
    preprocessamento = Column(JSON, nullable=True)
    
    # Status
    ativo = Column(Boolean, default=True)
    em_producao = Column(Boolean, default=False)
    
    # Histórico
    treinado_em = Column(DateTime(timezone=True), nullable=False)
    treinado_por = Column(String(100), nullable=True)
    
    # Performance em produção
    predicoes_realizadas = Column(Integer, default=0)
    tempo_medio_predicao = Column(Float, nullable=True)
    acuracia_producao = Column(Float, nullable=True)
    
    # Relacionamentos
    configuracoes = relationship("ConfiguracaoModelo", back_populates="modelo")

class HistoricoPredicao(BaseModel):
    """
    Modelo para histórico e comparação de predições vs realizado.
    """
    __tablename__ = "historico_predicoes"
    
    # Relacionamento
    predicao_id = Column(Integer, ForeignKey("predicoes.id"), nullable=False)
    predicao = relationship("Predicao", back_populates="historico")
    
    # Período
    data_referencia = Column(DateTime(timezone=True), nullable=False)
    
    # Valores
    valor_previsto = Column(Float, nullable=False)
    valor_realizado = Column(Float, nullable=True)
    erro_absoluto = Column(Float, nullable=True)
    erro_percentual = Column(Float, nullable=True)
    
    # Contexto
    contexto_clima = Column(JSON, nullable=True)
    contexto_mercado = Column(JSON, nullable=True)
    
    # Análise
    dentro_intervalo_confianca = Column(Boolean, nullable=True)
    anomalia_detectada = Column(Boolean, default=False)

class ConfiguracaoModelo(BaseModel):
    """
    Modelo para configurações personalizadas de modelos por usuário.
    """
    __tablename__ = "configuracoes_modelos"
    
    # Relacionamento
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    modelo_id = Column(Integer, ForeignKey("modelos_ml.id"), nullable=False)
    modelo = relationship("ModeloML", back_populates="configuracoes")
    
    # Configurações personalizadas
    parametros_customizados = Column(JSON, nullable=True)
    features_excluidas = Column(JSON, nullable=True)
    
    # Preferências
    auto_retreino = Column(Boolean, default=False)
    frequencia_retreino = Column(String(50), nullable=True)  # diario, semanal, mensal
    notificar_anomalias = Column(Boolean, default=True)
    threshold_confianca = Column(Float, default=0.8)
    
    # Status
    ativo = Column(Boolean, default=True)
    ultima_execucao = Column(DateTime(timezone=True), nullable=True)