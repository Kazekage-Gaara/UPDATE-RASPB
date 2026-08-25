# Base de Conocimiento del Proyecto

## Proposito

Este documento conserva aprendizajes tecnicos y decisiones reutilizables de
Update-WEB. No sustituye `PROJECT_CONTEXT.md` (estado y continuidad) ni
`DEVELOPMENT_PLAN.md` (trabajo futuro).

Agregar una entrada cuando una prueba, incidente o correccion revele un patron
que pueda ahorrar diagnosticos futuros. Incluir solo informacion validada y no
guardar contrasenas, tokens, llaves ni datos sensibles.

## Arquitectura y Operacion

- La aplicacion usa FastAPI para la interfaz/API, Celery para tareas de fondo,
  Redis como cola y SQLite para datos operativos.
- Los gateways ejecutan `solinfnet.exe` con Mono. Sus estados no siempre se
  pueden obtener por HTTP si el servicio no inicio correctamente.
- La aplicacion se ejecuta en Docker. Si se modifican `backend/main.py` o la
  interfaz servida por la aplicacion, reconstruir el servicio `app`; si se
  modifican tareas de Celery, reconstruir tambien `worker`.
- La referencia horaria comun es `America/Sao_Paulo`. Las fechas del backend
  deben incluir offset y la interfaz debe usar el formateador centralizado, no
  el reloj local de cada PC.

## Inventario y Datos de Clientes

- Los TXT de clientes y unidades se importan al iniciar la aplicacion y todos
  los dias a las 04:00, antes del escaneo automatico.
- Despues de cada importacion, los gateways ya existentes se reasocian de
  inmediato por red y tercer octeto. Esto actualiza cliente/unidad sin esperar
  al siguiente escaneo.
- Un IP visible no siempre es un gateway: las subredes de cliente son solo
  referencias y no deben abrir el panel web `:8085`.
- Los IPs reales de gateway pueden abrirse como `http://IP:8085` en una pestana
  nueva, siempre que se validen como IPv4 antes de generar el enlace.

## Escaneo y Actualizacion

- El escaneo programado ocurre a las 04:30. Solo revisa conectividad, version,
  Relay, GPS y estado; no actualiza ni reinicia gateways.
- El proceso automatico usa lotes pequenos y pausas para reducir carga en la
  red. Cada ejecucion guarda inicio, fin, duracion y resultado por gateway en
  SQLite.
- Cada resultado conserva una foto de version y Relay para compararse con el
  escaneo anterior. Los cambios relevantes son problema nuevo, recuperacion,
  cambio de version y cambio de Relay.
- Un gateway genera alerta tras dos fallos consecutivos (`OFFLINE`, `ERROR` o
  `TIMEOUT`). El umbral se configura con `SCHEDULED_SCAN_FAILURE_ALERT_THRESHOLD`.
- El mantenimiento programado se guarda por gateway con un motivo opcional.
  El escaneo nocturno lo omite y no cuenta fallos, pero no bloquea escaneos,
  actualizaciones ni configuraciones manuales.
- Al finalizar el escaneo nocturno, los resultados `OFFLINE`, `ERROR` y
  `TIMEOUT` se intentan una vez mas despues de una pausa configurable. Ese
  reintento se conserva como ejecucion separada y enlazada al escaneo original.
- A las 13:30 se ejecuta una revision de recuperacion: consulta solo los fallos
  que persistieron tras la ronda nocturna, sin actualizar ni reiniciar. El
  horario se configura con `SCHEDULED_RECHECK_HOUR` y
  `SCHEDULED_RECHECK_MINUTE`.
- Las metricas por lote se guardan en `scheduled_scan_batches`; permiten ajustar
  tamano de lote, pausas y horario usando duracion y errores reales.
- Los gateways `OFFLINE` o `ERROR` pueden requerir una actualizacion manual,
  aunque su ultima version guardada sea la objetivo. Por eso sus checkboxes
  individuales se mantienen disponibles.
- La seleccion global de actualizacion no debe incluir automaticamente
  gateways `OFFLINE` o `ERROR` con version objetivo ya confirmada. Debe
  priorizar pendientes, versiones desconocidas o versiones anteriores.
- Las tareas de actualizacion deben tratar los resultados internos terminales
  como completados, aunque Celery los transporte con estado tecnico `SUCCESS`,
  para que el progreso de la interfaz no quede girando indefinidamente.

## Versiones, Mono y Espacio

- La version de SolinfNet debe extraerse como numero con formato de version.
  Banners SSH o mensajes de instalacion no pueden guardarse como version.
- Antes de consultar la version conviene limpiar archivos `mono_crash`. Cuando
  el almacenamiento esta lleno, SolinfNet puede no arrancar y la consulta de
  version falla aunque el gateway siga siendo accesible por SSH.
- Los diagnosticos de Mono/espacio deben distinguir problemas activos de una
  limpieza que ya los resolvio. Los contadores operativos muestran gateways
  afectados, no el numero acumulado de eventos.
- Una tarjeta SD congelada es distinta de un gateway offline: puede responder
  y funcionar hasta reiniciar. Debe mostrarse como `FROZEN_CARD` o
  "Necesario substituir", no como offline.
- La verificacion de tarjeta congelada requiere escribir un marcador,
  reiniciar realmente el gateway y comprobar que el marcador persiste. Un
  simple reinicio de servicio no valida persistencia.
- Los gateways con estado `FROZEN_CARD` se excluyen de escaneos automaticos,
  reintentos y revisiones de recuperacion. Solo una accion manual puede volver
  a evaluarlos y cambiar su estado operativo.
- Los escaneos manuales normales tambien deben conservar `FROZEN_CARD`: la SD
  puede responder por red y aparentar estar sana. Solo una reinstalacion forzada
  debe volver a comprobar la persistencia tras reemplazar la tarjeta.

## Relay LPWAN y GPS

- No usar conteos o texto libre de `grep` para detectar Relay: los banners SSH
  pueden contaminar la salida. Usar marcadores explicitos como
  `RELAY_PRESENT` y `RELAY_ABSENT`.
- Si una consulta no puede confirmar Relay, conservar el ultimo valor conocido
  en vez de sobrescribirlo con un falso negativo.
- Las coordenadas se leen primero desde `SolinfNet.conf`. Si GPS esta activo y
  faltan coordenadas, usar una muestra corta de `/dev/ttyGPS` y aceptar solo
  sentencias NMEA con fix valido (`GPRMC`, `GPGGA` o `GPGLL`).
- La lectura de `/dev/ttyGPS` debe terminar al encontrar la primera sentencia
  valida; dejar un `cat` abierto bloquea la sesion SSH y hace fallar el flujo.

## Interfaz y Traducciones

- Cualquier texto que llegue del backend, historico o tareas en segundo plano
  debe pasar por la capa de traduccion ES/PT-BR antes de mostrarse.
- Si un bloque dinamico se genera con JavaScript, al cambiar de idioma hay que
  volver a renderizarlo o recargar sus datos de inmediato. Los atributos
  `data-i18n` solo actualizan contenido estatico ya presente en el DOM.
- Los valores internos como `FROZEN_CARD` no deben aparecer como texto crudo
  para operadores. Mostrar etiquetas localizadas y mensajes breves.
- Los graficos y exportaciones PDF deben usar colores con contraste suficiente
  en fondo claro. No confiar en el estilo oscuro de la interfaz para PDF.
- Los mapas de dossier de unidad deben incluir solo gateways de esa unidad; el
  dossier de cliente puede incluir todas sus unidades. Mantener siempre una
  opcion de vista ampliada para ubicaciones de campo.
- Para acciones globales que se necesitan durante paginas largas, usar una
  navegacion `sticky` con fondo opaco y z-index propio. En movil, el contenedor
  de pestañas debe permitir scroll horizontal en vez de comprimir etiquetas.
- Los KPIs extensos pueden conservarse en una franja fija compacta al salir de
  pantalla. Debe alimentarse del mismo snapshot de datos, ocultarse fuera de
  su pestaña y excluirse expresamente de la vista de impresion.
- Para recuperar rapidamente el encabezado en paginas largas, usar un boton
  fijo de regreso al inicio con aparicion condicionada por el desplazamiento,
  texto localizado y exclusion de la impresion.

## Verificacion Reutilizable

- Antes de editar: revisar `git status`, rama y remoto; no sobrescribir cambios
  existentes.
- Despues de cambios de texto o JavaScript: ejecutar `git diff --check` y
  revisar el diff. Para Python, usar al menos `python3 -m compileall -q backend`
  cuando aplique.
- Para cambios Docker: usar `docker compose config --quiet`, reconstruir solo
  los servicios afectados y comprobar que queden saludables.
- No hacer commit ni push sin solicitud explicita del usuario. Antes de
  preparar un commit, revisar `.gitignore` y agregar rutas especificas.

## Referencias

- Estado y cronologia: `PROJECT_CONTEXT.md`.
- Mejoras futuras: `DEVELOPMENT_PLAN.md`.
- Configuracion: `backend/config.py`.
- Escaneos y actualizaciones: `backend/tasks.py`.
- Programacion y API: `backend/main.py`.
