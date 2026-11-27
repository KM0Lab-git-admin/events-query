import { useState } from 'react';

export default function AnalysisView({ analisis }) {
  const [expandedEvents, setExpandedEvents] = useState(new Set());

  console.log('DEBUG AnalysisView: Recibiendo analisis =', analisis)
  console.log('DEBUG AnalysisView: analisis.length =', analisis?.length)

  if (!analisis || analisis.length === 0) {
    return (
      <div className="analysis-view">
        <p className="no-analysis">No hay análisis disponible. Activa el modo debug para ver el análisis detallado.</p>
      </div>
    );
  }

  const toggleEvent = (eventoId) => {
    const newExpanded = new Set(expandedEvents);
    if (newExpanded.has(eventoId)) {
      newExpanded.delete(eventoId);
    } else {
      newExpanded.add(eventoId);
    }
    setExpandedEvents(newExpanded);
  };

  const getSeverityColor = (severidad) => {
    switch (severidad) {
      case 'CRÍTICA': return '#dc2626';
      case 'ALTA': return '#ea580c';
      case 'MEDIA': return '#f59e0b';
      case 'BAJA': return '#84cc16';
      default: return '#6b7280';
    }
  };

  const getPriorityColor = (prioridad) => {
    switch (prioridad) {
      case 'CRÍTICA': return '#dc2626';
      case 'ALTA': return '#ea580c';
      case 'MEDIA': return '#f59e0b';
      case 'BAJA': return '#84cc16';
      default: return '#6b7280';
    }
  };

  return (
    <div className="analysis-view">
      <h2>🔬 Análisis Detallado de Similitud</h2>
      <p className="analysis-description">
        Análisis de los primeros {analisis.length} eventos para entender por qué pasan o no el filtro semántico.
      </p>

      <div className="events-analysis-list">
        {[...analisis].sort((a, b) => b.score_global - a.score_global).map((evento) => {
          const isExpanded = expandedEvents.has(evento.evento_id);
          const passFilter = evento.pasa_filtro;

          return (
            <div key={evento.evento_id} className={`event-analysis-card ${passFilter ? 'pass' : 'fail'}`}>
              {/* Header */}
              <div className="event-header" onClick={() => toggleEvent(evento.evento_id)}>
                <div className="event-title-section">
                  <span className="event-status">{passFilter ? '✅' : '❌'}</span>
                  <div>
                    <h3>{evento.titulo || 'Sin título'}</h3>
                    <p className="event-id">ID: {evento.evento_id}</p>
                  </div>
                </div>
                <div className="event-score-section">
                  <div className="score-badge" style={{ 
                    backgroundColor: passFilter ? '#10b981' : '#ef4444',
                    color: 'white'
                  }}>
                    Score: {evento.score_global}
                  </div>
                  <div className="threshold-info">
                    Umbral: {evento.umbral}
                  </div>
                  <button className="expand-btn">
                    {isExpanded ? '▼' : '▶'}
                  </button>
                </div>
              </div>

              {/* Expanded Content - Orden: Categoría (más relevante), Tags, Descripción */}
              {isExpanded && (
                <div className="event-details">
                  {/* Similitud por Categoría de producto (primero: más relevante que tags) */}
                  {evento.similitud_categoria && (
                    <div className="analysis-section">
                      <h4>📂 Similitud por Categoría</h4>
                      <div className="category-similarity">
                        <span className="category-name">{evento.similitud_categoria.categoria}</span>
                        <div className="similarity-bar-container">
                          <div 
                            className="similarity-bar" 
                            style={{ 
                              width: `${evento.similitud_categoria.similitud * 100}%`,
                              backgroundColor: evento.similitud_categoria.similitud > 0.3 ? '#10b981' : '#ef4444'
                            }}
                          />
                        </div>
                        <span className="similarity-value">{evento.similitud_categoria.similitud}</span>
                      </div>
                      {evento.similitud_categoria.similitud < 0.3 && (
                        <p className="warning-text">⚠️ Categoría poco relevante para la búsqueda</p>
                      )}
                      {evento.diagnostico?.impacto_categoria && (
                        <p className="impacto-categoria">
                          Impacto: {evento.diagnostico.impacto_categoria.aporta}
                        </p>
                      )}
                    </div>
                  )}

                  {/* Similitud por Tag */}
                  {evento.similitud_por_tag && evento.similitud_por_tag.length > 0 && (
                    <div className="analysis-section">
                      <h4>📊 Similitud por Tag</h4>
                      <div className="tags-similarity">
                        {evento.similitud_por_tag.map((tagInfo, idx) => {
                          const percentage = tagInfo.similitud * 100;
                          const isRelevant = tagInfo.similitud > 0.4;
                          
                          return (
                            <div key={idx} className="tag-similarity-row">
                              <span className="tag-name">{tagInfo.tag}</span>
                              <div className="similarity-bar-container">
                                <div 
                                  className="similarity-bar" 
                                  style={{ 
                                    width: `${percentage}%`,
                                    backgroundColor: isRelevant ? '#10b981' : '#6b7280'
                                  }}
                                />
                              </div>
                              <span className={`similarity-value ${isRelevant ? 'relevant' : ''}`}>
                                {tagInfo.similitud} {isRelevant && '⭐'}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Similitud por Descripción */}
                  {evento.similitud_descripcion !== null && (
                    <div className="analysis-section">
                      <h4>📝 Similitud por Descripción</h4>
                      <div className="description-similarity">
                        <div className="similarity-bar-container">
                          <div 
                            className="similarity-bar" 
                            style={{ 
                              width: `${evento.similitud_descripcion * 100}%`,
                              backgroundColor: evento.similitud_descripcion > 0.3 ? '#10b981' : '#6b7280'
                            }}
                          />
                        </div>
                        <span className="similarity-value">{evento.similitud_descripcion}</span>
                      </div>
                    </div>
                  )}

                  {/* Diagnóstico */}
                  {evento.diagnostico && (
                    <div className="analysis-section diagnostico-section">
                      <h4>🔍 Diagnóstico</h4>
                      
                      {/* Problemas */}
                      {evento.diagnostico.problemas && evento.diagnostico.problemas.length > 0 && (
                        <div className="problemas-list">
                          <h5>⚠️ Problemas Detectados:</h5>
                          {evento.diagnostico.problemas.map((problema, idx) => (
                            <div key={idx} className="problema-item" style={{ borderLeftColor: getSeverityColor(problema.severidad) }}>
                              <div className="problema-header">
                                <span className="problema-tipo">{problema.tipo}</span>
                                <span className="problema-severidad" style={{ backgroundColor: getSeverityColor(problema.severidad) }}>
                                  {problema.severidad}
                                </span>
                              </div>
                              <p className="problema-descripcion">{problema.descripcion}</p>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Soluciones */}
                      {evento.diagnostico.soluciones && evento.diagnostico.soluciones.length > 0 && (
                        <div className="soluciones-list">
                          <h5>💡 Soluciones Propuestas:</h5>
                          {evento.diagnostico.soluciones.map((solucion, idx) => (
                            <div key={idx} className="solucion-item" style={{ borderLeftColor: getPriorityColor(solucion.prioridad) }}>
                              <div className="solucion-header">
                                <span className="solucion-prioridad" style={{ backgroundColor: getPriorityColor(solucion.prioridad) }}>
                                  {solucion.prioridad}
                                </span>
                                <span className="solucion-tipo">{solucion.tipo}</span>
                                <span className="solucion-impacto">{solucion.impacto_estimado}</span>
                              </div>
                              <p className="solucion-accion">{solucion.accion}</p>
                              {solucion.categoria_sugerida && (
                                <p className="solucion-detalle">
                                  <strong>Cambiar:</strong> {solucion.categoria_actual} → {solucion.categoria_sugerida}
                                </p>
                              )}
                              {solucion.tags_sugeridos && (
                                <p className="solucion-detalle">
                                  <strong>Tags:</strong> {solucion.tags_sugeridos.join(', ')}
                                </p>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Score Estimado */}
                      {evento.diagnostico.score_estimado_con_mejoras && (
                        <div className="score-estimado">
                          <h5>📈 Score Estimado con Mejoras:</h5>
                          <div className="score-comparison">
                            <div className="score-item">
                              <span className="score-label">Actual:</span>
                              <span className="score-value current">{evento.score_global}</span>
                            </div>
                            <span className="score-arrow">→</span>
                            <div className="score-item">
                              <span className="score-label">Estimado:</span>
                              <span className="score-value estimated">{evento.diagnostico.score_estimado_con_mejoras}</span>
                            </div>
                            {evento.diagnostico.score_estimado_con_mejoras >= evento.umbral && (
                              <span className="score-pass">✅ Pasaría el filtro</span>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
