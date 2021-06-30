from sqlalchemy import Column
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.schema import UniqueConstraint
from sqlalchemy.types import Integer, String, BLOB

Base = declarative_base()


class AutograderZip(Base):
    __tablename__ = "autograder_zips"

    id = Column(String, primary_key=True)
    owner = Column(String)
    data = Column(BLOB)


class Result(Base):
    __tablename__ = "results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user = Column(String)
    assignment = Column(String)
    data = Column(String)

    __table_args__ = (UniqueConstraint("user", "assignment"),)

    def to_anonymous_dict(self):
        return {
            "data": self.data
        }