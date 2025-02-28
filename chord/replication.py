# from chord import ChordNode, ChordNodeReference
import logging

class ReplicationManager:
    def __init__(self, chord_node):
        self.node = chord_node

    def stabilize_files(self):
        """
        Recorre cada archivo almacenado localmente y asegura que:
        - Si este nodo no es el responsable (según la clave de enrutamiento), reenvía el archivo al nodo responsable.
        - Independientemente, se invoca la replicación usando el contenido ya almacenado.
        """
        for key in list(self.node.storage.files_index.keys()):
            file_data = self.node.storage.retrieve_file(key)
            if file_data is None:
                continue

            file_name = file_data["name"]
            file_type = file_data["type"]
            content = file_data["content"]

            # Calcular la clave de enrutamiento.
            h_name_type = self.node.storage._hash_name_type(file_name, file_type)
            routing_key = int(h_name_type, 16) % (2**self.node.m)

            responsible = self.node.find_succ(routing_key)

            if responsible.id != self.node.id:
                # Usamos get_reference para obtener la instancia del nodo responsable
                responsible_instance = self.node.get_reference(responsible)
                if responsible_instance is not None:
                    new_key = responsible_instance.storage.store_file(file_name, file_type, content)
                    if new_key:
                        logging.info(f"[ReplicationManager] Reinsertado '{file_name}' en nodo {responsible} (new_key={new_key}).")
                        key_to_replicate = new_key
                    else:
                        logging.error(f"[ReplicationManager] Error al reinsertar '{file_name}' en nodo {responsible}.")
                        key_to_replicate = key
                else:
                    logging.error(f"[ReplicationManager] No se encontró la instancia del nodo {responsible}.")
                    key_to_replicate = key
            else:
                key_to_replicate = key
                responsible = responsible

            self.replicate_file(responsible, key_to_replicate, file_data)

    def replicate_file(self, responsible_node, file_key: str, file_data: dict):
        """
        Replica el archivo dado a dos sucesores distintos del nodo responsable.
        """
        # Obtener el primer sucesor
        succ1 = responsible_node.succ
        # Obtener el segundo sucesor a partir del primer sucesor
        succ2 = succ1.succ

        # Obtener las instancias reales de los nodos sucesores usando get_reference
        node_succ1 = self.node.get_reference(succ1)
        node_succ2 = self.node.get_reference(succ2)

        if node_succ1 is None:
            logging.error(f"[ReplicationManager] No se encontró la instancia para el primer sucesor: {succ1}")
            return

        # Replicar en el primer sucesor
        resp1 = node_succ1.storage.store_file(file_data["name"], file_data["type"], file_data["content"])

        # Replicar en el segundo sucesor, si se encontró y es distinto
        if node_succ2 and (succ2.id != succ1.id):
            resp2 = node_succ2.storage.store_file(file_data["name"], file_data["type"], file_data["content"])
        else:
            resp2 = None

        if resp1 and (resp2 or node_succ2 is None):
            logging.info(f"[ReplicationManager] Archivo replicado en nodo {succ1} " +
                         (f" y en nodo {succ2}" if node_succ2 else " (solo replicado en el primer sucesor)") +
                         f" (desde {responsible_node}).")
        else:
            logging.error(f"[ReplicationManager] Falló replicación del archivo con key {file_key} desde {responsible_node}.")
