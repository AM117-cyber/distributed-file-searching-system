import socket
import os

def upload_file(client_socket, filename):
    if os.path.isfile(filename):
        filesize = os.path.getsize(filename)
        client_socket.send(f'UPLOAD == {filename} == {filesize}'.encode())
        confirm = client_socket.recv(1048576).decode()
        print(confirm)
        if confirm.startswith('Valid'):
            with open(filename, 'rb') as f:
                data = f.read(1048576)
                while data:
                    client_socket.send(data)
                    data = f.read(1048576)
        
            response = client_socket.recv(1048576).decode()
            print(response)
    else:
        print("File not found")

def search_file(client_socket, file_name, file_type):
    client_socket.send(f'SEARCH == {file_name} == {file_type}'.encode())
    response = client_socket.recv(1048576).decode()
    if response.startswith('FOUND'):
        num_files = int(response.split()[1])
        for _ in range(num_files):
            filename = client_socket.recv(1048576).decode()
            print(f"Found: {filename}")
            client_socket.send(b'ACK')
    else:
        print("No files found")

def download_file(client_socket, filename):
    client_socket.send(f'DOWNLOAD == {filename}'.encode())
    response = client_socket.recv(1048576).decode()
    if response.startswith('FileSize'):
        filesize = int(response.split()[1])
        with open('downloaded_' + filename, 'wb') as f:
            bytes_received = 0
            while bytes_received < filesize:
                data = client_socket.recv(1048576)
                f.write(data)
                bytes_received += len(data)
        print("Download complete.")
    else:
        print("File not found on server.")

def main():
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(('localhost', 9999))

    while True: 
        command = input("Enter command (UPLOAD, SEARCH, DOWNLOAD, EXIT): ")
        if command.startswith('UPLOAD'):
            filename = input("Enter  file name: ")
            
            upload_file(client_socket, filename)
        elif command.startswith('SEARCH'):
            filename = input("Enter file name: ")
            file_type = input("Enter file type: ")
            search_file(client_socket, filename, file_type)
        elif command.startswith('DOWNLOAD'):
            filename = input("Enter command file name: ")
            download_file(client_socket, filename)
        elif command == 'EXIT':
            client_socket.send(b'EXIT')
            client_socket.close()
            break

if __name__ == '__main__':
    main()
