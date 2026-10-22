      * variable-location items after an ODO table (IBM extension)
       01  VARLOC-REC.
           05  HDR-ID             PIC X(4).
           05  N-NOTES            PIC 9.
           05  NOTE-TEXT          PIC X(10) OCCURS 0 TO 5 DEPENDING ON
                                  N-NOTES.
           05  AFTER-AMOUNT       PIC S9(5)V99 COMP-3.
           05  AFTER-CODE         PIC X(3).
