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
import shutil
from io import BytesIO
from PIL import Image
import base64
import logging
import tempfile
import xml.etree.ElementTree as ET
from collections import OrderedDict
import copy
import pickle
from concurrent.futures import ProcessPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# Placeholders like {{FIRST_NAME}} — must match after logo substitution (paths are not matched).
PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_0-9]+\}\}")


def _subtree_has_placeholder(elem: ET.Element) -> bool:
    xml = ET.tostring(elem, encoding="unicode", method="xml")
    return PLACEHOLDER_RE.search(xml) is not None


def _static_prune(elem: ET.Element):
    """Keep only SVG subtrees with no mail-merge placeholders (static layer)."""
    if not _subtree_has_placeholder(elem):
        return copy.deepcopy(elem)
    new_el = ET.Element(elem.tag, dict(elem.attrib))
    if elem.text:
        new_el.text = PLACEHOLDER_RE.sub("", elem.text)
    else:
        new_el.text = elem.text
    new_el.tail = elem.tail
    for k, v in list(new_el.attrib.items()):
        if v and PLACEHOLDER_RE.search(v):
            del new_el.attrib[k]
    for child in elem:
        pruned = _static_prune(child)
        if pruned is not None:
            new_el.append(pruned)
    if len(new_el) == 0 and not (new_el.text and str(new_el.text).strip()):
        return None
    return new_el


def _elem_has_own_placeholder(elem: ET.Element) -> bool:
    parts = []
    if elem.text:
        parts.append(elem.text)
    if elem.tail:
        parts.append(elem.tail)
    for v in elem.attrib.values():
        if v:
            parts.append(v)
    return any(PLACEHOLDER_RE.search(p) for p in parts)


def _dynamic_prune(elem: ET.Element):
    """Keep only subtrees that still contain at least one placeholder (dynamic layer)."""
    if not _subtree_has_placeholder(elem):
        return None
    pruned_children = []
    for child in elem:
        p = _dynamic_prune(child)
        if p is not None:
            pruned_children.append(p)
    if not _elem_has_own_placeholder(elem) and not pruned_children:
        return None
    new_el = ET.Element(elem.tag, dict(elem.attrib))
    new_el.text = elem.text
    new_el.tail = elem.tail
    for p in pruned_children:
        new_el.append(p)
    return new_el


def split_template_svg(svg_text: str) -> tuple[str, str]:
    """Split full SVG into (static_xml, dynamic_xml) sharing the same root dimensions."""
    root = ET.fromstring(svg_text.strip())
    static_el = _static_prune(root)
    dynamic_el = _dynamic_prune(root)
    if static_el is None or dynamic_el is None:
        raise ValueError("split_template_svg produced empty static or dynamic layer")
    return (
        ET.tostring(static_el, encoding="unicode"),
        ET.tostring(dynamic_el, encoding="unicode"),
    )


def _generate_qr_code_bytes(data: str):
    """Module-level QR generator for picklable worker processes."""
    if not data:
        return None
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(str(data))
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _row_value_str(row: dict, col_name: str) -> str:
    if col_name not in row:
        return ""
    val = row[col_name]
    if val is None:
        return ""
    try:
        if pd.isna(val):
            return ""
    except Exception:
        pass
    return str(val)


def _apply_column_mappings(svg_content: str, row: dict, column_mappings: dict) -> str:
    for placeholder, column_name in column_mappings.items():
        if placeholder == "{{QR_CODE}}":
            continue
        if isinstance(column_name, list):
            sub_events = []
            for col in column_name:
                v = _row_value_str(row, col)
                if v:
                    event_name = col.split(" ~ ")[-1] if " ~ " in col else col
                    sub_events.append(event_name)
            value = "\n".join(sub_events)
        else:
            value = _row_value_str(row, column_name)
        if placeholder in svg_content:
            svg_content = svg_content.replace(placeholder, value)
    return svg_content


def _replace_qr_placeholder(
    svg_content: str, row: dict, temp_dir: str, row_index
) -> str:
    if "{{QR_CODE}}" not in svg_content:
        return svg_content
    replaced = False
    qr_data = row.get("QR Code", "")
    if qr_data is not None and qr_data != "":
        try:
            if pd.isna(qr_data):
                qr_data = ""
        except Exception:
            pass
    if qr_data:
        buf = _generate_qr_code_bytes(str(qr_data))
        if buf:
            fn = f"qr_{row_index}.png"
            with open(os.path.join(temp_dir, fn), "wb") as qf:
                qf.write(buf.getvalue())
            svg_content = svg_content.replace("{{QR_CODE}}", fn)
            replaced = True
    if not replaced:
        svg_content = svg_content.replace("{{QR_CODE}}", "")
    return svg_content


def _strip_remaining_placeholders(svg_content: str) -> str:
    remaining = set(PLACEHOLDER_RE.findall(svg_content))
    if remaining:
        logger.warning(
            "Final cleanup removing %s remaining placeholders: %s",
            len(remaining),
            remaining,
        )
    for token in remaining:
        svg_content = svg_content.replace(token, "")
    return svg_content


def _render_dynamic_drawing(args: dict):
    """Picklable worker: render dynamic-only SVG for one row; returns (row_index, pickle_bytes|None, err|None)."""
    row_index = args["row_index"]
    temp_dir = args["temp_dir"]
    dynamic_path = args["dynamic_svg_path"]
    column_mappings = args["column_mappings"]
    row = args["row"]
    badge_w = args["badge_width"]
    badge_h = args["badge_height"]
    try:
        with open(dynamic_path, "r", encoding="utf-8") as f:
            svg_content = f.read()
        svg_content = _apply_column_mappings(svg_content, row, column_mappings)
        svg_content = _replace_qr_placeholder(svg_content, row, temp_dir, row_index)
        svg_content = _strip_remaining_placeholders(svg_content)
        out_svg = os.path.join(temp_dir, f"badge_dynamic_{row_index}.svg")
        with open(out_svg, "w", encoding="utf-8") as wf:
            wf.write(svg_content)
        drawing = svg2rlg(out_svg)
        if os.path.exists(out_svg):
            os.remove(out_svg)
        if not drawing:
            return (row_index, None, "svg2rlg returned None")
        scale_x = badge_w / drawing.width
        scale_y = badge_h / drawing.height
        scale = min(scale_x, scale_y)
        drawing.width = badge_w
        drawing.height = badge_h
        drawing.scale(scale, scale)
        return (
            row_index,
            pickle.dumps(drawing, protocol=pickle.HIGHEST_PROTOCOL),
            None,
        )
    except Exception as e:
        logger.error(
            "Error rendering dynamic badge row_index=%s: %s",
            row_index,
            e,
            exc_info=True,
        )
        return (row_index, None, str(e))

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
                 club_logo_height=None, avery_template='5392', show_outlines=False):
        """
        Initialize the badge generator.
        
        Args:
            excel_file: Path to processed Excel file
            svg_template_path: Path to SVG template file
            column_mappings: Dict mapping placeholders to Excel columns
            afrp_logo_path: Path to default AFRP logo
            club_logo_path: Optional path to club-specific logo
            avery_template: Avery template code (default: 5392)
            show_outlines: Draw badge outlines for alignment testing
        """
        self.excel_file = excel_file
        self.svg_template_path = svg_template_path
        self.column_mappings = column_mappings
        # Resolve logo paths to absolute paths up-front so they survive any
        # later os.chdir() the caller might do (e.g. the /pull-process-generate
        # endpoint chdir's into a temp working dir while preprocessing).
        self.afrp_logo_path = os.path.abspath(afrp_logo_path) if afrp_logo_path else None
        self.club_logo_path = os.path.abspath(club_logo_path) if club_logo_path else None
        self.club_logo_width = club_logo_width
        self.club_logo_height = club_logo_height
        self.avery_template = avery_template
        self.show_outlines = show_outlines

        # Filenames used inside each per-badge temp dir; populated by
        # _stage_static_assets(). Empty string => placeholder will be cleared.
        self._afrp_logo_filename = ''
        self._club_logo_filename = ''
        
        # Debug logging
        logger.info(f"BadgeGenerator initialized with:")
        logger.info(f"  - AFRP logo: {afrp_logo_path} (exists: {os.path.exists(afrp_logo_path) if afrp_logo_path else False})")
        logger.info(f"  - Club logo: {club_logo_path} (exists: {os.path.exists(club_logo_path) if club_logo_path else False})")
        if club_logo_width and club_logo_height:
            logger.info(f"  - Club logo dimensions: {club_logo_width}x{club_logo_height}")
        logger.info(f"  - SVG template: {svg_template_path}")
        logger.info(f"  - Show outlines: {show_outlines}")
        
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
    
    def _stage_static_assets(self, temp_dir):
        """
        Copy AFRP and Club logos into ``temp_dir`` once per generation so each
        rendered SVG can reference them by relative filename.

        Using on-disk image files (instead of data: URIs embedded in the SVG)
        is significantly more reliable: ``svglib`` has full support for raster
        and SVG images referenced by relative path, but its inline data:-URI
        path only matches PNG/JPEG and silently drops other types (notably SVG
        club logos). It also avoids bloating every rendered SVG with a 400KB+
        base64 string per logo.
        """
        self._afrp_logo_filename = ''
        self._club_logo_filename = ''

        if self.afrp_logo_path and os.path.exists(self.afrp_logo_path):
            ext = os.path.splitext(self.afrp_logo_path)[1].lower() or '.png'
            filename = f'afrp_logo{ext}'
            try:
                shutil.copyfile(self.afrp_logo_path, os.path.join(temp_dir, filename))
                self._afrp_logo_filename = filename
                logger.info(f"Staged AFRP logo: {self.afrp_logo_path} -> {filename}")
            except Exception as e:
                logger.error(f"Failed to stage AFRP logo {self.afrp_logo_path}: {e}")
        else:
            logger.warning(
                f"AFRP logo missing or not provided (path={self.afrp_logo_path}); "
                "the {{AFRP_LOGO}} placeholder will be left blank."
            )

        if self.club_logo_path and os.path.exists(self.club_logo_path):
            ext = os.path.splitext(self.club_logo_path)[1].lower() or '.png'
            filename = f'club_logo{ext}'
            try:
                shutil.copyfile(self.club_logo_path, os.path.join(temp_dir, filename))
                self._club_logo_filename = filename
                logger.info(f"Staged club logo: {self.club_logo_path} -> {filename}")
            except Exception as e:
                logger.error(f"Failed to stage club logo {self.club_logo_path}: {e}")
        elif self.club_logo_path:
            logger.warning(
                f"Club logo path provided but file not found: {self.club_logo_path}; "
                "the {{CLUB_LOGO}} placeholder will be left blank."
            )

    def _scale_drawing_to_badge(self, drawing, badge_width, badge_height):
        """Scale a ReportLab Drawing to fit the Avery badge cell (mutates drawing)."""
        scale_x = badge_width / drawing.width
        scale_y = badge_height / drawing.height
        scale = min(scale_x, scale_y)
        drawing.width = badge_width
        drawing.height = badge_height
        drawing.scale(scale, scale)

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

        with open(self.svg_template_path, 'r', encoding='utf-8') as f:
            svg_content = f.read()

        svg_content = self.adjust_club_logo_dimensions(svg_content)

        logger.debug(f"SVG template length: {len(svg_content)} characters")

        row = row_data.to_dict()
        for placeholder, column_name in self.column_mappings.items():
            if placeholder == "{{QR_CODE}}":
                continue
            if not isinstance(column_name, list) and column_name not in row_data.index:
                logger.warning(
                    "Column '%s' not found in data for row %s",
                    column_name,
                    row_data.name,
                )

        svg_content = _apply_column_mappings(
            svg_content, row, self.column_mappings
        )
        svg_content = _replace_qr_placeholder(
            svg_content, row, temp_dir, row_data.name
        )

        # AFRP logo and Club logo: just point at the staged file in temp_dir.
        # svglib will resolve the relative href against the SVG's directory.
        svg_content = svg_content.replace("{{AFRP_LOGO}}", self._afrp_logo_filename)
        svg_content = svg_content.replace("{{CLUB_LOGO}}", self._club_logo_filename)

        svg_content = _strip_remaining_placeholders(svg_content)

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
            temp_dir = os.path.abspath(temp_dir)
            logger.info(f"Using temporary directory: {temp_dir}")

            # Copy AFRP/Club logos into the temp dir once so every per-badge
            # SVG can reference them by relative filename.
            self._stage_static_assets(temp_dir)

            cache_static = os.environ.get("BADGE_GENERATOR_CACHE_STATIC", "1") != "0"
            static_form_name = "badge_static_layer"

            with open(self.svg_template_path, "r", encoding="utf-8") as tf:
                svg_base = tf.read()
            svg_base = self.adjust_club_logo_dimensions(svg_base)
            svg_base = svg_base.replace("{{AFRP_LOGO}}", self._afrp_logo_filename)
            svg_base = svg_base.replace("{{CLUB_LOGO}}", self._club_logo_filename)

            static_xml, dynamic_xml = split_template_svg(svg_base)
            static_svg_path = os.path.join(temp_dir, "_static_layer.svg")
            dynamic_svg_path = os.path.join(temp_dir, "_dynamic_layer.svg")
            with open(static_svg_path, "w", encoding="utf-8") as sf:
                sf.write(static_xml)
            with open(dynamic_svg_path, "w", encoding="utf-8") as df:
                df.write(dynamic_xml)

            static_drawing = svg2rlg(static_svg_path)
            if not static_drawing:
                raise RuntimeError("Failed to convert static SVG layer to ReportLab drawing")
            self._scale_drawing_to_badge(static_drawing, badge_width, badge_height)

            if cache_static:
                c.beginForm(
                    static_form_name,
                    0,
                    0,
                    static_drawing.width,
                    static_drawing.height,
                )
                renderPDF.draw(static_drawing, c, 0, 0)
                c.endForm()

            max_workers = int(
                os.environ.get("BADGE_GENERATOR_WORKERS", os.cpu_count() or 4)
            )
            max_workers = max(1, max_workers)

            dynamic_by_index = {}
            if total_badges > 0:
                workers = min(max_workers, total_badges)
                work_items = []
                for idx, row in self.df.iterrows():
                    work_items.append(
                        {
                            "row_index": idx,
                            "temp_dir": temp_dir,
                            "dynamic_svg_path": dynamic_svg_path,
                            "column_mappings": self.column_mappings,
                            "row": row.to_dict(),
                            "badge_width": badge_width,
                            "badge_height": badge_height,
                        }
                    )
                with ProcessPoolExecutor(max_workers=workers) as pool:
                    futures = [
                        pool.submit(_render_dynamic_drawing, item) for item in work_items
                    ]
                    done = 0
                    for fut in as_completed(futures):
                        row_index, pdata, err = fut.result()
                        if err:
                            logger.error(
                                "Dynamic render failed for row_index=%s: %s",
                                row_index,
                                err,
                            )
                        elif pdata:
                            try:
                                dynamic_by_index[row_index] = pickle.loads(pdata)
                            except Exception as pe:
                                logger.error(
                                    "Failed to unpickle drawing row_index=%s: %s",
                                    row_index,
                                    pe,
                                    exc_info=True,
                                )
                        done += 1
                        if progress_callback:
                            progress_callback(
                                done,
                                total_badges,
                                f"Generated badge {done} of {total_badges}",
                            )

            badges_on_current_page = 0

            for index, row in self.df.iterrows():
                # Calculate position on page (index label order must match legacy behavior)
                badge_num = index % badges_per_page
                col = badge_num % cols
                row_pos = badge_num // cols

                # Calculate x, y position
                x = margin_left + col * (badge_width + gap_h)
                y = page_height - margin_top - (row_pos + 1) * badge_height - (row_pos * gap_v)

                try:
                    drawing = dynamic_by_index.get(index)
                    if drawing:
                        logger.debug(
                            "Compositing badge at PDF (%.2f\", %.2f\")",
                            x / inch,
                            y / inch,
                        )
                        c.saveState()
                        c.translate(x, y)
                        if cache_static and c.hasForm(static_form_name):
                            c.doForm(static_form_name)
                        else:
                            renderPDF.draw(static_drawing, c, 0, 0)
                        renderPDF.draw(drawing, c, 0, 0)
                        c.restoreState()
                    else:
                        logger.warning(
                            "No dynamic drawing for badge index=%s; skipping composite",
                            index,
                        )

                except Exception as e:
                    logger.error(
                        "Error compositing badge index=%s: %s",
                        index,
                        e,
                        exc_info=True,
                    )

                badges_on_current_page += 1
                page_is_full = badges_on_current_page == badges_per_page
                is_last_badge = (index + 1) == total_badges

                # Draw tear-line guides once per page (not once per badge).
                if self.show_outlines and (page_is_full or is_last_badge):
                    self._draw_cut_lines(c, page_width, page_height)

                if page_is_full and not is_last_badge:
                    c.showPage()
                    badges_on_current_page = 0
                    logger.debug("Starting new page after index=%s badges", index)

            # Save PDF
            c.save()
            logger.info(f"PDF saved to: {output_path}")
        
        return output_path

    def _draw_cut_lines(self, canvas_obj, page_width, page_height):
        """
        Draw unique badge boundary lines for the current Avery sheet.
        Lines are drawn once per page so only true tear/cut lines are shown.
        """
        spec = self.template_spec
        badge_width = spec['width'] * inch
        badge_height = spec['height'] * inch
        cols = spec['cols']
        rows = spec['rows']
        margin_left = spec['margin_left'] * inch
        margin_top = spec['margin_top'] * inch
        gap_h = spec.get('gap_horizontal', 0) * inch
        gap_v = spec.get('gap_vertical', 0) * inch

        # Preserve insertion order for deterministic rendering while deduplicating.
        unique_segments = OrderedDict()

        def add_segment(x1, y1, x2, y2):
            # Normalize direction so identical neighboring edges dedupe correctly.
            if (x1, y1) <= (x2, y2):
                key = (round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4))
            else:
                key = (round(x2, 4), round(y2, 4), round(x1, 4), round(y1, 4))
            unique_segments[key] = None

        for row_idx in range(rows):
            for col_idx in range(cols):
                x = margin_left + col_idx * (badge_width + gap_h)
                y = page_height - margin_top - (row_idx + 1) * badge_height - (row_idx * gap_v)

                # Rectangle edges for each label position.
                add_segment(x, y, x + badge_width, y)  # bottom
                add_segment(x, y + badge_height, x + badge_width, y + badge_height)  # top
                add_segment(x, y, x, y + badge_height)  # left
                add_segment(x + badge_width, y, x + badge_width, y + badge_height)  # right

        canvas_obj.saveState()
        canvas_obj.setStrokeColorRGB(0.8, 0.8, 0.8)  # Light gray guides
        canvas_obj.setLineWidth(0.5)

        for x1, y1, x2, y2 in unique_segments.keys():
            canvas_obj.line(x1, y1, x2, y2)

        canvas_obj.restoreState()
    
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
