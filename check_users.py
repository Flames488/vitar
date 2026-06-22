from app.core.database import SessionLocal
from app.models.models import User, Clinic
db = SessionLocal()
users = db.query(User).all()
print('Users in DB:', len(users))
for u in users:
    print(' -', u.id, u.email)
clinics = db.query(Clinic).all()
print('Clinics in DB:', len(clinics))
for c in clinics:
    print(' -', c.id, c.owner_id, c.name)
db.close()
