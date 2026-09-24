from sqlmodel import Field, SQLModel


class DeviceMeta(SQLModel, table=True):
    did: str = Field(primary_key=True)
    name: str = Field()
    product_name: str = Field()
    lock_switch: bool = Field()
    program_enabled: bool = Field()
