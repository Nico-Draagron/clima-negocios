# Endpoints de analytics
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, case
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from app.core.database import get_db
from app.core.security import oauth2_scheme, decode_token
from app.models.vendas import Venda, CategoriaVenda
from app.models.clima import DadoClimatico
from app.models.predicoes import Predicao, StatusPredicao
from app.schemas.analytics import (
    DashboardResponse,
    TendenciaResponse,
    ComparacaoResponse,
    KPIResponse
)
from app.services.cache_service import cache_service, cache_result, CacheKeys

router = APIRouter()

@router.get("/dashboard", response_model=DashboardResponse)
@cache_result(CacheKeys.ANALYTICS_DASHBOARD, ttl=300, key_params=['periodo'])
async def obter_dashboard(
    periodo: str = Query("mes", regex="^(dia|semana|mes|trimestre|ano)$"),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Obtém dados consolidados para dashboard.
    """
    payload = decode_token(token)
    user_id = int(payload.get("sub"))
    
    # Define período de análise
    hoje = datetime.now()
    if periodo == "dia":
        data_inicio = hoje.replace(hour=0, minute=0, second=0)
    elif periodo == "semana":
        data_inicio = hoje - timedelta(days=7)
    elif periodo == "mes":
        data_inicio = hoje - timedelta(days=30)
    elif periodo == "trimestre":
        data_inicio = hoje - timedelta(days=90)
    else:  # ano
        data_inicio = hoje - timedelta(days=365)
    
    # KPIs principais
    kpis = await _calcular_kpis(user_id, data_inicio, db)
    
    # Gráfico de vendas por período
    vendas_periodo = await _vendas_por_periodo(user_id, data_inicio, periodo, db)
    
    # Top produtos/categorias
    top_categorias = await _top_categorias(user_id, data_inicio, db)
    
    # Performance por canal
    performance_canal = await _performance_por_canal(user_id, data_inicio, db)
    
    # Correlação clima
    correlacao_clima = await _correlacao_clima_resumo(user_id, data_inicio, db)
    
    # Predições recentes
    predicoes_recentes = await _predicoes_recentes(user_id, db)
    
    return {
        "periodo": periodo,
        "data_atualizacao": datetime.now(),
        "kpis": kpis,
        "vendas_periodo": vendas_periodo,
        "top_categorias": top_categorias,
        "performance_canal": performance_canal,
        "correlacao_clima": correlacao_clima,
        "predicoes_recentes": predicoes_recentes
    }

async def _calcular_kpis(user_id: int, data_inicio: datetime, db: Session) -> Dict:
    """Calcula KPIs principais."""
    
    # Período atual
    stats_atual = db.query(
        func.sum(Venda.valor_total).label("vendas_total"),
        func.count(Venda.id).label("num_vendas"),
        func.avg(Venda.ticket_medio).label("ticket_medio")
    ).filter(
        and_(
            Venda.user_id == user_id,
            Venda.data_venda >= data_inicio
        )
    ).first()
    
    # Período anterior (mesmo tamanho)
    periodo_dias = (datetime.now() - data_inicio).days
    data_inicio_anterior = data_inicio - timedelta(days=periodo_dias)
    
    stats_anterior = db.query(
        func.sum(Venda.valor_total).label("vendas_total")
    ).filter(
        and_(
            Venda.user_id == user_id,
            Venda.data_venda >= data_inicio_anterior,
            Venda.data_venda < data_inicio
        )
    ).first()
    
    # Calcula variações
    vendas_atual = float(stats_atual.vendas_total or 0)
    vendas_anterior = float(stats_anterior.vendas_total or 0)
    
    if vendas_anterior > 0:
        crescimento = ((vendas_atual - vendas_anterior) / vendas_anterior) * 100
    else:
        crescimento = 100 if vendas_atual > 0 else 0
    
    return {
        "vendas_total": vendas_atual,
        "crescimento_percentual": round(crescimento, 2),
        "numero_vendas": int(stats_atual.num_vendas or 0),
        "ticket_medio": float(stats_atual.ticket_medio or 0),
        "vendas_dia_media": vendas_atual / max(periodo_dias, 1)
    }

@router.get("/tendencias", response_model=TendenciaResponse)
async def analisar_tendencias(
    periodo_meses: int = Query(6, ge=1, le=24),
    categoria: Optional[CategoriaVenda] = Query(None),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Analisa tendências de vendas.
    """
    payload = decode_token(token)
    user_id = int(payload.get("sub"))
    
    data_inicio = datetime.now() - timedelta(days=periodo_meses * 30)
    
    # Query base
    query = db.query(
        func.date_trunc('month', Venda.data_venda).label("mes"),
        func.sum(Venda.valor_total).label("total"),
        func.count(Venda.id).label("quantidade")
    ).filter(
        and_(
            Venda.user_id == user_id,
            Venda.data_venda >= data_inicio
        )
    )
    
    if categoria:
        query = query.filter(Venda.categoria == categoria)
    
    # Agrupa por mês
    dados_mensais = query.group_by(
        func.date_trunc('month', Venda.data_venda)
    ).order_by("mes").all()
    
    if len(dados_mensais) < 3:
        return {
            "tendencia": "insuficiente",
            "dados_mensais": dados_mensais,
            "projecao_proximos_meses": []
        }
    
    # Análise de tendência
    valores = [float(d.total) for d in dados_mensais]
    meses = list(range(len(valores)))
    
    # Regressão linear simples
    coef = np.polyfit(meses, valores, 1)
    tendencia = "crescente" if coef[0] > 0 else "decrescente"
    
    # Projeção para próximos 3 meses
    projecao = []
    for i in range(1, 4):
        mes_projetado = len(valores) + i
        valor_projetado = coef[0] * mes_projetado + coef[1]
        projecao.append({
            "mes": mes_projetado,
            "valor_projetado": max(0, valor_projetado)
        })
    
    return {
        "tendencia": tendencia,
        "taxa_crescimento_mensal": float(coef[0]),
        "dados_mensais": [
            {
                "mes": d.mes,
                "total": float(d.total),
                "quantidade": int(d.quantidade)
            }
            for d in dados_mensais
        ],
        "projecao_proximos_meses": projecao
    }

@router.get("/comparacao-periodos", response_model=ComparacaoResponse)
async def comparar_periodos(
    periodo1_inicio: datetime = Query(...),
    periodo1_fim: datetime = Query(...),
    periodo2_inicio: datetime = Query(...),
    periodo2_fim: datetime = Query(...),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Compara métricas entre dois períodos.
    """
    payload = decode_token(token)
    user_id = int(payload.get("sub"))
    
    # Valida períodos
    if periodo1_fim <= periodo1_inicio or periodo2_fim <= periodo2_inicio:
        raise HTTPException(
            status_code=400,
            detail="Períodos inválidos"
        )
    
    # Dados período 1
    dados_p1 = await _dados_periodo(user_id, periodo1_inicio, periodo1_fim, db)
    
    # Dados período 2
    dados_p2 = await _dados_periodo(user_id, periodo2_inicio, periodo2_fim, db)
    
    # Calcula variações
    variacoes = {}
    for metrica in ['vendas_total', 'ticket_medio', 'num_vendas']:
        if dados_p1[metrica] > 0:
            variacao = ((dados_p2[metrica] - dados_p1[metrica]) / dados_p1[metrica]) * 100
        else:
            variacao = 100 if dados_p2[metrica] > 0 else 0
        variacoes[f"variacao_{metrica}"] = round(variacao, 2)
    
    return {
        "periodo1": {
            "inicio": periodo1_inicio,
            "fim": periodo1_fim,
            **dados_p1
        },
        "periodo2": {
            "inicio": periodo2_inicio,
            "fim": periodo2_fim,
            **dados_p2
        },
        "variacoes": variacoes
    }

async def _dados_periodo(
    user_id: int,
    data_inicio: datetime,
    data_fim: datetime,
    db: Session
):
    """Obtém dados consolidados de vendas para um período."""
    stats = db.query(
        func.sum(Venda.valor_total).label("vendas_total"),
        func.count(Venda.id).label("num_vendas"),
        func.avg(Venda.ticket_medio).label("ticket_medio")
    ).filter(
        and_(
            Venda.user_id == user_id,
            Venda.data_venda >= data_inicio,
            Venda.data_venda <= data_fim
        )
    ).first()
    return {
        "vendas_total": float(stats.vendas_total or 0),
        "ticket_medio": float(stats.ticket_medio or 0),
        "num_vendas": int(stats.num_vendas or 0)
    }

# Função auxiliar: vendas por período (para dashboard)
async def _vendas_por_periodo(user_id: int, data_inicio: datetime, periodo: str, db: Session):
    """Retorna vendas agregadas por período (dia, semana, mês, etc)."""
    if periodo == "dia":
        trunc_func = func.date_trunc('hour', Venda.data_venda)
        label = "hora"
    elif periodo == "semana":
        trunc_func = func.date_trunc('day', Venda.data_venda)
        label = "dia"
    elif periodo == "mes":
        trunc_func = func.date_trunc('day', Venda.data_venda)
        label = "dia"
    elif periodo == "trimestre":
        trunc_func = func.date_trunc('week', Venda.data_venda)
        label = "semana"
    else:
        trunc_func = func.date_trunc('month', Venda.data_venda)
        label = "mes"
    rows = db.query(
        trunc_func.label(label),
        func.sum(Venda.valor_total).label("total"),
        func.count(Venda.id).label("quantidade")
    ).filter(
        and_(
            Venda.user_id == user_id,
            Venda.data_venda >= data_inicio
        )
    ).group_by(trunc_func).order_by(trunc_func).all()
    return [
        {label: getattr(r, label), "total": float(r.total), "quantidade": int(r.quantidade)}
        for r in rows
    ]

# Função auxiliar: top categorias
async def _top_categorias(user_id: int, data_inicio: datetime, db: Session):
    rows = db.query(
        Venda.categoria,
        func.sum(Venda.valor_total).label("total"),
        func.count(Venda.id).label("quantidade")
    ).filter(
        and_(
            Venda.user_id == user_id,
            Venda.data_venda >= data_inicio
        )
    ).group_by(Venda.categoria).order_by(func.sum(Venda.valor_total).desc()).limit(5).all()
    return [
        {"categoria": r.categoria, "total": float(r.total), "quantidade": int(r.quantidade)}
        for r in rows
    ]

# Função auxiliar: performance por canal
async def _performance_por_canal(user_id: int, data_inicio: datetime, db: Session):
    rows = db.query(
        Venda.canal,
        func.sum(Venda.valor_total).label("total"),
        func.count(Venda.id).label("quantidade")
    ).filter(
        and_(
            Venda.user_id == user_id,
            Venda.data_venda >= data_inicio
        )
    ).group_by(Venda.canal).order_by(func.sum(Venda.valor_total).desc()).all()
    return [
        {"canal": r.canal, "total": float(r.total), "quantidade": int(r.quantidade)}
        for r in rows
    ]

# Função auxiliar: correlação clima-vendas (resumo)
async def _correlacao_clima_resumo(user_id: int, data_inicio: datetime, db: Session):
    # Exemplo simplificado: correlação entre temperatura média diária e vendas diárias
    vendas = db.query(
        func.date_trunc('day', Venda.data_venda).label("dia"),
        func.sum(Venda.valor_total).label("vendas")
    ).filter(
        and_(Venda.user_id == user_id, Venda.data_venda >= data_inicio)
    ).group_by(func.date_trunc('day', Venda.data_venda)).all()
    clima = db.query(
        DadoClimatico.data.label("dia"),
        func.avg(DadoClimatico.temperatura).label("temperatura")
    ).filter(
        and_(DadoClimatico.user_id == user_id, DadoClimatico.data >= data_inicio)
    ).group_by(DadoClimatico.data).all()
    # Junta por dia
    vendas_dict = {str(v.dia): float(v.vendas) for v in vendas}
    clima_dict = {str(c.dia): float(c.temperatura) for c in clima}
    dias = set(vendas_dict.keys()) & set(clima_dict.keys())
    if len(dias) < 3:
        return {"correlacao": None, "n": len(dias)}
    vendas_list = [vendas_dict[d] for d in dias]
    temp_list = [clima_dict[d] for d in dias]
    correlacao = float(np.corrcoef(vendas_list, temp_list)[0, 1])
    return {"correlacao": correlacao, "n": len(dias)}

# Função auxiliar: predições recentes
async def _predicoes_recentes(user_id: int, db: Session):
    rows = db.query(
        Predicao.id,
        Predicao.data_predicao,
        Predicao.status,
        Predicao.resultado
    ).filter(
        Predicao.user_id == user_id
    ).order_by(Predicao.data_predicao.desc()).limit(5).all()
    return [
        {
            "id": r.id,
            "data_predicao": r.data_predicao,
            "status": r.status,
            "resultado": r.resultado
        }
        for r in rows
    ]