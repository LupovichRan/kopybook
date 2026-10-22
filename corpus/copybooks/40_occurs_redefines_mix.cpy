      * OCCURS inside a REDEFINES alternative
       01  MIX-REC.
           05  MX-KIND            PIC X.
           05  MX-AREA            PIC X(24).
           05  MX-TABLE REDEFINES MX-AREA.
               10  MX-CELL        PIC S9(5) COMP-3 OCCURS 8 TIMES.
           05  MX-PAIRS REDEFINES MX-AREA.
               10  MX-PAIR OCCURS 4 TIMES.
                   15  MX-K       PIC XX.
                   15  MX-V       PIC 9(4).
