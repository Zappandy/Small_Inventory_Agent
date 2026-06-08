# ABCs file to hold abstract classes and interface to use for models, processors, etc. for shareable code
# ABCs represent base classes which define basic functionality and are intended to be inherited from

from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Optional, TypedDict, List


class Prompt(ABC, BaseModel):
    
    # force subclass to define prompt_type
    def __init__(self) -> None:
        if not hasattr(self, "prompt_type"):
            raise NotImplementedError
    
    @abstractmethod
    @classmethod
    def process_query(cls) -> ModelInputDictionary:
        raise NotImplementedError
    
    @property
    def processed_query(self) -> ModelInputDictionary:
        raise NotImplementedError


class Chat(ABC, BaseModel):
    messages_list: list
    chat_history: list
    contains_prompt_types: set
    
    def add_message(self, turn_dictionary):
        self.messages_list.append(turn_dictionary)
        
    def clear_history(self):
        self.chat_history = []

class ModelInputDictionary(TypedDict):
    input_ids: List[int]
    attention_mask: List[int]
    token_type_ids: Optional[List[int]]
    
