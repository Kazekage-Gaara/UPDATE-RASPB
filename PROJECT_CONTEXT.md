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
