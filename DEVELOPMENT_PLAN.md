# Plan de Desarrollo

## Proposito

Este documento mantiene el backlog de mejoras del sistema Update-WEB. Sirve
para priorizar el trabajo futuro y complementar `PROJECT_CONTEXT.md`, que
registra el estado tecnico y las decisiones ya aplicadas.

## Como usar este plan

- Actualizar el estado al iniciar o completar una mejora importante.
- Registrar nuevas ideas con objetivo, alcance y criterio de aceptacion.
- Mantener las tareas pequenas dentro de la mejora principal relacionada.

Estados: propuesta, planificada, en curso, validada o descartada.

## Prioridad Actual

### 1. Historial Operativo Unificado por Gateway

- Estado: planificada.
- Prioridad: alta.
- Objetivo: mostrar en un solo lugar la historia tecnica de cada gateway para
  facilitar diagnostico, seguimiento y soporte.
- Alcance:
  - Unificar actualizaciones, reinstalaciones y configuraciones de Relay
    LPWAN.
  - Incluir escaneos manuales y programados, con resultado y duracion.
  - Registrar incidencias de Mono, falta de espacio y tarjeta SD congelada,
    incluyendo cuando se detectan y cuando se resuelven.
  - Mostrar fecha, origen (manual o automatico), resultado y un resumen breve
    de cada evento.
  - Incorporar la linea de tiempo en el dossier de unidad/gateway.
- Criterios de aceptacion:
  - Desde una unidad se puede consultar el historial de cada gateway sin
    revisar pantallas distintas.
  - Los eventos se presentan con texto traducido a espanol y portugues.
  - El historial permite identificar la ultima accion correcta y el ultimo
    problema conocido.
- Riesgos y consideraciones:
  - Requiere una migracion de SQLite y normalizar registros historicos ya
    existentes.
  - Debe conservar datos anteriores y evitar mensajes tecnicos extensos para
    usuarios operativos.

## Proximas Mejoras

### 2. Alertas Operativas

- Estado: en curso.
- Prioridad: media.
- Objetivo: avisar de forma visible cuando un gateway necesita atencion.
- Avance actual: el escaneo nocturno identifica fallos repetidos tras dos
  ejecuciones consecutivas y muestra recuperaciones, cambios de version y de
  Relay. Hace un reintento controlado de fallos al finalizar y una revision de
  recuperacion a las 13:30; los lotes guardan sus metricas. Los gateways en
  mantenimiento se excluyen de estas alertas.
- Alcance pendiente: alertas para incidencias de Mono, tarjeta congelada y
  actualizacion pendiente durante varios escaneos.
- Criterio de aceptacion: el inventario y los informes muestran las alertas
  pendientes con acceso directo a los equipos afectados.

### 3. Lista Exportable de Acciones Pendientes

- Estado: propuesta.
- Prioridad: media.
- Objetivo: generar una lista operativa para visitas de campo y soporte.
- Alcance inicial: filtros por cliente, unidad, tipo de incidencia y estado;
  exportacion a Excel y PDF legibles.
- Criterio de aceptacion: la lista identifica IP, cliente, unidad, problema,
  ultima deteccion y accion recomendada.

### 4. Configuracion Visual de Automatizaciones

- Estado: propuesta.
- Prioridad: baja.
- Objetivo: administrar desde la interfaz los horarios de importacion de TXT
  y escaneo programado.
- Alcance inicial: hora, dias de ejecucion, tamano de lote y pausa entre lotes,
  con valores seguros por defecto.
- Criterio de aceptacion: los cambios se validan, quedan registrados y se
  aplican sin editar archivos de configuracion manualmente.

### 5. Auditoria de Acciones

- Estado: propuesta.
- Prioridad: baja.
- Objetivo: saber quien inicio una actualizacion, configuracion o escaneo
  manual cuando el sistema tenga mas de un usuario.
- Alcance inicial: usuario, fecha, accion, IPs involucradas y resultado.
- Criterio de aceptacion: cada accion manual relevante se puede rastrear desde
  el historial operativo.

## Revision

- Ultima actualizacion: 2026-08-24.
- Proxima revision recomendada: despues de validar los informes del escaneo
  automatico del fin de semana.
