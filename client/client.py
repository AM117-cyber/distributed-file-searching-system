import mimetypes
import os
import socket
import struct
import time

import tempfile
from PIL import Image
from moviepy import VideoFileClip
from pydub import AudioSegment
from pydub.playback import play
from docx import Document
from openpyxl import load_workbook
import PyPDF2
import win32com.client

import subprocess
import platform


CLIENT_FILES_DIR = "/app/client_files"
DOWNLOADS_DIR = "/app/downloads"
PREVIEW_DIR = "/app/previews"

if not os.path.exists(CLIENT_FILES_DIR):
    os.makedirs(CLIENT_FILES_DIR, exist_ok=True)
    print(f"[INFO] Se ha creado la carpeta de archivos a subir: {CLIENT_FILES_DIR}")
if not os.path.exists(DOWNLOADS_DIR):
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    print(f"[INFO] Se ha creado la carpeta de descargas: {DOWNLOADS_DIR}")


MULTICAST_GROUP = '224.0.0.1'
MULTICAST_PORT = 10000
TCP_PORT = 8001

UPLOAD_FILE = 10
DOWNLOAD_FILE = 12
SEARCH_FILE = 11
PREVIEW_FILE = 20

def get_preview_name(mime_type):

        if mime_type and mime_type.startswith('text'):
            return "text_preview"
        elif mime_type:
            return "code_preview"
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

    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.setblocking(True)
        client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        client_socket.connect((node_ip, TCP_PORT))

        # Enviar operación GET_STATUS (99) sin datos extra
        message = f"99,"
        client_socket.sendall(message.encode('utf-8'))

        resp_data = client_socket.recv(2048).decode('utf-8')
        client_socket.close()

        try:
            status_dict = loads(resp_data)  # Ej: {"ring_stable": true, "replication_ok": false}
            ring_stable = status_dict.get("ring_stable", False)
            replication_ok = status_dict.get("replication_ok", False)
            return ring_stable, replication_ok
        except JSONDecodeError:
            print("[ERROR] Respuesta del servidor no es JSON válido.")
            return (False, False)
    except Exception as e:
        print(f"[ERROR] No se pudo conectar o leer estado de {node_ip}: {e}")
        return (False, False)


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
        print("Esperando respuesta de un nodo...")
        while True:
            data, addr = sock.recvfrom(1024)
            if data.decode('utf-8').strip() == "DISCOVER_NODE":
                continue
            node_ip = data.decode('utf-8').strip()
            print(f"[INFO] Nodo descubierto: {node_ip}")
            break
    except socket.timeout:
        print("[ERROR] No se recibió respuesta de ningún nodo.")
    finally:
        sock.close()
    return node_ip

def upload_file(command):
    node_ip = discover_node()
    if node_ip is None:
        print("[AVISO] No se pudo descubrir ningún nodo activo. No se realizará la operación.")
        return

    # 1) Chequear estado del anillo
    ring_stable, replication_ok = check_server_status(node_ip)
    if not ring_stable:
        print("[AVISO] El anillo no está estable todavía. Intente más tarde.")
        return

    # *** Si llegamos aquí, el servidor dice que está estable
    # Proseguimos con la lógica de upload normal **una sola vez**:
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.setblocking(True)
        client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        client_socket.connect((node_ip, TCP_PORT))
        print(f"[INFO] Conectado al nodo {node_ip}:{TCP_PORT} para subir el archivo.")
    except Exception as e:
        print(f"[ERROR] No se pudo conectar a {node_ip}: {e}")
        return

    try:
        _, file_path = command.split(" ", 1)
        if not os.path.isabs(file_path):
            file_path = os.path.join(CLIENT_FILES_DIR, file_path)
        if not os.path.exists(file_path):
            print(f"[ERROR] Archivo no encontrado en {CLIENT_FILES_DIR}.")
            client_socket.close()
            return

        file_name = os.path.basename(file_path)
        file_type = file_name.split(".")[-1]
        file_size = os.path.getsize(file_path)

        print(f"[INFO] Subiendo archivo '{file_name}' ({file_type}, {file_size} bytes)...")
        message = f"{UPLOAD_FILE},{file_name},{file_type},{file_size}"
        client_socket.sendall(message.encode('utf-8'))

        ready = client_socket.recv(1024).decode('utf-8')
        if ready.strip() != 'READY':
            print("[AVISO] El nodo no está listo para recibir. Operación cancelada.")
            client_socket.close()
            return

        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(1024000)
                if not chunk:
                    break
                client_socket.sendall(chunk)

        response = client_socket.recv(1024).decode('utf-8')
        print(f"[INFO] Respuesta del servidor: {response}")
        client_socket.close()
    except Exception as e:
        print(f"[ERROR] Error durante la subida: {e}")
        client_socket.close()

def download_file(command):
    node_ip = discover_node()
    if node_ip is None:
        print("[AVISO] No se pudo descubrir ningún nodo activo. No se realizará la operación.")
        return

    ring_stable, replication_ok = check_server_status(node_ip)
    if not ring_stable:
        print("[AVISO] El anillo no está estable todavía. Intente más tarde.")
        return

    # *** Lógica normal de "buscar" y luego "descargar"

    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((node_ip, TCP_PORT))
        print(f"[INFO] Conectado al nodo {node_ip}:{TCP_PORT} para búsqueda de archivo.")
    except Exception as e:
        print(f"[ERROR] No se pudo conectar a {node_ip}: {e}")
        return

    try:
        file_type = command[1]
        file_name = command[0]

        print(f"[INFO] Solicitando búsqueda de '{file_name}' (tipo '{file_type}')...")
        message = f"{SEARCH_FILE},{file_name},{file_type}"
        client_socket.sendall(message.encode('utf-8'))

        data = client_socket.recv(1024).decode('utf-8')
        try:
            results = eval(data)
        except Exception as e:
            print(f"[ERROR] Error procesando resultados de búsqueda: {e}")
            client_socket.close()
            return

        if not results:
            print("[AVISO] No se encontraron resultados.")
            client_socket.close()
            return

        print("[INFO] Resultados de búsqueda:")
        for idx, result in enumerate(results, start=1):
            print(f"  {idx}. {result['name']} ({result['type']}) - Nodo: {result['ip']} (hash: {result['hash']})")

            prompt = (
                "\nInsert the number corresponding to the action you want to perform next:\n"
                " 1- Preview one of the files\n"
                " 2- Download one of the files\n"
                " 3- exit\n"
            )
        operation = input(prompt)
        if not (1 <= operation < 4):
                print("[ERROR] Invalid action.")
                client_socket.close()
                return
        if operation == "3":
            client_socket.close()
            return
        else:
            print("[INFO] Resultados de búsqueda:")
            for idx, result in enumerate(results, start=1):
                print(f"  {idx}. {result['name']} ({result['type']}) - Nodo: {result['ip']} (hash: {result['hash']})")

            selection = input("Insert the file number: ")
        try:
            index = int(selection) - 1
            if not (0 <= index < len(results)):
                raise ValueError
        except:
            print("[ERROR] Invalid file number.")
            client_socket.close()
            return

        # Cerrar socket de búsqueda
        client_socket.close()

        selected_hash = results[index]['hash']
        # Nota: Asumamos que en el server el "DOWNLOAD_FILE" se hace con el hash para ubicar al responsable

        # 2) Reconectarnos (o reusar) con node_ip (o con results[index]['ip'],
        #    pero se asume el server reenvía si no es el responsable)
        node_ip = discover_node()
        if node_ip is None:
            print("[AVISO] No se pudo descubrir ningún nodo activo. No se realizará la operación.")
            return

        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((node_ip, TCP_PORT))
            print(f"[INFO] Conectado al nodo {node_ip} para descargar el archivo.")
        except Exception as e:
            print(f"[ERROR] No se pudo conectar a {node_ip}: {e}")
            return
        if operation == "1":
            operation = DOWNLOAD_FILE
        else:
            operation = PREVIEW_FILE
        client_socket.sendall(f"{operation},{selected_hash}".encode('utf-8'))
        size_str = client_socket.recv(1024).decode('utf-8')
        try:
            file_size = int(size_str.strip())
        except:
            print("[ERROR] No se recibió un tamaño válido.")
            client_socket.close()
            return

        if file_size == 0:
            print("[AVISO] El archivo no se encontró en este momento. Intente más tarde.")
            client_socket.close()
            return

        client_socket.sendall("ACK".encode('utf-8'))
        if operation == DOWNLOAD_FILE:
            local_filename = os.path.join(DOWNLOADS_DIR, results[index]['name'])
            print(f"[INFO] Descargando el archivo y guardándolo en: {local_filename}")

            remainder = file_size
            with open(local_filename, 'wb') as f:
                while remainder > 0:
                    chunk = client_socket.recv(min(remainder, 1024000))
                    if not chunk:
                        break
                    f.write(chunk)
                    remainder -= len(chunk)

            if remainder > 0:
                print("[AVISO] La descarga se interrumpió.")
            else:
                print(f"[INFO] Archivo descargado y guardado exitosamente: {local_filename}")

            client_socket.close()
        else:
            mime_type, _ = mimetypes.guess_type(f"{results[index]['name']}.{results[index]['type']}")
            lname = get_preview_name(mime_type)
            if lname == "":
                client_socket.close()
                return
            local_filename = os.path.join(PREVIEW_DIR, lname)
            print(f"[INFO] Descargando el preview del archivo y guardándolo en: {local_filename}")
            remainder = file_size
            with open(local_filename, 'wb') as f:
                while remainder > 0:
                    chunk = client_socket.recv(min(remainder, 1024000))
                    if not chunk:
                        break
                    f.write(chunk)
                    remainder -= len(chunk)
            if remainder > 0:
                print("[AVISO] La descarga se interrumpió.")
            else:
                print(f"[INFO] Archivo descargado y guardado exitosamente: {local_filename}")

            client_socket.close()
            with open(local_filename, 'rb') as f:
                preview = f.read()
                    # Display the preview
            if preview.endswith(".txt"):
                with open(preview, 'r') as file:
                    print(file.read())
            elif mime_type and mime_type.startswith('image'):
                with Image.open(preview) as img:
                    img.show()
        # elif mime_type and mime_type.startswith('audio'):
        #     try:
        #         # Load the audio preview file
        #         audio = AudioSegment.from_file(preview)
        #         print("Playing audio preview...")
        #         play(audio)
        #     except Exception as e:
        #         print(f"An error occurred while playing the audio preview: {e}")
            elif mime_type and mime_type.startswith('audio'):
                try:
                #    Check if the audio preview was created
                    if preview:
                        print(f"Playing audio preview: {preview}")
                        # Use the system's default media player to play the audio
                        if platform.system() == "Windows":
                            os.startfile(preview)  # Open with the default player on Windows
                        elif platform.system() == "Darwin":  # macOS
                            subprocess.run(["open", preview])
                        else:  # Linux/Unix
                            subprocess.run(["xdg-open", preview])
                    else:
                        print("Audio preview could not be created.")
                except Exception as e:
                    print(f"An error occurred while playing the audio preview: {e}")


            elif mime_type and mime_type.startswith('video'):
                if preview:  # Ensure the preview was created successfully
                    print(f"Playing video preview: {preview}")
                # Use system's default media player to play the preview
                    if platform.system() == "Windows":
                        os.startfile(preview)  # Open with the default player on Windows
                    elif platform.system() == "Darwin":  # macOS
                        subprocess.run(["open", preview])
                    else:  # Linux/Unix
                        subprocess.run(["xdg-open", preview])
                else:
                    print("Video preview could not be created.")
        # elif mime_type and mime_type.startswith('video'):
        #     with VideoFileClip(preview) as video:
        #         print(f"Video preview ready at: {preview}")
        #         video.preview()


            
    except Exception as e:
            print(f"[ERROR] Error al descargar el archivo: {e}")
            client_socket.close()

def get_search_criteria():
    prompt = (
                "\nSelect the number corresponding to the type of search you want:\n"
                " 1- search by file name and file type\n"
                " 2- search by file name\n"
                " 3- search by file type\n"
                " 4- search all files\n"
                " 5- exit\n"
            )
    command = input(prompt).strip()
    if command == "1":
        prompt = (
                "Please insert the search criteria in the format: filename.filetype\n"              
                " Example: file1.txt\n"
            )
        command = input(prompt).strip()
        try:
            filetype = command.split('.')[-1]
            filename = command.split("."+filetype)[0]
            if filetype.strip() == "" or filename.strip() == "":
                print("[ERROR] Comando inválido.")
                return ["exit"]
        except:
            print("[ERROR] Comando inválido.")
            return ["exit"]
    elif command == "2":
        prompt = (
                "Please insert the file name\n"
            )
        filename = input(prompt).strip()
        if filename.strip() == "":
                print("[ERROR] Comando inválido.")
                return ["exit"]
        filetype = "*"
    elif command == "3":
        prompt = (
                "Please insert the file type\n"
            )
        filetype = input(prompt).strip()
        if filetype.strip() == "":
                print("[ERROR] Comando inválido.")
                return ["exit"]
        filename= "*"
    elif command == "4":
        filename = "*"
        filetype = "*"
    elif command == "5":
        return ["exit"]
    else:
        print("[ERROR] Invalid option.")
        return ["exit"]
    return [filename, filetype]

def client_program():
    output_folder = "previews"

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    print("[INFO] Cliente iniciado.")
    try:
        while True:
            prompt = (
                "\nOptions:\n"
                "  upload <path>   (file in CLIENT_FILES_DIR: " + CLIENT_FILES_DIR + ")\n"
                "  search \n"
                "  exit\n"
            )
            command = input(prompt).strip()
            if command.startswith("upload"):
                upload_file(command)
            elif command.startswith("search"):
                command = get_search_criteria()
                if command[0] == "exit":
                    continue
                download_file(command)

            elif command.startswith("exit"):
                break
            else:
                print("[ERROR] Invalid option.")
    finally:
        print("[INFO] Cliente finalizado.")

if __name__ == "__main__":
    client_program()
