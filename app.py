from flask import Flask, render_template, request, send_file, jsonify
import qrcode
from io import BytesIO
from PIL import Image
import numpy as np  # Ensure numpy is installed
from utils.url_generator import extract_event_id, generate_event_registration_url, generate_event_summary_url

app = Flask(__name__)

@app.route('/', methods=['GET'])
def home():
    # This route displays the home page with tiles
    return render_template('home.html')

@app.route('/qr', methods=['GET', 'POST'])
def qr():
    if request.method == 'POST':
        data = request.form.get('data')
        image_file = request.files.get('image')
        shape = request.form.get('shape', 'circle')  # Get the shape selection
        solid_radius_percent = request.form.get('solid_radius', '60')  # Get the radius percentage

        if data:
            # Generate QR code
            qr_code = qrcode.QRCode(
                version=None,  # Adjusts size automatically based on data
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10,
                border=4,
            )
            qr_code.add_data(data)
            qr_code.make(fit=True)
            img_qr = qr_code.make_image(
                fill_color="black", back_color="white"
            ).convert('RGBA')  # Use 'RGBA' mode for transparency

            # Add center image if provided
            if image_file and image_file.filename != '':
                try:
                    # Convert solid_radius_percent to a float between 0 and 1
                    solid_radius = float(solid_radius_percent) / 100.0
                    # Ensure solid_radius is within valid range
                    solid_radius = min(max(solid_radius, 0.01), 1.0)

                    # Open and convert the icon image to RGBA
                    icon = Image.open(image_file).convert("RGBA")

                    # Calculate dimensions for the icon
                    img_w, img_h = img_qr.size
                    factor = 2.5  # Adjust factor to change icon size
                    size_w = int(img_w / factor)
                    size_h = int(img_h / factor)

                    # Resize the icon
                    icon = icon.resize((size_w, size_h), Image.LANCZOS)

                    # Create mask depending on the shape
                    if shape == 'circle':
                        # Circular fade mask with solid center
                        x = np.linspace(-1, 1, size_w)
                        y = np.linspace(-1, 1, size_h)
                        xv, yv = np.meshgrid(x, y)
                        d = np.sqrt(xv**2 + yv**2)
                        mask_array = np.ones_like(d)
                        fade_zone = d >= solid_radius
                        mask_array[fade_zone] = 1 - (d[fade_zone] - solid_radius) / (1 - solid_radius)
                        mask_array = np.clip(mask_array, 0, 1)
                        mask_array = (mask_array * 255).astype('uint8')
                        mask = Image.fromarray(mask_array, mode='L')
                    else:
                        # Rectangle fade mask with solid center
                        x = np.linspace(-1, 1, size_w)
                        y = np.linspace(-1, 1, size_h)
                        xv, yv = np.meshgrid(x, y)
                        dx = np.abs(xv)
                        dy = np.abs(yv)
                        mask_array = np.ones_like(dx)
                        fade_zone_x = dx >= solid_radius
                        mask_array[fade_zone_x] *= 1 - (dx[fade_zone_x] - solid_radius) / (1 - solid_radius)
                        fade_zone_y = dy >= solid_radius
                        mask_array[fade_zone_y] *= 1 - (dy[fade_zone_y] - solid_radius) / (1 - solid_radius)
                        mask_array = np.clip(mask_array, 0, 1)
                        mask_array = (mask_array * 255).astype('uint8')
                        mask = Image.fromarray(mask_array, mode='L')

                    # Apply the mask to the icon
                    icon.putalpha(mask)

                    # Paste the icon onto the QR code
                    pos_w = (img_w - size_w) // 2
                    pos_h = (img_h - size_h) // 2
                    img_qr.paste(icon, (pos_w, pos_h), icon)
                except Exception as e:
                    print(f"Error processing the image: {e}")

            # Save the generated QR code to a bytes buffer
            buf = BytesIO()
            img_qr.save(buf, format='PNG')
            buf.seek(0)
            return send_file(
                buf,
                mimetype='image/png',
                as_attachment=True,
                download_name='qr.png'
            )
    return render_template('qr.html')

@app.route('/event', methods=['GET', 'POST'])
def event():
    if request.method == 'POST':
        crm_url = request.form.get('crmUrl')
        try:
            # Extract event ID and generate URLs
            event_id = extract_event_id(crm_url)
            event_url = generate_event_registration_url(event_id)
            summary_url = generate_event_summary_url(event_id)
            
            return jsonify({
                'event_url': event_url,
                'summary_url': summary_url
            })
            
        except Exception as e:
            return jsonify({'error': str(e)})
    
    return render_template('event.html')

if __name__ == '__main__':
    app.run(debug=True)
