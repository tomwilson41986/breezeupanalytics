"""SQLAlchemy ORM models for the breeze-up analytics database."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Sale(Base):
    __tablename__ = "sale"

    sale_id: Mapped[str] = mapped_column(String(100), primary_key=True)  # e.g. "obs_march_2025"
    company: Mapped[str] = mapped_column(String(50))  # "OBS" | "Fasig-Tipton"
    sale_name: Mapped[str] = mapped_column(String(200))
    year: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[date | None] = mapped_column()
    end_date: Mapped[date | None] = mapped_column()
    location: Mapped[str | None] = mapped_column(String(200))
    catalog_url: Mapped[str | None] = mapped_column(Text)
    catalog_sale_id: Mapped[str | None] = mapped_column(String(50))  # OBS SPA sale ID e.g. "142"
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    lots: Mapped[list["Lot"]] = relationship(back_populates="sale", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("company IN ('OBS', 'Fasig-Tipton')", name="ck_sale_company"),
    )

    def __repr__(self) -> str:
        return f"<Sale(sale_id={self.sale_id!r}, name={self.sale_name!r})>"


class Lot(Base):
    __tablename__ = "lot"

    lot_id: Mapped[str] = mapped_column(String(150), primary_key=True)  # sale_id + hip_number
    hip_number: Mapped[int] = mapped_column(Integer)
    sale_id: Mapped[str] = mapped_column(ForeignKey("sale.sale_id"), index=True)

    # Horse identity
    horse_name: Mapped[str | None] = mapped_column(String(200))
    sex: Mapped[str | None] = mapped_column(String(20))  # "Colt", "Filly", "Gelding"
    colour: Mapped[str | None] = mapped_column(String(50))
    year_of_birth: Mapped[int | None] = mapped_column(Integer)

    # Pedigree
    sire: Mapped[str | None] = mapped_column(String(200))
    dam: Mapped[str | None] = mapped_column(String(200))
    dam_sire: Mapped[str | None] = mapped_column(String(200))
    breeder: Mapped[str | None] = mapped_column(Text)
    consignor: Mapped[str | None] = mapped_column(Text)
    state_bred: Mapped[str | None] = mapped_column(String(50))

    # Under tack
    under_tack_distance: Mapped[str | None] = mapped_column(String(10))  # "1/8" | "1/4"
    under_tack_time: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))  # e.g. 10.1
    under_tack_date: Mapped[date | None] = mapped_column()

    # Sale result
    sale_price: Mapped[int | None] = mapped_column(Integer)  # USD, null if RNA/out/withdrawn
    sale_status: Mapped[str | None] = mapped_column(String(20))  # sold/RNA/out/withdrawn
    buyer: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    sale: Mapped["Sale"] = relationship(back_populates="lots")
    assets: Mapped[list["Asset"]] = relationship(back_populates="lot", cascade="all, delete-orphan")
    performance: Mapped["Performance | None"] = relationship(
        back_populates="lot", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        UniqueConstraint("sale_id", "hip_number", name="uq_lot_sale_hip"),
        Index("ix_lot_sire", "sire"),
        Index("ix_lot_dam", "dam"),
        Index("ix_lot_consignor", "consignor"),
        CheckConstraint(
            "sale_status IS NULL OR sale_status IN ('sold', 'RNA', 'out', 'withdrawn')",
            name="ck_lot_sale_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<Lot(lot_id={self.lot_id!r}, hip={self.hip_number})>"


class Asset(Base):
    __tablename__ = "asset"

    asset_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lot_id: Mapped[str] = mapped_column(ForeignKey("lot.lot_id"), index=True)

    asset_type: Mapped[str] = mapped_column(String(50))  # breeze_video, walk_video, photo, etc.
    source_url: Mapped[str | None] = mapped_column(Text)
    local_path: Mapped[str | None] = mapped_column(Text)
    s3_key: Mapped[str | None] = mapped_column(Text)  # e.g. videos/obs_march_2025/1.mp4
    file_size: Mapped[int | None] = mapped_column(Integer)  # bytes
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime)  # S3 upload timestamp
    checksum: Mapped[str | None] = mapped_column(String(64))  # md5 hex digest

    lot: Mapped["Lot"] = relationship(back_populates="assets")

    __table_args__ = (
        CheckConstraint(
            "asset_type IN ('breeze_video', 'walk_video', 'photo', 'pedigree_page')",
            name="ck_asset_type",
        ),
    )

    def __repr__(self) -> str:
        return f"<Asset(id={self.asset_id}, type={self.asset_type!r}, lot={self.lot_id!r})>"


class Performance(Base):
    __tablename__ = "performance"

    performance_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lot_id: Mapped[str] = mapped_column(ForeignKey("lot.lot_id"), unique=True, index=True)

    horse_name: Mapped[str | None] = mapped_column(String(200))  # as raced (may differ from sale)
    country: Mapped[str | None] = mapped_column(String(10))  # "US", "GB", etc.
    starts: Mapped[int | None] = mapped_column(Integer, default=0)
    wins: Mapped[int | None] = mapped_column(Integer, default=0)
    places: Mapped[int | None] = mapped_column(Integer, default=0)
    earnings: Mapped[int | None] = mapped_column(Integer)  # USD
    best_class: Mapped[str | None] = mapped_column(String(20))
    best_race_name: Mapped[str | None] = mapped_column(String(300))
    best_equibase_speed_figure: Mapped[int | None] = mapped_column(Integer)
    last_updated: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[str | None] = mapped_column(Text)

    lot: Mapped["Lot"] = relationship(back_populates="performance")

    __table_args__ = (
        CheckConstraint(
            "best_class IS NULL OR best_class IN "
            "('G1', 'Graded', 'Stakes', 'Winner', 'Placed', 'Unplaced', 'Unraced')",
            name="ck_performance_best_class",
        ),
        Index("ix_performance_best_class", "best_class"),
    )

    def __repr__(self) -> str:
        return f"<Performance(id={self.performance_id}, horse={self.horse_name!r})>"
