from fastapi import HTTPException
from sqlalchemy.orm import Session
from app import models
from app.schemas.user import UserCreate
from app.utils.password import get_password_hash, verify_password
from app.core.security import create_access_token, create_refresh_token


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def create_user(self, payload: UserCreate):
        existing = self.db.query(models.user.User).filter(
            models.user.User.email == payload.email
        ).first()

        if existing:
            raise ValueError("User exists")

        # 🔥 Check if this is the first user
        user_count = self.db.query(models.user.User).count()

        hashed = get_password_hash(payload.password)

        new_user = models.user.User(
            email=payload.email,
            hashed_password=hashed,
            full_name=payload.full_name
        )

        self.db.add(new_user)
        self.db.commit()
        self.db.refresh(new_user)

        # 🔥 Decide role
        if user_count == 0:
            role_name = "ADMIN"
        else:
            role_name = "MEMBER"

        role = self.db.query(models.role.Role).filter_by(name=role_name).first()

        if role:
            new_user.roles.append(role)
            self.db.commit()
            self.db.refresh(new_user)
        else:
            raise ValueError(f"{role_name} role not found in DB")

        return {
            "id": new_user.id,
            "email": new_user.email,
            "full_name": new_user.full_name,
            "roles": [r.name for r in new_user.roles],
        }
 
    def authenticate_user_and_get_tokens(self, email: str, password: str):
        user = self.db.query(models.user.User).filter(
            models.user.User.email == email
        ).first()

        if not user or not verify_password(password, user.hashed_password):
            return None

        # ✅ extract roles
        role_names = [role.name for role in user.roles]

        access = create_access_token(
            subject=str(user.id)
        )

        refresh = create_refresh_token(subject=str(user.id))

        rt = models.refresh_token.RefreshToken(
            user_id=user.id,
            token=refresh
        )

        self.db.add(rt)
        self.db.commit()

        return {
            "access_token": access,
            "token_type": "bearer",
            "refresh_token": refresh,
            "roles": role_names,
            "full_name": user.full_name,
            "email": user.email,
        }

    def list_users(self, current_user, case_id: int | None = None):
        current_roles = {r.name for r in current_user.roles}

        query = self.db.query(models.user.User).join(models.user.User.roles)

        # ADMIN → all users + managers
        if "ADMIN" in current_roles:
            users = query.filter(
                models.role.Role.name.in_(["MEMBER", "MANAGER"])
            ).distinct().all()

        # MANAGER → all users
        elif "MANAGER" in current_roles:
            users = query.filter(
                models.role.Role.name == "MEMBER"
            ).distinct().all()

        # MEMBER → same case users
        elif "MEMBER" in current_roles:
            if not case_id:
                return []

            users = (
                query
                .join(models.associations_case_user.case_users)
                .filter(
                    models.associations_case_user.case_users.c.case_id == case_id,
                    models.role.Role.name == "MEMBER"
                )
                .distinct()
                .all()
            )
        else:
            users = []

        return self.format_users(users)
    
    def get_assignable_users(self, current_user, case_id: int):
        current_roles = {r.name for r in current_user.roles}

        # Only ADMIN or MANAGER can assign
        if "ADMIN" not in current_roles and "MANAGER" not in current_roles:
            raise HTTPException(403, "Not allowed")

        query = (
            self.db.query(models.user.User)
            .join(models.user.User.roles)
            .filter(models.role.Role.name == "MEMBER")
        )

        # Optional: exclude already assigned users
        query = query.outerjoin(
            models.associations_case_user.case_users,
            (models.associations_case_user.case_users.c.user_id == models.user.User.id) &
            (models.associations_case_user.case_users.c.case_id == case_id)
        ).filter(
            models.associations_case_user.case_users.c.user_id == None
        )

        users = query.distinct().all()

        return self.format_users(users)
    
    def get_assignable_managers(self, current_user, case_id: int):
        current_roles = {r.name for r in current_user.roles}

        # Only ADMIN can assign managers
        if "ADMIN" not in current_roles:
            raise HTTPException(403, "Not allowed")

        query = (
            self.db.query(models.user.User)
            .join(models.user.User.roles)
            .filter(models.role.Role.name == "MANAGER")
        )

        # Optional: exclude already assigned managers
        case = self.db.query(models.case.Case).filter(models.case.Case.id == case_id).first()

        if not case:
            raise HTTPException(404, "Case not found")

        existing_manager_ids = [m.id for m in case.managers]

        if existing_manager_ids:
            query = query.filter(~models.user.User.id.in_(existing_manager_ids))

        users = query.distinct().all()

        return self.format_users(users)
    
    def format_users(self, users):
        return [
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "roles": [r.name for r in u.roles],
            }
            for u in users
        ]
        
    def make_manager(self, current_user, user_id: int):
        current_roles = {r.name for r in current_user.roles}

        # Only ADMIN can make manager
        if "ADMIN" not in current_roles:
            raise HTTPException(403, "Not allowed")

        user = self.db.query(models.user.User).filter(models.user.User.id == user_id).first()

        if not user:
            raise HTTPException(404, "User not found")

        manager_role = self.db.query(models.role.Role).filter(models.role.Role.name == "MANAGER").first()

        if not manager_role:
            raise HTTPException(500, "MANAGER role not found")

        if manager_role in user.roles:
            raise HTTPException(400, "User is already a manager")

        user.roles.append(manager_role)
        self.db.commit()
        self.db.refresh(user)
        
        # migrate case assignments
        cases = (
            self.db.query(models.case.Case)
            .filter(
                models.case.Case.users.any(
                    models.user.User.id == user.id
                )
            )
            .all()
        )

        for case in cases:
            # remove from users relation
            if user in case.users:
                case.users.remove(user)

            # add to managers relation
            if user not in case.managers:
                case.managers.append(user)

        # remove MEMBER role
        member_role = (
            self.db.query(models.role.Role)
            .filter(models.role.Role.name == "MEMBER")
            .first()
        )

        if member_role in user.roles:
            user.roles.remove(member_role)

        self.db.commit()
        self.db.refresh(user)
        

        return {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "roles": [r.name for r in user.roles],
        }
def seed_roles(db):
    roles = ["ADMIN", "MANAGER", "MEMBER"]

    existing_roles = db.query(models.role.Role).count()

    if existing_roles == 0:
        for role_name in roles:
            role = models.role.Role(name=role_name)
            db.add(role)

        db.commit()