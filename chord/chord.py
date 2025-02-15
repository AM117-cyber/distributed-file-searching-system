import zmq
import json
import hashlib
import logging
import threading
import time
import random
import argparse
import sys

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

class ChordNode:
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

        logging.info(f"[INIT] ChordNode - ID={self.node_id} - Escuchando en {my_ip}:{my_port}")

    def createRing(self):
        """
        Crea un anillo donde este nodo es el único miembro.
        Me apunto como mi sucesor.
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
        succ = self.remote_findSuccessor(known_ip, known_port, self.node_id)
        if succ is not None:
            self.successor = succ
            logging.info(f"[join] Exito. Mi sucesor inicial: {self.successor}")
        else:
            logging.error("[join] Error: no se pudo obtener sucesor remoto.")

    def findSuccessor(self, target_id: int):
        """
        findSuccessor(target_id):
          - Si target_id ∈ (this.node_id, successorID], devuelvo self.successor
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
            return self.remote_findSuccessor(cpf[1], cpf[2], target_id)

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
        x = self.remote_getPredecessor(self.successor[1], self.successor[2])
        if x:
            x_id, x_ip, x_port = x
            if in_interval(x_id, self.node_id, self.successor[0], self.modulo):
                logging.debug(f"[stabilize] {self.node_id} => ajusta sucesor => {x}")
                self.successor = x

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
        req = {"method": "findSuccessor", "params": {"key_id": key_id}}
        return self._send_zmq_request(ip, port, req)

    def remote_closestPrecedingFinger(self, ip: str, port: int, key_id: int):
        req = {"method": "closestPrecedingFinger", "params": {"key_id": key_id}}
        return self._send_zmq_request(ip, port, req)

    def remote_getSuccessor(self, ip: str, port: int):
        req = {"method": "getSuccessor", "params": {}}
        return self._send_zmq_request(ip, port, req)

    def remote_getPredecessor(self, ip: str, port: int):
        req = {"method": "getPredecessor", "params": {}}
        return self._send_zmq_request(ip, port, req)

    def remote_notify(self, ip: str, port: int, candidate: tuple):
        req = {"method": "notify", "params": {"candidate": candidate}}
        return self._send_zmq_request(ip, port, req)

    def _send_zmq_request(self, ip: str, port: int, req: dict):
        """
        Crea un socket REQ, se conecta a (ip, port), envía 'req' en JSON y lee respuesta.
        Retorna 'result' del JSON si todo va bien, None si error.
        """
        ctx = zmq.Context()
        sock = ctx.socket(zmq.REQ)
        sock.connect(f"tcp://{ip}:{port}")
        try:
            sock.send_string(json.dumps(req))
            resp_str = sock.recv_string()
            resp = json.loads(resp_str)
            error = resp.get("error")
            if error:
                logging.error(f"_send_zmq_request => error remoto: {error}")
                return None
            return resp.get("result")
        except Exception as e:
            logging.error(f"_send_zmq_request => excepción {e}")
            return None
        finally:
            sock.close()
            ctx.term()

    def handle_message(self, req: dict):
        """
        Invocado cuando llega un mensaje REP. Retorna dict con 'result'/'error'.
        """
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

            else:
                return {"error": f"Método desconocido: {method}", "result": None}

        except Exception as e:
            logging.error(f"handle_message => exception: {e}")
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
            logging.error(f"server_loop => exception: {e}")
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

    logging.info("=== Iniciando prueba de anillo Chord ===")

    nodeA = ChordNode(my_ip="127.0.0.1", my_port=6000, m_bits=16)

    tA_server = threading.Thread(target=server_loop, args=(nodeA,), daemon=True)
    tA_server.start()
    tA_maint = threading.Thread(target=maintenance_loop, args=(nodeA,), daemon=True)
    tA_maint.start()

    time.sleep(1)
    nodeA.createRing()

    nodeB = ChordNode(my_ip="127.0.0.1", my_port=6001, m_bits=16)
    tB_server = threading.Thread(target=server_loop, args=(nodeB,), daemon=True)
    tB_server.start()
    tB_maint = threading.Thread(target=maintenance_loop, args=(nodeB,), daemon=True)
    tB_maint.start()

    time.sleep(1)
    nodeB.join("127.0.0.1", 6000)


    nodeC = ChordNode(my_ip="127.0.0.1", my_port=6002, m_bits=16)
    tC_server = threading.Thread(target=server_loop, args=(nodeC,), daemon=True)
    tC_server.start()
    tC_maint = threading.Thread(target=maintenance_loop, args=(nodeC,), daemon=True)
    tC_maint.start()

    time.sleep(1)

    nodeC.join("127.0.0.1", 6000)

    logging.info("Esperando ~10s para que se estabilice el anillo...")
    time.sleep(10)

    test_key = sha1_hash("test-key") % (2**16)
    logging.info(f"Buscando sucesor de {test_key} via nodeA...")
    resA = nodeA.findSuccessor(test_key)
    logging.info(f"nodeA => findSuccessor({test_key}) = {resA}")

    logging.info("Buscando Predecessor(10000) via nodeB...")
    resB = nodeB.findPredecessor(10000)
    logging.info(f"nodeB => findPredecessor(10000) = {resB}")

    logging.info("Nodos levantados y probados. Se quedan en funcionamiento... (Ctrl+C para salir)")
    try:
        while True:
            time.sleep(9999)
    except KeyboardInterrupt:
        logging.info("Saliendo...")
        sys.exit(0)
