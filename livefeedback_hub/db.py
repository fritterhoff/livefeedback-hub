from sqlalchemy import Column
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.schema import UniqueConstraint
from sqlalchemy.types import Integer, String, BLOB, Boolean

Base = declarative_base()

GUID_REGEX = r"[a-f0-9]{8}-[a-f0-9]{4}-[1-5][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}"


class AutograderZip(Base):
    __tablename__ = "autograder_zips"

    id = Column(String, primary_key=True)
    owner = Column(String)
    data = Column(BLOB)
    description = Column(String)
    ready = Column(Boolean)


class Result(Base):
    __tablename__ = "results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user = Column(String)
    assignment = Column(String)
    data = Column(String)

    __table_args__ = (UniqueConstraint("user", "assignment"),)
