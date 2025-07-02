# Gestor de tareas LLM

## Descripción

Aplicación para la gestión de tareas por medio de comandos de texto, utilizando un LLM (Large Language Model) para interpretar los comandos y realizar acciones sobre las tareas.

## Instalación Backend

Crear el entorno virtual:

```bash
python -m venv venv
```

Activar el entorno virtual:

```bash
source venv/bin/activate # En Windows usa `venv/Scripts/activate`
```

Instalar las dependencias:

```bash
pip install fastapi uvicorn pymongo pydantic python-dotenv httpx
```

## Instalación Frontend

```bash
npx create-react-app frontend
```

Ir a la carpeta `frontend` y instalar las dependencias:

```bash
npm install axios
```

## Ejecución Backend

```bash
cd backend
uvicorn main:app --reload --port 5000
```

## Ejecución Frontend

```bash
cd frontend
npm start
```
