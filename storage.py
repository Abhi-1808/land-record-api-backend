import os
import cloudinary
import cloudinary.uploader

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)


def upload_file(file_bytes: bytes, filename: str, folder: str = "land_records") -> str:
    """
    Uploads a file to storage and returns a public URL.
    Currently backed by Cloudinary — swap this implementation
    to change providers without touching the rest of the app.
    """
    result = cloudinary.uploader.upload(
        file_bytes,
        resource_type="raw",
        folder=folder,
        public_id=filename,
        use_filename=True,
        unique_filename=False
    )
    return result.get("secure_url")