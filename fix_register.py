import re

with open('/app/app/api/v1/endpoints/auth.py', 'r') as f:
    content = f.read()

old = """    user = User(
        email=body.email.lower(),
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        phone=body.phone,
        is_active=True,
        is_verified=False,
        email_verification_token=generate_secure_token(),
    )
    db.add(user)
    db.flush()"""

new = """    user = User(
        email=body.email.lower(),
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        phone=body.phone,
        is_active=True,
        is_verified=False,
        email_verification_token=generate_secure_token(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)"""

if old in content:
    content = content.replace(old, new)
    # Also remove the duplicate db.refresh(user) at the end since we do it above
    with open('/app/app/api/v1/endpoints/auth.py', 'w') as f:
        f.write(content)
    print('Patched successfully')
else:
    print('Pattern not found')
    # Show the relevant section
    idx = content.find('db.flush()')
    if idx >= 0:
        print(repr(content[idx-200:idx+50]))
    else:
        print('db.flush() not found either')
