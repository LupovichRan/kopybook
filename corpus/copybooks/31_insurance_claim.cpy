      * synthetic insurance claim with a variable number of lines
       01  INS-CLAIM.
           05  IC-HEADER.
               10  IC-CLAIM-NO    PIC X(14).
               10  IC-POLICY-NO   PIC X(12).
               10  IC-LOSS-DATE   PIC 9(8).
               10  IC-LOSS-PARTS  REDEFINES IC-LOSS-DATE.
                   15  IC-LOSS-YY PIC 9(4).
                   15  IC-LOSS-MM PIC 99.
                   15  IC-LOSS-DD PIC 99.
               10  IC-STATUS      PIC X.
                   88  IC-OPEN    VALUE 'O'.
                   88  IC-CLOSED  VALUE 'C'.
           05  IC-RESERVE         PIC S9(9)V99 COMP-3.
           05  IC-LINE-CNT        PIC S9(4) COMP.
           05  IC-LINES OCCURS 0 TO 10 TIMES DEPENDING ON IC-LINE-CNT.
               10  IC-LN-TYPE     PIC XX.
               10  IC-LN-AMOUNT   PIC S9(7)V99 COMP-3.
               10  IC-LN-DESC     PIC X(20).
