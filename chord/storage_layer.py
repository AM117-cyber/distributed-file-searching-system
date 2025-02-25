import sqlite3
import hashlib
import threading

class SQLiteConnectionManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.local = threading.local()

    def get_connection(self):
        if not hasattr(self.local, 'connection'):
            self.local.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        return self.local.connection

class StorageLayer:
    def __init__(self, db_path='files.db'):
        self.db_path = db_path

        self.connection_manager = SQLiteConnectionManager(db_path)
        self.connection = self.connection_manager.get_connection()
        self._create_tables()
        self.files_index = {}

    def _create_tables(self):
        with self.connection:
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS files (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    type TEXT,
                    hash_name_type TEXT,
                    hash_content TEXT,
                    content BLOB
                )
            ''')

    def _hash_name_type(self, name: str, file_type: str) -> str:
        combined = f"{name}:{file_type}"
        return hashlib.sha1(combined.encode('utf-8')).hexdigest()

    def _hash_content(self, content: bytes) -> str:
        return hashlib.sha1(content).hexdigest()

    def _generate_key(self, name: str, file_type: str, content: bytes) -> (str, str, str):
        h_name_type = self._hash_name_type(name, file_type)
        h_content = self._hash_content(content)
        # Usamos la concatenación de ambos hashes para formar la clave única
        composite_key = f"{h_name_type}_{h_content}"
        return composite_key, h_name_type, h_content

    def store_file(self, name: str, file_type: str, content: bytes) -> str:
        """
        Almacena un archivo dado su nombre, tipo y contenido (en bytes).
        Retorna la clave única del archivo.
        """
        key, h_name_type, h_content = self._generate_key(name, file_type, content)

        with self.connection:
            self.connection.execute('''
                INSERT OR REPLACE INTO files (id, name, type, hash_name_type, hash_content, content)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (key, name, file_type, h_name_type, h_content, content))

        self.files_index[key] = {
            "name": name,
            "type": file_type,
            "hash_name_type": h_name_type,
            "hash_content": h_content
        }
        return key

    def retrieve_file(self, key: str) -> dict:
        """
        Recupera el archivo asociado a la clave proporcionada.
        Retorna un diccionario con el nombre, tipo y contenido si se encuentra, de lo contrario None.
        """
        cur = self.connection.cursor()
        cur.execute("SELECT name, type, content FROM files WHERE id = ?", (key,))
        row = cur.fetchone()
        if row:
            name, file_type, content = row
            return {"name": name, "type": file_type, "content": content}
        return None

    def retrieve_all_files(self) -> dict:
        cur = self.connection.cursor()
        cur.execute("SELECT id, name, type FROM files")
        rows = cur.fetchall()
        return {key: {"name": name, "type": file_type} for key, name, file_type in rows}
