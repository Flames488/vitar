"""
Vitar — Disposable Email Blocklist

Registration alone doesn't stop trial abuse via throwaway inboxes (temp-mail
services etc.) — soft email verification (see auth.py's /verify-email) only
tracks whether a real inbox was checked, it doesn't stop someone from using
a disposable one in the first place. This blocks known disposable-email
domains outright at registration time, before a user/clinic row is even
created.

Not exhaustive — new disposable providers appear constantly and a fully
exhaustive list isn't maintainable by hand. This covers the common,
well-known ones, which catches the overwhelming majority of casual abuse
without needing a paid third-party API.
"""

DISPOSABLE_EMAIL_DOMAINS = frozenset({
    "mailinator.com", "mailinator.net", "mailinator.org",
    "guerrillamail.com", "guerrillamail.net", "guerrillamail.org", "guerrillamail.biz",
    "guerrillamailblock.com", "sharklasers.com", "grr.la", "spam4.me",
    "10minutemail.com", "10minutemail.net", "10minemail.com",
    "temp-mail.org", "tempmail.com", "tempmail.net", "tempmailo.com",
    "throwawaymail.com", "throwaway.email", "trashmail.com", "trashmail.net", "trashmail.me",
    "yopmail.com", "yopmail.net", "yopmail.fr", "cool.fr.nf",
    "getnada.com", "nada.email", "fakeinbox.com", "fakemailgenerator.com",
    "dispostable.com", "maildrop.cc", "mintemail.com", "mytemp.email",
    "tempinbox.com", "tempinbox.net", "moakt.com", "moakt.cc",
    "emailondeck.com", "mohmal.com", "mohmal.im", "spamgourmet.com",
    "mailnesia.com", "mailcatch.com", "mailnull.com", "meltmail.com",
    "spambog.com", "spambog.de", "spambog.ru", "discard.email", "discardmail.com",
    "tempr.email", "tmpmail.org", "tmpmail.net", "tmailinator.com",
    "burnermail.io", "temp-inbox.com", "inboxkitten.com", "harakirimail.com",
    "mailexpire.com", "emailfake.com", "fakeinbox.net", "anonaddy.com",
    "1secmail.com", "1secmail.net", "1secmail.org", "wegwerfmail.de",
    "wegwerfmail.net", "wegwerfmail.org", "einrot.com", "einrot.de",
    "mytrashmail.com", "trash-mail.com", "trash-mail.de", "objectmail.com",
    "byom.de", "e4ward.com", "letthemeatspam.com", "spamex.com",
    "no-spam.ws", "spamfree24.org", "spamfree24.com", "spamfree24.de",
    "jetable.org", "jetable.net", "jetable.fr.nf", "courriel.fr.nf",
    "nospam.ze.tc", "nomail.xl.cx", "spam.la", "putthisinyourspamdatabase.com",
    "receivemail.org", "receiveee.com", "getairmail.com", "airmail.cc",
    "mail-temporaire.fr", "boximail.com", "crazymailing.com", "deadaddress.com",
    "instant-mail.de", "kurzepost.de", "mytempemail.com", "no-spam.ws",
    "owlpic.com", "shieldedmail.com", "tafmail.com", "tempemail.co",
    "tempemail.net", "tempymail.com", "veryrealemail.com", "zetmail.com",
})


def is_disposable_email(email: str) -> bool:
    if "@" not in email:
        return False
    domain = email.rsplit("@", 1)[1].strip().lower()
    return domain in DISPOSABLE_EMAIL_DOMAINS
