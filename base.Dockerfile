FROM python:3.11-alpine

# Directorio de trabajo
WORKDIR /app

RUN apk update && apk add --no-cache ffmpeg

RUN pip install pillow moviepy pydub python-docx openpyxl PyPDF2