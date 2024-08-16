import structlog
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    JSON,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# Set up structured logging
log = structlog.get_logger()

# Set up database
Base = declarative_base()
engine = create_engine("sqlite:///door_events.db")
Session = sessionmaker(bind=engine)


class DoorEvent(Base):
    __tablename__ = "door_events"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    user = Column(String)
    action = Column(String)
    metadata = Column(JSON)


Base.metadata.create_all(engine)


def track_event(user: str, action: str, metadata: dict | None = None):
    if metadata is None:
        metadata = {}

    log.info("door_event", user=user, action=action, metadata=metadata)

    session = Session()
    event = DoorEvent(user=user, action=action, metadata=metadata)
    session.add(event)
    session.commit()
    session.close()
