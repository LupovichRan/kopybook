      * USAGE on a group applies to every elementary item inside it
       01  INHERIT-REC.
           05  TOTALS USAGE COMP-3.
               10  T-GROSS        PIC S9(9)V99.
               10  T-TAX          PIC S9(7)V99.
               10  T-NET          PIC S9(9)V99.
           05  COUNTERS COMP.
               10  C-ITEMS        PIC S9(4).
               10  C-LINES        PIC S9(9).
           05  LABEL              PIC X(6).
