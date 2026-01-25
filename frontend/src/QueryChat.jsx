import { useState } from 'react'

function QueryChat() {
  const [pregunta, setPregunta] = useState('')
  const [cpUsuario, setCpUsuario] = useState('08380')
  const [loading, setLoading] = useState(false)
  const [response, setResponse] = useState(null)
  const [error, setError] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    
    if (!pregunta.trim()) {
      setError('Por favor, escribe una pregunta')
      return
    }

    if (!cpUsuario.trim()) {
      setError('Por favor, ingresa un código postal')
      return
    }

    try {
      setLoading(true)
      setError(null)
      setResponse(null)

      const response = await fetch('/query', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          pregunta: pregunta,
          cp_usuario: cpUsuario,
          debug: true
        })
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Error en la consulta')
      }

      const data = await response.json()
      setResponse(data)
    } catch (err) {
      setError(err.message)
      console.error('Error en query:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="section">
      <h2>🔍 Chat de Consultas en Lenguaje Natural</h2>
      
      <form onSubmit={handleSubmit} className="query-form">
        <input
          type="text"
          placeholder="Ej: ¿Qué hacer este fin de semana?"
          value={pregunta}
          onChange={(e) => setPregunta(e.target.value)}
          disabled={loading}
        />
        <input
          type="text"
          placeholder="CP: 08380"
          value={cpUsuario}
          onChange={(e) => setCpUsuario(e.target.value)}
          disabled={loading}
          style={{ maxWidth: '150px' }}
        />
        <button type="submit" disabled={loading}>
          {loading ? 'Buscando...' : 'Buscar'}
        </button>
      </form>

      {error && (
        <div className="error">
          ❌ {error}
        </div>
      )}

      {loading && (
        <div className="loading">
          ⏳ Procesando tu consulta con OpenAI...
        </div>
      )}

      {response && (
        <div className="response-container">
          <h3 style={{ marginBottom: '15px', color: '#2c3e50' }}>
            📋 Respuesta de la API:
          </h3>
          
          <div style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#e8f5e9', borderRadius: '4px', borderLeft: '4px solid #4caf50' }}>
            <strong>Respuesta en lenguaje natural:</strong>
            <p style={{ marginTop: '8px', lineHeight: '1.6' }}>
              {response.respuesta_texto}
            </p>
          </div>

          <div style={{ marginBottom: '15px' }}>
            <strong>Eventos encontrados: {response.total}</strong>
          </div>

          <details open>
            <summary style={{ cursor: 'pointer', fontWeight: 'bold', marginBottom: '10px', color: '#2c3e50' }}>
              Ver JSON completo
            </summary>
            <pre className="response-json">
              {JSON.stringify(response, null, 2)}
            </pre>
          </details>
        </div>
      )}

      <div style={{ marginTop: '20px', padding: '15px', backgroundColor: '#fff3cd', borderRadius: '4px', fontSize: '13px' }}>
        <strong>💡 Ejemplos de preguntas:</strong>
        <ul style={{ marginTop: '8px', marginLeft: '20px' }}>
          <li>¿Qué hacer este fin de semana?</li>
          <li>Eventos gratuitos para niños</li>
          <li>Actividades de cultura en mi zona</li>
          <li>Conciertos de música cerca de mí</li>
        </ul>
      </div>
    </div>
  )
}

export default QueryChat
