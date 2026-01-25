# 🚀 Quick Start - PoC Frontend

## Inicio Rápido en 3 Pasos

### 1️⃣ Iniciar Backend (Terminal 1)

```bash
cd /home/ubuntu/events-query
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2️⃣ Iniciar Frontend (Terminal 2)

```bash
cd /home/ubuntu/events-query/frontend
pnpm install  # Solo la primera vez
pnpm dev
```

### 3️⃣ Abrir Navegador

Abre: **http://localhost:3000**

---

## ✅ Verificar que Todo Funciona

### Backend Health Check
```bash
curl http://localhost:8000/health
```

Debe devolver:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  ...
}
```

### Frontend
- Debes ver la lista de eventos en la parte superior
- Debes poder hacer preguntas en el chat inferior

---

## 🧪 Prueba Rápida

1. **Mira los eventos disponibles** en la lista superior
2. **Escribe una pregunta:** "¿Qué hacer este fin de semana?"
3. **CP:** 08380
4. **Click "Buscar"**
5. **Espera 2-3 segundos**
6. **Verás la respuesta** con eventos encontrados

---

## 🐛 Problemas Comunes

### "Failed to fetch"
→ El backend no está corriendo. Ejecuta el paso 1️⃣

### "No hay eventos disponibles"
→ Genera datos fake:
```bash
cd /home/ubuntu/events-query
python scripts/generate_fake_data.py
```

### "OpenAI API key not configured"
→ Configura `.env`:
```bash
cd /home/ubuntu/events-query
nano .env
# Añade: OPENAI_API_KEY=tu_key
```

---

## 📚 Documentación Completa

- **Guía detallada:** `POC_FRONTEND_GUIDE.md`
- **Plan de implementación:** `PLAN_FRONTEND_WEB.md`
- **README frontend:** `frontend/README.md`

---

## 🔗 Enlaces Útiles

- **Frontend:** http://localhost:3000
- **Backend API Docs:** http://localhost:8000/docs
- **Backend Health:** http://localhost:8000/health
- **Pull Request:** https://github.com/KM0Lab-git-admin/events-query/pull/1

---

**¡Listo para probar! 🎉**
