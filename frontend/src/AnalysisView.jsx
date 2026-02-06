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

              {/* Expanded Content */}
              {isExpanded && (
                <div className="event-details">
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

                  {/* Similitud por Categoría */}
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

      <style jsx>{`
        .analysis-view {
          margin-top: 30px;
          padding: 20px;
          background: white;
          border-radius: 8px;
          box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        .analysis-view h2 {
          margin: 0 0 10px 0;
          color: #1f2937;
        }

        .analysis-description {
          color: #6b7280;
          margin-bottom: 20px;
        }

        .no-analysis {
          text-align: center;
          color: #9ca3af;
          padding: 40px;
        }

        .events-analysis-list {
          display: flex;
          flex-direction: column;
          gap: 15px;
        }

        .event-analysis-card {
          border: 2px solid #e5e7eb;
          border-radius: 8px;
          overflow: hidden;
          transition: all 0.2s;
        }

        .event-analysis-card.pass {
          border-color: #10b981;
        }

        .event-analysis-card.fail {
          border-color: #ef4444;
        }

        .event-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 15px;
          background: #f9fafb;
          cursor: pointer;
          transition: background 0.2s;
        }

        .event-header:hover {
          background: #f3f4f6;
        }

        .event-title-section {
          display: flex;
          align-items: center;
          gap: 15px;
          flex: 1;
        }

        .event-status {
          font-size: 24px;
        }

        .event-title-section h3 {
          margin: 0;
          color: #1f2937;
          font-size: 16px;
        }

        .event-id {
          margin: 5px 0 0 0;
          color: #9ca3af;
          font-size: 12px;
        }

        .event-score-section {
          display: flex;
          align-items: center;
          gap: 15px;
        }

        .score-badge {
          padding: 6px 12px;
          border-radius: 4px;
          font-weight: 600;
          font-size: 14px;
        }

        .threshold-info {
          color: #6b7280;
          font-size: 14px;
        }

        .expand-btn {
          background: none;
          border: none;
          font-size: 18px;
          cursor: pointer;
          color: #6b7280;
        }

        .event-details {
          padding: 20px;
          background: white;
          border-top: 1px solid #e5e7eb;
        }

        .analysis-section {
          margin-bottom: 25px;
        }

        .analysis-section h4 {
          margin: 0 0 15px 0;
          color: #374151;
          font-size: 15px;
        }

        .tags-similarity {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }

        .tag-similarity-row,
        .category-similarity,
        .description-similarity {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .tag-name,
        .category-name {
          min-width: 120px;
          font-weight: 500;
          color: #4b5563;
        }

        .similarity-bar-container {
          flex: 1;
          height: 20px;
          background: #e5e7eb;
          border-radius: 4px;
          overflow: hidden;
        }

        .similarity-bar {
          height: 100%;
          transition: width 0.3s;
        }

        .similarity-value {
          min-width: 60px;
          text-align: right;
          font-weight: 600;
          color: #6b7280;
        }

        .similarity-value.relevant {
          color: #10b981;
        }

        .warning-text {
          margin: 10px 0 0 0;
          color: #f59e0b;
          font-size: 14px;
        }

        .diagnostico-section {
          background: #f9fafb;
          padding: 15px;
          border-radius: 6px;
        }

        .diagnostico-section h5 {
          margin: 0 0 15px 0;
          color: #1f2937;
          font-size: 14px;
        }

        .problemas-list,
        .soluciones-list {
          margin-bottom: 20px;
        }

        .problema-item,
        .solucion-item {
          background: white;
          border-left: 4px solid;
          padding: 12px;
          margin-bottom: 10px;
          border-radius: 4px;
        }

        .problema-header,
        .solucion-header {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 8px;
        }

        .problema-tipo,
        .solucion-tipo {
          font-weight: 600;
          color: #374151;
          font-size: 13px;
        }

        .problema-severidad,
        .solucion-prioridad {
          padding: 2px 8px;
          border-radius: 3px;
          color: white;
          font-size: 11px;
          font-weight: 600;
        }

        .solucion-impacto {
          margin-left: auto;
          color: #10b981;
          font-weight: 600;
        }

        .problema-descripcion,
        .solucion-accion {
          margin: 0;
          color: #4b5563;
          font-size: 14px;
        }

        .solucion-detalle {
          margin: 8px 0 0 0;
          color: #6b7280;
          font-size: 13px;
        }

        .score-estimado {
          background: white;
          padding: 15px;
          border-radius: 6px;
          border: 2px solid #10b981;
        }

        .score-estimado h5 {
          margin: 0 0 15px 0;
        }

        .score-comparison {
          display: flex;
          align-items: center;
          gap: 15px;
        }

        .score-item {
          display: flex;
          flex-direction: column;
          align-items: center;
        }

        .score-label {
          font-size: 12px;
          color: #6b7280;
          margin-bottom: 5px;
        }

        .score-value {
          font-size: 24px;
          font-weight: 700;
        }

        .score-value.current {
          color: #ef4444;
        }

        .score-value.estimated {
          color: #10b981;
        }

        .score-arrow {
          font-size: 24px;
          color: #6b7280;
        }

        .score-pass {
          margin-left: auto;
          color: #10b981;
          font-weight: 600;
        }
      `}</style>
    </div>
  );
}
