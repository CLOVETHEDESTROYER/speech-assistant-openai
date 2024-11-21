from sqlalchemy.orm import Session
from app import models, schemas


def create_call_schedule(db: Session, call: schemas.CallScheduleCreate):
    db_call = models.CallSchedule(
        phone_number=call.phone_number,
        scheduled_time=call.scheduled_time,
        scenario=call.scenario
    )
    db.add(db_call)
    db.commit()
    db.refresh(db_call)
    return db_call
