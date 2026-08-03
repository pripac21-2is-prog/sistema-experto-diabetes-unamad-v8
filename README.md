# Sistema inteligente de apoyo al tamizaje del riesgo de diabetes - UNAMAD V8

Aplicación web desarrollada para el curso **Sistemas Expertos** de la Escuela Profesional de Ingeniería de Sistemas e Informática de la Universidad Nacional Amazónica de Madre de Dios.

**Autores:** Poldy Raúl Ripa Challco y Frank Hiobert Palomino Usca.

## Funciones principales

- Consulta pública temporal, sin cuenta y sin guardar el caso.
- Acceso privado para enfermería, medicina y administración.
- 403 registros históricos importados automáticamente desde `diabetes.csv`.
- Fechas organizadas por lotes y día de la semana visible.
- Directorio paginado de 50 registros por página.
- Registro de pacientes y evaluaciones por enfermería.
- Motor híbrido: reglas SI-ENTONCES + Random Forest previamente entrenado.
- Cola médica automática para alertas medias y altas.
- Edición de ficha, observaciones, seguimiento y derivaciones médicas.
- Ficha visual con IMC, cintura, silueta y evolución de indicadores.
- Reporte PDF individual, directorio PDF y exportaciones CSV.
- Usuarios, permisos, auditoría, copias y restauración de SQLite.
- Métricas, matriz de confusión e importancia de variables.
- Tres diagramas grandes de arquitectura y funcionamiento.

## Datos incluidos

- 403 filas históricas del CSV.
- 19 columnas originales.
- 390 filas con `glyhb` disponible para construir la clase objetivo.
- 16 predictores del Random Forest.
- `glyhb` no se usa como predictor para evitar fuga de información.

Los códigos `HIS-xxxx` identifican filas de la cohorte histórica. Los códigos `PAC-xxxx` corresponden a registros creados desde la plataforma.

## Ejecución

1. Descomprima la carpeta completa.
2. Ejecute `INICIAR_V8.bat`.
3. Abra `http://localhost:8501` si el navegador no se abre automáticamente.
4. Mantenga abierta la ventana negra mientras use la aplicación.

Las siguientes veces ejecute `EJECUTAR_V8.bat`.

## Verificación

Ejecute `VERIFICAR_V8.bat`. La entrega contiene 22 pruebas automáticas.

## Estructura

```text
app.py                 Interfaz y navegación
src/database.py        SQLite, usuarios, pacientes, auditoría y respaldos
src/model_service.py   Entrenamiento y predicción
src/expert_system.py   Reglas y decisión híbrida
src/reports.py         PDF individual y directorio
src/security.py        Hash y validación de contraseñas
src/ui.py              Diseño visual y adaptación móvil
assets/                 Logos, imagen médica y diagramas
```

## Alcance

El sistema genera una alerta de apoyo al tamizaje. No confirma ni descarta diabetes y el resultado debe ser revisado por personal de salud.
