# Despliegue

## Opcion recomendada: Vercel

Esta app usa Flask, SQLite, Jinja2 y CSS vanilla. GitHub Pages no ejecuta Python ni base de datos, por eso no es una opcion valida para publicar la app completa.

### Configuracion en Vercel

1. Subir el proyecto a GitHub.
2. En Vercel, importar el repositorio.
3. Configurar el Root Directory como:

```text
artifacts/restaurant-app
```

4. Vercel detectara `app.py` como entrada Flask y `requirements.txt` para instalar Flask.
5. Deploy.

## Nota sobre SQLite

Vercel es adecuado para una demo o prototipo Flask. Para uso real con escritura persistente de datos, conviene migrar SQLite a una base administrada o usar un hosting con disco persistente.
