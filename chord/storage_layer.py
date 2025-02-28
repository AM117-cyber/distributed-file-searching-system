import sqlite3
import hashlib
import logging

class StorageLayer:
    def __init__(self, db_path='files.db'):
        self.db_path = db_path
        # Se permite uso en distintos hilos (ver concurrencia)
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._create_tables()
        # Diccionario en memoria para acelerar búsquedas (clave -> metadatos)
        self.files_index = {}

    def _create_tables(self):
        with self.connection:
            # Se elimina cualquier columna de rol, pues ya no se diferencia
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

    def _generate_key(self, name: str, file_type: str, content: bytes) -> (str, str, str):
        h_name_type = self._hash_name_type(name, file_type)
        h_content = hashlib.sha1(content).hexdigest()
        composite_key = f"{h_name_type}_{h_content}"
        return composite_key, h_name_type, h_content

    def store_file(self, name: str, file_type: str, content: bytes) -> str:
        key, h_name_type, h_content = self._generate_key(name, file_type, content)
        logging.info(f"[StorageLayer] Inserting file '{name}' with key {key}.")
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
        logging.info(f"[StorageLayer] Stored file '{name}' with key {key}")
        return key

    def retrieve_file(self, key: str) -> dict:
        cur = self.connection.cursor()
        cur.execute("SELECT name, type, content FROM files WHERE id = ?", (key,))
        row = cur.fetchone()
        if row:
            name, file_type, content = row
            logging.info(f"[StorageLayer] Retrieved file with key {key}: {name}")
            return {"name": name, "type": file_type, "content": content}
        logging.error(f"[StorageLayer] File with key {key} not found.")
        return None


    def delete_file(self, key: str):
        with self.connection:
            self.connection.execute("DELETE FROM files WHERE id = ?", (key,))
        if key in self.files_index:
            del self.files_index[key]
        logging.info(f"[StorageLayer] Deleted file with key {key}")
