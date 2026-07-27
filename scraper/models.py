from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Listing:
    # Required
    source: str
    title: str
    location: str
    url: str

    # Optional
    capacity: Optional[int] = None
    bedrooms: Optional[int] = None
    price: Optional[float] = None
    price_unit: Optional[str] = None          # "noc", "týden", "pobyt", …
    amenities: list[str] = field(default_factory=list)
    image_url: Optional[str] = None
    raw_extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "title": self.title,
            "location": self.location,
            "url": self.url,
            "capacity": self.capacity,
            "bedrooms": self.bedrooms,
            "price": self.price,
            "price_unit": self.price_unit,
            "amenities": self.amenities,
            "image_url": self.image_url,
            "raw_extra": self.raw_extra,
        }
