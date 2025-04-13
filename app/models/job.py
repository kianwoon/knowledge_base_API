from typing import Optional
from pydantic import BaseModel, Field, EmailStr, field_validator, model_validator

class Job(BaseModel):
    name: Optional[str] = None
    id: str
    status: str
    type: str
    owner: Optional[str] = None 

    def __repr__(self):
        return f"<Job(name={self.name}, id={self.id}, status={self.status}, type={self.type})>"
    
    def to_dict(self):
        return {"name": self.name, "id": self.id, "status": self.status, "type": self.type, "owner": self.owner}

    @classmethod
    def from_dict(cls, data):
        return cls(
            name=data.get("name"),
            id=data["id"],
            status=data["status"],
            type=data["type"],
            owner=data.get("owner")
        )