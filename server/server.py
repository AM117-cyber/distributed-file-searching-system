# server/myserver.py

import socket
import threading
import os
import sqlite3
import hashlib

# Directorio para almacenar archivos
FILE_DIR = '/app/server_files'
DB_FILE = 'db/files.db'

def save_file(file_content, filename):
    filepath = os.path.join(FILE_DIR, filename)
    with open(filepath, 'wb') as f:
        f.write(file_content)
    return filepath

def setup_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filetype TEXT,
            filesize INTEGER,
            filepath TEXT,
            hash TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS file_names (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER,
            name TEXT,
            FOREIGN KEY (file_id) REFERENCES files (id)
        )
    ''')
    conn.commit()
    conn.close()

def check_file_name_and_type(filename, filetype):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Search for the file name in the file_names table
    cursor.execute('SELECT file_id FROM file_names WHERE name = ?', (filename,))
    file_ids = cursor.fetchall()

    if not file_ids:
        return False  # No files with the given name found

    # Check if any of the files have the same type
    cursor.execute('SELECT filetype FROM files WHERE id IN ({})'.format(','.join('?' * len(file_ids))),
                   [file_id[0] for file_id in file_ids])
    file_types = cursor.fetchall()

    conn.close()

    for existing_filetype in file_types:
        if existing_filetype[0] == filetype:
            return True  # File with the same name and type exists

    return False  # No file with the same name and type found


def calculate_file_hash(filepath):
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        buf = f.read()
        while buf:
            hasher.update(buf)
            buf = f.read(1048576)  # Read in chunks to handle large files
    return hasher.hexdigest()

def handle_client(client_socket):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    while True:
        command = client_socket.recv(1048576).decode()

        if command.startswith('UPLOAD'):
            filename = command.split(" == ")[1]
            filesize = int(command.split(" == ")[2])
            filetype = filename.split('.')[-1]
            filename = filename.split("."+filetype)[0]
            name_with_type = f"{filename}.{filetype}"
            filepath = os.path.join(FILE_DIR, name_with_type)
            invalid_name = check_file_name_and_type(filename, filetype)
            if invalid_name:
                client_socket.send(b'There is already a file with that name. Please change the name and try again.')
                continue
            client_socket.send(b'Valid')
            # Compare metadata first
            cursor.execute('SELECT id, hash FROM files WHERE filesize = ? AND filetype = ?', (filesize, filetype))
            potential_duplicates = cursor.fetchall()

            duplicate_found = False
            with open(filepath, 'wb') as f:
                bytes_received = 0
                while bytes_received < filesize:
                    data = client_socket.recv(1048576)
                    f.write(data)
                    bytes_received += len(data)
            my_hash = calculate_file_hash(filepath)
            for file_id, hash in potential_duplicates:

                if my_hash == hash:
                    # file is the same
                    cursor.execute('SELECT name FROM file_names WHERE file_id = ? AND name = ?', (file_id, filename))
                    name_result = cursor.fetchone()
                    if not name_result:
                        cursor.execute('INSERT INTO file_names (file_id, name) VALUES (?, ?)', (file_id, filename))
                        conn.commit()
                    os.remove(filepath)  # Remove the duplicate file
                    client_socket.send(b'UPLOAD SUCCESS (duplicate)')
                    duplicate_found = True
                    break

            if not duplicate_found:
                cursor.execute('INSERT INTO files (filetype, filesize, filepath, hash) VALUES (?, ?, ?, ?)',
                               (filetype, filesize, filepath, my_hash))
                file_id = cursor.lastrowid
                cursor.execute('INSERT INTO file_names (file_id, name) VALUES (?, ?)', (file_id, filename))
                conn.commit()
                client_socket.send(b'UPLOAD SUCCESS')

        elif command.startswith('SEARCH'):
            filename = command.split(" == ")[1]
            filetype = command.split(" == ")[2]
            if filename == "" and filetype == "":
                cursor.execute('''
                    SELECT files.id, files.filetype, file_names.name
                    FROM files
                    JOIN file_names ON files.id = file_names.file_id
                    GROUP BY files.id
                    ''')
            elif filename == "":
                cursor.execute('''
                    SELECT files.id, files.filetype, file_names.name
                    FROM files
                    JOIN file_names ON files.id = file_names.file_id
                    WHERE files.filetype = ?
                    GROUP BY files.id
                    ''', (filetype,))
            elif filetype == "":
                cursor.execute('''
                    SELECT files.id, files.filetype, file_names.name
                    FROM files
                    JOIN file_names ON files.id = file_names.file_id
                    WHERE file_names.name LIKE ?
                    GROUP BY files.id
                    ''', (f'%{filename}%',))
            else:
                cursor.execute('''
                    SELECT files.id, files.filetype, file_names.name
                    FROM files
                    JOIN file_names ON files.id = file_names.file_id
                    WHERE file_names.name LIKE ? AND files.filetype = ?
                    GROUP BY files.id
                    ''', (f'%{filename}%', filetype))
            results = cursor.fetchall()

            if results:
                client_socket.send(f'FOUND {len(results)}'.encode())
                for result in results:
                    # filename.type == id
                    client_socket.send(f'{result[2]}.{result[1]} == {result[0]}'.encode())
                    client_socket.recv(1048576)  # Wait for ACK
            else:
                client_socket.send(b'NOT FOUND')

        elif command.startswith('DOWNLOAD'):
            # filename = command.split(" == ")[1]
            # filetype = filename.split('.')[-1]
            # filename = filename.split("."+filetype)[0]
            # name_with_type = f"{filename}.{filetype}"
            # filepath = os.path.join(FILE_DIR, name_with_type)
            id = command.split(" == ")[1]
            cursor.execute('SELECT filepath FROM files WHERE id = ?', (id))
            result = cursor.fetchone()
            if result:
                filepath = result[0]  # Extract the file path from the tuple
            if os.path.exists(filepath):
                filesize = os.path.getsize(filepath)
                client_socket.send(f"FileSize {filesize}".encode())
                with open(filepath, 'rb') as f:
                    data = f.read(1048576)
                    while data:
                        client_socket.send(data)
                        data = f.read(1048576)
            else:
                client_socket.send(b'ERROR File not found')

        elif command == 'EXIT':
            client_socket.close()
            break
    conn.close()

def main():
    if not os.path.exists(FILE_DIR):
        os.makedirs(FILE_DIR)
    setup_database()
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('0.0.0.0', 5000))
    server_socket.listen(5)
    print("Server listening...")
    while True:
        client_socket, addr = server_socket.accept()
        print(f"Got a connection from {addr}")
        client_handler = threading.Thread(target=handle_client, args=(client_socket,))
        client_handler.start()

if __name__ == '__main__':
    main()