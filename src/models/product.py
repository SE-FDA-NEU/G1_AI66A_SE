from sqlmodel import Field, SQLModel


class Product(SQLModel, table=True):
    __tablename__ = "products"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, min_length=1, max_length=200)
    description: str = ""
    price: int = Field(gt=0)
    stock_quantity: int = Field(default=0, ge=0)
    image_url: str | None = None
    is_active: bool = True