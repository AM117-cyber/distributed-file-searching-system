import socket
import threading
import time
import hashlib
import os
import sqlite3
import struct
import json
import logging
import traceback

# Configuración del sistema de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('chord-server')

BROADCAST_PORT = 50000
SERVER_IP = socket.gethostbyname(socket.gethostname())
BROADCAST_ADDRESS = '<broadcast>'

MULTICAST_GROUP = '224.0.0.1'
MULTICAST_PORT = 10000

# Operation codes
FIND_SUCCESSOR = 1
FIND_PREDECESSOR = 2
GET_SUCCESSOR = 3
GET_PREDECESSOR = 4
NOTIFY = 5
CLOSEST_PRECEDING_FINGER = 6
IS_ALIVE = 7
UPLOAD_FILE = 10
SEARCH_FILE = 11
DOWNLOAD_FILE = 12
SAVE_REPLIC = 13
REPLIC = 14
REMOVE_FILE = 15
TRIGGER_REPLICATION = 16



def compute_hash(file_content):
    sha_value = hashlib.sha1(file_content).hexdigest()
    return sha_value

def getShaRepr(data: str):
    hash_value = int(hashlib.sha1(data.encode()).hexdigest(),16)
    logger.debug(f"SHA1 hash para '{data}': {hash_value}")
    return hash_value

class ChordNodeReference:
    def __init__(self, ip: str, port: int = 8001):
        self.id = getShaRepr(ip)
        self.ip = ip
        self.port = port
        logger.debug(f"Creada referencia a nodo {self.ip}:{self.port} con ID {self.id}")

    def _send_data(self, op: int, data: str = None) -> bytes:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.ip, self.port))
                s.sendall(f'{op},{data}'.encode('utf-8'))
                logger.debug(f"Enviada operación {op} a {self.ip}:{self.port}")
                return s.recv(1024)
        except Exception as e:
            logger.error(f"Error enviando operación {op} a {self.ip}:{self.port}: {e}")
            return b''

    def find_successor(self, id: int) -> 'ChordNodeReference':
        logger.debug(f"Buscando sucesor del ID {id} a través de nodo {self.ip}")
        response = self._send_data(FIND_SUCCESSOR, str(id)).decode().split(',')
        logger.debug(f"Sucesor encontrado: {response}")
        return ChordNodeReference(response[1], self.port)

    def find_predecessor(self, id: int) -> 'ChordNodeReference':
        logger.debug(f"Buscando predecesor del ID {id} a través de nodo {self.ip}")
        response = self._send_data(FIND_PREDECESSOR, str(id)).decode().split(',')
        logger.debug(f"Predecesor encontrado: {response}")
        return ChordNodeReference(response[1], self.port)

    @property
    def succ(self) -> 'ChordNodeReference':
        logger.debug(f"Obteniendo sucesor de {self.ip}")
        response = self._send_data(GET_SUCCESSOR).decode().split(',')
        logger.debug(f"Sucesor de {self.ip}: {response}")
        return ChordNodeReference(response[1], self.port)

    @property
    def pred(self) -> 'ChordNodeReference':
        logger.debug(f"Obteniendo predecesor de {self.ip}")
        response = self._send_data(GET_PREDECESSOR).decode().split(',')
        logger.debug(f"Predecesor de {self.ip}: {response}")
        return ChordNodeReference(response[1], self.port)

    def notify(self, node: 'ChordNodeReference'):
        logger.debug(f"Notificando a {self.ip} sobre posible predecesor {node.ip}")
        self._send_data(NOTIFY, f'{node.id},{node.ip}')

    def closest_preceding_finger(self, id: int) -> 'ChordNodeReference':
        logger.debug(f"Buscando dedo más cercano a ID {id} a través de nodo {self.ip}")
        response = self._send_data(CLOSEST_PRECEDING_FINGER, str(id)).decode().split(',')
        logger.debug(f"Dedo más cercano: {response}")
        return ChordNodeReference(response[1], self.port)

    def alive(self):
        logger.debug(f"Verificando si nodo {self.ip} está vivo")
        response = self._send_data(IS_ALIVE).decode().split(',')
        logger.debug(f"Respuesta de verificación de vida de {self.ip}: {response}")
        return response

    def store_key(self, key: str, value: str):
        logger.debug(f"Almacenando clave {key} en nodo {self.ip}")
        self._send_data(STORE_KEY, f'{key},{value}')

    def save_file(self, file_name, file_type, file_content, file_size):
        try:
            logger.info(f"Enviando archivo '{file_name}' ({file_type}, {file_size} bytes) a nodo {self.ip}")
            s=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.connect((self.ip, self.port))
            s.send(f"{10},{file_name},{file_type},{file_size}".encode())
            logger.debug(f"Solicitud de guardado de archivo enviada a {self.ip}")

            ready = s.recv(1024).decode()
            if ready == 'READY':
                logger.info(f"Nodo {self.ip} listo para recibir. Enviando contenido...")
                bytes_sent = 0
                for i in range(0, len(file_content), 1024000):
                    chunk = file_content[i:i+1024000]
                    s.send(chunk)
                    bytes_sent += len(chunk)
                    if bytes_sent % (5*1024*1024) == 0:  # Log cada 5MB
                        logger.debug(f"Enviados {bytes_sent}/{file_size} bytes a {self.ip}")
                logger.info(f"Transferencia a {self.ip} completada ({file_size} bytes)")
            response = s.recv(1024)
            logger.info(f"Respuesta de guardado de archivo de {self.ip}: {response.decode()}")
            s.close()
        except Exception as e:
            logger.error(f"Error al guardar archivo en {self.ip}: {e}", exc_info=True)
            response = "ERROR".encode()
        return response

    def replic(self, file_name, file_type, file_content, file_size):
        try:
            logger.info(f"[REPLICACIÓN] Iniciando replicación de '{file_name}' ({file_type}, {file_size} bytes) a {self.ip}")
            s=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.connect((self.ip, self.port))
            s.send(f"{14},{file_name},{file_type},{file_size}".encode())
            logger.debug(f"[REPLICACIÓN] Solicitud enviada a {self.ip}")

            ready = s.recv(1024).decode()
            if ready == 'READY':
                logger.info(f"[REPLICACIÓN] Nodo {self.ip} listo. Iniciando transferencia...")
                bytes_sent = 0
                for i in range(0, len(file_content), 1024000):
                    chunk = file_content[i:i+1024000]
                    s.send(chunk)
                    bytes_sent += len(chunk)
                    if bytes_sent % (5*1024*1024) == 0:  # Log cada 5MB
                        logger.debug(f"[REPLICACIÓN] Progreso: {bytes_sent}/{file_size} bytes ({bytes_sent*100/file_size:.1f}%)")
                logger.info(f"[REPLICACIÓN] Transferencia a {self.ip} completada")

            response = s.recv(1024)
            logger.info(f"[REPLICACIÓN] Respuesta de {self.ip}: {response.decode()}")
            s.close()
        except Exception as e:
            logger.error(f"[REPLICACIÓN] Error replicando a {self.ip}: {e}", exc_info=True)
            response = "ERROR".encode()
        return response

    def remove_file(self, file_name: str):
        """
        Ordena remotamente a un nodo que elimine 'file_name' de su base de datos local.
        """
        try:
            response = self._send_data(REMOVE_FILE, file_name)
            logger.debug(f"Respuesta de remove_file en {self.ip}: {response.decode()}")
        except Exception as e:
            logger.error(f"Error solicitando remove_file para {file_name} en {self.ip}: {e}")

    def trigger_replication(self):
        """
        Pide remotamente a un nodo que ejecute su proceso de replicación completo.
        """
        try:
            response = self._send_data(TRIGGER_REPLICATION)
            logger.debug(f"Respuesta de trigger_replication en {self.ip}: {response.decode()}")
        except Exception as e:
            logger.error(f"Error solicitando trigger_replication en {self.ip}: {e}")


    def __str__(self) -> str:
        return f'{self.id},{self.ip},{self.port}'

    def __repr__(self) -> str:
        return self.__str__()


class ChordNode:
    def __init__(self, ip: str, peerId = None, port: int = 8001, m: int = 160):
        self.id = getShaRepr(ip)
        self.ip = ip
        self.port = port
        self.ref = ChordNodeReference(self.ip, self.port)
        self.pred = self.ref
        self.m = m
        self.finger = [self.ref] * self.m
        self.lock = threading.Lock()
        self.successor1 = self.ref
        self.successor2 = self.ref

        logger.info(f"Inicializando nodo Chord: ID={self.id}, IP={self.ip}, Puerto={self.port}")

        #manejo de la base de datos
        # creamos una base de datos unica por para cada servidor por el ip
        DB_FILE = f"db/server_files_{self.ip}.db"
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
            logger.warning(f"Se ha eliminado la base de datos {DB_FILE} para forzar reinicio.")

        # 2) Crear la conexión y tablas
        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._init_db()
        # logger.info(f"Base de datos inicializada: {DB_FILE}")

        # Iniciar hilos
        # threading.Thread(target=self.stabilize, daemon=True).start()
        # logger.info("Hilo de estabilización iniciado")

        # threading.Thread(target=self.fix_fingers, daemon=True).start()
        # logger.info("Hilo de corrección de finger table iniciado")

        threading.Thread(target=self.maintenance, daemon=True).start()
        logger.info("Hilo de estabilización iniciado")

        # Socket para broadcast
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', BROADCAST_PORT))
        # logger.info(f"Socket de broadcast vinculado al puerto {BROADCAST_PORT}")

        discovery_thread = threading.Thread(target=self.handle_discovery, args=(sock,))
        discovery_thread.daemon = True
        discovery_thread.start()
        # logger.info("Hilo de descubrimiento iniciado")

        # time.sleep(10)

        # Hilo de replicación
        # replic_thread = threading.Thread(target=self.replicate)
        # replic_thread.daemon = True
        # replic_thread.start()
        # logger.info("Hilo de replicación periódica iniciado")

        # Socket multicast
        sock_m = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock_m.bind(('', MULTICAST_PORT))
        group = socket.inet_aton(MULTICAST_GROUP)
        mreq = struct.pack('4sL', group, socket.INADDR_ANY)
        sock_m.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        # logger.info(f"Socket multicast vinculado al grupo {MULTICAST_GROUP}:{MULTICAST_PORT}")

        multicast_thread = threading.Thread(target=self.handle_multicast_discover,args=(sock_m,))
        multicast_thread.daemon=True
        multicast_thread.start()
        # logger.info("Hilo de descubrimiento multicast iniciado")

        # Buscar nodos existentes
        self.new_ip = self.discover_server()
        # logger.info(f"Descubrimiento de servidor existente: {self.new_ip or 'Ninguno encontrado'}")

        if self.new_ip is not None:
            threading.Thread(target=self.join, args=(ChordNodeReference(self.new_ip, self.port),), daemon=True).start()
            # logger.info(f"Iniciando unión al anillo a través de nodo {self.new_ip}")
        # else:
            # logger.info("No se encontró un anillo existente, este nodo formará uno nuevo")

        # Iniciar servidor
        # logger.info("Iniciando servidor...")
        self.start_server()

    @property
    def succ(self):
        return self.finger[0]

    @succ.setter
    def succ(self, node: 'ChordNodeReference'):
        with self.lock:
            logger.debug(f"Actualizando sucesor a {node.ip} (ID: {node.id})")
            self.finger[0] = node

    def _init_db(self):
        logger.debug("Inicializando esquema de base de datos")
        
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hash TEXT UNIQUE NOT NULL,
            content BLOB NOT NULL,
            type TEXT NOT NULL
            
        )
        ''')

        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS file_names (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            FOREIGN KEY (file_id) REFERENCES files (id)
        )
        ''')
        self.conn.commit()
        logger.debug("Esquema de base de datos inicializado correctamente")

    def save_file(self, file_name, file_type, file_content):
        """Guarda un archivo en la base de datos."""
        with self.lock:
            try:
                cursor = self.conn.cursor()  # en vez de self.cursor
                # logger.info(f"Guardando archivo: '{file_name}' ({file_type}, {len(file_content)} bytes)")
                file_hash = compute_hash(file_content)
                logger.debug(f"Hash del archivo: {file_hash[:10]}...")

                cursor.execute('SELECT id FROM files WHERE hash = ?', (file_hash,))
                file_record = cursor.fetchone()

                if file_record:
                    file_id = file_record[0]
                    logger.debug(f"Archivo con hash {file_hash[:10]}... ya existe (ID: {file_id})")

                    cursor.execute('SELECT name FROM file_names WHERE file_id = ? AND name = ?', (file_id, file_name))
                    name_record = cursor.fetchone()

                    if not name_record:
                        # logger.info(f"Añadiendo nuevo nombre '{file_name}' a archivo existente (ID: {file_id})")
                        cursor.execute('INSERT INTO file_names (file_id, name) VALUES (?, ?)', (file_id, file_name))
                        self.conn.commit()
                        return "Nombre agregado al archivo existente"

                    # logger.info(f"El archivo '{file_name}' ya existe con exactamente el mismo contenido")
                    return "El archivo ya existe con ese nombre"
                else:
                    # logger.info(f"Guardando nuevo archivo '{file_name}' ({file_type}, {len(file_content)} bytes)")
                    cursor.execute('INSERT INTO files (hash, content, type) VALUES (?, ?, ?)',
                                      (file_hash, file_content, file_type))
                    file_id = cursor.lastrowid
                    cursor.execute('INSERT INTO file_names (file_id, name) VALUES (?, ?)', (file_id, file_name))
                    self.conn.commit()
                    # logger.info(f"Nuevo archivo guardado con ID: {file_id}")
                    return "Archivo subido correctamente"
            except Exception as e:
                logger.error(f"Error al guardar archivo '{file_name}': {e}", exc_info=True)
                return f"Error al guardar archivo: {e}"
            
    def broadcast_search(self, file_name, file_type):
        results = []
        broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        broadcast_socket.settimeout(3)

        message = f"{SEARCH_FILE},{file_name},{file_type}"
        broadcast_socket.sendto(message.encode(), (BROADCAST_ADDRESS, BROADCAST_PORT))

        def handle_response(m):
            if m.startswith("SEARCH_RESULT~"):
                    Elements=eval(m.split("~")[1])
                    with self.lock:
                        for e in Elements:
                            if e not in results: results.append(e)

        while True:
            try:
                data, addr = broadcast_socket.recvfrom(1024)
                response = data.decode()
                threading.Thread(
                    target=handle_response,
                    args=(response,),
                    daemon=True
                ).start()
            except socket.timeout:
                break
        broadcast_socket.close()
        print(results)
        return results


    def search_file(self, file_name, file_type):
        """
        Busca localmente en la base de datos
        archivos que coincidan con file_name y file_type.
        """
        try:
            # Búsqueda en la DB local
            query = '''SELECT fn.name, f.type, f.hash
                    FROM files f
                    JOIN file_names fn ON f.id = fn.file_id
                    WHERE fn.name LIKE ?'''
            params = (f"%{file_name}%",)

            if file_type != "*":
                query += ' AND f.type = ?'
                params += (file_type,)

            self.cursor.execute(query, params)
            results = []
            for row in self.cursor.fetchall():
                results.append({
                    "name": row[0],
                    "type": row[1],
                    "hash": row[2],
                    "ip": self.ip
                })
            return results
        except Exception as e:
            logger.error(f"Error en búsqueda local: {e}", exc_info=True)
            return []

    def download_file(self, file_name):
        """Recupera un archivo de la base de datos local."""
        try:
            # logger.info(f"Solicitando descarga de archivo: '{file_name}'")
            self.cursor.execute('''SELECT f.content, fn.name FROM files f
            JOIN file_names fn ON f.id = fn.file_id WHERE fn.name = ?''', (file_name,))
            result = self.cursor.fetchone()

            if result:
                # logger.info(f"Archivo '{file_name}' encontrado. Tamaño: {len(result[0])} bytes")
                return result[0]
            else:
                logger.warning(f"Archivo '{file_name}' no encontrado en este nodo")
                return None
        except Exception as e:
            logger.error(f"Error al recuperar archivo '{file_name}': {e}", exc_info=True)
            return None

    def remove_local_file(self, file_name: str):
        """
        Elimina de la DB local toda referencia al 'file_name'.
        Si ese nombre era el último que apuntaba al contenido, elimina el contenido también.
        """
        with self.lock:
            try:
                # logger.info(f"Eliminando archivo local '{file_name}' en nodo {self.ip}")
                # 1) Buscar qué file_id corresponde a ese nombre
                self.cursor.execute('''
                    SELECT f.id
                    FROM files f
                    JOIN file_names fn ON f.id = fn.file_id
                    WHERE fn.name = ?
                ''', (file_name,))
                row = self.cursor.fetchone()
                if not row:
                    logger.warning(f"No se encontró '{file_name}' en este nodo.")
                    return "NOT_FOUND"

                file_id = row[0]

                # 2) Eliminar el nombre de la tabla file_names
                self.cursor.execute('DELETE FROM file_names WHERE file_id = ? AND name = ?', (file_id, file_name))

                # 3) Ver si ese file_id aún tiene otros nombres
                self.cursor.execute('SELECT COUNT(*) FROM file_names WHERE file_id = ?', (file_id,))
                count_names = self.cursor.fetchone()[0]

                # 4) Si no quedan nombres, eliminar el registro de 'files'
                if count_names == 0:
                    # logger.info(f"'{file_name}' era el único nombre. Eliminando contenido ID={file_id} definitivamente.")
                    self.cursor.execute('DELETE FROM files WHERE id = ?', (file_id,))
                self.conn.commit()
                return "OK"
            except Exception as e:
                logger.error(f"Error eliminando archivo '{file_name}': {e}", exc_info=True)
                return f"ERROR:{e}"


    def _inbetween(self, k: int, start: int, end: int) -> bool:
        result = False
        k = k % 2 ** self.m
        start = start % 2 ** self.m
        end = end % 2 ** self.m
        if start < end:
            result = start <= k < end
        else:
            result = start <= k or k < end
        logger.debug(f"_inbetween({k}, {start}, {end}) = {result}")
        return result

    def _inrange(self, k: int, start: int, end: int) -> bool:
        _start = (start + 1) % 2 ** self.m
        result = self._inbetween(k, _start, end)
        logger.debug(f"_inrange({k}, {start}, {end}) = {result}")
        return result

    def _inbetweencomp(self, k: int, start: int, end: int) -> bool:
        _end = (end - 1) % 2 ** self.m
        result = self._inbetween(k, start, _end)
        logger.debug(f"_inbetweencomp({k}, {start}, {end}) = {result}")
        return result

    def find_succ(self, id: int) -> 'ChordNodeReference':
        logger.debug(f"Buscando sucesor para ID {id}")
        node = self.find_pred(id)
        # logger.info(f"Encontrado predecesor {node.id} para ID {id}, solicitando su sucesor")
        return node.succ

    def find_pred(self, id: int) -> 'ChordNodeReference':
        logger.debug(f"Buscando predecesor para ID {id}")
        node = self
        try:
            if node.id == self.succ.id:
                logger.debug(f"Soy el único nodo en el anillo, yo mismo soy el predecesor de {id}")
                return node
        except Exception as e:
            logger.error(f"Error verificando si soy único nodo: {e}")

        while not self._inbetweencomp(id, node.id, node.succ.id):
            logger.debug(f"ID {id} no está entre {node.id} y {node.succ.id}, buscando dedo más cercano")
            prev_node_id = node.id
            node = node.closest_preceding_finger(id)
            logger.debug(f"Dedo más cercano encontrado: {node.id}")
            if node.id == self.id or node.id == prev_node_id:
                logger.debug("Dedo más cercano soy yo mismo o el anterior, deteniendo búsqueda")
                break
        # logger.info(f"Predecesor para ID {id}: {node.id}")
        return node

    def closest_preceding_finger(self, id: int) -> 'ChordNodeReference':
        logger.debug(f"Buscando dedo más cercano a ID {id}")
        node = None
        for i in range(self.m - 1, -1, -1):
            try:
                if node == self.finger[i]:
                    logger.debug(f"Dedo {i} ya verificado, saltando")
                    continue

                # Verificar que el dedo esté vivo
                self.finger[i].succ

                if self._inrange(self.finger[i].id, self.id, id):
                    logger.debug(f"Encontrado dedo {i} en rango: {self.finger[i].id}")
                    return self.finger[i] if self.finger[i].id != self.id else self
            except Exception as e:
                logger.debug(f"Error verificando dedo {i}: {e}")
                node = self.finger[i]
                continue

        logger.debug(f"No se encontró dedo más cercano, retornando a mí mismo")
        return self

    def join(self, node: 'ChordNodeReference'):
        """Unirse a un anillo Chord existente."""
        time.sleep(5)
        # logger.info(f"Iniciando unión al anillo a través de nodo {node.ip}")
        self.pred = self.ref
        logger.debug("Predecesor establecido a mí mismo inicialmente")

        # logger.info(f"Buscando mi sucesor a través de nodo {node.ip}")
        self.succ = node.find_successor(self.id)
        # logger.info(f"Sucesor encontrado: {self.succ.ip} (ID: {self.succ.id})")

        # logger.info("Recuperando sucesor del sucesor")
        self.successor1 = self.succ.succ
        # logger.info(f"Sucesor 2 establecido: {self.successor1.ip} (ID: {self.successor1.id})")

        # logger.info("Recuperando sucesor del sucesor 2")
        self.successor2 = self.successor1.succ
        # logger.info(f"Sucesor 3 establecido: {self.successor2.ip} (ID: {self.successor2.id})")

        # logger.info("Unión al anillo completada")

    def maintenance(self):
        """
        Un solo bucle que hace:
        1) estabilización,
        2) corrección de fingers
        3) replicación
        cada N segundos.
        """
        time.sleep(5)
        logger.info("[MAINTENANCE] Iniciando mantenimiento unificado (stabilize + fix_fingers + replicate)")

        while True:
            # 1) un ciclo de estabilización
            self.stabilize()

            # 2) un ciclo de fix_fingers
            self._fix_fingers_once()

            # 3) un ciclo de replicación
            self.replicate()

            # 4) Espera
            time.sleep(30)


    def stabilize(self):
        """
        Ciclo periódico de estabilización.
        - Verifica si el sucesor está vivo; si no, recurre a successor1 o successor2.
        - Pregunta quién es el pred del sucesor y ajusta si corresponde.
        - Actualiza successor1, successor2.
        """
    # time.sleep(5)  # Espera inicial
    # while True:
        try:
            # 1) Verifica si self.succ sigue vivo
            try:
                resp = self.succ.alive()  # Operation code IS_ALIVE
                if not resp or 'alive' not in resp:
                    raise Exception(f"Sucesor {self.succ.ip} no respondió 'alive'")
            except Exception as e:
                logger.warning(f"Sucesor {self.succ.ip} caído: {e}. Intentando con successor1/ successor2")
                # Salta a successor1
                self.succ = self.successor1
                try:
                    resp2 = self.succ.alive()
                    if not resp2 or 'alive' not in resp2:
                        logger.warning(f"successor1 {self.succ.ip} tampoco responde. Intentando successor2.")
                        self.succ = self.successor2
                except Exception as e2:
                    logger.warning(f"successor1 {self.succ.ip} falló: {e2}. Intentando successor2.")
                    self.succ = self.successor2

            # 2) Pregunta al sucesor por su pred
            try:
                x = self.succ.pred  # Podría lanzar excepción si el sucesor también está caído
                # Si x encaja en el rango (self.id, self.succ.id), actualizamos sucesor
                if x.id != self.id and self._inrange(x.id, self.id, self.succ.id):
                    self.succ = x
            except Exception as e:
                logger.debug(f"No se pudo obtener pred del sucesor: {e}")

            # 3) Notificar al sucesor de mi existencia
            try:
                self.succ.notify(self.ref)
            except Exception as e:
                logger.debug(f"No se pudo notificar al sucesor {self.succ.ip}: {e}")

            # 4) Actualizar successor1
            try:
                self.successor1 = self.succ.succ
            except Exception:
                self.successor1 = self.ref  # fallback a mí mismo si falla

            # 5) Actualizar successor2
            try:
                self.successor2 = self.successor1.succ
            except Exception:
                self.successor2 = self.ref

        except Exception as e:
            logger.error(f"Error en estabilización: {e}", exc_info=True)

        # time.sleep(5)

    def replicate(self):
        """
        - Si soy responsable, replico a successor1 y successor2 (si están vivos).
        - Si no, intento subir al responsable (verificando si está vivo).
        - Solo elimino mi copia si el remoto confirma que guardó (o “ya existe mismo hash”).
        """
    # while True:
        time.sleep(30)
        try:
            logger.info("[REPLICACIÓN] Iniciando verificación/replicación de archivos...")
            self.cursor.execute("""
                SELECT f.content, f.type, fn.name
                FROM files f
                JOIN file_names fn ON f.id = fn.file_id
            """)
            rows = self.cursor.fetchall()
            logger.info(f"[REPLICACIÓN] Encontrados {len(rows)} archivos/nombres en la base local.")

            for content, ftype, fname in rows:
                file_size = len(content)
                fid = getShaRepr(str(content))  # MISMA FUNCIÓN que usas para la responsabilidad
                responsable = self.find_succ(fid)

                # Verificar si el nodo responsable está vivo
                try:
                    resp_alive = responsable.alive()
                    if not resp_alive or 'alive' not in resp_alive:
                        logger.warning(f"[REPLICACIÓN] El supuesto responsable {responsable.ip} no responde. Saltando '{fname}'.")
                        continue
                except Exception as e:
                    logger.warning(f"[REPLICACIÓN] No se pudo contactar a {responsable.ip}: {e}. Saltando '{fname}'.")
                    continue

                # Decidir si soy responsable o no
                if responsable.id == self.id:
                    logger.info(f"[REPLICACIÓN] Soy responsable de '{fname}'. Replicando a successor1 y successor2...")
                    # Replico a successor1
                    try:
                        if self.successor1 and self.successor1.id != self.id:
                            alive2 = self.successor1.alive()
                            if alive2 and 'alive' in alive2:
                                resp2 = self.successor1.replic(fname, ftype, content, file_size)
                                logger.debug(f"[REPLICACIÓN] Resp replic en successor1: {resp2.decode()}")
                            else:
                                logger.warning(f"[REPLICACIÓN] successor1 {self.successor1.ip} no responde. Omisión de replic.")
                    except Exception as e2:
                        logger.warning(f"[REPLICACIÓN] Error replicando a successor1 {self.successor1.ip}: {e2}")

                    # Replico a successor2
                    try:
                        if self.successor2 and self.successor2.id != self.id:
                            alive3 = self.successor2.alive()
                            if alive3 and 'alive' in alive3:
                                resp3 = self.successor2.replic(fname, ftype, content, file_size)
                                logger.debug(f"[REPLICACIÓN] Resp replic en successor2: {resp3.decode()}")
                            else:
                                logger.warning(f"[REPLICACIÓN] successor2 {self.successor2.ip} no responde. Omisión de replic.")
                    except Exception as e3:
                        logger.warning(f"[REPLICACIÓN] Error replicando a successor2 {self.successor2.ip}: {e3}")

                else:
                    # No soy responsable → lo subo al responsable
                    logger.info(f"[REPLICACIÓN] '{fname}' no pertenece a mí. Lo envío a {responsable.ip} y luego lo elimino si confirma.")
                    upload_resp = responsable.save_file(fname, ftype, content, file_size).decode('utf-8', errors='ignore')

                    # Determina si realmente se guardó
                    # Ej. "Archivo subido correctamente" o "Nombre agregado al archivo existente"
                    # si confirmamos que la hash coincide.
                    if "subido correctamente" in upload_resp.lower() or "agregado al archivo existente" in upload_resp.lower():
                        # Eliminamos local
                        remove_resp = self.remove_local_file(fname)
                        logger.debug(f"[REPLICACIÓN] remove_local_file: {remove_resp}")
                    # elif "ya existe con ese nombre" in upload_resp.lower():
                    #     # Ideal: checar si es la misma hash.
                    #     # Suponiendo que es la misma, entonces lo borro local:
                    #     remove_resp = self.remove_local_file(fname)
                    #     logger.debug(f"[REPLICACIÓN] remove_local_file: {remove_resp}")
                    else:
                        logger.warning(f"[REPLICACIÓN] El responsable devolvió respuesta inesperada: '{upload_resp}'. No elimino mi copia local.")

            logger.info("[REPLICACIÓN] Ciclo de replicación completado. Próxima ejecución en 30 segundos.")
        except Exception as e:
            logger.error(f"[REPLICACIÓN] ERROR: Excepción en el proceso de replicación: {e}", exc_info=True)

        # time.sleep(5)


    def notify(self, node: 'ChordNodeReference'):
        """Maneja notificación de posible predecesor."""
        logger.debug(f"Recibida notificación de posible predecesor: {node.ip} (ID: {node.id})")

        if node.id == self.id:
            logger.debug("Ignorando notificación de mí mismo")
            return

        logger.debug(f"Verificando si {node.id} debe ser mi predecesor")
        if (self.pred.id == self.id) or self._inrange(node.id, self.pred.id, self.id):
            # logger.info(f"Actualizando predecesor: {self.pred.ip} -> {node.ip}")
            self.pred = node

    # def fix_fingers(self):
    #     """Proceso periódico de corrección de la finger table."""
    #     time.sleep(5)
    #     # logger.info("Iniciando proceso de corrección de finger table")

    #     while True:
    #         for i in range(self.m - 1, -1, -1):
    #             self.next = i
    #             with self.lock:
    #                 logger.debug(f"Corrigiendo entrada {self.next} de la finger table")
    #                 self.finger[self.next] = self.find_succ((self.id + 2 ** self.next) % (2 ** self.m))
    #         time.sleep(10)

    def _fix_fingers_once(self):
        """
        Hace lo que fix_fingers hacía, pero SOLO UNA VEZ,
        en lugar de su while True interno.
        """
        for i in range(self.m - 1, -1, -1):
            self.next = i
            with self.lock:
                logger.debug(f"Corrigiendo entrada {self.next} de la finger table")
                # Actualizas self.finger[self.next]
                self.finger[self.next] = self.find_succ((self.id + 2 ** self.next) % (2 ** self.m))


    def handle_discovery(self, sock):
        """Maneja solicitudes de descubrimiento por broadcast."""
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                message = data.decode('utf-8')
                logger.debug(f"Recibido mensaje de broadcast: {message} de {addr}")
                # Crear un hilo para manejar el mensaje
                threading.Thread(
                    target=self.handle_broadcast_message,
                    args=(sock, message, addr),
                    daemon=True
                ).start()

            except Exception as e:
                logger.error(f"Error en el hilo de descubrimiento: {e}")
                break

    def handle_broadcast_message(self, sock, message, addr):
        """Procesa mensajes de broadcast recibidos."""
        try:
            if message == "DISCOVER_REQUEST":
                response = f"SERVER_IP:{SERVER_IP}"
                sock.sendto(response.encode('utf-8'), addr)
                logger.debug(f"Respondido a solicitud de descubrimiento de {addr}")
        except Exception as e:
            logger.error(f"Error al manejar mensaje de broadcast: {e}")

    def handle_multicast_discover(self,sock):
        """Maneja solicitudes de descubrimiento por multicast."""
        try:
            while True:
                data, addr = sock.recvfrom(1024)
                if data == b"DISCOVER_NODE":
                    logger.debug("Recibido mensaje de multicast DISCOVER_NODE")
                    # Responder con la dirección IP del nodo
                    node_ip = socket.gethostbyname(socket.gethostname())
                    sock.sendto(node_ip.encode(), (MULTICAST_GROUP,MULTICAST_PORT))
                    logger.debug(f"Respondido a {MULTICAST_GROUP} con mi IP: {node_ip}")
        except Exception as e:
            logger.error(f"Error en el hilo de multicast: {e}")

    def discover_server(self):
        """Descubre servidores existentes en la red mediante broadcast."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1) #Permite broadcast

        sock.settimeout(5)  # Tiempo máximo para esperar una respuesta

        message = "DISCOVER_REQUEST"
        try:
            sock.sendto(message.encode('utf-8'), (BROADCAST_ADDRESS, BROADCAST_PORT))
            # logger.info("Enviando solicitud de descubrimiento por broadcast...")
            while True:
                try:
                    data, addr = sock.recvfrom(1024)
                    response = data.decode('utf-8')
                    logger.debug(f"Recibido respuesta de {addr}: {response}")

                    if response.startswith("SERVER_IP:"):
                        server_ip = response.split(":")[1]
                        if server_ip == self.ip:
                            continue
                        # logger.info(f"Servidor encontrado en la IP: {server_ip}")
                        return server_ip # Devuelve la IP del primer servidor encontrado

                except socket.timeout:
                    # logger.info("No se encontraron servidores en el tiempo especificado.")
                    return None  # No se encontró ningún servidor

        except Exception as e:
            logger.error(f"Error durante el descubrimiento: {e}")
            return None
        finally:
            sock.close()


    def start_server(self):
        # logger.info(f"Iniciando servidor en {self.ip}:{self.port}")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setblocking(True)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.ip, self.port))
            s.listen(10)

            while True:
                conn, addr = s.accept()
                logger.debug(f"Conexión aceptada de {addr}")
                threading.Thread(target=self.serve_client, args=(conn,), daemon=True).start()

    def serve_client(self, conn: socket.socket):
        try:
            data = conn.recv(1024).decode().split(',')
            data_resp = None
            if (data[0] not in ["3","4"]):
                logger.debug(f"Datos recibidos: {data[0]}")
            option = int(data[0])

            if option == FIND_SUCCESSOR:
                id = int(data[1])
                data_resp = self.find_succ(id)
            elif option == FIND_PREDECESSOR:
                id = int(data[1])
                data_resp = self.find_pred(id)
            elif option == GET_SUCCESSOR:
                data_resp = self.succ
            elif option == GET_PREDECESSOR:
                data_resp = self.pred
            elif option == NOTIFY:
                id = int(data[1])
                ip = data[2]
                self.notify(ChordNodeReference(ip, self.port))
            elif option == CLOSEST_PRECEDING_FINGER:
                id = int(data[1])
                data_resp = self.closest_preceding_finger(id)
            elif option == IS_ALIVE:
                data_resp = 'alive'
            elif option == UPLOAD_FILE:
                file_name, file_type, file_size = data[1], data[2], int(data[3])
                logger.debug("Listo para recibir archivo")
                conn.send('READY'.encode())
                file_content = b""
                remaining = file_size
                while remaining > 0:
                    chunk = conn.recv(min(1024000, remaining))
                    if not chunk:
                        break
                    file_content += chunk
                    remaining -= len(chunk)
                logger.debug("Archivo recibido, calculando hash")
                file_hash = getShaRepr(str(file_content))
                logger.debug("Buscando sucesor responsable del archivo")
                responsible_node = self.find_succ(file_hash)
                if responsible_node.id == self.id:
                    logger.debug("Este nodo es responsable del archivo")
                    response = self.save_file(file_name, file_type, file_content)
                else:
                    logger.debug("Otro nodo es responsable del archivo")
                    response = responsible_node.save_file(file_name, file_type, file_content, file_size).decode()
                    while response == "ERROR":
                        responsible_node = self.find_succ(file_hash)
                        if responsible_node.id == self.id:
                            response = self.save_file(file_name, file_type, file_content)
                        else:
                            response = responsible_node.save_file(file_name, file_type, file_content, file_size).decode()
                logger.debug("Enviando respuesta")
                conn.send(response.encode())

            elif option == REPLIC:
                file_name, file_type, file_size = data[1], data[2], int(data[3])
                logger.info(f"[REPLICACIÓN] Recibida solicitud de replicación para '{file_name}' ({file_type}) - {file_size} bytes")
                conn.send('READY'.encode())
                logger.debug(f"[REPLICACIÓN] Enviada confirmación 'READY' al remitente")

                file_content = b""
                remaining = file_size
                received_bytes = 0
                while remaining > 0:
                    chunk = conn.recv(min(1024000, remaining))
                    if not chunk:
                        break
                    file_content += chunk
                    received_bytes += len(chunk)
                    remaining -= len(chunk)
                    if received_bytes % 5242880 == 0:  # Log cada 5MB aproximadamente
                        logger.debug(f"[REPLICACIÓN] Recibidos {received_bytes} de {file_size} bytes para '{file_name}'")

                logger.debug(f"[REPLICACIÓN] Recibido contenido completo para '{file_name}'. Guardando en la base de datos local...")
                response = self.save_file(file_name, file_type, file_content)
                logger.info(f"[REPLICACIÓN] Archivo '{file_name}' guardado en la base de datos. Resultado: {response}")
                conn.send(response.encode())

            elif option == SEARCH_FILE:
                file_name,file_type= data[1],data[2]
                try:
                    results= self.broadcast_search(file_name,file_type)
                    conn.sendall(str(results).encode())
                except Exception as e:
                    logger.error(f"Búsqueda por broadcast fallada: {e}")
                    conn.sendall("ERROR DURANTE LA BUSQUEDA POR BROADCAST".encode())

            elif option == DOWNLOAD_FILE:
                file_hash = data[1]
                logger.debug("Buscando sucesor responsable del archivo a descargar")
                responsible_node = self.find_succ(file_hash)
                response = responsible_node.download_file(file_hash)
                conn.send(f'{len(response)}'.encode())
                conn.recv(1024).decode()
                for i in range(0, len(response), 1024000):
                    chunk = response[i:i+1024000]
                    conn.send(chunk)
            elif option == REMOVE_FILE:  # 15
                file_name = data[1]
                result = self.remove_local_file(file_name)
                conn.send(result.encode())

            elif option == TRIGGER_REPLICATION:  # 16
                logger.info(f"Recibida solicitud TRIGGER_REPLICATION de un nodo remoto.")
                self.replicate()
                conn.send("Replication done".encode())


            if option in [UPLOAD_FILE,SEARCH_FILE]:
                return
            if data_resp == 'alive':
                response = data_resp.encode()
                conn.sendall(response)
            elif data_resp:
                response = f'{data_resp.id},{data_resp.ip}'.encode()
                conn.sendall(response)
        except Exception as e:
            logger.error(f"Error sirviendo al cliente: {e}", exc_info=True)
        finally:
            conn.close()


if __name__ == "__main__":
    ip = socket.gethostbyname(socket.gethostname())
    node = ChordNode(ip)