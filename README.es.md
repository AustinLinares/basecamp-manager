# Basecamp Manager para Claude Code

*[Read in English](README.md)*

Un plugin de Claude Code para leer y gestionar **tableros de tarjetas de Basecamp** desde la terminal,
con un **hook de guardia** que impide que el agente borre algo o toque tarjetas que no son tuyas, y una
**instalación guiada** que nunca te pide pegar un secreto en el chat.

No oficial. Sin relación con 37signals ni con Anthropic.

## Por qué existe

Los tableros de tarjetas de Basecamp no están pensados para revisar una lista larga. Volver al tablero
después de abrir una tarjeta cuesta clics de más, y revisar muchas tarjetas obliga a abrir pestaña tras
pestaña. Este proyecto nació para evitar todo eso y dejar que el agente recorra la lista por ti.

Con el plugin, Claude puede:

- **Clasificar una columna de una pasada.** Lee cada tarjeta (texto, comentarios, imágenes, fechas de
  entrega) y las ordena en tareas rápidas, tareas largas, tarjetas con fecha límite y bugs. Cada una
  recibe una estimación de esfuerzo y, cuando está lo bastante clara, una propuesta de solución. Luego
  Claude puede encargarse de inmediato de las fáciles y las medianas, repartiendo el trabajo entre
  subagentes.
- **Mantener el tablero al día mientras trabajas.** Las tarjetas surgen a mitad de una tarea: un bug,
  algo que queda pendiente. Claude crea la tarjeta o agrega el paso en cuanto aparece, y marca los
  pasos como hechos a medida que avanza el trabajo, así nadie tiene que detenerse a actualizar
  Basecamp a mano.
- **Ponerte al día en un minuto.** "¿Qué tengo hoy?" lee tus asignaciones de todos los proyectos y
  te da lo vencido, lo de hoy, lo que está en progreso y en revisión. Claude también busca antes de
  crear una tarjeta (para evitar duplicados), muestra qué cambió en una tarjeta y resume tus
  notificaciones sin leer.
- **Adjuntar la evidencia.** Cuando se abre un PR, Claude comenta en la tarjeta con el enlace, qué
  cambió, cómo se verificó y qué sigue pendiente, con las capturas o grabaciones insertadas en el mismo
  comentario. Los pasos le indican al equipo qué falta por demostrar.

Todo desde la terminal, sin abrir Basecamp.

## Qué incluye

Darle a un agente un token de Basecamp es arriesgado por defecto: el token actúa como tú, puede mover,
reasignar o mandar a la papelera las tarjetas de cualquiera, y no hay deshacer. Este plugin trae:

1. **Una skill** con recetas probadas: leer tarjetas con sus imágenes y comentarios, crear tarjetas,
   añadir y completar pasos, comentar, mover entre columnas y reclamar tarjetas sin asignar.
2. **Un guardia** (hook `PreToolUse`) que corre antes de cada comando: nada de borrar, escrituras solo
   en tus tarjetas, lista de endpoints permitidos, solo `curl` y sin acceso a tus credenciales. Falla
   cerrado.
3. **Un asistente de instalación** que descubre por ti los ids de cuenta, persona y tablero, mientras
   el intercambio del token ocurre en tu propia terminal.

## Instalación

En Claude Code, pega **un comando a la vez** y pulsa Enter después de cada uno (si pegas los dos
juntos, Claude Code lee la segunda línea como argumento de la primera):

```
/plugin marketplace add AustinLinares/basecamp-manager
```

```
/plugin install basecamp-manager@basecamp-manager
```

Claude Code te pide las opciones del plugin (puedes dejar las de por defecto). Abre una sesión nueva y
sigue [docs/SETUP.md](docs/SETUP.md) (en inglés): registra tu app OAuth, ejecuta
`~/.config/basecamp-manager/bcm login` en tu terminal y di **"configura Basecamp"** en Claude Code. El
guardia queda activo en cuanto el plugin está habilitado.

> **Ejecuta `bcm login` en una terminal normal** (Terminal, iTerm, la terminal de tu IDE), **no en el
> chat de Claude** ni con el prefijo `!`: pide tu Client Secret, que nunca debe quedar en la sesión, y
> además `!` no tiene entrada de teclado.

**Deja que Claude lo configure con Claude in Chrome (opcional).** Si le das a Claude la extensión
[Claude in Chrome](https://claude.ai/chrome), di **"configura Basecamp"** y puede rellenar el
formulario de la app OAuth en Launchpad y descubrir tus ids de cuenta, persona y tablero. Nunca
escribe credenciales: **tú** pulsas **Register this app**, copias el Client ID y el Client Secret a tu
gestor de contraseñas y ejecutas `bcm login` en tu terminal para que no queden en la sesión.

La línea de comandos del plugin, siempre en `~/.config/basecamp-manager/bcm`:

| Comando | Qué hace |
|---|---|
| `bcm login` | Abre el navegador, recibe la autorización en localhost y guarda el token sin mostrarlo |
| `bcm refresh` | Renueva el token (cada dos semanas; Claude te avisa y puede ejecutarlo) |
| `bcm doctor` | Revisa herramientas, permisos, configuración, token, id de persona y el guardia |

Actualizaciones: en `/plugin`, **Marketplaces**, elige `basecamp-manager` y activa la actualización
automática, o actualiza a mano con `claude plugin update basecamp-manager@basecamp-manager`.

## Compatibilidad

| | Versión |
|---|---|
| Plugin | **0.4.1** (ver [CHANGELOG.md](CHANGELOG.md)) |
| Claude Code | **2.1.295 o superior** (necesita `onFailure: "block"` para que el guardia falle cerrado). Probado en 2.1.301 |
| API de Basecamp | API de Basecamp 5 (`3.basecampapi.com`), endpoints verificados en la [documentación oficial](https://github.com/basecamp/bc3-api) el 2026-10-17 |
| Python | 3.8 o superior, solo biblioteca estándar (ejecuta el guardia) |
| Herramientas | `curl`, `jq` |
| Sistema | Probado en macOS. Linux debería funcionar. Windows necesita Git Bash o WSL (sin probar) |

## Qué impone el guardia

| Regla | Efecto |
|---|---|
| Nunca borrar | `DELETE` y mandar a la papelera se niegan siempre |
| Solo tus tarjetas | Antes de cada escritura lee la tarjeta y comprueba que estás asignado |
| Tus tarjetas nuevas | Una tarjeta que creaste sigue editable mientras no tenga asignados y no esté en una columna protegida |
| Reclamar | Una tarjeta sin asignar se te puede asignar con una única escritura exacta, si `allow_claim` está activo |
| Comentarios | Solo se crean, en tus tarjetas, si `allow_comments` está activo |
| Subidas | Solo imágenes, videos y PDF, insertados en tus tarjetas, si `allow_uploads` está activo |
| Lista permitida | Cualquier otro endpoint o método de escritura se niega |
| Solo curl | El host de Basecamp solo puede aparecer en un comando que empiece por `curl`, con URLs literales |
| Credenciales | Claude no puede imprimir, copiar ni abrir tu token ni tus secretos OAuth |
| Falla cerrado | Si no puede verificar algo, bloquea |

Cada persona configura sus reglas: opciones del plugin en `/plugin` y `guard.protected_columns` en
`~/.config/basecamp-manager/config.json`. Detalle: [modelo de seguridad](skills/basecamp/references/security-model.md).

## Límites, sin rodeos

- El guardia **no puede saber qué pediste**. Reglas como "reclama solo si te lo pido" son
  instrucciones para Claude; el guardia solo restringe la forma de cada escritura.
- Solo cubre **las herramientas de Claude Code**. Tu token puede hacer todo lo que tu usuario de
  Basecamp puede hacer desde cualquier otra herramienta. Es una barrera en el cliente, no un permiso
  del servidor.
- Inspecciona el texto de los comandos. Protege el camino normal; no es un sandbox.
- Actúa con **tu identidad**: todo lo que Claude escribe aparece en Basecamp con tu nombre.

## Dónde viven tus datos

```
~/.config/basecamp-manager/
  config.json   ids y reglas, sin secretos
  token         token de acceso (600)
  oauth.json    refresh token y credenciales de la app OAuth (600); Claude nunca puede leerlo
  token-info.json  solo la fecha de caducidad del token
  bcm           acceso a la línea de comandos del plugin, que el plugin mantiene al día
```

`BASECAMP_MANAGER_HOME` cambia el directorio. Nada se guarda en este repositorio.

## Desarrollo

```bash
python3 -m unittest discover -s tests     # 92 pruebas; nada llega a Basecamp
claude plugin validate .                   # manifiesto del marketplace
claude plugin validate .claude-plugin/plugin.json
claude --plugin-dir .                      # probar el plugin sin instalarlo
```

## Licencia

[MIT](LICENSE) © 2026 Austin Airton Linares Castillo
