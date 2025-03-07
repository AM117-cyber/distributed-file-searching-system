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
# import win32com.client

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


client_ssl_context = ssl.create_default_context()
client_ssl_context.check_hostname = False
client_ssl_context.verify_mode = ssl.CERT_NONE


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
    #         print("[ERROR] Respuesta del servidor no es JSON válido.")
    #         return (False, False)
    # except Exception as e:
    #     print(f"[ERROR] No se pudo conectar o leer estado de {node_ip}: {e}")
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

    ring_stable, replication_ok = check_server_status(node_ip)
    if not ring_stable:
        print("[AVISO] El anillo no está estable todavía. Intente más tarde.")
        return

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Envolver el socket con SSL usando el contexto creado
        ssl_socket = client_ssl_context.wrap_socket(s, server_hostname=node_ip)
        ssl_socket.connect((node_ip, TCP_PORT))
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
            ssl_socket.close()
            return

        file_name = os.path.basename(file_path)
        file_type = file_name.split(".")[-1]
        file_size = os.path.getsize(file_path)

        print(f"[INFO] Subiendo archivo '{file_name}' ({file_type}, {file_size} bytes)...")
        message = f"{UPLOAD_FILE},{file_name},{file_type},{file_size}"
        ssl_socket.sendall(message.encode('utf-8'))

        ready = ssl_socket.recv(1024).decode('utf-8')
        if ready.strip() != 'READY':
            print("[AVISO] El nodo no está listo para recibir. Operación cancelada.")
            ssl_socket.close()
            return

        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(1024000)
                if not chunk:
                    break
                ssl_socket.sendall(chunk)

        response = ssl_socket.recv(1024).decode('utf-8')
        print(f"[INFO] Respuesta del servidor: {response}")
        ssl_socket.close()
    except Exception as e:
        print(f"[ERROR] Error durante la subida: {e}")
        ssl_socket.close()

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
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ssl_socket = client_ssl_context.wrap_socket(s, server_hostname=node_ip)
        ssl_socket.connect((node_ip, TCP_PORT))
        print(f"[INFO] Conectado al nodo {node_ip}:{TCP_PORT} para búsqueda de archivo.")
    except Exception as e:
        print(f"[ERROR] No se pudo conectar a {node_ip}: {e}")
        return

    try:
        file_type = command[1]
        file_name = command[0]

        print(f"[INFO] Solicitando búsqueda de '{file_name}' (tipo '{file_type}')...")
        message = f"{SEARCH_FILE},{file_name},{file_type}"
        ssl_socket.sendall(message.encode('utf-8'))

        data = ssl_socket.recv(1024).decode('utf-8')
        try:
            results = eval(data)
        except Exception as e:
            print(f"[ERROR] Error procesando resultados de búsqueda: {e}")
            ssl_socket.close()
            return

        if not results:
            print("[AVISO] No se encontraron resultados.")
            ssl_socket.close()
            return

        print("[INFO] Resultados de búsqueda:")
        for idx, result in enumerate(results, start=1):
            print(f"  {idx}. {result['name']} ({result['type']}) - Nodo: {result['ip']} (hash: {result['hash']})")

            prompt = (
                "\nInsert the number corresponding to the action you want to perform next:\n"
                " 1- Download one of the files\n"
                " 2- Preview one of the files"
                " 3- exit\n"
            )
        operation = input(prompt)
        if operation != "1" and operation != "2":
                # print("[ERROR] Invalid action.")
                ssl_socket.close()
                return


        print("[INFO] Resultados de búsqueda:")
        for idx, result in enumerate(results, start=1):
                print(f"  {idx}. {result['name']} ({result['type']}) - Nodo: {result['ip']} (hash: {result['hash']})")

        selection = input("Insert the file number: ")
        try:
            index = int(selection) - 1
            if not (0 <= index < len(results)):
                raise ValueError
        except:
            print("[ERROR] Número de archivo inválido.")
            ssl_socket.close()
            return

        # Cerrar socket de búsqueda
        ssl_socket.close()

        selected_hash = results[index]['hash']
        # En el server el "DOWNLOAD_FILE" se hace con el hash para ubicar al responsable

        # 2) Reconectarnos (o reusar) con node_ip (o con results[index]['ip'],
        #    pero se asume el server reenvía si no es el responsable)
        node_ip = discover_node()
        if node_ip is None:
            print("[AVISO] No se pudo descubrir ningún nodo activo. No se realizará la operación.")
            return

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            ssl_socket = client_ssl_context.wrap_socket(s, server_hostname=node_ip)
            ssl_socket.connect((node_ip, TCP_PORT))
            print(f"[INFO] Conectado al nodo {node_ip} para descargar el archivo.")
        except Exception as e:
            print(f"[ERROR] No se pudo conectar a {node_ip}: {e}")
            return

        if operation == "1":
            operation = DOWNLOAD_FILE
        else:
            operation = PREVIEW_FILE
        ssl_socket.sendall(f"{operation},{selected_hash},{results[index]['name']}.{results[index]['type']}".encode('utf-8'))
        size_str = ssl_socket.recv(1024).decode('utf-8')
        try:
            file_size = int(size_str.strip())
        except:
            print("[ERROR] No se recibió un tamaño válido.")
            ssl_socket.close()
            return

        if file_size == 0:
            print("[AVISO] El archivo no se encontró en este momento. Intente más tarde.")
            ssl_socket.close()
            return

        ssl_socket.sendall("ACK".encode('utf-8'))
        if operation == DOWNLOAD_FILE:
            local_filename = os.path.join(DOWNLOADS_DIR, results[index]['name'])
            print(f"[INFO] Descargando el archivo y guardándolo en: {local_filename}")

            remainder = file_size
            with open(local_filename, 'wb') as f:
                while remainder > 0:
                    chunk = ssl_socket.recv(min(remainder, 1024000))
                    if not chunk:
                        break
                    f.write(chunk)
                    remainder -= len(chunk)

            if remainder > 0:
                print("[AVISO] La descarga se interrumpió.")
            else:
                print(f"[INFO] Archivo descargado y guardado exitosamente: {local_filename}")

            ssl_socket.close()
        else:
            mime_type, _ = mimetypes.guess_type(f"{results[index]['name']}.{results[index]['type']}")
            lname = get_preview_name(mime_type)
            if lname == "":
                ssl_socket.close()
                return
            local_filename = os.path.join(PREVIEW_DIR, lname)
            print(f"[INFO] Descargando el preview del archivo y guardándolo en: {local_filename}")
            remainder = file_size
            with open(local_filename, 'wb') as f:
                while remainder > 0:
                    chunk = ssl_socket.recv(min(remainder, 1024000))
                    if not chunk:
                        break
                    f.write(chunk)
                    remainder -= len(chunk)
            if remainder > 0:
                print("[AVISO] La descarga se interrumpió.")
            else:
                print(f"[INFO] Archivo descargado y guardado exitosamente: {local_filename}")

            ssl_socket.close()
            # Después de descargar el preview y guardarlo en local_filename...
            with open(local_filename, 'rb') as f:
                preview = f.read()

            # Ahora, en lugar de hacer preview.endswith(".txt"),
            # comprobamos la extensión del archivo usando local_filename.
            if local_filename.endswith(".txt"):
                with open(local_filename, 'r', encoding='utf-8') as file:
                    print(file.read())
            elif mime_type and mime_type.startswith('image'):
                with Image.open(local_filename) as img:
                    img.show()
            elif mime_type and mime_type.startswith('audio'):
                try:
                    # Se asume que 'preview' es el nombre del archivo
                    if local_filename:
                        print(f"Playing audio preview: {local_filename}")
                        if platform.system() == "Windows":
                            os.startfile(local_filename)
                        elif platform.system() == "Darwin":
                            subprocess.run(["open", local_filename])
                        else:
                            subprocess.run(["xdg-open", local_filename])
                    else:
                        print("Audio preview could not be created.")
                except Exception as e:
                    print(f"An error occurred while playing the audio preview: {e}")
            elif mime_type and mime_type.startswith('video'):
                if local_filename:
                    print(f"Playing video preview: {local_filename}")
                    if platform.system() == "Windows":
                        os.startfile(local_filename)
                    elif platform.system() == "Darwin":
                        subprocess.run(["open", local_filename])
                    else:
                        subprocess.run(["xdg-open", local_filename])
                else:
                    print("Video preview could not be created.")




    except Exception as e:
            print(f"[ERROR] Error al descargar el archivo: {e}")
            ssl_socket.close()

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
