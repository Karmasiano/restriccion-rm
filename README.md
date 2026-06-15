# Alerta restricción vehicular — carga con sello verde (RM)

Uso personal. Un cron gratuito (GitHub Actions) revisa el portal **Aire RM** del MMA,
te avisa por **Telegram** cuando hay **preemergencia o emergencia** y publica el estado en un
**dashboard web** (GitHub Pages).

## Estructura
```
check_restriccion.py              # lógica (fetch + parser + decisión + Telegram)
test_parser.py                    # tests offline
index.html                        # dashboard (lee data/status.json)
data/status.json, history.json    # los escribe el cron; sirven a la web
.github/workflows/restriccion.yml # cron noche/mañana (hora Chile)
```

## Setup (los únicos pasos manuales, ~10 min)
1. **Bot de Telegram**: en Telegram habla con **@BotFather** → `/newbot` → copia el **token**.
2. **Tu chat_id**: escríbele algo a tu bot, luego abre en el navegador
   `https://api.telegram.org/bot<TOKEN>/getUpdates` y copia el número de `chat.id`.
3. Sube esta carpeta a un repo de GitHub (o "Add file → Upload files").
4. En el repo → **Settings → Secrets and variables → Actions → New repository secret**:
   - `TELEGRAM_TOKEN`
   - `TELEGRAM_CHAT_ID`
5. **Settings → Pages** → Source: *Deploy from a branch* → rama `main`, carpeta `/ (root)`.
   Tu dashboard quedará en `https://<usuario>.github.io/<repo>/`.

## Probar
- Manual: **Actions → Alerta restriccion vehicular → Run workflow**. Revisa el log y, si hay
  episodio activo, tu Telegram. El dashboard se actualiza al commitear `data/`.
- Local: `pip install requests beautifulsoup4 && python test_parser.py` (tests offline).
  Sin secrets, el script imprime el mensaje en consola en vez de enviarlo.

## VALIDAR contra la fuente real (no pude hacerlo yo)
- Abre `https://airerm.mma.gob.cl/wp-json/wp/v2/posts` y confirma que responde JSON.
- Un día de preemergencia, compara los dígitos del Telegram/dashboard con la tabla **MEDIDAS**
  de la noticia. Si la API estuviera apagada, solo se cambia `fetch_latest_episode()` para
  parsear el HTML de `/noticias/`; el parser de la tabla sirve igual.

## Límites honestos
- Máxima anticipación ≈ la noche anterior (la autoridad decreta esa noche).
- Cubre **carga con sello verde**. Si tu camioneta fuera carga *sin* sello verde o *particular*,
  las reglas cambian (revisa tu permiso de circulación).
- DST: el cron asume Chile UTC-4 (invierno, que es la temporada de restricción).

## Hardening sugerido
Cruzar con una 2ª fuente oficial (subtrans.gob.cl o uoct.cl) y avisar solo si coinciden.
