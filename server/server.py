import socket
import threading
import sys
import time
import hashlib
import random
from storage_layer import *
from replication import *

# Operation codes
FIND_SUCCESSOR = 1
FIND_PREDECESSOR = 2
GET_SUCCESSOR = 3
GET_PREDECESSOR = 4
NOTIFY = 5
CLOSEST_PRECEDING_FINGER = 7
UPLOAD_FILE = 10  # Código de operación para subir archivos
DOWNLOAD_FILE = 12
DELETE_FILE = 14
SAVE_REPLIC = 13




def getShaRepr(data: str):
    return int(hashlib.sha1(data.encode()).hexdigest(),16)

class ChordNodeReference:
    def __init__(self, ip: str, port: int = 8001):
        self.id = getShaRepr(ip)
        self.ip = ip
        self.port = port

    def _send_data(self, op: int, data: str = None) -> bytes:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.ip, self.port))
                s.sendall(f'{op},{data}'.encode('utf-8'))
                return s.recv(1024)
        except Exception as e:
            print(f"Error sending data: {e}")
            return b''

    def find_successor(self, id: int) -> 'ChordNodeReference':
        response = self._send_data(FIND_SUCCESSOR, str(id)).decode().split(',')
        return ChordNodeReference(response[1], self.port)

    def find_predecessor(self, id: int) -> 'ChordNodeReference':
        response = self._send_data(FIND_PREDECESSOR, str(id)).decode().split(',')
        return ChordNodeReference(response[1], self.port)

    @property
    def succ(self) -> 'ChordNodeReference':
        response = self._send_data(GET_SUCCESSOR).decode().split(',')
        return ChordNodeReference(response[1], self.port)

    @property
    def pred(self) -> 'ChordNodeReference':
        response = self._send_data(GET_PREDECESSOR).decode().split(',')
        return ChordNodeReference(response[1], self.port)

    def notify(self, node: 'ChordNodeReference'):
        self._send_data(NOTIFY, f'{node.id},{node.ip}')

    def closest_preceding_finger(self, id: int) -> 'ChordNodeReference':
        response = self._send_data(CLOSEST_PRECEDING_FINGER, str(id)).decode().split(',')
        return ChordNodeReference(response[1], self.port)

    def __str__(self) -> str:
        return f'{self.id},{self.ip},{self.port}'

    def __repr__(self) -> str:
        return self.__str__()


    def store_file(self, file_name: str, file_type: str, file_content: bytes) -> str:
        """Envía el archivo al nodo remoto para que lo almacene."""
        try:
            file_size = len(file_content)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.ip, self.port))
                # Se envía el mensaje inicial con los datos del archivo
                message = f"{UPLOAD_FILE},{file_name},{file_type},{file_size}"
                s.sendall(message.encode('utf-8'))
                # Se espera una respuesta de 'READY'
                ready = s.recv(1024).decode('utf-8')
                if ready == 'READY':
                    # Enviar el contenido en bloques (chunks)
                    for i in range(0, file_size, 1024000):
                        chunk = file_content[i:i+1024000]
                        s.sendall(chunk)
                # Recibir respuesta final del nodo remoto
                response = s.recv(1024).decode('utf-8')
                return response
        except Exception as e:
            print(f"Error en store_file en {self.ip}:{self.port} - {e}")
            return "ERROR"

     # Código de operación para descargar archivos

    def retrieve_file(self, file_key: str) -> dict:
        """Solicita al nodo remoto que recupere el archivo identificado por file_key."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.ip, self.port))
                s.sendall(f"{DOWNLOAD_FILE},{file_key}".encode('utf-8'))
                # Se espera recibir primero el tamaño del archivo
                file_size_str = s.recv(1024).decode('utf-8')
                file_size = int(file_size_str)
                # Se notifica que se está listo para recibir
                s.sendall("READY".encode('utf-8'))
                content = b""
                remaining = file_size
                while remaining > 0:
                    chunk = s.recv(min(1024000, remaining))
                    if not chunk:
                        break
                    content += chunk
                    remaining -= len(chunk)
                return {"key": file_key, "content": content}
        except Exception as e:
            print(f"Error en retrieve_file en {self.ip}:{self.port} - {e}")
            return None

    def delete_file(self, file_key: str) -> str:
        """Envía una solicitud para borrar un archivo en el nodo remoto."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.ip, self.port))
                s.sendall(f"{DELETE_FILE},{file_key}".encode('utf-8'))
                response = s.recv(1024).decode('utf-8')
                return response
        except Exception as e:
            print(f"Error en delete_file en {self.ip}:{self.port} - {e}")
            return "ERROR"



    def replicate_file(self, file_name: str, file_type: str, file_content: bytes, nodes: list) -> str:
        """Envía una solicitud de replicación al nodo remoto."""
        try:
            file_size = len(file_content)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.ip, self.port))
                # Preparar la lista de nodos como cadena separada por comas
                nodes_str = ",".join(nodes)
                message = f"{SAVE_REPLIC},{file_name},{file_type},{file_size},{nodes_str}"
                s.sendall(message.encode('utf-8'))
                ready = s.recv(1024).decode('utf-8')
                if ready == 'READY':
                    for i in range(0, file_size, 1024000):
                        chunk = file_content[i:i+1024000]
                        s.sendall(chunk)
                response = s.recv(1024).decode('utf-8')
                return response
        except Exception as e:
            print(f"Error en replicate_file en {self.ip}:{self.port} - {e}")
            return "ERROR"






class ChordNode:
    # Registro global de nodos: clave = (ip, port), valor = instancia de ChordNode
    registry = {}

    def __init__(self, ip: str, peerId=None, port: int = 8001, m: int = 160, db_path='files.db'):
        self.id = getShaRepr(ip)
        self.ip = ip
        self.port = port
        self.ref = ChordNodeReference(self.ip, self.port)
        self.pred = self.ref  # Inicialmente, el predecesor es el mismo nodo
        self.m = m  # Número de bits en el espacio de claves
        self.finger = [self.ref] * self.m  # Tabla de dedos
        self.lock = threading.Lock()
        self.storage = StorageLayer(db_path)  # Instancia de StorageLayer
        self.replication_manager = ReplicationManager(self)  # Instancia de ReplicationManager

        # Registrar la instancia en el registro global
        ChordNode.registry[(self.ip, self.port)] = self

        threading.Thread(target=self.stabilize, daemon=True).start()  # Hilo de estabilización
        threading.Thread(target=self.fix_fingers, daemon=True).start()  # Hilo de fix_fingers

        if peerId is not None:
            threading.Thread(target=self.join, args=(ChordNodeReference(peerId, self.port),), daemon=True).start()

        # Iniciar el servidor en un hilo separado para no bloquear la ejecución
        threading.Thread(target=self.start_server, daemon=True).start()

    def get_reference(self, ref: ChordNodeReference) -> 'ChordNode':
        """Retorna la instancia de ChordNode correspondiente a la referencia."""
        return ChordNode.registry.get((ref.ip, ref.port), None)
    @property
    def succ(self):
        print(self.finger[0])
        return self.finger[0]

    @succ.setter
    def succ(self, node: 'ChordNodeReference'):
        with self.lock:
            self.finger[0] = node

    def _inbetween(self, k: int, start: int, end: int) -> bool:
        """Check if k is in the interval [start, end)."""
        #print(end < start, start <= k, k < end)

        k = k % 2 ** self.m
        start = start % 2 ** self.m
        end = end % 2 ** self.m
        if end < start:
            return start <= k < end
        return start <= k or k < end

    def _inrange(self, k: int, start: int, end: int) -> bool:
        """Check if k is in the interval (start, end)."""
        _start = (start + 1) % 2 ** self.m
        return self._inbetween(k, _start, end)

    def _inbetweencomp(self, k: int, start: int, end: int) -> bool:
        """Check if k is in the interval (start, end]."""
        _end = (end - 1) % 2 ** self.m
        return self._inbetween(k, start, _end)

    def find_succ(self, id: int) -> 'ChordNodeReference':
        node = self.find_pred(id)  # Find predecessor of id
        return node.succ  # Return successor of that node

    def find_pred(self, id: int) -> 'ChordNodeReference':
        node = self
        if node.id == self.succ.id:
            return node
        print(f"in bteween {id}, {node.id} {node.succ.id} {self._inbetweencomp(id, node.id, node.succ.id)}")
        while not self._inbetweencomp(id, node.id, node.succ.id):
            node = node.closest_preceding_finger(id)
            if node.id == self.id:
                break
        print(f"closest finger: {node.id} {node.ip}")
        return node

    def closest_preceding_finger(self, id: int) -> 'ChordNodeReference':
        for i in range(self.m - 1, -1, -1):
            #if self.finger[i].id != self.id and self._inrange(self.finger[i].id, self.id, id):
            if self._inrange(self.finger[i].id, self.id, id):
                return self.finger[i] if self.finger[i].id != self.id else self
        return self

    def join(self, node: 'ChordNodeReference'):
        time.sleep(5)
        """Join a Chord network using 'node' as an entry point."""
        self.pred = self.ref
        print("before find succc")
        self.succ = node.find_successor(self.id)
        print(self.succ)

    def stabilize(self):
        """
        Regular check for correct Chord structure and file replication.
        """
        while True:
            try:
                if self.succ:
                    x = self.succ.pred
                    if x.id != self.id:
                        if self.succ.id == self.id or self._inrange(x.id, self.id, self.succ.id):
                            self.succ = x
                    self.succ.notify(self.ref)
            except Exception as e:
                logging.error(f"Error in stabilize: {e}")

            # Adding file replication process here
            self.replication_manager.stabilize_files()

            logging.info(f"successor: {self.succ} predecessor: {self.pred}")
            time.sleep(10)

    def notify(self, node: 'ChordNodeReference'):
        if node.id == self.id:
            return
        print(f"notify with node {node} self {self.ref} pred {self.pred}")
        if (self.pred.id == self.id) or self._inrange(node.id, self.pred.id, self.id):
            self.pred = node

    def fix_fingers(self):
        time.sleep(5)

        while True:
            self.next = random.randint(0,self.m-1)
            with self.lock:
                self.finger[self.next] = self.find_succ((self.id + 2 ** self.next) % (2 ** self.m))
            print(f'Finger table updated at index {self.next}: {self.finger[self.next]}')
            time.sleep(10)

    def start_server(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.ip, self.port))
            s.listen(10)

            while True:
                conn, addr = s.accept()
                #print(f'new connection from {addr}' )
                threading.Thread(target=self.serve_client, args=(conn,), daemon=True).start()

    def upload_file(self, name: str, file_type: str, content: bytes):
        """
        Uploads a file to the correct Chord node based on the computed hash of the name and type.
        """
        # Generate a routing key using the hash of name and type
        h_name_type = self.storage._hash_name_type(name, file_type)
        routing_key = int(h_name_type, 16) % (2**self.m)

        # Find the successor node responsible for this key
        responsible_node = self.find_succ(routing_key)

        # Check if the current node is responsible
        if responsible_node.id == self.id:
            # Store file locally
            key = self.storage.store_file(name, file_type, content)
            logging.info(f"File '{name}' stored locally under key {key}.")
            # After storing locally, replicate the file
            self.replication_manager.replicate_file(self.ref, key, {"name": name, "type": file_type, "content": content})
        else:
            # If not, send the file to the responsible node
            key = responsible_node.store_file(name, file_type, content)
            logging.info(f"File '{name}' sent to {responsible_node.ip} and stored under key {key}.")
            # Trigger replication from the responsible node
            responsible_node.replication_manager.replicate_file(responsible_node, key, {"name": name, "type": file_type, "content": content})
    # def upload_file(self, name: str, file_type: str, content: bytes):
    #     # Calcular clave de enrutamiento, hallar el nodo responsable, etc.
    #     h_name_type = self.storage._hash_name_type(name, file_type)
    #     routing_key = int(h_name_type, 16) % (2**self.m)
    #     responsible = self.find_succ(routing_key)
    #     # Obtener la instancia remota a través de la referencia:
    #     if responsible.id == self.id:
    #         # Si es este mismo nodo, almacenar localmente
    #         key = self.storage.store_file(name, file_type, content)
    #         print(f"Archivo {name} almacenado localmente con clave {key}.")
    #     else:
    #         # Si el nodo responsable es otro, se usa la llamada remota
    #         result = responsible.store_file(name, file_type, content)
    #         print(f"Archivo {name} enviado a {responsible.ip}:{responsible.port} con respuesta: {result}")


    def serve_client(self, conn: socket.socket):
        try:
            data = conn.recv(1024).decode('utf-8').split(',')
            if not data or not data[0]:
                conn.close()
                return

            option = int(data[0])
            data_resp = None

            # Operaciones del protocolo CHORD
            if option == FIND_SUCCESSOR:
                id_val = int(data[1])
                data_resp = self.find_succ(id_val)
            elif option == FIND_PREDECESSOR:
                id_val = int(data[1])
                data_resp = self.find_pred(id_val)
            elif option == GET_SUCCESSOR:
                data_resp = self.succ
            elif option == GET_PREDECESSOR:
                data_resp = self.pred
            elif option == NOTIFY:
                # data: NOTIFY, node_id, node_ip
                node_ref = ChordNodeReference(data[2], self.port)
                self.notify(node_ref)
            elif option == CLOSEST_PRECEDING_FINGER:
                id_val = int(data[1])
                data_resp = self.closest_preceding_finger(id_val)

            # Operaciones relacionadas con archivos:
            elif option == UPLOAD_FILE:
                # Formato: UPLOAD_FILE,file_name,file_type,file_size
                file_name = data[1]
                file_type = data[2]
                file_size = int(data[3])
                # Indicar que se está listo para recibir el contenido
                conn.sendall("READY".encode('utf-8'))
                file_content = b""
                remaining = file_size
                while remaining > 0:
                    chunk = conn.recv(min(1024000, remaining))
                    if not chunk:
                        break
                    file_content += chunk
                    remaining -= len(chunk)
                # Almacenar el archivo usando la capa de almacenamiento
                response = self.storage_layer.store_file(file_name, file_type, file_content)
                conn.sendall(response.encode('utf-8'))
                conn.close()
                return

            elif option == DOWNLOAD_FILE:
                # Formato: DOWNLOAD_FILE,file_key
                file_key = data[1]
                file_info = self.storage_layer.retrieve_file(file_key)
                if not file_info:
                    conn.sendall("0".encode('utf-8'))
                    conn.close()
                    return
                file_content = file_info["content"]
                file_size = len(file_content)
                # Enviar el tamaño del archivo
                conn.sendall(str(file_size).encode('utf-8'))
                # Esperar confirmación para empezar a enviar datos
                ack = conn.recv(1024)
                for i in range(0, file_size, 1024000):
                    chunk = file_content[i:i+1024000]
                    conn.sendall(chunk)
                conn.close()
                return

            elif option == DELETE_FILE:
                # Formato: DELETE_FILE,file_key
                file_key = data[1]
                response = self.storage_layer.delete_file(file_key)
                conn.sendall(response.encode('utf-8'))
                conn.close()
                return

            elif option == SAVE_REPLIC:
                # Formato: SAVE_REPLIC,file_name,file_type,file_size,node1,node2,...
                file_name = data[1]
                file_type = data[2]
                file_size = int(data[3])
                # Los nodos se pasan como parámetros separados a partir del índice 4
                nodes = data[4:]
                conn.sendall("READY".encode('utf-8'))
                file_content = b""
                remaining = file_size
                while remaining > 0:
                    chunk = conn.recv(min(1024000, remaining))
                    if not chunk:
                        break
                    file_content += chunk
                    remaining -= len(chunk)
                file_data = {"name": file_name, "type": file_type, "content": file_content, "nodes": nodes}
                # La replicación se maneja mediante el ReplicationManager
                response = self.replication_manager.replicate_file(self.ref, file_name, file_data)
                conn.sendall(response.encode('utf-8'))
                conn.close()
                return

            # Respuesta para operaciones del protocolo CHORD
            if data_resp:
                response = f"{data_resp.id},{data_resp.ip}"
                conn.sendall(response.encode('utf-8'))
        except Exception as e:
            print(f"Error in serve_client: {e}")
        finally:
            conn.close()



def main():
    # Usaremos puertos únicos para cada nodo
    ports = [8001, 8002, 8003, 8004, 8005]
    nodes = []
    ip = "127.0.0.1"  # Usamos una IP fija para pruebas locales

    # Iniciar el nodo inicial (bootstrap)
    initial_node = ChordNode(ip, port=ports[0], db_path=f'node_{ports[0]}.db')
    nodes.append(initial_node)
    print(f"Iniciado nodo bootstrap en {ip}:{ports[0]}")

    # Dar tiempo para que el nodo inicial se estabilice
    time.sleep(3)

    # Iniciar los nodos restantes y unirlos al anillo usando el nodo inicial
    for port in ports[1:]:
        node = ChordNode(ip, peerId=ip, port=port, db_path=f'node_{port}.db')
        # Llamamos explícitamente a join pasando la referencia del nodo inicial con el puerto correcto
        node.join(ChordNodeReference(ip, ports[0]))
        nodes.append(node)
        print(f"Iniciado nodo en {ip}:{port} y se une al anillo.")
        time.sleep(2)  # Espera breve para que cada nodo se una correctamente

    # Esperar un tiempo suficiente para que todos los nodos se estabilicen (por ejemplo, 15 segundos)
    print("Esperando estabilización completa de la red...")
    time.sleep(15)

    # Subir archivos a la red
    files = [
        ("file1.txt", "txt", b"Contenido de file1"),
        ("file2.txt", "txt", b"Contenido de file2"),
        ("image1.png", "png", b"Datos de image1")
    ]

    for name, file_type, content in files:
        # Escoger un nodo aleatorio para subir el archivo
        chosen_node = random.choice(nodes)
        print(f"Subiendo {name} desde nodo {chosen_node.ip}:{chosen_node.port}...")
        chosen_node.upload_file(name, file_type, content)
        time.sleep(1)

    # Esperar para que se completen las replicaciones
    print("Esperando replicación...")
    time.sleep(10)

    # Mostrar los archivos almacenados en cada nodo
    for node in nodes:
        print(f"\nArchivos en nodo {node.ip}:{node.port}:")
        cursor = node.storage.connection.cursor()
        cursor.execute("SELECT name, type FROM files")
        stored_files = cursor.fetchall()
        for f in stored_files:
            print(f"  {f[0]} ({f[1]})")


if __name__ == "__main__":
    main()