from PIL import Image
import cv2

from typing import Union, Optional, List, Dict

from scripts.abcs import Prompt, ModelInputDictionary, Chat

import logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VisionPrompt(Prompt):
    text_prompt: Optional[str]
    images: Optional[Union[Image, List[Image]]]
    videos: Optional[Union[Image, List[cv2.VideoCapture]]]
    prompt_type: str = "vision"

    def __post_init__(self, **kwargs):
        if not self.images and not self.videos and not self.text_prompt:
            raise ValueError("At least one of images or videos must be provided for VisionPrompt.")
        elif self.text_prompt and (self.images or self.videos):
            pass
        elif self.text_prompt:
            logger.warning(
                "No images or videos provided for VisionPrompt."
                "Determining if the chat history contains an image or video."
            )
            chat = kwargs.get("chat", None)
            if not chat:
                logger.warning(
                    "No chat provided for VisionPrompt."
                    "Cannot determine if the chat history contains an image or video."
                    "Loading a text prompt."
                )
                self.prompt_type = "text"
                return None # implement

            contains_vision = "vision" in chat.contains_prompt_types
            if contains_vision: # implement
                return None
            else:
                logger.warning(
                    "No previous image or video message found in chat history."
                    "Loading a text prompt."
                )
                self.prompt_type = "text"
                return None # implement

    @property
    def processed_query(self) -> ModelInputDictionary:
        return self.process_query()

    @classmethod
    def procesS_query(cls):
        # to implement
        pass

if __name__ == '__main__':
    pass