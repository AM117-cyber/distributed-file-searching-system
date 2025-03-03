import os
import socket
import struct
import time
import json
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

# Operation codes
UPLOAD_FILE = 10
DOWNLOAD_FILE = 12
SEARCH_FILE = 11
GET_STATUS = 99  # Para consultar ring_stable, replication_ok


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
    sock.settimeout(5)  # 5s para recibir
    try:
        st.info("Buscando un nodo activo en la red (multicast)...")
        data, addr = sock.recvfrom(1024)
        # Ignorar si data=="DISCOVER_NODE" (lo que nosotros mismos enviamos)
        if data.decode('utf-8').strip() == "DISCOVER_NODE":
            pass
        else:
            node_ip = data.decode('utf-8').strip()
            st.success(f"Nodo descubierto: {node_ip}")
    except socket.timeout:
        st.error("No se recibió respuesta de ningún nodo (multicast).")
    finally:
        sock.close()
    return node_ip

def check_server_status(node_ip):
    """
    Se conecta a 'node_ip:TCP_PORT' y solicita GET_STATUS (op=99).
    Devuelve (ring_stable, replication_ok).
    Si falla, retorna (False, False).
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((node_ip, TCP_PORT))
        # mandar GET_STATUS
        message = f"{GET_STATUS},"
        s.sendall(message.encode('utf-8'))
        resp_data = s.recv(2048).decode('utf-8')
        s.close()
        status_dict = json.loads(resp_data)
        ring_stable = status_dict.get("ring_stable", False)
        replication_ok = status_dict.get("replication_ok", False)
        return (ring_stable, replication_ok)
    except Exception as e:
        st.error(f"No se pudo obtener estado del servidor {node_ip}: {e}")
        return (False, False)

def upload_file_to_node(node_ip, file):
    """
    Sube 'file' al nodo 'node_ip' (ya verificado que el anillo está estable).
    """
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((node_ip, TCP_PORT))
        st.info(f"Conectado al nodo {node_ip}:{TCP_PORT} para subir el archivo.")

        # Guardar el archivo en la carpeta local del cliente
        file_path = os.path.join(CLIENT_FILES_DIR, file.name)
        with open(file_path, "wb") as f_local:
            f_local.write(file.getbuffer())

        file_name = os.path.basename(file_path)
        file_type = file_name.split(".")[-1]
        file_size = os.path.getsize(file_path)

        st.info(f"Subiendo archivo '{file_name}' ({file_type}, {file_size} bytes)...")
        message = f"{UPLOAD_FILE},{file_name},{file_type},{file_size}"
        client_socket.sendall(message.encode('utf-8'))

        ready = client_socket.recv(1024).decode('utf-8')
        if ready.strip() != 'READY':
            st.warning("El nodo no está listo para recibir.")
            client_socket.close()
            return

        # Enviar el contenido en bloques
        with open(file_path, "rb") as f_local:
            while True:
                chunk = f_local.read(1024000)
                if not chunk:
                    break
                client_socket.sendall(chunk)

        response = client_socket.recv(1024).decode('utf-8')
        st.success(f"Respuesta del servidor: {response}")
        client_socket.close()
    except Exception as e:
        st.error(f"Error durante la subida: {e}")

def search_files_in_node(node_ip, file_name, file_type="*"):
    """
    Envía SEARCH_FILE al nodo 'node_ip' para buscar 'file_name' (opcionalmente por 'file_type').
    Retorna lista de resultados (diccionarios) o [].
    """
    results = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((node_ip, TCP_PORT))
        st.info(f"Conectado a {node_ip} para buscar '{file_name}' (tipo '{file_type}').")

        message = f"{SEARCH_FILE},{file_name},{file_type}"
        s.sendall(message.encode('utf-8'))

        data = s.recv(2048).decode('utf-8')
        s.close()

        try:
            results = eval(data)
        except:
            st.warning("No se pudo parsear la respuesta del servidor.")
            results = []
    except Exception as e:
        st.error(f"Error buscando archivos en {node_ip}: {e}")
    return results

def download_file_from_node(node_ip, file_hash, download_name):
    """
    Solicita DOWNLOAD_FILE,<file_hash> al nodo 'node_ip'.
    Guarda el archivo con nombre 'download_name' en DOWNLOADS_DIR.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((node_ip, TCP_PORT))
        st.info(f"Conectado a {node_ip} para descargar el archivo {download_name}.")

        s.sendall(f"{DOWNLOAD_FILE},{file_hash}".encode('utf-8'))
        size_str = s.recv(1024).decode('utf-8')
        try:
            file_size = int(size_str.strip())
        except:
            st.warning("No se recibió un tamaño de archivo válido.")
            s.close()
            return

        s.sendall("ACK".encode('utf-8'))

        local_filename = os.path.join(DOWNLOADS_DIR, download_name)
        st.info(f"Descargando el archivo y guardándolo en: {local_filename}")
        remainder = file_size
        with open(local_filename, 'wb') as f_local:
            while remainder > 0:
                chunk = s.recv(min(remainder, 1024000))
                if not chunk:
                    break
                f_local.write(chunk)
                remainder -= len(chunk)
        s.close()

        if remainder > 0:
            st.warning("La descarga se interrumpió o no se completó.")
        else:
            st.success(f"Archivo descargado exitosamente: {local_filename}")
    except Exception as e:
        st.error(f"Error al descargar el archivo: {e}")

def main():
    st.title("Cliente Chord con Streamlit")
    # 1) Descubrir un nodo solo una vez
    if "node_ip" not in st.session_state:
        st.session_state.node_ip = None

    if st.session_state.node_ip is None:
        st.write("Buscando un nodo de la red...")
        node_ip = discover_node()
        if node_ip:
            st.session_state.node_ip = node_ip
        else:
            st.warning("No se encontró nodo. Por favor, refresca la página.")
            st.stop()

    # 2) Chequear la estabilidad en un loop => 'Pantalla de cargando'
    #    Usamos un "while ring_stable is false" -> pero en Streamlit
    if "ring_stable" not in st.session_state:
        st.session_state.ring_stable = False

    check_interval = 2.0  # cada 2s re-chequeamos
    if not st.session_state.ring_stable:
        with st.spinner("Esperando que el anillo se estabilice..."):
            # Repetimos la consulta
            # (En Streamlit, un while True bloquearía la interfaz, así que
            #  podemos simularlo recargando la página con st.experimental_rerun
            #  o algo similar. Aquí haremos un approach simple:)
            ring_stable, replication_ok = check_server_status(st.session_state.node_ip)
            if ring_stable:
                st.session_state.ring_stable = True
                st.success("¡El anillo está estable! Puedes subir/buscar/descargar archivos.")
            else:
                time.sleep(check_interval)
                st.experimental_rerun()
        # cuando sale del spinner, ya ring_stable == True

    # Si llegamos aquí => anillo estable
    st.subheader("1. Subir un archivo")
    uploaded_file = st.file_uploader("Selecciona un archivo para subir:")
    if uploaded_file:
        if st.button("Subir"):
            upload_file_to_node(st.session_state.node_ip, uploaded_file)

    st.subheader("2. Buscar archivos")
    file_name = st.text_input("Nombre (parcial o completo)", "")
    file_type = st.text_input("Tipo (extensión o *):", "*")
    if st.button("Buscar"):
        if file_name.strip() == "" and file_type.strip() == "*":
            st.warning("Indica al menos un nombre o un tipo distinto de * para refinar la búsqueda.")
        else:
            results = search_files_in_node(st.session_state.node_ip, file_name, file_type)
            if results:
                st.write("Resultados encontrados:")
                for idx, r in enumerate(results):
                    st.write(f"{idx+1}. {r['name']} ({r['type']}) [Hash: {r['hash']}] - IP: {r['ip']}")
                # Seleccionar un índice para descargar
                download_index = st.number_input("Número de archivo a descargar (0 = ninguno)", min_value=0, max_value=len(results))
                if download_index != 0:
                    selected = results[download_index-1]
                    # Botón para descargar
                    if st.button("Descargar ese archivo"):
                        # Por convención, unimos su 'name' y 'type' para guardarlo
                        d_name = f"{selected['name']}.{selected['type']}"
                        download_file_from_node(st.session_state.node_ip, selected['hash'], d_name)
            else:
                st.info("No se encontraron archivos con esos criterios.")

    st.subheader("3. Finalizar")
    if st.button("Desconectar"):
        st.write("Cliente finalizado. Refresca la página si quieres reconectar.")
        st.stop()

if __name__ == "__main__":
    main()
