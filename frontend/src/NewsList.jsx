import { useState, useEffect, useMemo } from 'react'

const TEXTOS_UI = {
  es: {
    tituloSeccion: 'Explorar Noticias',
    cambiarIdioma: 'Ver en catalán',
    ciudad: 'Ciudad',
    todas: 'Todas',
    limpiarFiltros: 'Limpiar filtros',
    noticiasEncontradas: 'noticias encontradas',
    mostrando: 'Mostrando',
    cargando: 'Cargando noticias...',
    noResultados: 'No se encontraron noticias con los filtros seleccionados',
    cuerpo: 'Contenido',
    ciudadLabel: 'Ciudad',
    publicacion: 'Publicación',
    etiquetas: 'Tags',
    fuente: 'Fuente',
    anterior: '← Anterior',
    siguiente: 'Siguiente →',
    pagina: 'Página',
    de: 'de',
    placeholderBuscar: 'Buscar en noticias...',
    filtros: 'Filtros',
    ocultarFiltros: 'Ocultar filtros',
    error: 'Error',
    apiNoResponde:
      'No hay respuesta de la API (¿arrancada en http://localhost:8000?). Revisa uvicorn y MySQL.'
  },
  ca: {
    tituloSeccion: 'Explorar Notícies',
    cambiarIdioma: 'Veure en castellà',
    ciudad: 'Ciutat',
    todas: 'Totes',
    limpiarFiltros: 'Netejar filtres',
    noticiasEncontradas: 'notícies trobades',
    mostrando: 'Mostrant',
    cargando: 'Carregant notícies...',
    noResultados: 'No s\'han trobat notícies amb els filtres seleccionats',
    cuerpo: 'Contingut',
    ciudadLabel: 'Ciutat',
    publicacion: 'Publicació',
    etiquetas: 'Etiquetes',
    fuente: 'Font',
    anterior: '← Anterior',
    siguiente: 'Següent →',
    pagina: 'Pàgina',
    de: 'de',
    placeholderBuscar: 'Cercar en notícies...',
    filtros: 'Filtres',
    ocultarFiltros: 'Amagar filtres',
    error: 'Error',
    apiNoResponde:
      'Sense resposta de l\'API (¿arrancada a http://localhost:8000?). Revisa uvicorn i MySQL.'
  }
}

function NewsList() {
  const [noticias, setNoticias] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [total, setTotal] = useState(0)

  const [idioma, setIdioma] = useState('es')
  const [ciudades, setCiudades] = useState([])
  const [ciudad, setCiudad] = useState('Malgrat de Mar')
  const [busquedaTexto, setBusquedaTexto] = useState('')
  const [filtrosAbiertos, setFiltrosAbiertos] = useState(false)

  const [offset, setOffset] = useState(0)
  const limit = 20

  useEffect(() => {
    fetchCiudades()
  }, [])

  useEffect(() => {
    fetchNoticias()
  }, [ciudad, offset])

  const fetchCiudades = async () => {
    try {
      const response = await fetch('/events/poblaciones')
      if (response.ok) {
        const data = await response.json()
        setCiudades(data.poblaciones || [])
      }
    } catch (err) {
      console.error('Error fetching ciudades:', err)
    }
  }

  const fetchNoticias = async () => {
    const controller = new AbortController()
    const timeoutMs = 20000
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs)
    try {
      setLoading(true)
      setError(null)

      const params = new URLSearchParams()
      params.append('limit', limit)
      params.append('offset', offset)
      if (ciudad) params.append('city', ciudad)

      const response = await fetch(`/api/v1/news?${params.toString()}`, {
        signal: controller.signal
      })

      if (!response.ok) {
        throw new Error('Error al cargar noticias')
      }

      const data = await response.json()
      setNoticias(data.data || [])
      setTotal(data.total || 0)
    } catch (err) {
      const isAbort =
        err?.name === 'AbortError' ||
        (typeof DOMException !== 'undefined' &&
          err instanceof DOMException &&
          err.name === 'AbortError')
      const mensajeApi = TEXTOS_UI[idioma]?.apiNoResponde ?? TEXTOS_UI.es.apiNoResponde
      setError(isAbort ? mensajeApi : err.message)
      console.error('Error fetching noticias:', err)
    } finally {
      window.clearTimeout(timeoutId)
      setLoading(false)
    }
  }

  const limpiarFiltros = () => {
    setCiudad('Malgrat de Mar')
    setBusquedaTexto('')
    setOffset(0)
  }

  const formatearFecha = (fecha) => {
    if (!fecha) return '—'
    const d = new Date(fecha)
    return d.toLocaleDateString(idioma === 'ca' ? 'ca-ES' : 'es-ES', {
      weekday: 'short',
      day: 'numeric',
      month: 'short',
      year: 'numeric'
    })
  }

  const t = TEXTOS_UI[idioma]
  const hasMore = offset + limit < total

  const normalizar = (texto) => {
    if (!texto) return ''
    return texto.toString().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
  }

  const calcularScore = (noticia, termino) => {
    if (!termino) return 0
    const term = normalizar(termino)
    let score = 0
    if (normalizar(noticia.titulo_es).includes(term) || normalizar(noticia.titulo_cat).includes(term)) score += 3
    if (normalizar(noticia.ciudad).includes(term)) score += 2
    if (normalizar(noticia.cuerpo_es).includes(term) || normalizar(noticia.cuerpo_cat).includes(term)) score += 1
    const tagsStr = [...(noticia.tags_es || []), ...(noticia.tags_cat || [])].join(' ')
    if (normalizar(tagsStr).includes(term)) score += 1
    return score
  }

  const noticiasOrdenadas = useMemo(() => {
    if (!busquedaTexto.trim()) return noticias
    const termino = busquedaTexto.trim()
    const conScore = noticias.map((n, idx) => ({
      noticia: n,
      score: calcularScore(n, termino),
      originalIdx: idx
    }))
    conScore.sort((a, b) => {
      if (a.score !== b.score) return b.score - a.score
      return a.originalIdx - b.originalIdx
    })
    return conScore.filter((item) => item.score > 0).map((item) => item.noticia)
  }, [noticias, busquedaTexto])

  /** Telegram/redes suelen meter \n entre emojis; los colapsamos para leer en flujo continuo. */
  const normalizarCuerpo = (texto) => {
    if (!texto) return texto
    return texto.replace(/\r\n|\r|\n/g, ' ').replace(/[ \t\f\v]+/g, ' ').trim()
  }

  const noticiaTexto = (noticia, campo) => {
    if (campo === 'titulo') {
      return idioma === 'ca' ? (noticia.titulo_cat || noticia.titulo_es) : (noticia.titulo_es || noticia.titulo_cat)
    }
    if (campo === 'cuerpo') {
      const raw =
        idioma === 'ca' ? (noticia.cuerpo_cat || noticia.cuerpo_es) : (noticia.cuerpo_es || noticia.cuerpo_cat)
      return normalizarCuerpo(raw)
    }
    if (campo === 'tags') {
      return idioma === 'ca'
        ? (noticia.tags_cat?.length ? noticia.tags_cat : noticia.tags_es)
        : (noticia.tags_es || noticia.tags_cat || [])
    }
    return null
  }

  const formatTags = (tags) => {
    if (!tags || !Array.isArray(tags)) return []
    return tags
      .map((tag) => (typeof tag === 'string' && tag.trim() ? (tag.startsWith('#') ? tag : `#${tag}`) : ''))
      .filter(Boolean)
  }

  return (
    <div className="events-container">
      <div className="events-sticky-header">
        <div className="events-header-row">
          <h2>{t.tituloSeccion}</h2>
          <div className="events-header-actions">
            <button
              type="button"
              className={`btn-filtros-toggle ${filtrosAbiertos ? 'btn-filtros-toggle-active' : ''}`}
              onClick={() => setFiltrosAbiertos((prev) => !prev)}
            >
              {filtrosAbiertos ? t.ocultarFiltros : t.filtros}
            </button>
            <button
              type="button"
              className="btn-idioma"
              onClick={() => setIdioma((prev) => (prev === 'es' ? 'ca' : 'es'))}
              title={idioma === 'es' ? t.cambiarIdioma : TEXTOS_UI.es.cambiarIdioma}
            >
              {idioma === 'es' ? 'Català' : 'Castellano'}
            </button>
          </div>
        </div>

        {filtrosAbiertos && (
          <div className="filters-panel filters-panel-compact">
            <div className="filters-row">
              <div className="filter-group">
                <label>{t.ciudad}</label>
                <select
                  value={ciudad}
                  onChange={(e) => {
                    setCiudad(e.target.value)
                    setOffset(0)
                  }}
                >
                  <option value="">{t.todas}</option>
                  {ciudades.map((c) => (
                    <option key={c.cp} value={c.nombre}>
                      {c.nombre}
                    </option>
                  ))}
                </select>
              </div>
              <div className="filter-group">
                <label>&nbsp;</label>
                <button className="btn-limpiar" onClick={limpiarFiltros}>
                  {t.limpiarFiltros}
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="search-text-wrapper">
          <input
            type="text"
            className="search-text-input"
            placeholder={t.placeholderBuscar}
            value={busquedaTexto}
            onChange={(e) => setBusquedaTexto(e.target.value)}
          />
          {busquedaTexto && (
            <button
              type="button"
              className="search-text-clear"
              onClick={() => setBusquedaTexto('')}
            >
              X
            </button>
          )}
        </div>

        <div className="results-summary">
          <span>{loading ? t.cargando : `${total} ${t.noticiasEncontradas}`}</span>
          {offset > 0 && (
            <span className="pagination-info">
              {t.mostrando} {offset + 1} - {Math.min(offset + limit, total)}
            </span>
          )}
        </div>
      </div>

      <div className="events-scroll-area">
        {error && (
          <div className="error-message">
            {t.error}: {error}
          </div>
        )}

        {loading ? (
          <div className="loading-spinner">{t.cargando}</div>
        ) : (
          <div className="events-grid">
            {noticiasOrdenadas.length === 0 ? (
              <div className="no-results">{t.noResultados}</div>
            ) : (
              noticiasOrdenadas.map((noticia) => (
                <div key={noticia.id} className="event-card event-card-full news-card">
                  {noticia.imagen_principal_url ? (
                    <div className="event-card-media">
                      <img
                        src={noticia.imagen_principal_url}
                        alt=""
                        className="event-card-thumb"
                        loading="lazy"
                      />
                    </div>
                  ) : null}

                  <div className="event-card-header">
                    <div className="news-city-badge">
                      <span className="detail-icon">📍</span>
                      {noticia.ciudad || '—'}
                    </div>
                    {noticia.fecha_publicacion && (
                      <div className="news-date-badge">
                        <span className="detail-icon">📅</span>
                        {formatearFecha(noticia.fecha_publicacion)}
                      </div>
                    )}
                  </div>

                  <h3 className="event-card-title">{noticiaTexto(noticia, 'titulo')}</h3>

                  <div className="event-card-description">
                    <span className="field-label">{t.cuerpo}</span>
                    <p>{noticiaTexto(noticia, 'cuerpo') || '—'}</p>
                  </div>

                  <div className="event-card-block event-card-tags">
                    <span className="field-label">{t.etiquetas}</span>
                    <div className="tags-list">
                      {formatTags(noticiaTexto(noticia, 'tags')).length ? (
                        formatTags(noticiaTexto(noticia, 'tags')).map((tag, i) => (
                          <span key={i} className="tag-hash">
                            {tag}
                          </span>
                        ))
                      ) : (
                        <span className="tag-empty">—</span>
                      )}
                    </div>
                  </div>

                  {noticia.fuente_url_original && (
                    <div className="event-card-block">
                      <span className="field-label">{t.fuente}</span>
                      <div className="event-card-details">
                        <div className="detail-item">
                          <span className="detail-icon">🔗</span>
                          <a
                            href={noticia.fuente_url_original}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="link-external"
                          >
                            {noticia.fuente_url_original}
                          </a>
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="event-card-id">
                    <span className="field-label">ID</span>
                    <code>{noticia.id}</code>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

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
            <button className="btn-pagination" disabled={!hasMore} onClick={() => setOffset(offset + limit)}>
              {t.siguiente}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default NewsList
