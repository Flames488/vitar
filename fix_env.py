with open('/app/alembic/env.py', 'r') as f:
    content = f.read()

old = "        with context.begin_transaction():\n            context.run_migrations()\n    finally:"
new = "        with context.begin_transaction():\n            context.run_migrations()\n        connection.commit()\n    finally:"

if old in content:
    content = content.replace(old, new)
    with open('/app/alembic/env.py', 'w') as f:
        f.write(content)
    print('Patched successfully')
else:
    print('Pattern not found - showing relevant section:')
    idx = content.find('context.run_migrations()')
    print(repr(content[idx-50:idx+100]))
