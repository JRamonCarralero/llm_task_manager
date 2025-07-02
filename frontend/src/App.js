import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './App.css'; // Para estilos básicos

const API_BASE_URL = 'http://localhost:5000'; // La URL de tu backend FastAPI

/**
 * La función principal de la aplicación, que renderiza la interfaz de usuario y gestiona el estado.
 *
 * Esta función se encarga de:
 *  1. Mostrar la interfaz de usuario, incluyendo un formulario para introducir comandos de texto.
 *  2. Renderizar una lista de tareas, con sus descripciones, fechas de inicio y estado.
 *  3. Procesar los comandos de texto introducidos por el usuario, llamando a la API de FastAPI.
 *  4. Mostrar mensajes de resultado para cada comando, como por ejemplo "Tarea creada correctamente" o "Error al procesar el comando".
 *  5. Refrescar la lista de tareas después de cada comando, si es necesario.
 */
function App() {
  const [tasks, setTasks] = useState([]);
  const [commandInput, setCommandInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(''); // Mensajes del sistema/LLM
  const [messageType, setMessageType] = useState(''); // 'success', 'error', 'info'

  // Efecto para cargar las tareas al inicio y después de cada comando
  useEffect(() => {
    fetchTasks();
  }, []);

/**
 * Fetches the list of tasks from the backend API and updates the state.
 *
 * This function will set the loading state to true, make an HTTP GET request
 * to the tasks endpoint, and update the tasks state with the retrieved data.
 * In case of an error, it logs the error and updates the message state with
 * an error message. The loading state is set to false once the request is
 * completed, regardless of success or failure.
 */
  const fetchTasks = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API_BASE_URL}/tasks`);
      setTasks(response.data);
    } catch (err) {
      console.error('Error fetching tasks:', err);
      setMessage('Error al cargar las tareas.');
      setMessageType('error');
    } finally {
      setLoading(false);
    }
  };

  /**
   * Processes the user's command input by calling the FastAPI backend API.
   * @param {Event} e The submit event of the command form.
   * @async
   */
  const handleCommandSubmit = async (e) => {
    e.preventDefault();
    if (!commandInput.trim()) {
      setMessage('Por favor, introduce un comando.');
      setMessageType('info');
      return;
    }

    setLoading(true);
    setMessage(''); // Limpiar mensajes anteriores
    setMessageType('');

    try {
      const response = await axios.post(`${API_BASE_URL}/command`, { command: commandInput });
      const { llm_interpretation, action_result } = response.data;

      // Mostrar el mensaje del resultado de la acción
      setMessage(action_result.message);
      setMessageType(action_result.status);

      // Si la acción no es 'unknown', refrescar la lista de tareas
      if (llm_interpretation.action !== 'unknown') {
        fetchTasks();
      }
      setCommandInput(''); // Limpiar el input después de enviar
    } catch (err) {
      console.error('Error processing command:', err.response ? err.response.data : err.message);
      setMessage(`Error al procesar el comando: ${err.response?.data?.detail || err.message}`);
      setMessageType('error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Gestor de Tareas con MCP y React</h1>
        <p>Introduce tus comandos de texto para gestionar tus tareas.</p>
      </header>

      <main className="App-main">
        <form onSubmit={handleCommandSubmit} className="command-form">
          <input
            type="text"
            value={commandInput}
            onChange={(e) => setCommandInput(e.target.value)}
            placeholder="Ej: crear la tarea 'Estudiar React' con estado 'pendiente'"
            disabled={loading}
            className="command-input"
          />
          <button type="submit" disabled={loading} className="command-button">
            {loading ? 'Procesando...' : 'Enviar Comando'}
          </button>
        </form>

        {message && (
          <div className={`message-box ${messageType}`}>
            {message}
          </div>
        )}

        <h2>Mis Tareas</h2>
        {loading && <p className="loading-text">Cargando tareas...</p>}
        {!loading && tasks.length === 0 && (
          <p className="no-tasks">No hay tareas para mostrar. ¡Crea una!</p>
        )}
        
        <ul className="task-list">
          {tasks.map((task) => (
            <li key={task.id} className={`task-item ${task.status}`}>
              <div className="task-details">
                <span className="task-description">{task.description}</span>
                {task.start_date && <span className="task-date">Inicio: {task.start_date}</span>}
                <span className={`task-status ${task.status}`}>{task.status.toUpperCase()}</span>
              </div>
              <div className="task-id">ID: {task._id}</div>
            </li>
          ))}
        </ul>
      </main>
    </div>
  );
}

export default App;

