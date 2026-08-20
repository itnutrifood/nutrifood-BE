from pydantic import BaseModel, Field


class PublicStatistics(BaseModel):
    happy_customers: int = Field(ge=0)
    healty_meals: int = Field(ge=0)
    customer_rating: float = Field(ge=0, le=5)
