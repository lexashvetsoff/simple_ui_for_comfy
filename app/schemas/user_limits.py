from pydantic import BaseModel


class UserLimitsBase(BaseModel):
    max_concurrent_jobs: int
    max_jobs_per_day: int


class UserLimitsUpdate(UserLimitsBase):
    pass


class UserLimitsOut(UserLimitsBase):
    user_id: int

    class Config:
        from_attributes = True
