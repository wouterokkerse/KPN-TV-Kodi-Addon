"""Build Kodi translation catalogs from this project's English/Dutch strings."""
import json
from pathlib import Path

STRINGS = {
30001: ('Live TV', 'Live tv'),
30002: ('Replay / TV guide', 'Terugkijken / tv-gids'),
30003: ('Films', 'Films'),
30004: ('Series', 'Series'),
30005: ('Search films and series', 'Zoek films en series'),
30006: ('My list (this device)', 'Mijn lijst (dit apparaat)'),
30007: ('Watch later (this device)', 'Kijk later (dit apparaat)'),
30008: ('Sign in', 'Inloggen'),
30009: ('Sign out', 'Uitloggen'),
30010: ('Settings', 'Instellingen'),
30011: ('Export diagnostics', 'Diagnostiek opslaan'),
30012: ('No items found.', 'Geen items gevonden.'),
30013: ('KPN ID email address', 'E-mailadres KPN ID'),
30014: ('KPN ID password', 'Wachtwoord KPN ID'),
30015: ('TV subscription number', 'Abonnementsnummer tv'),
30016: ('TV PIN', 'Pincode tv'),
30017: ('Signed in.', 'Ingelogd.'),
30018: ('Sign in with your KPN subscription to continue.', 'Log in met je KPN-abonnement om door te gaan.'),
30019: ('Error', 'Fout'),
30020: ('KPN TV could not complete this request. Check your connection, subscription and API setting. This experimental version still needs subscriber testing.', 'KPN TV kon dit verzoek niet uitvoeren. Controleer je verbinding, abonnement en API-instelling. Deze experimentele versie moet nog met een abonnement worden getest.'),
30021: ('Add to My list', 'Toevoegen aan Mijn lijst'),
30022: ('Add to Watch later', 'Toevoegen aan Kijk later'),
30023: ('Remove from this list', 'Verwijderen uit deze lijst'),
30024: ('List updated.', 'Lijst bijgewerkt.'),
30025: ('Today', 'Vandaag'),
30026: ('Widevine or InputStream Adaptive is unavailable on this device.', 'Widevine of InputStream Adaptive is niet beschikbaar op dit apparaat.'),
30027: ('Your session expired or KPN refused access. Sign in again; check subscription and device limits if this continues.', 'Je sessie is verlopen of KPN heeft toegang geweigerd. Log opnieuw in; controleer je abonnement en apparaatlimiet als dit blijft gebeuren.'),
30028: ('Session removed from this device.', 'Sessie verwijderd van dit apparaat.'),
30029: ('KPN profiles are not available in this addon.', 'KPN-profielen zijn niet beschikbaar in deze addon.'),
30030: ('Diagnostics saved (no credentials or stream URLs):', 'Diagnostiek opgeslagen (zonder inloggegevens of stream-URL’s):'),
30031: ('TV guide', 'Tv-gids'),
30032: ('Not yet broadcast', 'Nog niet uitgezonden'),
30033: ('Now', 'Nu'),
30034: ('Next', 'Straks'),
30035: ('Current programme information is unavailable.', 'Informatie over het huidige programma is niet beschikbaar.'),
30040: ('Account and connection', 'Account en verbinding'),
30041: ('Sign-in method', 'Inlogmethode'),
30042: ('KPN ID (email and password)', 'KPN ID (e-mail en wachtwoord)'),
30043: ('TV subscription number and PIN', 'Abonnementsnummer tv en pincode'),
30044: ('KPN API endpoint (sign in again after changing)', 'KPN API-adres (na wijzigen opnieuw inloggen)'),
30045: ('Experimental — Kodi 20/21; no password storage', 'Experimenteel — Kodi 20/21; wachtwoord wordt niet opgeslagen'),
}

root = Path(__file__).resolve().parents[1] / 'plugin.video.kpntv/resources/language'
for index, language in enumerate(('en_gb', 'nl_nl')):
    target = root / ('resource.language.' + language) / 'strings.po'
    target.parent.mkdir(parents=True, exist_ok=True)
    blocks = ['msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n']
    for number, texts in STRINGS.items():
        blocks.append('msgctxt "#%s"\nmsgid %s\nmsgstr %s\n' % (
            number, json.dumps(texts[0], ensure_ascii=False),
            json.dumps(texts[index] if index else '', ensure_ascii=False)))
    target.write_text('\n'.join(blocks), encoding='utf-8')
