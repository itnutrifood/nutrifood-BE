from enum import StrEnum


class Country(StrEnum):
    ARMENIA = "Armenia"


class ArmeniaRegion(StrEnum):
    ARAGATSOTN = "Aragatsotn"
    ARARAT = "Ararat"
    ARMAVIR = "Armavir"
    GEGHARKUNIK = "Gegharkunik"
    KOTAYK = "Kotayk"
    LORI = "Lori"
    SHIRAK = "Shirak"
    SYUNIK = "Syunik"
    TAVUSH = "Tavush"
    VAYOTS_DZOR = "Vayots Dzor"
    YEREVAN = "Yerevan"


class AddressLocationSource(StrEnum):
    MANUAL = "manual"
    YANDEX = "yandex"
