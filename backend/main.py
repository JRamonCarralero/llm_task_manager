import os
import json
import re
import httpx
from datetime import datetime
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any
from bson.objectid import ObjectId # Importar ObjectId para json_encoders
from pymongo.errors import ConnectionFailure # Importar ConnectionFailure

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# --- Modelos Pydantic para validación de datos y documentación ---

class TaskBase(BaseModel):
    """Modelo base para una tarea."""
    description: str = Field(..., min_length=1, max_length=200)
    start_date: Optional[str] = None # Formato ISO 8601 (YYYY-MM-DD)
    status: Literal["pending", "completed", "in_progress", "cancelled"] = "pending"

class TaskCreate(TaskBase):
    """Modelo para crear una nueva tarea."""
    pass

class TaskUpdate(BaseModel):
    """Modelo para actualizar una tarea existente."""
    description: Optional[str] = None
    start_date: Optional[str] = None
    status: Optional[Literal["pending", "completed", "in_progress", "cancelled"]] = None

class Task(TaskBase):
    """Modelo completo de una tarea, incluyendo el ID de MongoDB."""
    id: str = Field(..., alias="_id") # Mapea _id de MongoDB a 'id' en la respuesta JSON
    created_at: datetime # Campo adicional para la fecha de creación

    class Config:
        """Configuración para Pydantic."""
        allow_population_by_field_name = True # Permite que Pydantic use el alias '_id'
        json_encoders = {
            ObjectId: lambda oid: str(oid),
            datetime: lambda dt: dt.isoformat() # Convertir datetime a string ISO
        }

# --- Modelo para la salida estructurada del LLM (nuestro MCP) ---

class LLMCommand(BaseModel):
    """
    Define el esquema de JSON que esperamos del LLM.
    Este es el corazón de nuestro Model Context Protocol (MCP).
    """
    action: Literal["create", "read", "update", "delete", "unknown"]
    task_id: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = None #YYYY-MM-DD
    status: Optional[Literal["pending", "completed", "in_progress", "cancelled"]] = None
    message: Optional[str] = None # Mensaje para el usuario si la acción es 'unknown' o necesita aclaración

# --- Configuración de FastAPI ---

app = FastAPI(
    title="API de Gestión de Tareas con MongoDB, FastAPI y MCP",
    description="Una API RESTful que interpreta comandos de texto para gestionar tareas, usando un LLM.",
    version="1.0.0",
)

# Configuración de CORS para permitir que el frontend de React se conecte
origins = [
    "http://localhost",
    "http://localhost:3000", # El puerto donde se ejecuta tu aplicación React
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Permite todos los métodos (GET, POST, PUT, DELETE)
    allow_headers=["*"], # Permite todas las cabeceras
)

# Importar y inicializar MongoDBManager de forma segura
db_manager = None
try:
    from db import MongoDBManager
    db_manager = MongoDBManager()
except ConnectionFailure as e:
    print(f"CRITICAL ERROR: No se pudo conectar a MongoDB al iniciar la aplicación: {e}")
    print("La aplicación se iniciará, pero las operaciones de base de datos no funcionarán.")
except Exception as e:
    print(f"CRITICAL ERROR: Error inesperado al inicializar MongoDBManager: {e}")
    print("La aplicación se iniciará, pero las operaciones de base de datos no funcionarán.")

# --- Funciones de interacción con el LLM ---

async def call_llm_for_command(user_prompt: str) -> LLMCommand:
    """
    Llama al LLM para interpretar el comando del usuario y devolver un JSON estructurado.
    """
    # Define el JSON Schema que el LLM debe seguir para su respuesta
    response_schema = {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["create", "read", "update", "delete", "unknown"],
                "description": "The action to perform on tasks."
            },
            "task_id": {
                "type": "STRING",
                "description": "ID of the task for update or delete actions. Required for update/delete."
            },
            "description": {
                "type": "STRING",
                "description": "Description of the task. Required for create, optional for update."
            },
            "start_date": {
                "type": "STRING",
                "format": "date-time", # Correcto para la API de Gemini
                "description": "Start date of the task in McClellan-MM-DD format. Optional for create/update."
            },
            "status": {
                "type": "STRING",
                "enum": ["pending", "completed", "in_progress", "cancelled"],
                "description": "Status of the task. Optional for create/update."
            },
            "message": {
                "type": "STRING",
                "description": "A user-friendly message if the action is 'unknown' or needs clarification."
            }
        },
        "required": ["action"],
        "propertyOrdering": ["action", "task_id", "description", "start_date", "status", "message"]
    }

    # ¡CORRECCIÓN CRÍTICA: Duplicar las llaves en los ejemplos JSON dentro de la lista de cadenas!
    prompt_template_lines = [
        "Eres un asistente de gestión de tareas. Tu objetivo es interpretar los comandos del usuario y devolver UN OBJETO JSON que represente la acción y los datos de la tarea. NO INCLUYAS NINGÚN TEXTO ADICIONAL FUERA DEL JSON.",
        "Las fechas deben estar en formato McClellan-MM-DD.",
        "Los estados posibles de las tareas son: \"pending\", \"completed\", \"in_progress\", \"cancelled\".",
        "",
        "Si no puedes determinar una acción clara, usa \"unknown\" para la acción y proporciona un mensaje útil en el campo \"message\".",
        "",
        "Ejemplos:",
        "Comando de usuario: 'crear la tarea \"realizar app\" con fecha de inicio 03-07-2025 y estado \"pendiente\"'",
        "JSON esperado:",
        "```json",
        "{{", # ¡Aquí la corrección! Ahora son llaves dobles
        "  \"action\": \"create\",",
        "  \"description\": \"realizar app\",",
        "  \"start_date\": \"2025-07-03\",",
        "  \"status\": \"pending\"",
        "}}", # ¡Aquí la corrección! Ahora son llaves dobles
        "```",
        "",
        "Comando de usuario: 'marcar tarea 60c7b41b1d7d8f9c7b4c3e21 como completada'",
        "JSON esperado:",
        "```json",
        "{{",
        "  \"action\": \"update\",",
        "  \"task_id\": \"60c7b41b1d7d8f9c7b4c3e21\",",
        "  \"status\": \"completed\"",
        "}}",
        "```",
        "",
        "Comando de usuario: 'actualizar la descripción de la tarea 60c7b41b1d7d8f9c7b4c3e21 a \"Terminar informe\"'",
        "JSON esperado:",
        "```json",
        "{{",
        "  \"action\": \"update\",",
        "  \"task_id\": \"60c7b41b1d7d8f9c7b4c3e21\",",
        "  \"description\": \"Terminar informe\"",
        "}}",
        "```",
        "",
        "Comando de usuario: 'eliminar tarea 60c7b41b1d7d8f9c7b4c3e21'",
        "JSON esperado:",
        "```json",
        "{{",
        "  \"action\": \"delete\",",
        "  \"task_id\": \"60c7b41b1d7d8f9c7b4c3e21\"",
        "}}",
        "```",
        "",
        "Comando de usuario: 'mostrar todas mis tareas'",
        "JSON esperado:",
        "```json",
        "{{",
        "  \"action\": \"read\"",
        "}}",
        "```",
        "",
        "Comando de usuario: '¿Qué tiempo hace hoy?'",
        "JSON esperado:",
        "```json",
        "{{",
        "  \"action\": \"unknown\",",
        "  \"message\": \"Lo siento, solo puedo gestionar tareas. ¿Hay algo que pueda hacer con tus tareas?\"",
        "}}",
        "```",
        "",
        "Comando de usuario: '{user_prompt}'" # Este es el único marcador de posición para format()
    ]
    prompt_template = "\n".join(prompt_template_lines)

    print(f"DEBUG: Prompt template ANTES de format: \n{repr(prompt_template)}") # Depuración
    
    formatted_prompt = prompt_template.format(user_prompt=user_prompt)
    print(f"DEBUG: Prompt template DESPUÉS de format: \n{repr(formatted_prompt)}") # Depuración

    chat_history = []
    chat_history.append({ "role": "user", "parts": [{ "text": formatted_prompt }] })
    
    payload = {
        "contents": chat_history,
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": response_schema
        }
    }

    api_key = os.getenv("GEMINI_API_KEY", "") 
    if not api_key:
        print("ERROR: La clave API de Gemini no se encontró en las variables de entorno. Asegúrate de tenerla en tu archivo .env como GEMINI_API_KEY.")
        return LLMCommand(action="unknown", message="Error de configuración: Clave API no encontrada.")

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                api_url,
                headers={'Content-Type': 'application/json'},
                json=payload
            )
            response.raise_for_status() # Lanza una excepción para errores HTTP (4xx o 5xx)
            result = response.json()

            print(f"DEBUG: Respuesta cruda del LLM: {result}") # Depuración: ver la respuesta completa

            if result.get("candidates") and len(result["candidates"]) > 0 and \
               result["candidates"][0].get("content") and \
               result["candidates"][0]["content"].get("parts") and \
               len(result["candidates"][0]["content"]["parts"]) > 0:
                
                raw_text = result["candidates"][0]["content"]["parts"][0]["text"]
                print(f"DEBUG: Texto extraído del LLM: '{raw_text}' (repr: {repr(raw_text)})") # Depuración: ver el texto antes de parsear

                json_string_to_parse = ""
                json_block_match = re.search(r'```json\s*(.*?)\s*```', raw_text, re.DOTALL)
                
                if json_block_match:
                    json_string_to_parse = json_block_match.group(1).strip()
                    print(f"DEBUG: JSON extraído de bloque markdown: '{json_string_to_parse}'") # Depuración
                else:
                    json_string_to_parse = raw_text.strip()
                    print(f"DEBUG: JSON directo del texto crudo: '{json_string_to_parse}'") # Depuración

                try:
                    parsed_json = json.loads(json_string_to_parse)
                    print(f"DEBUG: JSON parseado: {parsed_json}") # Depuración

                    clean_parsed_json = {}
                    for k, v in parsed_json.items():
                        cleaned_key = re.sub(r'[^\w]', '', k).strip() 
                        print(f"DEBUG: Original key: '{k}' (repr: {repr(k)}) -> Cleaned key: '{cleaned_key}' (repr: {repr(cleaned_key)})")
                        clean_parsed_json[cleaned_key] = v
                    
                    print(f"DEBUG: JSON con claves limpias: {clean_parsed_json}") # Depuración
                    
                    action_value = clean_parsed_json.get('action')
                    if action_value is None:
                        print(f"Advertencia: La clave 'action' no se encontró después de parsear y limpiar. JSON original: '{raw_text}', JSON limpio: {clean_parsed_json}")
                        return LLMCommand(action="unknown", message="No pude determinar la acción del LLM. Por favor, sé más específico.")

                    if action_value not in ["create", "read", "update", "delete", "unknown"]:
                         print(f"Advertencia: El valor de 'action' '{action_value}' no es válido. JSON limpio: {clean_parsed_json}")
                         return LLMCommand(action="unknown", message=f"La acción '{action_value}' no es válida. Por favor, sé más específico.")

                    return LLMCommand(**clean_parsed_json) # Validar con el modelo Pydantic
                except json.JSONDecodeError as e:
                    print(f"ERROR: Error al decodificar JSON del LLM: {e}. String intentado parsear: '{json_string_to_parse}' (repr: {repr(json_string_to_parse)})")
                    return LLMCommand(action="unknown", message="El LLM devolvió un formato JSON inválido. Inténtalo de nuevo.")
            else:
                print(f"ERROR: Respuesta inesperada del LLM (no candidates/content): {result}")
                return LLMCommand(action="unknown", message="No pude interpretar tu comando. Inténtalo de nuevo.")
    except httpx.HTTPStatusError as e:
        print(f"ERROR HTTP al llamar al LLM: {e.response.status_code} - {e.response.text}")
        return LLMCommand(action="unknown", message=f"Error del servidor al procesar tu comando: {e.response.status_code}.")
    except Exception as e: # Captura cualquier otro error inesperado
        print(f"ERROR general al llamar al LLM: {e}")
        return LLMCommand(action="unknown", message="Ocurrió un error inesperado al procesar tu comando.")


# --- Rutas de la API ---

@app.get("/")
async def read_root():
    """Ruta raíz para verificar que la API está funcionando."""
    return {"message": "¡Bienvenido a la API de Gestión de Tareas con FastAPI y MCP!"}

@app.post("/command", response_model=Dict[str, Any])
async def process_command(request: Request):
    """
    Endpoint principal para procesar comandos de texto del usuario.
    El LLM interpreta el comando y realiza la acción correspondiente en la DB.
    """
    data = await request.json()
    user_input = data.get('command')

    if not user_input:
        raise HTTPException(status_code=400, detail="El campo 'command' es requerido.")

    # 1. Llamar al LLM para interpretar el comando
    llm_response: LLMCommand = await call_llm_for_command(user_input)

    # 2. Ejecutar la acción basada en la interpretación del LLM
    action_result = {"status": "success", "message": "Comando procesado."}
    
    # Asegurarse de que db_manager está inicializado antes de usarlo
    if db_manager is None:
        action_result = {"status": "error", "message": "Error de base de datos: Conexión no establecida."}
    elif llm_response.action == "create":
        if not llm_response.description:
            action_result = {"status": "error", "message": "Para crear una tarea, necesito una descripción."}
        else:
            task_id = db_manager.add_task(
                description=llm_response.description,
                start_date=llm_response.start_date,
                status=llm_response.status
            )
            action_result["message"] = f"Tarea '{llm_response.description}' creada con ID: {task_id}"
            action_result["task_id"] = task_id
            
    elif llm_response.action == "read":
        # Las tareas se leerán directamente desde el frontend después de cada comando.
        # Aquí solo confirmamos que la acción fue reconocida.
        action_result["message"] = "Listando todas las tareas."

    elif llm_response.action == "update":
        if not llm_response.task_id:
            action_result = {"status": "error", "message": "Para actualizar una tarea, necesito el ID de la tarea."}
        elif not (llm_response.description or llm_response.start_date or llm_response.status):
            action_result = {"status": "error", "message": "Para actualizar, necesito al menos una descripción, fecha o estado."}
        else:
            success = db_manager.update_task(
                task_id=llm_response.task_id,
                description=llm_response.description,
                start_date=llm_response.start_date,
                status=llm_response.status
            )
            if success:
                action_result["message"] = f"Tarea {llm_response.task_id} actualizada correctamente."
            else:
                action_result = {"status": "error", "message": f"No se pudo actualizar la tarea {llm_response.task_id}. ¿El ID es correcto?"}

    elif llm_response.action == "delete":
        if not llm_response.task_id:
            action_result = {"status": "error", "message": "Para eliminar una tarea, necesito el ID de la tarea."}
        else:
            success = db_manager.delete_task(llm_response.task_id)
            if success:
                action_result["message"] = f"Tarea {llm_response.task_id} eliminada correctamente."
            else:
                action_result = {"status": "error", "message": f"No se pudo eliminar la tarea {llm_response.task_id}. ¿El ID es correcto?"}

    elif llm_response.action == "unknown":
        action_result = {"status": "info", "message": llm_response.message or "No pude entender tu comando. Por favor, sé más específico."}

    else:
        action_result = {"status": "error", "message": "Acción no reconocida por el sistema."}

    return {"llm_interpretation": llm_response.dict(), "action_result": action_result}

@app.get("/tasks", response_model=List[Task])
async def get_tasks():
    """
    Endpoint para obtener todas las tareas.
    El frontend llamará a esto después de cada comando para refrescar la lista.
    """
    # Asegurarse de que db_manager está inicializado antes de usarlo
    if db_manager is None:
        raise HTTPException(status_code=500, detail="Error de base de datos: Conexión no establecida.")
    tasks = db_manager.get_all_tasks()
    return tasks

# Para cerrar la conexión a MongoDB cuando la aplicación se detiene
@app.on_event("shutdown")
async def shutdown_event():
    """Cierra la conexión a MongoDB al apagar la aplicación."""
    if db_manager:
        db_manager.close_connection()

