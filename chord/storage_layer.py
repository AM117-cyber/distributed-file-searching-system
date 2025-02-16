from chord import *

class StorageLayer(ChordNode):
    """
    Almacenamiento .
    Se separan dos registros:
      - Registro de metadatos: se almacena usando la clave calculada a partir de file_name y file_type.
        Contiene: file_name, file_type y content_key (clave del contenido).
      - Registro de contenido: se almacena usando la clave derivada del hash del contenido.
        Contiene: content y content_hash.
    """
    def __init__(self, my_ip: str, my_port: int, m_bits: int = 16):
        super().__init__(my_ip, my_port, m_bits)
        self.metadata = {}  # key_metadata -> { 'file_name': ..., 'file_type': ..., 'content_key': ... }
        self.contents = {}  # key_content -> { 'content': ..., 'content_hash': ... }

    def compute_metadata_key(self, file_name: str, file_type: str) -> int:
        key_str = f"{file_name}.{file_type}"
        return sha1_hash(key_str) % self.modulo

    def compute_content_key(self, content: str) -> int:
        content_hash = hashlib.sha1(content.encode('utf-8')).hexdigest()
        # Convertimos el hash hexadecimal a entero y lo mapeamos al anillo
        return int(content_hash, 16) % self.modulo

    def storeFile(self, file_name: str, file_type: str, content: str):
        """
        Almacena un archivo de forma deduplicada:
          1. Calcula la clave de metadatos a partir de file_name.file_type.
          2. Calcula el content_hash y la clave de contenido.
          3. Se almacena el registro de metadatos en el nodo responsable de metadata_key.
          4. Se almacena el registro de contenido en el nodo responsable de content_key, si no existe ya.
        """
        metadata_key = self.compute_metadata_key(file_name, file_type)
        content_key = self.compute_content_key(content)
        # Calculamos el hash del contenido para los metadatos (en formato hexadecimal)
        content_hash = hashlib.sha1(content.encode('utf-8')).hexdigest()

        # Usamos findSuccessor para determinar el nodo responsable del registro de metadatos.
        responsible_meta = self.findSuccessor(metadata_key)
        if responsible_meta[0] == self.node_id:
            # Este nodo es responsable de los metadatos: almacena o actualiza.
            self.metadata[metadata_key] = {
                'file_name': file_name,
                'file_type': file_type,
                'content_key': content_key,
                'content_hash': content_hash
            }
            logging.info(f"[storeFile-Meta] '{file_name}.{file_type}' almacenado en nodo {self.node_id} con metadata_key {metadata_key}.")
        else:
            logging.info(f"[storeFile-Meta] Redirigiendo '{file_name}.{file_type}' al nodo {responsible_meta[0]} para metadatos.")
            return self.remote_storeFile_metadata(responsible_meta[1], responsible_meta[2], file_name, file_type, content_key, content_hash)

        # Ahora, almacenar el contenido en el nodo responsable de content_key.
        responsible_cont = self.findSuccessor(content_key)
        if responsible_cont[0] == self.node_id:
            # Si no existe ya, almacena el contenido.
            if content_key not in self.contents:
                self.contents[content_key] = {
                    'content': content,
                    'content_hash': content_hash
                }
                logging.info(f"[storeFile-Content] Contenido almacenado en nodo {self.node_id} con content_key {content_key}.")
            else:
                logging.info(f"[storeFile-Content] Contenido ya existente en nodo {self.node_id} con content_key {content_key}.")
            return True
        else:
            logging.info(f"[storeFile-Content] Redirigiendo contenido al nodo {responsible_cont[0]} (content_key {content_key}).")
            return self.remote_storeFile_content(responsible_cont[1], responsible_cont[2], content, content_key, content_hash)

    def remote_storeFile_metadata(self, ip: str, port: int, file_name: str, file_type: str, content_key: int, content_hash: str):
        req = {
            "method": "storeFile",
            "params": {
                "file_name": file_name,
                "file_type": file_type,
                "content_key": content_key,
                "content_hash": content_hash,
                "is_metadata": True
            }
        }
        return self._send_zmq_request(ip, port, req)

    def remote_storeFile_content(self, ip: str, port: int, content: str, content_key: int, content_hash: str):
        req = {
            "method": "storeFile",
            "params": {
                "content": content,
                "content_key": content_key,
                "content_hash": content_hash,
                "is_metadata": False
            }
        }
        return self._send_zmq_request(ip, port, req)

    def retrieveFile(self, file_name: str, file_type: str):
        """
        Recupera un archivo de la siguiente manera:
          1. Calcula la metadata_key a partir de file_name.file_type y consulta el registro de metadatos.
          2. Desde el registro se obtiene el content_key y content_hash.
          3. Se usa content_key para buscar el registro de contenido y retornar el contenido.
        """
        metadata_key = self.compute_metadata_key(file_name, file_type)
        responsible_meta = self.findSuccessor(metadata_key)
        if responsible_meta[0] == self.node_id:
            meta = self.metadata.get(metadata_key)
            if not meta:
                logging.warning(f"[retrieveFile-Meta] No se encontró registro de metadatos para '{file_name}.{file_type}' en nodo {self.node_id}.")
                return None
        else:
            meta = self.remote_retrieveFile_metadata(responsible_meta[1], responsible_meta[2], file_name, file_type)
            if not meta:
                logging.warning(f"[retrieveFile-Meta] No se encontró registro remoto para '{file_name}.{file_type}'.")
                return None

        content_key = meta['content_key']
        responsible_cont = self.findSuccessor(content_key)
        if responsible_cont[0] == self.node_id:
            cont = self.contents.get(content_key)
            if not cont:
                logging.warning(f"[retrieveFile-Content] No se encontró contenido para key {content_key} en nodo {self.node_id}.")
                return None
            return cont['content']
        else:
            return self.remote_retrieveFile_content(responsible_cont[1], responsible_cont[2], file_name, file_type)

    def remote_retrieveFile_metadata(self, ip: str, port: int, file_name: str, file_type: str):
        req = {
            "method": "retrieveFile",
            "params": {
                "file_name": file_name,
                "file_type": file_type,
                "is_metadata": True
            }
        }
        return self._send_zmq_request(ip, port, req)

    def remote_retrieveFile_content(self, ip: str, port: int, file_name: str, file_type: str):
        req = {
            "method": "retrieveFile",
            "params": {
                "file_name": file_name,
                "file_type": file_type,
                "is_metadata": False
            }
        }
        return self._send_zmq_request(ip, port, req)

    def handle_message(self, req: dict):
        """
        Extiende el handler de la capa base para incorporar operaciones de almacenamiento.
        Si se recibe una solicitud con "storeFile" o "retrieveFile" y se indica el flag is_metadata,
        se almacena o recupera la parte correspondiente.
        """
        method = req.get("method")
        params = req.get("params", {})

        if method == "storeFile":
            # Diferenciar entre almacenar metadatos y contenido.
            is_metadata = params.get("is_metadata", True)
            if is_metadata:
                file_name = params["file_name"]
                file_type = params["file_type"]
                content_key = params["content_key"]
                content_hash = params["content_hash"]
                # Almacenar el registro de metadatos
                key = self.compute_metadata_key(file_name, file_type)
                self.metadata[key] = {
                    'file_name': file_name,
                    'file_type': file_type,
                    'content_key': content_key,
                    'content_hash': content_hash
                }
                logging.info(f"[storeFile-Meta] Registro de metadatos almacenado en nodo {self.node_id} (key {key}).")
                return {"result": True}
            else:
                # Almacenar contenido
                content = params["content"]
                content_key = params["content_key"]
                content_hash = params["content_hash"]
                if content_key not in self.contents:
                    self.contents[content_key] = {
                        'content': content,
                        'content_hash': content_hash
                    }
                    logging.info(f"[storeFile-Content] Contenido almacenado en nodo {self.node_id} (key {content_key}).")
                else:
                    logging.info(f"[storeFile-Content] Contenido ya existente en nodo {self.node_id} (key {content_key}).")
                return {"result": True}
        elif method == "retrieveFile":
            is_metadata = params.get("is_metadata", True)
            if is_metadata:
                file_name = params["file_name"]
                file_type = params["file_type"]
                key = self.compute_metadata_key(file_name, file_type)
                meta = self.metadata.get(key)
                logging.info(f"[retrieveFile-Meta] Nodo {self.node_id} retorna metadatos para key {key}: {meta}")
                return {"result": meta}
            else:
                # Recuperar contenido
                file_name = params["file_name"]
                file_type = params["file_type"]
                # Calculamos la metadata para obtener el content_key.
                key = self.compute_metadata_key(file_name, file_type)
                meta = self.metadata.get(key)
                if not meta:
                    logging.warning(f"[retrieveFile-Content] No se encontraron metadatos en nodo {self.node_id} para '{file_name}.{file_type}'.")
                    return {"result": None}
                content_key = meta['content_key']
                cont = self.contents.get(content_key)
                logging.info(f"[retrieveFile-Content] Nodo {self.node_id} retorna contenido para key {content_key}: {cont}")
                return {"result": cont}
        else:
            return super().handle_message(req)


def server_loop(node):
    """Hilo que se queda escuchando peticiones RPC vía ZeroMQ."""
    ctx = zmq.Context()
    rep_sock = ctx.socket(zmq.REP)
    rep_sock.bind(f"tcp://*:{node.my_port}")
    logging.info(f"[server_loop] Nodo {node.node_id} escuchando en {node.my_ip}:{node.my_port}")
    while True:
        try:
            msg_str = rep_sock.recv_string()
            req = json.loads(msg_str)
            resp = node.handle_message(req)
        except Exception as e:
            logging.error(f"server_loop exception: {e}")
            resp = {"result": None, "error": str(e)}
        rep_sock.send_string(json.dumps(resp))


if __name__ == "__main__":
    logging.info("Prueba")

    nodeA = StorageLayer(my_ip="127.0.0.1", my_port=6000, m_bits=16)
    nodeB = StorageLayer(my_ip="127.0.0.1", my_port=6001, m_bits=16)
    nodeC = StorageLayer(my_ip="127.0.0.1", my_port=6002, m_bits=16)

    tA_server = threading.Thread(target=server_loop, args=(nodeA,), daemon=True)
    tB_server = threading.Thread(target=server_loop, args=(nodeB,), daemon=True)
    tC_server = threading.Thread(target=server_loop, args=(nodeC,), daemon=True)
    tA_server.start()
    tB_server.start()
    tC_server.start()

    tA_maint = threading.Thread(target=maintenance_loop, args=(nodeA,), daemon=True)
    tB_maint = threading.Thread(target=maintenance_loop, args=(nodeB,), daemon=True)
    tC_maint = threading.Thread(target=maintenance_loop, args=(nodeC,), daemon=True)
    tA_maint.start()
    tB_maint.start()
    tC_maint.start()

    time.sleep(1)
    nodeA.createRing()
    time.sleep(1)
    nodeB.join("127.0.0.1", 6000)
    nodeC.join("127.0.0.1", 6000)

    time.sleep(5)

    contenido = "Este es el contenido idéntico de todos los archivos."
    logging.info("Almacenando 'file1.mkv'...")
    nodeA.storeFile("file1", "mkv", contenido)
    logging.info("Almacenando 'file2.kmp'...")
    nodeA.storeFile("file2", "kmp", contenido)
    logging.info("Almacenando 'file1.jpg'...")
    nodeA.storeFile("file1", "jpg", contenido)

    time.sleep(2)
    logging.info("Recuperando 'file1.mkv'...")
    res1 = nodeB.retrieveFile("file1", "mkv")
    logging.info(f"Resultado: {res1}")
    logging.info("Recuperando 'file2.kmp'...")
    res2 = nodeB.retrieveFile("file2", "kmp")
    logging.info(f"Resultado: {res2}")
    logging.info("Recuperando 'file1.jpg'...")
    res3 = nodeB.retrieveFile("file1", "jpg")
    logging.info(f"Resultado: {res3}")

    logging.info("Prueba finalizada. Presiona Ctrl+C para salir.")
    try:
        while True:
            time.sleep(9999)
    except KeyboardInterrupt:
        logging.info("Saliendo...")
        sys.exit(0)