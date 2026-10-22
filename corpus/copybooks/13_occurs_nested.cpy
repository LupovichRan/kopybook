       01  MATRIX-REC.
           05  REGION OCCURS 3 TIMES.
               10  REGION-CODE    PIC XX.
               10  QUARTER OCCURS 4 TIMES.
                   15  SALES      PIC S9(7) COMP-3.
                   15  UNITS      PIC 9(5).
           05  TRAILER            PIC X(4).
