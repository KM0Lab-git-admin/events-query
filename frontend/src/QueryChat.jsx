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

          {/* Eventos en 4 bloques por nivel de coincidencia */}
          {response.eventos && response.eventos.length > 0 && (() => {
            const BLOQUES = [
              { nivel: 'mayor', titulo: 'Coincidencia mayor', clase: 'coincidencia-mayor', max: 10 },
              { nivel: 'templada', titulo: 'Coincidencia templada', clase: 'coincidencia-templada', max: 10 },
              { nivel: 'baja', titulo: 'Coincidencia baja', clase: 'coincidencia-baja', max: 10 },
              { nivel: 'muy_poca', titulo: 'Muy poca coincidencia', clase: 'coincidencia-muy-poca', max: 10 }
            ]
            const porNivel = { mayor: [], templada: [], baja: [], muy_poca: [] }
            response.eventos.forEach(ev => {
              const n = ev.nivel_coincidencia || 'muy_poca'
              if (porNivel[n] && porNivel[n].length < 10) porNivel[n].push(ev)
            })
            return (
              <div className="chat-events-list">
                {BLOQUES.map(({ nivel, titulo, clase, max }) => {
                  const eventos = porNivel[nivel] || []
                  if (eventos.length === 0) return null
                  return (
                    <div key={nivel} className={`chat-events-block ${clase}`}>
                      <h4 className="block-titulo">{titulo} ({eventos.length})</h4>
                      {eventos.map((evento, idx) => {
                        const pasaUmbral = evento.similitud_score !== null && evento.similitud_score >= 0.4
                        return (
                          <div
                            key={evento.id_unico_evento || idx}
                            className={`chat-event-item ${pasaUmbral ? 'evento-pasa' : 'evento-no-pasa'}`}
                          >
                            <div className="chat-event-header">
                              <span className="evento-indicador">{pasaUmbral ? '✅' : '❌'}</span>
                              <span className="evento-titulo">{evento.titulo || 'Sin título'}</span>
                              {evento.similitud_score !== null && (
                                <span className={`evento-score ${pasaUmbral ? 'score-pasa' : 'score-no-pasa'}`}>
                                  Score: {evento.similitud_score.toFixed(3)}
                                </span>
                              )}
                            </div>
                            {evento.descripcion_corta && (
                              <p className="evento-descripcion">{evento.descripcion_corta}</p>
                            )}
                            <div className="evento-meta">
                              {evento.poblacion_nombre && <span>📍 {evento.poblacion_nombre}</span>}
                              {evento.fecha_inicio && <span>📅 {new Date(evento.fecha_inicio).toLocaleDateString('es-ES')}</span>}
                              {evento.es_gratuito && <span>💰 Gratis</span>}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )
                })}
              </div>
            )
          })()}

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
