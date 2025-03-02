import os
import socket
import struct
import time
import streamlit as st



CLIENT_FILES_DIR = "/app/client_files"
DOWNLOADS_DIR = "/app/downloads"

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

def upload_file(file):
    """
    Procesa el comando 'subir <ruta_archivo>' y sube el archivo al nodo descubierto.
    Se reintenta la operación cada 5 segundos hasta completarse correctamente.
    Se usan archivos ubicados en CLIENT_FILES_DIR.
    """
    while True:
        node_ip = discover_node()
        if node_ip is None:
            print("[AVISO] No se pudo descubrir ningún nodo activo. Reintentando en 5 segundos...")
            time.sleep(5)
            continue

        # section to handle connection with chord ring
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.setblocking(True)
            client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            client_socket.connect((node_ip, TCP_PORT))
            print(f"[INFO] Conectado al nodo {node_ip}:{TCP_PORT} para subir el archivo.")
        except Exception as e:
            print(f"[AVISO] Error de conexión a {node_ip}: {e}. Reintentando en 5 segundos...")
            time.sleep(5)
            continue

        # extract file to upload
        try:
            # _, file_path = file.split(" ", 1)
            # # Si la ruta no es absoluta, se asume que está en CLIENT_FILES_DIR.
            # if not os.path.isabs(file_path):
            #     file_path = os.path.join(CLIENT_FILES_DIR, file_path)
            # if not os.path.exists(file_path):
            #     print(f"[ERROR] Archivo no encontrado en {CLIENT_FILES_DIR}.")
            #     client_socket.close()
            #     return
            file_path = os.path.join(CLIENT_FILES_DIR, file.name)
            with open(file_path, "wb") as f:
                f.write(file.getbuffer())  # Save file to the designated folder
            file_name = os.path.basename(file_path)
            file_type = file_name.split(".")[-1]
            file_size = os.path.getsize(file_path)

            print(f"[INFO] Subiendo archivo '{file_name}' ({file_type}, {file_size} bytes)...")
            message = f"{UPLOAD_FILE},{file_name},{file_type},{file_size}"
            client_socket.sendall(message.encode('utf-8'))

            ready = client_socket.recv(1024).decode('utf-8')
            if ready.strip() != 'READY':
                print("[AVISO] El nodo no está listo para recibir. Reintentando en 5 segundos...")
                client_socket.close()
                time.sleep(5)
                continue

            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(1024000)
                    if not chunk:
                        break
                    client_socket.sendall(chunk)

            response = client_socket.recv(1024).decode('utf-8')
            print(f"[INFO] Respuesta del servidor: {response}")
            client_socket.close()
            st.session_state.action = None
            return  # Operación completada correctamente
        except Exception as e:
            print(f"[AVISO] Error durante la subida: {e}. Reintentando en 5 segundos...")
            client_socket.close()
            time.sleep(5)
            continue

def search_file(file_name, file_type):
    """
    Procesa el comando 'descargar <nombre_archivo> [tipo_archivo]' y descarga el archivo
    desde el nodo que lo posee. Se reintenta la operación cada 5 segundos hasta completarse.
    Los archivos se guardan en CLIENT_FILES_DIR.
    """
    while True:
        node_ip = discover_node()
        if node_ip is None:
            print("[AVISO] No se pudo descubrir ningún nodo activo. Reintentando en 5 segundos...")
            time.sleep(5)
            continue
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.setblocking(True)
            client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            client_socket.connect((node_ip, TCP_PORT))
            print(f"[INFO] Conectado al nodo {node_ip}:{TCP_PORT} para búsqueda de archivo.")
        except Exception as e:
            print(f"[AVISO] Error de conexión a {node_ip}: {e}. Reintentando en 5 segundos...")
            time.sleep(5)
            continue

        try:
            print(f"[INFO] Solicitando búsqueda de '{file_name}' (tipo '{file_type}')...")
            message = f"{SEARCH_FILE},{file_name},{file_type}"
            client_socket.sendall(message.encode('utf-8'))

            data = client_socket.recv(1024).decode('utf-8')
            try:
                results = eval(data)
            except Exception as e:
                print(f"[AVISO] Error procesando resultados de búsqueda: {e}. Reintentando en 5 segundos...")
                client_socket.close()
                time.sleep(5)
                continue

            if not results:
                print("[AVISO] No se encontraron resultados. Reintentando en 5 segundos...")
                client_socket.close()
                time.sleep(5)
                continue
            client_socket.close()
            return results
        
        except Exception as e:
            print(f"[AVISO] Error al buscar archivos: {e}. Reintentando en 5 segundos...")
            client_socket.close()
            time.sleep(5)
            continue

def download_file(file_hash, file_name, file_type):

    while True:
        node_ip = discover_node()
        if node_ip is None:
            print("[AVISO] No se pudo descubrir ningún nodo activo. Reintentando en 5 segundos...")
            time.sleep(5)
            continue

        # section to handle connection with chord ring
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.setblocking(True)
            client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            client_socket.connect((node_ip, TCP_PORT))
            print(f"[INFO] Conectado al nodo {node_ip}:{TCP_PORT} para subir el archivo.")
        except Exception as e:
            print(f"[AVISO] Error de conexión a {node_ip}: {e}. Reintentando en 5 segundos...")
            time.sleep(5)
            continue


        client_socket.sendall(f"{DOWNLOAD_FILE},{file_hash}".encode('utf-8'))
        size_str = client_socket.recv(1024).decode('utf-8')
        try:
                file_size = int(size_str.strip())
        except Exception as e:
                print(f"[AVISO] Error recibiendo tamaño de archivo: {e}. Reintentando en 5 segundos...")
                client_socket.close()
                time.sleep(5)
                continue

        client_socket.sendall("ACK".encode('utf-8'))

        local_filename = os.path.join(DOWNLOADS_DIR, f"{file_name}.{file_type}")
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
            print("[AVISO] La descarga se interrumpió. Reintentando en 5 segundos...")
            client_socket.close()
            time.sleep(5)
            continue
        print(f"[INFO] Archivo descargado y guardado exitosamente: {local_filename}")
        client_socket.close()
        return  # Operación completada correctamente

def client_program():
    print("[INFO] Cliente iniciado.")
    try:
        while True:
            # Upload Section
            st.header("Upload a File")
            uploaded_file = st.file_uploader("Choose a file")
            if uploaded_file and st.button("Upload"):
                upload_file(uploaded_file)
                st.session_state.action = UPLOAD_FILE
            
            # prompt = (
            #     "\nOptions:\n"
            #     "  upload <path>   (file in CLIENT_FILES_DIR: " + CLIENT_FILES_DIR + ")\n"
            #     "  download <name>.<tipe>\n"
            #     "  exit\n"
            # )
            # command = input(prompt).strip()
            # if command.startswith("upload"):
            #     upload_file(command)

            # elif command.startswith("download"):
            #     search_file(command)
            # elif command.startswith("exit"):
            #     break
            # else:
            #     print("[ERROR] Invalid option.")

                        # Search Section
            st.header("Search for Files")
            file_name = st.text_input("Enter file name")
            file_type = st.text_input("Enter file type")
            if st.button("Search") and st.session_state.action != UPLOAD_FILE:
                st.session_state.action = SEARCH_FILE
                # Get the search results
                results = search_file(file_name, file_type)

                if results:
                    st.session_state.action = None
                # Create a mapping of display strings to actual results
                    display_options = [f"{result['name']} - {result['type']}" for result in results]

                    # Show a dropdown for selecting a file by its name and type
                    selected_display = st.selectbox("Select a file to download", display_options)

                    # Map the selected display string back to the actual result
                    if selected_display:
                        selected_result = next((result for result in results if f"{result['name']} - {result['type']}" == selected_display), None)

                        # Display the selected file details (optional)
                    if selected_result:
                        st.write("You selected:")
                        st.json(selected_result)  # Display details of the selected file

                        if st.button("Download") and not st.session_state.action:
                            download_file(selected_result['hash'], selected_result['name'])

            # Close connection
            if st.button("Disconnect"):
                break


    finally:
        print("[INFO] Cliente finalizado.")

if __name__ == "__main__":
    client_program()
