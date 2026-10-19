# Promotion names in fixed-size EXE fields, by promotion index: the real
# promotions instead of the in-game stand-ins.
# Short names stay within 5 cells (the longest Japanese short name).
# Full names: 15 x 26 bytes at 0x80049054; short: 15 x 14 bytes at 0x800491DC.
FULL_AT, FULL_SIZE = 0x80049054, 26
SHORT_AT, SHORT_SIZE = 0x800491DC, 14
NAMES = [  # (full, short): the real promotions the in-game names stand for
    ("New Japan", "NJPW"),          # VIEW JAPAN
    ("All Japan", "AJPW"),          # OLIVE JAPAN
    ("FMW", "FMW"),                 # IW New Generation
    ("WAR", "WAR"),                 # R.Y.U
    ("Michinoku Pro", "M-Pro"),     # Yukiguni Puroresu
    ("WCW", "WCW"),                 # WWC Puroresu
    ("WWF", "WWF"),                 # WFW Puroresu
    ("RINGS", "RINGS"),             # Gongs
    ("K-1", "K-1"),                 # S-1 (its wrestlers are the K-1 fighters)
    ("BattlArts", "B-Arts"),        # Fighting Expedition 'Battlation'
    ("Pancrase", "Panc."),          # High Class
    ("AAA", "AAA"),                 # THREE A
    ("Shoot Fighters", "Shoot"),    # Kakutouka
    ("Freelance", "FREE"),          # FREE
    ("Legends", "Legend"),          # LEGEND
]
# The game's own names, for the fake-names build (build.py --fake-names). VIEW JAPAN
# and OLIVE JAPAN are in mixed case: in capitals they no longer fit story lines.
FAKE_NAMES = [
    ("View Japan", "VJP"),
    ("Olive Japan", "OJP"),
    ("New IW", "New IW"),
    ("R.Y.U", "R.Y.U"),
    ("Yukiguni Pro", "YukiPro"),
    ("WWC Pro", "WWC"),
    ("WFW Pro", "WFW"),
    ("GONGS", "GONGS"),
    ("S-1", "S-1"),
    ("Battlation", "Batre"),
    ("High Class", "H.Class"),
    ("THREE-A", "T-A"),
    ("Fighters", "Fighter"),
    ("Freelance", "FREE"),
    ("Legends", "Legend"),
]
