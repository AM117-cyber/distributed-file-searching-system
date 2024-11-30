# server/myserver.py

import socket
import threading
import os

# Directorio para almacenar archivos
FILE_DIR = '/app/server_files'

def handle_client(client_socket):
    while True:
        # Receive command from client
        command = client_socket.recv(1024).decode()
        if command.startswith('UPLOAD'):
            filename = command.split(" == ")[1]
            filesize = int(command.split(" == ")[2])
            with open(os.path.join(FILE_DIR, filename), 'wb') as f:
                bytes_received = 0
                while bytes_received < filesize:
                    data = client_socket.recv(1024)
                    f.write(data)
                    bytes_received += len(data)
            client_socket.send(b'UPLOAD SUCCESS')
        elif command.startswith('SEARCH'):
            query = command.split()[1]
            file_type = command.split()[2]
            results = [f for f in os.listdir(FILE_DIR) if f.startswith(query) and f.endswith(file_type)]
            if results:
                client_socket.send(f'FOUND {len(results)}'.encode())
                for result in results:
                    client_socket.send(result.encode())
                    client_socket.recv(1024)  # Wait for ACK
            else:
                client_socket.send(b'NOT FOUND')
        elif command.startswith('DOWNLOAD'):
            filename = command.split()[1]
            filepath = os.path.join(FILE_DIR, filename)
            if os.path.isfile(filepath):
                client_socket.send(f'EXISTS {os.path.getsize(filepath)}'.encode())
                with open(filepath, 'rb') as f:
                    data = f.read(1024)
                    while data:
                        client_socket.send(data)
                        data = f.read(1024)
            else:
                client_socket.send(b'ERROR File not found')
        elif command == 'EXIT':
            client_socket.close()
            break

def main():
    if not os.path.exists(FILE_DIR):
        os.makedirs(FILE_DIR)

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('0.0.0.0', 9999))
    server_socket.listen(5)
    print("Server is listening...")

    while True:
        client_socket, addr = server_socket.accept()
        print(f"Got a connection from {addr}")
        client_handler = threading.Thread(target=handle_client, args=(client_socket,))
        client_handler.start()

if __name__ == '__main__':
    main()
