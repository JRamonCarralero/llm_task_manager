import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from bson.objectid import ObjectId
from datetime import datetime

class MongoDBManager:
    def __init__(self):
        # Obtener la URI de MongoDB de las variables de entorno
        # Asegúrate de que tu archivo .env tenga MONGO_URI="mongodb://localhost:27017/" (o tu URI de Atlas)
        self.mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
        self.client = None
        self.db = None
        self.connect()

    def connect(self):
        """Establece la conexión con la base de datos MongoDB."""
        try:
            self.client = MongoClient(self.mongo_uri)
            # Intenta una operación para verificar la conexión
            self.client.admin.command('ping')
            self.db = self.client.task_manager_db # Nombre de tu base de datos
            print("Conexión a MongoDB establecida con éxito.")
        except ConnectionFailure as e:
            print(f"Error al conectar a MongoDB: {e}")
            # Puedes decidir si quieres relanzar la excepción o manejarla de otra manera
            raise

    def close_connection(self):
        """Cierra la conexión con la base de datos MongoDB."""
        if self.client:
            self.client.close()
            print("Conexión a MongoDB cerrada.")

    def add_task(self, description: str, start_date: str = None, status: str = "pending") -> str:
        """Añade una nueva tarea a la base de datos."""
        # CORRECCIÓN: Usar 'is None' para comprobar el objeto de la base de datos
        if self.db is None:
            print("Error: No hay conexión a la base de datos.")
            return None
        
        task_data = {
            "description": description,
            "created_at": datetime.now(),
            "status": status # Usar el status proporcionado o el default
        }
        if start_date:
            task_data["start_date"] = start_date

        try:
            result = self.db.tasks.insert_one(task_data)
            return str(result.inserted_id)
        except Exception as e:
            print(f"Error al añadir tarea: {e}")
            return None

    def get_all_tasks(self) -> list:
        """
        Recupera todas las tareas de la base de datos.
        Asegura que el campo 'status' siempre sea válido.
        """
        # CORRECCIÓN: Usar 'is None' para comprobar el objeto de la base de datos
        if self.db is None:
            print("Error: No hay conexión a la base de datos.")
            return []

        tasks = []
        valid_statuses = {"pending", "completed", "in_progress", "cancelled"}
        try:
            for task_doc in self.db.tasks.find():
                # Convertir ObjectId a string para el frontend
                task_doc["_id"] = str(task_doc["_id"])
                
                # Validar y corregir el campo 'status'
                current_status = task_doc.get("status")
                if current_status not in valid_statuses:
                    print(f"Advertencia: Tarea con ID {task_doc['_id']} tiene un estado inválido '{current_status}'. Estableciendo a 'pending'.")
                    task_doc["status"] = "pending" # Establecer un valor por defecto válido
                
                # Asegurar que created_at sea un string ISO si no lo es
                if isinstance(task_doc.get("created_at"), datetime):
                    task_doc["created_at"] = task_doc["created_at"].isoformat()
                
                tasks.append(task_doc)
            return tasks
        except Exception as e:
            print(f"Error al obtener todas las tareas: {e}")
            return []

    def update_task(self, task_id: str, description: str = None, start_date: str = None, status: str = None) -> bool:
        """Actualiza una tarea existente por su ID."""
        # CORRECCIÓN: Usar 'is None' para comprobar el objeto de la base de datos
        if self.db is None:
            print("Error: No hay conexión a la base de datos.")
            return False

        update_fields = {}
        if description:
            update_fields["description"] = description
        if start_date:
            update_fields["start_date"] = start_date
        if status:
            # Opcional: añadir validación aquí también si el status viene del usuario
            valid_statuses = {"pending", "completed", "in_progress", "cancelled"}
            if status in valid_statuses:
                update_fields["status"] = status
            else:
                print(f"Advertencia: Intento de actualizar tarea {task_id} con estado inválido '{status}'. Ignorando el cambio de estado.")
                return False # O manejar de otra forma, por ejemplo, lanzar una excepción

        if not update_fields:
            return False # No hay campos para actualizar

        try:
            result = self.db.tasks.update_one(
                {"_id": ObjectId(task_id)},
                {"$set": update_fields}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error al actualizar tarea {task_id}: {e}")
            return False

    def delete_task(self, task_id: str) -> bool:
        """Elimina una tarea por su ID."""
        # CORRECCIÓN: Usar 'is None' para comprobar el objeto de la base de datos
        if self.db is None:
            print("Error: No hay conexión a la base de datos.")
            return False
        try:
            result = self.db.tasks.delete_one({"_id": ObjectId(task_id)})
            return result.deleted_count > 0
        except Exception as e:
            print(f"Error al eliminar tarea {task_id}: {e}")
            return False

