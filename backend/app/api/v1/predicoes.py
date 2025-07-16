# Endpoints de predições de ML
from fastapi import APIRouter, Depends, HTTPException, Query, Body, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from datetime import datetime, timedelta

from app.core.database import get_db
from app.core.security import oauth2_scheme, decode_token
from app.models.predicoes import Predicao, TipoPredicao, StatusPredicao, ModeloML
from app.schemas.predicoes import (
    PredicaoCreate,
    PredicaoResponse,
    PredicaoDetalhada,
    ModeloMLResponse,
    FeatureImportance
)
from app.services.ml_service import ml_service
from app.services.cache_service import cache_service, cache_result, CacheKeys

router = APIRouter()

@router.post("/", response_model=PredicaoResponse, status_code=status.HTTP_201_CREATED)
async def criar_predicao(
    predicao_data: PredicaoCreate,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Cria uma nova predição.
    """
    payload = decode_token(token)
    user_id = int(payload.get("sub"))
    
    # Valida parâmetros
    if predicao_data.data_fim <= predicao_data.data_inicio:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Data fim deve ser posterior à data início"
        )
    
    # Cria predição
    predicao = await ml_service.criar_predicao(
        user_id=user_id,
        tipo=predicao_data.tipo,
        parametros={
            "data_inicio": predicao_data.data_inicio,
            "data_fim": predicao_data.data_fim,
            "horizonte_dias": predicao_data.horizonte_dias,
            **predicao_data.parametros
        }
    )
    
    return predicao

@router.get("/", response_model=List[PredicaoResponse])
async def listar_predicoes(
    tipo: Optional[TipoPredicao] = Query(None),
    status: Optional[StatusPredicao] = Query(None),
    data_inicio: Optional[datetime] = Query(None),
    data_fim: Optional[datetime] = Query(None),
    limite: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Lista predições do usuário.
    """
    payload = decode_token(token)
    user_id = int(payload.get("sub"))
    
    query = db.query(Predicao).filter(Predicao.user_id == user_id)
    
    if tipo:
        query = query.filter(Predicao.tipo == tipo)
    
    if status:
        query = query.filter(Predicao.status == status)
    
    if data_inicio:
        query = query.filter(Predicao.created_at >= data_inicio)
    
    if data_fim:
        query = query.filter(Predicao.created_at <= data_fim)
    
    predicoes = query.order_by(Predicao.created_at.desc()).offset(offset).limit(limite).all()
    
    return predicoes

@router.get("/{predicao_id}", response_model=PredicaoDetalhada)
@cache_result(CacheKeys.PREDICAO_RESULTADO, ttl=3600, key_params=['predicao_id'])
async def obter_predicao(
    predicao_id: int,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Obtém detalhes de uma predição específica.
    """
    payload = decode_token(token)
    user_id = int(payload.get("sub"))
    
    predicao = db.query(Predicao).filter(
        Predicao.id == predicao_id,
        Predicao.user_id == user_id
    ).first()
    
    if not predicao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Predição não encontrada"
        )
    
    return predicao

@router.delete("/{predicao_id}")
async def deletar_predicao(
    predicao_id: int,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Deleta uma predição.
    """
    payload = decode_token(token)
    user_id = int(payload.get("sub"))
    
    predicao = db.query(Predicao).filter(
        Predicao.id == predicao_id,
        Predicao.user_id == user_id
    ).first()
    
    if not predicao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Predição não encontrada"
        )
    
    # Só pode deletar se não estiver processando
    if predicao.status == StatusPredicao.PROCESSANDO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível deletar predição em processamento"
        )
    
    db.delete(predicao)
    db.commit()
    
    # Limpa cache
    cache_service.delete(f"{CacheKeys.PREDICAO_RESULTADO}:{predicao_id}")
    
    return {"message": "Predição deletada com sucesso"}

@router.get("/{predicao_id}/export")
async def exportar_predicao(
    predicao_id: int,
    formato: str = Query("csv", regex="^(csv|json|excel)$"),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Exporta resultados de uma predição.
    """
    payload = decode_token(token)
    user_id = int(payload.get("sub"))
    
    predicao = db.query(Predicao).filter(
        Predicao.id == predicao_id,
        Predicao.user_id == user_id
    ).first()
    
    if not predicao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Predição não encontrada"
        )
    
    if predicao.status != StatusPredicao.CONCLUIDA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Predição ainda não foi concluída"
        )
    
    # Implementar exportação baseada no formato
    # Por enquanto, retorna dados em JSON
    return {
        "formato": formato,
        "dados": predicao.resultado
    }

@router.get("/modelos/disponiveis", response_model=List[ModeloMLResponse])
async def listar_modelos_disponiveis(
    tipo_predicao: Optional[TipoPredicao] = Query(None),
    ativo: bool = Query(True),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Lista modelos de ML disponíveis.
    """
    query = db.query(ModeloML).filter(ModeloML.ativo == ativo)
    
    if tipo_predicao:
        # Filtra modelos compatíveis com o tipo de predição
        # Implementar lógica de mapeamento
        pass
    
    modelos = query.all()
    
    return modelos

@router.get("/modelos/{modelo_id}/features", response_model=FeatureImportance)
async def obter_feature_importance(
    modelo_id: int,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Obtém importância das features de um modelo.
    """
    modelo = db.query(ModeloML).filter(
        ModeloML.id == modelo_id,
        ModeloML.ativo == True
    ).first()
    
    if not modelo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Modelo não encontrado"
        )
    
    feature_importance = await ml_service.obter_feature_importance(modelo.nome)
    
    return {
        "modelo_id": modelo_id,
        "modelo_nome": modelo.nome,
        "features": feature_importance
    }

@router.post("/modelos/retreinar")
async def retreinar_modelos(
    force: bool = Body(False, description="Forçar retreino mesmo se recente"),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    Solicita retreino dos modelos do usuário.
    """
    payload = decode_token(token)
    user_id = int(payload.get("sub"))
    
    # Verifica se já existe solicitação recente
    if not force:
        ultima_solicitacao = cache_service.get(f"retreino:{user_id}")
        if ultima_solicitacao:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Retreino já solicitado recentemente. Use force=true para forçar."
            )
    
    # Marca solicitação
    cache_service.set(f"retreino:{user_id}", True, ttl=3600)  # 1 hora
    
    # Agenda retreino assíncrono
    await ml_service.retreinar_modelos(user_id)
    
    return {"message": "Retreino agendado com sucesso"}

@router.get("/insights/sugestoes")
async def obter_sugestoes_ml(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    Obtém sugestões de uso de ML baseadas nos dados do usuário.
    """
    payload = decode_token(token)
    user_id = int(payload.get("sub"))
    
    sugestoes = []
    
    # Verifica quantidade de dados de vendas
    total_vendas = db.query(Venda).filter(Venda.user_id == user_id).count()
    
    if total_vendas > 1000:
        sugestoes.append({
            "tipo": "predicao_vendas",
            "titulo": "Predição de Vendas Disponível",
            "descricao": "Você tem dados suficientes para criar predições precisas de vendas",
            "confianca": "alta",
            "acao": "Criar predição de vendas"
        })
    
    # Verifica sazonalidade
    vendas_por_mes = db.query(
        Venda.mes,
        func.avg(Venda.valor_total).label("media")
    ).filter(
        Venda.user_id == user_id
    ).group_by(Venda.mes).all()
    
    if len(vendas_por_mes) == 12:
        # Calcula variação entre meses
        valores = [v.media for v in vendas_por_mes]
        cv = np.std(valores) / np.mean(valores) if np.mean(valores) > 0 else 0
        
        if cv > 0.2:  # Alta variação
            sugestoes.append({
                "tipo": "analise_sazonalidade",
                "titulo": "Padrão Sazonal Detectado",
                "descricao": "Suas vendas apresentam variações sazonais significativas",
                "confianca": "media",
                "acao": "Analisar sazonalidade"
            })
    
    # Verifica correlação com clima
    vendas_com_clima = db.query(Venda).filter(
        Venda.user_id == user_id,
        Venda.temperatura.isnot(None)
    ).count()
    
    if vendas_com_clima > 500:
        sugestoes.append({
            "tipo": "correlacao_clima",
            "titulo": "Análise Climática Disponível",
            "descricao": "Podemos analisar como o clima afeta suas vendas",
            "confianca": "alta",
            "acao": "Ver correlação clima-vendas"
        })
    
    return {"sugestoes": sugestoes}