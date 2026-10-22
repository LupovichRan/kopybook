       01  BANK-TXN.
           05  BT-TXN-ID          PIC 9(16).
           05  BT-ACCT            PIC 9(12).
           05  BT-TS.
               10  BT-DATE        PIC 9(8).
               10  BT-TIME        PIC 9(6).
               10  BT-MICROS      PIC 9(6) COMP-3.
           05  BT-TYPE            PIC X(3).
           05  BT-AMOUNT          PIC S9(13)V99 COMP-3.
           05  BT-CURRENCY        PIC X(3).
           05  BT-FX-RATE         PIC 9(3)V9(6) COMP-3.
           05  BT-CHANNEL         PIC S9(4) COMP-5.
           05  BT-MEMO            PIC X(40).
