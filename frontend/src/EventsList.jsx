import { useState, useEffect } from 'react'

function EventsList() {
  const [eventos, setEventos] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchEventos()
  }, [])

  const fetchEventos = async () => {
    try {
      setLoading(true)
      setError(null)
      
      const response = await fetch('/events/simple')
      
      if (!response.ok) {
        throw new Error('Error al cargar eventos')
      }
      
      const data = await response.json()
      setEventos(data.eventos || [])
    } catch (err) {
      setError(err.message)
      console.error('Error fetching eventos:', err)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <div className="loading">Cargando eventos...</div>
  }

  if (error) {
    return <div className="error">Error: {error}</div>
  }

  return (
    <div className="section">
      <h2>📊 Datos Disponibles en la Base de Datos</h2>
      
      <div className="stats">
        <div className="stat-card">
          <h3>Total Eventos</h3>
          <p>{eventos.length}</p>
        </div>
        <div className="stat-card">
          <h3>Eventos Gratuitos</h3>
          <p>{eventos.filter(e => e.es_gratuito).length}</p>
        </div>
        <div className="stat-card">
          <h3>Eventos de Pago</h3>
          <p>{eventos.filter(e => !e.es_gratuito).length}</p>
        </div>
      </div>

      <div className="events-list">
        {eventos.length === 0 ? (
          <p>No hay eventos disponibles</p>
        ) : (
          eventos.map((evento, index) => (
            <div key={evento.id || index} className="event-item">
              <div className="event-title">
                {evento.titulo_es}
                {evento.es_gratuito ? (
                  <span className="badge badge-free">GRATIS</span>
                ) : (
                  <span className="badge badge-paid">
                    {evento.precio ? `${evento.precio}€` : 'DE PAGO'}
                  </span>
                )}
              </div>
              <div className="event-details">
                📍 {evento.poblacion} ({evento.cp}) | 
                📅 {evento.fecha || 'Sin fecha'} {evento.hora ? `- ${evento.hora}` : ''} |
                🏷️ {evento.categorias || 'Sin categoría'}
              </div>
            </div>
          ))
        )}
      </div>
      
      <p style={{ marginTop: '15px', fontSize: '13px', color: '#666' }}>
        💡 <strong>Tip:</strong> Usa estos datos para hacer preguntas relevantes en el chat de abajo
      </p>
    </div>
  )
}

export default EventsList
