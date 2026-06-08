from PIL import Image
import cv2

def is_image(path: str) -> bool:
    ...
    
def is_video(path: str) -> bool:
    ... 

def is_model(path: str) -> bool:
    ...
    
def is_audio(path: str) -> bool:
    ...

def resolve_file_type(path: str) -> str:
    if is_image(path):
        return "image"
    elif is_video(path):
        return "video"
    else:
        raise ValueError(f"Unknown file type: {path}")