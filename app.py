from flask import Flask, request, render_template, send_file
import requests
import os
import sqlite3
from datetime import datetime
import csv
from io import BytesIO, StringIO

app = Flask(__name__)

# Azure endpoints and keys
CUSTOM_VISION_URL = "https://realestateh-prediction.cognitiveservices.azure.com/customvision/v3.0/Prediction/b08e48db-14b3-4e49-9347-8b88ffebb37a/classify/iterations/realestate_classifier/image"
CUSTOM_VISION_KEY = "8zJvwXgeVIfaJuBdWvxZZZnXysgEDuvWeqbg9mKpKabTOsZ6xVqDJQQJ99BFACYeBjFXJ3w3AAAIACOGVWwr"
COMPUTER_VISION_URL = "https://imgqualityvision.cognitiveservices.azure.com/vision/v3.2/analyze?visualFeatures=ImageType"
COMPUTER_VISION_KEY = "1aXrg8d6sp5Zt0lbfDgiZEiLxlW9ofqsSmhxQrP7JBMekWRD6vjtJQQJ99BFACYeBjFXJ3w3AAAFACOGU39q"

UPLOAD_FOLDER = "static/uploads"
DB_PATH = "predictions.db"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/", methods=["GET", "POST"])
def index():
    prediction_result = {"tag_name": "N/A", "confidence": "N/A"}
    quality_result = {"format": "N/A", "width": "N/A", "height": "N/A"}
    feedback_message = ""
    image_path = None

    if request.method == "POST":
        image_file = request.files.get("image")
        if image_file:
            filename = image_file.filename
            image_path = os.path.join(UPLOAD_FOLDER, filename)
            image_file.save(image_path)

            with open(image_path, "rb") as img:
                image_data = img.read()

                # Call Azure Custom Vision
                try:
                    headers = {
                        "Prediction-Key": CUSTOM_VISION_KEY,
                        "Content-Type": "application/octet-stream"
                    }
                    prediction_response = requests.post(CUSTOM_VISION_URL, headers=headers, data=image_data)
                    prediction_data = prediction_response.json()
                    predictions = prediction_data.get("predictions", [])
                    if predictions:
                        top_prediction = max(predictions, key=lambda x: x.get("probability", 0))
                        tag = top_prediction.get("tagName", "N/A")
                        confidence = f'{top_prediction.get("probability", 0.0):.2%}'
                        prediction_result = {"tag_name": tag, "confidence": confidence}

                        if tag.lower() == "lowquality":
                            feedback_message = "❗ Low quality image detected. Please upload a clearer image."
                        elif tag.lower() == "aesthetic":
                            feedback_message = "✅ Image accepted! It is aesthetic and meets the criteria."
                        elif tag.lower() == "non-aesthetic":
                            feedback_message = "⚠️ Non-aesthetic features detected. Consider re-uploading a more appealing photo."
                        else:
                            feedback_message = "ℹ️ Image analyzed but tag unrecognized. Try another."
                    else:
                        feedback_message = "⚠️ No prediction returned. Try a different image."
                except Exception:
                    feedback_message = "Error during prediction. Try again later."

                # Call Azure Computer Vision
                try:
                    headers = {
                        "Ocp-Apim-Subscription-Key": COMPUTER_VISION_KEY,
                        "Content-Type": "application/octet-stream"
                    }
                    quality_response = requests.post(COMPUTER_VISION_URL, headers=headers, data=image_data)
                    quality_data = quality_response.json()
                    metadata = quality_data.get("metadata", {})
                    quality_result = {
                        "format": metadata.get("format", "N/A"),
                        "width": metadata.get("width", "N/A"),
                        "height": metadata.get("height", "N/A")
                    }
                except Exception:
                    pass  # Leave defaults

                # Save to DB
                log_prediction_to_db(
                    filename,
                    prediction_result["tag_name"],
                    prediction_result["confidence"],
                    quality_result["format"],
                    quality_result["width"],
                    quality_result["height"]
                )

    return render_template("index.html",
                           prediction_result=prediction_result,
                           quality_result=quality_result,
                           feedback_message=feedback_message,
                           image_path=os.path.basename(image_path) if image_path else None)

def log_prediction_to_db(filename, tag, confidence, format_, width, height):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO prediction_logs (filename, tag, confidence, format, width, height, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (filename, tag, confidence, format_, width, height, datetime.now()))
    conn.commit()
    conn.close()

@app.route("/history")
def history():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM prediction_logs ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return render_template("history.html", rows=rows)

from io import BytesIO

@app.route("/download")
def download():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM prediction_logs ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()

    si = StringIO()
    csv_writer = csv.writer(si)
    csv_writer.writerow(["ID", "Filename", "Tag", "Confidence", "Format", "Width", "Height", "Timestamp"])
    csv_writer.writerows(rows)

    mem = BytesIO()
    mem.write(si.getvalue().encode("utf-8"))
    mem.seek(0)

    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name="prediction_history.csv"
    )

if __name__ == "__main__":
    app.run(debug=True)
