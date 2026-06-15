from pydantic import BaseModel
from typing import Literal


class Order(BaseModel):
    order_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    type: str
    quantity: float
    price: float
    status: str
    reduce_only: bool
