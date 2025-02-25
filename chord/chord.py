import zmq
import json
import hashlib
import logging
import threading
import time
import random
import sys
from storage_layer import *

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')

def sha1_hash(value: str) -> int:
    """Devuelve la versión entera del hash SHA-1 de una cadena."""
    return int(hashlib.sha1(value.encode('utf-8')).hexdigest(), 16)

def in_interval(x: int, start: int, end: int, modulo: int) -> bool:
    """
    Retorna True si x está en (start, end) (intervalo abierto) sobre un anillo [0..modulo-1].
    Maneja wrap-around cuando start > end.
    """
    if start < end:
        return start < x < end
    else:
        return x > start or x < end


class ChordNodeReference:
    """
    Referencia liviana para un nodo remoto en el anillo.
    Se encarga de hacer llamadas ZeroMQ (REQ) a la IP:puerto del nodo remoto.
    """
    def __init__(self, ip: str, port: int, m_bits: int):
        self.ip = ip
        self.port = port
        self.m_bits = m_bits
        node_key_str = f"{ip}:{port}"
        self.node_id = sha1_hash(node_key_str) % (2 ** m_bits)

    def findSuccessor(self, key_id: int):
        req = {"method": "findSuccessor", "params": {"key_id": key_id}}
        return self._send_zmq_request(req)

    def closestPrecedingFinger(self, key_id: int):
        req = {"method": "closestPrecedingFinger", "params": {"key_id": key_id}}
        return self._send_zmq_request(req)

    def getSuccessor(self):
        req = {"method": "getSuccessor", "params": {}}
        return self._send_zmq_request(req)

    def getPredecessor(self):
        req = {"method": "getPredecessor", "params": {}}
        return self._send_zmq_request(req)

    def notify(self, candidate: tuple):
        req = {"method": "notify", "params": {"candidate": candidate}}
        return self._send_zmq_request(req)

    def storeFile(self, name: str, file_type: str, content: bytes):
        # Se envía la petición de almacenar archivo, convirtiendo los bytes a string (latin1)
        req = {"method": "storeFile", "params": {"name": name, "type": file_type, "content": content.decode('latin1')}}
        return self._send_zmq_request(req)

    def _send_zmq_request(self, req: dict):
        """
        Crea un socket REQ, se conecta a (self.ip, self.port), envía 'req' en JSON y lee respuesta.
        Retorna 'result' del JSON si todo va bien, None si error.
        """
        ctx = zmq.Context()
        sock = ctx.socket(zmq.REQ)
        sock.connect(f"tcp://{self.ip}:{self.port}")
        try:
            sock.send_string(json.dumps(req))
            resp_str = sock.recv_string()
            resp = json.loads(resp_str)
            error = resp.get("error")
            if error:
                logging.error(f"[ChordNodeReference] Error remoto: {error}")
                return None
            return resp.get("result")
        except Exception as e:
            logging.error(f"[ChordNodeReference] Excepción en _send_zmq_request: {e}")
            return None
        finally:
            sock.close()
            ctx.term()


class ChordNode:
    """
    Nodo 'local' con toda la lógica principal de Chord (createRing, join, findSuccessor, etc.).
    Emplea ChordNodeReference para contactar remotamente a otros nodos.
    """
    def __init__(self, my_ip: str, my_port: int, m_bits: int = 16):
        """
        my_ip, my_port: Dirección donde el nodo *escucha* peticiones (server).
        m_bits: tamaño del espacio de identificadores (2^m_bits).
        """
        self.my_ip = my_ip
        self.my_port = my_port
        self.m_bits = m_bits
        self.modulo = 2 ** m_bits

        node_key_str = f"{my_ip}:{my_port}"
        self.node_id = sha1_hash(node_key_str) % self.modulo

        self.predecessor = None
        self.successor = (self.node_id, self.my_ip, self.my_port)

        self.finger = [(None, None)] * m_bits

        self.storage = StorageLayer(db_path=f"node_{my_port}_files.db")


        logging.info(f"[INIT] ChordNode - ID={self.node_id} - Escuchando en {my_ip}:{my_port}")


    def createRing(self):
        """
        Crea un anillo donde este nodo es el único miembro.
        Me apunto como mi propio sucesor.
        """
        logging.info(f"[createRing] El nodo {self.node_id} se apunta como su propio sucesor.")
        self.predecessor = None
        self.successor = (self.node_id, self.my_ip, self.my_port)

        for i in range(self.m_bits):
            start_i = (self.node_id + 2**i) % self.modulo
            self.finger[i] = (start_i, (self.node_id, self.my_ip, self.my_port))

    def join(self, known_ip: str, known_port: int):
        """
        Se une a un anillo existente, conociendo un nodo <known_ip, known_port>.
        Obtiene su sucesor inicial llamando a findSuccessor(node_id).
        """
        self.predecessor = None
        logging.info(f"[join] {self.node_id} => contacta a {known_ip}:{known_port} para su sucesor.")
        known_ref = ChordNodeReference(known_ip, known_port, self.m_bits)

        succ = known_ref.findSuccessor(self.node_id)
        if succ is not None:
            self.successor = succ
            logging.info(f"[join] Éxito. Mi sucesor inicial: {self.successor}")
        else:
            logging.error("[join] Error: no se pudo obtener sucesor remoto.")

    def findSuccessor(self, target_id: int):
        """
        findSuccessor(target_id):
          - Si target_id ∈ (self.node_id, successorID], devuelvo self.successor
          - Si no, reenvío la consulta a closestPrecedingFinger(target_id)
        """
        succ_id = self.successor[0]
        if in_interval(target_id, self.node_id, succ_id, self.modulo) or (self.node_id == succ_id):
            return self.successor
        else:
            cpf = self.closestPrecedingFinger(target_id)
            if cpf is None:
                return self.successor
            if cpf[0] == self.node_id:
                return self.successor

            cpf_ref = ChordNodeReference(cpf[1], cpf[2], self.m_bits)
            return cpf_ref.findSuccessor(target_id)

    def findPredecessor(self, target_id: int):
        """
        findPredecessor(target_id):
          Recorre la red hasta encontrar el nodo n tal que target_id ∈ (n, n.successor]
        """
        n_id, n_ip, n_port = (self.node_id, self.my_ip, self.my_port)
        while True:

            n_succ = self.remote_getSuccessor(n_ip, n_port)
            if not n_succ:

                return (n_id, n_ip, n_port)
            n_succ_id = n_succ[0]
            if in_interval(target_id, n_id, n_succ_id, self.modulo) or n_id == n_succ_id:
                return (n_id, n_ip, n_port)

            cpf = self.remote_closestPrecedingFinger(n_ip, n_port, target_id)
            if not cpf:
                return (n_id, n_ip, n_port)
            if cpf[0] == n_id:
                return (n_id, n_ip, n_port)

            n_id, n_ip, n_port = cpf

    def closestPrecedingFinger(self, target_id: int):
        """
        Recorre la finger table (desde la más alta) y devuelve la primera
        que esté en (this.node_id, target_id) en el anillo.
        """
        for i in range(self.m_bits - 1, -1, -1):
            start_i, finger_node = self.finger[i]
            if finger_node is not None:
                fn_id, fn_ip, fn_port = finger_node
                if in_interval(fn_id, self.node_id, target_id, self.modulo):
                    return finger_node
        return (self.node_id, self.my_ip, self.my_port)

    def notify(self, candidate: tuple):
        """
        notify(candidate): 'candidate' cree que es mi predecesor.
        """
        if self.predecessor is None:
            self.predecessor = candidate
            logging.debug(f"[notify] {self.node_id} => predecessor = {candidate}")
        else:
            pred_id = self.predecessor[0]
            if in_interval(candidate[0], pred_id, self.node_id, self.modulo):
                logging.debug(f"[notify] {self.node_id} => actualiza predecessor => {candidate}")
                self.predecessor = candidate

    def stabilize(self):
        """
        1) x = successor.predecessor
        2) if x ∈ (this.node_id, successorID), successor = x
        3) successor.notify(this)
        """
        if self.successor[0] == self.node_id:
            return

        # 1) x = successor.predecessor
        x = self.remote_getPredecessor(self.successor[1], self.successor[2])
        if x:
            x_id, x_ip, x_port = x
            # 2) if x ∈ (this.node_id, successorID), successor = x
            if in_interval(x_id, self.node_id, self.successor[0], self.modulo):
                logging.debug(f"[stabilize] {self.node_id} => ajusta sucesor => {x}")
                self.successor = x

        # 3) successor.notify(this)
        self.remote_notify(self.successor[1], self.successor[2], (self.node_id, self.my_ip, self.my_port))

    def fixFingers(self):
        """
        Actualiza una entrada aleatoria de la finger table.
        """
        i = random.randint(0, self.m_bits - 1)
        start_i = (self.node_id + 2**i) % self.modulo
        succ = self.findSuccessor(start_i)
        self.finger[i] = (start_i, succ)
        logging.debug(f"[fixFingers] finger[{i}] = {succ}")


    def remote_findSuccessor(self, ip: str, port: int, key_id: int):
        ref = ChordNodeReference(ip, port, self.m_bits)
        return ref.findSuccessor(key_id)

    def remote_closestPrecedingFinger(self, ip: str, port: int, key_id: int):
        ref = ChordNodeReference(ip, port, self.m_bits)
        return ref.closestPrecedingFinger(key_id)

    def remote_getSuccessor(self, ip: str, port: int):
        ref = ChordNodeReference(ip, port, self.m_bits)
        return ref.getSuccessor()

    def remote_getPredecessor(self, ip: str, port: int):
        ref = ChordNodeReference(ip, port, self.m_bits)
        return ref.getPredecessor()

    def remote_notify(self, ip: str, port: int, candidate: tuple):
        ref = ChordNodeReference(ip, port, self.m_bits)
        return ref.notify(candidate)

    def upload_file(self, name: str, file_type: str, content: bytes) -> str:
        """
        Calcula la clave de enrutamiento usando el hash de nombre y tipo,
        busca el nodo responsable y delega (o almacena localmente) el archivo.
        """
        h_name_type = self.storage._hash_name_type(name, file_type)
        routing_key = int(h_name_type, 16) % self.modulo
        successor = self.findSuccessor(routing_key)
        if successor[0] == self.node_id:
            logging.info(f"[upload_file] Nodo {self.node_id} es responsable. Almacenando localmente.")
            return self.storage.store_file(name, file_type, content)
        else:
            logging.info(f"[upload_file] Nodo {self.node_id} delega en {successor}.")
            remote_ref = ChordNodeReference(successor[1], successor[2], self.m_bits)
            return remote_ref.storeFile(name, file_type, content)

    def handle_message(self, req: dict):
        method = req.get("method")
        params = req.get("params", {})

        try:
            if method == "findSuccessor":
                key_id = params["key_id"]
                r = self.findSuccessor(key_id)
                return {"result": r}
            elif method == "closestPrecedingFinger":
                key_id = params["key_id"]
                r = self.closestPrecedingFinger(key_id)
                return {"result": r}
            elif method == "getSuccessor":
                return {"result": self.successor}
            elif method == "getPredecessor":
                return {"result": self.predecessor}
            elif method == "notify":
                candidate = params["candidate"]
                self.notify(candidate)
                return {"result": True}
            elif method == "storeFile":
                name = params["name"]
                file_type = params["type"]
                content_str = params["content"]
                content = content_str.encode('latin1')
                key = self.storage.store_file(name, file_type, content)
                return {"result": key}
            elif method == "retrieveFile":
                key = params["key"]
                file_data = self.storage.retrieve_file(key)
                if file_data is not None:
                    file_data["content"] = file_data["content"].decode('latin1')
                return {"result": file_data}
            elif method == "retrieve_all_files":
                all_files = self.storage.retrieve_all_files()
                return {"result": all_files}
            else:
                return {"error": f"Método desconocido: {method}", "result": None}
        except Exception as e:
            logging.error(f"[handle_message] excepción: {e}")
            return {"error": str(e), "result": None}


def server_loop(chord_node: ChordNode):
    """
    Hilo que se queda escuchando conexiones entrantes en modo REP con ZeroMQ.
    """
    ctx = zmq.Context()
    rep_sock = ctx.socket(zmq.REP)
    rep_sock.bind(f"tcp://*:{chord_node.my_port}")
    logging.info(f"[server_loop] Nodo {chord_node.node_id} - listening on {chord_node.my_ip}:{chord_node.my_port}")

    while True:
        msg_str = rep_sock.recv_string()
        req = {}
        try:
            req = json.loads(msg_str)
            resp = chord_node.handle_message(req)
            if resp is None:
                resp = {"result": None, "error": "Null response?"}
        except Exception as e:
            logging.error(f"[server_loop] => excepción: {e}")
            resp = {"result": None, "error": str(e)}

        rep_sock.send_string(json.dumps(resp))


def maintenance_loop(chord_node: ChordNode):
    """
    Hilo que cada cierto tiempo llama a stabilize() y fixFingers().
    """
    while True:
        time.sleep(3)
        chord_node.stabilize()
        chord_node.fixFingers()

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')
    logging.info("=== Iniciando prueba de Chord con StorageLayer y Retrieval ===")

    # Nodo A
    nodeA = ChordNode(my_ip="127.0.0.1", my_port=6000, m_bits=16)
    tA_server = threading.Thread(target=server_loop, args=(nodeA,), daemon=True)
    tA_server.start()
    tA_maint = threading.Thread(target=maintenance_loop, args=(nodeA,), daemon=True)
    tA_maint.start()
    time.sleep(1)
    nodeA.createRing()

    # Nodo B
    nodeB = ChordNode(my_ip="127.0.0.1", my_port=6001, m_bits=16)
    tB_server = threading.Thread(target=server_loop, args=(nodeB,), daemon=True)
    tB_server.start()
    tB_maint = threading.Thread(target=maintenance_loop, args=(nodeB,), daemon=True)
    tB_maint.start()
    time.sleep(1)
    nodeB.join("127.0.0.1", 6000)

    # Nodo C
    nodeC = ChordNode(my_ip="127.0.0.1", my_port=6002, m_bits=16)
    tC_server = threading.Thread(target=server_loop, args=(nodeC,), daemon=True)
    tC_server.start()
    tC_maint = threading.Thread(target=maintenance_loop, args=(nodeC,), daemon=True)
    tC_maint.start()
    time.sleep(1)
    nodeC.join("127.0.0.1", 6000)

    logging.info("Esperando ~10s para que se estabilice el anillo...")
    time.sleep(10)

    # ------------------- Pruebas de Almacenamiento -------------------
    # Archivo 1: desde nodeA
    file1_name = "documento.txt"
    file1_type = "text/plain"
    file1_content = b"Contenido del documento 1"
    key1 = nodeA.upload_file(file1_name, file1_type, file1_content)
    logging.info(f"Archivo subido: {file1_name} con key {key1}")

    # Archivo 2: mismo nombre y tipo, pero contenido diferente, desde nodeB
    file2_name = "documento.txt"
    file2_type = "text/plain"
    file2_content = b"Contenido diferente del documento 1"
    key2 = nodeB.upload_file(file2_name, file2_type, file2_content)
    logging.info(f"Archivo subido: {file2_name} con key {key2}")

    # Archivo 3: desde nodeC
    file3_name = "imagen.png"
    file3_type = "image/png"
    file3_content = b"Datos de la imagen"
    key3 = nodeC.upload_file(file3_name, file3_type, file3_content)
    logging.info(f"Archivo subido: {file3_name} con key {key3}")

    # ------------------- Pruebas de Recuperación -------------------
    # Recuperar archivo 1 (usando nodeA, que es responsable o delega según corresponda)
    req_all_A = {"method": "retrieve_all_files", "params": {}}
    result_all_A = nodeA.handle_message(req_all_A)
    logging.info(f"Recuperados todos los archivos en nodo A: {result_all_A}")

    # Se recuperan todos los archivos almacenados en el nodo B
    req_all_B = {"method": "retrieve_all_files", "params": {}}
    result_all_B = nodeB.handle_message(req_all_B)
    logging.info(f"Recuperados todos los archivos en nodo B: {result_all_B}")

    req_all_C = {"method": "retrieve_all_files", "params": {}}
    result_all_C = nodeC.handle_message(req_all_C)
    logging.info(f"Recuperados todos los archivos en nodo C: {result_all_C}")


    logging.info("Pruebas de almacenamiento y recuperación completadas. Los nodos permanecen en funcionamiento... (Ctrl+C para salir)")
    try:
        while True:
            time.sleep(9999)
    except KeyboardInterrupt:
        logging.info("Saliendo...")
        sys.exit(0)