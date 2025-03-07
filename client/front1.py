from time import sleep
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import threading

# import mimetypes
import mimetypes
import os
import socket
import struct
import time
import ssl
import tempfile
from PIL import Image
from moviepy import VideoFileClip
from pydub import AudioSegment
from pydub.playback import play
from docx import Document
from openpyxl import load_workbook
import PyPDF2

import subprocess
import platform


CLIENT_FILES_DIR = "/app/client_files"
DOWNLOADS_DIR = "/app/downloads"
PREVIEW_DIR = "/app/previews"

results_data = {}

if not os.path.exists(CLIENT_FILES_DIR):
    os.makedirs(CLIENT_FILES_DIR, exist_ok=True)
    messagebox.showinfo(f"[INFO] Se ha creado la carpeta de archivos a subir: {CLIENT_FILES_DIR}")
if not os.path.exists(DOWNLOADS_DIR):
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    messagebox.showinfo(f"[INFO] Se ha creado la carpeta de descargas: {DOWNLOADS_DIR}")


MULTICAST_GROUP = '224.0.0.1'
MULTICAST_PORT = 10000
TCP_PORT = 8001

UPLOAD_FILE = 10
DOWNLOAD_FILE = 12
SEARCH_FILE = 11
PREVIEW_FILE = 20

# Directory to save uploaded files
UPLOAD_DIRECTORY = "uploaded_files"

client_ssl_context = ssl.create_default_context()
client_ssl_context.check_hostname = False
client_ssl_context.verify_mode = ssl.CERT_NONE

# Ensure the upload directory exists
if not os.path.exists(UPLOAD_DIRECTORY):
    os.makedirs(UPLOAD_DIRECTORY)

# Global variables to track actions and threads
action_in_progress = False
current_thread = None

def get_preview_name(mime_type):

        if mime_type and mime_type.startswith('text'):
            return "text_preview"
        elif mime_type == 'application/pdf':
            return "pdf_preview"
        elif mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            return "docx_preview"
        elif mime_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
            return "xlsx_preview"
        elif mime_type and mime_type.startswith('image'):
            return "image_preview"
        elif mime_type and mime_type.startswith('audio'):
            return "audio_preview"
        elif mime_type and mime_type.startswith('video'):
            return "video_preview"
        elif mime_type:
            return "code_preview"
        else:
            print(f"Unsupported file type or file not found for")
            return ""


def check_server_status(node_ip):
    """
    Se conecta a 'node_ip:TCP_PORT' y solicita GET_STATUS (op=99).
    Devuelve (ring_stable, replication_ok) si todo va bien,
    o (False, False) si falla la conexión o el servidor no responde correctamente.
    """
    from json import loads, JSONDecodeError

    return (True, True)

    # try:
    #     ssl_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #     ssl_socket.setblocking(True)
    #     ssl_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    #     ssl_socket.connect((node_ip, TCP_PORT))

    #     # Enviar operación GET_STATUS (99) sin datos extra
    #     message = f"99,"
    #     ssl_socket.sendall(message.encode('utf-8'))

    #     resp_data = ssl_socket.recv(2048).decode('utf-8')
    #     ssl_socket.close()

    #     try:
    #         status_dict = loads(resp_data)  # Ej: {"ring_stable": true, "replication_ok": false}
    #         ring_stable = status_dict.get("ring_stable", False)
    #         replication_ok = status_dict.get("replication_ok", False)
    #         return ring_stable, replication_ok
    #     except JSONDecodeError:
    #         messagebox.showinfo("[ERROR] Respuesta del servidor no es JSON válido.")
    #         return (False, False)
    # except Exception as e:
    #     messagebox.showinfo(f"[ERROR] No se pudo conectar o leer estado de {node_ip}: {e}")
    #     return (False, False)


def discover_node():
    """
    Envía una solicitud de descubrimiento vía multicast y espera la respuesta de un nodo activo.
    Retorna la IP del nodo descubierto o None si no se recibe respuesta.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", MULTICAST_PORT))

    group = socket.inet_aton(MULTICAST_GROUP)
    mreq = struct.pack('4sL', group, socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    discover_message = b"DISCOVER_NODE"
    sock.sendto(discover_message, (MULTICAST_GROUP, MULTICAST_PORT))

    node_ip = None
    try:
        messagebox.showinfo("Esperando respuesta de un nodo...")
        while True:
            data, addr = sock.recvfrom(1024)
            if data.decode('utf-8').strip() == "DISCOVER_NODE":
                continue
            node_ip = data.decode('utf-8').strip()
            messagebox.showinfo(f"[INFO] Nodo descubierto: {node_ip}")
            break
    except socket.timeout:
        messagebox.showinfo("[ERROR] No se recibió respuesta de ningún nodo.")
    finally:
        sock.close()
    return node_ip


def handle_search_file_logic(file_type, file_name):
    node_ip = discover_node()
    if node_ip is None:
        messagebox.showinfo("[AVISO] No se pudo descubrir ningún nodo activo. No se realizará la operación.")
        return

    ring_stable, replication_ok = check_server_status(node_ip)
    if not ring_stable:
        messagebox.showinfo("[AVISO] El anillo no está estable todavía. Intente más tarde.")
        return

    # *** Lógica normal de "buscar" y luego "descargar"

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ssl_socket = client_ssl_context.wrap_socket(s, server_hostname=node_ip)
        ssl_socket.connect((node_ip, TCP_PORT))
        messagebox.showinfo(f"[INFO] Conectado al nodo {node_ip}:{TCP_PORT} para búsqueda de archivo.")
    except Exception as e:
        messagebox.showinfo(f"[ERROR] No se pudo conectar a {node_ip}: {e}")
        return

    try:

        messagebox.showinfo(f"[INFO] Solicitando búsqueda de '{file_name}' (tipo '{file_type}')...")
        message = f"{SEARCH_FILE},{file_name},{file_type}"
        ssl_socket.sendall(message.encode('utf-8'))

        data = ssl_socket.recv(1024).decode('utf-8')
        try:
            results = eval(data)
        except Exception as e:
            messagebox.showinfo(f"[ERROR] Error procesando resultados de búsqueda: {e}")
            ssl_socket.close()
            return

        if not results:
            messagebox.showinfo("[AVISO] No se encontraron resultados.")
            ssl_socket.close()
            return
        ssl_socket.close()
        return results

    except Exception as e:
            messagebox.showinfo(f"[ERROR] Error al descargar el archivo: {e}")
            ssl_socket.close()

def set_action_state(state):
    """Set the global action state."""
    global action_in_progress
    action_in_progress = state


def guard_action(func):
    """Decorator to prevent new actions when one is in progress."""
    def wrapper(*args, **kwargs):
        if action_in_progress:
            messagebox.showwarning("Action in Progress", "Another action is currently being performed. Please wait.")
        else:
            func(*args, **kwargs)
    return wrapper


def stop_current_action():
    """Stop the current action by terminating its thread."""
    global current_thread, action_in_progress
    if current_thread and current_thread.is_alive():
        messagebox.showinfo("Stopping", "Stopping the current action...")
        set_action_state(False)
        current_thread = None


def on_close(root):
    """Handle app closure and stop any ongoing actions."""
    if action_in_progress:
        stop_current_action()
    root.destroy()


@guard_action
def upload_file():
    """Allow the user to upload a file and save it locally."""
    def task():
        global current_thread
        set_action_state(True)
        file_path = filedialog.askopenfilename()
        messagebox.showinfo(f"Received path: {file_path}")
        node_ip = discover_node()
        if node_ip is None:
            messagebox.showinfo("[AVISO] No se pudo descubrir ningún nodo activo. No se realizará la operación.")
            return

        ring_stable, replication_ok = check_server_status(node_ip)
        if not ring_stable:
            messagebox.showinfo("[AVISO] El anillo no está estable todavía. Intente más tarde.")
            return

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Envolver el socket con SSL usando el contexto creado
            ssl_socket = client_ssl_context.wrap_socket(s, server_hostname=node_ip)
            ssl_socket.connect((node_ip, TCP_PORT))
            messagebox.showinfo(f"[INFO] Conectado al nodo {node_ip}:{TCP_PORT} para subir el archivo.")
        except Exception as e:
            messagebox.showinfo(f"[ERROR] No se pudo conectar a {node_ip}: {e}")
            return

        try:
            if not os.path.isabs(file_path):
                file_path = os.path.join(CLIENT_FILES_DIR, file_path)
            if not os.path.exists(file_path):
                messagebox.showinfo(f"[ERROR] Archivo no encontrado en {CLIENT_FILES_DIR}.")
                ssl_socket.close()
                return

            file_name = os.path.basename(file_path)
            file_type = file_name.split(".")[-1]
            file_size = os.path.getsize(file_path)

            messagebox.showinfo(f"[INFO] Subiendo archivo '{file_name}' ({file_type}, {file_size} bytes)...")
            message = f"{UPLOAD_FILE},{file_name},{file_type},{file_size}"
            ssl_socket.sendall(message.encode('utf-8'))

            ready = ssl_socket.recv(1024).decode('utf-8')
            if ready.strip() != 'READY':
                messagebox.showinfo("[AVISO] El nodo no está listo para recibir. Operación cancelada.")
                ssl_socket.close()
                return

            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(1024000)
                    if not chunk:
                        break
                    ssl_socket.sendall(chunk)

            response = ssl_socket.recv(1024).decode('utf-8')
            messagebox.showinfo(f"[INFO] Respuesta del servidor: {response}")
            ssl_socket.close()
        except Exception as e:
            messagebox.showinfo(f"[ERROR] Error durante la subida: {e}")
            ssl_socket.close()
        set_action_state(False)
        current_thread = None

    global current_thread
    current_thread = threading.Thread(target=task)
    current_thread.start()




@guard_action
def search_files(file_name, file_type, result_listbox):
    """Search for files in the upload directory by name and/or type."""
    def task():
        global current_thread
        set_action_state(True)
        result_listbox.delete(0, tk.END)  # Clear previous results




####### Showing results#############33
        if file_type == "":
            file_type = "*"
        if file_name == "":
            file_name = "*"
        results = handle_search_file_logic(file_type, file_name)
        if results:
            displayed_hashes = set()  # To keep track of unique hashes
            for idx, result in enumerate(results, start=1):
                full_name = f"{result['name']}.{result['type']}"
                results_data[idx] = [result['hash'], result['type'], result['name']]
                if result['hash'] not in displayed_hashes:  # Check if the hash is new
                    displayed_hashes.add(result['hash'])   # Add the new hash to the set
                    formatted_result = (
                        f"{idx}. {result['name']}- "
                        f"Nodo: {result['ip']}"
                    )
                    result_listbox.insert(tk.END, formatted_result)

        else:
            messagebox.showwarning("No Results", "No files match your search.")
        set_action_state(False)
        current_thread = None

    global current_thread
    current_thread = threading.Thread(target=task)
    current_thread.start()


@guard_action
def preview_file(selected_result):
    """Display the contents of the selected file in a popup window."""
    def task():
        global current_thread
        set_action_state(True)
    # Assuming the result in result_listbox is formatted as: "1. Name (Type) - Nodo: IP (hash: Hash)"
        if not selected_result:
            return
            # Extract the fields from the selected result string
        parts = selected_result.split(".")  # Split by " - "
        index = int(parts[0])
        list = results_data[index]
        file_hash = list[0]
        file_type = list[1]
        file_name = list[2]

        # En el server el "DOWNLOAD_FILE" se hace con el hash para ubicar al responsable

        # 2) Reconectarnos (o reusar) con node_ip (o con results[index]['ip'],
        #    pero se asume el server reenvía si no es el responsable)
        node_ip = discover_node()
        if node_ip is None:
            messagebox.showinfo("[AVISO] No se pudo descubrir ningún nodo activo. No se realizará la operación.")
            return

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            ssl_socket = client_ssl_context.wrap_socket(s, server_hostname=node_ip)
            ssl_socket.connect((node_ip, TCP_PORT))
            messagebox.showinfo(f"[INFO] Conectado al nodo {node_ip} para descargar el archivo.")
        except Exception as e:
            messagebox.showinfo(f"[ERROR] No se pudo conectar a {node_ip}: {e}")
            return

        operation = PREVIEW_FILE
        ssl_socket.sendall(f"{operation},{file_hash},{file_name}.{file_type}".encode('utf-8'))
        size_str = ssl_socket.recv(1024).decode('utf-8')
        try:
            file_size = int(size_str.strip())
        except:
            messagebox.showinfo("[ERROR] No se recibió un tamaño válido.")
            ssl_socket.close()
            return

        if file_size == 0:
            messagebox.showinfo("[AVISO] El archivo no se encontró en este momento. Intente más tarde.")
            ssl_socket.close()
            return
        try:
            ssl_socket.sendall("ACK".encode('utf-8'))

            mime_type, _ = mimetypes.guess_type(f"{file_name}.{file_type}")
            lname = get_preview_name(mime_type)
            if lname == "":
                ssl_socket.close()
                return
            a= f"{lname}.{file_type}"
            local_filename = os.path.join(PREVIEW_DIR, a)
            messagebox.showinfo(f"[INFO] Descargando el preview del archivo y guardándolo en: {local_filename}")
            remainder = file_size
            with open(local_filename, 'wb') as f:
                while remainder > 0:
                    chunk = ssl_socket.recv(min(remainder, 1024000))
                    if not chunk:
                        break
                    f.write(chunk)
                    remainder -= len(chunk)
            if remainder > 0:
                messagebox.showinfo("[AVISO] La descarga se interrumpió.")
            else:
                messagebox.showinfo(f"[INFO] Archivo descargado y guardado exitosamente: {local_filename}")

            ssl_socket.close()
            if mime_type and mime_type.startswith('text'):
                try:
                    with open(local_filename, 'r', encoding='utf-8') as file:
                        preview_content = file.read()
                    print("[INFO] Contenido del preview:")
                    print(preview_content)
                except Exception as e:
                    print(f"[ERROR] No se pudo leer el preview de texto: {e}")


        except Exception as e:
            messagebox.showinfo(f"[ERROR] Error al descargar el archivo: {e}")
            ssl_socket.close()

        set_action_state(False)
        current_thread = None

    global current_thread
    current_thread = threading.Thread(target=task)
    current_thread.start()


@guard_action
def download_file(selected_result):
    """Display the contents of the selected file in a popup window."""
    def task():
        global current_thread
        set_action_state(True)
    # Assuming the result in result_listbox is formatted as: "1. Name (Type) - Nodo: IP (hash: Hash)"
        if not selected_result:
            return
            # Extract the fields from the selected result string
        parts = selected_result.split(".")  # Split by " - "
        index = int(parts[0])
        list = results_data[index]
        file_hash = list[0]
        file_type = list[1]
        file_name = list[2]

        # En el server el "DOWNLOAD_FILE" se hace con el hash para ubicar al responsable

        # 2) Reconectarnos (o reusar) con node_ip (o con results[index]['ip'],
        #    pero se asume el server reenvía si no es el responsable)
        node_ip = discover_node()
        if node_ip is None:
            messagebox.showinfo("[AVISO] No se pudo descubrir ningún nodo activo. No se realizará la operación.")
            return

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            ssl_socket = client_ssl_context.wrap_socket(s, server_hostname=node_ip)
            ssl_socket.connect((node_ip, TCP_PORT))
            messagebox.showinfo(f"[INFO] Conectado al nodo {node_ip} para descargar el archivo.")
        except Exception as e:
            messagebox.showinfo(f"[ERROR] No se pudo conectar a {node_ip}: {e}")
            return

        operation = DOWNLOAD_FILE
        ssl_socket.sendall(f"{operation},{file_hash},{file_name}.{file_type}".encode('utf-8'))
        size_str = ssl_socket.recv(1024).decode('utf-8')
        try:
            file_size = int(size_str.strip())
        except:
            messagebox.showinfo("[ERROR] No se recibió un tamaño válido.")
            ssl_socket.close()
            return

        if file_size == 0:
            messagebox.showinfo("[AVISO] El archivo no se encontró en este momento. Intente más tarde.")
            ssl_socket.close()
            return
        try:
            ssl_socket.sendall("ACK".encode('utf-8'))

            local_filename = os.path.join(DOWNLOADS_DIR, file_name)
            messagebox.showinfo(f"[INFO] Descargando el archivo y guardándolo en: {local_filename}")

            remainder = file_size
            with open(local_filename, 'wb') as f:
                while remainder > 0:
                    chunk = ssl_socket.recv(min(remainder, 1024000))
                    if not chunk:
                        break
                    f.write(chunk)
                    remainder -= len(chunk)

            if remainder > 0:
                messagebox.showinfo("[AVISO] La descarga se interrumpió.")
            else:
                messagebox.showinfo(f"[INFO] Archivo descargado y guardado exitosamente: {local_filename}")

            ssl_socket.close()


        except Exception as e:
            messagebox.showinfo(f"[ERROR] Error al descargar el archivo: {e}")
            ssl_socket.close()

        set_action_state(False)
        current_thread = None

    global current_thread
    current_thread = threading.Thread(target=task)
    current_thread.start()


# GUI setup
def create_app():
    """Create the Tkinter application."""
    root = tk.Tk()
    root.title("File Management System")
    root.geometry("800x600")  # Set default window size
    root.configure(bg="white")
    root.protocol("WM_DELETE_WINDOW", lambda: on_close(root))

    # Title label
    title_label = tk.Label(root, text="File Management System", font=("Arial", 20, "bold"), bg="white", fg="black")
    title_label.pack(pady=20)

    # Upload button
    upload_button = tk.Button(
        root, text="Upload File", command=upload_file,
        font=("Arial", 14), bg="#1f77b4", fg="white", activebackground="#125f87", activeforeground="white"
    )
    upload_button.pack(pady=10)

    # Search bars
    name_label = tk.Label(root, text="Insert File Name:", font=("Arial", 14), bg="white", fg="black")
    name_label.pack(pady=5)
    name_entry = tk.Entry(root, font=("Arial", 14), width=40)
    name_entry.pack(pady=5)

    type_label = tk.Label(root, text="Insert File Type (e.g., .txt):", font=("Arial", 14), bg="white", fg="black")
    type_label.pack(pady=5)
    type_entry = tk.Entry(root, font=("Arial", 14), width=40)
    type_entry.pack(pady=5)

    # Search results
    result_listbox = tk.Listbox(root, font=("Arial", 12), width=60, height=10)
    result_listbox.pack(pady=10)

    search_button = tk.Button(
        root, text="Search Files",
        command=lambda: search_files(name_entry.get(), type_entry.get(), result_listbox),
        font=("Arial", 14), bg="#2ca02c", fg="white", activebackground="#217821", activeforeground="white"
    )
    search_button.pack(pady=10)

    # Action buttons
    actions_frame = tk.Frame(root, bg="white")
    actions_frame.pack(pady=10)

    preview_button = tk.Button(
        actions_frame, text="Preview", font=("Arial", 14),
        command=lambda: preview_file(result_listbox.get(tk.ACTIVE)),
        bg="#ff7f0e", fg="white", activebackground="#c5620b", activeforeground="white"
    )
    preview_button.grid(row=0, column=0, padx=10)

    download_button = tk.Button(
        actions_frame, text="Download", font=("Arial", 14),
        command=lambda: download_file(result_listbox.get(tk.ACTIVE)),
        bg="#d62728", fg="white", activebackground="#a31e1e", activeforeground="white"
    )
    download_button.grid(row=0, column=1, padx=10)

    root.mainloop()


if __name__ == "__main__":
    create_app()
