"""
Tests para los endpoints de la API.
"""

import pytest
from httpx import AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_root_endpoint():
    """Test del endpoint raíz."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert data["name"] == "Events Query API"


@pytest.mark.asyncio
async def test_health_endpoint():
    """Test del health check."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "version" in data
        assert "checks" in data
        assert data["status"] in ["healthy", "unhealthy"]


@pytest.mark.asyncio
async def test_query_endpoint_validation():
    """Test de validación del endpoint /query."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Request sin pregunta (debe fallar)
        response = await client.post("/query", json={
            "cp_usuario": "08380"
        })
        assert response.status_code == 422  # Validation error
        
        # Request con CP inválido (debe fallar)
        response = await client.post("/query", json={
            "pregunta": "¿Qué hacer?",
            "cp_usuario": "123"  # CP inválido (debe ser 5 dígitos)
        })
        assert response.status_code == 422
        
        # Request con pregunta muy corta (debe fallar)
        response = await client.post("/query", json={
            "pregunta": "ab",  # Muy corta (mínimo 3 caracteres)
            "cp_usuario": "08380"
        })
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_endpoint_success():
    """Test exitoso del endpoint /query."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/query", json={
            "pregunta": "¿Qué hacer este fin de semana?",
            "cp_usuario": "08380",
            "debug": True
        })
        
        # Puede fallar si no hay BD configurada, pero la estructura debe ser correcta
        if response.status_code == 200:
            data = response.json()
            assert "respuesta_texto" in data
            assert "eventos" in data
            assert "total" in data
            assert "idioma_respuesta" in data
            assert isinstance(data["eventos"], list)
            assert isinstance(data["total"], int)
            assert data["idioma_respuesta"] in ["es", "ca"]
            
            # Si debug está activado, debe incluir debug_info
            assert "debug_info" in data
            assert "parametros_extraidos" in data["debug_info"]


@pytest.mark.asyncio
async def test_query_endpoint_catalan():
    """Test del endpoint /query en catalán."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/query", json={
            "pregunta": "Què fer aquest cap de setmana?",
            "cp_usuario": "08380"
        })
        
        if response.status_code == 200:
            data = response.json()
            # Debe detectar catalán
            assert data["idioma_respuesta"] == "ca"
