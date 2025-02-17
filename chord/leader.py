import socket
import threading
import time
import logging

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')

logger = logging.getLogger(__name__)

OK = 2
ELECTION = 1
WINNER = 3

PORT = 8005

def broadcast_call(message: str, port: int):
    """
    Envía 'message' por broadcast UDP en el puerto 'port'.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.sendto(message.encode('utf-8'), ('<broadcast>', port))
    s.close()

class BullyBroadcastElector:
    """
    Implementación del algoritmo de elección Bully usando
    mensajes UDP en broadcast.

    Atributos principales:
      - id: Identificador local (por defecto, la IP local).
      - Leader: El líder actual (None si no hay).
      - InElection: Indica si estamos en medio de un proceso de elección.
      - ImTheLeader: Indica si NOSOTROS somos el líder.
      - port: el puerto UDP donde escuchamos y enviamos broadcast.
    """
    def __init__(self):
        try:
            self.id = socket.gethostbyname(socket.gethostname())
        except socket.gaierror:
            self.id = "127.0.0.1"

        self.port = PORT

        self.Leader = None
        self.InElection = False
        self.ImTheLeader = False
        self.InElectionSwap = False

    def bully(self, id_local: str, id_otro: str) -> bool:
        """
        Comparación del "poder" de dos IDs (tipo string).
        Retorna True si 'id_local' > 'id_otro'.

        En este ejemplo, se toma la última parte de la IP y
        se compara numéricamente. Ajusta según tus necesidades
        (por ejemplo, comparando todo como entero).
        """
        return int(id_local.split('.')[-1]) > int(id_otro.split('.')[-1])

    def election_call(self):
        """
        Inicia la elección, enviando por broadcast el mensaje ELECTION.
        """
        t = threading.Thread(target=broadcast_call, args=(f'{ELECTION}', self.port))
        t.start()

    def winner_call(self):
        """
        Indica que nos declaramos ganadores, enviando WINNER.
        """
        t = threading.Thread(target=broadcast_call, args=(f'{WINNER}', self.port))
        t.start()

    def loop(self):
        """
        Hilo que maneja la lógica temporal de la elección:

        - Espera un tiempo en el que podrían llegar OKs de nodos
          "más poderosos". Si no llegan, nos autoproclamamos líder.
        - Cada ciclo de ~1s chequea si se ha resuelto la elección.

        Este bucle finaliza cuando:
          - Dejamos de estar en elección, o
          - Se cumple un número de iteraciones (p.e. 3) sin resolver.
        """
        counter = 0
        while True:
            counter += 1
            if not self.Leader and not self.InElection:
                self.InElection = True
                self.InElectionSwap = False
                self.election_call()

            if self.InElection:
                if counter == 3:
                    if not self.Leader and self.ImTheLeader:
                        self.Leader = self.id
                        self.winner_call()
                    self.InElection = False
                    counter = 0
                    break

            if counter == 3:
                break

            time.sleep(1)


    def data_receive(self, newId: str, msg: str):
        """
        Procesa un mensaje (string) llegado por UDP de la IP newId.
        Puede ser un ELECTION, OK o WINNER.
        """
        msg_val = int(msg)

        if msg_val == ELECTION and newId != self.id:
            logger.debug(f"BULLY => Recibido ELECTION de {newId}")

            if not self.InElection and not self.InElectionSwap:
                self.InElectionSwap = True
                self.Leader = None
                self.ImTheLeader = True
                threading.Thread(target=self.loop, daemon=True).start()

            if self.bully(self.id, newId):
                logger.debug(f"BULLY => Enviando OK a {newId}")
                s_send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s_send.sendto(f'{OK}'.encode('utf-8'), (newId, self.port))

        elif msg_val == OK:
            logger.debug(f"BULLY => Recibido OK de {newId}, resignando liderazgo")
            self.ImTheLeader = False

        elif msg_val == WINNER:
            logger.debug(f"BULLY => Recibido WINNER de {newId}")
            if not self.bully(self.id, newId):

                if (not self.Leader) or self.bully(newId, self.Leader):
                    self.Leader = newId
                    self.ImTheLeader = (self.Leader == self.id)
                    self.InElection = False


    def server_thread(self):
        """
        Hilo que escucha en self.port mensajes UDP de otros nodos
        y despacha data_receive.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        s.bind(('', self.port))

        logger.debug(f"[Bully] Escuchando UDP en puerto {self.port}. Mi ID={self.id}")

        while True:
            try:
                msg, sender = s.recvfrom(1024)
                if not msg:
                    continue

                newId = sender[0]
                msg_str = msg.decode("utf-8")


                threading.Thread(target=self.data_receive, args=(newId, msg_str), daemon=True).start()

            except Exception as e:
                logger.error(f"Bully => Error en server_thread: {e}")