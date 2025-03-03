import os
import mimetypes
import tempfile
from PIL import Image
from moviepy import VideoFileClip
from pydub import AudioSegment
from pydub.playback import play
from docx import Document
from openpyxl import load_workbook
import PyPDF2
import win32com.client

import subprocess
import platform


def ensure_output_folder(output_folder):
    """Ensure the output folder exists."""
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)



def convert_doc_to_docx(doc_path):
    """Convert .doc file to .docx using pywin32."""
    word = win32com.client.Dispatch("Word.Application")
    doc = word.Documents.Open(doc_path)
    docx_path = doc_path + "x"  # Convert .doc to .docx
    doc.SaveAs(docx_path, FileFormat=16)  # 16 corresponds to .docx format
    doc.Close()
    word.Quit()
    return docx_path

def generate_doc_preview(file_path, output_folder):
    """Generate a preview for a Word .doc file."""
    preview_file = os.path.join(output_folder, "doc_preview.txt")

    try:
        # Convert .doc to .docx
        converted_path = convert_doc_to_docx(file_path)
        
        # Process the .docx using python-docx
        doc = Document(converted_path)
        with open(preview_file, 'w') as preview:
            for i, paragraph in enumerate(doc.paragraphs[:10]):  # Preview first 10 paragraphs
                preview.write(paragraph.text + '\n')
                if i >= 9:  # Limit preview to 10 paragraphs
                    break
        print(f"Word document preview (.doc) saved at: {preview_file}")
    except Exception as e:
        print(f"An error occurred while processing .doc file: {e}")

    return preview_file

def generate_text_preview(file_path, output_folder):
    """Generate a text preview and save it."""
    preview_file = os.path.join(output_folder, "text_preview.txt")
    with open(file_path, 'r') as file, open(preview_file, 'w') as preview:
        preview.write(''.join(file.readlines()[:10]))
    print(f"Text preview saved at: {preview_file}")
    return preview_file

def generate_docx_preview(file_path, output_folder):
    """Generate a preview for a Word document."""
    preview_file = os.path.join(output_folder, "docx_preview.txt")
    doc = Document(file_path)
    with open(preview_file, 'w') as preview:
        for i, paragraph in enumerate(doc.paragraphs[:10]):  # Preview first 10 paragraphs
            preview.write(paragraph.text + '\n')
            if i >= 9:  # Limit preview to 10 paragraphs
                break
    print(f"Word document preview saved at: {preview_file}")
    return preview_file


def generate_xlsx_preview(file_path, output_folder):
    """Generate a preview for an Excel file."""
    preview_file = os.path.join(output_folder, "xlsx_preview.txt")
    workbook = load_workbook(file_path)
    sheet = workbook.active
    with open(preview_file, 'w') as preview:
        for row in sheet.iter_rows(max_row=10, values_only=True):  # Preview first 10 rows
            preview.write('\t'.join([str(cell) if cell is not None else '' for cell in row]) + '\n')
    print(f"Excel file preview saved at: {preview_file}")
    return preview_file


def generate_code_preview(file_path, output_folder):
    """Generate a preview for code files (e.g., Python, C#) and save it."""
    preview_file = os.path.join(output_folder, "code_preview.txt")
    try:
        # Open the code file for reading and the preview file for writing
        with open(file_path, 'r', encoding="utf-8") as file, open(preview_file, 'w', encoding="utf-8") as preview:
            for i, line in enumerate(file):
                if i < 100:  # Only process the first 100 lines
                    preview.write(line)
                else:
                    break
        print(f"Code preview (first 100 lines) saved at: {preview_file}")
        return preview_file
    except Exception as e:
        print(f"An error occurred while generating the code preview: {e}")
        return None



def generate_pdf_preview(file_path, output_folder):
    """Generate a preview for a PDF file and save it."""
    preview_file = os.path.join(output_folder, "pdf_preview.txt")
    with open(file_path, 'rb') as pdf_file, open(preview_file, 'w') as preview:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        if pdf_reader.pages:
            preview.write(pdf_reader.pages[0].extract_text() or "No text found on the first page.")
        else:
            preview.write("No pages found in the PDF.")
    print(f"PDF preview saved at: {preview_file}")
    return preview_file


def generate_image_preview(file_path, output_folder):
    """Generate a thumbnail for an image and save it."""
    preview_file = os.path.join(output_folder, "image_preview.jpg")
    try:
        # Ensure the output folder exists
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        # Open the image
        with Image.open(file_path) as img:
            # Convert RGBA to RGB (remove the alpha channel)
            if img.mode == "RGBA":
                img = img.convert("RGB")

            # Create a thumbnail (resize while maintaining aspect ratio)
            img.thumbnail((400, 400))
            
            # Save the image as a JPEG
            img.save(preview_file, "JPEG")
        print(f"Image preview saved at: {preview_file}")
        return preview_file
    except Exception as e:
        print(f"An error occurred while generating the image preview: {e}")
        return None

def generate_audio_preview(file_path, output_folder):
    """Generate an audio preview (short clip) and save it."""
    preview_file = os.path.join(output_folder, "audio_preview.mp3")

    try:
        # Ensure the output folder exists
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        # Load the audio file and create a short preview
        audio = AudioSegment.from_file(file_path)
        preview_clip = audio[5000:40000]  # Extract the first 10 seconds

        # Export the preview to the output folder
        preview_clip.export(preview_file, format="mp3")
        print(f"Audio preview successfully saved at: {preview_file}")

        return preview_file
    except Exception as e:
        print(f"An error occurred while generating the audio preview: {e}")
        return None



def generate_video_preview(file_path, output_folder):
    """Generate a smaller video preview (short clip with reduced resolution) and save it."""
    preview_file = os.path.join(output_folder, "video_preview.mp4")

    try:
        with VideoFileClip(file_path) as video:
            # Define the start and end times for the preview
            end = min(16, video.duration)
            preview_clip = video.subclipped(5, end)  # Extract clip from 5 seconds to 'end'

            # Resize the video to reduce resolution (e.g., 480p or smaller)
            preview_clip_resized = preview_clip.resized(height=144) # Resize to 360px in height
            # Optionally, you can use .resize(width=854) to resize by width, or both.

            # Write the smaller video file with reduced bitrate to save space
            preview_clip_resized.write_videofile(
                preview_file,
                codec="libx264",
                audio_codec="aac",
                bitrate="500k"  # Set bitrate to lower the file size
            )

        print(f"Smaller video preview saved at: {preview_file}")
        return preview_file

    except Exception as e:
        print(f"An error occurred while generating the video preview: {e}")
        return None


def process_file(file_path):
    """Process the file and generate a preview based on its type."""
    mime_type, _ = mimetypes.guess_type(file_path)
    output_folder = "previews"
    ensure_output_folder(output_folder)

    try:
        if mime_type and mime_type.startswith('text'):
            preview = generate_text_preview(file_path, output_folder)
        elif mime_type and (file_path.endswith('.py') or file_path.endswith('.cs')):
            preview = generate_code_preview(file_path, output_folder)
        elif mime_type == 'application/pdf':
            preview = generate_pdf_preview(file_path, output_folder)
        elif mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            preview = generate_docx_preview(file_path, output_folder)
        elif mime_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
            preview = generate_xlsx_preview(file_path, output_folder)
        elif mime_type and mime_type.startswith('image'):
            preview = generate_image_preview(file_path, output_folder)
        elif mime_type and mime_type.startswith('audio'):
            preview = generate_audio_preview(file_path, output_folder)
        elif mime_type and mime_type.startswith('video'):
            preview = generate_video_preview(file_path, output_folder)
        else:
            print(f"Unsupported file type or file not found for: {file_path}")
            return

        # Display the preview
        if preview.endswith(".txt"):
            with open(preview, 'r') as file:
                print(file.read())
        elif mime_type and mime_type.startswith('image'):
            with Image.open(preview) as img:
                img.show()
        # elif mime_type and mime_type.startswith('audio'):
        #     try:
        #         # Load the audio preview file
        #         audio = AudioSegment.from_file(preview)
        #         print("Playing audio preview...")
        #         play(audio)
        #     except Exception as e:
        #         print(f"An error occurred while playing the audio preview: {e}")
        elif mime_type and mime_type.startswith('audio'):
            try:
            # Check if the audio preview was created
                if preview:
                    print(f"Playing audio preview: {preview}")
                    # Use the system's default media player to play the audio
                    if platform.system() == "Windows":
                        os.startfile(preview)  # Open with the default player on Windows
                    elif platform.system() == "Darwin":  # macOS
                        subprocess.run(["open", preview])
                    else:  # Linux/Unix
                        subprocess.run(["xdg-open", preview])
                else:
                    print("Audio preview could not be created.")
            except Exception as e:
                print(f"An error occurred while playing the audio preview: {e}")


        elif mime_type and mime_type.startswith('video'):
            if preview:  # Ensure the preview was created successfully
                print(f"Playing video preview: {preview}")
                # Use system's default media player to play the preview
                if platform.system() == "Windows":
                    os.startfile(preview)  # Open with the default player on Windows
                elif platform.system() == "Darwin":  # macOS
                    subprocess.run(["open", preview])
                else:  # Linux/Unix
                    subprocess.run(["xdg-open", preview])
            else:
                print("Video preview could not be created.")
        # elif mime_type and mime_type.startswith('video'):
        #     with VideoFileClip(preview) as video:
        #         print(f"Video preview ready at: {preview}")
        #         video.preview()

    except Exception as e:
        print(f"An error occurred while processing {file_path}: {e}")


# Example usage
file_name = input("Enter the full path of the file to preview: ").strip()
process_file(file_name)
