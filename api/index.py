import os
import numpy as np
from pydub import AudioSegment
import cv2
import requests
from PIL import Image
from io import BytesIO
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from datetime import datetime
import zipfile

# Create Flask app and configure CORS
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, methods=["GET","POST"], 
     allow_headers=["Authorization","Content-Type"], supports_credentials=True)

# Define constants
AUDIO_FOLDER = "piano"
OUTPUT_FOLDER = "output"

# Create the output folder if it doesn't exist
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Define all your functions here
def generate_unique_filename(base_filename):
    filename, extension = os.path.splitext(base_filename)
    counter = 1
    new_filename = f"{filename}{extension}"
    
    while os.path.exists(os.path.join(OUTPUT_FOLDER, new_filename)):
        new_filename = f"{filename}_{counter}{extension}"
        counter += 1
    
    return new_filename

def map_to_scale(value, old_min, old_max, new_min, new_max):
    if old_max == old_min:
        return (new_min + new_max) / 2
    return new_min + (value - old_min) * (new_max - new_min) / (old_max - old_min)

def download_image_from_url(url):
    try:
        response = requests.get(url)
        image = Image.open(BytesIO(response.content))
        return image
    except requests.exceptions.RequestException as e:
        print(f"Error al descargar la imagen: {e}")
        return None

def find_stars(image):
    min_area = 3
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

def create_audio_from_coordinates(coords, image_width, base_filename, max_stars, interval_between_starts):
    if not coords:
        print("No se encontraron coordenadas.")
        return None

    output_filename = generate_unique_filename(base_filename)
    output_path = os.path.join(OUTPUT_FOLDER, output_filename)

    coords.sort(key=lambda coord: coord['x'])
    if max_stars is not None and len(coords) > max_stars:
        coords = coords[:max_stars]

    y_values = [coord['y'] for coord in coords]
    original_min_y = min(y_values)
    original_max_y = max(y_values)

    total_duration = max((len(coords) - 1) * interval_between_starts + 1000, 10000)
    base_audio = AudioSegment.silent(duration=total_duration)

    current_time = 0
    for coord in coords:
        try:
            y_mapped = map_to_scale(coord['y'], original_min_y, original_max_y, 25, 75)
            piano_file = os.path.join(AUDIO_FOLDER, f"{int(y_mapped)}.mp3")

            sound = AudioSegment.from_mp3(piano_file)
            sound_duration = len(sound)
            end_time = current_time + sound_duration

            if end_time > len(base_audio):
                extra_duration = end_time - len(base_audio)
                base_audio = base_audio + AudioSegment.silent(duration=extra_duration)

            base_audio = base_audio.overlay(sound, position=int(current_time))
            current_time += interval_between_starts

        except FileNotFoundError:
            print(f"Archivo {piano_file} no encontrado.")

    if base_audio.duration_seconds > 0:
        base_audio.export(output_path, format="mp3")
        return output_filename
    return None

# Define process_image function
def process_image(url, star_limit, interval):
    image = download_image_from_url(url)
    if image is None:
        return None, "Error al descargar la imagen"

    coords, processed_image = find_stars(image)
    if not coords:
        return None, "No se encontraron estrellas en la imagen"

    # Save processed image
    image_filename = generate_unique_filename("processed_image.png")
    image_path = os.path.join(OUTPUT_FOLDER, image_filename)
    Image.fromarray(processed_image).save(image_path)

    # Create audio
    audio_filename = create_audio_from_coordinates(coords, image.width, "star_sound.mp3", star_limit, interval)
    if not audio_filename:
        return None, "Error al generar el audio"

    return {"audio": audio_filename, "image": image_filename}, None

# Define route handlers
@app.route('/procesar_imagen', methods=['POST', 'OPTIONS'])
def procesar_imagen_endpoint():
    if request.method == 'OPTIONS':
        return '', 200

    data = request.json
    url = data.get('url')
    star_limit = data.get('star_limit', None)
    interval = data.get('interval', 350)

    if not url:
        return jsonify({"error": "URL no proporcionada"}), 400

    output_files, error = process_image(url, star_limit, interval)

    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "message": "Procesamiento completado",
        "audio_file": output_files["audio"],
        "image_file": output_files["image"]
    }), 200

@app.route('/output/download_all', methods=['GET'])
def download_all_files():
    zip_filename = "output_files.zip"
    OUTPUT_FOLDER = "/app/output"
    zip_path = os.path.join(OUTPUT_FOLDER, zip_filename)

    try:
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for root, dirs, files in os.walk(OUTPUT_FOLDER):
                for file in files:
                    if file != zip_filename:
                        zipf.write(os.path.join(root, file), file)

        return send_file(zip_path, as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/output', methods=['GET'])
def list_files():
    try:
        files = os.listdir(OUTPUT_FOLDER)
        return jsonify({"files": files})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return response

if __name__ == '__main__':
    app.run(debug=True)