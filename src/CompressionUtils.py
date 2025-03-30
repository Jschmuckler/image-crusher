import os
import tempfile
from PIL import Image
import mimetypes

class CompressionUtils:
    # Default thumbnail height (can be modified)
    THUMBNAIL_HEIGHT = 512
    
    # Supported image types for compression
    SUPPORTED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".gif", ".webp"]
    SUPPORTED_MIMETYPES = ["image/jpeg", "image/png", "image/bmp", "image/tiff", "image/gif", "image/webp"]
    
    @classmethod
    def is_supported_image(cls, content_type=None, file_name=None):
        """Check if the file is a supported image type.
        Args:
            content_type: The content type of the file
            file_name: The name of the file
        Returns:
            Boolean indicating if the file is a supported image
        """
        if content_type and content_type in cls.SUPPORTED_MIMETYPES:
            return True
            
        if file_name:
            ext = os.path.splitext(file_name.lower())[1]
            return ext in cls.SUPPORTED_EXTENSIONS
            
        return False
    
    @classmethod
    def compress_image(cls, input_file, height=None):
        """Compress an image to WebP format with the specified height, maintaining aspect ratio and orientation.
        Args:
            input_file: Path to the input image file
            height: Output height (defaults to THUMBNAIL_HEIGHT)
        Returns:
            Path to the compressed image file
        """
        if height is None:
            height = cls.THUMBNAIL_HEIGHT
            
        try:
            # Open the image
            img = Image.open(input_file)
            
            # Apply EXIF orientation first - manually rotate the image based on EXIF data
            # This ensures the WebP will have the correct visual orientation
            if hasattr(img, '_getexif') and img._getexif() is not None:
                exif = dict(img._getexif().items())
                orientation = exif.get(274)  # 274 is the orientation tag
                
                if orientation:
                    # Apply orientation corrections
                    if orientation == 2:
                        img = img.transpose(Image.FLIP_LEFT_RIGHT)
                    elif orientation == 3:
                        img = img.transpose(Image.ROTATE_180)
                    elif orientation == 4:
                        img = img.transpose(Image.FLIP_TOP_BOTTOM)
                    elif orientation == 5:
                        img = img.transpose(Image.FLIP_LEFT_RIGHT).transpose(Image.ROTATE_90)
                    elif orientation == 6:
                        img = img.transpose(Image.ROTATE_270)
                    elif orientation == 7:
                        img = img.transpose(Image.FLIP_LEFT_RIGHT).transpose(Image.ROTATE_270)
                    elif orientation == 8:
                        img = img.transpose(Image.ROTATE_90)
            
            # Get image dimensions after any rotation
            width, height_actual = img.size
            
            # If the image height is already smaller than target, keep original size
            if height_actual <= height:
                resize_height = height_actual
                new_width = width
            else:
                resize_height = height
                # Calculate new width to maintain aspect ratio
                width_percent = resize_height / float(height_actual)
                new_width = int(float(width) * width_percent)
            
            # Resize image maintaining aspect ratio
            img = img.resize((new_width, resize_height), Image.LANCZOS)
            
            # Save as WebP
            _, output_file = tempfile.mkstemp(suffix=".webp")
            
            # WebP format with maximum quality for transparency support
            img.save(output_file, "WEBP", quality=90, method=6)
            
            # Close the image after we're done
            img.close()
            
            return output_file
        except Exception as e:
            raise Exception(f"Error compressing image: {str(e)}")
    
    @classmethod
    def set_thumbnail_height(cls, height):
        """Set the thumbnail height globally.
        Args:
            height: New thumbnail height
        """
        cls.THUMBNAIL_HEIGHT = height
