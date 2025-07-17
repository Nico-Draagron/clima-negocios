import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

def test_criar_venda(client: TestClient, auth_headers: dict):
    """Test creating a sale."""
    response = client.post(
        "/api/v1/vendas/",
        headers=auth_headers,
        json={
            "data_venda": datetime.now().isoformat(),
            "valor_total": 150.50,
            "quantidade_itens": 3,
            "categoria": "bebidas",
            "canal": "loja_fisica",
            "cidade": "Porto Alegre",
            "estado": "RS"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["valor_total"] == 150.50
    assert data["ticket_medio"] == pytest.approx(50.17, 0.01)

def test_listar_vendas(client: TestClient, auth_headers: dict):
    """Test listing sales."""
    response = client.get(
        "/api/v1/vendas/",
        headers=auth_headers
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_estatisticas_vendas(client: TestClient, auth_headers: dict):
    """Test sales statistics."""
    response = client.get(
        "/api/v1/vendas/estatisticas?periodo=mes",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "total_vendas" in data
    assert "ticket_medio" in data