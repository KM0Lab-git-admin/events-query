import { useState, useEffect, useCallback } from 'react'

// Colores para categorías
const CATEGORIA_COLORS = {
  cultura: '#9C27B0',
  deportes: '#4CAF50',
  ocio: '#FF9800',
  infantil: '#2196F3',
  formacion: '#607D8B',
  gastronomia: '#F44336',
  musica: '#E91E63',
  naturaleza: '#8BC34A'
}

// Textos de la interfaz en castellano y catalán
const TEXTOS_UI = {
  es: {
    tituloSeccion: 'Explorar Eventos',
    cambiarIdioma: 'Ver en catalán',
    poblacion: 'Población',
    categoria: 'Categoría',
    todas: 'Todas',
    todos: 'Todos',
    organizador: 'Organizador',
    tags: 'Tags',
    precio: 'Precio',
    tipo: 'Tipo',
    gratuitos: 'Gratuitos',
    dePago: 'De pago',
    recurrentes: 'Recurrentes',
    puntuales: 'Puntuales',
    desde: 'Desde',
    hasta: 'Hasta',
    limpiarFiltros: 'Limpiar filtros',
    eventosEncontrados: 'eventos encontrados',
    mostrando: 'Mostrando',
    cargando: 'Cargando eventos...',
    noResultados: 'No se encontraron eventos con los filtros seleccionados',
    descripcion: 'Descripción',
    ubicacion: 'Ubicación',
    fechasHorario: 'Fechas y horario',
    inicio: 'Inicio',
    fin: 'Fin',
    recurrente: 'Recurrente',
    etiquetas: 'Tags',
    gratis: 'GRATIS',
    anterior: '← Anterior',
    siguiente: 'Siguiente →',
    pagina: 'Página',
    de: 'de',
    cada: 'cada',
    hastaFecha: 'hasta',
    publico: 'Público',
    privado: 'Privado',
    asociacion: 'Asociación',
    placeholderTags: 'Ej: cultura, #gastronomia, yoga...',
    error: 'Error'
  },
  ca: {
    tituloSeccion: 'Explorar Esdeveniments',
    cambiarIdioma: 'Veure en castellà',
    poblacion: 'Població',
    categoria: 'Categoria',
    todas: 'Totes',
    todos: 'Tots',
    organizador: 'Organitzador',
    tags: 'Etiquetes',
    precio: 'Preu',
    tipo: 'Tipus',
    gratuitos: 'Gratuïts',
    dePago: 'De pagament',
    recurrentes: 'Recurrents',
    puntuales: 'Puntuals',
    desde: 'Des de',
    hasta: 'Fins',
    limpiarFiltros: 'Netejar filtres',
    eventosEncontrados: 'esdeveniments trobats',
    mostrando: 'Mostrant',
    cargando: 'Carregant esdeveniments...',
    noResultados: 'No s\'han trobat esdeveniments amb els filtres seleccionats',
    descripcion: 'Descripció',
    ubicacion: 'Ubicació',
    fechasHorario: 'Dates i horari',
    inicio: 'Inici',
    fin: 'Fi',
    recurrente: 'Recurrent',
    etiquetas: 'Etiquetes',
    gratis: 'GRATUÏT',
    anterior: '← Anterior',
    siguiente: 'Següent →',
    pagina: 'Pàgina',
    de: 'de',
    cada: 'cada',
    hastaFecha: 'fins',
    publico: 'Públic',
    privado: 'Privat',
    asociacion: 'Associació',
    placeholderTags: 'Ex: cultura, #gastronomia, ioga...',
    error: 'Error'
  }
}

function EventsList() {
  const [eventos, setEventos] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [total, setTotal] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  
  /** Idioma de visualización: 'es' = Castellano, 'ca' = Català */
  const [idioma, setIdioma] = useState('es')
  
  // Datos para filtros
  const [poblaciones, setPoblaciones] = useState([])
  const [categorias, setCategorias] = useState([])
  
  // Estado de filtros
  const [filtros, setFiltros] = useState({
    poblacion: '',
    categoria: '',
    tipo_organizador: '',
    tags: '',
    es_gratuito: '',
    es_recurrente: '',
    fecha_desde: '',
    fecha_hasta: ''
  })
  
  // Paginación
  const [offset, setOffset] = useState(0)
  const limit = 20

  // Cargar datos iniciales
  useEffect(() => {
    fetchPoblaciones()
    fetchCategorias()
  }, [])

  // Cargar eventos cuando cambian filtros o paginación
  useEffect(() => {
    fetchEventos()
  }, [filtros, offset])

  const fetchPoblaciones = async () => {
    try {
      const response = await fetch('/events/poblaciones')
      if (response.ok) {
        const data = await response.json()
        setPoblaciones(data.poblaciones || [])
      }
    } catch (err) {
      console.error('Error fetching poblaciones:', err)
    }
  }

  const fetchCategorias = async () => {
    try {
      const response = await fetch('/events/categorias')
      if (response.ok) {
        const data = await response.json()
        setCategorias(data.categorias || [])
      }
    } catch (err) {
      console.error('Error fetching categorias:', err)
    }
  }

  const fetchEventos = async () => {
    try {
      setLoading(true)
      setError(null)
      
      // Construir URL con parámetros
      const params = new URLSearchParams()
      params.append('limit', limit)
      params.append('offset', offset)
      
      if (filtros.poblacion) params.append('poblacion', filtros.poblacion)
      if (filtros.categoria) params.append('categoria', filtros.categoria)
      if (filtros.tipo_organizador) params.append('tipo_organizador', filtros.tipo_organizador)
      if (filtros.tags?.trim()) params.append('tags', filtros.tags.trim())
      if (filtros.es_gratuito !== '') params.append('es_gratuito', filtros.es_gratuito)
      if (filtros.es_recurrente !== '') params.append('es_recurrente', filtros.es_recurrente)
      if (filtros.fecha_desde) params.append('fecha_desde', filtros.fecha_desde)
      if (filtros.fecha_hasta) params.append('fecha_hasta', filtros.fecha_hasta)
      
      const response = await fetch(`/events/list?${params.toString()}`)
      
      if (!response.ok) {
        throw new Error('Error al cargar eventos')
      }
      
      const data = await response.json()
      setEventos(data.eventos || [])
      setTotal(data.total || 0)
      setHasMore(data.has_more || false)
    } catch (err) {
      setError(err.message)
      console.error('Error fetching eventos:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleFiltroChange = (campo, valor) => {
    setFiltros(prev => ({ ...prev, [campo]: valor }))
    setOffset(0) // Reset paginación al cambiar filtros
  }

  const limpiarFiltros = () => {
    setFiltros({
      poblacion: '',
      categoria: '',
      tipo_organizador: '',
      tags: '',
      es_gratuito: '',
      es_recurrente: '',
      fecha_desde: '',
      fecha_hasta: ''
    })
    setOffset(0)
  }

  const formatearFecha = (fecha) => {
    if (!fecha) return 'Sin fecha'
    const d = new Date(fecha)
    return d.toLocaleDateString('es-ES', { 
      weekday: 'short', 
      day: 'numeric', 
      month: 'short' 
    })
  }

  const formatearHora = (hora) => {
    if (!hora) return ''
    // Hora viene como "HH:MM:SS", mostrar solo "HH:MM"
    return hora.substring(0, 5)
  }

  const getTipoOrganizadorIcon = (tipo) => {
    switch (tipo) {
      case 'PUBLICO': return '🏛️'
      case 'PRIVADO': return '🏢'
      case 'ASOCIACION': return '🤝'
      default: return '📍'
    }
  }

  const t = TEXTOS_UI[idioma]

  const getTipoOrganizadorLabel = (tipo) => {
    switch (tipo) {
      case 'PUBLICO': return t.publico
      case 'PRIVADO': return t.privado
      case 'ASOCIACION': return t.asociacion
      default: return tipo
    }
  }

  /** Asegura que cada tag se muestre con # delante */
  const formatTags = (tags) => {
    if (!tags || !Array.isArray(tags)) return []
    return tags.map(tag => (typeof tag === 'string' && tag.trim() ? (tag.startsWith('#') ? tag : `#${tag}`) : '')).filter(Boolean)
  }

  /** Recurrencia JSON a texto legible */
  const formatRecurrencia = (recurrencia) => {
    if (!recurrencia) return null
    try {
      const r = typeof recurrencia === 'string' ? JSON.parse(recurrencia) : recurrencia
      const tipo = r.tipo || ''
      const intervalo = r.intervalo
      const regla = r.regla || {}
      const dias = regla.dias_semana || []
      const fin = regla.finalizacion?.valor || ''
      const horarios = (r.horarios || []).map(h => `${h.inicio || ''}-${h.fin || ''}`).filter(Boolean)
      const parts = []
      if (tipo) parts.push(tipo)
      if (intervalo) parts.push(`${t.cada} ${intervalo}`)
      if (dias.length) parts.push(dias.join(', '))
      if (fin) parts.push(`${t.hastaFecha} ${fin}`)
      if (horarios.length) parts.push(horarios.join('; '))
      return parts.join(' · ') || null
    } catch (_) {
      return null
    }
  }

  /** Contenido del evento en el idioma seleccionado (con fallback al otro) */
  const eventoTexto = (evento, campo) => {
    if (campo === 'titulo') return idioma === 'ca' ? (evento.titulo_cat || evento.titulo_es) : evento.titulo_es
    if (campo === 'descripcion') return idioma === 'ca' ? (evento.descripcion_cat || evento.descripcion_es) : evento.descripcion_es
    if (campo === 'tags') return idioma === 'ca' ? (evento.tags_cat?.length ? evento.tags_cat : evento.tags_es) : (evento.tags_es || [])
    if (campo === 'categorias') {
      const arr = idioma === 'ca' ? (evento.categorias_cat || evento.categorias_es) : (evento.categorias_es || evento.categorias_slugs)
      return Array.isArray(arr) ? arr : []
    }
    return null
  }

  return (
    <div className="events-container">
      <div className="events-header-row">
        <h2>{t.tituloSeccion}</h2>
        <button
          type="button"
          className="btn-idioma"
          onClick={() => setIdioma(prev => prev === 'es' ? 'ca' : 'es')}
          title={idioma === 'es' ? t.cambiarIdioma : TEXTOS_UI.es.cambiarIdioma}
        >
          {idioma === 'es' ? 'Català' : 'Castellano'}
        </button>
      </div>
      
      {/* Panel de filtros */}
      <div className="filters-panel">
        <div className="filters-row">
          {/* Población */}
          <div className="filter-group">
            <label>{t.poblacion}</label>
            <select 
              value={filtros.poblacion} 
              onChange={(e) => handleFiltroChange('poblacion', e.target.value)}
            >
              <option value="">{t.todas}</option>
              {poblaciones.map(p => (
                <option key={p.cp} value={p.nombre}>
                  {p.nombre} ({p.total_eventos})
                </option>
              ))}
            </select>
          </div>
          
          {/* Categoría */}
          <div className="filter-group">
            <label>{t.categoria}</label>
            <select 
              value={filtros.categoria} 
              onChange={(e) => handleFiltroChange('categoria', e.target.value)}
            >
              <option value="">{t.todas}</option>
              {categorias.map(c => (
                <option key={c.slug} value={c.slug}>{idioma === 'ca' ? (c.nombre_cat || c.nombre_es) : c.nombre_es}</option>
              ))}
            </select>
          </div>
          
          {/* Tipo organizador */}
          <div className="filter-group">
            <label>{t.organizador}</label>
            <select 
              value={filtros.tipo_organizador} 
              onChange={(e) => handleFiltroChange('tipo_organizador', e.target.value)}
            >
              <option value="">{t.todos}</option>
              <option value="PUBLICO">{t.publico}</option>
              <option value="PRIVADO">{t.privado}</option>
              <option value="ASOCIACION">{t.asociacion}</option>
            </select>
          </div>
          
          {/* Tags (campo abierto) */}
          <div className="filter-group filter-group-tags">
            <label>{t.tags}</label>
            <input 
              type="text" 
              placeholder={t.placeholderTags}
              value={filtros.tags}
              onChange={(e) => handleFiltroChange('tags', e.target.value)}
              className="filter-input-tags"
            />
          </div>
          
          {/* Gratuito */}
          <div className="filter-group">
            <label>{t.precio}</label>
            <select 
              value={filtros.es_gratuito} 
              onChange={(e) => handleFiltroChange('es_gratuito', e.target.value)}
            >
              <option value="">{t.todos}</option>
              <option value="true">{t.gratuitos}</option>
              <option value="false">{t.dePago}</option>
            </select>
          </div>
          
          {/* Recurrente */}
          <div className="filter-group">
            <label>{t.tipo}</label>
            <select 
              value={filtros.es_recurrente} 
              onChange={(e) => handleFiltroChange('es_recurrente', e.target.value)}
            >
              <option value="">{t.todos}</option>
              <option value="true">{t.recurrentes}</option>
              <option value="false">{t.puntuales}</option>
            </select>
          </div>
        </div>
        
        <div className="filters-row">
          {/* Fecha desde */}
          <div className="filter-group">
            <label>{t.desde}</label>
            <input 
              type="date" 
              value={filtros.fecha_desde}
              onChange={(e) => handleFiltroChange('fecha_desde', e.target.value)}
            />
          </div>
          
          {/* Fecha hasta */}
          <div className="filter-group">
            <label>{t.hasta}</label>
            <input 
              type="date" 
              value={filtros.fecha_hasta}
              onChange={(e) => handleFiltroChange('fecha_hasta', e.target.value)}
            />
          </div>
          
          {/* Botón limpiar */}
          <div className="filter-group">
            <label>&nbsp;</label>
            <button className="btn-limpiar" onClick={limpiarFiltros}>
              {t.limpiarFiltros}
            </button>
          </div>
        </div>
      </div>
      
      {/* Resumen */}
      <div className="results-summary">
        <span>
          {loading ? t.cargando : `${total} ${t.eventosEncontrados}`}
        </span>
        {offset > 0 && (
          <span className="pagination-info">
            {t.mostrando} {offset + 1} - {Math.min(offset + limit, total)}
          </span>
        )}
      </div>
      
      {/* Lista de eventos */}
      {error && <div className="error-message">{t.error}: {error}</div>}
      
      {loading ? (
        <div className="loading-spinner">{t.cargando}</div>
      ) : (
        <div className="events-grid">
          {eventos.length === 0 ? (
            <div className="no-results">
              {t.noResultados}
            </div>
          ) : (
            eventos.map((evento) => (
              <div key={evento.id} className="event-card event-card-full">
                {/* Header con categorías y tipo organizador */}
                <div className="event-card-header">
                  <div className="event-categories">
                    {(evento.categorias_slugs || []).map((slug, idx) => (
                      <span 
                        key={slug} 
                        className="category-badge"
                        style={{ backgroundColor: CATEGORIA_COLORS[slug] || '#666' }}
                      >
                        {(eventoTexto(evento, 'categorias') || [])[idx] || slug}
                      </span>
                    ))}
                  </div>
                  <div className="event-tipo">
                    <span title={getTipoOrganizadorLabel(evento.tipo_organizador)}>
                      {getTipoOrganizadorIcon(evento.tipo_organizador)}
                    </span>
                  </div>
                </div>
                
                {/* Título en idioma seleccionado */}
                <h3 className="event-card-title">{eventoTexto(evento, 'titulo')}</h3>
                
                {/* Descripción en idioma seleccionado */}
                <div className="event-card-description">
                  <span className="field-label">{t.descripcion}</span>
                  <p>{eventoTexto(evento, 'descripcion') || '—'}</p>
                </div>
                
                {/* Ubicación: CP, población, lugar, dirección */}
                <div className="event-card-block">
                  <span className="field-label">{t.ubicacion}</span>
                  <div className="event-card-details">
                    <div className="detail-item">
                      <span className="detail-icon">📮</span>
                      <span>CP {evento.cp}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-icon">📍</span>
                      <span>{evento.poblacion || '—'}</span>
                    </div>
                    {evento.lugar && (
                      <div className="detail-item">
                        <span className="detail-icon">🏢</span>
                        <span>{evento.lugar}</span>
                      </div>
                    )}
                    {evento.direccion && (
                      <div className="detail-item">
                        <span className="detail-icon">🗺️</span>
                        <span>{evento.direccion}</span>
                      </div>
                    )}
                  </div>
                </div>
                
                {/* Organizador y tipo */}
                <div className="event-card-block">
                  <span className="field-label">{t.organizador}</span>
                  <div className="event-card-details">
                    <div className="detail-item">
                      <span className="detail-icon">👤</span>
                      <span>{evento.organizador || '—'}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-icon">{getTipoOrganizadorIcon(evento.tipo_organizador)}</span>
                      <span>{getTipoOrganizadorLabel(evento.tipo_organizador)}</span>
                    </div>
                    {evento.organizador_web && (
                      <div className="detail-item">
                        <span className="detail-icon">🔗</span>
                        <a href={evento.organizador_web} target="_blank" rel="noopener noreferrer" className="link-external">{evento.organizador_web}</a>
                      </div>
                    )}
                  </div>
                </div>
                
                {/* Fechas y horarios */}
                <div className="event-card-block">
                  <span className="field-label">{t.fechasHorario}</span>
                  <div className="event-card-details">
                    <div className="detail-item">
                      <span className="detail-icon">📅</span>
                      <span>{t.inicio}: {formatearFecha(evento.fecha_inicio)}{evento.hora_inicio ? ` · ${formatearHora(evento.hora_inicio)}` : ''}</span>
                    </div>
                    {(evento.fecha_fin || evento.hora_fin) && (
                      <div className="detail-item">
                        <span className="detail-icon">📅</span>
                        <span>{t.fin}: {evento.fecha_fin ? formatearFecha(evento.fecha_fin) : '—'}{evento.hora_fin ? ` · ${formatearHora(evento.hora_fin)}` : ''}</span>
                      </div>
                    )}
                    {evento.es_recurrente && (
                      <div className="detail-item">
                        <span className="detail-icon">🔄</span>
                        <span>{t.recurrente}</span>
                      </div>
                    )}
                    {formatRecurrencia(evento.recurrencia) && (
                      <div className="detail-item detail-recurrencia">
                        <span className="detail-icon">📋</span>
                        <span>{formatRecurrencia(evento.recurrencia)}</span>
                      </div>
                    )}
                  </div>
                </div>
                
                {/* Tags en idioma seleccionado */}
                <div className="event-card-block event-card-tags">
                  <span className="field-label">{t.etiquetas}</span>
                  <div className="tags-list">
                    {formatTags(eventoTexto(evento, 'tags')).length ? formatTags(eventoTexto(evento, 'tags')).map((tag, i) => (
                      <span key={i} className="tag-hash">{tag}</span>
                    )) : <span className="tag-empty">—</span>}
                  </div>
                </div>
                
                {/* Precio e ID */}
                <div className="event-card-footer">
                  <div className="event-price">
                    {evento.es_gratuito ? (
                      <span className="price-free">{t.gratis}</span>
                    ) : (
                      <span className="price-paid">
                        {evento.precio != null ? `${Number(evento.precio).toFixed(2)}€` : t.dePago}
                      </span>
                    )}
                  </div>
                  <div className="event-badges">
                    {evento.es_recurrente && (
                      <span className="badge-recurrente" title="Evento recurrente">🔄</span>
                    )}
                  </div>
                </div>
                <div className="event-card-id">
                  <span className="field-label">ID</span>
                  <code>{evento.id}</code>
                </div>
              </div>
            ))
          )}
        </div>
      )}
      
      {/* Paginación */}
      {total > limit && (
        <div className="pagination">
          <button 
            className="btn-pagination"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - limit))}
          >
            {t.anterior}
          </button>
          <span className="pagination-text">
            {t.pagina} {Math.floor(offset / limit) + 1} {t.de} {Math.ceil(total / limit)}
          </span>
          <button 
            className="btn-pagination"
            disabled={!hasMore}
            onClick={() => setOffset(offset + limit)}
          >
            {t.siguiente}
          </button>
        </div>
      )}
    </div>
  )
}

export default EventsList
