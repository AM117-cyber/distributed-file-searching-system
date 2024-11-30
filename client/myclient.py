import socket
import os

# Ruta base para los archivos del cliente
FILEPATH = "/app/client_files/"

def upload_file(client_socket, filename):
    # Verifica si el archivo existe en la ruta especificada
    filepath = os.path.join(FILEPATH, filename)
    if os.path.isfile(filepath):
        filesize = os.path.getsize(filepath)
        client_socket.send(f'UPLOAD == {filename} == {filesize}'.encode())
        with open(filepath, 'rb') as f:
            data = f.read(1024)
            while data:
                client_socket.send(data)
                data = f.read(1024)
        response = client_socket.recv(1024).decode()
        print(response)
    else:
        print(f"File not found: {filepath}")

def search_file(client_socket, query, file_type):
    client_socket.send(f'SEARCH {query} {file_type}'.encode())
    response = client_socket.recv(1024).decode()
    if response.startswith('FOUND'):
        num_files = int(response.split()[1])
        for _ in range(num_files):
            filename = client_socket.recv(1024).decode()
            print(f"Found: {filename}")
            client_socket.send(b'ACK')
    else:
        print("No files found")

def download_file(client_socket, filename):
    client_socket.send(f'DOWNLOAD {filename}'.encode())
    response = client_socket.recv(1024).decode()
    if response.startswith('EXISTS'):
        filesize = int(response.split()[1])
        download_path = os.path.join(FILEPATH, 'downloaded_' + filename)
        with open(download_path, 'wb') as f:
            bytes_received = 0
            while bytes_received < filesize:
                data = client_socket.recv(1024)
                f.write(data)
                bytes_received += len(data)
        print(f"Download complete: {download_path}")
    else:
        print("File not found on server.")

def main():
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client_socket.connect(('10.0.11.10', 9999))  # Conecta al servidor en la red configurada
        print("Connected to server")
    except socket.error as e:
        print(f"Error connecting to server: {e}")
        return

    while True:
        command = input("Enter command (UPLOAD, SEARCH, DOWNLOAD, EXIT): ")
        if command.startswith('UPLOAD'):
            filename = input("Enter the name of the file to upload: ")
            upload_file(client_socket, filename)
        elif command.startswith('SEARCH'):
            query = input("Enter the search query: ")
            file_type = input("Enter the file type (e.g., .txt, .pdf): ")
            search_file(client_socket, query, file_type)
        elif command.startswith('DOWNLOAD'):
            filename = input("Enter the name of the file to download: ")
            download_file(client_socket, filename)
        elif command == 'EXIT':
            client_socket.send(b'EXIT')
            client_socket.close()
            print("Disconnected from server")
            break
        else:
            print("Invalid command. Please try again.")

if __name__ == '__main__':
    main()