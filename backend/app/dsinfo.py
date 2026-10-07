from dataclasses import dataclass, field


@dataclass
class DatasetInfo:
    """Plain, thread-safe view of a Dataset row (agents never touch the ORM session)."""

    id: str
    org_id: str
    name: str
    table_name: str
    row_count: int
    columns: list
    profile: dict = field(default_factory=dict)
    parquet_key: str = ""

    @classmethod
    def from_orm(cls, ds) -> "DatasetInfo":
        return cls(ds.id, ds.org_id, ds.name, ds.table_name, ds.row_count, ds.columns or [], ds.profile or {}, ds.parquet_key)
