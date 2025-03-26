from app.db import SessionLocal
from app.models import User


def update_admin():
    db = SessionLocal()
    try:
        # Get user with ID 1
        user = db.query(User).filter(User.id == 1).first()

        if user:
            # Set as admin
            user.is_admin = True
            db.commit()
            print(f"User {user.email} (ID: {user.id}) has been set as admin.")
        else:
            print("User with ID 1 not found.")
    except Exception as e:
        print(f"Error updating admin: {str(e)}")
    finally:
        db.close()


if __name__ == "__main__":
    update_admin()
