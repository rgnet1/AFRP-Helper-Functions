"""
Badge Generator Module
Generates print-ready PDF badges from Excel data using SVG templates.
"""

import qrcode
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF
import pandas as pd
import os
import json
import re
from io import BytesIO
from PIL import Image
import base64
import logging
import tempfile
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

class BadgeGenerator:
    """Generate print-ready badges from Excel data using SVG templates."""
    
    # Avery template specifications (width, height, cols, rows, margins in inches)
    AVERY_TEMPLATES = {
        '5392': {
            'name': 'Avery 5392 - Name Badge Insert Refills',
            'width': 4.0,
            'height': 3.0,
            'cols': 2,
            'rows': 3,
            'margin_left': 0.25,
            'margin_top': 1.0,
            'gap_horizontal': 0.0,
            'gap_vertical': 0.0,
            'orientation': 'portrait'
        },
        '5395': {
            'name': 'Avery 5395 - Name Badge Insert Refills',
            'width': 2.625,
            'height': 3.625,
            'cols': 2,
            'rows': 2,
            'margin_left': 0.875,
            'margin_top': 0.6875,
            'gap_horizontal': 0.625,
            'gap_vertical': 0.6875
        },
        '8395': {
            'name': 'Avery 8395 - Name Badge Labels',
            'width': 2.625,
            'height': 3.625,
            'cols': 2,
            'rows': 2,
            'margin_left': 0.875,
            'margin_top': 0.6875,
            'gap_horizontal': 0.625,
            'gap_vertical': 0.6875
        },
        '74459': {
            'name': 'Avery 74459 - Removable Name Badge Labels',
            'width': 2.25,
            'height': 3.5,
            'cols': 3,
            'rows': 2,
            'margin_left': 0.875,
            'margin_top': 0.5,
            'gap_horizontal': 0.125,
            'gap_vertical': 1.0
        }
    }
    
    def __init__(self, excel_file, svg_template_path, column_mappings, 
                 afrp_logo_path, club_logo_path=None, club_logo_width=None, 
                 club_logo_height=None, avery_template='5392'):
        """
        Initialize the badge generator.
        
        Args:
            excel_file: Path to processed Excel file
            svg_template_path: Path to SVG template file
            column_mappings: Dict mapping placeholders to Excel columns
            afrp_logo_path: Path to default AFRP logo
            club_logo_path: Optional path to club-specific logo
            avery_template: Avery template code (default: 5392)
        """
        self.excel_file = excel_file
        self.svg_template_path = svg_template_path
        self.column_mappings = column_mappings
        self.afrp_logo_path = afrp_logo_path
        self.club_logo_path = club_logo_path
        self.club_logo_width = club_logo_width
        self.club_logo_height = club_logo_height
        self.avery_template = avery_template
        
        # Debug logging
        logger.info(f"BadgeGenerator initialized with:")
        logger.info(f"  - AFRP logo: {afrp_logo_path} (exists: {os.path.exists(afrp_logo_path) if afrp_logo_path else False})")
        logger.info(f"  - Club logo: {club_logo_path} (exists: {os.path.exists(club_logo_path) if club_logo_path else False})")
        if club_logo_width and club_logo_height:
            logger.info(f"  - Club logo dimensions: {club_logo_width}x{club_logo_height}")
        logger.info(f"  - SVG template: {svg_template_path}")
        
        # Load Excel data
        logger.info(f"Loading Excel file: {excel_file}")
        self.df = pd.read_excel(excel_file)
        logger.info(f"Loaded {len(self.df)} rows from Excel")
        
        # Validate template exists
        if avery_template not in self.AVERY_TEMPLATES:
            raise ValueError(f"Unknown Avery template: {avery_template}")
        
        self.template_spec = self.AVERY_TEMPLATES[avery_template]
        logger.info(f"Using template: {self.template_spec['name']}")
    
    def generate_qr_code(self, data):
        """
        Generate QR code image from string data.
        
        Args:
            data: String data to encode in QR code
            
        Returns:
            BytesIO object containing PNG image
        """
        if not data or pd.isna(data):
            return None
            
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2
        )
        qr.add_data(str(data))
        qr.make(fit=True)
        
        img = qr.make_image(fill_color='black', back_color='white')
        
        # Convert to bytes
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        return img_bytes
    
    def image_to_base64(self, image_path):
        """
        Convert image file to base64 encoded string.
        
        Args:
            image_path: Path to image file
            
        Returns:
            Base64 encoded string
        """
        if not image_path or not os.path.exists(image_path):
            return None
            
        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()
                return base64.b64encode(image_data).decode('utf-8')
        except Exception as e:
            logger.warning(f"Failed to encode image {image_path}: {e}")
            return None
    
    def adjust_club_logo_dimensions(self, svg_content):
        """
        Dynamically adjust club logo dimensions in SVG based on actual image aspect ratio.
        
        Args:
            svg_content: SVG content as string
            
        Returns:
            Modified SVG content with adjusted club logo dimensions
        """
        if not self.club_logo_width or not self.club_logo_height:
            logger.debug("No club logo dimensions provided, skipping adjustment")
            return svg_content
        
        # Calculate aspect ratio
        aspect_ratio = self.club_logo_width / self.club_logo_height
        logger.info(f"Club logo aspect ratio: {aspect_ratio:.2f}:1")
        
        # Find club logo image tag in SVG using regex
        # Match image tag with CLUB_LOGO regardless of attribute order
        import re
        pattern = r'<image[^>]*href="{{CLUB_LOGO}}"[^>]*/>'
        match = re.search(pattern, svg_content, re.DOTALL)
        
        if not match:
            logger.warning("Could not find CLUB_LOGO image tag in SVG")
            logger.debug(f"SVG contains CLUB_LOGO placeholder: {'{{CLUB_LOGO}}' in svg_content}")
            return svg_content
        
        original_tag = match.group(0)
        logger.info(f"Found club logo tag, adjusting dimensions")
        
        # Extract x and y position from the original tag
        x_match = re.search(r'x="([^"]+)"', original_tag)
        y_match = re.search(r'y="([^"]+)"', original_tag)
        
        if not x_match or not y_match:
            logger.warning("Could not extract x/y from club logo tag")
            return svg_content
        
        x_pos = x_match.group(1)
        y_pos = y_match.group(1)
        
        # Calculate appropriate dimensions
        # Target height of 50px, adjust width based on aspect ratio
        target_height = 50
        target_width = int(target_height * aspect_ratio)
        
        logger.info(f"Adjusting club logo to {target_width}x{target_height} (from {self.club_logo_width}x{self.club_logo_height})")
        
        # Create new image tag with correct dimensions
        new_tag = (
            f'<image x="{x_pos}" y="{y_pos}" '
            f'width="{target_width}" height="{target_height}" '
            f'preserveAspectRatio="xMidYMid meet" '
            f'href="{{{{CLUB_LOGO}}}}"/>'
        )
        
        # Replace in SVG content
        svg_content = svg_content.replace(original_tag, new_tag)
        logger.info("Club logo dimensions adjusted in SVG")
        
        return svg_content
    
    def render_svg_badge(self, row_data, temp_dir):
        """
        Render a single badge by replacing placeholders in SVG template.
        
        Args:
            row_data: Pandas Series containing data for one attendee
            temp_dir: Temporary directory for storing files
            
        Returns:
            Path to rendered SVG file
        """
        logger.debug(f"Rendering SVG for row {row_data.name}")
        logger.debug(f"Row data columns: {list(row_data.index)}")
        
        # Read SVG template
        with open(self.svg_template_path, 'r', encoding='utf-8') as f:
            svg_content = f.read()
        
        # Dynamically adjust club logo dimensions if available
        svg_content = self.adjust_club_logo_dimensions(svg_content)
        
        logger.debug(f"SVG template length: {len(svg_content)} characters")
        replacements_made = 0
        
        # Replace text placeholders
        for placeholder, column_name in self.column_mappings.items():
            if placeholder == '{{QR_CODE}}':
                continue  # Handle QR code separately
                
            if isinstance(column_name, list):
                # Handle sub-events (multiple columns)
                sub_events = []
                for col in column_name:
                    if col in row_data.index and pd.notna(row_data[col]):
                        # Extract event name from column like "Event ~ Sub-event"
                        event_name = col.split(' ~ ')[-1] if ' ~ ' in col else col
                        sub_events.append(event_name)
                value = '\n'.join(sub_events) if sub_events else ''
            else:
                # Single column mapping
                if column_name in row_data.index:
                    value = str(row_data[column_name]) if pd.notna(row_data[column_name]) else ''
                else:
                    value = ''
                    logger.warning(f"Column '{column_name}' not found in data for row {row_data.name}")
            
            # Replace placeholder in SVG
            if placeholder in svg_content:
                svg_content = svg_content.replace(placeholder, value)
                replacements_made += 1
                logger.debug(f"Replaced {placeholder} with '{value[:50]}...'")
            else:
                logger.warning(f"Placeholder {placeholder} not found in SVG template")
        
        logger.debug(f"Made {replacements_made} replacements in SVG")
        
        # Handle QR code
        if '{{QR_CODE}}' in svg_content:
            logger.debug("Found QR_CODE placeholder in SVG")
            qr_replaced = False
            if 'QR Code' in row_data.index:
                qr_data = row_data.get('QR Code', '')
                logger.debug(f"QR Code data: {qr_data}")
                if qr_data and not pd.isna(qr_data):
                    qr_img_bytes = self.generate_qr_code(qr_data)
                    if qr_img_bytes:
                        qr_base64 = base64.b64encode(qr_img_bytes.getvalue()).decode()
                        logger.debug(f"Generated QR code, base64 length: {len(qr_base64)}")
                        svg_content = svg_content.replace(
                            '{{QR_CODE}}',
                            f'data:image/png;base64,{qr_base64}'
                        )
                        qr_replaced = True
                    else:
                        logger.warning("Failed to generate QR code image")
                else:
                    logger.warning(f"QR Code data is empty or NA for row {row_data.name}")
            else:
                logger.warning("QR Code column not found in row data")
            
            # If QR code wasn't replaced (empty data or error), remove the placeholder
            if not qr_replaced:
                svg_content = svg_content.replace('{{QR_CODE}}', '')
                logger.debug("Removed empty QR_CODE placeholder")
        
        # Handle AFRP logo
        if '{{AFRP_LOGO}}' in svg_content:
            logger.debug(f"Found AFRP_LOGO placeholder, path: {self.afrp_logo_path}")
            afrp_base64 = self.image_to_base64(self.afrp_logo_path)
            if afrp_base64:
                logger.debug(f"AFRP logo encoded, base64 length: {len(afrp_base64)}")
                # Detect file type from extension
                ext = os.path.splitext(self.afrp_logo_path)[1].lower()
                mime_type = 'image/svg+xml' if ext == '.svg' else 'image/png'
                svg_content = svg_content.replace(
                    '{{AFRP_LOGO}}',
                    f'data:{mime_type};base64,{afrp_base64}'
                )
            else:
                logger.warning("Failed to encode AFRP logo, removing placeholder")
                svg_content = svg_content.replace('{{AFRP_LOGO}}', '')
        
        # Handle club logo
        if '{{CLUB_LOGO}}' in svg_content:
            logger.info(f"Found {{{{CLUB_LOGO}}}} placeholder in SVG")
            if self.club_logo_path:
                logger.info(f"Club logo path provided: {self.club_logo_path}")
                logger.info(f"Club logo exists: {os.path.exists(self.club_logo_path)}")
                club_base64 = self.image_to_base64(self.club_logo_path)
                if club_base64:
                    logger.info(f"Club logo encoded successfully, length: {len(club_base64)}")
                    ext = os.path.splitext(self.club_logo_path)[1].lower()
                    mime_type = 'image/svg+xml' if ext == '.svg' else 'image/png'
                    logger.info(f"Club logo mime type: {mime_type}")
                    svg_content = svg_content.replace(
                        '{{CLUB_LOGO}}',
                        f'data:{mime_type};base64,{club_base64}'
                    )
                    logger.info("Club logo placeholder replaced with base64 data")
                else:
                    logger.warning("Failed to encode club logo, removing placeholder")
                    svg_content = svg_content.replace('{{CLUB_LOGO}}', '')
            else:
                logger.warning("No club logo path provided, removing placeholder")
                svg_content = svg_content.replace('{{CLUB_LOGO}}', '')
        else:
            logger.warning("No {{CLUB_LOGO}} placeholder found in SVG template")
        
        # Final cleanup: Remove any remaining placeholders that weren't handled
        final_cleanup = re.findall(r'\{\{[A-Z_0-9]+\}\}', svg_content)
        if final_cleanup:
            logger.warning(f"Final cleanup removing {len(final_cleanup)} remaining placeholders: {final_cleanup}")
            for remaining in final_cleanup:
                svg_content = svg_content.replace(remaining, '')
        
        # Save rendered SVG to temp file
        temp_svg_path = os.path.join(temp_dir, f'badge_{row_data.name}.svg')
        with open(temp_svg_path, 'w', encoding='utf-8') as f:
            f.write(svg_content)
        
        logger.debug(f"Saved rendered SVG to: {temp_svg_path}")
        logger.debug(f"Final SVG length: {len(svg_content)} characters")
        
        return temp_svg_path
    
    def generate_pdf(self, output_path, progress_callback=None):
        """
        Generate PDF with all badges arranged on Avery template sheets.
        
        Args:
            output_path: Path where PDF should be saved
            progress_callback: Optional callback function(current, total, message)
            
        Returns:
            Path to generated PDF file
        """
        logger.info(f"Generating PDF with {len(self.df)} badges")
        logger.info(f"Excel columns: {list(self.df.columns)}")
        logger.info(f"Column mappings: {self.column_mappings}")
        logger.info(f"SVG template: {self.svg_template_path}")
        logger.info(f"AFRP logo: {self.afrp_logo_path}")
        logger.info(f"Club logo: {self.club_logo_path}")
        logger.info(f"Output path: {output_path}")
        
        # Verify files exist
        if not os.path.exists(self.svg_template_path):
            raise FileNotFoundError(f"SVG template not found: {self.svg_template_path}")
        if not os.path.exists(self.afrp_logo_path):
            logger.warning(f"AFRP logo not found: {self.afrp_logo_path}")
        
        # Create canvas
        c = canvas.Canvas(output_path, pagesize=letter)
        page_width, page_height = letter
        
        # Get template specifications
        spec = self.template_spec
        badge_width = spec['width'] * inch
        badge_height = spec['height'] * inch
        cols = spec['cols']
        rows = spec['rows']
        margin_left = spec['margin_left'] * inch
        margin_top = spec['margin_top'] * inch
        gap_h = spec.get('gap_horizontal', 0) * inch
        gap_v = spec.get('gap_vertical', 0) * inch
        
        badges_per_page = cols * rows
        total_badges = len(self.df)
        
        logger.info(f"Badge dimensions: {badge_width/inch}\" x {badge_height/inch}\"")
        logger.info(f"Layout: {cols} x {rows} = {badges_per_page} per page")
        
        # Create temporary directory for SVG files
        with tempfile.TemporaryDirectory() as temp_dir:
            logger.info(f"Using temporary directory: {temp_dir}")
            
            for index, row in self.df.iterrows():
                # Calculate position on page
                badge_num = index % badges_per_page
                col = badge_num % cols
                row_pos = badge_num // cols
                
                # Calculate x, y position
                x = margin_left + col * (badge_width + gap_h)
                y = page_height - margin_top - (row_pos + 1) * badge_height - (row_pos * gap_v)
                
                try:
                    # Render SVG for this badge
                    logger.debug(f"Rendering badge {index + 1}/{total_badges}")
                    svg_path = self.render_svg_badge(row, temp_dir)
                    logger.debug(f"SVG rendered to: {svg_path}")
                    
                    # Convert SVG to ReportLab drawing
                    drawing = svg2rlg(svg_path)
                    logger.debug(f"SVG converted to drawing: {drawing is not None}")
                    
                    if drawing:
                        logger.debug(f"Original drawing size: {drawing.width} x {drawing.height}")
                        
                        # Scale to fit badge dimensions
                        scale_x = badge_width / drawing.width
                        scale_y = badge_height / drawing.height
                        scale = min(scale_x, scale_y)
                        
                        logger.debug(f"Scale factors: x={scale_x}, y={scale_y}, using={scale}")
                        
                        drawing.width = badge_width
                        drawing.height = badge_height
                        drawing.scale(scale, scale)
                        
                        # Render to PDF
                        logger.debug(f"Drawing to PDF at position ({x/inch:.2f}\", {y/inch:.2f}\")")
                        renderPDF.draw(drawing, c, x, y)
                        
                        logger.debug(f"Successfully rendered badge {index + 1}/{total_badges}")
                    else:
                        logger.warning(f"Failed to convert SVG to drawing for badge {index + 1}")
                        logger.warning(f"SVG file content preview: {open(svg_path).read()[:200]}")
                    
                    # Clean up temp SVG file
                    if os.path.exists(svg_path):
                        os.remove(svg_path)
                    
                except Exception as e:
                    logger.error(f"Error rendering badge {index + 1}: {e}", exc_info=True)
                    # Continue with next badge
                
                # Report progress
                if progress_callback:
                    progress_callback(index + 1, total_badges, f"Generated badge {index + 1} of {total_badges}")
                
                # Start new page if current page is full
                if (index + 1) % badges_per_page == 0 and (index + 1) < total_badges:
                    c.showPage()
                    logger.debug(f"Starting new page after {index + 1} badges")
            
            # Save PDF
            c.save()
            logger.info(f"PDF saved to: {output_path}")
        
        return output_path
    
    @classmethod
    def get_available_templates(cls):
        """
        Get list of available Avery templates.
        
        Returns:
            List of dicts with template information
        """
        return [
            {
                'code': code,
                'name': spec['name'],
                'size': f"{spec['width']}\" x {spec['height']}\"",
                'layout': f"{spec['cols']} x {spec['rows']}"
            }
            for code, spec in cls.AVERY_TEMPLATES.items()
        ]
    
    @staticmethod
    def extract_placeholders_from_svg(svg_path):
        """
        Extract placeholder strings from SVG template.
        
        Args:
            svg_path: Path to SVG template file
            
        Returns:
            List of placeholder strings found in the template
        """
        import re
        
        placeholders = set()
        pattern = r'\{\{([A-Z_]+)\}\}'
        
        try:
            with open(svg_path, 'r', encoding='utf-8') as f:
                content = f.read()
                matches = re.findall(pattern, content)
                placeholders.update([f"{{{{{m}}}}}" for m in matches])
        except Exception as e:
            logger.error(f"Error extracting placeholders from {svg_path}: {e}")
        
        return sorted(list(placeholders))
