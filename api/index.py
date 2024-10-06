import os
import numpy as np
from pydub import AudioSegment
import cv2
import requests
from PIL import Image
from io import BytesIO
from flask import Flask, request, jsonify

# Definir la carpeta de sonidos del piano
AUDIO_FOLDER = "piano"  # Asegúrate de que contenga archivos como 25.mp3, 26.mp3, etc.
DEFAULT_OUTPUT_FILENAME = "audio_coordenadas_estelares.mp3"

# Indicador para cancelar el procesamiento
cancel_processing = False

# Función para mapear un valor de un rango a otro
def map_to_scale(value, old_min, old_max, new_min, new_max):
    if old_max == old_min:
        return (new_min + new_max) / 2  # Valor por defecto en el medio del nuevo rango
    return new_min + (value - old_min) * (new_max - new_min) / (old_max - old_min)

# Función para descargar la imagen desde la URL
def download_image_from_url(url):
    try:
        response = requests.get(url)
        image = Image.open(BytesIO(response.content))
        return image
    except requests.exceptions.RequestException as e:
        print(f"Error al descargar la imagen: {e}")
        return None

# Función para detectar estrellas en la imagen
def find_stars(image):
    min_area = 3  # Umbral mínimo de área para retener una estrella

    image_array = np.array(image.convert('RGB'))
    gray_image = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)

    _, thresholded = cv2.threshold(gray_image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(thresholded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    star_coords_filtered = []
    for contour in contours:
        if cv2.contourArea(contour) >= min_area:
            M = cv2.moments(contour)
            if M['m00'] != 0:
                cX = int(M['m10'] / M['m00'])
                cY = int(M['m01'] / M['m00'])
                star_coords_filtered.append((cY, cX))
                cv2.circle(image_array, (cX, cY), radius=2, color=(255, 0, 0), thickness=-1)

    return [{'x': int(x), 'y': int(y)} for y, x in star_coords_filtered], image_array

# Función para generar el archivo de audio basado en las coordenadas
def create_audio_from_coordinates(coords, image_width, output_filename, max_stars, interval_between_starts):
    global cancel_processing
    if not coords:
        print("No se encontraron coordenadas.")
        return

    coords.sort(key=lambda coord: coord['x'])

    if max_stars is not None and len(coords) > max_stars:
        coords = coords[:max_stars]

    y_values = [coord['y'] for coord in coords]
    original_min_y = min(y_values)
    original_max_y = max(y_values)

    total_duration = (len(coords) - 1) * interval_between_starts + 1000  # Extra 1000ms para seguridad
    min_audio_duration = 10000  # 10 segundos en milisegundos

    if total_duration < min_audio_duration:
        total_duration = min_audio_duration

    base_audio = AudioSegment.silent(duration=total_duration)

    current_time = 0
    for coord in coords:
        if cancel_processing:
            print("Procesamiento de audio cancelado.")
            return

        x = coord['x']
        y = coord['y']

        try:
            y_mapped = map_to_scale(y, original_min_y, original_max_y, 25, 75)  # Mapeamos la coordenada Y
            file_name = os.path.join(AUDIO_FOLDER, f"{int(y_mapped)}.mp3")  # Asignar archivo de piano

            sound = AudioSegment.from_mp3(file_name)
            sound_duration = len(sound)  # Duración del archivo de sonido
            end_time = current_time + sound_duration

            if end_time > len(base_audio):
                extra_duration = end_time - len(base_audio)
                base_audio = base_audio + AudioSegment.silent(duration=extra_duration)

            print(f"Superponiendo {file_name} en la posición {current_time / 1000} segundos.")
            base_audio = base_audio.overlay(sound, position=int(current_time))
            current_time += interval_between_starts  # Mover current_time al inicio de la siguiente nota

        except FileNotFoundError:
            print(f"Archivo {file_name} no encontrado.")

    if base_audio.duration_seconds > 0:
        base_audio.export(output_filename, format="mp3")
        print(f"Audio guardado como: {output_filename}")
    else:
        print("No se generó audio.")

# Función para procesar la imagen y generar el audio
def process_image(url, max_stars=None, interval_between_starts=350):
    print(f"Procesando la imagen desde la URL: {url}")

    image = download_image_from_url(url)
    if not image:
        return None, "Error al descargar la imagen."

    image_width = image.width

    coords, _ = find_stars(image)

    if not coords:
        return None, "No se detectaron estrellas."

    global cancel_processing
    cancel_processing = False
    create_audio_from_coordinates(coords, image_width, DEFAULT_OUTPUT_FILENAME, max_stars, interval_between_starts)
    
    return DEFAULT_OUTPUT_FILENAME, None

# Crear una aplicación Flask
app = Flask(__name__)

# Endpoint para procesar la imagen
@app.route('/procesar_imagen', methods=['POST'])
def procesar_imagen():
    data = request.json
    url = data.get('url')
    star_limit = data.get('star_limit', None)  # Opcional
    interval_between_starts = data.get('interval_between_starts', 350)  # Opcional, valor por defecto 350

    if not url:
        return jsonify({"error": "URL no proporcionada"}), 400

    output_filename, error = process_image(url, star_limit, interval_between_starts)

    if error:
        return jsonify({"error": error}), 400

    return jsonify({"message": "Procesamiento completado", "audio_file": output_filename}), 200

if __name__ == '__main__':
    app.run(debug=True)
