from pydantic import BaseModel

class UserInfo(BaseModel):
    user_id: str
    spreadsheet_id: str
    role: str
    enabled: bool = True

    @property
    def is_admin(self) -> bool:
        return self.role.lower() == "admin"
