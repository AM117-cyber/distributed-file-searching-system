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
        print("ENTERING DSICOVER NODE")
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
    st.title("P2P File Sharing Client")
    print("HOLA!!!!!")
    st.write("[INFO] EMPEZANDO")
    # Upload Section
    st.header("Upload a File")
    uploaded_file = st.file_uploader("Choose a file", key="file_uploader")  # ✅ Ensure a unique key
    if uploaded_file and st.button("Upload", key="upload_btn"):  
        upload_file(uploaded_file)
        st.session_state.action = UPLOAD_FILE
    
    # Search Section
    st.header("Search for Files")
    file_name = st.text_input("Enter file name", key="search_name")
    file_type = st.text_input("Enter file type", key="search_type")
    
    if st.button("Search", key="search_btn"):
        st.session_state.action = SEARCH_FILE
        results = search_file(file_name, file_type)
        if results:
            st.session_state.results = results  # Store results in session state
    
    # Display results if found
    if "results" in st.session_state and st.session_state.results:
        display_options = [f"{res['name']} - {res['type']}" for res in st.session_state.results]
        selected_display = st.selectbox("Select a file to download", display_options, key="file_select")

        # Find the selected file's details
        selected_result = next((res for res in st.session_state.results if f"{res['name']} - {res['type']}" == selected_display), None)

        if selected_result:
            st.write("You selected:")
            st.json(selected_result)  # Show details

            if st.button("Download", key="download_btn"):
                download_file(selected_result['hash'], selected_result['name'], selected_result['type'])
    
    # Disconnect Button
    if st.button("Disconnect", key="disconnect_btn"):
        st.session_state.action = None
        st.session_state.results = []
        st.write("[INFO] Disconnected.")
        

if __name__ == "__main__":
    client_program()