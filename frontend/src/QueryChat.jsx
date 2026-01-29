import { useState } from 'react'

function QueryChat({ onAnalysisUpdate }) {
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
      
      // Pasar análisis al componente padre
      console.log('DEBUG: data.debug_info =', data.debug_info)
      console.log('DEBUG: analisis_detallado =', data.debug_info?.analisis_detallado)
      
      if (onAnalysisUpdate && data.debug_info && data.debug_info.analisis_detallado) {
        console.log('DEBUG: Llamando onAnalysisUpdate con', data.debug_info.analisis_detallado.length, 'eventos')
        onAnalysisUpdate(data.debug_info.analisis_detallado)
      } else {
        console.log('DEBUG: NO se llama onAnalysisUpdate')
      }
    } catch (err) {
      setError(err.message)
      console.error('Error en query:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="chat-panel">
      <h2 className="chat-title">🔍 Consultas en Lenguaje Natural</h2>
      
      <form onSubmit={handleSubmit} className="chat-form">
        <input
          type="text"
          placeholder="Ej: ¿Qué hacer este fin de semana?"
          value={pregunta}
          onChange={(e) => setPregunta(e.target.value)}
          disabled={loading}
          className="chat-input-pregunta"
        />
        <div className="chat-form-row">
          <input
            type="text"
            placeholder="CP"
            value={cpUsuario}
            onChange={(e) => setCpUsuario(e.target.value)}
            disabled={loading}
            className="chat-input-cp"
          />
          <button type="submit" disabled={loading} className="chat-btn">
            {loading ? '...' : 'Buscar'}
          </button>
        </div>
      </form>

      {error && (
        <div className="chat-error">
          ❌ {error}
        </div>
      )}

      {loading && (
        <div className="chat-loading">
          ⏳ Procesando...
        </div>
      )}

      {response && (
        <div className="chat-response">
          <div className="chat-response-text">
            <p>{response.respuesta_texto}</p>
          </div>

          <div className="chat-response-meta">
            <strong>{response.total} eventos encontrados</strong>
          </div>

          <details>
            <summary className="chat-details-summary">
              Ver JSON completo
            </summary>
            <pre className="chat-json">
              {JSON.stringify(response, null, 2)}
            </pre>
          </details>
        </div>
      )}

      {!response && !loading && (
        <div className="chat-examples">
          <strong>💡 Ejemplos:</strong>
          <ul>
            <li>¿Qué hacer este fin de semana?</li>
            <li>Eventos gratuitos para niños</li>
            <li>Actividades de cultura</li>
          </ul>
        </div>
      )}
    </div>
  )
}

export default QueryChat
