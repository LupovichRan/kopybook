       01  DATE-REC.
           05  EVENT-DATE         PIC 9(8).
           05  EVENT-DATE-PARTS REDEFINES EVENT-DATE.
               10  EV-YYYY        PIC 9(4).
               10  EV-MM          PIC 99.
               10  EV-DD          PIC 99.
           05  EVENT-TIME         PIC 9(6).
