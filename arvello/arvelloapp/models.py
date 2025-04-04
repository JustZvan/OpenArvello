from django.db import models
from django.template.defaultfilters import slugify
from django.utils import timezone
from uuid import uuid4
from django.core.validators import RegexValidator, MinValueValidator, MinLengthValidator
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from decimal import Decimal
from datetime import datetime, date
from .utils.text_utils import standardize_city_name
from django.db.models import Q
from simple_history.models import HistoricalRecords
from django.contrib.auth import get_user_model
from .middleware import get_current_request
from dateutil.relativedelta import relativedelta
from .utils.decimal_helpers import safe_decimal

class HistoryMixin:
    def get_history_user(self):
        # Dohvaća trenutnog korisnika iz zahtjeva
        request = get_current_request()
        if request and hasattr(request, 'user'):
            return request.user
        return None

    def get_history_data(self):
        # Formatira podatke iz povijesti za prikaz
        data = {}
        for field in self._meta.fields:
            if field.name not in ['id', 'history_id', 'history_date', 'history_type', 'history_user_id']:
                value = getattr(self, field.name)
                if value is not None:
                    data[field.verbose_name or field.name] = self._format_field_value(value)
        return data
    
    def _format_field_value(self, value):
        # Formatira vrijednost polja za prikaz
        if value is None:
            return "(prazno)"
        if isinstance(value, (datetime, date)):
            return value.strftime('%d.m.%Y. %H:%M:%S')
        if isinstance(value, Decimal):
            return f"{value:.2f}"
        if isinstance(value, get_user_model()):
            return value.get_full_name() or value.username
        return str(value)

    def save(self, *args, **kwargs):
        # Postavlja korisnika povijesti prije spremanja
        request = get_current_request()
        if request and hasattr(request, 'user'):
            self.history_user = request.user
        super().save(*args, **kwargs)

    def get_history_changes(self):
        # Dohvaća stvarne promjene između verzija
        try:
            prev_record = self.prev_record
            changes = {}
            if prev_record:
                for field in self._meta.fields:
                    if field.name not in ['id', 'history_id', 'history_date', 'history_type', 'history_user_id']:
                        old_value = getattr(prev_record, field.name)
                        new_value = getattr(self, field.name)
                        if old_value != new_value:
                            changes[field.verbose_name or field.name] = {
                                'old': self._format_field_value(old_value),
                                'new': self._format_field_value(new_value)
                            }
            return changes
        except Exception as e:
            print(f"Greška pri dohvaćanju promjena: {e}")
            return {}

    def get_field_changes(self):
        # Dohvaća promjene između verzija na siguran način
        changes = {}
        if not hasattr(self, 'prev_record') or not self.prev_record:
            return changes

        # Dohvati sva polja modela osim internih
        fields = [f for f in self._meta.fields 
                 if f.name not in ['id', 'history_id', 'history_date', 
                                 'history_type', 'history_user_id']]
        
        for field in fields:
            old_value = getattr(self.prev_record, field.name, None)
            new_value = getattr(self, field.name, None)
            
            if old_value != new_value:
                changes[field.name] = {
                    'verbose_name': field.verbose_name or field.name,
                    'old': self._format_field_value(old_value),
                    'new': self._format_field_value(new_value)
                }
        
        return changes

def validate_phone_number(value):
    # Validacija telefonskog broja
    if not all(char.isdigit() or char == '+' for char in value):
        raise ValidationError(
            ('Telefonski broj može sadržavati samo brojeve i znak +.'),
            params={'value': value},
        )

class Company(models.Model):
    # Model za tvrtku/subjekt

    PROVINCES = [
    ("ZAGREBAČKA ŽUPANIJA", "ZAGREBAČKA ŽUPANIJA"),
    ("KRAPINSKO-ZAGORSKA ŽUPANIJA", "KRAPINSKO-ZAGORSKA ŽUPANIJA"),
    ("SISAČKO-MOSLAVAČKA ŽUPANIJA", "SISAČKO-MOSLAVAČKA ŽUPANIJA"),
    ("KARLOVAČKA ŽUPANIJA", "KARLOVAČKA ŽUPANIJA"),
    ("VARAŽDINSKA ŽUPANIJA", "VARAŽDINSKA ŽUPANIJA"),
    ("KOPRIVNIČKO-KRIŽEVAČKA ŽUPANIJA", "KOPRIVNIČKO-KRIŽEVAČKA ŽUPANIJA"),
    ("BJELOVARSKO-BILOGORSKA ŽUPANIJA", "BJELOVARSKO-BILOGORSKA ŽUPANIJA"),
    ("PRIMORSKO-GORANSKA ŽUPANIJA", "PRIMORSKO-GORANSKA ŽUPANIJA"),
    ("LIČKO-SENJSKA ŽUPANIJA", "LIČKO-SENJSKA ŽUPANIJA"),
    ("VIROVITIČKO-PODRAVSKA ŽUPANIJA", "VIROVITIČKO-PODRAVSKA ŽUPANIJA"),
    ("POŽEŠKO-SLAVONSKA ŽUPANIJA", "POŽEŠKO-SLAVONSKA ŽUPANIJA"),
    ("BRODSKO-POSAVSKA ŽUPANIJA", "BRODSKO-POSAVSKA ŽUPANIJA"),
    ("ZADARSKA ŽUPANIJA", "ZADARSKA ŽUPANIJA"),
    ("OSJEČKO-BARANJSKA ŽUPANIJA", "OSJEČKO-BARANJSKA ŽUPANIJA"),
    ("ŠIBENSKO-KNINSKA ŽUPANIJA", "ŠIBENSKO-KNINSKA ŽUPANIJA"),
    ("VUKOVARSKO-SRIJEMSKA ŽUPANIJA", "VUKOVARSKO-SRIJEMSKA ŽUPANIJA"),
    ("SPLITSKO-DALMATINSKA ŽUPANIJA", "SPLITSKO-DALMATINSKA ŽUPANIJA"),
    ("ISTARSKA ŽUPANIJA", "ISTARSKA ŽUPANIJA"),
    ("DUBROVAČKO-NERETVANSKA ŽUPANIJA", "DUBROVAČKO-NERETVANSKA ŽUPANIJA"),
    ("MEĐIMURSKa ŽUPANIJA", "MEĐIMURSKA ŽUPANIJA"),
    ("GRAD ZAGREB", "GRAD ZAGREB"),
    ("INOZEMSTVO / NIJE PRIMJENJIVO", "INOZEMSTVO / NIJE PRIMJENJIVO")
    ]

    clientTypes = [
    ("Fizička osoba", "Fizička osoba"),
    ("Pravna osoba", "Pravna osoba"),
    ]

    vatcountry = ["AF", "AX", "AL", "DZ", "AS", "AD", "AO", "AI", "AQ", "AG", "AR",
    "AM", "AW", "AU", "AT", "AZ", "BS", "BH", "BD", "BB", "BY", "BE",
    "BZ", "BJ", "BM", "BT", "BO", "BQ", "BA", "BW", "BV", "BR", "IO",
    "BN", "BG", "BF", "BI", "CV", "KH", "CM", "CA", "KY", "CF", "TD",
    "CL", "CN", "CX", "CC", "CO", "KM", "CG", "CD", "CK", "CR", "CI",
    "HR", "CU", "CW", "CY", "CZ", "DK", "DJ", "DM", "DO", "EC", "EG",
    "SV", "GQ", "ER", "EE", "ET", "FK", "FO", "FJ", "FI", "FR", "GF",
    "PF", "TF", "GA", "GM", "GE", "DE", "GH", "GI", "GR", "GL", "GD",
    "GP", "GU", "GT", "GG", "GN", "GW", "GY", "HT", "HM", "VA", "HN",
    "HK", "HU", "IS", "IN", "ID", "IR", "IQ", "IE", "IM", "IL", "IT",
    "JM", "JP", "JE", "JO", "KZ", "KE", "KI", "KP", "KR", "KW", "KG",
    "LA", "LV", "LB", "LS", "LR", "LY", "LI", "LT", "LU", "MO", "MK",
    "MG", "MW", "MY", "MV", "ML", "MT", "MH", "MQ", "MR", "MU", "YT",
    "MX", "FM", "MD", "MC", "MN", "ME", "MS", "MA", "MZ", "MM", "NA",
    "NR", "NP", "NL", "NC", "NZ", "NI", "NE", "NG", "NU", "NF", "MP",
    "NO", "OM", "PK", "PW", "PS", "PA", "PG", "PY", "PE", "PH", "PN",
    "PL", "PT", "PR", "QA", "RE", "RO", "RU", "RW", "BL", "SH", "KN",
    "LC", "MF", "PM", "VC", "WS", "SM", "ST", "SA", "SN", "RS", "SC",
    "SL", "SG", "SX", "SK", "SI", "SB", "SO", "ZA", "GS", "SS", "ES",
    "LK", "SD", "SR", "SJ", "SZ", "SE", "CH", "SY", "TW", "TJ", "TZ",
    "TH", "TL", "TG", "TK", "TO", "TT", "TN", "TR", "TM", "TC", "TV",
    "UG", "UA", "AE", "GB", "US", "UM", "UY", "UZ", "VU", "VE", "VN",
    "VG", "VI", "WF", "EH", "YE", "ZM", "ZW"]

    clientName = models.CharField(null=True, blank=False, max_length=200)
    addressLine1 = models.CharField(null=True, blank=False, max_length=200)
    town = models.CharField(null=True, blank=False, max_length=200)
    province = models.CharField(choices=PROVINCES, blank=False, max_length=100)
    postalCode = models.CharField(null=True, blank=False, max_length=5)
    phoneNumber = models.CharField(null=True, blank=False, max_length=40, validators=[validate_phone_number])
    emailAddress = models.CharField(null=True, blank=False, max_length=100)
    clientUniqueId = models.CharField(null=True, blank=False, max_length=4, unique=True, validators=[RegexValidator(r'^\d{4}$', 'Identifikacijski broj klijenta mora sadržavati točno 4 broja.')])
    clientType = models.CharField(choices=clientTypes, blank=False, max_length=40)
    OIB = models.CharField(null=True, blank=True, max_length=11, unique=True, validators=[RegexValidator(r'^\d{11}$', 'OIB mora sadržavati točno 11 broja.')])
    SustavPDVa = models.BooleanField(default=False)
    IBAN = models.CharField(null=True, blank=False, max_length=34)
    uniqueId = models.CharField(null=True, blank=True, max_length=100)
    slug = models.SlugField(max_length=500, unique=True, blank=True, null=True)
    date_created = models.DateTimeField(blank=True, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)
    history = HistoricalRecords()


    def __str__(self):
        # Tekstualna reprezentacija tvrtke
        return '{}'.format(self.clientName)


    def get_absolute_url(self):
        # Vraća URL za detalje tvrtke
        return reverse('settings-detail', kwargs={'slug': self.slug})


    def save(self, *args, **kwargs):
        # Automatsko postavljanje datuma kreiranja, uniqueId i slug-a
        if self.date_created is None:
            self.date_created = timezone.localtime(timezone.now())
        if self.uniqueId is None:
            self.uniqueId = str(uuid4()).split('-')[4]
            self.slug = slugify('{} {}'.format(self.clientName, self.uniqueId))

        self.slug = slugify('{} {}'.format(self.clientName, self.uniqueId))
        self.last_updated = timezone.localtime(timezone.now())

        super(Company, self).save(*args, **kwargs)

class Client(models.Model):
    # Model za klijenta

    PROVINCES = [
    ("ZAGREBAČKA ŽUPANIJA", "ZAGREBAČKA ŽUPANIJA"),
    ("KRAPINSKO-ZAGORSKA ŽUPANIJA", "KRAPINSKO-ZAGORSKA ŽUPANIJA"),
    ("SISAČKO-MOSLAVAČKA ŽUPANIJA", "SISAČKO-MOSLAVAČKA ŽUPANIJA"),
    ("KARLOVAČKA ŽUPANIJA", "KARLOVAČKA ŽUPANIJA"),
    ("VARAŽDINSKA ŽUPANIJA", "VARAŽDINSKA ŽUPANIJA"),
    ("KOPRIVNIČKO-KRIŽEVAČKA ŽUPANIJA", "KOPRIVNIČKO-KRIŽEVAČKA ŽUPANIJA"),
    ("BJELOVARSKO-BILOGORSKA ŽUPANIJA", "BJELOVARSKO-BILOGORSKA ŽUPANIJA"),
    ("PRIMORSKO-GORANSKA ŽUPANIJA", "PRIMORSKO-GORANSKA ŽUPANIJA"),
    ("LIČKO-SENJSKA ŽUPANIJA", "LIČKO-SENJSKA ŽUPANIJA"),
    ("VIROVITIČKO-PODRAVSKA ŽUPANIJA", "VIROVITIČKO-PODRAVSKA ŽUPANIJA"),
    ("POŽEŠKO-SLAVONSKA ŽUPANIJA", "POŽEŠKO-SLAVONSKA ŽUPANIJA"),
    ("BRODSKO-POSAVSKA ŽUPANIJA", "BRODSKO-POSAVSKA ŽUPANIJA"),
    ("ZADARSKA ŽUPANIJA", "ZADARSKA ŽUPANIJA"),
    ("OSJEČKO-BARANJSKA ŽUPANIJA", "OSJEČKO-BARANJSKA ŽUPANIJA"),
    ("ŠIBENSKO-KNINSKA ŽUPANIJA", "ŠIBENSKO-KNINSKA ŽUPANIJA"),
    ("VUKOVARSKO-SRIJEMSKA ŽUPANIJA", "VUKOVARSKO-SRIJEMSKA ŽUPANIJA"),
    ("SPLITSKO-DALMATINSKA ŽUPANIJA", "SPLITSKO-DALMATINSKA ŽUPANIJA"),
    ("ISTARSKA ŽUPANIJA", "ISTARSKA ŽUPANIJA"),
    ("DUBROVAČKO-NERETVANSKA ŽUPANIJA", "DUBROVAČKO-NERETVANSKA ŽUPANIJA"),
    ("MEĐIMURSKA ŽUPANIJA", "MEĐIMURSKA ŽUPANIJA"),
    ("GRAD ZAGREB", "GRAD ZAGREB"),
    ("INOZEMSTVO / NIJE PRIMJENJIVO", "INOZEMSTVO / NIJE PRIMJENJIVO")
    ]

    clientTypes = [
    ("Fizička osoba", "Fizička osoba"),
    ("Pravna osoba", "Pravna osoba"),
    ]

    vatcountry = ["AF", "AX", "AL", "DZ", "AS", "AD", "AO", "AI", "AQ", "AG", "AR",
    "AM", "AW", "AU", "AT", "AZ", "BS", "BH", "BD", "BB", "BY", "BE",
    "BZ", "BJ", "BM", "BT", "BO", "BQ", "BA", "BW", "BV", "BR", "IO",
    "BN", "BG", "BF", "BI", "CV", "KH", "CM", "CA", "KY", "CF", "TD",
    "CL", "CN", "CX", "CC", "CO", "KM", "CG", "CD", "CK", "CR", "CI",
    "HR", "CU", "CW", "CY", "CZ", "DK", "DJ", "DM", "DO", "EC", "EG",
    "SV", "GQ", "ER", "EE", "ET", "FK", "FO", "FJ", "FI", "FR", "GF",
    "PF", "TF", "GA", "GM", "GE", "DE", "GH", "GI", "GR", "GL", "GD",
    "GP", "GU", "GT", "GG", "GN", "GW", "GY", "HT", "HM", "VA", "HN",
    "HK", "HU", "IS", "IN", "ID", "IR", "IQ", "IE", "IM", "IL", "IT",
    "JM", "JP", "JE", "JO", "KZ", "KE", "KI", "KP", "KR", "KW", "KG",
    "LA", "LV", "LB", "LS", "LR", "LY", "LI", "LT", "LU", "MO", "MK",
    "MG", "MW", "MY", "MV", "ML", "MT", "MH", "MQ", "MR", "MU", "YT",
    "MX", "FM", "MD", "MC", "MN", "ME", "MS", "MA", "MZ", "MM", "NA",
    "NR", "NP", "NL", "NC", "NZ", "NI", "NE", "NG", "NU", "NF", "MP",
    "NO", "OM", "PK", "PW", "PS", "PA", "PG", "PY", "PE", "PH", "PN",
    "PL", "PT", "PR", "QA", "RE", "RO", "RU", "RW", "BL", "SH", "KN",
    "LC", "MF", "PM", "VC", "WS", "SM", "ST", "SA", "SN", "RS", "SC",
    "SL", "SG", "SX", "SK", "SI", "SB", "SO", "ZA", "GS", "SS", "ES",
    "LK", "SD", "SR", "SJ", "SZ", "SE", "CH", "SY", "TW", "TJ", "TZ",
    "TH", "TL", "TG", "TK", "TO", "TT", "TN", "TR", "TM", "TC", "TV",
    "UG", "UA", "AE", "GB", "US", "UM", "UY", "UZ", "VU", "VE", "VN",
    "VG", "VI", "WF", "EH", "YE", "ZM", "ZW"]

    clientName = models.CharField(null=False, blank=False, max_length=200)
    addressLine1 = models.CharField(null=False, blank=False, max_length=200)
    province = models.CharField(choices=PROVINCES, blank=False, max_length=100)
    postalCode = models.CharField(null=False, blank=False, max_length=5)
    phoneNumber = models.CharField(null=True, blank=True, max_length=40, validators=[validate_phone_number])
    emailAddress = models.CharField(null=False, blank=False, max_length=100)
    clientUniqueId = models.CharField(null=False, blank=False, max_length=4, unique=True, validators=[RegexValidator(r'^\d{4}$', 'Identifikacijski broj klijenta mora sadržavati točno 4 broja.')])
    clientType = models.CharField(choices=clientTypes, blank=False, max_length=40)
    OIB = models.CharField(null=True, blank=True, max_length=11, unique=True, validators=[RegexValidator(r'^\d{11}$', 'OIB mora sadržavati točno 11 broja.')])
    VATID = models.CharField(null=False, blank=False, max_length=13, unique=True, validators=[RegexValidator(r'^[A-Za-z0-9]{13}$', 'Porezni identifikacijski broj mora sadržavati točno 13 karaktera, prva dva karaktera moraju biti identifikatori države, a ostalih 11 karaktera moraju biti brojevi koji označavaju entitet.')])
    SustavPDVa = models.BooleanField(default=False)
    IBAN = models.CharField(null=True, blank=False, max_length=34)
    uniqueId = models.CharField(null=True, blank=True, max_length=100)
    slug = models.SlugField(max_length=500, unique=True, blank=True, null=True)
    date_created = models.DateTimeField(blank=True, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)
    history = HistoricalRecords()


    def __str__(self):
        # Tekstualna reprezentacija klijenta
        return '{}'.format(self.clientName)


    def get_absolute_url(self):
        # Vraća URL za detalje klijenta
        return reverse('client-detail', kwargs={'slug': self.slug})


    def save(self, *args, **kwargs):
        # Automatsko postavljanje datuma kreiranja, uniqueId i slug-a
        if self.date_created is None:
            self.date_created = timezone.localtime(timezone.now())
        if self.uniqueId is None:
            self.uniqueId = str(uuid4()).split('-')[4]
            self.slug = slugify('{} {}'.format(self.clientName, self.VATID))

        self.slug = slugify('{} {}'.format(self.clientName, self.VATID))
        self.last_updated = timezone.localtime(timezone.now())
        

        super(Client, self).save(*args, **kwargs)



class Product(models.Model):
    # Model za proizvod/uslugu
    CURRENCY = [
    ('€', 'EUR'),
    ('$', 'USD'),
    ('£', 'GBP'),
    ]

    title = models.CharField(null=False, blank=False, max_length=100)
    description = models.TextField(null=True, blank=True)
    price = models.FloatField(null=False, blank=False)
    currency = models.CharField(choices=CURRENCY, default='€', max_length=100)
    taxPercent = models.FloatField(null=False, blank=False, default=25)
    barid = models.CharField(null=False, blank=False, max_length=100)

    uniqueId = models.CharField(null=True, blank=True, max_length=100)
    slug = models.SlugField(max_length=500, unique=True, blank=True, null=True)
    date_created = models.DateTimeField(blank=True, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)
    history = HistoricalRecords()

    def price_with_vat(self):
        # Izračunava cijenu s PDV-om
        return round(self.price * (1+(self.taxPercent/100)), 2)
    
    def __str__(self):
        # Tekstualna reprezentacija proizvoda
        return '{} {}'.format(self.barid, self.title)


    def get_absolute_url(self):
        # Vraća URL za detalje proizvoda
        return reverse('product-detail', kwargs={'slug': self.slug})

    def get_currency_code(self):
        # Vraća kod valute
        currency_dict = dict((x, y) for x, y in self.CURRENCY)
        return currency_dict.get(self.currency)

    def save(self, *args, **kwargs):
        # Automatsko postavljanje datuma kreiranja, uniqueId i slug-a
        if self.date_created is None:
            self.date_created = timezone.localtime(timezone.now())
        if self.uniqueId is None:
            self.uniqueId = str(uuid4()).split('-')[4]
            self.slug = slugify('{} {}'.format(self.title, self.uniqueId))

        self.slug = slugify('{} {}'.format(self.title, self.uniqueId))
        self.last_updated = timezone.localtime(timezone.now())

        super(Product, self).save(*args, **kwargs)


class Offer(models.Model):
    # Model za ponudu
    title = models.CharField(null=True, blank=True, max_length=30)
    number = models.CharField(null=False, blank=False, max_length=20, validators=[MinValueValidator(6, 'Broj računa mora sadržavati više od 5 karaktera.')])
    dueDate = models.DateField(null=True, blank=False)
    notes = models.TextField(null=True, blank=True)
    client = models.ForeignKey(Client, blank=False, null=False, on_delete=models.DO_NOTHING)
    subject = models.ForeignKey(Company, blank=False, null=False, on_delete=models.DO_NOTHING)
    uniqueId = models.CharField(null=True, blank=True, max_length=100, unique=True)
    slug = models.SlugField(max_length=500, unique=True, blank=True, null=True)
    date_created = models.DateTimeField(blank=False, null=True)
    date = models.DateField(blank=False, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)
    history = HistoricalRecords()

    def poziv_na_broj(self):
        # Generira poziv na broj za ponudu
        return "HR 00 "  + " " + self.client.clientUniqueId + "-" + self.number.replace('/', '-')
    
    def reference(self):
        # Generira referencu za ponudu
        return self.number.replace('/', '-')

    def __str__(self):
        # Tekstualna reprezentacija ponude
        return '{} {}'.format(self.title, self.uniqueId)

    def save(self, *args, **kwargs):
        # Automatsko postavljanje datuma kreiranja, uniqueId i slug-a
        if self.date_created is None:
            self.date_created = timezone.localtime(timezone.now())
        if self.uniqueId is None:
            self.uniqueId = str(uuid4()).split('-')[4]
            self.slug = slugify('{} {}'.format(self.title, self.uniqueId))

        self.slug = slugify('{} {}'.format(self.title, self.uniqueId))
        self.last_updated = timezone.localtime(timezone.now())

        super(Offer, self).save(*args, **kwargs)

    def pretax(self):
        # Izračunava iznos ponude bez PDV-a
        ofrprdt = OfferProduct.objects.filter(offer=self)
        return round(sum(offer_product.pretotal() for offer_product in ofrprdt), 2)
    
    def price_with_vat(self):
        # Izračunava ukupan iznos ponude s PDV-om
        ofrprdt = OfferProduct.objects.filter(offer=self)
        return round(sum(offer_product.total() for offer_product in ofrprdt), 2)
    
    def tax(self):
        # Izračunava ukupan iznos PDV-a za ponudu
        ofrprdt = OfferProduct.objects.filter(offer=self)
        return round(sum(offer_product.tax() for offer_product in ofrprdt), 2)
    
    def curr(self):
        # Vraća simbol valute prvog proizvoda na ponudi
        first_product = OfferProduct.objects.filter(offer=self).first()
        return first_product.product.currency
    
    def currtext(self):
        # Vraća kod valute prvog proizvoda na ponudi
        first_product = OfferProduct.objects.filter(offer=self).first()
        return first_product.product.get_currency_code()
        
    def total100(self):
        # Vraća ukupan iznos ponude u centima
        return self.price_with_vat() * 100
    
    def tolrabat(self):
        # Izračunava ukupan iznos rabata za ponudu
        ofrprdt = OfferProduct.objects.filter(offer=self, rabat__gt=0)
        return round(sum((Decimal(offer_product.product.price) * Decimal(offer_product.quantity) * Decimal(offer_product.rabat/100)) for offer_product in ofrprdt), 2)

    def toldiscount(self):
        # Izračunava ukupan iznos popusta za ponudu
        ofrprdt = OfferProduct.objects.filter(offer=self, discount__gt=0)
        return round(sum((Decimal(offer_product.product.price) * Decimal(offer_product.quantity) * Decimal(offer_product.discount/100)) for offer_product in ofrprdt), 2)
    
    def hasDiscount(self):
        # Provjerava ima li ponuda popust
        ofrprdt = OfferProduct.objects.filter(offer=self, discount__gt=0)
        if ofrprdt:
            return True
        else:
            return False
        
    def hasRabat(self):
        # Provjerava ima li ponuda rabat
        ofrprdt = OfferProduct.objects.filter(offer=self, rabat__gt=0)
        if ofrprdt:
            return True
        else:
            return False



class Invoice(models.Model):
    # Model za račun
    title = models.CharField(null=True, blank=True, max_length=30)
    number = models.CharField(null=False, blank=False, max_length=20, validators=[MinLengthValidator(6, 'Broj računa mora sadržavati više od 5 karaktera.')])
    dueDate = models.DateField(null=True, blank=False)
    notes = models.TextField(null=True, blank=True)
    client = models.ForeignKey(Client, blank=False, null=False, on_delete=models.DO_NOTHING)
    subject = models.ForeignKey(Company, blank=False, null=False, on_delete=models.DO_NOTHING)
    uniqueId = models.CharField(null=True, blank=True, max_length=100, unique=True)
    slug = models.SlugField(max_length=500, unique=True, blank=True, null=True)
    date_created = models.DateTimeField(blank=False, null=True)
    date = models.DateField(blank=False, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)
    history = HistoricalRecords()

    def poziv_na_broj(self):
        # Generira poziv na broj za račun
        return "HR 00 "  + " " + self.client.clientUniqueId + "-" + self.number.replace('/', '-')
    
    def reference(self):
        # Generira referencu za račun
        return self.number.replace('/', '-')

    def __str__(self):
        # Tekstualna reprezentacija računa
        return '{} {}'.format(self.title, self.uniqueId)

    def save(self, *args, **kwargs):
        # Automatsko postavljanje datuma kreiranja, uniqueId i slug-a
        if self.date_created is None:
            self.date_created = timezone.localtime(timezone.now())
        if self.uniqueId is None:
            self.uniqueId = str(uuid4()).split('-')[4]
            self.slug = slugify('{} {}'.format(self.title, self.uniqueId))

        self.slug = slugify('{} {}'.format(self.title, self.uniqueId))
        self.last_updated = timezone.localtime(timezone.now())

        super(Invoice, self).save(*args, **kwargs)

    def pretax(self):
        # Izračunava iznos računa bez PDV-a
        invprdt = InvoiceProduct.objects.filter(invoice=self)
        return round(sum(invoice_product.pretotal() for invoice_product in invprdt), 2)
    
    def price_with_vat(self):
        # Izračunava ukupan iznos računa s PDV-om
        invprdt = InvoiceProduct.objects.filter(invoice=self)
        return round(sum(invoice_product.total() for invoice_product in invprdt), 2)
    
    def tax(self):
        # Izračunava ukupan iznos PDV-a za račun
        invprdt = InvoiceProduct.objects.filter(invoice=self)
        return round(sum(invoice_product.tax() for invoice_product in invprdt), 2)
    
    def curr(self):
        # Vraća simbol valute prvog proizvoda na računu
        first_product = InvoiceProduct.objects.filter(invoice=self).first()
        return first_product.product.currency
    
    def currtext(self):
        # Vraća kod valute prvog proizvoda na računu
        first_product = InvoiceProduct.objects.filter(invoice=self).first()
        return first_product.product.get_currency_code()
        
    def total100(self):
        # Vraća ukupan iznos računa u centima
        return self.price_with_vat() * 100
    
    def tolrabat(self):
        # Izračunava ukupan iznos rabata za račun
        invprdt = InvoiceProduct.objects.filter(invoice=self, rabat__gt=0)
        return round(sum((Decimal(invoice_product.product.price) * Decimal(invoice_product.quantity) * (Decimal(invoice_product.rabat)/Decimal(100))) for invoice_product in invprdt), 2)

    def toldiscount(self):
        # Izračunava ukupan iznos popusta za račun
        invprdt = InvoiceProduct.objects.filter(invoice=self, discount__gt=0)
        return round(sum((Decimal(invoice_product.product.price) * Decimal(invoice_product.quantity) * (Decimal(invoice_product.discount)/Decimal(100))) for invoice_product in invprdt), 2)
    
    def hasDiscount(self):
        # Provjerava ima li račun popust
        invprdt = InvoiceProduct.objects.filter(invoice=self, discount__gt=0)
        if invprdt:
            return True
        else:
            return False
    
    def hasRabat(self):
        # Provjerava ima li račun rabat
        invprdt = InvoiceProduct.objects.filter(invoice=self, rabat__gt=0)
        if invprdt:
            return True
        else:
            return False
class Inventory(models.Model):
    # Model za inventar
    title= models.CharField(null=True, blank=True, max_length=100)
    quantity = models.FloatField(null=True, blank=True)
    subject = models.ForeignKey(Company, blank=True, null=True, on_delete=models.SET_NULL)
    date_created = models.DateTimeField(blank=True, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)
    history = HistoricalRecords()

    def __str__(self):
        # Tekstualna reprezentacija stavke inventara
        return '{} {}'.format(self.title, self.quantity)

    def save(self, *args, **kwargs):
        # Automatsko postavljanje datuma kreiranja i ažuriranja
        if self.date_created is None:
            self.date_created = timezone.localtime(timezone.now())
        self.last_updated = timezone.localtime(timezone.now())

        super(Inventory, self).save(*args, **kwargs)

class InvoiceProduct(models.Model):
    # Model za stavku računa (proizvod na računu)
    product = models.ForeignKey(to=Product, on_delete=models.CASCADE)
    invoice = models.ForeignKey(to=Invoice, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=False, default=0)
    discount = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True, default=0)
    rabat = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True, default=0)
    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        # Sprema stavku računa
        super().save(*args, **kwargs)

    def pretotal(self):
        # Izračunava iznos stavke prije PDV-a, uzimajući u obzir rabat i popust
        if self.rabat and self.discount:
            return round(Decimal(self.product.price) * Decimal(self.quantity) * (1 - Decimal(self.rabat)/100) * (1 - Decimal(self.discount)/100), 2)
        elif self.rabat:
            return round(Decimal(self.product.price) * Decimal(self.quantity) * (1 - Decimal(self.rabat)/100), 2)
        elif self.discount:
            return round(Decimal(self.product.price) * Decimal(self.quantity) * (1 - Decimal(self.discount)/100), 2)
        else:
            return round(Decimal(self.product.price) * Decimal(self.quantity), 2)

    def total(self):
        # Izračunava ukupan iznos stavke s PDV-om
        return round(self.pretotal() * (Decimal(self.product.taxPercent)/100+1), 2)

    def tax(self):
        # Izračunava iznos PDV-a za stavku
        return round((Decimal(self.pretotal()) * (1 + Decimal(self.product.taxPercent)/100))-Decimal(self.pretotal()), 2)

    def curr(self):
        # Vraća simbol valute proizvoda
        return self.product.currency

class OfferProduct(models.Model):
    # Model za stavku ponude (proizvod na ponudi)
    product = models.ForeignKey(to=Product, on_delete=models.CASCADE)
    offer = models.ForeignKey(to=Offer, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=6, decimal_places=3, null=False, blank=False, default=1)
    discount = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    rabat = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        # Sprema stavku ponude
        super().save(*args, **kwargs)

    def pretotal(self):
        # Izračunava iznos stavke prije PDV-a, uzimajući u obzir rabat i popust
        if self.rabat and self.discount:
            return round(Decimal(self.product.price) * Decimal(self.quantity) * (1 - Decimal(self.rabat)/100) * (1 - Decimal(self.discount)/100), 2)
        elif self.rabat:
            return round(Decimal(self.product.price) * Decimal(self.quantity) * (1 - Decimal(self.rabat)/100), 2)
        elif self.discount:
            return round(Decimal(self.product.price) * Decimal(self.quantity) * (1 - Decimal(self.discount)/100), 2)
        else:
            return round(Decimal(self.product.price) * Decimal(self.quantity), 2)

    def total(self):
        # Izračunava ukupan iznos stavke s PDV-om
        return round(self.pretotal() * (Decimal(self.product.taxPercent)/100+1), 2)

    def tax(self):
        # Izračunava iznos PDV-a za stavku
        return round((Decimal(self.pretotal()) * (1 + Decimal(self.product.taxPercent)/100))-Decimal(self.pretotal()), 2)

    def curr(self):
        # Vraća simbol valute proizvoda
        return self.product.currency

#class inventory(models.Model): # Zakomentirani model inventara - mogućnosti live stocka u budućnosti
#    product = models.ForeignKey(Product, blank=True, null=True, on_delete=models.SET_NULL)
#    quantity = models.FloatField(null=True, blank=True)
#    date_created = models.DateTimeField(blank=True, null=True)
#    last_updated = models.DateTimeField(blank=True, null=True)
#
#    def __str__(self):
#        return '{} {}'.format(self.product, self.quantity)
#
#    def save(self, *args, **kwargs):
#        if self.date_created is None:
#            self.date_created = timezone.localtime(timezone.now)
#        self.last_updated = timezone.localtime(timezone.now)
#
#        super(inventory, self).save(*args, **kwargs)

class Supplier(models.Model):    
    # Model za dobavljača
    PROVINCES = [
    ("ZAGREBAČKA ŽUPANIJA", "ZAGREBAČKA ŽUPANIJA"),
    ("KRAPINSKO-ZAGORSKA ŽUPANIJA", "KRAPINSKO-ZAGORSKA ŽUPANIJA"),
    ("SISAČKO-MOSLAVAČKA ŽUPANIJA", "SISAČKO-MOSLAVAČKA ŽUPANIJA"),
    ("KARLOVAČKA ŽUPANIJA", "KARLOVAČKA ŽUPANIJA"),
    ("VARAŽDINSKA ŽUPANIJA", "VARAŽDINSKA ŽUPANIJA"),
    ("KOPRIVNIČKO-KRIŽEVAČKA ŽUPANIJA", "KOPRIVNIČKO-KRIŽEVAČKA ŽUPANIJA"),
    ("BJELOVARSKO-BILOGORSKA ŽUPANIJA", "BJELOVARSKO-BILOGORSKA ŽUPANIJA"),
    ("PRIMORSKO-GORANSKA ŽUPANIJA", "PRIMORSKO-GORANSKA ŽUPANIJA"),
    ("LIČKO-SENJSKA ŽUPANIJA", "LIČKO-SENJSKA ŽUPANIJA"),
    ("VIROVITIČKO-PODRAVSKA ŽUPANIJA", "VIROVITIČKO-PODRAVSKA ŽUPANIJA"),
    ("POŽEŠKO-SLAVONSKA ŽUPANIJA", "POŽEŠKO-SLAVONSKA ŽUPANIJA"),
    ("BRODSKO-POSAVSKA ŽUPANIJA", "BRODSKO-POSAVSKA ŽUPANIJA"),
    ("ZADARSKA ŽUPANIJA", "ZADARSKA ŽUPANIJA"),
    ("OSJEČKO-BARANJSKA ŽUPANIJA", "OSJEČKO-BARANJSKA ŽUPANIJA"),
    ("ŠIBENSKO-KNINSKA ŽUPANIJA", "ŠIBENSKO-KNINSKA ŽUPANIJA"),
    ("VUKOVARSKO-SRIJEMSKA ŽUPANIJA", "VUKOVARSKO-SRIJEMSKA ŽUPANIJA"),
    ("SPLITSKO-DALMATINSKA ŽUPANIJA", "SPLITSKO-DALMATINSKA ŽUPANIJA"),
    ("ISTARSKA ŽUPANIJA", "ISTARSKA ŽUPANIJA"),
    ("DUBROVAČKO-NERETVANSKA ŽUPANIJA", "DUBROVAČKO-NERETVANSKA ŽUPANIJA"),
    ("MEĐIMURSKA ŽUPANIJA", "MEĐIMURSKA ŽUPANIJA"),
    ("GRAD ZAGREB", "GRAD ZAGREB"),
    ("INOZEMSTVO / NIJE PRIMJENJIVO", "INOZEMSTVO / NIJE PRIMJENJIVO")
    ]

    businessTypes = [
    ("Fizička osoba", "Fizička osoba"),
    ("Pravna osoba", "Pravna osoba"),
    ]

    supplierName = models.CharField(verbose_name="Naziv", null=False, blank=False, max_length=200)
    addressLine1 = models.CharField(verbose_name="Adresa", null=False, blank=False, max_length=200, default="")
    town = models.CharField(verbose_name="Grad", null=False, blank=False, max_length=100, default="")
    province = models.CharField(verbose_name="Županija", choices=PROVINCES, blank=False, max_length=100, default="GRAD ZAGREB")
    postalCode = models.CharField(verbose_name="Poštanski broj", null=False, blank=False, max_length=5, default="10000")
    phoneNumber = models.CharField(verbose_name="Telefonski broj", null=True, blank=True, max_length=40, validators=[validate_phone_number])
    emailAddress = models.EmailField(verbose_name="E-pošta", null=True, blank=True, max_length=100)
    businessType = models.CharField(verbose_name="Vrsta osobe", choices=businessTypes, blank=False, max_length=40, default="Pravna osoba")
    OIB = models.CharField(verbose_name="OIB", null=True, blank=True, max_length=11, validators=[RegexValidator(r'^\d{11}$', 'OIB must contain exactly 11 digits.')])
    IBAN = models.CharField(verbose_name="IBAN", null=True, blank=True, max_length=34)
    notes = models.TextField(verbose_name="Bilješke", null=True, blank=True)
    
    history = HistoricalRecords()
    
    uniqueId = models.CharField(null=True, blank=True, max_length=100)
    slug = models.SlugField(max_length=500, unique=True, blank=True, null=True)
    date_created = models.DateTimeField(verbose_name="Date Created", blank=True, null=True)
    last_updated = models.DateTimeField(verbose_name="Last Updated", blank=True, null=True)

    class Meta:
        verbose_name = "Dobavljač"
        verbose_name_plural = "Dobavljači"
        ordering = ['supplierName']

    def __str__(self):
        # Tekstualna reprezentacija dobavljača
        return '{}'.format(self.supplierName)

    def get_absolute_url(self):
        # Vraća URL za detalje dobavljača
        return reverse('supplier_detail', kwargs={'slug': self.slug})

    def save(self, *args, **kwargs):
        # Automatsko postavljanje datuma kreiranja, uniqueId i slug-a
        if self.date_created is None:
            self.date_created = timezone.localtime(timezone.now())
        if self.uniqueId is None:
            self.uniqueId = str(uuid4()).split('-')[4]
            self.slug = slugify('{} {}'.format(self.supplierName, self.uniqueId))

        self.slug = slugify('{} {}'.format(self.supplierName, self.uniqueId))
        self.last_updated = timezone.localtime(timezone.now())

        super(Supplier, self).save(*args, **kwargs)

class Expense(models.Model):
    # Model za trošak
    EXPENSE_CATEGORIES = [
        ('office', 'Uredski troškovi'),
        ('travel', 'Putni troškovi'),
        ('utilities', 'Režije'),
        ('equipment', 'Oprema'),
        ('services', 'Usluge'),
        ('other', 'Ostalo')
    ]

    CURRENCY = [
        ('€', 'EUR'),
        ('$', 'USD'),
        ('£', 'GBP'),
    ]

    title = models.CharField(verbose_name="Naslov", null=False, blank=False, max_length=200)
    amount = models.DecimalField(verbose_name="Ukupan iznos", max_digits=10, decimal_places=2, null=False, blank=False)
    currency = models.CharField(verbose_name="Valuta", choices=CURRENCY, default='€', max_length=3)
    date = models.DateField(verbose_name="Datum", null=False, blank=False)
    category = models.CharField(verbose_name="Kategorija", choices=EXPENSE_CATEGORIES, max_length=50, null=False, blank=False)
    description = models.TextField(verbose_name="Opis", null=True, blank=True)
    subject = models.ForeignKey(Company, verbose_name="Subjekt", blank=False, null=False, on_delete=models.DO_NOTHING)
    supplier = models.ForeignKey(Supplier, verbose_name='Dobavljač', on_delete=models.SET_NULL, null=True, blank=True)
    receipt = models.FileField(verbose_name="Račun (slika/PDF)", upload_to='receipts/', null=True, blank=True)
    uniqueId = models.CharField(null=True, blank=True, max_length=100, unique=True)
    slug = models.SlugField(max_length=500, unique=True, blank=True, null=True)
    date_created = models.DateTimeField(blank=True, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)

    history = HistoricalRecords()

    invoice_number = models.CharField(max_length=30, blank=True, null=True, verbose_name='Broj računa')
    invoice_date = models.DateField(null=True, blank=True, verbose_name='Datum računa')
    
    pretax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    tax_base_0 = models.DecimalField(max_digits=10, decimal_places=2, default=0.0, verbose_name='Porezna osnovica 0%')
    tax_base_5 = models.DecimalField(max_digits=10, decimal_places=2, default=0.0, verbose_name='Porezna osnovica 5%')
    tax_base_13 = models.DecimalField(max_digits=10, decimal_places=2, default=0.0, verbose_name='Porezna osnovica 13%')
    tax_base_25 = models.DecimalField(max_digits=10, decimal_places=2, default=0.0, verbose_name='Porezna osnovica 25%')
    
    tax_5_deductible = models.DecimalField(max_digits=10, decimal_places=2, default=0.0, verbose_name='PDV 5% (odbitni)')
    tax_13_deductible = models.DecimalField(max_digits=10, decimal_places=2, default=0.0, verbose_name='PDV 13% (odbitni)')
    tax_25_deductible = models.DecimalField(max_digits=10, decimal_places=2, default=0.0, verbose_name='PDV 25% (odbitni)')
    tax_5_nondeductible = models.DecimalField(max_digits=10, decimal_places=2, default=0.0, verbose_name='PDV 5% (neodbitni)')
    tax_13_nondeductible = models.DecimalField(max_digits=10, decimal_places=2, default=0.0, verbose_name='PDV 13% (neodbitni)')
    tax_25_nondeductible = models.DecimalField(max_digits=10, decimal_places=2, default=0.0, verbose_name='PDV 25% (neodbitni)')
    
    def total_tax_base(self):
        # Izračunava ukupnu poreznu osnovicu
        return self.tax_base_0 + self.tax_base_5 + self.tax_base_13 + self.tax_base_25
    
    def total_tax_deductible(self):
        # Izračunava ukupan odbitni PDV
        return self.tax_5_deductible + self.tax_13_deductible + self.tax_25_deductible
    
    def total_tax_nondeductible(self):
        # Izračunava ukupan neodbitni PDV
        return self.tax_5_nondeductible + self.tax_13_nondeductible + self.tax_25_nondeductible
    
    def total_tax(self):
        # Izračunava ukupan PDV (odbitni + neodbitni)
        return self.total_tax_deductible() + self.total_tax_nondeductible()
    
    def total_amount(self):
        # Vraća ukupan iznos troška
        return self.amount
    
    class Meta:
        verbose_name = "Trošak"
        verbose_name_plural = "Troškovi"
        ordering = ['-date']

    def __str__(self):
        # Tekstualna reprezentacija troška
        return f'{self.title} - {self.amount} {self.currency}'

    def get_currency_code(self):
        # Vraća kod valute
        currency_dict = dict((x, y) for x, y in self.CURRENCY)
        return currency_dict.get(self.currency)

    def save(self, *args, **kwargs):
        # Automatsko postavljanje datuma kreiranja, uniqueId i slug-a
        if self.date_created is None:
            self.date_created = timezone.localtime(timezone.now())
        if self.uniqueId is None:
            self.uniqueId = str(uuid4()).split('-')[4]
            self.slug = slugify('{} {}'.format(self.title, self.uniqueId))

        self.slug = slugify('{} {}'.format(self.title, self.uniqueId))
        self.last_updated = timezone.localtime(timezone.now())

        super(Expense, self).save(*args, **kwargs)

class Employee(HistoryMixin, models.Model):
    # Model za zaposlenika
    EMPLOYMENT_TYPE_CHOICES = [
        ('full_time', 'Puno radno vrijeme'),
        ('part_time', 'Nepuno radno vrijeme'),
        ('fixed_term', 'Određeno vrijeme'),
        ('student', 'Student'),
        ('contractor', 'Vanjski suradnik'),
    ]
    
    PENSION_PILLAR_CHOICES = [
        (1, 'Samo I. stup (20%)'),
        (2, 'I. i II. stup (15% + 5%)'),
    ]
    
    first_name = models.CharField(max_length=100, verbose_name="Ime")
    last_name = models.CharField(max_length=100, verbose_name="Prezime")
    date_of_birth = models.DateField(verbose_name='Datum rođenja')
    email = models.EmailField(blank=True, null=True, verbose_name='Email')
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name='Telefon')
    oib = models.CharField(max_length=11, verbose_name="OIB", validators=[RegexValidator(r'^\d{11}$', 'OIB mora sadržavati točno 11 znamenki.')])
    address = models.CharField(max_length=255, verbose_name="Adresa")
    city = models.CharField(max_length=100, verbose_name="Grad")
    postal_code = models.CharField(max_length=10, verbose_name="Poštanski broj")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name='Subjekt')
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Satnica (EUR)")
    date_of_employment = models.DateField(verbose_name='Datum zaposlenja')
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, default='full_time', verbose_name='Vrsta zaposlenja')
    job_title = models.CharField(max_length=100, verbose_name='Radno mjesto')
    iban = models.CharField(max_length=34, verbose_name='IBAN')
    
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Satnica (EUR)")
    tax_deduction_coefficient = models.DecimalField(max_digits=5, decimal_places=3, default=1.0, verbose_name='Koeficijent osobnog odbitka')
    work_experience_percentage = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Postotak dodatka za staž (%)", default=0.0)
    annual_vacation_days = models.PositiveIntegerField(default=20, verbose_name="Godišnji odmor (dana)")
    
    pension_pillar = models.IntegerField(choices=PENSION_PILLAR_CHOICES, default=2, 
                                       verbose_name="Mirovinski stup")
    pension_pillar_3 = models.BooleanField(default=False, 
                                         verbose_name="Sudjeluje u III. stupu (dobrovoljno)")
    
    is_active = models.BooleanField(default=True, verbose_name="Aktivan")
    date_created = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()
    
    class Meta:
        verbose_name = "Zaposlenik"
        verbose_name_plural = "Zaposlenici"
        ordering = ['last_name', 'first_name']
    
    def __str__(self):
        # Tekstualna reprezentacija zaposlenika
        return f"{self.first_name} {self.last_name}"
    
    def get_full_name(self):
        # Vraća puno ime zaposlenika
        return f"{self.first_name} {self.last_name}"
    
    def calculate_experience_bonus(self, base_amount):
        # Izračunava dodatak na staž na temelju postotka i osnovice.
        try:
            # Koristimo sigurnu konverziju umjesto ručne
            base = safe_decimal(base_amount)
            percentage = safe_decimal(self.work_experience_percentage)
            
            # Izračun dodatka (postotak / 100 * osnovica)
            factor = percentage / Decimal('100')
            bonus = factor * base
            
            return bonus
        except Exception as e:
            import traceback
            # logger.error(f"Greška u calculate_experience_bonus: {e}", exc_info=True)
            return Decimal('0')
    
    def get_remaining_vacation_days(self, year):
        # Izračunava preostale dane godišnjeg odmora za zaposlenika za danu godinu.
        if not hasattr(self, 'annual_vacation_days'):
            return 0
            
        try:
            # Dohvati sve plaće u traženoj godini
            salaries = Salary.objects.filter(
                employee=self,
                period_year=year
            )
            
            # Koristi polje vacation_days umjesto annual_leave_days_used koje ne postoji
            # Ako je to field koji nedostaje, izračunaj iz vacation_hours
            used_vacation_days = Decimal('0')
            
            for salary in salaries:
                # Ako postoji vacation_days, koristi njega
                if hasattr(salary, 'vacation_days') and salary.vacation_days:
                    used_vacation_days += Decimal(str(salary.vacation_days))
                # Inače, pretvori vacation_hours u dane (pretpostavka: 8 sati = 1 dan)
                elif salary.vacation_hours:
                    used_vacation_days += Decimal(str(salary.vacation_hours)) / Decimal('8.0')
            
            # Vrati preostale dane (ukupno dodijeljeno - iskorišteno)
            return max(0, self.annual_vacation_days - used_vacation_days)
        except Exception as e:
            import traceback
            # Razmisliti o logiranju greške umjesto ispisa
            # logger.error(f"Greška u get_remaining_vacation_days: {e}", exc_info=True)
            return self.annual_vacation_days  # Vrati ukupan broj dana kao fallback
    
    def calculate_tax_deduction(self, year):
        # Izračunava porezni odbitak za zaposlenika za danu godinu
        # 600 EUR je osnovni osobni odbitak od 2025.
        base_deduction = TaxParameter.objects.get(year=year, parameter_type='base_deduction').value
        return base_deduction * self.tax_deduction_coefficient
    
    def get_remaining_vacation_days(self, year):
        # Izračunava preostale dane godišnjeg odmora za zaposlenika za danu godinu.
        if not hasattr(self, 'annual_vacation_days'):
            return 0
            
        # Dohvati sve plaće u traženoj godini
        salaries = Salary.objects.filter(
            employee=self,
            period_year=year
        )
        
        # Koristi polje vacation_days umjesto annual_leave_days_used koje ne postoji
        # Ako je to field koji nedostaje, izračunaj iz vacation_hours
        used_vacation_days = 0
        
        for salary in salaries:
            # Ako postoji vacation_days, koristi njega
            if hasattr(salary, 'vacation_days') and salary.vacation_days:
                used_vacation_days += salary.vacation_days
            # Inače, pretvori vacation_hours u dane (pretpostavka: 8 sati = 1 dan)
            elif hasattr(salary, 'vacation_hours') and salary.vacation_hours:
                used_vacation_days += salary.vacation_days / Decimal('8.0')
        
        # Vrati preostale dane (ukupno dodijeljeno - iskorišteno)
        return max(0, self.annual_vacation_days - used_vacation_days)
    
    def calculate_personal_deduction(self):
        """Izračunava osobni odbitak zaposlenika na temelju poreznih parametara za odgovarajuću godinu."""
        try:
            from django.utils import timezone
            current_year = timezone.now().year
            
            # Dohvati osnovni osobni odbitak iz poreznih parametara
            tax_param = TaxParameter.objects.get(year=current_year, parameter_type='base_deduction')
            base_deduction = tax_param.value
            
            # Izračunaj ukupni osobni odbitak množeći osnovicu s koeficijentom
            return base_deduction * self.tax_deduction_coefficient
        except TaxParameter.DoesNotExist:
            # Ako parametar nije pronađen, logiraj grešku i koristi fallback vrijednost
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Osobni odbitak nije definiran za godinu {current_year}')
            return Decimal('600.00') * self.tax_deduction_coefficient  # Fallback na 600 EUR
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Greška pri izračunu osobnog odbitka: {str(e)}')
            return Decimal('600.00') * self.tax_deduction_coefficient  # Fallback na 600 EUR

    def save(self, *args, **kwargs):
        # Osigurava da je satnica Decimal prije spremanja
        if not isinstance(self.hourly_rate, Decimal):
            self.hourly_rate = Decimal(str(self.hourly_rate))
        super().save(*args, **kwargs)


class Salary(HistoryMixin, models.Model):
    # Model za plaću
    STATUS_CHOICES = [
        ('draft', 'U pripremi'),
        ('final', 'Finalizirano'),
        ('submitted', 'Prijavljeno JOPPD'),
        ('cancelled', 'Stornirano')
    ]
    
    # Postojeća polja
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="salaries", verbose_name="Zaposlenik")
    period_month = models.IntegerField(verbose_name="Mjesec")
    period_year = models.IntegerField(verbose_name="Godina")
    
    # Osnovni elementi
    regular_hours = models.DecimalField(
        verbose_name='Redovni sati',
        max_digits=6,
        decimal_places=2,
        default=0
    )
    vacation_days = models.IntegerField(
        verbose_name='Dani godišnjeg',
        default=0,
        validators=[MinValueValidator(0)]
    )
    vacation_hours = models.DecimalField(
        verbose_name='Sati godišnjeg',
        max_digits=6,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    overtime_hours = models.DecimalField(
        verbose_name='Prekovremeni sati',
        max_digits=6,
        decimal_places=2,
        default=0
    )
    bonus = models.DecimalField(
        verbose_name='Stimulacija',
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=0
    )
    gross_salary = models.DecimalField(
        verbose_name='Bruto plaća',
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    sick_leave_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0, verbose_name="Bolovanje (sati)")
    sick_leave_rate = models.DecimalField(max_digits=4, decimal_places=2, default=0.70, verbose_name="% uobičajene satnice")
    overtime_rate_increase = models.DecimalField(max_digits=4, decimal_places=2, default=0.50, verbose_name="Faktor uvećanja za prekovremeni rad")
    
    # Izračunati elementi
    regular_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Iznos redovnog rada (EUR)")
    vacation_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Iznos GO (EUR)")
    sick_leave_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Iznos bolovanja (EUR)")
    overtime_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Iznos prekovremenih (EUR)")
    experience_bonus_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Dodatak za staž (EUR)")
    
    # Ukupno bruto i neto
    net_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Neto plaća (EUR)")
    
    # Doprinosi
    pension_pillar_1 = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="MIO I. stup (15%)")
    pension_pillar_2 = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="MIO II. stup (5%)")
    health_insurance = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Zdravstveno osiguranje (16.5%)")
    
    # Porez
    income_tax_base = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Osnovica poreza na dohodak")
    tax_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Osobni odbitak")
    income_tax = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Porez na dohodak")
    notes = models.TextField(null=True, blank=True, verbose_name="Napomene")
    # Neoporezive naknade
    non_taxable_payments = models.JSONField(default=dict, blank=True, verbose_name="Neoporezivi primici")
    
    # Status JOPPD
    joppd_status = models.BooleanField(default=False, verbose_name="Prijavljeno u JOPPD")
    joppd_reference = models.CharField(max_length=50, null=True, blank=True, verbose_name="JOPPD referenca")
    
    # Metapodaci
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="created_salaries")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Status i kontrola izmjena
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name="Status"
    )
    
    # Snapshot podataka pri kreiranju
    employee_data = models.JSONField(
        default=dict, 
        verbose_name="Podatci zaposlenika pri obračunu"
    )
    company_data = models.JSONField(
        default=dict, 
        verbose_name="Podatci tvrtke pri obračunu"
    )
    tax_params = models.JSONField(
        default=dict, 
        verbose_name="Porezni parametri pri obračunu"
    )
    history = HistoricalRecords()
    
    payment_date = models.DateField(
        verbose_name='Datum isplate',
        null=True,
        blank=True,
        help_text='Datum isplate plaće'
    )
    
    is_locked = models.BooleanField(
        default=False,
        verbose_name='Zaključano',
        help_text='Zaključane plaće se ne mogu mijenjati'
    )
    
    total_contributions = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0, 
        verbose_name="Ukupni doprinosi (EUR)"
    )

    lower_tax_rate_used = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('20.00'))
    higher_tax_rate_used = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('30.00'))
    lower_tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    higher_tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    @property
    def total_cost(self):
        """Calculate the total cost of the salary including net salary, health insurance, and non-taxable payments."""
        return self.net_salary + self.health_insurance + Decimal(sum(self.non_taxable_payments.values()))

    def sick_rate_100(self):
        return self.sick_leave_rate * Decimal('100')

    def calculate_base_tax_amount(self):
        """Vraća iznos poreza po osnovnoj stopi"""
        return self.lower_tax_amount or Decimal('0.00')
    
    def calculate_higher_bracket_tax_amount(self):
        """Vraća iznos poreza po višoj stopi"""
        return self.higher_tax_amount or Decimal('0.00')

    def calculate_salary(self):
        """Izračunava sve elemente plaće"""
        # Izračunaj osnovne komponente plaće
        self.regular_amount = self.regular_hours * self.employee.hourly_rate
        self.vacation_amount = self.vacation_hours * self.employee.hourly_rate
        self.sick_leave_amount = self.sick_leave_hours * self.employee.hourly_rate * self.sick_leave_rate

        # Izračunaj prekovremeni rad s uvećanjem
        overtime_rate = self.employee.hourly_rate * (1 + self.overtime_rate_increase / Decimal('100'))
        self.overtime_amount = self.overtime_hours * overtime_rate

        # Dodatak za staž
        base_for_seniority = self.regular_amount + self.vacation_amount + self.sick_leave_amount + self.overtime_amount + (self.bonus or Decimal('0'))
        self.experience_bonus_amount = self.employee.calculate_experience_bonus(base_for_seniority)

        # Bruto plaća (bez neoporezivih dodataka)
        self.gross_salary = self.regular_amount + self.vacation_amount + self.sick_leave_amount + self.overtime_amount + (self.bonus or Decimal('0')) + self.experience_bonus_amount

        # Doprinosi
        self.pension_pillar_1 = self.gross_salary * Decimal('0.15')
        self.pension_pillar_2 = self.gross_salary * Decimal('0.05')
        self.health_insurance = round(self.gross_salary, 2) * Decimal('0.165')

        # Izračunaj ukupne doprinose
        self.total_contributions = self.pension_pillar_1 + self.pension_pillar_2

        # Izračunaj dohodak
        income = self.gross_salary - self.total_contributions

        # Izračunaj osobni odbitak
        self.tax_deduction = self.employee.calculate_personal_deduction()
        if self.tax_deduction > income:
            self.tax_deduction = income

        # Izračunaj poreznu osnovicu
        self.income_tax_base = max(income - self.tax_deduction, Decimal('0'))

        # Dohvati porezne stope za grad zaposlenika i godinu obračuna
        try:
            from .utils.salary_calculator import standardize_city_name
            from django.utils import timezone
            
            # Osiguraj da je payment_date_obj tipa datetime.date
            if isinstance(self.payment_date, str):
                try:
                    payment_date_obj = datetime.strptime(self.payment_date, "%Y-%m-%d").date()
                except ValueError:
                    raise ValueError(f"Neispravan format datuma: {self.payment_date}")
            else:
                payment_date_obj = self.payment_date or timezone.now().date()

            year = payment_date_obj.year

            # Dohvati prag poreza
            from .models import TaxParameter, LocalIncomeTax
            threshold_param = TaxParameter.objects.get(parameter_type='monthly_tax_threshold', year=year)
            monthly_threshold = Decimal(str(threshold_param.value))

            # Dohvati lokalne stope
            local_tax = LocalIncomeTax.objects.filter(
                city_name__iexact=standardize_city_name(self.employee.city),
                valid_from__lte=payment_date_obj
            ).latest('valid_from')

            # Spremi korištene porezne stope
            self.lower_tax_rate_used = local_tax.tax_rate_lower
            self.higher_tax_rate_used = local_tax.tax_rate_higher

            # Pretvorba postotaka u decimalne vrijednosti za izračun
            base_tax_rate = self.lower_tax_rate_used / Decimal('100')
            higher_bracket_tax_rate = self.higher_tax_rate_used / Decimal('100')

        except (LocalIncomeTax.DoesNotExist, TaxParameter.DoesNotExist) as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Nisu pronađene porezne stope/prag za {self.employee.city} u {year}. Koristim defaultne stope (20/30%). Greška: {e}")
            self.lower_tax_rate_used = Decimal('20.00')
            self.higher_tax_rate_used = Decimal('30.00')
            base_tax_rate = Decimal('0.20')
            higher_bracket_tax_rate = Decimal('0.30')
            monthly_threshold = Decimal('4200.00')

        # Izračunaj porez na dohodak koristeći spremljene stope
        if self.income_tax_base <= monthly_threshold:
            self.lower_tax_amount = self.income_tax_base * base_tax_rate
            self.higher_tax_amount = Decimal('0.00')
            self.income_tax = self.lower_tax_amount
        else:
            self.lower_tax_amount = monthly_threshold * base_tax_rate
            self.higher_tax_amount = (self.income_tax_base - monthly_threshold) * higher_bracket_tax_rate
            self.income_tax = self.lower_tax_amount + self.higher_tax_amount

        # Izračunaj neto plaću
        self.net_salary = income - self.income_tax

        # Zaokruži sve vrijednosti na dvije decimale
        decimal_fields = ['gross_salary', 'pension_pillar_1', 'pension_pillar_2', 'health_insurance',
                      'tax_deduction', 'income_tax_base', 'income_tax', 'net_salary',
                      'total_contributions', 'lower_tax_amount', 'higher_tax_amount',
                      'lower_tax_rate_used', 'higher_tax_rate_used']
        
        for field in decimal_fields:
            if hasattr(self, field) and getattr(self, field) is not None:
                current_value = getattr(self, field)
                try:
                    setattr(self, field, round(Decimal(str(current_value)), 2))
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Greška pri zaokruživanju polja {field} s vrijednošću {current_value}: {e}")

        # Spremi promjene u bazu
        self.save()

    def lock(self):
        # Zaključaj plaću nakon isplate
        self.is_locked = True
        self.save()

    def finalize(self):
        # Finalizira plaću - nakon toga nije moguća izmjena
        if self.status == 'draft':
            self.status = 'final'
            self.save()

    def submit_joppd(self):
        # Označi da je plaća prijavljena u JOPPD
        if self.status == 'final':
            self.status = 'submitted'
            self.save()

    def get_history_data(self):
        # Formatira podatke iz povijesti za prikaz
        data = {}
        for field in self._meta.fields:
            value = getattr(self, field.name)
            if value is not None:
                if isinstance(value, (datetime, date)):
                    data[field.verbose_name] = value.strftime('%d.m.%Y. %H:%M:%S')
                elif isinstance(value, Decimal):
                    data[field.verbose_name] = f"{value:.2f}"
                elif isinstance(value, get_user_model()):
                    data[field.verbose_name] = value.get_full_name() or value.username
                else:
                    data[field.verbose_name] = str(value)
        return data

    def diff_against(self, old_record):
        # Uspoređuje ovaj zapis s starijom verzijom
        changes = {}
        for field in self._meta.fields:
            if field.name in ['id', 'history_id', 'history_date', 'history_change_reason', 'history_type', 'history_user_id']:
                continue
            
            old_value = getattr(old_record, field.name)
            new_value = getattr(self, field.name)
            
            if old_value != new_value:
                changes[field.verbose_name] = {
                    'old': self._format_field_value(old_value),
                    'new': self._format_field_value(new_value)
                }
        return changes

    def _format_field_value(self, value):
        # Formatira vrijednost polja za prikaz
        if value is None:
            return "(prazno)"
        if isinstance(value, (datetime, date)):
            return value.strftime('%d.m.%Y. %H:%M:%S')
        if isinstance(value, Decimal):
            return f"{value:.2f}"
        if isinstance(value, get_user_model()):
            return value.get_full_name() or value.username
        return str(value)

    def get_lower_tax_amount(self):
        """Vraća ukupni iznos poreza na nižoj poreznoj stopi s nižom poreznom stopom"""
        return self.lower_tax_amount or Decimal('0.00')
    
    def get_higher_tax_amount(self):
        """Vraća ukupni iznos poreza na višoj poreznoj stopi s višom poreznom stopom"""
        return self.higher_tax_amount or Decimal('0.00')


class NonTaxablePaymentType(models.Model):
    # Model za vrstu neoporezivog primitka
    name = models.CharField(max_length=200, verbose_name="Naziv")
    code = models.CharField(max_length=50, verbose_name="Šifra")
    description = models.TextField(blank=True, verbose_name="Opis")
    max_annual_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Maksimalni godišnji iznos (EUR)")
    max_monthly_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Maksimalni mjesečni iznos (EUR)")
    active = models.BooleanField(default=True, verbose_name="Aktivno")
    history = HistoricalRecords()
    
    class Meta:
        verbose_name = "Vrsta neoporezivog primitka"
        verbose_name_plural = "Vrste neoporezivih primitaka"
        ordering = ['name']
    
    def __str__(self):
        # Tekstualna reprezentacija vrste neoporezivog primitka
        if self.max_monthly_amount:
            return f"{self.name} (do {self.max_monthly_amount} EUR mjesečno)"
        elif self.max_annual_amount:
            return f"{self.name} (do {self.max_annual_amount} EUR godišnje)"
        else:
            return self.name


class TaxParameter(models.Model):
    # Model za porezni parametar
    PARAMETER_TYPES = [
        ('base_deduction', 'Osnovni odbitak'),
        ('monthly_tax_threshold', 'Mjesečni porezni prag'),
        ('health_insurance', 'Zdravstveno osiguranje'),
        ('pension_rate_1', 'MIO I. stup'),
        ('pension_rate_2', 'MIO II. stup'),
    ]
    
    parameter_type = models.CharField(
        max_length=30,
        choices=PARAMETER_TYPES,
        verbose_name='Vrsta parametra')
    value = models.DecimalField(max_digits=10, decimal_places=6, verbose_name='Vrijednost')
    year = models.IntegerField(verbose_name='Godina')
    description = models.CharField(max_length=255, null=True, blank=True, verbose_name='Opis')
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Datum kreiranja')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Datum izmjene')
    
    class Meta:

        verbose_name = 'Porezni parametar'
        verbose_name_plural = 'Porezni parametri'
        unique_together = ['parameter_type', 'year']
    
    def __str__(self):
        return f"{self.get_parameter_type_display()} ({self.year}): {self.value}"
    history = HistoricalRecords()


class LocalIncomeTax(models.Model):
    # Model za lokalnu poreznu stopu
    CITY_TYPE_CHOICES = [
        ('OPCINA', 'Općina'),
        ('GRAD', 'Grad'),
        ('VELIKI_GRAD', 'Veliki grad ili sjedište županije'),
        ('ZAGREB', 'Grad Zagreb'),
    ]
    
    city_name = models.CharField(max_length=200, unique=True, verbose_name="Ime grada/općine")
    city_code = models.CharField(max_length=10, blank=True, null=True, verbose_name="Šifra grada/općine")
    city_type = models.CharField(max_length=20, choices=CITY_TYPE_CHOICES, default='GRAD', verbose_name="Vrsta JLS")
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Stopa prireza (do 2024.)")
    tax_rate_lower = models.DecimalField(max_digits=5, decimal_places=2, default=20.00, verbose_name="Niža stopa poreza")
    tax_rate_higher = models.DecimalField(max_digits=5, decimal_places=2, default=30.00, verbose_name="Viša stopa poreza")
    valid_from = models.DateField(default=timezone.now, verbose_name="Vrijedi od")
    valid_until = models.DateField(null=True, blank=True, verbose_name="Vrijedi do")
    account_number = models.CharField(max_length=50, blank=True, null=True, verbose_name="Uplatni račun")
    official_gazette = models.CharField(max_length=20, blank=True, null=True, verbose_name="Broj NN")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Lokalna porezna stopa"
        verbose_name_plural = "Lokalne porezne stope"

    def __str__(self):
        # Tekstualna reprezentacija lokalne porezne stope
        return f"{self.city_name} - {self.tax_rate_lower}%/{self.tax_rate_higher}%"

    def get_rate_limits_2025(self):
        # Vraća limite poreznih stopa za 2025. ovisno o vrsti JLS
        if self.city_type == 'OPCINA':
            return {'lower_min': 15, 'lower_max': 20, 'higher_min': 25, 'higher_max': 30}
        elif self.city_type == 'GRAD':
            return {'lower_min': 15, 'lower_max': 21, 'higher_min': 25, 'higher_max': 31}
        elif self.city_type == 'VELIKI_GRAD':
            return {'lower_min': 15, 'lower_max': 22, 'higher_min': 25, 'higher_max': 32}
        elif self.city_type == 'ZAGREB':
            return {'lower_min': 15, 'lower_max': 23, 'higher_min': 25, 'higher_max': 33}
        else:
            return {'lower_min': 15, 'lower_max': 20, 'higher_min': 25, 'higher_max': 30}
        
    def save(self, *args, **kwargs):
        # Formatira šifru grada/općine prije spremanja
        if self.city_code and isinstance(self.city_code, str):
            digits_only = ''.join(c for c in self.city_code if c.isdigit())
            self.city_code = digits_only.zfill(5)
        super().save(*args, **kwargs)
