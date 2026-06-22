with open('/app/app/api/v1/endpoints/auth.py', 'r') as f:
    content = f.read()

old = """    trial_ends = utcnow() + timedelta(days=settings.TRIAL_DAYS)
    region = _determine_region(body.country)
    currency = "NGN" if body.country == "NG" else "USD"

    clinic = Clinic(
        owner_id=user.id,
        name=body.clinic_name,
        slug=_generate_slug(body.clinic_name, db),
        email=body.email.lower(),
        phone=body.phone,
        city=body.city,
        country=body.country.upper(),
        region=region,
        currency=currency,
        trial_started_at=utcnow(),
        trial_ends_at=trial_ends,
        is_active=True,
        onboarding_completed=False,
        onboarding_step=1,
    )
    db.add(clinic)
    db.flush()

    db.add(Subscription(
        clinic_id=clinic.id,
        plan=SubscriptionPlan.TRIAL,
        status=SubscriptionStatus.TRIALING,
        current_period_start=utcnow(),
        current_period_end=trial_ends,
        amount=0,
        currency=currency,
    ))
    _create_default_notification_settings(clinic.id, db)

    # Generate tokens and store refresh hash
    access_token  = create_access_token({"sub": user.id, "clinic_id": clinic.id})
    refresh_token = create_refresh_token({"sub": user.id})
    _store_refresh_token(user.id, refresh_token, db)

    db.commit()
    db.refresh(user)
    db.refresh(clinic)"""

new = """    trial_ends = utcnow() + timedelta(days=settings.TRIAL_DAYS)
    region = _determine_region(body.country)
    currency = "NGN" if body.country == "NG" else "USD"

    clinic = Clinic(
        owner_id=user.id,
        name=body.clinic_name,
        slug=_generate_slug(body.clinic_name, db),
        email=body.email.lower(),
        phone=body.phone,
        city=body.city,
        country=body.country.upper(),
        region=region,
        currency=currency,
        trial_started_at=utcnow(),
        trial_ends_at=trial_ends,
        is_active=True,
        onboarding_completed=False,
        onboarding_step=1,
    )
    db.add(clinic)
    db.commit()
    db.refresh(clinic)

    db.add(Subscription(
        clinic_id=clinic.id,
        plan=SubscriptionPlan.TRIAL,
        status=SubscriptionStatus.TRIALING,
        current_period_start=utcnow(),
        current_period_end=trial_ends,
        amount=0,
        currency=currency,
    ))
    _create_default_notification_settings(clinic.id, db)

    # Generate tokens and store refresh hash
    access_token  = create_access_token({"sub": user.id, "clinic_id": clinic.id})
    refresh_token = create_refresh_token({"sub": user.id})
    _store_refresh_token(user.id, refresh_token, db)

    db.commit()
    db.refresh(user)
    db.refresh(clinic)"""

if old in content:
    content = content.replace(old, new)
    with open('/app/app/api/v1/endpoints/auth.py', 'w') as f:
        f.write(content)
    print('Patched successfully')
else:
    print('Pattern not found')
    idx = content.find('db.flush()')
    print('db.flush() occurrences:', content.count('db.flush()'))
    idx2 = content.find('_generate_slug')
    print(repr(content[idx2:idx2+300]))
