import tkinter as tk
from tkinter import filedialog, messagebox
import os

# Directory to save uploaded files
UPLOAD_DIRECTORY = "uploaded_files"
if not os.path.exists(UPLOAD_DIRECTORY):
    os.makedirs(UPLOAD_DIRECTORY)

def search_files(name_query, type_query, result_listbox, listbox_frame):
    """Search for files in the upload directory by name and/or type."""
    results = []
    result_listbox.delete(0, tk.END)  # Clear previous results
    try:
        for f in os.listdir(UPLOAD_DIRECTORY):
            if (name_query.lower() in f.lower() or not name_query) and \
               (f.lower().endswith(type_query.lower()) or not type_query):
                results.append(f)

        if results:
            for file in results:
                result_listbox.insert(tk.END, file)
            listbox_frame.pack(pady=10)  # Show the listbox if there are results
        else:
            listbox_frame.pack_forget()  # Hide the listbox if no results found
            messagebox.showwarning("No Results", "No files match your search.")
    except Exception as e:
        listbox_frame.pack_forget()  # Hide the listbox on error
        messagebox.showerror("Error", f"An error occurred while searching: {e}")

# GUI setup
def create_app():
    """Create the Tkinter application."""
    root = tk.Tk()
    root.title("File Management System")
    root.geometry("800x600")
    root.configure(bg="white")

    # Title label
    title_label = tk.Label(root, text="File Management System", font=("Arial", 20, "bold"), bg="white", fg="black")
    title_label.pack(pady=20)

    # Search bars
    name_label = tk.Label(root, text="Insert File Name:", font=("Arial", 14), bg="white", fg="black")
    name_label.pack(pady=5)
    name_entry = tk.Entry(root, font=("Arial", 14), width=40)
    name_entry.pack(pady=5)

    type_label = tk.Label(root, text="Insert File Type (e.g., .txt):", font=("Arial", 14), bg="white", fg="black")
    type_label.pack(pady=5)
    type_entry = tk.Entry(root, font=("Arial", 14), width=40)
    type_entry.pack(pady=5)

    # Search results frame (hidden initially)
    listbox_frame = tk.Frame(root, bg="white")
    result_listbox = tk.Listbox(listbox_frame, font=("Arial", 12), width=60, height=10)

    # Search button
    search_button = tk.Button(
        root, text="Search Files",
        command=lambda: search_files(name_entry.get(), type_entry.get(), result_listbox, listbox_frame),
        font=("Arial", 14), bg="#2ca02c", fg="white", activebackground="#217821", activeforeground="white"
    )
    search_button.pack(pady=10)

    # Initially, don't show the listbox
    result_listbox.pack()
    listbox_frame.pack_forget()

    root.mainloop()

if __name__ == "__main__":
    create_app()
