# Endpoints de clima
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta

from app.core.database import get_db
from app.core.security import oauth2_scheme, decode_token
from app.services.clima_service import clima_service
from app.schemas.clima import (
    EstacaoResponse,
    DadoClimaticoResponse,
    PrevisaoTempoResponse,
    EventoClimaticoResponse,
    CorrelacaoClimaVendasResponse
)
from app.models.clima import EstacaoMeteorologica, DadoClimatico

router = APIRouter()

@router.get("/estacoes", response_model=List[EstacaoResponse])
async def listar_estacoes(
    estado: Optional[str] = Query(None, description="Filtrar por estado (UF)"),
    cidade: Optional[str] = Query(None, description="Filtrar por cidade"),
    ativa: Optional[bool] = Query(None, description="Filtrar por status"),
    limite: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Lista estações meteorológicas disponíveis.
    """
    query = db.query(EstacaoMeteorologica)
    
    if estado:
        query = query.filter(EstacaoMeteorologica.estado == estado.upper())
    
    if cidade:
        query = query.filter(EstacaoMeteorologica.cidade.ilike(f"%{cidade}%"))
    
    if ativa is not None:
        query = query.filter(EstacaoMeteorologica.ativa == ativa)
    
    total = query.count()
    estacoes = query.offset(offset).limit(limite).all()
    
    return estacoes

@router.get("/estacoes/{codigo_inmet}", response_model=EstacaoResponse)
async def obter_estacao(
    codigo_inmet: str,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Obtém detalhes de uma estação específica.
    """
    estacao = db.query(EstacaoMeteorologica).filter(
        EstacaoMeteorologica.codigo_inmet == codigo_inmet
    ).first()
    
    if not estacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Estação não encontrada"
        )
    
    return estacao

@router.get("/atual/{codigo_inmet}", response_model=DadoClimaticoResponse)
async def obter_clima_atual(
    codigo_inmet: str,
    token: str = Depends(oauth2_scheme)
):
    """
    Obtém dados climáticos atuais de uma estação.
    """
    async with clima_service as service:
        dados = await service.obter_clima_atual(codigo_inmet)
    
    if not dados:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dados climáticos não disponíveis"
        )
    
    return dados

@router.get("/historico", response_model=List[DadoClimaticoResponse])
async def obter_historico_clima(
    codigo_inmet: Optional[str] = Query(None),
    data_inicio: datetime = Query(..., description="Data inicial"),
    data_fim: datetime = Query(..., description="Data final"),
    agregacao: str = Query("hora", regex="^(hora|dia|semana|mes)$"),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Obtém histórico de dados climáticos.
    """
    # Valida período
    if data_fim < data_inicio:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Data final deve ser posterior à data inicial"
        )
    
    if (data_fim - data_inicio).days > 365:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Período máximo de consulta é 1 ano"
        )
    
    # Query base
    query = db.query(DadoClimatico).filter(
        DadoClimatico.data_hora >= data_inicio,
        DadoClimatico.data_hora <= data_fim
    )
    
    if codigo_inmet:
        estacao = db.query(EstacaoMeteorologica).filter(
            EstacaoMeteorologica.codigo_inmet == codigo_inmet
        ).first()
        
        if not estacao:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Estação não encontrada"
            )
        
        query = query.filter(DadoClimatico.estacao_id == estacao.id)
    
    # Aplica agregação se necessário
    if agregacao != "hora":
        # Implementar agregação por dia/semana/mês
        pass
    
    dados = query.order_by(DadoClimatico.data_hora).limit(10000).all()
    
    return dados

@router.get("/previsao", response_model=List[PrevisaoTempoResponse])
async def obter_previsao_tempo(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    dias: int = Query(7, ge=1, le=15),
    token: str = Depends(oauth2_scheme)
):
    """
    Obtém previsão do tempo para coordenadas específicas.
    """
    async with clima_service as service:
        previsoes = await service.obter_previsao_tempo(latitude, longitude, dias)
    
    if not previsoes:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Serviço de previsão temporariamente indisponível"
        )
    
    return previsoes

@router.get("/correlacao-vendas", response_model=CorrelacaoClimaVendasResponse)
async def analisar_correlacao_vendas(
    periodo_dias: int = Query(30, ge=7, le=365),
    token: str = Depends(oauth2_scheme)
):
    """
    Analisa correlação entre clima e vendas do usuário.
    """
    # Decodifica token para obter user_id
    payload = decode_token(token)
    user_id = int(payload.get("sub"))
    
    async with clima_service as service:
        analise = await service.analisar_correlacao_clima_vendas(
            user_id,
            periodo_dias
        )
    
    if 'erro' in analise:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=analise['erro']
        )
    
    return analise

@router.get("/eventos-extremos", response_model=List[EventoClimaticoResponse])
async def listar_eventos_extremos(
    estado: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    ativo: bool = Query(True),
    dias_passados: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Lista eventos climáticos extremos recentes.
    """
    data_inicio = datetime.now() - timedelta(days=dias_passados)
    
    query = db.query(EventoClimatico).filter(
        EventoClimatico.data_inicio >= data_inicio
    )
    
    if ativo:
        query = query.filter(EventoClimatico.ativo == True)
    
    if estado:
        query = query.filter(
            EventoClimatico.estados_afetados.contains([estado.upper()])
        )
    
    if tipo:
        query = query.filter(EventoClimatico.tipo == tipo)
    
    eventos = query.order_by(EventoClimatico.data_inicio.desc()).all()
    
    return eventos

@router.post("/alertas/subscribe")
async def inscrever_alertas_clima(
    tipos_eventos: List[str] = Body(...),
    regioes: List[str] = Body(...),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    Inscreve usuário para receber alertas de eventos climáticos.
    """
    payload = decode_token(token)
    user_id = int(payload.get("sub"))
    
    # Atualiza preferências do usuário
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
        )
    
    # Atualiza configurações de notificação
    notification_settings = user.notification_settings or {}
    notification_settings['alertas_clima'] = {
        'ativo': True,
        'tipos_eventos': tipos_eventos,
        'regioes': regioes,
        'inscrito_em': datetime.now().isoformat()
    }
    
    user.notification_settings = notification_settings
    db.commit()
    
    return {"message": "Inscrição em alertas realizada com sucesso"}

@router.get("/estatisticas/resumo")
async def obter_estatisticas_clima(
    periodo: str = Query("mes", regex="^(dia|semana|mes|ano)$"),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    Obtém estatísticas resumidas do clima.
    """
    # Define período de análise
    if periodo == "dia":
        data_inicio = datetime.now() - timedelta(days=1)
    elif periodo == "semana":
        data_inicio = datetime.now() - timedelta(days=7)
    elif periodo == "mes":
        data_inicio = datetime.now() - timedelta(days=30)
    else:  # ano
        data_inicio = datetime.now() - timedelta(days=365)
    
    # Query para estatísticas
    stats_query = f"""
        SELECT 
            AVG(temperatura) as temp_media,
            MIN(temperatura) as temp_minima,
            MAX(temperatura) as temp_maxima,
            AVG(umidade) as umidade_media,
            SUM(precipitacao_24h) as precipitacao_total,
            COUNT(DISTINCT DATE(data_hora)) as dias_com_dados
        FROM dados_climaticos
        WHERE data_hora >= :data_inicio
    """
    
    result = db.execute(stats_query, {"data_inicio": data_inicio}).first()
    
    return {
        "periodo": periodo,
        "temperatura": {
            "media": round(result.temp_media or 0, 1),
            "minima": round(result.temp_minima or 0, 1),
            "maxima": round(result.temp_maxima or 0, 1)
        },
        "umidade_media": round(result.umidade_media or 0, 1),
        "precipitacao_total": round(result.precipitacao_total or 0, 1),
        "dias_analisados": result.dias_com_dados or 0
    }