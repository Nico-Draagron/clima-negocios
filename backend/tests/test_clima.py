import pytest
from fastapi.testclient import TestClient

def test_listar_estacoes(client: TestClient, auth_headers: dict):
    """Test listing weather stations."""
    response = client.get(
        "/api/v1/clima/estacoes",
        headers=auth_headers
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_obter_previsao(client: TestClient, auth_headers: dict):
    """Test getting weather forecast."""
    response = client.get(
        "/api/v1/clima/previsao?latitude=-30.05&longitude=-51.17&dias=7",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 7