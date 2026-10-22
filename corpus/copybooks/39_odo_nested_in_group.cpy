      * ODO table inside a subgroup, with a sibling after the subgroup
       01  PORTFOLIO-REC.
           05  PF-ID              PIC X(8).
           05  PF-HOLDINGS.
               10  PF-N           PIC S9(3) COMP-3.
               10  PF-POSITION OCCURS 0 TO 6 DEPENDING ON PF-N.
                   15  PF-SYMBOL  PIC X(6).
                   15  PF-QTY     PIC S9(9) COMP.
                   15  PF-PRICE   PIC S9(5)V9(4) COMP-3.
           05  PF-AS-OF           PIC 9(8).
