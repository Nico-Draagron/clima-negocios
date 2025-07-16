# Endpoints de vendas
from fastapi import APIRouter, Depends, HTTPException, Query, Body, status
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import pandas as pd

from app.core.database import get_db
from app.core.security import oauth2_scheme, decode_token
from app.models.vendas import Venda, MetaVenda, CategoriaVenda, CanalVenda
from app.schemas.vendas import (
    VendaCreate,
    VendaResponse,
    VendaBulkCreate,
    MetaVendaCreate,
    MetaVendaResponse,
    VendasAgregadas,
    EstatisticasVendas
)
from app.services.cache_service import cache_service, CacheKeys

router = APIRouter()

@router.post("/", response_model=VendaResponse, status_code=status.HTTP_201_CREATED)
async def criar_venda(
    venda: VendaCreate,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Registra uma nova venda.
    """
    payload = decode_token(token)
    user_id = int(payload.get("sub"))
    
    # Calcula campos derivados
    ticket_medio = venda.valor_total / venda.quantidade_itens if venda.quantidade_itens > 0 else 0
    
    db_venda = Venda(
        user_id=user_id,
        data_venda=venda.data_venda,
        ano=venda.data_venda.year,
        mes=venda.data_venda.month,
        dia=venda.data_venda.day,
        dia_semana=venda.data_venda.weekday(),
        hora=venda.data_venda.hour,
        valor_total=venda.valor_total,
        quantidade_itens=venda.quantidade_itens,
        ticket_medio=ticket_medio,
        desconto_total=venda.desconto_total or 0,
        categoria=venda.categoria,
        subcategoria=venda.subcategoria,
        canal=venda.canal,
        loja_id=venda.loja_id,
        cidade=venda.cidade,
        estado=venda.estado,
        regiao=venda.regiao,
        feriado=venda.feriado or False,
        fim_semana=venda.data_venda.weekday() >= 5,
        evento_especial=venda.evento_especial,
        fonte_dados=venda.fonte_dados or "manual"
    )
    
    db.add(db_venda)
    db.commit()
    db.refresh(db_venda)
    
    # Limpa cache relacionado
    cache_service.delete_pattern(f"{CacheKeys.VENDAS_DIA}:{user_id}:*")
    cache_service.delete_pattern(f"{CacheKeys.VENDAS_AGREGADO}:{user_id}:*")
    
    return db_venda

@router.post("/bulk", response_model=Dict[str, int])
async def criar_vendas_lote(
    vendas_data: VendaBulkCreate,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Cria múltiplas vendas de uma vez (importação em lote).
    """
    payload = decode_token(token)
    user_id = int(payload.get("sub"))
    
    vendas_criadas = 0
    vendas_erro = 0
    
    for venda in vendas_data.vendas:
        try:
            db_venda = Venda(
                user_id=user_id,
                data_venda=venda.data_venda,
                ano=venda.data_venda.year,
                mes=venda.data_venda.month,
                dia=venda.data_venda.day,
                dia_semana=venda.data_venda.weekday(),
                hora=venda.data_venda.hour,
                valor_total=venda.valor_total,
                quantidade_itens=venda.quantidade_itens,
                ticket_medio=venda.valor_total / venda.quantidade_itens if venda.quantidade_itens > 0 else 0,
                desconto_total=venda.desconto_total or 0,
                categoria=venda.categoria,
                subcategoria=venda.subcategoria,
                canal=venda.canal,
                loja_id=venda.loja_id,
                cidade=venda.cidade,
                estado=venda.estado,
                regiao=venda.regiao,
                feriado=venda.feriado or False,
                fim_semana=venda.data_venda.weekday() >= 5,
                evento_especial=venda.evento_especial,
                fonte_dados=vendas_data.fonte_dados or "importacao"
            )
            
            db.add(db_venda)
            vendas_criadas += 1
            
        except Exception as e:
            vendas_erro += 1
            continue
    
    db.commit()
    
    # Limpa cache
    cache_service.delete_pattern(f"{CacheKeys.VENDAS_DIA}:{user_id}:*")
    cache_service.delete_pattern(f"{CacheKeys.VENDAS_AGREGADO}:{user_id}:*")
    
    return {
        "vendas_criadas": vendas_criadas,
        "vendas_erro": vendas_erro,
        "total_processadas": len(vendas_data.vendas)
    }

@router.get("/", response_model=List[VendaResponse])
async def listar_vendas(
    data_inicio: Optional[datetime] = Query(None),
    data_fim: Optional[datetime] = Query(None),
    categoria: Optional[CategoriaVenda] = Query(None),
    canal: Optional[CanalVenda] = Query(None),
    loja_id: Optional[str] = Query(None),
    limite: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Lista vendas com filtros opcionais.
    """
    payload = decode_token(token)
    user_id = int(payload.get("sub"))
    
    query = db.query(Venda).filter(Venda.user_id == user_id)
    
    if data_inicio:
        query = query.filter(Venda.data_venda >= data_inicio)
    
    if data_fim:
        query = query.filter(Venda.data_venda <= data_fim)
    
    if categoria:
        query = query.filter(Venda.categoria == categoria)
    
    if canal:
        query = query.filter(Venda.canal == canal)
    
    if loja_id:
        query = query.filter(Venda.loja_id == loja_id)
    
    vendas = query.order_by(Venda.data_venda.desc()).offset(offset).limit(limite).all()
    
    return vendas

@router.get("/agregadas", response_model=VendasAgregadas)
async def obter_vendas_agregadas(
    periodo: str = Query("dia", regex="^(dia|semana|mes|ano)$"),
    data_inicio: Optional[datetime] = Query(None),
    data_fim: Optional[datetime] = Query(None),
    agrupar_por: List[str] = Query(["data"], description="Campos para agrupar"),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Obtém vendas agregadas por período.
    """
    payload = decode_token(token)
    user_id = int(payload.get("sub"))
    
    # Define período padrão se não especificado
    if not data_inicio:
        if periodo == "dia":
            data_inicio = datetime.now() - timedelta(days=30)
        elif periodo == "semana":
            data_inicio = datetime.now() - timedelta(days=90)
        elif periodo == "mes":
            data_inicio = datetime.now() - timedelta(days=365)
        else:
            data_inicio = datetime.now() - timedelta(days=730)
    
    if not data_fim:
        data_fim = datetime.now()
    
    # Monta query de agregação
    campos_agrupamento = []
    campos_select = []
    
    for campo in agrupar_por:
        if campo == "data":
            if periodo == "dia":
                campos_agrupamento.append(func.date(Venda.data_venda))
                campos_select.append(func.date(Venda.data_venda).label("data"))
            elif periodo == "semana":
                campos_agrupamento.append(func.date_trunc('week', Venda.data_venda))
                campos_select.append(func.date_trunc('week', Venda.data_venda).label("data"))
            elif periodo == "mes":
                campos_agrupamento.append(func.date_trunc('month', Venda.data_venda))
                campos_select.append(func.date_trunc('month', Venda.data_venda).label("data"))
        elif campo == "categoria":
            campos_agrupamento.append(Venda.categoria)
            campos_select.append(Venda.categoria)
        elif campo == "canal":
            campos_agrupamento.append(Venda.canal)
            campos_select.append(Venda.canal)
        elif campo == "loja":
            campos_agrupamento.append(Venda.loja_id)
            campos_select.append(Venda.loja_id)
    
    # Adiciona agregações
    campos_select.extend([
        func.sum(Venda.valor_total).label("valor_total"),
        func.count(Venda.id).label("quantidade_vendas"),
        func.sum(Venda.quantidade_itens).label("quantidade_itens"),
        func.avg(Venda.ticket_medio).label("ticket_medio"),
        func.sum(Venda.desconto_total).label("desconto_total")
    ])
    
    query = db.query(*campos_select).filter(
        and_(
            Venda.user_id == user_id,
            Venda.data_venda >= data_inicio,
            Venda.data_venda <= data_fim
        )
    ).group_by(*campos_agrupamento)
    
    resultados = query.all()
    
    # Formata resultados
    dados_agregados = []
    for r in resultados:
        item = {
            "valor_total": float(r.valor_total or 0),
            "quantidade_vendas": int(r.quantidade_vendas or 0),
            "quantidade_itens": int(r.quantidade_itens or 0),
            "ticket_medio": float(r.ticket_medio or 0),
            "desconto_total": float(r.desconto_total or 0)
        }
        
        # Adiciona campos de agrupamento
        if hasattr(r, 'data'):
            item['data'] = r.data
        if hasattr(r, 'categoria'):
            item['categoria'] = r.categoria
        if hasattr(r, 'canal'):
            item['canal'] = r.canal
        if hasattr(r, 'loja_id'):
            item['loja_id'] = r.loja_id
        
        dados_agregados.append(item)
    
    return {
        "periodo": periodo,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "dados": dados_agregados
    }

@router.get("/estatisticas", response_model=EstatisticasVendas)
async def obter_estatisticas_vendas(
    periodo: str = Query("mes", regex="^(dia|semana|mes|ano)$"),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Obtém estatísticas gerais de vendas.
    """
    payload = decode_token(token)
    user_id = int(payload.get("sub"))
    
    # Define período
    if periodo == "dia":
        data_inicio = datetime.now().replace(hour=0, minute=0, second=0)
    elif periodo == "semana":
        data_inicio = datetime.now() - timedelta(days=7)
    elif periodo == "mes":
        data_inicio = datetime.now() - timedelta(days=30)
    else:
        data_inicio = datetime.now() - timedelta(days=365)
    
    # Período anterior para comparação
    periodo_dias = (datetime.now() - data_inicio).days
    data_inicio_anterior = data_inicio - timedelta(days=periodo_dias)
    
    # Estatísticas período atual
    stats_atual = db.query(
        func.sum(Venda.valor_total).label("total"),
        func.count(Venda.id).label("quantidade"),
        func.avg(Venda.ticket_medio).label("ticket_medio")
    ).filter(
        and_(
            Venda.user_id == user_id,
            Venda.data_venda >= data_inicio
        )
    ).first()
    
    # Estatísticas período anterior
    stats_anterior = db.query(
        func.sum(Venda.valor_total).label("total")
    ).filter(
        and_(
            Venda.user_id == user_id,
            Venda.data_venda >= data_inicio_anterior,
            Venda.data_venda < data_inicio
        )
    ).first()
    
    # Top categorias
    top_categorias = db.query(
        Venda.categoria,
        func.sum(Venda.valor_total).label("total")
    ).filter(
        and_(
            Venda.user_id == user_id,
            Venda.data_venda >= data_inicio
        )
    ).group_by(Venda.categoria).order_by(func.sum(Venda.valor_total).desc()).limit(5).all()
    
    # Calcula variações
    total_atual = float(stats_atual.total or 0)
    total_anterior = float(stats_anterior.total or 0)
    
    if total_anterior > 0:
        variacao_percentual = ((total_atual - total_anterior) / total_anterior) * 100
    else:
        variacao_percentual = 100 if total_atual > 0 else 0
    
    return {
        "periodo": periodo,
        "total_vendas": total_atual,
        "quantidade_vendas": int(stats_atual.quantidade or 0),
        "ticket_medio": float(stats_atual.ticket_medio or 0),
        "variacao_periodo_anterior": round(variacao_percentual, 2),
        "top_categorias": [
            {"categoria": cat.categoria, "total": float(cat.total)}
            for cat in top_categorias
        ]
    }

@router.post("/metas", response_model=MetaVendaResponse)
async def criar_meta_venda(
    meta: MetaVendaCreate,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Cria uma nova meta de vendas.
    """
    payload = decode_token(token)
    user_id = int(payload.get("sub"))
    
    # Verifica se já existe meta para o período
    meta_existente = db.query(MetaVenda).filter(
        and_(
            MetaVenda.user_id == user_id,
            MetaVenda.ano == meta.ano,
            MetaVenda.mes == meta.mes,
            MetaVenda.categoria == meta.categoria
        )
    ).first()
    
    if meta_existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Meta já existe para este período"
        )
    
    db_meta = MetaVenda(
        user_id=user_id,
        ano=meta.ano,
        mes=meta.mes,
        valor_meta=meta.valor_meta,
        categoria=meta.categoria
    )
    
    db.add(db_meta)
    db.commit()
    db.refresh(db_meta)
    
    return db_meta

@router.get("/metas", response_model=List[MetaVendaResponse])
async def listar_metas_vendas(
    ano: Optional[int] = Query(None),
    mes: Optional[int] = Query(None),
    ativa: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Lista metas de vendas do usuário.
    """
    payload = decode_token(token)
    user_id = int(payload.get("sub"))
    
    query = db.query(MetaVenda).filter(MetaVenda.user_id == user_id)
    
    if ano:
        query = query.filter(MetaVenda.ano == ano)
    
    if mes:
        query = query.filter(MetaVenda.mes == mes)
    
    if ativa is not None:
        query = query.filter(MetaVenda.ativa == ativa)
    
    metas = query.order_by(MetaVenda.ano.desc(), MetaVenda.mes.desc()).all()
    
    # Atualiza valores realizados
    for meta in metas:
        if meta.mes:
            data_inicio = datetime(meta.ano, meta.mes, 1)
            if meta.mes == 12:
                data_fim = datetime(meta.ano + 1, 1, 1)
            else:
                data_fim = datetime(meta.ano, meta.mes + 1, 1)
        else:
            data_inicio = datetime(meta.ano, 1, 1)
            data_fim = datetime(meta.ano + 1, 1, 1)
        
        query_realizado = db.query(
            func.sum(Venda.valor_total)
        ).filter(
            and_(
                Venda.user_id == user_id,
                Venda.data_venda >= data_inicio,
                Venda.data_venda < data_fim
            )
        )
        
        if meta.categoria:
            query_realizado = query_realizado.filter(Venda.categoria == meta.categoria)
        
        valor_realizado = query_realizado.scalar() or 0
        
        meta.valor_realizado = float(valor_realizado)
        meta.percentual_atingido = (meta.valor_realizado / meta.valor_meta * 100) if meta.valor_meta > 0 else 0
    
    db.commit()
    
    return metas