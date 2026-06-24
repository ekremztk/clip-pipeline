from abc import ABC, abstractmethod
from ..models import Listing, SearchConfig


class BaseAdapter(ABC):
    @abstractmethod
    async def search(self, config: SearchConfig) -> list[Listing]:
        ...

    @abstractmethod
    def platform_name(self) -> str:
        ...
