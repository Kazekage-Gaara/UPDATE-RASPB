# Instrucciones de trabajo para este proyecto

Estoy trabajando en este proyecto desde dos computadoras diferentes:

- Una computadora en el trabajo.
- Una laptop en casa.

En ambas utilizo Visual Studio Code con Remote SSH para conectarme al mismo servidor Ubuntu remoto. Por lo tanto, los archivos del proyecto están almacenados en una única carpeta del servidor y no existen dos copias locales independientes.

El repositorio ya está conectado a GitHub.

## Objetivo

Ayúdame a mantener el proyecto organizado, documentado y respaldado en GitHub, de manera que pueda continuar trabajando desde cualquiera de las dos computadoras sin perder cambios ni contexto.

## Reglas generales

1. Antes de modificar archivos, revisa:

```bash
git status
git branch --show-current
git remote -v
```

2. Comprueba si existen cambios sin guardar de una sesión anterior.

3. No ejecutes automáticamente comandos destructivos como:

```bash
git reset --hard
git clean -fd
git checkout -- .
git restore .
git push --force
```

Solo podrás utilizar alguno de esos comandos después de explicarme exactamente qué se perdería y recibir mi autorización explícita.

4. Nunca elimines ni sobrescribas cambios existentes que no hayan sido creados durante la tarea actual.

5. Antes de modificar un archivo, analiza su función y sus dependencias.

6. Realiza cambios pequeños, claros y fáciles de revisar.

7. No cambies archivos ajenos a la tarea solicitada.

8. No subas a GitHub información sensible, incluyendo:

- Contraseñas.
- Tokens.
- Claves API.
- Llaves SSH.
- Certificados privados.
- Archivos `.env`.
- Credenciales.
- Direcciones o configuraciones internas sensibles.
- Copias de bases de datos.
- Logs que puedan contener datos privados.

9. Antes de hacer `git add`, revisa el archivo `.gitignore` y confirma que no se incluirán secretos, archivos temporales, dependencias, logs o archivos generados automáticamente.

10. No hagas `git push` ni publiques cambios sin mostrarme primero un resumen de lo que se modificó, salvo que yo te indique explícitamente que puedes completar todo el proceso automáticamente.

## Al comenzar una sesión

Ejecuta o revisa:

```bash
git status
git log --oneline -5
git branch --show-current
```

Si el repositorio tiene cambios pendientes, informa:

- Qué archivos están modificados.
- Qué archivos son nuevos.
- Qué cambios parecen pertenecer a una sesión anterior.
- Si existe algún riesgo de conflicto o pérdida.

Como ambas computadoras trabajan sobre el mismo servidor remoto, no asumas que es necesario ejecutar `git pull` en cada cambio de computadora.

Ejecuta `git pull` solamente cuando sea necesario sincronizar el servidor con cambios que existan en GitHub y no estén en el servidor.

Antes de ejecutar `git pull`, comprueba que no haya cambios locales sin guardar que puedan producir conflictos.

## Durante una tarea

Antes de editar:

1. Lee los archivos relevantes.
2. Explícame brevemente qué planeas cambiar.
3. Identifica posibles riesgos o dependencias.
4. Mantén la compatibilidad con el funcionamiento actual del proyecto.
5. No agregues dependencias nuevas sin justificarlo.
6. No modifiques configuraciones de producción innecesariamente.

Después de editar:

1. Revisa los cambios con:

```bash
git diff
git status
```

2. Ejecuta las pruebas, validaciones o comprobaciones disponibles.

3. Informa claramente:

- Archivos modificados.
- Qué se cambió.
- Por qué se cambió.
- Qué pruebas se ejecutaron.
- Qué no pudo comprobarse.
- Posibles riesgos o tareas pendientes.

## Commits

Cuando yo autorice guardar los cambios:

1. Incluye únicamente los archivos relacionados con la tarea.
2. Evita utilizar `git add .` sin revisar antes todos los archivos.
3. Prefiere agregar archivos explícitamente:

```bash
git add ruta/archivo1 ruta/archivo2
```

4. Crea un commit con un mensaje claro y descriptivo.

Ejemplos:

```bash
git commit -m "Corrige validación de conexión del gateway"
```

```bash
git commit -m "Agrega documentación del despliegue"
```

```bash
git commit -m "Evita duplicados en la configuración de cron"
```

5. Antes del commit, muéstrame:

```bash
git diff --cached
```

6. Después del commit, confirma:

```bash
git status
git log -1 --oneline
```

## Push a GitHub

Solo ejecuta:

```bash
git push
```

después de:

- Verificar que el commit se creó correctamente.
- Confirmar que no contiene secretos.
- Confirmar que las pruebas relevantes pasaron.
- Mostrarme un resumen final.
- Recibir mi autorización, excepto cuando yo haya pedido explícitamente “haz commit y push”.

Nunca utilices `git push --force` sin autorización explícita.

## Archivo de continuidad

Mantén un archivo llamado:

```text
PROJECT_CONTEXT.md
```

Este archivo debe servir para continuar el trabajo desde una sesión nueva de Codex.

Debe contener solamente información útil y no sensible:

```markdown
# Contexto del proyecto

## Objetivo del proyecto

Descripción breve del objetivo general.

## Estado actual

Qué partes están funcionando y cuál es el estado actual.

## Últimos cambios

- 2026-08-13: Se mejoro la exportacion de reportes: el PDF prepara los graficos con una paleta de alto contraste y fondo blanco sin gradientes antes de imprimir; el Excel ahora incorpora pestaña de resumen con grafico, encabezado, filtros, filas congeladas, estados traducidos y formato de lectura.

Resumen de los cambios recientes importantes.

## Trabajo pendiente

Lista de tareas pendientes.

## Decisiones técnicas

Decisiones relevantes y motivos.

## Archivos principales

Descripción de los archivos o directorios más importantes.

## Cómo ejecutar o probar

Comandos necesarios para iniciar, validar o probar el proyecto.

## Problemas conocidos

Errores, limitaciones o riesgos conocidos.

## Próximo paso recomendado

La siguiente tarea lógica que debería realizarse.
```

Actualiza `PROJECT_CONTEXT.md` después de cambios importantes, pero no incluyas contraseñas, tokens, IP privadas sensibles ni credenciales.

Al comenzar una conversación nueva, lee primero:

```text
PROJECT_CONTEXT.md
```

y después revisa:

```bash
git status
git log --oneline -5
```

## Final de cada sesión

Cuando yo diga que terminé de trabajar, realiza una revisión final y dime:

1. Si hay archivos sin guardar en Git.
2. Si hay archivos nuevos sin seguimiento.
3. Si existen cambios todavía sin commit.
4. Cuál fue el último commit.
5. Si el commit ya fue enviado a GitHub.
6. Qué queda pendiente.
7. Qué debería leer o hacer Codex en la próxima sesión.

No cierres la sesión dejando cambios importantes sin advertírmelo.

## Comportamiento esperado

Actúa como asistente técnico del repositorio, no como propietario autónomo del proyecto.

Prioriza siempre:

1. No perder cambios.
2. No exponer secretos.
3. Mantener el proyecto funcionando.
4. Crear cambios pequeños y revisables.
5. Mantener Git y la documentación actualizados.
6. Facilitar la continuación desde cualquier computadora conectada al servidor.

## Registro de continuidad

- 2026-08-08: Se agrego accion individual `Reinstalar` en `backend/index.html` para repetir el proceso aunque el gateway ya este en version objetivo. El boton llama `/api/update` con `force: true` sin hacer escaneo previo, para casos donde la version dice 6.5 pero archivos/crontab/Relay quedaron incompletos por falta de espacio. `backend/main.py` acepta y pasa `force` a `update_gateway`; `backend/tasks.py` acepta el argumento y registra `REINSTALACION FORZADA` en logs. Se reconstruyeron `app` y `worker`; se verifico HTML servido, firma del worker y servicios saludables. No se ejecuto la reinstalacion real de `220.119.1.105` desde Codex.
- 2026-08-08: Se diagnostico `220.119.1.105`: tenia 4 bloques `Hardware = RadioLocal` y 0 `Hardware = Relay`; la configuracion Relay habia fallado porque `/` estaba al 100% por miles de archivos `/mono_crash*` generados por Mono (~14029 archivos, ~5758 MB). `limpar_logs.sh` ya borraba esos archivos, pero durante update solo se copiaba/programaba para reboot y no se ejecutaba antes de manipular `SolinfNet.conf`. Se agrego `cleanup_runtime_artifacts()` en `backend/tasks.py` para borrar `/mono_crash*` y temporales conocidos antes de copiar/configurar, abortar Relay si sigue sin espacio, y mostrar advertencia si Relay falla en vez de ocultarlo. Se reconstruyo `worker` y se verifico saludable.
- 2026-08-08: Se reforzo la limpieza del flujo RB /24 despues de actualizar desde inventario. La condicion anterior dependia de `lastDiscoveredGatewayStatus` y podia no activarse aunque la lista siguiera visible. Ahora `updateSelected()` usa `hasMultipleOperationState()` para detectar si hay RB, lista o resultados visibles y, al completar el monitoreo, limpia esos campos con `clearMultipleOperationState()`. Se reconstruyo `app` y se verifico HTML servido, servicios saludables y simulacion de la nueva condicion.
- 2026-08-08: Se completo la limpieza del flujo RB /24 cuando la actualizacion se lanza desde la tabla de inventario: `updateSelected()` ahora detecta si las IP seleccionadas pertenecen al ultimo descubrimiento por RB y, al terminar el monitoreo de esas tareas, limpia textarea de IPs, campo RB/subred, contador y panel de resultados. Se reconstruyo `app` y se verifico HTML servido, servicios saludables y simulacion de seleccion desde inventario.
- 2026-08-08: Se ajusto la limpieza del flujo RB /24 en `backend/index.html`: si `Actualizar Todos` detecta que todos los gateways del ultimo descubrimiento estan `UPDATED`, muestra el aviso de que no hay acciones pendientes y limpia el textarea de IPs, el campo de RB/subred, el contador y el panel de resultados. Tambien se agrego `autocomplete=off` y se limpian esos campos al cargar la pagina para evitar que F5 restaure valores anteriores. Se reconstruyo `app` y se verifico HTML servido, servicios saludables y simulacion del caso sin pendientes.
- 2026-08-07: Se mejoro `Actualizar Todos` despues del descubrimiento por RB /24 en `backend/index.html`: la app recuerda el estado detectado de cada gateway y, si alguno ya quedo `UPDATED`, lo omite automaticamente del lote de actualizacion. Si todos estan `UPDATED`, muestra aviso de que no hay acciones pendientes y no abre el modal de actualizacion. Se agregaron mensajes ES/PT-BR y se reconstruyo `app`; se verifico HTML servido y simulacion de 5 gateways con 2 ya actualizados.
- 2026-08-07: Se agrego backup automatico diario de `data/solinfnet.db` desde `backend/main.py`: al arrancar crea un backup si no existe uno del dia y luego revisa cada 24 horas. Los backups se guardan en `data/backups/solinfnet-YYYYMMDD-HHMMSS.db`, con retencion configurable por `DB_BACKUP_RETENTION_DAYS` (14 dias por defecto) y carpeta configurable por `DB_BACKUP_DIR`. Se agrego `data/backups/` a `.gitignore`. Tambien se mejoro el estado `UPDATED` para mostrar `OK - sin accion necesaria` / `OK - sem acao necessaria` y devolver `current_version` tambien cuando el gateway ya esta en version objetivo. Se reconstruyeron `app` y `worker`; se verifico backup creado e integro, HTML servido y worker saludable.
- 2026-08-06: Se ajusto el panel visual de descubrimiento por RB /24 en `backend/index.html`: al terminar Escanear Todos ya no quedan los 24 candidatos en pantalla; el textarea y las tarjetas se reemplazan por solo los gateways detectados y un resumen de candidatos descartados, en ES/PT-BR. Se reconstruyo `app` y se verifico que el HTML servido contiene la logica nueva.
- 2026-08-06: Se limpio manualmente el inventario para la subred `220.30.39.5/24` despues de la prueba de generacion por RB: se eliminaron los candidatos falsos `220.30.39.*` dejando solo el gateway real `220.30.39.105`. Antes de borrar se creo respaldo temporal en `/tmp/solinfnet-before-clean-220-30-39.db`; la BD runtime `data/solinfnet.db` esta ignorada/no versionada y no aparece en `git status`.
- 2026-08-06: Se corrigio el descubrimiento desde RB /24 para no contaminar el inventario con los 24 candidatos. Las listas generadas deben pasar primero por Escanear Todos; app consulta /api/scan/{ip}?discovery=true en lotes de 5 y reemplaza la lista por solo los gateways donde pudo leer una version valida. backend/tasks.py no persiste OFFLINE/ERROR durante descubrimiento, pero el escaneo normal conserva su comportamiento. Actualizar Todos bloquea candidatos sin descubrir. Se reconstruyeron app y worker y se probo con red simulada que fallos no escriben en BD y gateways validos si. Los falsos registros creados antes no se borran automaticamente porque son indistinguibles de equipos legitimos actualmente apagados.
- 2026-08-06: Se agrego generacion segura de gateways desde una RB /24 en backend/index.html. Una RB terminada en .5 genera los 24 candidatos .15, .25, ... .245, excluyendo la propia RB y dejando la lista visible para revision. La actualizacion multiple procesa esa lista secuencialmente en lotes maximos de 5, espera el resultado de cada lote, mantiene progreso acumulado y conserva la lista cuando hay errores. La interfaz y los mensajes nuevos estan disponibles en ES y PT-BR. Se reconstruyo app y se verificaron contenedor saludable, HTML servido, generacion de 24 IPs y lotes 5/5/5/5/4 sin contactar gateways reales.
- 2026-08-06: Se pulio la actualizacion multiple por lista de IPs en `backend/index.html`. La caja de multiples IPs ahora tiene boton `Actualizar Todos`, envia la lista a `/api/update`, muestra el mismo panel de progreso filtrado por `task_id`, deshabilita botones mientras corren las tareas y consulta `/api/update/status/{task_id}` como fallback para evitar paneles cargando indefinidamente. Se reconstruyo `app` y se verifico que el HTML servido contiene el flujo nuevo.
- 2026-08-06: Se corrigio la UI de progreso de actualizacion en `backend/index.html`. El monitor global ahora recibe los `task_id` recien creados y filtra activo/completado por esas tareas, evitando mostrar 'todas las actualizaciones completadas' por tareas viejas. La actualizacion desde inventario tambien muestra de inmediato las tarjetas de progreso arriba de la tabla. Se reconstruyo `app` para servir el HTML actualizado.
- 2026-08-06: Se amplio la traduccion ES/PT-BR en `backend/index.html`: los popups del mapa principal ahora traducen Cliente/Unidad/Descripcion/Flota/Version/Estado/Coordenadas y muestran estados localizados. Tambien se conectaron a i18n filtros, paginacion, historiales, graficos de reportes, mensajes de configuracion/Mono y popups del mapa en modo presentacion. Se reconstruyo `app` para servir el HTML actualizado.
- 2026-08-05: Se corrigio el caso `215.69.1.105`: estaba asociado a `Santo Aleixo` / `Araxa-MG` pero sin coordenadas, por eso el mini-mapa de unidad podia mostrar el hermano `215.69.2.105`. Se cargaron coordenadas GPS propias para `215.69.1.105` en la BD activa y se ajusto `backend/index.html` para no centrar el mini-mapa en un hermano cuando la unidad seleccionada no tenga GPS propio.
- 2026-08-05: Se diagnostico el gateway `215.69.2.105`: la BD tenia cliente `Santo Aleixo` pero no unidades importadas para `215.69.0.0`; se reimportaron presets sin `--clean` dentro del contenedor y se reasocio el gateway a `Faz. Santa Fe`. Se ajusto GPS para leer `/dev/ttyGPS` con `timeout -s KILL` porque el `cat` serial no terminaba con timeout normal; se guardaron coordenadas GPS en la BD activa para ese gateway.
- 2026-08-05: Se automatizo la importacion de clientes/unidades desde los TXT de presets: `backend/main.py` importa sin `--clean` al arrancar y cada 24 horas; `docker-compose.yml` monta los tres TXT desde el host dentro de `app` y `worker` como solo lectura para que los cambios sean visibles sin rebuild.
- 2026-08-05: Se agrego fallback de coordenadas GPS en `backend/tasks.py`: si `SolinfNet.conf` no trae latitud/longitud y `UseGPS = 1`, el backend lee una muestra corta de `/dev/ttyGPS`, parsea sentencias NMEA con fix valido (`GPRMC`, `GPGGA`, `GPGLL`) y guarda las coordenadas decimales en el gateway.
- 2026-08-05: Se localizo el modo presentacion/kiosco en `backend/index.html` para que respete el idioma activo (`ES` o `PT`). El modo ahora muestra etiquetas principales, controles, mensajes vacios/error y leyendas en portugues de Brasil cuando `currentLang` es `pt`.

- 2026-08-05: Se corrigio el fallback GPS para puertos serie continuos. El comando anterior usaba timeout con cat /dev/ttyGPS, que dejaba la sesion SSH esperando y devolvia success=False. Ahora se cierra al recibir la primera sentencia NMEA valida mediante awk. Se reconstruyo el worker y se verifico el escaneo completo de los gateways probados: las coordenadas se guardan correctamente en la BD activa.

- 2026-08-08: Se agrego tabla `gateway_diagnostic_events` para contabilizar problemas de espacio relacionados con Mono (`MONO_NO_SPACE`, `LOW_DISK_SPACE`) y pruebas de persistencia. Las actualizaciones crean un marcador antes de un reboot y lo verifican despues: si desaparece se registra `FROZEN_CARD` como posible cartao congelado; si sobrevive se registra `PERSISTENCE_OK`. Los reinicios solo del servicio quedan como no verificados. El dashboard muestra los contadores acumulados de Mono/espacio, poco espacio, tarjetas congeladas y pruebas persistentes. No se ejecuto una actualizacion real despues de este cambio.
- 2026-08-08: En la tabla de inventario se cambio el icono de configuracion LPWAN/Relay de rueda dentada a nube con lluvia para que se asocie mejor con meteorologia. Tambien se ajusto el tooltip ES/PT y se corrigio la etiqueta espanola de tarjetas congeladas.
- 2026-08-08: Se corrigio la seleccion masiva del inventario para que el contador de "Actualizar" solo incluya gateways pendientes dentro de la lista filtrada/visible. Al cambiar filtros, pagina o recargar inventario se eliminan selecciones antiguas que ya no aplican.
- 2026-08-08: Se mejoro la navegacion de los dossiers de cliente y unidad: el contador de unidades del cliente ahora lleva a la tabla, cada unidad abre su ficha tecnica, y al cambiar entre dossiers se cierra la ventana anterior para que la nueva quede al frente. La API de detalle de cliente ahora incluye el id de cada unidad.
- 2026-08-08: Se corrigio la interaccion dentro del dossier de cliente: el contador de unidades ahora enfoca y resalta la tabla de unidades, las unidades individuales abren directamente su ficha tecnica desde el cliente, y las funciones usadas por botones inline quedan expuestas globalmente para evitar clicks sin respuesta.
- 2026-08-08: Se reforzo el click de unidades dentro del dossier de cliente usando atributos `data-*` y listeners despues del render, evitando que las comillas de la IP rompan el `onclick` inline.
- 2026-08-08: Se mejoro la presentacion visual de SO y Status en la tabla de inventario: columnas centradas, badges compactos con texto principal/subtexto, tooltips con el estado completo y separacion visual mas consistente.
- 2026-08-08: Se corrigio el mapa de la ficha de unidad para mostrar todos los gateways con GPS de esa misma unidad y no mezclar puntos de unidades hermanas. El endpoint `/api/unidad/{id}/detalle` ahora devuelve `gateways` de la unidad con `is_primary`; el frontend resalta el gateway principal y ajusta bounds a todos los pines propios. Validado con Grupo Natter: Faz. Vaca Branca devuelve 4 pines y Faz. Sta Terezinha 6.
- 2026-08-10: Se corrigio la deteccion de `FROZEN_CARD` en `backend/tasks.py`. El problema observado con `220.181.1.125` era que en gateways con systemd el flujo reiniciaba solo el servicio, borraba/no verificaba el marcador de persistencia y podia guardar `SUCCESS` aunque la SD estuviera congelada. Ahora, si la actualizacion no paso por un reboot real, el worker hace un reboot controlado de persistencia antes de declarar exito; `wait_for_ping()` exige ver caer y volver el ping, y si el marcador desaparece se registra `FROZEN_CARD`, se guarda historial `FAILED` y no se marca como success. Se reconstruyo `worker`; no se relanzo la actualizacion real del gateway desde Codex.
- 2026-08-10: Se pulio la deteccion de `FROZEN_CARD`: el worker ahora guarda/devuelve un mensaje corto (`Cartao congelado`) y la UI normaliza mensajes tecnicos antiguos en historial/progreso. Tambien se ajusto el monitor de progreso de inventario para tratar resultados internos terminales (`FAILED`, `BLOCKED`, `ERROR`, `OFFLINE`, `FROZEN_CARD`) como completados aunque Celery los entregue con estado `SUCCESS`, evitando que quede el spinner girando. Se limpio en la BD runtime el mensaje largo existente de `220.181.1.125`.
- 2026-08-10: Se agrego estado explicito `FROZEN_CARD` para tarjetas congeladas en inventario. El worker guarda ese status cuando detecta cartao congelado; la tabla muestra `Necesario/Substituir` (`Necessário/Substituir` en PT) y el filtro de Status incluye la nueva opcion. Los reportes cuentan `FROZEN_CARD` como fallo/offline y se marco `220.181.1.125` en la BD runtime con el nuevo estado.
- 2026-08-10: Se ajustaron los contadores de diagnosticos del dashboard para contar gateways unicos por tipo de evento, no eventos acumulados. Esto evita que `MONO_NO_SPACE` suba varias veces por reinstalar/limpiar el mismo gateway. Tambien se corrigio el popup del mapa en dossier de cliente para mostrar el estado localizado (`statusLabel`) en vez del valor interno `FROZEN_CARD`.
- 2026-08-10: Se corrigio otro render crudo de `FROZEN_CARD` en el dossier de cliente: la tabla de unidades ahora muestra `Necesario substituir` / `Necessario substituir` en vez del valor interno. Tambien se agrego `FROZEN_CARD` al estado visual del dossier de unidad, a los contadores locales de fallo/offline y al formato de exportacion para tratar las tarjetas congeladas como problema operativo.
- 2026-08-10: Se separo `FROZEN_CARD` de `offline` en el dossier de cliente. Las tarjetas congeladas pueden estar operativas/respondiendo, asi que ahora el KPI `Offline` solo cuenta `OFFLINE/ERROR` y se agrego un KPI separado `Substituir` para `FROZEN_CARD`; la grafica de salud sigue tratandolo como atencion operativa.
- 2026-08-10: Se simplifico el bloque de diagnosticos en Reportes: ahora solo muestra `Problemas Mono / espacio` y `Tarjetas congeladas`, quitando `Poco espacio` y `Pruebas persistentes` de la UI. Las tarjetas son clicables y abren un modal con gateways afectados, cliente/unidad, estado actual, ultimo evento, detalle y accesos a los dossiers relacionados. Se agrego endpoint `/api/reportes/diagnosticos/{event_type}` para consultar afectados unicos por diagnostico.
- 2026-08-10: Se pulio el modal de afectados por diagnostico: se elimino la columna redundante `Acciones` y ahora el nombre del cliente abre el dossier de cliente, mientras que el nombre de la unidad abre la ficha de unidad directamente desde la tabla.
- 2026-08-10: Se corrigio el flujo de retorno del modal de afectados por diagnostico. Al abrir un dossier de cliente/unidad desde la lista de afectados, el modal de diagnostico ya no se elimina; queda debajo y vuelve a verse al cerrar el dossier superior.
- 2026-08-10: Se simplifico la tabla del modal de afectados por diagnostico quitando la columna `Detalle`, porque repetia informacion tecnica sin aportar al operador. El modal queda con IP, cliente, unidad, descripcion, estado y ultimo evento.
- 2026-08-10: Se ajusto la clasificacion de diagnosticos para evitar doble conteo: si un gateway esta marcado como `FROZEN_CARD` o tuvo evento de tarjeta congelada, queda priorizado en `Tarjetas congeladas` y se excluye de `Problemas Mono / espacio` en dashboard y modal de afectados.
- 2026-08-12: Se ajusto la seleccion del inventario para permitir marcar gateways `OFFLINE` y `ERROR` ademas de `PENDING`, evitando tener que escribir manualmente la IP para intentar una actualizacion desde la tabla. `UPDATED` y `FROZEN_CARD` siguen sin seleccionarse para actualizacion normal.
- 2026-08-12: Se corrigio la lectura de version de SolinfNet para evitar guardar banners de SSH/instalacion como `INSTALING SOLIFNET` dentro de `gateway.version`. `read_solinfnet_version()` ahora extrae solo versiones numericas tipo `6.5.0`, `normalize_version()` usa esa limpieza y `save_gateway_status()` sanea la version antes de persistir. Se limpio en la BD runtime el registro `220.37.1.135`, dejando version `6.5.0` y conservando status `ERROR` hasta nuevo escaneo.
- 2026-08-12: Se diagnostico el flujo de configurar Relay en `220.37.1.135`: el gateway imprime un banner `INSTALING SOLIFNET` en sesiones SSH no interactivas. Ese banner contaminaba la salida de `grep 'Hardware = Relay'` y el sistema interpretaba falsamente que el Relay ya estaba configurado, guardando `Sin cambios necesarios`. Se cambio la deteccion a marcadores `RELAY_PRESENT/RELAY_ABSENT`, se hizo mas robusta la lectura `has_relay` ante banners y la UI ahora muestra en rojo resultados internos `FAILED` aunque Celery devuelva estado tecnico `SUCCESS`.
- 2026-08-12: Se agrego vista ampliada de mapa en los dossiers de cliente y unidad. Cuando hay coordenadas GPS, aparece un boton junto al mini-mapa que abre un modal grande con los mismos pines, popups y bounds; al cerrar el dossier tambien se desmonta el mapa ampliado si estaba abierto.
- 2026-08-12: Se corrigio la diferencia de totales en Reportes: el dashboard ahora cuenta `FROZEN_CARD` como categoria propia (`Necesario substituir`) en el grafico global y por cultivo, por lo que las categorias suman el total real de gateways. Tambien se mejoro la presentacion visual de los graficos con tarjetas mas pulidas y controles para alternar vistas (dona/barras/polar y apilado/horizontal/linea), con textos ES/PT-BR.
- 2026-08-12: Se quito la vista Polar de los graficos de Reportes por baja legibilidad. Se agrego drill-down clicable desde los graficos global y por cultivo: al clicar categorias de atencion (`PENDING`, `OFFLINE/ERROR`, `FROZEN_CARD`) se abre un modal con IP, cliente, unidad, descripcion, version, estado y ultima revision, con enlaces a dossiers de cliente/unidad. `UPDATED` no abre lista para evitar cargar demasiados registros.
- 2026-08-13: Se corrigio la deteccion persistida de Relay LPWAN en `extract_conf_data()`: ahora usa marcadores `RELAY_PRESENT/RELAY_ABSENT` en vez de parsear numeros de `grep -c`, evitando falsos negativos por ruido/banners en stdout; ademas `save_gateway_status()` conserva el valor existente si una lectura SSH no consigue confirmar Relay. Se verifico `220.165.1.105`: el gateway tiene `Hardware = Relay`, se refrescaron metadatos en la BD runtime y la API ya devuelve `has_relay=true`. Se reconstruyo `worker`.
- 2026-08-13: Se habilito acceso directo al panel web de cada gateway desde cualquier IPv4 visible en la interfaz. Las IPs de inventario, escaneos, progreso, reportes, dossiers, historial y popups de mapas se convierten automaticamente en enlaces a `http://IP:8085`, abren en una pestaña nueva y validan la IPv4 antes de crear el enlace.
- 2026-08-13: Se excluyeron las subredes de cliente del acceso directo por IP. En los dossiers de cliente y unidad se muestran solo como referencia y no abren `:8085`; el enlace se mantiene exclusivamente para IPs reales de gateway.
- 2026-08-13: Se agrego la vista circular tipo Pizza a los graficos de Estado Global y Relay LPWAN en Reportes. Conserva leyenda, porcentajes y los drill-downs del estado global; el grafico por cultivo mantiene barras/linea porque compara varias series.
- 2026-08-13: Los graficos circulares de Estado Global y Relay LPWAN ahora muestran permanentemente el valor de cada segmento. Los sectores demasiado finos se mantienen legibles mediante la leyenda y el tooltip.
- 2026-08-13: Se unifico la referencia horaria del panel en `America/Sao_Paulo` (Araçatuba/SP). El backend emite fechas API con offset explicito, interpreta los registros SQLite existentes en esa zona y guarda las nuevas operaciones con la misma referencia. El frontend usa un formateador unico para tablas, historiales, dossiers y reportes; los relojes en vivo se sincronizan contra el endpoint `/api/time` del servidor, para no depender del reloj configurado en cada PC. Se reconstruyeron `app` y `worker` y se verificaron saludables. Se confirmo que los registros historicos estaban en UTC sin offset; se creo el backup `data/backups/solinfnet-before-timezone-migration-20260813-1705.db` y se migro una sola vez la BD runtime a hora de Sao Paulo (incluye escaneos, actualizaciones, diagnosticos y fechas de alta), evitando que queden tres horas adelantadas.
- 2026-08-13: Se corrigio el reloj del modo kiosco: el formato anterior indicaba solo `hour12:false`, por lo que algunos navegadores mostraban una fecha corta y la repetian junto a la fecha larga. Ahora el encabezado muestra hora `HH:mm:ss` y debajo solo dia de la semana con fecha extendida, usando la hora centralizada de Sao Paulo.
- 2026-08-14: Se aclaro el mensaje de error cuando el gateway responde pero SolinfNet no devuelve la version tras 3 intentos. Se reemplazo la frase ambigua `(¿reiniciandose?)` por una explicacion directa para el operador.
- 2026-08-14: Los diagnosticos de Mono/espacio ahora diferencian incidentes activos de limpiezas resueltas. Al eliminar `mono_crash`, si quedan mas de 100 MB libres se registra la resolucion; el contador de reportes solo muestra casos aun pendientes. El dossier de cada cliente incorpora el historial por IP con fecha de deteccion y resolucion, e interpreta los eventos anteriores usando el espacio libre registrado al terminar la limpieza.
- 2026-08-17: Se adelanto la limpieza de `mono_crash` al inicio de los escaneos y actualizaciones, inmediatamente despues de confirmar conectividad. Asi, cuando SolinfNet no inicia por falta de espacio, el sistema libera espacio antes de consultar `about.htm` y puede registrar la version real en vez de `Desconocida`. La deteccion y el historial de Mono/espacio se conservan aunque la misma limpieza resuelva el caso.
