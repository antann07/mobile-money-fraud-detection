"""Promote user id=2 to admin role."""
from db import get_db

conn = get_db()
conn.execute("UPDATE users SET role = 'admin' WHERE id = 2")
conn.commit()
row = conn.execute("SELECT id, full_name, email, role FROM users WHERE id = 2").fetchone()
print(dict(row))
conn.close()
